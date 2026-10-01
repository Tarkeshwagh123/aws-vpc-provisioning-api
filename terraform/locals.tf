resource "random_id" "suffix" {
  byte_length = 3
}

locals {
  name = "${var.project_name}-${random_id.suffix.hex}"

  tags = {
    Project = var.project_name
  }
}
