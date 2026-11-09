terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project = "aec-demo"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  name       = "aec-demo"
  account_id = data.aws_caller_identity.current.account_id
}
