resource "aws_ecr_repository" "images" {
  for_each             = toset(["api", "geometry", "language", "vision-lambda"])
  name                 = "${local.name}/${each.key}"
  force_delete         = true # lets terraform destroy remove repositories that still hold images
  image_tag_mutability = "MUTABLE"
}

resource "aws_ecr_repository_policy" "lambda_pull" {
  repository = aws_ecr_repository.images["vision-lambda"].name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "LambdaPull"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    }]
  })
}
