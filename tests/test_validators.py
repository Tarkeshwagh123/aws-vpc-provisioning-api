import pytest

from errors import ValidationError
from validators import parse_create_request


REGION = "us-east-1"
DEFAULTS = {"default_cidr": "10.0.0.0/16", "max_subnets": 16, "region": REGION}


def test_valid_two_public_private_subnets():
    spec = parse_create_request(
        {
            "name": "demo",
            "cidr_block": "10.0.0.0/16",
            "subnets": [
                {"cidr_block": "10.0.1.0/24", "availability_zone": "us-east-1a", "public": True},
                {"cidr_block": "10.0.2.0/24", "name": "private-a", "public": False},
            ],
        },
        **DEFAULTS,
    )
    assert spec.name == "demo"
    assert spec.cidr_block == "10.0.0.0/16"
    assert spec.has_public_subnets() is True
    assert spec.subnets[1].availability_zone is None
    assert spec.subnets[1].name == "private-a"


def test_default_cidr_when_omitted():
    spec = parse_create_request(
        {"subnets": [{"cidr_block": "10.0.0.0/24"}]},
        **DEFAULTS,
    )
    assert spec.cidr_block == "10.0.0.0/16"


def test_rejects_subnet_outside_vpc():
    with pytest.raises(ValidationError, match="not inside"):
        parse_create_request(
            {
                "cidr_block": "10.0.0.0/16",
                "subnets": [{"cidr_block": "192.168.1.0/24"}],
            },
            **DEFAULTS,
        )


def test_rejects_overlapping_subnets():
    with pytest.raises(ValidationError, match="overlaps"):
        parse_create_request(
            {
                "cidr_block": "10.0.0.0/16",
                "subnets": [
                    {"cidr_block": "10.0.1.0/24"},
                    {"cidr_block": "10.0.1.0/25"},
                ],
            },
            **DEFAULTS,
        )


def test_rejects_non_strict_cidr():
    with pytest.raises(ValidationError, match="not a valid CIDR"):
        parse_create_request(
            {"cidr_block": "10.0.1.1/16", "subnets": [{"cidr_block": "10.0.1.0/24"}]},
            **DEFAULTS,
        )


def test_rejects_empty_subnets():
    with pytest.raises(ValidationError, match="non-empty"):
        parse_create_request({"subnets": []}, **DEFAULTS)


def test_rejects_other_region():
    with pytest.raises(ValidationError, match="region must be"):
        parse_create_request(
            {
                "region": "eu-west-1",
                "subnets": [{"cidr_block": "10.0.0.0/24"}],
            },
            **DEFAULTS,
        )


def test_rejects_too_many_subnets():
    with pytest.raises(ValidationError, match="max 2"):
        parse_create_request(
            {
                "subnets": [
                    {"cidr_block": "10.0.0.0/24"},
                    {"cidr_block": "10.0.1.0/24"},
                    {"cidr_block": "10.0.2.0/24"},
                ]
            },
            default_cidr="10.0.0.0/16",
            max_subnets=2,
            region=REGION,
        )


@pytest.mark.parametrize("vpc_cidr", ["10.0.0.0/8", "10.0.0.0/15", "10.0.0.0/29"])
def test_rejects_vpc_cidr_outside_aws_range(vpc_cidr):
    with pytest.raises(ValidationError, match="between /16 and /28"):
        parse_create_request(
            {"cidr_block": vpc_cidr, "subnets": [{"cidr_block": "10.0.0.0/29"}]},
            **DEFAULTS,
        )


@pytest.mark.parametrize("subnet_cidr", ["10.0.0.0/29", "10.0.0.0/32"])
def test_rejects_subnet_cidr_outside_aws_range(subnet_cidr):
    with pytest.raises(ValidationError, match="between /16 and /28"):
        parse_create_request({"subnets": [{"cidr_block": subnet_cidr}]}, **DEFAULTS)


def test_accepts_aws_range_boundaries():
    spec = parse_create_request(
        {"cidr_block": "10.0.0.0/16", "subnets": [{"cidr_block": "10.0.0.0/28"}]},
        **DEFAULTS,
    )
    assert spec.subnets[0].cidr_block == "10.0.0.0/28"
