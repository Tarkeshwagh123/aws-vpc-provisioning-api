import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

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
        # A single conditional write: if a DELETE removed the record after we
        # read it, this fails with 404 instead of writing the record back.
        names = {f"#f{i}": k for i, k in enumerate(fields)}
        values = {f":v{i}": v for i, v in enumerate(fields.values())}
        assignments = ", ".join(f"#f{i} = :v{i}" for i in range(len(fields)))
        try:
            resp = self.table.update_item(
                Key={"id": record_id},
                UpdateExpression=f"SET {assignments}",
                ConditionExpression=Attr("id").exists(),
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if _is_condition_failure(exc):
                raise NotFoundError(f"Record '{record_id}' was not found") from exc
            raise
        return resp["Attributes"]

    def delete(self, record_id):
        try:
            self.table.delete_item(
                Key={"id": record_id}, ConditionExpression=Attr("id").exists()
            )
        except ClientError as exc:
            if _is_condition_failure(exc):
                raise NotFoundError(f"Record '{record_id}' was not found") from exc
            raise

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


def _is_condition_failure(exc):
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def _drop_none(value):
    if isinstance(value, dict):
        return {k: _drop_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_drop_none(v) for v in value]
    return value
