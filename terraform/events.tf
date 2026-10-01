resource "aws_cloudwatch_event_bus" "vpc" {
  name = "${local.name}-events"
}

resource "aws_cloudwatch_event_rule" "vpc" {
  name           = "${local.name}-vpc-lifecycle"
  event_bus_name = aws_cloudwatch_event_bus.vpc.name
  event_pattern = jsonencode({
    source      = ["vpc.api"]
    detail-type = ["VpcCreated", "VpcDeleted"]
  })
}

resource "aws_cloudwatch_log_group" "audit" {
  name              = "/aws/lambda/${local.name}-audit"
  retention_in_days = 14
}

resource "aws_lambda_function" "audit" {
  function_name    = "${local.name}-audit"
  role             = aws_iam_role.audit.arn
  handler          = "audit.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = 10
  memory_size      = 128

  tracing_config {
    mode = "Active"
  }

  depends_on = [aws_cloudwatch_log_group.audit]
}

resource "aws_iam_role" "audit" {
  name               = "${local.name}-audit"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "audit_logs" {
  role       = aws_iam_role.audit.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "audit_xray" {
  role       = aws_iam_role.audit.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

resource "aws_lambda_permission" "audit_events" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.audit.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.vpc.arn
}

resource "aws_cloudwatch_event_target" "audit" {
  rule           = aws_cloudwatch_event_rule.vpc.name
  event_bus_name = aws_cloudwatch_event_bus.vpc.name
  arn            = aws_lambda_function.audit.arn
}
