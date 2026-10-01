variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "vpc-api"
}

variable "lambda_timeout_seconds" {
  type    = number
  default = 29

  # API Gateway HTTP APIs stop waiting after 30s. A longer Lambda keeps
  # creating the VPC after the client already got a 503, and a retry then
  # creates a duplicate.
  validation {
    condition     = var.lambda_timeout_seconds >= 10 && var.lambda_timeout_seconds <= 29
    error_message = "lambda_timeout_seconds must be between 10 and 29 (API Gateway's 30s integration limit)."
  }
}

variable "demo_user_email" {
  type    = string
  default = ""
}

variable "demo_user_password" {
  type      = string
  default   = ""
  sensitive = true
}

variable "cors_allow_origins" {
  type    = list(string)
  default = ["*"]
}
