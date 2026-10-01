import json

from errors import NotFoundError
from app import lambda_handler


class FakeRepo:
    def __init__(self):
        self.items = {}

    def save(self, item):
        self.items[item["id"]] = item

    def get(self, record_id):
        if record_id not in self.items:
            raise NotFoundError(f"Record '{record_id}' was not found")
        return self.items[record_id]

    def update(self, record_id, fields):
        item = self.get(record_id)
        item.update(fields)
        self.items[record_id] = item
        return item

    def delete(self, record_id):
        self.get(record_id)
        del self.items[record_id]

    def list_all(self, limit=50):
        return list(self.items.values())[:limit]

    def list_by_creator(self, created_by, limit=50):
        return [i for i in self.items.values() if i.get("created_by") == created_by][:limit]


class FakeVpcService:
    def __init__(self):
        self.deleted = []

    def create(self, spec, record_id):
        return {
            "vpc_id": "vpc-123",
            "internet_gateway_id": "igw-123" if spec.has_public_subnets() else None,
            "public_route_table_id": "rtb-123" if spec.has_public_subnets() else None,
            "subnets": [
                {
                    "subnet_id": f"subnet-{i}",
                    "cidr_block": s.cidr_block,
                    "availability_zone": s.availability_zone or "us-east-1a",
                    "name": s.name,
                    "public": s.public,
                    "route_table_id": "rtb-123" if s.public else None,
                }
                for i, s in enumerate(spec.subnets)
            ],
        }

    def delete(self, vpc_id):
        self.deleted.append(vpc_id)


class FakeEvents:
    def __init__(self):
        self.calls = []

    def publish(self, detail_type, detail):
        self.calls.append((detail_type, detail))


class FakeConfig:
    table_name = "test"
    region = "us-east-1"
    project_name = "test"
    max_subnets = 16
    default_vpc_cidr = "10.0.0.0/16"
    event_bus_name = "test-bus"


class FakeContext:
    aws_request_id = "req-abc"


def _event(method, path, body=None, query=None, sub="user-1", username="alice"):
    event = {
        "rawPath": path,
        "requestContext": {
            "requestId": "apigw-1",
            "http": {"method": method},
            "authorizer": {"jwt": {"claims": {"sub": sub, "cognito:username": username}}},
        },
    }
    if body is not None:
        event["body"] = json.dumps(body)
    if query:
        event["queryStringParameters"] = query
    return event


def _deps(repo=None, vpc_service=None, events=None):
    return {
        "config": FakeConfig(),
        "repo": repo or FakeRepo(),
        "vpc_service": vpc_service or FakeVpcService(),
        "events": events or FakeEvents(),
        "new_id": lambda: "rec-1",
        "now": lambda: "2026-10-01T00:00:00+00:00",
        "request_id": "req-abc",
    }


def test_create_vpc_publishes_event():
    repo = FakeRepo()
    events = FakeEvents()
    result = lambda_handler(
        _event(
            "POST",
            "/vpcs",
            {
                "name": "demo",
                "subnets": [
                    {"cidr_block": "10.0.1.0/24", "public": True},
                    {"cidr_block": "10.0.2.0/24", "public": False},
                ],
            },
        ),
        FakeContext(),
        deps=_deps(repo, events=events),
    )
    assert result["statusCode"] == 201
    assert result["headers"]["X-Request-Id"] == "req-abc"
    body = json.loads(result["body"])
    assert body["vpc_id"] == "vpc-123"
    assert events.calls[0][0] == "VpcCreated"
    assert events.calls[0][1]["vpc_id"] == "vpc-123"


def test_bad_json():
    event = _event("POST", "/vpcs")
    event["body"] = "{not-json"
    result = lambda_handler(event, FakeContext(), deps=_deps())
    assert result["statusCode"] == 400


def test_get_missing():
    result = lambda_handler(_event("GET", "/vpcs/missing"), FakeContext(), deps=_deps())
    assert result["statusCode"] == 404


def test_patch_vpc_status():
    repo = FakeRepo()
    repo.save({"id": "rec-1", "name": "old", "status": "ACTIVE"})
    result = lambda_handler(
        _event("PATCH", "/vpcs/rec-1", {"name": "new", "status": "DISABLED"}),
        FakeContext(),
        deps=_deps(repo),
    )
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["name"] == "new"
    assert body["status"] == "DISABLED"


def test_delete_vpc_publishes_event():
    repo = FakeRepo()
    svc = FakeVpcService()
    events = FakeEvents()
    repo.save({"id": "rec-1", "vpc_id": "vpc-123"})
    result = lambda_handler(
        _event("DELETE", "/vpcs/rec-1"), FakeContext(), deps=_deps(repo, svc, events)
    )
    assert result["statusCode"] == 200
    assert svc.deleted == ["vpc-123"]
    assert events.calls[0][0] == "VpcDeleted"


def test_unknown_route():
    result = lambda_handler(_event("GET", "/nope"), FakeContext(), deps=_deps())
    assert result["statusCode"] == 404
