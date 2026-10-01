#!/usr/bin/env bash
# Deploy with Terraform (Linux/macOS).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/terraform"
if [[ ! -f terraform.tfvars ]]; then
  cp terraform.tfvars.example terraform.tfvars
  echo "Copied terraform.tfvars.example → terraform.tfvars"
fi
terraform init -input=false
terraform apply "$@"
terraform output
