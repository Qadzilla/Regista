#!/usr/bin/env bash
# Deploy (or update) the Regista service on Azure Container Apps from a prebuilt image, as a person: the first
# deploy, and whenever secrets, settings or roles change. Image-only updates are done by GitHub Actions after every
# push to main (infra/ci-deploy.sh).
#
#   IMAGE=<registry>.azurecr.io/regista:<commit sha> ./infra/deploy-app.sh
#   ./infra/deploy-app.sh                       # image: $ACR_LOGIN_SERVER/regista:latest
#
# Reads .env (written by infra/provision.sh). The app gets a system-assigned identity with: AcrPull on the registry
# (it pulls its image with that identity: there is no registry password), the Foundry User role on the project, the
# Cosmos DB data-contributor role, and the Search roles. The write token and the tracing connection string are
# Container Apps secrets.
set -euo pipefail
. "$(dirname "$0")/lib/dotenv.sh"
. "$(dirname "$0")/lib/aca.sh"
load_dotenv .env   # parsed, never executed: values may contain ';'
# Deploy into the subscription provision.sh wrote .env for, never the CLI's current default.
if [[ -n "${REGISTA_SUBSCRIPTION_ID:-}" ]]; then
  az account set --subscription "$REGISTA_SUBSCRIPTION_ID" || { echo "cannot use subscription $REGISTA_SUBSCRIPTION_ID from .env" >&2; exit 1; }
fi

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
PLACEHOLDER="mcr.microsoft.com/k8se/quickstart:latest"   # public: a new app starts on it until its identity may pull ours

log() { printf '\n\033[1;33m== %s\033[0m\n' "$*"; }

ENV_VARS=("REGISTA_CLOUD=1" "FOUNDRY_PROJECT_ENDPOINT=${FOUNDRY_PROJECT_ENDPOINT:-}" "FOUNDRY_MODEL=${FOUNDRY_MODEL:-}"
          "REGISTA_COSMOS_ENDPOINT=${REGISTA_COSMOS_ENDPOINT:-}" "REGISTA_COSMOS_DATABASE=${REGISTA_COSMOS_DATABASE:-regista}"
          "REGISTA_SEARCH_ENDPOINT=${REGISTA_SEARCH_ENDPOINT:-}")
# Writes (uploads, verdicts, reviews, retraining) on the public URL need the admin key; it also opens the Studio. The app
# fails closed without it (REGISTA_CLOUD=1, no key: Studio closed, writes off), but a deploy that silently drops the key
# is still a mistake, so refuse it.
if [[ -z "${REGISTA_ADMIN_TOKEN:-}" ]]; then
  echo "REGISTA_ADMIN_TOKEN is not set in .env: refusing to deploy without the admin key (infra/provision.sh writes one)" >&2
  exit 1
fi
SECRETS=("admin-token=$REGISTA_ADMIN_TOKEN")
ENV_VARS+=("REGISTA_ADMIN_TOKEN=secretref:admin-token")
if [[ -n "${REGISTA_STUDIO_VIEW_TOKEN:-}" ]]; then
  # The Studio view key: the whole Studio, read-only (for judges, and for Claude reading the live Studio).
  SECRETS+=("studio-view-token=$REGISTA_STUDIO_VIEW_TOKEN")
  ENV_VARS+=("REGISTA_STUDIO_VIEW_TOKEN=secretref:studio-view-token")
else
  echo "warning: REGISTA_STUDIO_VIEW_TOKEN is not set in .env: the Studio opens only with the admin key (no key for judges)" >&2
fi
if [[ -n "${APPLICATIONINSIGHTS_CONNECTION_STRING:-}" ]]; then
  # The tracing connection string goes in as a Container Apps secret, referenced by the env var.
  SECRETS+=("appi-connection=$APPLICATIONINSIGHTS_CONNECTION_STRING")
  ENV_VARS+=("APPLICATIONINSIGHTS_CONNECTION_STRING=secretref:appi-connection")
fi

CREATED=""
if ! az containerapp show -n "$ACA_APP" -g "$RG" -o none 2>/dev/null; then
  CREATED=1
  log "Creating $ACA_APP on a public placeholder image, with its own identity"
  az containerapp create -n "$ACA_APP" -g "$RG" --environment "$ACA_ENV" --image "$PLACEHOLDER" --system-assigned \
    --ingress external --target-port 8000 --cpu 1.0 --memory 2.0Gi --min-replicas 1 --max-replicas 1 -o none
fi

log "Managed identity and roles"
APP_OID=$(az containerapp identity assign -n "$ACA_APP" -g "$RG" --system-assigned --query principalId -o tsv)
ACR_ID=$(az acr show -n "$ACR_NAME" --query id -o tsv)
az role assignment create --role AcrPull --assignee-object-id "$APP_OID" --assignee-principal-type ServicePrincipal --scope "$ACR_ID" -o none 2>/dev/null || true
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

if [[ -n "$CREATED" ]]; then
  log "Waiting a minute for the new identity's roles to take effect (role assignments are not instant)"
  sleep 60
fi

log "Updating $ACA_APP to $IMAGE (pulled with the app's identity), with its settings and secrets"
az containerapp registry set -n "$ACA_APP" -g "$RG" --server "$ACR_LOGIN_SERVER" --identity system -o none
az containerapp secret set -n "$ACA_APP" -g "$RG" --secrets "${SECRETS[@]}" -o none
# One replica: uploaded matches and paused reviews live on the replica's disk.
az containerapp update -n "$ACA_APP" -g "$RG" --image "$IMAGE" --set-env-vars "${ENV_VARS[@]}" --min-replicas 1 --max-replicas 1 \
  --revision-suffix "$(revision_suffix)" -o none

log "Waiting for the new revision to pass its health checks"
wait_ready "$ACA_APP" "$RG" || exit 1

APP_URL="https://$(az containerapp show -n "$ACA_APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
grep -q '^REGISTA_APP_URL=' .env 2>/dev/null && sed -i '' "s#^REGISTA_APP_URL=.*#REGISTA_APP_URL=$APP_URL#" .env || echo "REGISTA_APP_URL=$APP_URL" >> .env
log "Done: $APP_URL   (health: $APP_URL/api/health)"
