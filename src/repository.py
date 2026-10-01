import boto3
from boto3.dynamodb.conditions import Key

from errors import NotFoundError


class VpcRepository:
    def __init__(self, table_name, dynamodb_resource=None):
        resource = dynamodb_resource or boto3.resource("dynamodb")
        self.table = resource.Table(table_name)

    def save(self, item):
        self.table.put_item(Item=_drop_none(item))

    def get(self, record_id):
        item = self.table.get_item(Key={"id": record_id}).get("Item")
        if not item:
            raise NotFoundError(f"Record '{record_id}' was not found")
        return item

    def update(self, record_id, fields):
        item = self.get(record_id)
        item.update(fields)
        self.save(item)
        return item

    def delete(self, record_id):
        self.get(record_id)  # 404 if missing
        self.table.delete_item(Key={"id": record_id})

    def list_all(self, limit=50):
        items = []
        kwargs = {"Limit": min(limit, 100)}
        while True:
            resp = self.table.scan(**kwargs)
            items.extend(resp.get("Items", []))
            if len(items) >= limit or "LastEvaluatedKey" not in resp:
                break
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        return items[:limit]

    def list_by_creator(self, created_by, limit=50):
        resp = self.table.query(
            IndexName="created_by-index",
            KeyConditionExpression=Key("created_by").eq(created_by),
            ScanIndexForward=False,
            Limit=min(limit, 100),
        )
        return resp.get("Items", [])[:limit]


def _drop_none(value):
    if isinstance(value, dict):
        return {k: _drop_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_none(v) for v in value]
    return value
