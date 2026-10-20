#!/usr/bin/env bash
# Provision Regista's Azure resources with the Azure CLI (>= 2.80) and write a local .env.
#
#   az login
#   ./infra/provision.sh                 # everything: Foundry + model, Cosmos DB, Container Apps
#   SKIP_ACA=1 ./infra/provision.sh      # Foundry + Cosmos only (cheapest; run the service locally)
#   COSMOS_LOCATION=eastus2 ./infra/provision.sh   # when a region reports "high demand" for Cosmos DB
#   ./infra/provision.sh --destroy       # delete the whole resource group
#
# Every step is idempotent: existing resources are reused. Names are suffixed with 6 characters of
# the subscription id so the globally unique ones (Foundry custom domain, Cosmos account) do not clash.
#
# Costs (October 2026 list prices, approximate): the Foundry resource has no base charge; the model
# deployment bills per token (gpt-5-mini: cents per million tokens; a full labelling run of one match
# is well under a cent). Cosmos DB serverless bills per request unit and GB (pennies for this data).
# Container Apps consumption has a monthly free grant; the container registry `containerapp up`
# creates is Basic (~$5/month). Delete the group when done: ./infra/provision.sh --destroy
set -euo pipefail

SUB_ID=$(az account show --query id -o tsv)
SUFFIX=$(echo "$SUB_ID" | tr -d '-' | cut -c1-6)
: "${RG:=regista-rg}"
: "${LOCATION:=eastus}"
: "${FOUNDRY:=regista-foundry-$SUFFIX}"
: "${PROJECT:=regista}"
: "${MODEL:=gpt-5-mini}"
: "${MODEL_VERSION:=}"
: "${MODEL_SKU:=GlobalStandard}"
: "${MODEL_CAPACITY:=10}"
: "${COSMOS:=regista-cosmos-$SUFFIX}"
: "${COSMOS_LOCATION:=$LOCATION}"   # Cosmos capacity varies by region; override when a region is full
: "${COSMOS_DB:=regista}"
: "${ACA_ENV:=regista-env}"
: "${ACA_APP:=regista-api}"
: "${ENV_FILE:=.env}"
FOUNDRY_USER_ROLE="53ca6127-db72-4b80-b1b0-d745d6d5456d"      # "Foundry User" (formerly Azure AI User)
COSMOS_DATA_CONTRIBUTOR="00000000-0000-0000-0000-000000000002" # Cosmos DB Built-in Data Contributor

log() { printf '\n\033[1;33m== %s\033[0m\n' "$*"; }

if [[ "${1:-}" == "--destroy" ]]; then
  log "Deleting resource group $RG (everything in it)"
  az group delete --name "$RG" --yes --no-wait
  echo "Deletion started. Remove $ENV_FILE by hand if you no longer want it."
  exit 0
fi

log "Subscription $(az account show --query name -o tsv) ($SUB_ID), region $LOCATION"
ME_OID=$(az ad signed-in-user show --query id -o tsv)
ME_UPN=$(az ad signed-in-user show --query userPrincipalName -o tsv)

log "Resource group $RG"
az group create --name "$RG" --location "$LOCATION" -o none

log "Foundry resource $FOUNDRY"
if ! az cognitiveservices account show -n "$FOUNDRY" -g "$RG" -o none 2>/dev/null; then
  az cognitiveservices account create -n "$FOUNDRY" -g "$RG" --kind AIServices --sku S0 --location "$LOCATION" \
    --custom-domain "$FOUNDRY" --assign-identity --allow-project-management true -o none
fi

log "Foundry project $PROJECT"
if ! az cognitiveservices account project show -n "$FOUNDRY" -g "$RG" --project-name "$PROJECT" -o none 2>/dev/null; then
  az cognitiveservices account project create -n "$FOUNDRY" -g "$RG" --project-name "$PROJECT" --location "$LOCATION" -o none
fi
PROJECT_ID=$(az cognitiveservices account project show -n "$FOUNDRY" -g "$RG" --project-name "$PROJECT" --query id -o tsv)
PROJECT_ENDPOINT=$(az cognitiveservices account project show -n "$FOUNDRY" -g "$RG" --project-name "$PROJECT" --query 'properties.endpoints."AI Foundry API"' -o tsv)

log "Model deployment $MODEL"
if [[ -z "$MODEL_VERSION" ]]; then
  MODEL_VERSION=$(az cognitiveservices model list --location "$LOCATION" \
    --query "[?model.name=='$MODEL' && contains(join(',', model.skus[].name), '$MODEL_SKU')].model.version | [0]" -o tsv)
  [[ -n "$MODEL_VERSION" ]] || { echo "No $MODEL version with SKU $MODEL_SKU in $LOCATION. Try another MODEL/LOCATION." >&2; exit 1; }
fi
if ! az cognitiveservices account deployment show -n "$FOUNDRY" -g "$RG" --deployment-name "$MODEL" -o none 2>/dev/null; then
  az cognitiveservices account deployment create -n "$FOUNDRY" -g "$RG" --deployment-name "$MODEL" \
    --model-name "$MODEL" --model-version "$MODEL_VERSION" --model-format OpenAI \
    --sku-name "$MODEL_SKU" --sku-capacity "$MODEL_CAPACITY" -o none
fi

log "Foundry User role for $ME_UPN on the project"
az role assignment create --role "$FOUNDRY_USER_ROLE" --assignee-object-id "$ME_OID" --assignee-principal-type User --scope "$PROJECT_ID" -o none 2>/dev/null || true

log "Cosmos DB account $COSMOS (serverless) in $COSMOS_LOCATION"
if ! az cosmosdb show -n "$COSMOS" -g "$RG" -o none 2>/dev/null; then
  az cosmosdb create -n "$COSMOS" -g "$RG" --locations regionName="$COSMOS_LOCATION" --capabilities EnableServerless \
    --default-consistency-level Session -o none
fi
COSMOS_ENDPOINT=$(az cosmosdb show -n "$COSMOS" -g "$RG" --query documentEndpoint -o tsv)
az cosmosdb sql database create -a "$COSMOS" -g "$RG" -n "$COSMOS_DB" -o none 2>/dev/null || true
for c in matches clips labels annotations; do
  az cosmosdb sql container create -a "$COSMOS" -g "$RG" -d "$COSMOS_DB" -n "$c" --partition-key-path /match_id -o none 2>/dev/null || true
done
log "Cosmos data-plane role for $ME_UPN"
az cosmosdb sql role assignment create -a "$COSMOS" -g "$RG" --scope "/" --principal-id "$ME_OID" --role-definition-id "$COSMOS_DATA_CONTRIBUTOR" -o none 2>/dev/null || true

log "Writing $ENV_FILE"
cat > "$ENV_FILE" <<EOF
# Generated by infra/provision.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ). Keyless auth: run 'az login'.
FOUNDRY_PROJECT_ENDPOINT=$PROJECT_ENDPOINT
FOUNDRY_MODEL=$MODEL
REGISTA_COSMOS_ENDPOINT=$COSMOS_ENDPOINT
REGISTA_COSMOS_DATABASE=$COSMOS_DB
REGISTA_RESOURCE_GROUP=$RG
EOF

if [[ -z "${SKIP_ACA:-}" ]]; then
  log "Container Apps environment $ACA_ENV and registry"
  az config set extension.use_dynamic_install=yes_without_prompt -o none
  if ! az containerapp env show -n "$ACA_ENV" -g "$RG" -o none 2>/dev/null; then
    az containerapp env create -n "$ACA_ENV" -g "$RG" --location "$LOCATION" -o none
  fi
  : "${ACR_NAME:=registaacr$SUFFIX}"
  if ! az acr show -n "$ACR_NAME" -g "$RG" -o none 2>/dev/null; then
    az acr create -n "$ACR_NAME" -g "$RG" --sku Basic --admin-enabled true -o none
  fi
  ACR_LOGIN_SERVER=$(az acr show -n "$ACR_NAME" -g "$RG" --query loginServer -o tsv)
  echo "ACR_LOGIN_SERVER=$ACR_LOGIN_SERVER" >> "$ENV_FILE"
  cat <<MSG

The image is built by GitHub Actions (.github/workflows/build-image.yml), because free-trial subscriptions
cannot run ACR Tasks. Set the repository secrets ACR_LOGIN_SERVER, ACR_USERNAME, ACR_PASSWORD from
  az acr credential show -n $ACR_NAME
push to main (or run the workflow), then deploy the app with:
  ./infra/deploy-app.sh
MSG
fi

log "Done"
cat "$ENV_FILE"
echo "Try: python3 -m regista.agents data/synthetic/sample/syn_0294 --player t_home_09 --cloud --query \"find me Castellanos doing a nutmeg\""
