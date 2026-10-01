import json
import os


def _required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing env var {name}")
    return value


class Config:
    def __init__(self):
        self.table_name = _required("TABLE_NAME")
        self.region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
        self.project_name = os.environ.get("PROJECT_NAME", "vpc-api")
        self.max_subnets = int(os.environ.get("MAX_SUBNETS", "16"))
        self.default_vpc_cidr = os.environ.get("DEFAULT_VPC_CIDR", "10.0.0.0/16")
        self.event_bus_name = os.environ.get("EVENT_BUS_NAME", "").strip()
