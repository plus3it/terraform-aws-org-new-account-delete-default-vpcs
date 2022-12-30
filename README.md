# terraform-aws-org-new-account-delete-default-vpcs

A Terraform module to delete the default VPCs in all regions when new AWS accounts
are added or invited to an AWS Organization.

The Lambda function is triggered for the account by an Event Rule that matches
the CreateAccountResult or InviteAccountToOrganization events. The function then
describes the available regions, and deletes all resources associated with the
default VPC in every region for that account.

<!-- BEGIN TFDOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.3 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | >= 4.9 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | >= 4.9 |

## Resources

| Name | Type |
|------|------|
| [aws_iam_policy_document.lambda](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_partition.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/partition) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_project_name"></a> [project\_name](#input\_project\_name) | Project name to prefix resources with | `string` | n/a | yes |
| <a name="input_assume_role_name"></a> [assume\_role\_name](#input\_assume\_role\_name) | Name of the IAM role that the lambda will assume in the target account | `string` | `"OrganizationAccountAccessRole"` | no |
| <a name="input_dry_run"></a> [dry\_run](#input\_dry\_run) | Boolean toggle to control the dry-run mode of the lambda function | `bool` | `true` | no |
| <a name="input_event_bus_name"></a> [event\_bus\_name](#input\_event\_bus\_name) | Event bus name to create event rules in | `string` | `"default"` | no |
| <a name="input_event_types"></a> [event\_types](#input\_event\_types) | Event types that will trigger this lambda | `set(string)` | <pre>[<br>  "CreateAccountResult",<br>  "InviteAccountToOrganization"<br>]</pre> | no |
| <a name="input_lambda"></a> [lambda](#input\_lambda) | Object of optional attributes passed on to the lambda module | <pre>object({<br>    artifacts_dir            = optional(string, "builds")<br>    build_in_docker          = optional(bool, false)<br>    create_package           = optional(bool, true)<br>    ephemeral_storage_size   = optional(number)<br>    ignore_source_code_hash  = optional(bool, true)<br>    local_existing_package   = optional(string)<br>    memory_size              = optional(number, 128)<br>    recreate_missing_package = optional(bool, false)<br>    runtime                  = optional(string, "python3.8")<br>    s3_bucket                = optional(string)<br>    s3_existing_package      = optional(map(string))<br>    s3_prefix                = optional(string)<br>    store_on_s3              = optional(bool, false)<br>    timeout                  = optional(number, 300)<br>  })</pre> | `{}` | no |
| <a name="input_log_level"></a> [log\_level](#input\_log\_level) | Log level for lambda | `string` | `"INFO"` | no |
| <a name="input_max_workers"></a> [max\_workers](#input\_max\_workers) | Number of worker threads to use to process delete | `number` | `20` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | Tags for resource | `map(string)` | `{}` | no |

## Outputs

No outputs.

<!-- END TFDOCS -->
