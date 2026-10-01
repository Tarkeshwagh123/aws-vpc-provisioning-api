import json


def json_response(status_code, body, request_id=None):
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
    }
    if request_id:
        headers["X-Request-Id"] = request_id
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, default=str),
    }


def error_response(status_code, message, details=None, request_id=None):
    payload = {"error": message}
    if details:
        payload["details"] = details
    return json_response(status_code, payload, request_id=request_id)
