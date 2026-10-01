import base64
import binascii
import json
import logging
import re
import traceback
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs

from auth import caller_from_event
from config import Config
from errors import ApiError, ForbiddenError, ValidationError
from events import EventPublisher
from repository import VpcRepository
from responses import error_response, json_response
from validators import parse_create_request, parse_vpc_patch
from vpc_service import VpcService

logger = logging.getLogger()
logger.setLevel(logging.INFO)

VPC_ID_PATH = re.compile(r"^/vpcs/([^/]+)$")


def lambda_handler(event, context, deps=None):
    request_id = _request_id(event, context)
    try:
        deps = deps or default_dependencies()
        deps["request_id"] = request_id
        deps.setdefault("time_left", _time_left(context))
        method, path = _route_key(event)
        _log("info", "request", request_id=request_id, method=method, path=path)

        if path == "/vpcs" and method == "POST":
            return _create_vpc(event, deps)
        if path == "/vpcs" and method == "GET":
            return _list_vpcs(event, deps)

        match = VPC_ID_PATH.match(path)
        if match:
            record_id = match.group(1)
            if method == "GET":
                return json_response(200, deps["repo"].get(record_id), request_id=request_id)
            if method == "PATCH":
                return _patch_vpc(event, record_id, deps)
            if method == "DELETE":
                return _delete_vpc(event, record_id, deps)

        return error_response(404, f"No route for {method} {path}", request_id=request_id)
    except ApiError as exc:
        _log("warning", "api_error", request_id=request_id, status=exc.status_code, error=exc.message)
        return error_response(exc.status_code, exc.message, exc.details, request_id=request_id)
    except Exception:
        _log("error", "unhandled", request_id=request_id, traceback=traceback.format_exc())
        return error_response(500, "Internal server error", request_id=request_id)


def default_dependencies():
    config = Config()
    return {
        "config": config,
        "repo": VpcRepository(config.table_name),
        "vpc_service": VpcService(config.region, config.project_name),
        "events": EventPublisher(config.event_bus_name),
        "new_id": lambda: str(uuid.uuid4()),
        "now": lambda: datetime.now(timezone.utc).isoformat(),
        "request_id": "local",
    }


def _request_id(event, context):
    if context is not None and getattr(context, "aws_request_id", None):
        return context.aws_request_id
    return (event.get("requestContext") or {}).get("requestId") or "local"


def _time_left(context):
    remaining = getattr(context, "get_remaining_time_in_millis", None)
    if remaining is None:
        return None
    return lambda: remaining() / 1000


def _log(level, msg, **fields):
    line = json.dumps({"level": level, "msg": msg, **fields}, default=str)
    if level == "error":
        logger.error(line)
    elif level == "warning":
        logger.warning(line)
    else:
        logger.info(line)


def _route_key(event):
    http = event.get("requestContext", {}).get("http", {})
    method = (http.get("method") or event.get("httpMethod") or "GET").upper()
    path = event.get("rawPath") or event.get("path") or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return method, path


def _create_vpc(event, deps):
    request_id = deps.get("request_id")
    config = deps["config"]
    spec = parse_create_request(
        _parse_json_body(event),
        default_cidr=config.default_vpc_cidr,
        max_subnets=config.max_subnets,
        region=config.region,
    )
    caller = caller_from_event(event)
    record_id = deps["new_id"]()
    aws_result = deps["vpc_service"].create(spec, record_id, time_left=deps.get("time_left"))

    record = {
        "id": record_id,
        "name": spec.name,
        "vpc_id": aws_result["vpc_id"],
        "cidr_block": spec.cidr_block,
        "region": spec.region,
        "subnets": aws_result["subnets"],
        "internet_gateway_id": aws_result["internet_gateway_id"],
        "public_route_table_id": aws_result["public_route_table_id"],
        "status": "ACTIVE",
        "created_by": caller["sub"],
        "created_by_username": caller["username"],
        "created_at": deps["now"](),
        "updated_at": deps["now"](),
    }
    _save_or_roll_back(record, deps)
    deps["events"].publish(
        "VpcCreated",
        {
            "id": record_id,
            "vpc_id": record["vpc_id"],
            "cidr_block": record["cidr_block"],
            "created_by": record["created_by"],
            "request_id": request_id,
        },
    )
    _log("info", "vpc_created", request_id=request_id, id=record_id, vpc_id=record["vpc_id"])
    return json_response(201, record, request_id=request_id)


def _save_or_roll_back(record, deps):
    """Without a record the VPC can't be listed or deleted through the API,
    so a failed save removes the VPC again before the error is returned."""
    request_id = deps.get("request_id")
    try:
        deps["repo"].save(record)
    except Exception:
        _log("error", "vpc_record_save_failed", request_id=request_id, id=record["id"],
             vpc_id=record["vpc_id"], traceback=traceback.format_exc())
        try:
            deps["vpc_service"].delete(record["vpc_id"])
        except Exception:
            # Left for an operator: the VPC is tagged VpcRecordId=<id>.
            _log("error", "vpc_rollback_failed", request_id=request_id, id=record["id"],
                 vpc_id=record["vpc_id"], traceback=traceback.format_exc())
        raise


def _require_owner(event, item):
    caller = caller_from_event(event)
    if caller["sub"] == "unknown" or item.get("created_by") != caller["sub"]:
        raise ForbiddenError("Only the user who created this VPC can change or delete it")


def _list_vpcs(event, deps):
    request_id = deps.get("request_id")
    params = _query_params(event)
    limit = _parse_limit(params.get("limit"))
    created_by = params.get("created_by")
    mine = params.get("mine", "").lower() in {"1", "true", "yes"}

    if mine:
        caller = caller_from_event(event)
        items = deps["repo"].list_by_creator(caller["sub"], limit=limit)
    elif created_by:
        items = deps["repo"].list_by_creator(created_by, limit=limit)
    else:
        items = deps["repo"].list_all(limit=limit)

    return json_response(200, {"items": items, "count": len(items)}, request_id=request_id)


def _patch_vpc(event, record_id, deps):
    _require_owner(event, deps["repo"].get(record_id))
    updates = parse_vpc_patch(_parse_json_body(event))
    updates["updated_at"] = deps["now"]()
    return json_response(
        200, deps["repo"].update(record_id, updates), request_id=deps.get("request_id")
    )


def _delete_vpc(event, record_id, deps):
    request_id = deps.get("request_id")
    item = deps["repo"].get(record_id)
    _require_owner(event, item)
    if item.get("vpc_id"):
        deps["vpc_service"].delete(item["vpc_id"])
    deps["repo"].delete(record_id)
    deps["events"].publish(
        "VpcDeleted",
        {"id": record_id, "vpc_id": item.get("vpc_id"), "request_id": request_id},
    )
    _log("info", "vpc_deleted", request_id=request_id, id=record_id, vpc_id=item.get("vpc_id"))
    return json_response(
        200, {"deleted": record_id, "vpc_id": item.get("vpc_id")}, request_id=request_id
    )


def _parse_json_body(event):
    raw = event.get("body")
    if raw in (None, ""):
        return {}
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise ValidationError("Request body is not valid base64-encoded UTF-8") from exc
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("Request body is not valid JSON") from exc


def _query_params(event):
    params = event.get("queryStringParameters") or {}
    if params:
        return {k: (v if v is not None else "") for k, v in params.items()}
    parsed = parse_qs(event.get("rawQueryString") or "", keep_blank_values=True)
    return {k: vs[-1] for k, vs in parsed.items()}


def _parse_limit(value):
    if not value:
        return 50
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("limit must be an integer") from exc
    if limit < 1 or limit > 100:
        raise ValidationError("limit must be between 1 and 100")
    return limit
