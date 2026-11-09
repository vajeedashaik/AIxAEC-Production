data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# ECS itself: pull images and write logs.
resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# The application containers.
data "aws_iam_policy_document" "task" {
  statement {
    sid       = "ObjectAccess"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.files.arn}/*"]
  }

  statement {
    sid       = "ListForPrefixDelete"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.files.arn]
  }

  statement {
    sid       = "JobQueue"
    actions   = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage"]
    resources = [aws_sqs_queue.jobs.arn]
  }

  statement {
    sid       = "Notify"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.alerts.arn]
  }

  statement {
    sid       = "RunVision"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.vision.arn]
  }

  statement {
    sid = "Speech"
    actions = [
      "transcribe:StartTranscriptionJob",
      "transcribe:GetTranscriptionJob",
      "transcribe:DeleteTranscriptionJob",
    ]
    resources = ["*"]
  }

  dynamic "statement" {
    for_each = var.bedrock_model_id == "" ? [] : [1]

    content {
      sid     = "CommandParsing"
      actions = ["bedrock:InvokeModel"]
      resources = [
        "arn:aws:bedrock:*::foundation-model/*",
        "arn:aws:bedrock:*:${local.account_id}:inference-profile/*",
      ]
    }
  }
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "task" {
  name   = "app"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

# The vision function: only its hand-off files and OCR.
data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "HandoffFiles"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.files.arn}/tmp/*"]
  }

  statement {
    sid       = "Ocr"
    actions   = ["textract:DetectDocumentText"]
    resources = ["*"]
  }

  statement {
    sid       = "PullImage"
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = [aws_ecr_repository.images["vision-lambda"].arn]
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "lambda" {
  name   = "vision"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
