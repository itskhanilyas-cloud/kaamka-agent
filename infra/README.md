# Azure deployment

1. **One-time setup (owner, ~15 minutes).** In Azure Cloud Shell (Bash), create and run
   `setup-azure.sh` from this folder. It creates the registry, database, Key Vault, Container App,
   Microsoft sign-in for the dashboard, and a GitHub deployer identity that uses OIDC (no password).
   At the end it prints six values, none of which are secrets.
2. **Repository variables.** The IDs printed by the script (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
   and `ACR_NAME`) are written into `.github/workflows/deploy.yml`; they are identifiers, not secrets.
3. **Deploy.** Every push to `main` runs CI; when it passes, `deploy.yml` builds the image on the GitHub runner, pushes it to Azure
   Container Registry, rolls the Container App, and checks `/healthz`.

## What lives where

| Thing | Where | Notes |
|---|---|---|
| Database connection string | Key Vault secret `db-url` | read by the app's managed identity |
| Azure OpenAI access | role `Cognitive Services OpenAI User` on the app identity | no API key exists in the app |
| Dashboard sign-in | Entra ID app "Kaam Ka AI dashboard" | single tenant, assignment required, only the owner assigned |
| Sign-in client secret | Container App secret | expires after 1 year: re-run step 6 of the script to renew |
| GitHub → Azure | Entra app "kaamka-github-deploy", federated to `main` only | Contributor on the app and registry, Reader on the group |

## Known MVP trade-offs

- PostgreSQL allows connections from Azure services (strong random password + TLS). A private
  network adds ~₹1,500/month; revisit when revenue justifies it.
- Tables are created on start-up. Alembic migrations must be added before the first schema change
  to a database that holds real data.
- The publish job is not deployed yet; until Instagram is connected (Phase 6) approved posts simply
  stay approved.
