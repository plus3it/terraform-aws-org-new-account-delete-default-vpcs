"""Delete Default VPC.

Purpose:
    Delete all resources associated with the default VPC for an account
Permissions:
    * ec2:DescribeRegions
    * ec2:DescribeVpcs
    * ec2:DescribeInternetGateways
    * ec2:DescribeSubnets
    * ec2:DescribeRouteTables
    * ec2:DescribeNetworkAcls
    * ec2:DescribeSecurityGroups
    * ec2:DetachInternetGateway
    * ec2:DeleteInternetGateway
    * ec2:DeleteSubnet
    * ec2:DeleteRouteTable
    * ec2:DeleteNetworkAcl
    * ec2:DeleteSecurityGroup
    * ec2:DeleteVpc
Environment Variables:
    LOG_LEVEL: (optional): sets the level for function logging
            supported values:
            critical, error, warning, info (default)
    DRY_RUN: (optional): true or false, defaults to true
    sets whether the delete should be performed,
    otherwise just log the actions that would be taken
    ASSUME_ROLE_NAME: Name of role sto assume
    MAX_WORKERS: (optional) # of workers to process resources, default 20

"""

from argparse import ArgumentParser, RawDescriptionHelpFormatter
import collections
import concurrent.futures
import logging
import os
import sys

import boto3
from aws_assume_role_lib import (  # type: ignore
    assume_role,
    generate_lambda_session_name,
)

# Standard logging config
DEFAULT_LOG_LEVEL = logging.INFO
LOG_LEVELS = collections.defaultdict(
    lambda: DEFAULT_LOG_LEVEL,
    {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
    },
)

# Lambda initializes a root logger that needs to be removed in order to set a
# different logging config
root = logging.getLogger()
if root.handlers:
    for handler in root.handlers:
        root.removeHandler(handler)

logging.basicConfig(
    format="%(asctime)s.%(msecs)03dZ [%(name)s][%(levelname)s]: %(message)s ",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=LOG_LEVELS[os.environ.get("LOG_LEVEL", "").upper()],
)

log = logging.getLogger(__name__)

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
ASSUME_ROLE_NAME = os.environ.get("ASSUME_ROLE_NAME", "OrganizationAccountAccessRole")
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "20"))

# Get the Lambda session in the lambda context
SESSION = boto3.Session()


class DeleteVPCError(Exception):
    """Delete VPC Error."""


class DeleteVPCResourcesError(Exception):
    """Delete VPC Resource Error."""


class DeleteDefaultVPCInvalidArgsError(Exception):
    """Invalid arguments were used to delete VPCs."""


def lambda_handler(event, context):  # pylint: disable=unused-argument, too-many-locals
    """Delete Default VPC in all regions.

    Assumes role to account and deletes default VPC resources in all regions
    Entrypoint if triggered via lambda
    """
    log.debug("AWS Event: %s", event)

    event_data = parse_event(event)
    log.info("Parsed event data: %s", event_data)

    assume_role_arn = (
        f"arn:{get_partition()}:iam::{event_data['account_id']}:role/{ASSUME_ROLE_NAME}"
    )

    main(event_data["account_id"], assume_role_arn, event_data["regions"])


def get_new_account_id(event):
    """Return account id for new account events."""
    return event["detail"]["serviceEventDetails"]["createAccountStatus"]["accountId"]


def get_invite_account_id(event):
    """Return account id for invite account events."""
    return event["detail"]["requestParameters"]["target"]["id"]


def get_enable_region_account_id(event):
    """Return account id for enable region events."""
    return event["detail"].get("accountId") or event["account"]


def get_cloudtrail_event_name(event):
    """Return event name for cloudtrail events."""
    return event["detail"]["eventName"]


def get_region_opt_in_regions(event):
    """Return region name for region opt-in events."""
    return [event["detail"]["regionName"]]


def parse_event(event):
    """Return event data for supported events."""
    event_name_strategy = {
        "AWS Service Event via CloudTrail": get_cloudtrail_event_name,
        "Region Opt-In Status Change": lambda x: "EnableOptInRegion",
    }

    account_id_strategy = {
        "CreateAccountResult": get_new_account_id,
        "InviteAccountToOrganization": get_invite_account_id,
        "EnableOptInRegion": get_enable_region_account_id,
    }

    regions_strategy = {
        "CreateAccountResult": lambda x: None,
        "InviteAccountToOrganization": lambda x: None,
        "EnableOptInRegion": get_region_opt_in_regions,
    }

    event_name = event_name_strategy[event["detail-type"]](event)

    return {
        "account_id": account_id_strategy[event_name](event),
        "regions": regions_strategy[event_name](event),
    }


def get_assumed_role_session(account_id, role_arn):
    """Get boto3 session."""
    function_name = os.environ.get(
        "AWS_LAMBDA_FUNCTION_NAME", os.path.basename(__file__)
    )

    role_session_name = generate_lambda_session_name(function_name)

    # Assume the session
    assumed_role_session = assume_role(
        SESSION, role_arn, RoleSessionName=role_session_name, validate=False
    )
    # do stuff with the assumed role using assumed_role_session
    log.debug(
        "Assumed identity for account %s is %s",
        account_id,
        assumed_role_session.client("sts").get_caller_identity()["Arn"],
    )
    return assumed_role_session


def get_partition():
    """Return AWS partition."""
    sts = boto3.client("sts")
    return sts.get_caller_identity()["Arn"].split(":")[1]


def get_regions(assumed_role_session):
    """Build a region list."""
    client = assumed_role_session.client("ec2")
    regions = client.describe_regions()
    return [region["RegionName"] for region in regions["Regions"]]


def get_default_vpc_ids(assumed_role_session, account_id, region):
    """Get default VPC ID."""
    log.info("Retrieve VPCs for account %s region %s", account_id, region)
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


def del_igw(vpc):
    """Detach and delete the internet-gateway."""
    igws = None
    vpc_id = vpc["id"]

    igws = vpc["resource"].internet_gateways.all()

    if not igws:
        log.info("There are no igws for vpcid %s ", vpc_id)

    for igw in igws:
        log.info("Detaching and Removing igw: %s", igw.id)
        igw.detach_from_vpc(DryRun=DRY_RUN, VpcId=vpc_id)
        igw.delete(DryRun=DRY_RUN)


def del_sub(vpc):
    """Delete the subnets."""
    subnets = vpc["resource"].subnets.all()
    default_subnets = [subnet for subnet in subnets if subnet.default_for_az]

    if not default_subnets:
        log.info("There are no default subnets for VPC id %s ", vpc["id"])

    for sub in default_subnets:
        log.info("Removing subnet: %s", sub.id)
        sub.delete(DryRun=DRY_RUN)


def del_rtb(vpc):
    """Delete the route-tables."""
    rtbs = vpc["resource"].route_tables.all()
    if not rtbs:
        log.info("There are no rtbs for vpcid %s ", vpc["id"])

    for rtb in rtbs:
        assoc_attr = [rtb.associations_attribute for rtb in rtbs]
        if [rtb_ass[0]["RouteTableId"] for rtb_ass in assoc_attr if rtb_ass[0]["Main"]]:
            log.info("%s is the main route table, continue...", rtb.id)
            continue
        log.info("Removing rtb: %s", rtb.id)
        rtb.delete(DryRun=DRY_RUN)


def del_acl(vpc):
    """Delete the network-access-lists."""
    acls = vpc["resource"].network_acls.all()
    if not acls:
        log.info("There are no acls for vpcid %s ", vpc["id"])

    for acl in acls:
        if acl.is_default:
            log.info("%s is the default NACL, continue...", acl.id)
            continue
        log.info("Removing acl: %s ", acl.id)
        acl.delete(DryRun=DRY_RUN)


def del_sgp(vpc):
    """Delete any security-groups."""
    security_groups = vpc["resource"].security_groups.all()
    if not security_groups:
        log.info("There are no security groups for vpcid %s ", vpc["id"])

    for security_group in security_groups:
        if security_group.group_name == "default":
            log.info("%s is the default security group, continue...", security_group.id)
            continue
        log.info("Removing sg: %s", security_group.id)
        security_group.delete(DryRun=DRY_RUN)


def del_vpc(vpc):
    """Delete the VPC."""
    vpc_id = vpc["id"]
    log.info("Removing vpc-id: %s", vpc_id)
    vpc["resource"].delete(DryRun=DRY_RUN)


def del_vpc_all(vpc_resource, region):
    """Do the work - order of operation.

    1.) Delete the internet-gateway
    2.) Delete subnets
    3.) Delete route-tables
    4.) Delete network access-lists
    5.) Delete security-groups
    6.) Delete the VPC
    """
    exception_list = []

    log.info("Delete All VPC started for vpc %s", vpc_resource.id)
    vpc = {
        "resource": vpc_resource,
        "account_id": vpc_resource.owner_id,
        "id": vpc_resource.id,
        "region": region,
    }

    try:
        del_igw(vpc)
    except BaseException as exc:  # pylint: disable=broad-except
        # Allow threads to continue on exception, but capture the error
        exception_list.append(process_exception(vpc, "del_igw", exc))

    try:
        del_sub(vpc)
    except BaseException as exc:  # pylint: disable=broad-except
        # Allow threads to continue on exception, but capture the error
        exception_list.append(process_exception(vpc, "del_sub", exc))

    try:
        del_rtb(vpc)
    except BaseException as exc:  # pylint: disable=broad-except
        # Allow threads to continue on exception, but capture the error
        exception_list.append(process_exception(vpc, "del_rtb", exc))

    try:
        del_acl(vpc)
    except BaseException as exc:  # pylint: disable=broad-except
        # Allow threads to continue on exception, but capture the error
        exception_list.append(process_exception(vpc, "del_acl", exc))

    try:
        del_sgp(vpc)
    except BaseException as exc:  # pylint: disable=broad-except
        # Allow threads to continue on exception, but capture the error
        exception_list.append(process_exception(vpc, "del_sgp", exc))

    try:
        del_vpc(vpc)
    except BaseException as exc:  # pylint: disable=broad-except
        # Allow threads to continue on exception, but capture the error
        exception_list.append(process_exception(vpc, "del_vpc", exc))

    if exception_list:
        exception_list = "\r\r ".join(exception_list)
        exception_str = (
            f"Exceptions for Account: {vpc['account_id']} "
            f"Region: {vpc['region']} VPC: {vpc['id']}:\r{exception_list}"
        )
        log.error(exception_str)
        raise DeleteVPCError(Exception(exception_str))


def get_error_prefix(account_id, region, method_name):
    """Get prefix for error message."""
    return f"Account: {account_id}\r Region: {region}\r Method: {method_name}"


def convert_exception_to_string(account_id, region, method_name, msg, exception):
    """Convert exception to string."""
    error_str = get_error_prefix(account_id, region, method_name)
    if msg:
        error_str = f"{error_str}\r Error:{msg}\r"
    error_str = f"{error_str}\r Exception:{exception}"
    return error_str


def process_exception(vpc, method_name, exception):
    """Handle exceptions and return error string."""
    error_str = convert_exception_to_string(
        vpc["account_id"], vpc["region"], method_name, None, exception
    )

    log.error(error_str)
    log.exception(exception)

    return error_str


def cli_main(target_account_id, assume_role_arn=None, assume_role_name=None):
    """Process cli assume_role_name arg and pass to main."""
    log.debug(
        "CLI - target_account_id=%s assume_role_arn=%s assume_role_name=%s",
        target_account_id,
        assume_role_arn,
        assume_role_name,
    )

    if assume_role_name:
        assume_role_arn = (
            f"arn:{get_partition()}:iam::{target_account_id}:role/{assume_role_name}"
        )
        log.info("assume_role_arn for provided role name is '%s'", assume_role_arn)

    main(target_account_id, assume_role_arn)


def main(target_account_id, assume_role_arn, regions=None):
    """Assume role and concurrently delete default vpc resources."""
    log.debug(
        "Main identity is %s",
        SESSION.client("sts").get_caller_identity()["Arn"],
    )

    assumed_role_session = get_assumed_role_session(target_account_id, assume_role_arn)

    regions = regions or get_regions(assumed_role_session)

    exception_list = concurrently_delete_vpcs(
        assumed_role_session,
        target_account_id,
        regions,
    )

    if exception_list:
        exception_list = "\r\r ".join(exception_list)
        exception_str = f"All Exceptions encountered:\r\r{exception_list}\r\r"
        log.error(exception_str)
        raise DeleteVPCError(Exception(exception_str))

    if DRY_RUN:
        log.debug("Dry Run listed all resources that would be deleted")
    else:
        log.debug("Deleted all default VPCs and associated resources")


def concurrently_delete_vpcs(
    assumed_role_session,
    target_account_id,
    regions,
):
    """Create worker threads and deletes vpc resources."""
    exception_list = []
    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for region in regions:
            try:
                ec2 = assumed_role_session.resource("ec2", region_name=region)
                vpc_ids = get_default_vpc_ids(
                    assumed_role_session, target_account_id, region
                )
            except BaseException as exc:  # pylint: disable=broad-except
                # Allow threads to continue on exception, but capture the error
                vpc_ids = []
                msg = "Error: Error getting vpc resource"
                exception_list.append(
                    convert_exception_to_string(
                        target_account_id,
                        region,
                        lambda_handler.__name__,
                        msg,
                        exc,
                    )
                )
                log.exception(exc)

            for vpc_id in vpc_ids:
                log.info(
                    "Processing Account: %s Region: %s and VPC Id: %s",
                    target_account_id,
                    region,
                    vpc_id,
                )
                try:
                    vpc_resource = ec2.Vpc(vpc_id)
                    futures.append(executor.submit(del_vpc_all, vpc_resource, region))
                except BaseException as exc:  # pylint: disable=broad-except
                    # Allow threads to continue on exception, but capture the error
                    msg = "Error: Exception submitting del_vpc_all executor"
                    exception_list.append(
                        convert_exception_to_string(
                            target_account_id,
                            region,
                            lambda_handler.__name__,
                            msg,
                            exc,
                        )
                    )
                    log.exception(exc)
    concurrent.futures.wait(futures)
    for fut in futures:
        try:
            fut.result()
        except BaseException as exc:  # pylint: disable=broad-except
            # Allow threads to continue on exception, but capture the error
            exception_list.append(str(exc))

    return exception_list


if __name__ == "__main__":

    def create_args():
        """Return parsed arguments."""
        parser = ArgumentParser(
            formatter_class=RawDescriptionHelpFormatter,
            description="""
Delete Default VPC for all supported regions for provided target account.

Supported Environment Variables:
    'LOG_LEVEL': defaults to 'info'
        - set the desired log level ('error', 'warning', 'info' or 'debug')

    'DRY_RUN': defaults to 'true'
        - set whether actions should be simulated or live
        - value of 'true' (case insensitive) will be simulated.

    'MAX_WORKERS': defaults to '20'
        -sets max number of worker threads to run simultaneously.
""",
        )
        required_args = parser.add_argument_group("required named arguments")
        required_args.add_argument(
            "--target-account-id",
            required=True,
            type=str,
            help="Account number to delete default VPC resources in",
        )
        mut_x_group = parser.add_mutually_exclusive_group(required=True)
        mut_x_group.add_argument(
            "--assume-role-arn",
            type=str,
            help="ARN of IAM role to assume in the target account (case sensitive)",
        )
        mut_x_group.add_argument(
            "--assume-role-name",
            type=str,
            help="Name of IAM role to assume in the target account (case sensitive)",
        )

        return parser.parse_args()

    sys.exit(cli_main(**vars(create_args())))
