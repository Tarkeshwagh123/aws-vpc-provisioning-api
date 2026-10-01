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
  default = 60
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
