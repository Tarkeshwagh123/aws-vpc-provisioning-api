import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

from errors import ProvisioningTimeoutError, UpstreamError
from models import CreatedSubnet, SubnetSpec, VpcSpec

logger = logging.getLogger(__name__)

# Stop starting new create steps when less than this is left on the Lambda
# clock, so rollback can finish before API Gateway (30s) or Lambda gives up.
MIN_SECONDS_LEFT = 8


class VpcService:
    def __init__(self, region, project_name, ec2_client=None):
        self.region = region
        self.project_name = project_name
        self.ec2 = ec2_client or boto3.client("ec2", region_name=region)
        self._time_left = None

    def create(self, spec: VpcSpec, record_id: str, time_left=None) -> dict[str, Any]:
        """`time_left` returns the seconds left before the request times out;
        when it gets low the create is rolled back and a 504 is raised, so the
        client never sees a timeout for a VPC that still gets created."""
        self._time_left = time_left
        created = {
            "vpc_id": None,
            "subnet_ids": [],
            "igw_id": None,
            "public_rtb_id": None,
            "rtb_associations": [],
        }
        try:
            return self._create_inner(spec, record_id, created)
        except ClientError as exc:
            logger.exception("create_vpc failed")
            self._cleanup(created)
            err = exc.response.get("Error", {})
            raise UpstreamError(
                "AWS rejected the VPC create request",
                details={"aws_code": err.get("Code"), "aws_message": err.get("Message")},
            ) from exc
        except Exception:
            logger.exception("create_vpc failed")
            self._cleanup(created)
            raise

    def delete(self, vpc_id: str) -> None:
        """Tear down subnets / igw / route tables then the VPC itself.
        A VPC that is already gone counts as deleted, so its record can still
        be removed."""
        try:
            self._delete_inner(vpc_id)
        except ClientError as exc:
            err = exc.response.get("Error", {})
            if err.get("Code") == "InvalidVpcID.NotFound":
                logger.warning("vpc %s already deleted", vpc_id)
                return
            raise UpstreamError(
                f"Could not delete {vpc_id}",
                details={"aws_code": err.get("Code"), "aws_message": err.get("Message")},
            ) from exc

    def _create_inner(self, spec, record_id, created):
        azs = self._availability_zones()
        self._assign_azs(spec.subnets, azs)

        self._check_time()
        vpc = self.ec2.create_vpc(
            CidrBlock=spec.cidr_block,
            TagSpecifications=[self._tag_spec("vpc", spec.name, record_id)],
        )
        vpc_id = vpc["Vpc"]["VpcId"]
        created["vpc_id"] = vpc_id
        self.ec2.get_waiter("vpc_available").wait(
            VpcIds=[vpc_id], WaiterConfig={"Delay": 2, "MaxAttempts": 5}
        )

        self.ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={"Value": True})
        self.ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True})

        if spec.has_public_subnets():
            self._check_time()
            self._create_public_path(vpc_id, spec.name, record_id, created)
        igw_id = created["igw_id"]
        public_rtb_id = created["public_rtb_id"]

        created_subnets = []
        for i, subnet_spec in enumerate(spec.subnets):
            self._check_time()
            subnet_name = subnet_spec.name or f"{spec.name}-subnet-{i + 1}"
            subnet = self.ec2.create_subnet(
                VpcId=vpc_id,
                CidrBlock=subnet_spec.cidr_block,
                AvailabilityZone=subnet_spec.availability_zone,
                TagSpecifications=[self._tag_spec("subnet", subnet_name, record_id)],
            )
            subnet_id = subnet["Subnet"]["SubnetId"]
            created["subnet_ids"].append(subnet_id)

            route_table_id = None
            if subnet_spec.public:
                self.ec2.modify_subnet_attribute(
                    SubnetId=subnet_id,
                    MapPublicIpOnLaunch={"Value": True},
                )
                assoc = self.ec2.associate_route_table(
                    SubnetId=subnet_id,
                    RouteTableId=public_rtb_id,
                )
                created["rtb_associations"].append(assoc["AssociationId"])
                route_table_id = public_rtb_id

            created_subnets.append(
                CreatedSubnet(
                    subnet_id=subnet_id,
                    cidr_block=subnet_spec.cidr_block,
                    availability_zone=subnet["Subnet"]["AvailabilityZone"],
                    name=subnet_name,
                    public=subnet_spec.public,
                    route_table_id=route_table_id,
                )
            )

        return {
            "vpc_id": vpc_id,
            "internet_gateway_id": igw_id,
            "public_route_table_id": public_rtb_id,
            "subnets": [s.to_dict() for s in created_subnets],
        }

    def _delete_inner(self, vpc_id):
        subnets = self.ec2.describe_subnets(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
        ).get("Subnets", [])
        route_tables = self.ec2.describe_route_tables(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
        ).get("RouteTables", [])
        igws = self.ec2.describe_internet_gateways(
            Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}]
        ).get("InternetGateways", [])

        for rtb in route_tables:
            for assoc in rtb.get("Associations", []):
                if not assoc.get("Main"):
                    self.ec2.disassociate_route_table(
                        AssociationId=assoc["RouteTableAssociationId"]
                    )
            if not any(a.get("Main") for a in rtb.get("Associations", [])):
                self.ec2.delete_route_table(RouteTableId=rtb["RouteTableId"])

        for igw in igws:
            igw_id = igw["InternetGatewayId"]
            self.ec2.detach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
            self.ec2.delete_internet_gateway(InternetGatewayId=igw_id)

        for subnet in subnets:
            self.ec2.delete_subnet(SubnetId=subnet["SubnetId"])

        self.ec2.delete_vpc(VpcId=vpc_id)

    def _create_public_path(self, vpc_id, name, record_id, created):
        # Record each ID as soon as it exists, so a failure in a later step
        # still rolls it back.
        igw = self.ec2.create_internet_gateway(
            TagSpecifications=[self._tag_spec("internet-gateway", f"{name}-igw", record_id)]
        )
        igw_id = igw["InternetGateway"]["InternetGatewayId"]
        created["igw_id"] = igw_id
        self.ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)

        rtb = self.ec2.create_route_table(
            VpcId=vpc_id,
            TagSpecifications=[self._tag_spec("route-table", f"{name}-public-rtb", record_id)],
        )
        rtb_id = rtb["RouteTable"]["RouteTableId"]
        created["public_rtb_id"] = rtb_id
        self.ec2.create_route(
            RouteTableId=rtb_id,
            DestinationCidrBlock="0.0.0.0/0",
            GatewayId=igw_id,
        )

    def _check_time(self):
        if self._time_left is not None and self._time_left() < MIN_SECONDS_LEFT:
            raise ProvisioningTimeoutError(
                "VPC create ran out of time and was rolled back; nothing was created",
            )

    def _availability_zones(self):
        resp = self.ec2.describe_availability_zones(
            Filters=[{"Name": "state", "Values": ["available"]}]
        )
        zones = [z["ZoneName"] for z in resp.get("AvailabilityZones", [])]
        if not zones:
            raise UpstreamError("No available AZs in this region")
        return zones

    @staticmethod
    def _assign_azs(subnets, azs):
        i = 0
        for subnet in subnets:
            if not subnet.availability_zone:
                subnet.availability_zone = azs[i % len(azs)]
                i += 1

    def _tag_spec(self, resource_type, name, record_id):
        return {
            "ResourceType": resource_type,
            "Tags": [
                {"Key": "Name", "Value": name},
                {"Key": "Project", "Value": self.project_name},
                {"Key": "VpcRecordId", "Value": record_id},
            ],
        }

    def _cleanup(self, created):
        logger.warning("rolling back %s", created)
        for association_id in created.get("rtb_associations") or []:
            _ignore(lambda: self.ec2.disassociate_route_table(AssociationId=association_id))
        for subnet_id in created.get("subnet_ids") or []:
            _ignore(lambda sid=subnet_id: self.ec2.delete_subnet(SubnetId=sid))
        if created.get("public_rtb_id"):
            _ignore(lambda: self.ec2.delete_route_table(RouteTableId=created["public_rtb_id"]))
        if created.get("igw_id") and created.get("vpc_id"):
            _ignore(
                lambda: self.ec2.detach_internet_gateway(
                    InternetGatewayId=created["igw_id"], VpcId=created["vpc_id"]
                )
            )
        if created.get("igw_id"):
            _ignore(lambda: self.ec2.delete_internet_gateway(InternetGatewayId=created["igw_id"]))
        if created.get("vpc_id"):
            _ignore(lambda: self.ec2.delete_vpc(VpcId=created["vpc_id"]))


def _ignore(action):
    try:
        action()
    except Exception:
        logger.exception("cleanup step failed")
