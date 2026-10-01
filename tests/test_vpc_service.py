from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from errors import ProvisioningTimeoutError, UpstreamError
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


def _client_error(code, op="Op"):
    return ClientError({"Error": {"Code": code, "Message": code}}, op)


def _public_spec():
    return VpcSpec(
        name="demo",
        cidr_block="10.0.0.0/16",
        region="us-east-1",
        subnets=[SubnetSpec("10.0.1.0/24", public=True)],
    )


@pytest.mark.parametrize("failing_call", ["attach_internet_gateway", "create_route_table", "create_route"])
def test_cleanup_removes_igw_and_route_table_when_public_path_fails(failing_call):
    client = _ec2()
    getattr(client, failing_call).side_effect = _client_error("Boom", failing_call)
    with pytest.raises(UpstreamError):
        VpcService("us-east-1", "test", ec2_client=client).create(_public_spec(), "rec-1")

    client.delete_internet_gateway.assert_called_once_with(InternetGatewayId="igw-abc")
    if failing_call == "create_route":
        client.delete_route_table.assert_called_once_with(RouteTableId="rtb-abc")
    else:
        client.delete_route_table.assert_not_called()
    client.delete_vpc.assert_called_once_with(VpcId="vpc-abc")


def test_delete_treats_missing_vpc_as_deleted():
    client = _ec2()
    client.describe_subnets.return_value = {"Subnets": []}
    client.describe_route_tables.return_value = {"RouteTables": []}
    client.describe_internet_gateways.return_value = {"InternetGateways": []}
    client.delete_vpc.side_effect = _client_error("InvalidVpcID.NotFound", "DeleteVpc")
    VpcService("us-east-1", "test", ec2_client=client).delete("vpc-gone")


def test_delete_still_fails_on_other_errors():
    client = _ec2()
    client.describe_subnets.return_value = {"Subnets": []}
    client.describe_route_tables.return_value = {"RouteTables": []}
    client.describe_internet_gateways.return_value = {"InternetGateways": []}
    client.delete_vpc.side_effect = _client_error("DependencyViolation", "DeleteVpc")
    with pytest.raises(UpstreamError):
        VpcService("us-east-1", "test", ec2_client=client).delete("vpc-abc")


def test_create_rolls_back_when_time_runs_low():
    spec = VpcSpec(
        name="demo",
        cidr_block="10.0.0.0/16",
        region="us-east-1",
        subnets=[SubnetSpec("10.0.1.0/24"), SubnetSpec("10.0.2.0/24")],
    )
    client = _ec2()
    clock = iter([20, 20, 3])  # create_vpc, subnet 1, then too little left for subnet 2
    with pytest.raises(ProvisioningTimeoutError):
        VpcService("us-east-1", "test", ec2_client=client).create(
            spec, "rec-1", time_left=lambda: next(clock)
        )
    assert client.create_subnet.call_count == 1
    client.delete_subnet.assert_called_once_with(SubnetId="subnet-1")
    client.delete_vpc.assert_called_once_with(VpcId="vpc-abc")


def test_create_does_not_start_when_no_time_left():
    client = _ec2()
    with pytest.raises(ProvisioningTimeoutError):
        VpcService("us-east-1", "test", ec2_client=client).create(
            _public_spec(), "rec-1", time_left=lambda: 1
        )
    client.create_vpc.assert_not_called()
