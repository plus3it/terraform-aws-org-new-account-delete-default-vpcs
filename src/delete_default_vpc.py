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
import collections
import concurrent.futures
import logging
import os

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
MAX_WORKERS = int(os.getenv("MAX_WORKERS", 20))

# Get the Lambda session in the lambda context
SESSION = boto3.Session()


class DeleteVPCError(Exception):
    """Delete VPC Error."""


class DeleteVPCResourcesError(Exception):
    """Delete VPC Resource Error."""


def lambda_handler(event, context):  # pylint: disable=unused-argument
    """Delete Default VPC in all regions.

    Assumes role to account and deletes default VPC resources in all regions
    """
    log.debug("AWS Event:%s", event)

    account_id = get_account_id(event)

    # do stuff with the Lambda role using SESSION
    log.debug(
        "Main identity is %s",
        SESSION.client("sts").get_caller_identity()["Arn"],
    )

    assumed_role_session = get_assumed_role_session(account_id)

    regions = get_regions(assumed_role_session)

    exception_list = []
    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for region in regions:
            try:
                ec2 = assumed_role_session.resource("ec2", region_name=region)
                vpc_ids = get_default_vpc_ids(assumed_role_session, account_id, region)
            except BaseException as bex:
                vpc_ids = []
                msg = "Error: Error getting vpc resource"
                exception_list.append(
                    convert_exception_to_string(
                        account_id,
                        region,
                        lambda_handler.__name__,
                        msg,
                        bex,
                    )
                )
                log.exception(bex)

            for vpc_id in vpc_ids:
                log.info(
                    "Processing Account: %s Region: %s and VPC Id: %s",
                    account_id,
                    region,
                    vpc_id,
                )
                try:
                    vpc_resource = ec2.Vpc(vpc_id)
                    futures.append(executor.submit(del_vpc_all, vpc_resource, region))
                except BaseException as bex:
                    msg = "Error: Exception submitting del_vpc_all executor"
                    exception_list.append(
                        convert_exception_to_string(
                            account_id,
                            region,
                            lambda_handler.__name__,
                            msg,
                            bex,
                        )
                    )
                    log.exception(bex)
    concurrent.futures.wait(futures)
    for fut in futures:
        try:
            fut.result()
        except BaseException as ex:
            exception_list.append(str(ex))

    if exception_list:
        exception_list = "\r\r ".join(exception_list)
        exception_str = f"All Exceptions encountered:\r\r{exception_list}\r\r"
        log.error(exception_str)
        raise DeleteVPCError(Exception(exception_str))

    if DRY_RUN:
        log.debug("Dry Run listed all resources that would be deleted")
    else:
        log.debug("Deleted all default VPCs and associated resources")


def get_new_account_id(event):
    """Return account id for new account events."""
    return event["detail"]["serviceEventDetails"]["createAccountStatus"]["accountId"]


def get_invite_account_id(event):
    """Return account id for invite account events."""
    return event["detail"]["requestParameters"]["target"]["id"]


def get_account_id(event):
    """Return account id for supported events."""
    event_name = event["detail"]["eventName"]
    get_account_id_strategy = {
        "CreateAccountResult": get_new_account_id,
        "InviteAccountToOrganization": get_invite_account_id,
    }
    return get_account_id_strategy[event_name](event)


def get_assumed_role_session(account_id):
    # Get the config
    role_arn = f"arn:{get_partition()}:iam::{account_id}:role/{ASSUME_ROLE_NAME}"
    role_session_name = generate_lambda_session_name()

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
    """Build a region list"""
    client = assumed_role_session.client("ec2")
    regions = client.describe_regions()
    return [region["RegionName"] for region in regions["Regions"]]


def get_default_vpc_ids(assumed_role_session, account_id, region):
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
    """Detach and delete the internet-gateway"""
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
    """Delete the subnets"""
    subnets = vpc["resource"].subnets.all()
    default_subnets = [subnet for subnet in subnets if subnet.default_for_az]

    if not default_subnets:
        log.info("There are no default subnets for VPC id %s ", vpc["id"])

    for sub in default_subnets:
        log.info("Removing subnet: %s", sub.id)
        sub.delete(DryRun=DRY_RUN)


def del_rtb(vpc):
    """Delete the route-tables"""
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
    """Delete the network-access-lists"""
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
    """Delete any security-groups"""
    sgps = vpc["resource"].security_groups.all()
    if not sgps:
        log.info("There are no sgps for vpcid %s ", vpc["id"])

    for sg in sgps:
        if sg.group_name == "default":
            log.info("%s is the default security group, continue...", sg.id)
            continue
        log.info("Removing sg: %s", sg.id)
        sg.delete(DryRun=DRY_RUN)


def del_vpc(vpc):
    """Delete the VPC"""
    vpc_id = vpc["id"]
    log.info("Removing vpc-id: %s", vpc_id)
    vpc["resource"].delete(DryRun=DRY_RUN)


def del_vpc_all(vpc_resource, region):
    """
    Do the work - order of operation
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
    except BaseException as ex:
        exception_list.append(process_exception(vpc, "del_igw", ex))

    try:
        del_sub(vpc)
    except BaseException as ex:
        exception_list.append(process_exception(vpc, "del_sub", ex))

    try:
        del_rtb(vpc)
    except BaseException as ex:
        exception_list.append(process_exception(vpc, "del_rtb", ex))

    try:
        del_acl(vpc)
    except BaseException as ex:
        exception_list.append(process_exception(vpc, "del_acl", ex))

    try:
        del_sgp(vpc)
    except BaseException as ex:
        exception_list.append(process_exception(vpc, "del_sgp", ex))

    try:
        del_vpc(vpc)
    except BaseException as ex:
        exception_list.append(process_exception(vpc, "del_vpc", ex))

    if exception_list:
        exception_list = "\r\r ".join(exception_list)
        exception_str = (
            f"Exceptions for Account: {vpc['account_id']} "
            f"Region: {vpc['region']} VPC: {vpc['id']}:\r{exception_list}"
        )
        log.error(exception_str)
        raise DeleteVPCError(Exception(exception_str))


def get_error_prefix(account_id, region, method_name):
    return f"Account: {account_id}\r Region: {region}\r Method: {method_name}"


def convert_exception_to_string(account_id, region, method_name, msg, exception):
    error_str = get_error_prefix(account_id, region, method_name)
    if msg:
        error_str = f"{error_str}\r Error:{msg}\r"
    error_str = f"{error_str}\r Exception:{exception}"
    return error_str


def process_exception(vpc, method_name, exception):
    error_str = convert_exception_to_string(
        vpc["account_id"], vpc["region"], method_name, None, exception
    )

    log.error(error_str)
    log.exception(exception)

    return error_str
