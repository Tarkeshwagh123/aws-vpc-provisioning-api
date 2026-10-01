from unittest.mock import MagicMock

from events import EventPublisher


def test_publish_skips_when_bus_not_configured():
    client = MagicMock()
    EventPublisher("", client=client).publish("VpcCreated", {"id": "1"})
    client.put_events.assert_not_called()


def test_publish_does_not_raise_on_aws_error():
    client = MagicMock()
    client.put_events.side_effect = RuntimeError("bus down")
    EventPublisher("my-bus", client=client).publish("VpcCreated", {"id": "1"})
    client.put_events.assert_called_once()
