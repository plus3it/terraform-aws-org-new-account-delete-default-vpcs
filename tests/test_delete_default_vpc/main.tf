module "delete_default_vpc" {
  source           = "../../"
  project_name     = local.project
  assume_role_name = aws_iam_role.assume_role.name
  dry_run          = true
  max_workers      = 20
  log_level        = "INFO"
  tags             = local.tags
}

locals {
  id      = random_string.id.result
  project = "test-delete-default-vpc-${local.id}"

  tags = {
    "project" = local.project
  }
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

data "aws_iam_policy_document" "iam_vpc" {
  statement {
    actions = [
      "ec2:DescribeRegions",
      "ec2:DescribeVpcs",
      "ec2:DescribeInternetGateways",
      "ec2:DescribeSubnets",
      "ec2:DescribeRouteTables",
      "ec2:DescribeNetworkAcls",
      "ec2:DescribeSecurityGroups",
      "ec2:DetachInternetGateway",
      "ec2:DeleteInternetGateway",
      "ec2:DeleteSubnet",
      "ec2:DeleteRouteTable",
      "ec2:DeleteNetworkAcl",
      "ec2:DeleteSecurityGroup",
      "ec2:DeleteVpc"
    ]

    resources = [
      "*"
    ]
  }
}

resource "aws_iam_role" "assume_role" {
  name = "${local.project}-delete-default-vpc-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        "Sid" : "AssumeRoleCrossAccount",
        "Effect" : "Allow",
        "Principal" : {
          "AWS" : "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"
        },
        "Action" : "sts:AssumeRole"
      }
    ]
  })

  inline_policy {
    name   = local.project
    policy = data.aws_iam_policy_document.iam_vpc.json
  }
}

resource "random_string" "id" {
  length  = 6
  upper   = false
  special = false
  numeric = false
}
