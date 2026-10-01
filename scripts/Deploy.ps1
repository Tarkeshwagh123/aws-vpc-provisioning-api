# Deploy the serverless stack (API Gateway, Lambda, Cognito, DynamoDB).
param(
    [switch]$AutoApprove
)

$ErrorActionPreference = "Stop"
$terraformDir = Join-Path $PSScriptRoot "..\terraform"

if (-not (Get-Command terraform -ErrorAction SilentlyContinue)) {
    Write-Error "Terraform is not on PATH. Install from https://developer.hashicorp.com/terraform/install"
}

Push-Location $terraformDir
try {
    if (-not (Test-Path "terraform.tfvars")) {
        Write-Host "No terraform.tfvars found. Copying example (no demo user until you edit it)."
        Copy-Item "terraform.tfvars.example" "terraform.tfvars"
    }
    terraform init -input=false
    if ($AutoApprove) {
        terraform apply -auto-approve
    }
    else {
        terraform apply
    }
    Write-Host ""
    Write-Host "Outputs:"
    terraform output
}
finally {
    Pop-Location
}
