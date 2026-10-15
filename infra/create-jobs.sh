#!/usr/bin/env bash
# Phase 7: scheduled Container Apps Jobs that run the same image as the web app.
#   kaamka-job-publish   every 15 min   python -m app.jobs publish        (approved posts whose time has come)
#   kaamka-job-metrics   every 6 h      python -m app.jobs sync-metrics   (views, reach, saves, followers)
#   kaamka-job-token     daily 03:10    python -m app.jobs refresh-token  (renews Instagram access)
# Re-runnable. Copies the app's KA_* settings and Key Vault secret references, so no secret is typed here.
set -euo pipefail
RG=kaamka-rg; APP=kaamka-app; ENV=kaamka-env; ID=kaamka-jobs-id
SUB=$(az account show --query id -o tsv)

# One identity for all jobs: pull the image and read the Key Vault secrets.
az identity create -g $RG -n $ID -o none
ID_RES=$(az identity show -g $RG -n $ID --query id -o tsv)
ID_PRN=$(az identity show -g $RG -n $ID --query principalId -o tsv)
ACR_ID=$(az acr list -g $RG --query "[0].id" -o tsv)
KV_ID=$(az keyvault list -g $RG --query "[0].id" -o tsv)
az role assignment create --assignee-object-id $ID_PRN --assignee-principal-type ServicePrincipal --role AcrPull --scope $ACR_ID -o none 2>/dev/null || true
az role assignment create --assignee-object-id $ID_PRN --assignee-principal-type ServicePrincipal --role "Key Vault Secrets User" --scope $KV_ID -o none 2>/dev/null || true

az containerapp show -n $APP -g $RG -o json > /tmp/app.json
make_yaml() {  # $1 = job name, $2 = cron, $3 = job argument
python3 - "$1" "$2" "$3" "$ID_RES" <<'PY'
import json, sys
name, cron, arg, ident = sys.argv[1:5]
app = json.load(open("/tmp/app.json"))
props, tmpl = app["properties"], app["properties"]["template"]
c = tmpl["containers"][0]
env = [e for e in c.get("env", []) if e["name"].startswith("KA_")]
used = {e["secretRef"] for e in env if "secretRef" in e}
secrets = [{"name": s["name"], "keyVaultUrl": s["keyVaultUrl"], "identity": ident}
           for s in props["configuration"].get("secrets", []) if s["name"] in used and s.get("keyVaultUrl")]
server = props["configuration"]["registries"][0]["server"]
doc = {
  "location": app["location"],
  "identity": {"type": "UserAssigned", "userAssignedIdentities": {ident: {}}},
  "properties": {
    "environmentId": props["environmentId"],
    "configuration": {
      "triggerType": "Schedule", "replicaTimeout": 1800, "replicaRetryLimit": 0,
      "scheduleTriggerConfig": {"cronExpression": cron, "parallelism": 1, "replicaCompletionCount": 1},
      "secrets": secrets, "registries": [{"server": server, "identity": ident}]},
    "template": {"containers": [{"name": name, "image": c["image"], "command": ["python", "-m", "app.jobs", arg],
                                 "env": env, "resources": {"cpu": 0.5, "memory": "1Gi"}}]}}}
json.dump(doc, open(f"/tmp/{name}.json", "w"))
print(f"{name}: {len(env)} settings, {len(secrets)} Key Vault refs, image {c['image'].split(':')[-1][:12]}")
PY
}
GH_SP=$(az ad sp list --display-name kaamka-github-deploy --query "[0].id" -o tsv 2>/dev/null || true)
for spec in "kaamka-job-publish|*/15 * * * *|publish" "kaamka-job-metrics|20 */6 * * *|sync-metrics" "kaamka-job-token|10 3 * * *|refresh-token"; do
  IFS='|' read -r NAME CRON ARG <<< "$spec"
  make_yaml "$NAME" "$CRON" "$ARG"
  az rest --method put --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.App/jobs/$NAME?api-version=2024-03-01" \
    --body @/tmp/$NAME.json -o none
  # Let GitHub's deploy identity roll the jobs to each new image.
  [ -n "$GH_SP" ] && az role assignment create --assignee-object-id $GH_SP --assignee-principal-type ServicePrincipal --role Contributor \
    --scope "/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.App/jobs/$NAME" -o none 2>/dev/null || true
done
rm -f /tmp/app.json /tmp/kaamka-job-*.json
az containerapp job list -g $RG --query "[].{job:name,schedule:properties.configuration.scheduleTriggerConfig.cronExpression,state:properties.provisioningState}" -o table
echo JOBS-OK
