from unittest.mock import MagicMock

from models import SubnetSpec, VpcSpec
from vpc_service import VpcService


def _ec2():
    client = MagicMock()
    client.describe_availability_zones.return_value = {
        "AvailabilityZones": [{"ZoneName": "us-east-1a"}, {"ZoneName": "us-east-1b"}]
    }
    client.create_vpc.return_value = {"Vpc": {"VpcId": "vpc-abc"}}
    client.create_internet_gateway.return_value = {
        "InternetGateway": {"InternetGatewayId": "igw-abc"}
    }
    client.create_route_table.return_value = {"RouteTable": {"RouteTableId": "rtb-abc"}}
    client.create_subnet.side_effect = [
        {"Subnet": {"SubnetId": "subnet-1", "AvailabilityZone": "us-east-1a"}},
        {"Subnet": {"SubnetId": "subnet-2", "AvailabilityZone": "us-east-1b"}},
    ]
    client.associate_route_table.return_value = {"AssociationId": "rtbassoc-1"}
    return client


def test_creates_igw_only_when_a_subnet_is_public():
    spec = VpcSpec(
        name="demo",
        cidr_block="10.0.0.0/16",
        region="us-east-1",
        subnets=[
            SubnetSpec("10.0.1.0/24", public=True),
            SubnetSpec("10.0.2.0/24", public=False),
        ],
    )
    client = _ec2()
    result = VpcService("us-east-1", "test", ec2_client=client).create(spec, "rec-1")
    assert result["vpc_id"] == "vpc-abc"
    assert result["internet_gateway_id"] == "igw-abc"
    client.create_internet_gateway.assert_called_once()
    client.associate_route_table.assert_called_once()
    assert result["subnets"][0]["public"] is True
    assert result["subnets"][1]["public"] is False


def test_assigns_azs_round_robin_when_omitted():
    spec = VpcSpec(
        name="demo",
        cidr_block="10.0.0.0/16",
        region="us-east-1",
        subnets=[SubnetSpec("10.0.1.0/24"), SubnetSpec("10.0.2.0/24")],
    )
    client = _ec2()
    VpcService("us-east-1", "test", ec2_client=client).create(spec, "rec-1")
    azs = [c.kwargs["AvailabilityZone"] for c in client.create_subnet.call_args_list]
    assert azs == ["us-east-1a", "us-east-1b"]
    client.create_internet_gateway.assert_not_called()


def test_cleanup_on_subnet_failure():
    spec = VpcSpec(
        name="demo",
        cidr_block="10.0.0.0/16",
        region="us-east-1",
        subnets=[SubnetSpec("10.0.1.0/24")],
    )
    client = _ec2()
    client.create_subnet.side_effect = RuntimeError("boom")
    service = VpcService("us-east-1", "test", ec2_client=client)
    try:
        service.create(spec, "rec-1")
        assert False, "expected failure"
    except RuntimeError:
        pass
    client.delete_vpc.assert_called_once_with(VpcId="vpc-abc")


def test_delete_vpc_removes_subnets_and_igw():
    client = _ec2()
    client.describe_subnets.return_value = {
        "Subnets": [{"SubnetId": "subnet-1"}, {"SubnetId": "subnet-2"}]
    }
    client.describe_route_tables.return_value = {
        "RouteTables": [
            {
                "RouteTableId": "rtb-main",
                "Associations": [{"Main": True, "RouteTableAssociationId": "assoc-main"}],
            },
            {
                "RouteTableId": "rtb-pub",
                "Associations": [
                    {"Main": False, "RouteTableAssociationId": "assoc-pub"}
                ],
            },
        ]
    }
    client.describe_internet_gateways.return_value = {
        "InternetGateways": [{"InternetGatewayId": "igw-abc"}]
    }
    VpcService("us-east-1", "test", ec2_client=client).delete("vpc-abc")
    client.delete_subnet.assert_any_call(SubnetId="subnet-1")
    client.delete_internet_gateway.assert_called_once_with(InternetGatewayId="igw-abc")
    client.delete_vpc.assert_called_once_with(VpcId="vpc-abc")
