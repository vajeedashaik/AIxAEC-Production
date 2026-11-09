output "region" {
  value = var.region
}

output "registry" {
  value = "${local.account_id}.dkr.ecr.${var.region}.amazonaws.com"
}

output "bucket" {
  value = aws_s3_bucket.files.bucket
}

output "artifact_origin" {
  description = "Set as NEXT_PUBLIC_ARTIFACT_ORIGIN so the browser may load S3 images."
  value       = "https://${aws_s3_bucket.files.bucket_regional_domain_name}"
}

output "cluster" {
  value = aws_ecs_cluster.main.name
}

output "service" {
  value = aws_ecs_service.app.name
}

output "vision_lambda" {
  value = aws_lambda_function.vision.function_name
}

output "dashboard_url" {
  value = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}
