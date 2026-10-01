import json
import logging

import boto3

logger = logging.getLogger(__name__)

SOURCE = "vpc.api"


class EventPublisher:
    def __init__(self, bus_name, client=None):
        self.bus_name = bus_name or ""
        self.client = client or boto3.client("events")

    def publish(self, detail_type, detail):
        if not self.bus_name:
            return
        try:
            self.client.put_events(
                Entries=[
                    {
                        "Source": SOURCE,
                        "DetailType": detail_type,
                        "Detail": json.dumps(detail, default=str),
                        "EventBusName": self.bus_name,
                    }
                ]
            )
        except Exception:
            # API call already succeeded; do not fail the request because of events.
            logger.exception("failed to publish %s", detail_type)
