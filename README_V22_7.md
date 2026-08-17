# V22.7 — AWS Lambda Deployment Foundation

V22.7 prepares the already-tested Brain Core for a real AWS Lambda deployment without enabling any schedule.

## Added
- stable Lambda handler module: `v22.runtime.lambda_entry.lambda_handler`
- AWS safety guard: deployed Lambda rejects disposable SQLite as durable Brain memory
- AWS Lambda defaults to the live evidence collector unless explicitly overridden
- reproducible Python 3.12 x86_64 Linux deployment ZIP builder
- manual GitHub package-build workflow
- manual GitHub OIDC deployment workflow scaffold
- Stage 7 deployment tests and smoke test

## Intended validation configuration
- AWS region: `ap-southeast-2` (Sydney)
- runtime: Python 3.12
- architecture: x86_64
- memory: 512 MB
- timeout: 180 seconds
- database: existing Neon pooled `DATABASE_URL`
- collector: `live`
- migrations: disabled during normal Lambda cycles; schema is managed separately

## Still deliberately OFF
- no recurring EventBridge schedule
- no Restate
- no AI/agents
- no automated trading

The deployment workflow uses GitHub OIDC and expects repository variable `AWS_V22_DEPLOY_ROLE_ARN`. No long-lived AWS access key is designed into V22.7.

## AWS bootstrap templates
`aws/v22_lambda_foundation.yaml` creates the validation Lambda and its basic execution role but no schedule. `aws/v22_github_oidc_deploy_role.yaml` creates a least-privilege GitHub OIDC deployment role restricted to this repository's `main` branch; it can also reuse an existing GitHub OIDC provider ARN.
