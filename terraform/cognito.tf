resource "aws_cognito_user_pool" "this" {
  name = "${local.name}-users"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # The client is public (no secret), so open sign-up would let anyone on the
  # internet get a token and provision VPCs in this account. Users are created
  # by an admin (scripts/New-DemoUser.ps1 or the demo_user_* variables).
  admin_create_user_config {
    allow_admin_create_user_only = true
  }
}

resource "aws_cognito_user_pool_client" "this" {
  name         = "${local.name}-client"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  prevent_user_existence_errors = "ENABLED"
  supported_identity_providers  = ["COGNITO"]

  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}

resource "aws_cognito_user" "demo" {
  count = var.demo_user_email != "" && var.demo_user_password != "" ? 1 : 0

  user_pool_id = aws_cognito_user_pool.this.id
  username     = var.demo_user_email

  attributes = {
    email          = var.demo_user_email
    email_verified = true
  }

  password       = var.demo_user_password
  message_action = "SUPPRESS"
  enabled        = true
}
