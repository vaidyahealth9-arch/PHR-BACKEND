# Repo Standards (phr_backend1)

## Required GitHub Environment Variables

- `GCP_PROJECT_ID`
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_DEPLOYER_SERVICE_ACCOUNT`
- `PHR_BACKEND_SUBSTITUTIONS`

## Required Branch Protection Checks (recommended)

- `verify`
- `markdown-lint`
- `link-check`

## Secret policy

- Do not commit secret values.
- Keep runtime secrets in GCP Secret Manager.
- Keep only CI bootstrap values in GitHub environment vars/secrets.
