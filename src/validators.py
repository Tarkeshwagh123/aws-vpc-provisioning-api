import ipaddress
import re
from typing import Any

from errors import ValidationError
from models import SubnetSpec, VpcSpec

NAME_RE = re.compile(r"^[\w .\-/]{1,255}$")


def parse_create_request(body, *, default_cidr, max_subnets, region) -> VpcSpec:
    data = _as_dict(body)
    name = _optional_str(data.get("name"), "name") or "vpc-api-vpc"
    if not NAME_RE.match(name):
        raise ValidationError("name has invalid characters")

    vpc_net = _cidr(data.get("cidr_block", default_cidr), "cidr_block")

    requested_region = data.get("region") or region
    if not isinstance(requested_region, str) or not requested_region.strip():
        raise ValidationError("region must be a string")
    requested_region = requested_region.strip()
    if requested_region != region:
        raise ValidationError(f"region must be {region} (where the API is deployed)")

    subnets_raw = data.get("subnets")
    if not isinstance(subnets_raw, list) or not subnets_raw:
        raise ValidationError("subnets must be a non-empty array")
    if len(subnets_raw) > max_subnets:
        raise ValidationError(f"max {max_subnets} subnets per request")

    parsed = []
    nets = []
    for i, item in enumerate(subnets_raw):
        prefix = f"subnets[{i}]"
        if not isinstance(item, dict):
            raise ValidationError(f"{prefix} must be an object")

        subnet_net = _cidr(item.get("cidr_block"), f"{prefix}.cidr_block")
        if not subnet_net.subnet_of(vpc_net):
            raise ValidationError(f"{prefix}.cidr_block is not inside the VPC CIDR")
        for other in nets:
            if subnet_net.overlaps(other):
                raise ValidationError(f"{prefix}.cidr_block overlaps another subnet")

        az = item.get("availability_zone")
        if az is not None and not isinstance(az, str):
            raise ValidationError(f"{prefix}.availability_zone must be a string")
        az = az.strip() if isinstance(az, str) and az.strip() else None

        public = item.get("public", False)
        if not isinstance(public, bool):
            raise ValidationError(f"{prefix}.public must be true or false")

        parsed.append(
            SubnetSpec(
                cidr_block=str(subnet_net),
                availability_zone=az,
                name=_optional_str(item.get("name"), f"{prefix}.name"),
                public=public,
            )
        )
        nets.append(subnet_net)

    return VpcSpec(
        name=name,
        cidr_block=str(vpc_net),
        subnets=parsed,
        region=requested_region,
    )


def parse_vpc_patch(body):
    data = _as_dict(body)
    allowed = {}
    if "name" in data:
        name = _optional_str(data.get("name"), "name")
        if not name:
            raise ValidationError("name cannot be empty")
        if not NAME_RE.match(name):
            raise ValidationError("name has invalid characters")
        allowed["name"] = name
    if "status" in data:
        status = data.get("status")
        if status not in ("ACTIVE", "DISABLED"):
            raise ValidationError("status must be ACTIVE or DISABLED")
        allowed["status"] = status
    if not allowed:
        raise ValidationError("nothing to update (name, status)")
    return allowed


def _as_dict(body) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object")
    return body


def _cidr(value, field_name) -> ipaddress.IPv4Network:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} is required, e.g. 10.0.0.0/16")
    try:
        network = ipaddress.ip_network(value.strip(), strict=True)
    except ValueError as exc:
        raise ValidationError(f"{field_name} is not a valid CIDR: {exc}") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise ValidationError(f"{field_name} must be IPv4")
    return network


def _optional_str(value, field_name):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")
    text = value.strip()
    return text or None
