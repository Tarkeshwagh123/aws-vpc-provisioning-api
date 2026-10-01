resource "aws_dynamodb_table" "vpcs" {
  name         = "${local.name}-records"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  attribute {
    name = "created_by"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "created_by-index"
    hash_key        = "created_by"
    range_key       = "created_at"
    projection_type = "ALL"
  }
}
