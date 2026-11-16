# Agent Instructions

Before starting any task in this repository:

1. Run `make agents/sync`. It writes the shared Plus3 IT instructions for this repository's tardigrade-ci version to `.agents/plus3it/AGENTS.md`.
2. Read `.agents/plus3it/AGENTS.md` and follow it together with this file. If the sync fails, tell the user, and don't guess the conventions.

These rules always apply, even without the shared instructions:

- Don't push, open pull requests, publish releases, or apply infrastructure changes unless the user asks. List those steps for a person in your final report.
- Don't edit files under `.agents/plus3it/`; they are generated and overwritten by the sync.

@.agents/plus3it/AGENTS.md

## Repository-specific

### Purpose

This Terraform module deploys a Python Lambda function that deletes the default VPCs in all regions of an AWS account, and EventBridge rules that trigger it when an account is created, invited to the organization, or opts in to a region. The main input is `project_name`, which prefixes the resource names; `dry_run` defaults to `true`, so the function only logs what it would delete. The module has no outputs.

### Module-specific files

- `src/delete_default_vpc.py` — Lambda source, packaged by the module at plan time; `lambda_handler` assumes a role in the target account and deletes the default VPC resources in each region using a thread pool, and it can also run as a command line script
- `src/requirements.txt` — Pinned runtime packages that are installed into the Lambda package
- `scripts/create_default_vpc/` — Helper script that does the reverse: `create_default_vpc.py` creates a default VPC in each region of an account that lacks one, `run.sh` runs it in a temporary virtual environment with `--dry-run --debug`, and `requirements.txt` lists its packages
- `Dockerfile` — Builds on the tardigrade-ci image and installs `src/requirements.txt` so the Lambda packages are available in the image. The tardigrade-ci `docker/run` target, which the shared lint workflow calls, builds this image when it is not already present
