# Obtain a Cognito ID token for the HTTP API.
# Dot-source so the variables stay in your shell:
#   . .\scripts\Get-Token.ps1
param(
    [string]$Email = $env:DEMO_USER_EMAIL,
    [string]$Password = $env:DEMO_USER_PASSWORD
)

$ErrorActionPreference = "Stop"
$terraformDir = Join-Path $PSScriptRoot "..\terraform"

if (-not $Email) { $Email = Read-Host "Cognito user email" }
if (-not $Password) {
    $secure = Read-Host "Password" -AsSecureString
    $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    )
}

$outputs = terraform -chdir="$terraformDir" output -json | ConvertFrom-Json
$clientId = $outputs.user_pool_client_id.value
$apiBase = $outputs.api_base_url.value
$region = $outputs.aws_region.value

$auth = aws cognito-idp initiate-auth `
    --region $region `
    --auth-flow USER_PASSWORD_AUTH `
    --client-id $clientId `
    --auth-parameters "USERNAME=$Email,PASSWORD=$Password" `
    --output json | ConvertFrom-Json

$env:ID_TOKEN = $auth.AuthenticationResult.IdToken
$env:API_BASE_URL = $apiBase
$env:AWS_REGION = $region

Write-Host "API_BASE_URL=$env:API_BASE_URL"
Write-Host "ID_TOKEN is set ($($env:ID_TOKEN.Substring(0, 20))...)"
Write-Host "Use the ID token (not the access token) in Authorization: Bearer ..."
