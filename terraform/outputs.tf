output "api_base_url" {
  value = aws_apigatewayv2_api.this.api_endpoint
}

output "user_pool_id" {
  value = aws_cognito_user_pool.this.id
}

output "user_pool_client_id" {
  value = aws_cognito_user_pool_client.this.id
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.vpcs.name
}

output "lambda_function_name" {
  value = aws_lambda_function.api.function_name
}

output "event_bus_name" {
  value = aws_cloudwatch_event_bus.vpc.name
}

output "github_actions_role_arn" {
  value = aws_iam_role.github_actions.arn
}
