from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from errors import NotFoundError
from repository import VpcRepository


def _repo():
    table = MagicMock()
    resource = MagicMock()
    resource.Table.return_value = table
    return VpcRepository("vpcs", dynamodb_resource=resource), table


def _condition_failed():
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "failed"}}, "Op"
    )


def test_update_is_a_single_conditional_write():
    repo, table = _repo()
    table.update_item.return_value = {"Attributes": {"id": "rec-1", "name": "new"}}

    item = repo.update("rec-1", {"name": "new", "status": "DISABLED"})

    assert item == {"id": "rec-1", "name": "new"}
    table.put_item.assert_not_called()
    kwargs = table.update_item.call_args.kwargs
    assert kwargs["Key"] == {"id": "rec-1"}
    assert kwargs["ConditionExpression"] is not None
    assert set(kwargs["ExpressionAttributeNames"].values()) == {"name", "status"}


def test_update_of_deleted_record_is_404_not_a_resurrection():
    repo, table = _repo()
    table.update_item.side_effect = _condition_failed()
    with pytest.raises(NotFoundError):
        repo.update("rec-1", {"name": "new"})
    table.put_item.assert_not_called()


def test_delete_of_missing_record_is_404():
    repo, table = _repo()
    table.delete_item.side_effect = _condition_failed()
    with pytest.raises(NotFoundError):
        repo.delete("rec-1")


def test_other_dynamodb_errors_propagate():
    repo, table = _repo()
    table.update_item.side_effect = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "x"}}, "Op"
    )
    with pytest.raises(ClientError):
        repo.update("rec-1", {"name": "new"})
