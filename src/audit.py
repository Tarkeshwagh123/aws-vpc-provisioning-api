import json


def lambda_handler(event, context):
    """Triggered by EventBridge when a VPC is created or deleted."""
    print(
        json.dumps(
            {
                "msg": "vpc_event",
                "detail_type": event.get("detail-type"),
                "detail": event.get("detail"),
                "request_id": getattr(context, "aws_request_id", None),
            },
            default=str,
        )
    )
    return {"ok": True}
