# Admin-create a confirmed Cognito user for the demo (no signup email).
param(
    [Parameter(Mandatory = $true)][string]$Email,
    [Parameter(Mandatory = $true)][string]$Password
)

$ErrorActionPreference = "Stop"
$terraformDir = Join-Path $PSScriptRoot "..\terraform"
$outputs = terraform -chdir="$terraformDir" output -json | ConvertFrom-Json
$poolId = $outputs.user_pool_id.value
$region = $outputs.aws_region.value

aws cognito-idp admin-create-user `
    --region $region `
    --user-pool-id $poolId `
    --username $Email `
    --user-attributes Name=email,Value=$Email Name=email_verified,Value=true `
    --message-action SUPPRESS | Out-Null

aws cognito-idp admin-set-user-password `
    --region $region `
    --user-pool-id $poolId `
    --username $Email `
    --password $Password `
    --permanent

$env:DEMO_USER_EMAIL = $Email
$env:DEMO_USER_PASSWORD = $Password
Write-Host "Created $Email in $poolId"
