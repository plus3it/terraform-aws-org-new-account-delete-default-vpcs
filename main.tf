##############################
# Lambda
##############################
module "lambda" {
  source = "git::https://github.com/terraform-aws-modules/terraform-aws-lambda.git?ref=v7.14.0"

  function_name = "${var.project_name}-delete-default-vpc"

  description = "Deletes Default VPC in all regions, triggered by new account events"
  handler     = "delete_default_vpc.lambda_handler"
  tags        = var.tags

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.lambda.json

  artifacts_dir            = var.lambda.artifacts_dir
  build_in_docker          = var.lambda.build_in_docker
  create_package           = var.lambda.create_package
  ephemeral_storage_size   = var.lambda.ephemeral_storage_size
  ignore_source_code_hash  = var.lambda.ignore_source_code_hash
  local_existing_package   = var.lambda.local_existing_package
  memory_size              = var.lambda.memory_size
  recreate_missing_package = var.lambda.recreate_missing_package
  runtime                  = var.lambda.runtime
  s3_bucket                = var.lambda.s3_bucket
  s3_existing_package      = var.lambda.s3_existing_package
  s3_prefix                = var.lambda.s3_prefix
  store_on_s3              = var.lambda.store_on_s3
  timeout                  = var.lambda.timeout

  source_path = [
    {
      path             = "${path.module}/src"
      pip_requirements = true
      patterns         = ["!\\.terragrunt-source-manifest"]
    }
  ]

  environment_variables = {
    LOG_LEVEL                  = var.log_level
    ASSUME_ROLE_NAME           = var.assume_role_name
    DRY_RUN                    = var.dry_run
    MAX_WORKERS                = var.max_workers
    AWS_STS_REGIONAL_ENDPOINTS = var.aws_sts_regional_endpoints
  }
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid = "AllowAssumeRole"

    actions = [
      "sts:AssumeRole"
    ]

    resources = [
      "arn:${data.aws_partition.current.partition}:iam::*:role/${var.assume_role_name}"
    ]
  }
}

##############################
# Events
##############################
locals {
  lambda_name = module.lambda.lambda_function_name

  event_types = {
    CreateAccountResult = jsonencode(
      {
        "detail" : {
          "eventSource" : ["organizations.amazonaws.com"],
          "eventName" : ["CreateAccountResult"]
          "serviceEventDetails" : {
            "createAccountStatus" : {
              "state" : ["SUCCEEDED"]
            }
          }
        }
      }
    )
    InviteAccountToOrganization = jsonencode(
      {
        "detail" : {
          "eventSource" : ["organizations.amazonaws.com"],
          "eventName" : ["InviteAccountToOrganization"]
        }
      }
    )
  }
}

resource "aws_cloudwatch_event_rule" "this" {
  for_each = var.event_types

  name           = "${var.project_name}-${each.value}"
  description    = "Managed by Terraform"
  event_pattern  = local.event_types[each.value]
  event_bus_name = var.event_bus_name
  tags           = var.tags
}

resource "aws_cloudwatch_event_target" "this" {
  for_each = aws_cloudwatch_event_rule.this

  rule = each.value.name
  arn  = module.lambda.lambda_function_arn
}

resource "aws_lambda_permission" "events" {
  for_each = aws_cloudwatch_event_rule.this

  action        = "lambda:InvokeFunction"
  function_name = module.lambda.lambda_function_name
  principal     = "events.amazonaws.com"
  source_arn    = each.value.arn
}

##############################
# Common
##############################
data "aws_partition" "current" {}
