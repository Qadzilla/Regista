#!/usr/bin/env bash
# The Player view's vision worker as an event-driven Azure Container Apps Job: one execution per message on the Storage
# queue vision-jobs (KEDA azure-queue scaler), each running `python -m regista.player.worker --once` from the app's
# image. Keyless: the job's system-assigned identity pulls the image (AcrPull), reads the queue for the scaler and the
# worker, and reads and writes Blob storage (uploads, matches, models). Re-run after changing settings; GitHub Actions
# keeps its image in step with the app's (infra/ci-deploy.sh).
#
#   ./infra/deploy-job.sh                          # image: $ACR_LOGIN_SERVER/regista:latest
#   IMAGE=<registry>.azurecr.io/regista:<sha> ./infra/deploy-job.sh
set -euo pipefail
. "$(dirname "$0")/lib/dotenv.sh"
load_dotenv .env   # parsed, never executed
if [[ -n "${REGISTA_SUBSCRIPTION_ID:-}" ]]; then
  az account set --subscription "$REGISTA_SUBSCRIPTION_ID" || { echo "cannot use subscription $REGISTA_SUBSCRIPTION_ID from .env" >&2; exit 1; }
fi

: "${RG:=${REGISTA_RESOURCE_GROUP:-regista-rg}}"
: "${ACA_ENV:=regista-env}"
: "${JOB:=regista-vision}"
: "${ACR_LOGIN_SERVER:?set ACR_LOGIN_SERVER (in .env)}"
: "${REGISTA_STORAGE_ACCOUNT:?set REGISTA_STORAGE_ACCOUNT (provision.sh writes it to .env)}"
: "${IMAGE:=$ACR_LOGIN_SERVER/regista:latest}"
: "${CPU:=2.0}"
: "${MEMORY:=4.0Gi}"
ACR_NAME="${ACR_LOGIN_SERVER%%.*}"
PLACEHOLDER="mcr.microsoft.com/k8se/quickstart-jobs:latest"   # public: the job starts on it until its identity may pull ours

log() { printf '\n\033[1;33m== %s\033[0m\n' "$*"; }

CREATED=""
if ! az containerapp job show -n "$JOB" -g "$RG" -o none 2>/dev/null; then
  CREATED=1
  log "Creating $JOB: one execution per message on $REGISTA_STORAGE_ACCOUNT/vision-jobs"
  az containerapp job create -n "$JOB" -g "$RG" --environment "$ACA_ENV" --image "$PLACEHOLDER" --mi-system-assigned \
    --trigger-type Event --replica-timeout 1800 --replica-retry-limit 0 --replica-completion-count 1 --parallelism 1 \
    --min-executions 0 --max-executions 3 --polling-interval 15 --cpu "$CPU" --memory "$MEMORY" \
    --scale-rule-name vision-queue --scale-rule-type azure-queue \
    --scale-rule-metadata "accountName=$REGISTA_STORAGE_ACCOUNT" "queueName=vision-jobs" "queueLength=1" \
    --scale-rule-identity system -o none
fi

log "Identity and roles"
JOB_OID=$(az containerapp job show -n "$JOB" -g "$RG" --query identity.principalId -o tsv)
ACR_ID=$(az acr show -n "$ACR_NAME" --query id -o tsv)
STORAGE_ID=$(az storage account show -n "$REGISTA_STORAGE_ACCOUNT" -g "$RG" --query id -o tsv)
az role assignment create --role AcrPull --assignee-object-id "$JOB_OID" --assignee-principal-type ServicePrincipal --scope "$ACR_ID" -o none 2>/dev/null || true
for role in "Storage Blob Data Contributor" "Storage Queue Data Contributor"; do
  az role assignment create --role "$role" --assignee-object-id "$JOB_OID" --assignee-principal-type ServicePrincipal --scope "$STORAGE_ID" -o none 2>/dev/null || true
done
if [[ -n "$CREATED" ]]; then
  log "Waiting a minute for the new identity's roles to take effect"
  sleep 60
fi

log "Pointing $JOB at $IMAGE (pulled with the job's identity) and the worker command"
az containerapp job registry set -n "$JOB" -g "$RG" --server "$ACR_LOGIN_SERVER" --identity system -o none
az containerapp job update -n "$JOB" -g "$RG" --image "$IMAGE" \
  --set-env-vars "REGISTA_STORAGE_ACCOUNT=$REGISTA_STORAGE_ACCOUNT" "REGISTA_SEASON=/app/data/season/league.json" \
                 "PYTHONUNBUFFERED=1" -o none
# The command goes in as one JSON list: `job update --args "-m" ...` reads the dashes as its own options.
az resource update --ids "$(az containerapp job show -n "$JOB" -g "$RG" --query id -o tsv)" \
  --set 'properties.template.containers[0].command=["python","-m","regista.player.worker","--once"]' -o none
az containerapp job show -n "$JOB" -g "$RG" \
  --query "{image: properties.template.containers[0].image, command: properties.template.containers[0].command, trigger: properties.configuration.triggerType, scale: properties.configuration.eventTriggerConfig.scale.rules[0].type}" -o json
log "Done. Executions: az containerapp job execution list -n $JOB -g $RG -o table"
