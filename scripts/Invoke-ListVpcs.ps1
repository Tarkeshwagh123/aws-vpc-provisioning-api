# GET /vpcs  or  GET /vpcs/{id}
param(
    [string]$Id = $env:VPC_RECORD_ID,
    [switch]$Mine
)

$ErrorActionPreference = "Stop"
if (-not $env:ID_TOKEN -or -not $env:API_BASE_URL) {
    Write-Error "Run  . .\scripts\Get-Token.ps1  first"
}

$headers = @{ Authorization = "Bearer $env:ID_TOKEN" }
if ($Id) {
    $uri = "$env:API_BASE_URL/vpcs/$Id"
}
elseif ($Mine) {
    $uri = "$env:API_BASE_URL/vpcs?mine=true"
}
else {
    $uri = "$env:API_BASE_URL/vpcs"
}

Invoke-RestMethod -Method Get -Uri $uri -Headers $headers | ConvertTo-Json -Depth 8
