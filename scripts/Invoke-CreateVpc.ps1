# POST /vpcs using examples/create-vpc.json
param(
    [string]$BodyFile = (Join-Path $PSScriptRoot "..\examples\create-vpc.json")
)

$ErrorActionPreference = "Stop"
if (-not $env:ID_TOKEN -or -not $env:API_BASE_URL) {
    Write-Error "Run  . .\scripts\Get-Token.ps1  first"
}

$headers = @{
    Authorization  = "Bearer $env:ID_TOKEN"
    "Content-Type" = "application/json"
}
$body = Get-Content -Raw $BodyFile
$response = Invoke-RestMethod -Method Post -Uri "$env:API_BASE_URL/vpcs" -Headers $headers -Body $body
$response | ConvertTo-Json -Depth 8
$env:VPC_RECORD_ID = $response.id
Write-Host "Saved VPC_RECORD_ID=$env:VPC_RECORD_ID"
