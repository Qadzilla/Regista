#!/usr/bin/env bash
# Deploy (or update) the Regista service on Azure Container Apps from a prebuilt image.
#
#   ./infra/deploy-app.sh                       # image: $ACR_LOGIN_SERVER/regista:latest (built by GitHub Actions)
#   IMAGE=myregistry.azurecr.io/regista:abc123 ./infra/deploy-app.sh
#
# Reads FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL, REGISTA_COSMOS_ENDPOINT, REGISTA_COSMOS_DATABASE and
# ACR_LOGIN_SERVER from .env (written by infra/provision.sh). Gives the app a system-assigned identity
# with the Foundry User role on the project and the Cosmos DB data-contributor role, so no keys are
# stored in the container.
set -euo pipefail
set -a; [[ -f .env ]] && source .env; set +a

: "${RG:=${REGISTA_RESOURCE_GROUP:-regista-rg}}"
: "${ACA_ENV:=regista-env}"
: "${ACA_APP:=regista-api}"
: "${ACR_LOGIN_SERVER:?set ACR_LOGIN_SERVER (in .env)}"
: "${IMAGE:=$ACR_LOGIN_SERVER/regista:latest}"
: "${FOUNDRY:=}"
: "${PROJECT:=regista}"
: "${COSMOS:=}"
FOUNDRY_USER_ROLE="53ca6127-db72-4b80-b1b0-d745d6d5456d"
COSMOS_DATA_CONTRIBUTOR="00000000-0000-0000-0000-000000000002"
ACR_NAME="${ACR_LOGIN_SERVER%%.*}"

log() { printf '\n\033[1;33m== %s\033[0m\n' "$*"; }

ENV_VARS=("REGISTA_CLOUD=1" "FOUNDRY_PROJECT_ENDPOINT=${FOUNDRY_PROJECT_ENDPOINT:-}" "FOUNDRY_MODEL=${FOUNDRY_MODEL:-}"
          "REGISTA_COSMOS_ENDPOINT=${REGISTA_COSMOS_ENDPOINT:-}" "REGISTA_COSMOS_DATABASE=${REGISTA_COSMOS_DATABASE:-regista}"
          "REGISTA_SEARCH_ENDPOINT=${REGISTA_SEARCH_ENDPOINT:-}")
SECRETS=()
if [[ -n "${REGISTA_ADMIN_TOKEN:-}" ]]; then
  # Writes (uploads, verdicts, reviews, retraining) on the public URL need this token; reads stay open.
  SECRETS+=("admin-token=$REGISTA_ADMIN_TOKEN")
  ENV_VARS+=("REGISTA_ADMIN_TOKEN=secretref:admin-token")
fi
if [[ -n "${APPLICATIONINSIGHTS_CONNECTION_STRING:-}" ]]; then
  # The tracing connection string goes in as a Container Apps secret, referenced by the env var.
  SECRETS+=("appi-connection=$APPLICATIONINSIGHTS_CONNECTION_STRING")
  ENV_VARS+=("APPLICATIONINSIGHTS_CONNECTION_STRING=secretref:appi-connection")
fi

log "Registry credentials for $ACR_NAME"
ACR_USER=$(az acr credential show -n "$ACR_NAME" --query username -o tsv)
ACR_PASS=$(az acr credential show -n "$ACR_NAME" --query "passwords[0].value" -o tsv)

if az containerapp show -n "$ACA_APP" -g "$RG" -o none 2>/dev/null; then
  log "Updating $ACA_APP to $IMAGE"
  az containerapp registry set -n "$ACA_APP" -g "$RG" --server "$ACR_LOGIN_SERVER" --username "$ACR_USER" --password "$ACR_PASS" -o none
  [[ ${#SECRETS[@]} -gt 0 ]] && az containerapp secret set -n "$ACA_APP" -g "$RG" --secrets "${SECRETS[@]}" -o none
  # One replica: uploaded matches and paused reviews live on the replica's disk.
  az containerapp update -n "$ACA_APP" -g "$RG" --image "$IMAGE" --set-env-vars "${ENV_VARS[@]}" --min-replicas 1 --max-replicas 1 -o none
else
  log "Creating $ACA_APP from $IMAGE"
  az containerapp create -n "$ACA_APP" -g "$RG" --environment "$ACA_ENV" --image "$IMAGE" \
    --registry-server "$ACR_LOGIN_SERVER" --registry-username "$ACR_USER" --registry-password "$ACR_PASS" \
    --ingress external --target-port 8000 --cpu 1.0 --memory 2.0Gi --min-replicas 1 --max-replicas 1 \
    ${SECRETS[@]:+--secrets "${SECRETS[@]}"} --env-vars "${ENV_VARS[@]}" -o none
fi

log "Managed identity and roles"
APP_OID=$(az containerapp identity assign -n "$ACA_APP" -g "$RG" --system-assigned --query principalId -o tsv)
if [[ -n "${FOUNDRY_PROJECT_ENDPOINT:-}" ]]; then
  FOUNDRY_NAME=$(echo "$FOUNDRY_PROJECT_ENDPOINT" | sed -E 's#https://([^.]+)\..*#\1#')
  PROJECT_ID=$(az cognitiveservices account project show -n "$FOUNDRY_NAME" -g "$RG" --project-name "$PROJECT" --query id -o tsv)
  az role assignment create --role "$FOUNDRY_USER_ROLE" --assignee-object-id "$APP_OID" --assignee-principal-type ServicePrincipal --scope "$PROJECT_ID" -o none 2>/dev/null || true
fi
if [[ -n "${REGISTA_SEARCH_ENDPOINT:-}" ]]; then
  SEARCH_NAME=$(echo "$REGISTA_SEARCH_ENDPOINT" | sed -E 's#https://([^.]+)\..*#\1#')
  SEARCH_ID=$(az search service show -n "$SEARCH_NAME" -g "$RG" --query id -o tsv)
  for role in "7ca78c08-252a-4471-8644-bb5ff32d4ba0" "8ebe5a00-799e-43f5-93ac-243d3dce84a7"; do
    az role assignment create --role "$role" --assignee-object-id "$APP_OID" --assignee-principal-type ServicePrincipal --scope "$SEARCH_ID" -o none 2>/dev/null || true
  done
fi
if [[ -n "${REGISTA_COSMOS_ENDPOINT:-}" ]]; then
  COSMOS_NAME=$(echo "$REGISTA_COSMOS_ENDPOINT" | sed -E 's#https://([^.]+)\..*#\1#')
  # The Cosmos data-plane API accepts duplicate assignments, so only create one when none exists.
  HAS_COSMOS_ROLE=$(az cosmosdb sql role assignment list -a "$COSMOS_NAME" -g "$RG" \
    --query "[?principalId=='$APP_OID' && ends_with(roleDefinitionId, '$COSMOS_DATA_CONTRIBUTOR')] | length(@)" -o tsv 2>/dev/null || echo 0)
  if [[ "${HAS_COSMOS_ROLE:-0}" == "0" ]]; then
    az cosmosdb sql role assignment create -a "$COSMOS_NAME" -g "$RG" --scope "/" --principal-id "$APP_OID" --role-definition-id "$COSMOS_DATA_CONTRIBUTOR" -o none 2>/dev/null || true
  fi
fi

log "Waiting for the new revision to pass its health checks"
LATEST=$(az containerapp show -n "$ACA_APP" -g "$RG" --query properties.latestRevisionName -o tsv)
for i in $(seq 1 60); do
  READY=$(az containerapp show -n "$ACA_APP" -g "$RG" --query properties.latestReadyRevisionName -o tsv)
  STATE=$(az containerapp revision show -n "$ACA_APP" -g "$RG" --revision "$LATEST" --query properties.runningState -o tsv 2>/dev/null)
  [[ "$READY" == "$LATEST" ]] && { echo "revision $LATEST is ready"; break; }
  if [[ "$STATE" == "Failed" || "$STATE" == "Degraded" || ( $i -eq 60 ) ]]; then
    echo "revision $LATEST did not become ready (state: $STATE); traffic stays on $READY. Recent logs:" >&2
    az containerapp logs show -n "$ACA_APP" -g "$RG" --revision "$LATEST" --tail 30 --format text 2>/dev/null | tail -30 >&2
    exit 1
  fi
  sleep 10
done

APP_URL="https://$(az containerapp show -n "$ACA_APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
grep -q '^REGISTA_APP_URL=' .env 2>/dev/null && sed -i '' "s#^REGISTA_APP_URL=.*#REGISTA_APP_URL=$APP_URL#" .env || echo "REGISTA_APP_URL=$APP_URL" >> .env
log "Done: $APP_URL   (health: $APP_URL/api/health)"
