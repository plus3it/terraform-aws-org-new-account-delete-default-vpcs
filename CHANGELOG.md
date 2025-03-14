## terraform-aws-org-new-account-delete-default-vpcs

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/) and this project adheres to [Semantic Versioning](http://semver.org/).

### [1.3.1](https://github.com/plus3it/terraform-aws-org-new-account-delete-default-vpcs/releases/tag/1.3.1)

**Released**: 2025.03.14

**Summary**:

* Updates opt-in pattern to fix issue with case-sensitivity in status value

### [1.3.0](https://github.com/plus3it/terraform-aws-org-new-account-delete-default-vpcs/releases/tag/1.3.0)

**Released**: 2024.11.26

**Summary**:

* Supports deleting default vpc when an opt-in region is enabled

### [1.2.0](https://github.com/plus3it/terraform-aws-org-new-account-delete-default-vpcs/releases/tag/1.2.0)

**Released**: 2024.11.19

**Summary**:

* Adds aws_sts_regional_endpoints variable as function environment variable with
  default of 'regional' to direct boto3 to use regional sts endpoints.

### [1.1.1](https://github.com/plus3it/terraform-aws-org-new-account-delete-default-vpcs/releases/tag/1.1.1)

**Released**: 2023.04.18

**Summary**:

* Simplifies event rule patterns, relying only on details from cloudtrail event

### 1.1.0

**Commit Delta**: [Change from 1.0.0 release](https://github.com/plus3it/terraform-aws-org-new-account-delete-default-vpcs/compare/1.1.0...1.0.0)

**Released**: 2023.02.23

**Summary**:

* Add CLI option to run delete_default_vpc.py script

### 1.0.0

**Commit Delta**: N/A

**Released**: 2023.01.04

**Summary**:

* Initial release of capability
