resource "aws_cloudwatch_log_group" "containers" {
  for_each          = toset(["api", "worker", "geometry", "language"])
  name              = "/${local.name}/${each.key}"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}-vision"
  retention_in_days = 7
}

locals {
  ecs_dimensions = ["ClusterName", aws_ecs_cluster.main.name, "ServiceName", aws_ecs_service.app.name]
  lambda_name    = aws_lambda_function.vision.function_name

  dashboard_widgets = [
    {
      title = "ECS CPU and memory (%)"
      metrics = [
        concat(["AWS/ECS", "CPUUtilization"], local.ecs_dimensions),
        concat(["AWS/ECS", "MemoryUtilization"], local.ecs_dimensions),
      ]
    },
    {
      title = "Job queue"
      metrics = [
        ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.jobs.name],
        ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", aws_sqs_queue.jobs.name],
        ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.jobs_dlq.name, { label = "Dead-letter queue" }],
      ]
    },
    {
      title = "Vision Lambda"
      metrics = [
        ["AWS/Lambda", "Invocations", "FunctionName", local.lambda_name, { stat = "Sum" }],
        ["AWS/Lambda", "Errors", "FunctionName", local.lambda_name, { stat = "Sum" }],
        ["AWS/Lambda", "Duration", "FunctionName", local.lambda_name, { yAxis = "right" }],
      ]
    },
  ]
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = local.name

  dashboard_body = jsonencode({
    widgets = [
      for index, widget in local.dashboard_widgets : {
        type   = "metric"
        x      = index * 8
        y      = 0
        width  = 8
        height = 8
        properties = {
          title   = widget.title
          metrics = widget.metrics
          region  = var.region
          stat    = "Average"
          period  = 60
          view    = "timeSeries"
        }
      }
    ]
  })
}

resource "aws_cloudwatch_metric_alarm" "dlq" {
  alarm_name          = "${local.name}-dlq-has-messages"
  alarm_description   = "A processing job's message failed repeatedly."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.jobs_dlq.name }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${local.name}-vision-errors"
  alarm_description   = "The vision Lambda raised an error."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.vision.function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Without Container Insights there is no running-task metric, so CPU samples stand in: no samples means no task.
resource "aws_cloudwatch_metric_alarm" "no_task" {
  alarm_name          = "${local.name}-no-running-task"
  alarm_description   = "The ECS service has no running task."
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  dimensions          = { ClusterName = aws_ecs_cluster.main.name, ServiceName = aws_ecs_service.app.name }
  statistic           = "SampleCount"
  period              = 60
  evaluation_periods  = 3
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_query_definition" "follow_job" {
  name = "${local.name}/follow-one-job"
  log_group_names = concat(
    [for group in aws_cloudwatch_log_group.containers : group.name],
    [aws_cloudwatch_log_group.lambda.name],
  )

  # Replace job- with the full id from the worker log, e.g. job-1234...
  query_string = <<-EOT
    fields @timestamp, @log, @message
    | filter @message like "job-"
    | sort @timestamp asc
    | limit 200
  EOT
}
