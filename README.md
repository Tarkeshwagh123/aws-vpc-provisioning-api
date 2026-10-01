# VPC API

Python API on AWS (API Gateway + Lambda). Create a VPC with multiple subnets, save the result in DynamoDB, then retrieve or delete it.

Auth: Cognito. Send `Authorization: Bearer <IdToken>` on every request.

## Endpoints

- `POST /vpcs` — create VPC + subnets, store the result
- `GET /vpcs` — list stored records
- `GET /vpcs/{id}` — get one record
- `PATCH /vpcs/{id}` — update name / status in DynamoDB
- `DELETE /vpcs/{id}` — delete the VPC in EC2 and the DB row

## Deploy

```
cd terraform
copy terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

```
.\scripts\New-DemoUser.ps1 -Email you@example.com -Password "YourPass_123!"
. .\scripts\Get-Token.ps1
.\scripts\Invoke-CreateVpc.ps1
```

Use the **Id token**, not the access token.

## Example

`POST /vpcs`

```json
{
  "name": "demo-vpc",
  "cidr_block": "10.0.0.0/16",
  "subnets": [
    { "cidr_block": "10.0.1.0/24", "public": true, "name": "public-a" },
    { "cidr_block": "10.0.2.0/24", "public": false, "name": "private-a" }
  ]
}
```

## Tests

```
python -m pytest -q
```

## Events and tracing

After a successful create or delete, Lambda publishes `VpcCreated` / `VpcDeleted` to an EventBridge bus. A small audit Lambda listens and writes the event to CloudWatch. If EventBridge is down, the API still returns 201/200.

Logs are JSON and include `request_id`. The same id is returned as `X-Request-Id`. Lambda has X-Ray tracing set to Active. API Gateway access logs go to `/aws/apigateway/...`.

## CI

PRs run pytest and `terraform validate`. If you set the GitHub Actions variable `AWS_ROLE_ARN` to the Terraform output `github_actions_role_arn`, PRs also run `terraform plan` via OIDC (no long-lived AWS keys).

## Cleanup

`DELETE /vpcs/{id}` removes the VPC. `terraform destroy` only removes the API stack.
