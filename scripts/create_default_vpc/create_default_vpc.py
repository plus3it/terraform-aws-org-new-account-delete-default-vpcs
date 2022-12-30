import concurrent.futures
from pathlib import Path  # to find user home directory

import boto3
import botocore
import click  # for command line arguments
from aws_assume_role_lib import assume_role
from botocore.exceptions import ClientError


@click.command()
@click.option(
    "--com",
    "cloud",
    flag_value="commercial",
    default=True,
    help="Cloud",
    show_default=True,
)
@click.option("--gov", "cloud", flag_value="govcloud", help="Cloud")
@click.option(
    "--account-id",
    "account_id",
    help="Account to process",
    required=True,
)
@click.option("--dry-run", "dry_run", is_flag=True)
@click.option("--debug", "debug", is_flag=True)
@click.option(
    "--role-session-name",
    "role_session_name",
    help="Role session name that is logged for activity",
    required=True,
)
@click.option(
    "--role-to-assume",
    "role_to_assume",
    help="Role to assume",
    default="OrganizationAccountAccessRole",
    show_default=True,
)
@click.option(
    "--max-workers",
    "max_workers",
    help="Number of workers in executor pool",
    default=20,
    show_default=True,
)
def main(
    cloud, account_id, dry_run, debug, role_session_name, role_to_assume, max_workers
):

    assumed_role_session = get_assumed_role_session(
        cloud, account_id, role_to_assume, role_session_name
    )

    regions = get_regions(assumed_role_session, cloud, debug)
    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for region in regions:
            try:
                ec2 = assumed_role_session.client("ec2", region_name=region)
                vpc_ids = get_default_vpc_ids(assumed_role_session, region)
            except boto3.exceptions.Boto3Error as e:
                print(e)
                exit(1)

            if not vpc_ids:
                print(f"Creating default VPC in region: {region}")
                futures.append(executor.submit(create_vpc, ec2, dry_run))
            else:
                print(f"Default VPC exists in region {region}")
    concurrent.futures.wait(futures)

    print("Script End")


def get_partition(cloud):
    if cloud == "commercial":
        return "aws"
    return "aws-us-gov"


def get_assumed_role_session(cloud, account_id, role_to_assume, role_session_name):
    # Get the config
    role_arn = f"arn:{get_partition(cloud)}:iam::{account_id}:role/{role_to_assume}"

    # Get the Lambda session
    default_session = boto3.Session()

    # Assume the session
    assumed_role_session = assume_role(
        default_session, role_arn, RoleSessionName=role_session_name
    )
    # do stuff with the assumed role using assumed_role_session
    print(
        f'Assumed identity for account {account_id} is {assumed_role_session.client("sts").get_caller_identity()["Arn"]}'
    )
    return assumed_role_session


def get_regions(assumed_role_session, cloud, debug):
    if debug:
        return ["us-east-1"] if cloud == "commercial" else ["us-gov-west-1"]

    client = assumed_role_session.client("ec2")
    regions = client.describe_regions()
    return [region["RegionName"] for region in regions["Regions"]]


def get_default_vpc_ids(assumed_role_session, region):
    print(f"Retrieve VPCs for region {region}")
    client = assumed_role_session.client("ec2", region_name=region)
    vpcs = client.describe_vpcs(
        Filters=[
            {
                "Name": "isDefault",
                "Values": [
                    "true",
                ],
            },
        ]
    )
    return [vpc["VpcId"] for vpc in vpcs["Vpcs"]]


def create_vpc(ec2, dry_run):
    """Create the default VPC"""
    print(f"Create default VPC dry_run={dry_run}")
    try:
        response = ec2.create_default_vpc(DryRun=dry_run)
        print(
            f'Created VPC id {response["Vpc"]["VpcId"]} {response["Vpc"]["IsDefault"]}'
        )
    except (
        boto3.exceptions.Boto3Error,
        botocore.exceptions.ClientError,
        Exception,
    ) as e:
        print(e)


if __name__ == "__main__":
    main()
