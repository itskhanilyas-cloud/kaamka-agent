#!/usr/bin/env bash
# One-time Azure setup for Kaam Ka AI. Run in Azure Cloud Shell (Bash), signed in as the owner.
# Safe to re-run: names are derived from your subscription, and existing resources are reused.
#
# Creates (Central India, except the OpenAI account which already exists in South India):
#   - Container Registry (Basic)            images built by GitHub Actions
#   - PostgreSQL Flexible Server (B1ms)     app database, 32 GB, 7-day backups
#   - Key Vault (RBAC)                      database connection string
#   - Container Apps environment + app      the dashboard/API, scales to zero
#   - Entra ID sign-in on the app           only you can open it
#   - GitHub OIDC deployer identity         lets GitHub deploy without any stored password
set -euo pipefail

LOC=centralindia
RG=kaamka-rg
OPENAI=kaamka-ai-4856
GH_REPO=itskhanilyas-cloud/kaamka-agent
APP=kaamka-app
ENVN=kaamka-env

az config set extension.use_dynamic_install=yes_without_prompt core.only_show_errors=true >/dev/null
SUB=$(az account show --query id -o tsv)
TENANT=$(az account show --query tenantId -o tsv)
S=$(echo "$SUB" | tr -d '-' | cut -c1-6)
ACR=kaamkaacr$S
DB=kaamka-db-$S
KV=kaamka-kv-$S
ME_ID=$(az ad signed-in-user show --query id -o tsv)
ME_NAME=$(az ad signed-in-user show --query "mail || userPrincipalName" -o tsv)

echo "== 1/8 Registering resource providers"
for p in Microsoft.App Microsoft.OperationalInsights Microsoft.ContainerRegistry Microsoft.DBforPostgreSQL Microsoft.KeyVault; do
  az provider register -n $p --wait >/dev/null
done

echo "== 2/8 Container Registry $ACR"
az acr show -n $ACR -g $RG >/dev/null 2>&1 || az acr create -n $ACR -g $RG -l $LOC --sku Basic -o none

echo "== 3/8 PostgreSQL $DB (takes ~5-10 minutes)"
if ! az postgres flexible-server show -n $DB -g $RG >/dev/null 2>&1; then
  PW=$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | cut -c1-32)
  az postgres flexible-server create -n $DB -g $RG -l $LOC --tier Burstable --sku-name Standard_B1ms \
    --storage-size 32 --version 16 --admin-user kaadmin --admin-password "$PW" \
    --public-access 0.0.0.0 --database-name kaamka --backup-retention 7 --yes -o none
  NEW_DB_PW=$PW
fi

echo "== 4/8 Key Vault $KV"
az keyvault show -n $KV -g $RG >/dev/null 2>&1 || az keyvault create -n $KV -g $RG -l $LOC --enable-rbac-authorization true -o none
KV_ID=$(az keyvault show -n $KV -g $RG --query id -o tsv)
az role assignment create --assignee-object-id $ME_ID --assignee-principal-type User --role "Key Vault Secrets Officer" --scope $KV_ID -o none 2>/dev/null || true
if [ -n "${NEW_DB_PW:-}" ]; then
  echo "   waiting 60s for Key Vault permission to apply..."; sleep 60
  az keyvault secret set --vault-name $KV -n db-url -o none \
    --value "postgresql+psycopg://kaadmin:${NEW_DB_PW}@${DB}.postgres.database.azure.com:5432/kaamka?sslmode=require"
  unset NEW_DB_PW
fi

echo "== 5/8 Container Apps environment and app"
az containerapp env show -n $ENVN -g $RG >/dev/null 2>&1 || az containerapp env create -n $ENVN -g $RG -l $LOC -o none
if ! az containerapp show -n $APP -g $RG >/dev/null 2>&1; then
  az containerapp create -n $APP -g $RG --environment $ENVN --image mcr.microsoft.com/k8se/quickstart:latest \
    --target-port 8000 --ingress external --min-replicas 0 --max-replicas 1 --cpu 0.5 --memory 1.0Gi \
    --system-assigned -o none
fi
APP_MI=$(az containerapp show -n $APP -g $RG --query identity.principalId -o tsv)
ACR_ID=$(az acr show -n $ACR -g $RG --query id -o tsv)
OPENAI_ID=$(az cognitiveservices account show -n $OPENAI -g $RG --query id -o tsv)
az role assignment create --assignee-object-id $APP_MI --assignee-principal-type ServicePrincipal --role AcrPull --scope $ACR_ID -o none 2>/dev/null || true
az role assignment create --assignee-object-id $APP_MI --assignee-principal-type ServicePrincipal --role "Key Vault Secrets User" --scope $KV_ID -o none 2>/dev/null || true
az role assignment create --assignee-object-id $APP_MI --assignee-principal-type ServicePrincipal --role "Cognitive Services OpenAI User" --scope $OPENAI_ID -o none 2>/dev/null || true
echo "   waiting 60s for app permissions to apply..."; sleep 60
az containerapp registry set -n $APP -g $RG --server $ACR.azurecr.io --identity system -o none
az containerapp secret set -n $APP -g $RG -o none \
  --secrets "db-url=keyvaultref:https://$KV.vault.azure.net/secrets/db-url,identityref:system"
az containerapp update -n $APP -g $RG -o none --set-env-vars \
  KA_APP_ENV=production KA_OWNER_EMAIL="$ME_NAME" KA_DATABASE_URL=secretref:db-url \
  KA_TEXT_PROVIDER=azure_openai KA_AZURE_OPENAI_ENDPOINT="https://$OPENAI.openai.azure.com/" \
  KA_AZURE_OPENAI_DEPLOYMENT=text-main KA_MONTHLY_BUDGET_INR=4000 KA_MAX_POSTS_PER_DAY=3
FQDN=$(az containerapp show -n $APP -g $RG --query properties.configuration.ingress.fqdn -o tsv)

echo "== 6/8 Sign-in with your Microsoft account (only you)"
WEB_APPID=$(az ad app list --display-name "Kaam Ka AI dashboard" --query "[0].appId" -o tsv)
if [ -z "$WEB_APPID" ]; then
  WEB_APPID=$(az ad app create --display-name "Kaam Ka AI dashboard" --sign-in-audience AzureADMyOrg \
    --web-redirect-uris "https://$FQDN/.auth/login/aad/callback" --enable-id-token-issuance true --query appId -o tsv)
  az ad sp create --id $WEB_APPID -o none
fi
WEB_SP=$(az ad sp show --id $WEB_APPID --query id -o tsv)
az ad sp update --id $WEB_APPID --set appRoleAssignmentRequired=true -o none
az rest --method POST --uri "https://graph.microsoft.com/v1.0/servicePrincipals/$WEB_SP/appRoleAssignedTo" \
  --body "{\"principalId\":\"$ME_ID\",\"resourceId\":\"$WEB_SP\",\"appRoleId\":\"00000000-0000-0000-0000-000000000000\"}" -o none 2>/dev/null || true
WEB_SECRET=$(az ad app credential reset --id $WEB_APPID --display-name easyauth --years 1 --append --query password -o tsv)
az containerapp secret set -n $APP -g $RG --secrets "microsoft-provider-authentication-secret=$WEB_SECRET" -o none
unset WEB_SECRET
az containerapp auth microsoft update -n $APP -g $RG --client-id $WEB_APPID \
  --client-secret-name microsoft-provider-authentication-secret \
  --issuer "https://login.microsoftonline.com/$TENANT/v2.0" --yes -o none
az containerapp auth update -n $APP -g $RG --unauthenticated-client-action RedirectToLoginPage \
  --redirect-provider azureactivedirectory --require-https true --excluded-paths "/healthz" -o none

echo "== 7/8 GitHub deployer (no password: GitHub OIDC)"
GH_APPID=$(az ad app list --display-name "kaamka-github-deploy" --query "[0].appId" -o tsv)
if [ -z "$GH_APPID" ]; then
  GH_APPID=$(az ad app create --display-name "kaamka-github-deploy" --query appId -o tsv)
  az ad sp create --id $GH_APPID -o none
  az ad app federated-credential create --id $GH_APPID -o none --parameters "{\"name\":\"main\",\"issuer\":\"https://token.actions.githubusercontent.com\",\"subject\":\"repo:$GH_REPO:ref:refs/heads/main\",\"audiences\":[\"api://AzureADTokenExchange\"]}"
fi
GH_SP=$(az ad sp show --id $GH_APPID --query id -o tsv)
APP_ID=$(az containerapp show -n $APP -g $RG --query id -o tsv)
az role assignment create --assignee-object-id $GH_SP --assignee-principal-type ServicePrincipal --role Contributor --scope $APP_ID -o none 2>/dev/null || true
az role assignment create --assignee-object-id $GH_SP --assignee-principal-type ServicePrincipal --role Contributor --scope $ACR_ID -o none 2>/dev/null || true
az role assignment create --assignee-object-id $GH_SP --assignee-principal-type ServicePrincipal --role Reader --scope "/subscriptions/$SUB/resourceGroups/$RG" -o none 2>/dev/null || true

echo "== 8/8 Done. Send these values to Claude (none of them are secrets):"
echo "AZURE_CLIENT_ID=$GH_APPID"
echo "AZURE_TENANT_ID=$TENANT"
echo "AZURE_SUBSCRIPTION_ID=$SUB"
echo "ACR_NAME=$ACR"
echo "APP_URL=https://$FQDN"
echo "OWNER=$ME_NAME"
