resource "aws_ecs_cluster" "main" {
  name = local.name
}

resource "aws_security_group" "api" {
  name        = "${local.name}-api"
  description = "Only the public API port, from the allowed address"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Public API"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [var.api_ingress_cidr]
  }

  egress {
    description = "Supabase, Clerk and AWS APIs"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

locals {
  # Secrets live in SSM Parameter Store (SecureString) and reach the containers through the task's `secrets`,
  # so they no longer appear in the task definition. They are still in the local Terraform state.
  secret_names = ["INTERNAL_SERVICE_TOKEN", "DATABASE_URL", "WORKER_DATABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "CLERK_SECRET_KEY"]
  secret_values = {
    INTERNAL_SERVICE_TOKEN    = var.internal_service_token
    DATABASE_URL              = var.database_url
    WORKER_DATABASE_URL       = var.worker_database_url
    SUPABASE_SERVICE_ROLE_KEY = var.supabase_service_role_key
    CLERK_SECRET_KEY          = var.clerk_secret_key
  }
  secret_arns    = { for n in local.secret_names : n => aws_ssm_parameter.secret[n].arn }
  common_secrets = { INTERNAL_SERVICE_TOKEN = local.secret_arns["INTERNAL_SERVICE_TOKEN"] }
  api_secrets    = local.secret_arns

  common_env = {
    ENVIRONMENT = "production"
    LOG_FORMAT  = "json"
    AWS_REGION  = var.region
    S3_BUCKET   = aws_s3_bucket.files.bucket
  }

  api_env = merge(local.common_env, {
    SUPABASE_URL             = var.supabase_url
    CLERK_ISSUER             = var.clerk_issuer
    CLERK_AUTHORIZED_PARTIES = jsonencode([var.web_origin])
    CORS_ORIGINS             = jsonencode([var.web_origin])
    GEOMETRY_URL             = "http://127.0.0.1:8002"
    LANGUAGE_URL             = "http://127.0.0.1:8003"
    BLOB_BACKEND             = "hybrid"
    QUEUE_BACKEND            = "sqs"
    VISION_MODE              = "lambda"
    NOTIFIER                 = "sns"
    SQS_QUEUE_URL            = aws_sqs_queue.jobs.url
    SNS_TOPIC_ARN            = aws_sns_topic.alerts.arn
    VISION_LAMBDA_NAME       = aws_lambda_function.vision.function_name
  })

  # Hybrid parsing tries the rules first. Without LLM_MODEL there is no LLM and the rules answer alone.
  language_env = merge(
    local.common_env,
    {
      COMMAND_PARSER = "hybrid"
      STT_PROVIDER   = var.stt_provider
    },
    var.bedrock_model_id == "" ? {} : { LLM_PROVIDER = "bedrock", LLM_MODEL = var.bedrock_model_id },
  )

  containers = {
    api      = { image = "api", env = local.api_env, secrets = local.api_secrets, command = null, port = 8000 }
    worker   = { image = "api", env = local.api_env, secrets = local.api_secrets, command = ["python", "-m", "app.worker"], port = null }
    geometry = { image = "geometry", env = local.common_env, secrets = local.common_secrets, command = null, port = null }
    language = { image = "language", env = local.language_env, secrets = local.common_secrets, command = null, port = null }
  }
}

resource "aws_ssm_parameter" "secret" {
  for_each = toset(local.secret_names)

  name  = "/${local.name}/${each.key}"
  type  = "SecureString" # standard tier, default aws/ssm key: free
  value = local.secret_values[each.key]
}

resource "aws_ecs_task_definition" "app" {
  family                   = local.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 3072
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    for name, c in local.containers : merge(
      {
        name        = name
        image       = "${aws_ecr_repository.images[c.image].repository_url}:${var.image_tag}"
        essential   = true
        stopTimeout = 120 # the Fargate maximum, so the worker can finish a job after SIGTERM
        environment = [for key, value in c.env : { name = key, value = value }]
        secrets     = [for key, arn in c.secrets : { name = key, valueFrom = arn }]
        logConfiguration = {
          logDriver = "awslogs"
          options = {
            awslogs-group         = aws_cloudwatch_log_group.containers[name].name
            awslogs-region        = var.region
            awslogs-stream-prefix = name
          }
        }
      },
      c.command == null ? {} : { command = c.command },
      c.port == null ? {} : { portMappings = [{ containerPort = c.port, protocol = "tcp" }] },
    )
  ])
}

resource "aws_ecs_service" "app" {
  name            = local.name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.app.arn
  launch_type     = "FARGATE"
  desired_count   = 1

  # One task at a time: a redeploy stops the old task first, so two workers never overlap.
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = true
  }
}
