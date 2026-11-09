resource "aws_lambda_function" "vision" {
  function_name = "${local.name}-vision"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.images["vision-lambda"].repository_url}:${var.image_tag}"
  architectures = ["x86_64"]
  timeout       = 300
  memory_size   = 3008

  environment {
    variables = {
      OCR_PROVIDER = var.ocr_provider # the image bundles Tesseract; Textract needs a paid AWS plan
    }
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.lambda.name
  }

  depends_on = [
    aws_ecr_repository_policy.lambda_pull,
    aws_iam_role_policy_attachment.lambda_logs,
  ]
}
