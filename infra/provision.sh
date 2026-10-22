#!/usr/bin/env bash
# Provision every Azure resource Regista uses, in one run, and write a local .env. infra/SETUP.md is the runbook.
#
#   az login --tenant <tenant id> --use-device-code   # as an in-directory admin (user@<dir>.onmicrosoft.com), not an
#                                                     # external personal account: security defaults block those
#   SUBSCRIPTION="Azure for Students" LOCATION=francecentral BUDGET_EMAIL=you@outlook.com ./infra/provision.sh
#   SKIP_ACA=1 ./infra/provision.sh                   # Foundry, Cosmos DB and Search only (run the service locally)
#   ./infra/provision.sh --destroy                    # delete the whole resource group (after judging)
#
# What it creates (all idempotent; existing resources are reused, so re-running is safe):
#   resource group; Foundry resource + project + model deployment; Cosmos DB serverless (database + 4 containers);
#   Azure AI Search (free tier); Container Apps environment (+ its Log Analytics workspace, capped at 0.1 GB/day);
#   Application Insights on that workspace, connected to the Foundry project for tracing; Container Registry
#   (Basic, no admin user); a GitHub Actions deploy identity (federated: no password) with the repository variables
#   the workflow reads; a monthly budget with email alerts; Entra ID role assignments for you.
# Data-plane auth is Entra ID only: key login is switched off on Cosmos DB and AI Search (the code never uses keys).
#
# SUBSCRIPTION (name or id) is required: in a directory with several subscriptions, a wrong default would create
# everything in someone else's. Regions: LOCATION is used for everything unless COSMOS_LOCATION or SEARCH_LOCATION
# is set (a subscription may allow only a few regions: Azure for Students at Northeastern allows francecentral,
# germanywestcentral, canadacentral, denmarkeast, belgiumcentral).
#
# Names are suffixed with 6 characters of the subscription id so the globally unique ones do not clash.
# Costs (approximate): Foundry has no base charge (gpt-5-mini bills per token, cents per match); Cosmos DB serverless
# is pennies for this data; Search free tier is free; the registry is ~$5/month; the always-on container app is
# most of the bill (about $1-3/day). Delete everything after judging: ./infra/provision.sh --destroy
set -euo pipefail

log() { printf '\n\033[1;33m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }

[[ -n "${SUBSCRIPTION:-}" ]] || die "Set SUBSCRIPTION to the subscription's name or id (az account list -o table shows them).
It is required so a wrong default subscription never gets these resources."
az account set --subscription "$SUBSCRIPTION" || die "Cannot use subscription '$SUBSCRIPTION'. az account list -o table shows yours."
SUB_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
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
: "${COSMOS_LOCATION:=$LOCATION}"         # the first environment needed eastus2: East US had no Cosmos DB capacity
: "${COSMOS_DB:=regista}"
: "${SEARCH:=regista-search-$SUFFIX}"
: "${STORAGE:=registast$SUFFIX}"           # the Player view: uploads, results, models (Blob) and the vision-jobs queue
: "${SEARCH_LOCATION:=$LOCATION}"         # the first environment needed southcentralus: no free tier in East US
: "${ACA_ENV:=regista-env}"
: "${ACA_APP:=regista-api}"
: "${ACR_NAME:=registaacr$SUFFIX}"
: "${APPI:=regista-appi}"
: "${LOG_CAP_GB:=0.1}"
: "${BUDGET_AMOUNT:=60}"
: "${BUDGET_EMAIL:=}"
: "${DISABLE_LOCAL_AUTH:=1}"
: "${GITHUB_REPO:=}"                     # owner/name; default: the repository gh sees from here
: "${DEPLOY_IDENTITY:=regista-github-deploy}"
: "${ENV_FILE:=.env}"
: "${RG_TAGS:=}"   # tags for the resource group, "Key=value;Key=value" (some directories require them; resources inherit)
TAG_ARGS=()
[[ -z "$RG_TAGS" ]] || IFS=';' read -r -a TAG_ARGS <<<"$RG_TAGS"
NO_KEYS=$([[ "$DISABLE_LOCAL_AUTH" == "1" ]] && echo true || echo false)
FOUNDRY_USER_ROLE="53ca6127-db72-4b80-b1b0-d745d6d5456d"      # "Foundry User" (formerly Azure AI User)
COSMOS_DATA_CONTRIBUTOR="00000000-0000-0000-0000-000000000002" # Cosmos DB Built-in Data Contributor
SEARCH_ROLES=("7ca78c08-252a-4471-8644-bb5ff32d4ba0" "8ebe5a00-799e-43f5-93ac-243d3dce84a7")  # Service Contributor, Index Data Contributor

# Pass a subscription id to every command too: a sign-in elsewhere can change the CLI's default mid-run.
az() { case "$1 ${2:-}" in "ad "*|"rest "*|"account "*|"config "*|"provider "*) command az "$@" ;; *) command az "$@" --subscription "$SUB_ID" ;; esac; }

# The deploy identity is an app registration in the directory. A directory can be shared (a university's), so only
# ever look up, reuse or delete an app you own: another person's app of the same name is never touched.
my_app_id() { command az ad app list --show-mine --query "[?displayName=='$DEPLOY_IDENTITY'] | [0].appId" -o tsv 2>/dev/null || true; }

if [[ "${1:-}" == "--destroy" ]]; then
  log "Deleting resource group $RG (everything in it)"
  az group delete --name "$RG" --yes --no-wait
  APP_ID=$(my_app_id)
  [[ -z "$APP_ID" ]] || { az ad app delete --id "$APP_ID" && echo "deleted the GitHub deploy identity $DEPLOY_IDENTITY"; }
  echo "Deletion started. Remove $ENV_FILE by hand if you no longer want it."
  exit 0
fi

# A .env from another environment would carry its write token and app URL into this one (and a restore would then
# write to the old app). Reuse only a .env this script wrote for this subscription.
if [[ -f "$ENV_FILE" ]] && ! head -1 "$ENV_FILE" | grep -q "for subscription $SUB_ID"; then
  die "$ENV_FILE belongs to another environment. Move it out of the repository first (for example: mv $ENV_FILE ~/.regista-old.env)."
fi

# ---------------------------------------------------------------------------- 1. sign-in checks, before anything is created
log "Subscription $(az account show --query name -o tsv) ($SUB_ID), tenant $TENANT_ID, region $LOCATION"
ME_OID=$(az ad signed-in-user show --query id -o tsv)
ME_UPN=$(az ad signed-in-user show --query userPrincipalName -o tsv)
case "$ME_UPN" in
  *"#EXT#"*) die "Signed in as an external account ($ME_UPN). Security defaults block its command-line sign-ins (single-factor).
Sign in as an in-directory admin (name@<directory>.onmicrosoft.com) with Microsoft Authenticator; see infra/SETUP.md." ;;
esac
for scope in "https://management.azure.com/.default" "https://ai.azure.com/.default"; do
  az account get-access-token --scope "$scope" -o none 2>/dev/null || die "No token for $scope. Sign in again: az login --tenant $TENANT_ID --use-device-code"
done
echo "signed in as $ME_UPN; management and Foundry tokens OK"

log "Resource providers"
for ns in Microsoft.CognitiveServices Microsoft.DocumentDB Microsoft.Search Microsoft.App Microsoft.OperationalInsights \
          Microsoft.Insights Microsoft.ContainerRegistry Microsoft.Consumption Microsoft.Storage; do
  az provider register -n "$ns" --wait -o none
done

# ---------------------------------------------------------------------------- 2. model and quota, before anything is created
log "Model $MODEL ($MODEL_SKU) in $LOCATION: availability and quota"
if [[ -z "$MODEL_VERSION" ]]; then
  MODEL_VERSION=$(az cognitiveservices model list --location "$LOCATION" \
    --query "[?model.name=='$MODEL' && contains(join(',', model.skus[].name), '$MODEL_SKU')].model.version | [0]" -o tsv)
  [[ -n "$MODEL_VERSION" ]] || die "No $MODEL with SKU $MODEL_SKU in $LOCATION. Try LOCATION=eastus2 or swedencentral, or another MODEL."
fi
QUOTA=$(az cognitiveservices usage list --location "$LOCATION" \
  --query "[?name.value=='OpenAI.$MODEL_SKU.$MODEL'] | [0].[limit, currentValue]" -o tsv 2>/dev/null || true)
if [[ -n "$QUOTA" ]]; then
  read -r Q_LIMIT Q_USED <<<"$QUOTA"
  Q_FREE=$(python3 -c "print(int(float('$Q_LIMIT' or 0) - float('${Q_USED:-0}' or 0)))")   # 'used' is blank before first use
  echo "quota: ${Q_USED:-0} of $Q_LIMIT used; need $MODEL_CAPACITY"
  if (( Q_FREE < MODEL_CAPACITY )); then
    die "Not enough $MODEL quota in $LOCATION ($Q_FREE free, need $MODEL_CAPACITY). Request more in the Foundry portal
(Management center > Quota), try another LOCATION, or lower MODEL_CAPACITY (min 1)."
  fi
else
  echo "quota entry for $MODEL not listed; the deployment step will report a quota problem if there is one"
fi

# ---------------------------------------------------------------------------- 3. Foundry, Cosmos DB, AI Search
log "Resource group $RG"
az group create --name "$RG" --location "$LOCATION" ${TAG_ARGS[@]+--tags "${TAG_ARGS[@]}"} -o none

log "Foundry resource $FOUNDRY, project $PROJECT, deployment $MODEL $MODEL_VERSION"
if ! az cognitiveservices account show -n "$FOUNDRY" -g "$RG" -o none 2>/dev/null; then
  az cognitiveservices account create -n "$FOUNDRY" -g "$RG" --kind AIServices --sku S0 --location "$LOCATION" \
    --custom-domain "$FOUNDRY" --assign-identity --allow-project-management true -o none
fi
if ! az cognitiveservices account project show -n "$FOUNDRY" -g "$RG" --project-name "$PROJECT" -o none 2>/dev/null; then
  az cognitiveservices account project create -n "$FOUNDRY" -g "$RG" --project-name "$PROJECT" --location "$LOCATION" -o none
fi
PROJECT_ID=$(az cognitiveservices account project show -n "$FOUNDRY" -g "$RG" --project-name "$PROJECT" --query id -o tsv)
PROJECT_ENDPOINT=$(az cognitiveservices account project show -n "$FOUNDRY" -g "$RG" --project-name "$PROJECT" --query 'properties.endpoints."AI Foundry API"' -o tsv)
if ! az cognitiveservices account deployment show -n "$FOUNDRY" -g "$RG" --deployment-name "$MODEL" -o none 2>/dev/null; then
  az cognitiveservices account deployment create -n "$FOUNDRY" -g "$RG" --deployment-name "$MODEL" \
    --model-name "$MODEL" --model-version "$MODEL_VERSION" --model-format OpenAI \
    --sku-name "$MODEL_SKU" --sku-capacity "$MODEL_CAPACITY" -o none
fi
az role assignment create --role "$FOUNDRY_USER_ROLE" --assignee-object-id "$ME_OID" --assignee-principal-type User --scope "$PROJECT_ID" -o none 2>/dev/null || true

log "Cosmos DB $COSMOS (serverless) in $COSMOS_LOCATION"
if ! az cosmosdb show -n "$COSMOS" -g "$RG" -o none 2>/dev/null; then
  az cosmosdb create -n "$COSMOS" -g "$RG" --locations regionName="$COSMOS_LOCATION" --capacity-mode Serverless \
    --default-consistency-level Session --disable-local-auth "$NO_KEYS" -o none
else
  # key login off: Entra ID only (a generic update: the cosmosdb-preview extension drops --disable-local-auth from update)
  az resource update -g "$RG" -n "$COSMOS" --resource-type Microsoft.DocumentDB/databaseAccounts \
    --set properties.disableLocalAuth="$NO_KEYS" -o none
fi
COSMOS_ENDPOINT=$(az cosmosdb show -n "$COSMOS" -g "$RG" --query documentEndpoint -o tsv)
az cosmosdb sql database create -a "$COSMOS" -g "$RG" -n "$COSMOS_DB" -o none 2>/dev/null || true
for c in matches clips labels annotations; do
  az cosmosdb sql container create -a "$COSMOS" -g "$RG" -d "$COSMOS_DB" -n "$c" --partition-key-path /match_id -o none 2>/dev/null || true
done
HAS_ROLE=$(az cosmosdb sql role assignment list -a "$COSMOS" -g "$RG" \
  --query "[?principalId=='$ME_OID' && ends_with(roleDefinitionId, '$COSMOS_DATA_CONTRIBUTOR')] | length(@)" -o tsv 2>/dev/null || echo 0)
[[ "${HAS_ROLE:-0}" != "0" ]] || az cosmosdb sql role assignment create -a "$COSMOS" -g "$RG" --scope "/" --principal-id "$ME_OID" \
  --role-definition-id "$COSMOS_DATA_CONTRIBUTOR" -o none

log "Azure AI Search $SEARCH (free tier) in $SEARCH_LOCATION"
if ! az search service show -n "$SEARCH" -g "$RG" -o none 2>/dev/null; then
  if [[ "$NO_KEYS" == "true" ]]; then
    az search service create -n "$SEARCH" -g "$RG" -l "$SEARCH_LOCATION" --sku free --disable-local-auth true -o none
  else
    az search service create -n "$SEARCH" -g "$RG" -l "$SEARCH_LOCATION" --sku free \
      --auth-options aadOrApiKey --aad-auth-failure-mode http401WithBearerChallenge -o none
  fi
elif [[ "$NO_KEYS" == "true" ]]; then
  az search service update -n "$SEARCH" -g "$RG" --disable-local-auth true -o none
fi
SEARCH_ID=$(az search service show -n "$SEARCH" -g "$RG" --query id -o tsv)
for role in "${SEARCH_ROLES[@]}"; do
  az role assignment create --role "$role" --assignee-object-id "$ME_OID" --assignee-principal-type User --scope "$SEARCH_ID" -o none 2>/dev/null || true
done

# ---------------------------------------------------------------------------- 3b. storage for the Player view
log "Storage account $STORAGE: containers uploads, matches, models; queue vision-jobs (Entra ID only)"
if ! az storage account show -n "$STORAGE" -g "$RG" -o none 2>/dev/null; then
  az storage account create -n "$STORAGE" -g "$RG" -l "$LOCATION" --sku Standard_LRS --kind StorageV2 \
    --allow-shared-key-access false --allow-blob-public-access false --min-tls-version TLS1_2 -o none
fi
STORAGE_ID=$(az storage account show -n "$STORAGE" -g "$RG" --query id -o tsv)
# Data roles for you (to create the containers and push models), keyless like everything else.
for role in "Storage Blob Data Contributor" "Storage Queue Data Contributor"; do
  az role assignment create --role "$role" --assignee-object-id "$ME_OID" --assignee-principal-type User --scope "$STORAGE_ID" -o none 2>/dev/null || true
done
for c in uploads matches models; do
  for _ in 1 2 3 4 5 6; do  # a new role assignment can take a minute to apply
    az storage container create --account-name "$STORAGE" -n "$c" --auth-mode login -o none 2>/dev/null && break
    sleep 15
  done
done
for _ in 1 2 3 4 5 6; do
  az storage queue create --account-name "$STORAGE" -n vision-jobs --auth-mode login -o none 2>/dev/null && break
  sleep 15
done

# ---------------------------------------------------------------------------- 4. hosting, tracing, registry, CI identity
APPI_CONN=""
if [[ -z "${SKIP_ACA:-}" ]]; then
  az config set extension.use_dynamic_install=yes_without_prompt -o none
  log "Container Apps environment $ACA_ENV"
  if ! az containerapp env show -n "$ACA_ENV" -g "$RG" -o none 2>/dev/null; then
    # Standard (workload profiles) mode, named: newer CLI extensions default to "express" environments, which cannot
    # pull images with the app's own identity. Reuse the resource group's Log Analytics workspace if there is one
    # (Application Insights sits on it); otherwise the environment creates its own.
    WS_ARGS=()
    WS_NAME=$(az monitor log-analytics workspace list -g "$RG" --query "[0].name" -o tsv)
    if [[ -n "$WS_NAME" ]]; then
      WS_ARGS=(--logs-workspace-id "$(az monitor log-analytics workspace show -g "$RG" -n "$WS_NAME" --query customerId -o tsv)"
               --logs-workspace-key "$(az monitor log-analytics workspace get-shared-keys -g "$RG" -n "$WS_NAME" --query primarySharedKey -o tsv)")
    fi
    az containerapp env create -n "$ACA_ENV" -g "$RG" --location "$LOCATION" --environment-mode WorkloadProfiles \
      ${WS_ARGS[@]+"${WS_ARGS[@]}"} -o none
  fi

  log "Application Insights $APPI on the environment's workspace (capped at $LOG_CAP_GB GB/day), connected to Foundry"
  WS_CUSTOMER=$(az containerapp env show -n "$ACA_ENV" -g "$RG" --query properties.appLogsConfiguration.logAnalyticsConfiguration.customerId -o tsv)
  WS_ID=$(az monitor log-analytics workspace list -g "$RG" --query "[?customerId=='$WS_CUSTOMER'].id | [0]" -o tsv)
  WS_NAME=$(az monitor log-analytics workspace list -g "$RG" --query "[?customerId=='$WS_CUSTOMER'].name | [0]" -o tsv)
  [[ -n "$WS_ID" ]] || die "Could not find the Container Apps environment's Log Analytics workspace in $RG."
  az monitor log-analytics workspace update -g "$RG" -n "$WS_NAME" --quota "$LOG_CAP_GB" -o none
  if ! az monitor app-insights component show -a "$APPI" -g "$RG" -o none 2>/dev/null; then
    az monitor app-insights component create -a "$APPI" -g "$RG" -l "$LOCATION" --kind web --application-type web --workspace "$WS_ID" -o none
  fi
  APPI_ID=$(az monitor app-insights component show -a "$APPI" -g "$RG" --query id -o tsv)
  APPI_CONN=$(az monitor app-insights component show -a "$APPI" -g "$RG" --query connectionString -o tsv)
  if ! az cognitiveservices account project connection show -g "$RG" -n "$FOUNDRY" --project-name "$PROJECT" --connection-name "$APPI" -o none 2>/dev/null; then
    CONN_FILE=$(mktemp)
    trap 'rm -f "$CONN_FILE"' EXIT   # it holds the connection string
    python3 - "$APPI_ID" "$APPI_CONN" "$CONN_FILE" <<'PY'
import json, sys
app_id, conn, path = sys.argv[1:]
json.dump({"type": "app_insights", "target": app_id, "credentials": {"type": "api_key", "key": conn},
           "metadata": {"ApiType": "Azure", "ResourceId": app_id}}, open(path, "w"))
PY
    az cognitiveservices account project connection create -g "$RG" -n "$FOUNDRY" --project-name "$PROJECT" \
      --connection-name "$APPI" --file "$CONN_FILE" -o none
    rm -f "$CONN_FILE"
  fi

  log "Container Registry $ACR_NAME (Basic, no admin user: the app pulls with its own identity, CI pushes with its own)"
  if ! az acr show -n "$ACR_NAME" -g "$RG" -o none 2>/dev/null; then
    az acr create -n "$ACR_NAME" -g "$RG" --sku Basic --admin-enabled false -o none
  fi
  az acr update -n "$ACR_NAME" -g "$RG" --admin-enabled false -o none
  ACR_ID=$(az acr show -n "$ACR_NAME" -g "$RG" --query id -o tsv)
  ACR_LOGIN_SERVER=$(az acr show -n "$ACR_NAME" -g "$RG" --query loginServer -o tsv)

  if [[ -z "${SKIP_GITHUB:-}" ]]; then
    log "GitHub Actions deploy identity $DEPLOY_IDENTITY (federated credential: no secret is stored anywhere)"
    [[ -n "$GITHUB_REPO" ]] || GITHUB_REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)
    [[ -n "$GITHUB_REPO" ]] || die "Set GITHUB_REPO=owner/name (gh could not tell from here), or SKIP_GITHUB=1."
    APP_ID=$(my_app_id)
    [[ -n "$APP_ID" ]] || APP_ID=$(az ad app create --display-name "$DEPLOY_IDENTITY" --query appId -o tsv)
    SP_OID=$(az ad sp show --id "$APP_ID" --query id -o tsv 2>/dev/null || az ad sp create --id "$APP_ID" --query id -o tsv)
    # GitHub signs the workflow's token with one of two subject formats: the classic repo:owner/name:ref:..., or
    # (newer repositories) one that carries the owner and repository ids, repo:owner@<id>/name@<id>:ref:...
    # Trust both, for main only.
    IDS=$(gh api "repos/$GITHUB_REPO" --jq '"\(.owner.id) \(.id)"')
    read -r OWNER_ID REPO_ID <<<"$IDS"
    for entry in "github-main=repo:$GITHUB_REPO:ref:refs/heads/main" \
                 "github-main-ids=repo:${GITHUB_REPO%%/*}@$OWNER_ID/${GITHUB_REPO#*/}@$REPO_ID:ref:refs/heads/main"; do
      FIC_NAME=${entry%%=*}; SUBJECT=${entry#*=}
      if [[ -z "$(az ad app federated-credential list --id "$APP_ID" --query "[?subject=='$SUBJECT'].name | [0]" -o tsv)" ]]; then
        az ad app federated-credential create --id "$APP_ID" --parameters "{\"name\": \"$FIC_NAME\", \"issuer\": \"https://token.actions.githubusercontent.com\",
          \"subject\": \"$SUBJECT\", \"audiences\": [\"api://AzureADTokenExchange\"]}" -o none
      fi
    done
    # Push images, and update the container app's image. Nothing else: secrets and roles stay with deploy-app.sh.
    az role assignment create --role AcrPush --assignee-object-id "$SP_OID" --assignee-principal-type ServicePrincipal --scope "$ACR_ID" -o none 2>/dev/null || true
    az role assignment create --role Contributor --assignee-object-id "$SP_OID" --assignee-principal-type ServicePrincipal \
      --scope "$(az group show -n "$RG" --query id -o tsv)" -o none 2>/dev/null || true
    log "Repository variables for the workflow (identifiers, not secrets)"
    for kv in "AZURE_CLIENT_ID=$APP_ID" "AZURE_TENANT_ID=$TENANT_ID" "AZURE_SUBSCRIPTION_ID=$SUB_ID" "AZURE_RG=$RG" \
              "ACR_NAME=$ACR_NAME" "ACR_LOGIN_SERVER=$ACR_LOGIN_SERVER" "ACA_APP=$ACA_APP"; do
      gh variable set "${kv%%=*}" --repo "$GITHUB_REPO" --body "${kv#*=}"
    done
  fi
fi

# ---------------------------------------------------------------------------- 5. budget
if [[ -n "$BUDGET_EMAIL" ]]; then
  log "Budget regista-budget: \$$BUDGET_AMOUNT a month, emails to $BUDGET_EMAIL at 50%, 80% and 100%"
  START=$(date -u +%Y-%m-01)
  END=$(python3 -c "import datetime; print((datetime.date.today().replace(day=1) + datetime.timedelta(days=370)).replace(day=1))")
  BODY=$(python3 - "$BUDGET_AMOUNT" "$BUDGET_EMAIL" "$START" "$END" <<'PY'
import json, sys
amount, email, start, end = sys.argv[1:]
note = lambda pct: {"enabled": True, "operator": "GreaterThan", "threshold": pct, "contactEmails": [email], "thresholdType": "Actual"}
print(json.dumps({"properties": {"category": "Cost", "amount": float(amount), "timeGrain": "Monthly",
                                 "timePeriod": {"startDate": f"{start}T00:00:00Z", "endDate": f"{end}T00:00:00Z"},
                                 "notifications": {"actual50": note(50), "actual80": note(80), "actual100": note(100)}}}))
PY
)
  # Some offers (Azure for Students) do not support budgets; they stop at their credit limit instead. Warn, go on.
  az rest --method put --url "https://management.azure.com/subscriptions/$SUB_ID/providers/Microsoft.Consumption/budgets/regista-budget?api-version=2023-05-01" \
    --body "$BODY" -o none || echo "budget not created (this subscription's offer may not support budgets); continuing"
else
  log "Budget skipped: set BUDGET_EMAIL=you@example.com to get alerts at 50%, 80% and 100% of \$$BUDGET_AMOUNT a month"
fi

# ---------------------------------------------------------------------------- 6. .env
log "Writing $ENV_FILE"
# The write token and the Studio view key survive a re-run (rotating it would lock the deployed app's operator out); everything else is
# read back from Azure.
prior() { [[ -f "$ENV_FILE" ]] || return 0; sed -n "s/^$1=//p" "$ENV_FILE" | tail -1; }   # no .env yet: nothing to keep
ADMIN_TOKEN=$(prior REGISTA_ADMIN_TOKEN)
[[ -n "$ADMIN_TOKEN" ]] || ADMIN_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
VIEW_TOKEN=$(prior REGISTA_STUDIO_VIEW_TOKEN)
[[ -n "$VIEW_TOKEN" ]] || VIEW_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
APP_URL=$(prior REGISTA_APP_URL)
cat > "$ENV_FILE" <<EOF
# Generated by infra/provision.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ) for subscription $SUB_ID. Data-plane auth is Entra ID.
AZURE_TENANT_ID=$TENANT_ID
REGISTA_SUBSCRIPTION_ID=$SUB_ID
FOUNDRY_PROJECT_ENDPOINT=$PROJECT_ENDPOINT
FOUNDRY_MODEL=$MODEL
REGISTA_COSMOS_ENDPOINT=$COSMOS_ENDPOINT
REGISTA_COSMOS_DATABASE=$COSMOS_DB
REGISTA_SEARCH_ENDPOINT=https://$SEARCH.search.windows.net
REGISTA_STORAGE_ACCOUNT=$STORAGE
REGISTA_RESOURCE_GROUP=$RG
REGISTA_ADMIN_TOKEN=$ADMIN_TOKEN
REGISTA_STUDIO_VIEW_TOKEN=$VIEW_TOKEN
EOF
[[ -z "$APPI_CONN" ]] || echo "APPLICATIONINSIGHTS_CONNECTION_STRING=$APPI_CONN" >> "$ENV_FILE"
[[ -z "${ACR_LOGIN_SERVER:-}" ]] || echo "ACR_LOGIN_SERVER=$ACR_LOGIN_SERVER" >> "$ENV_FILE"
[[ -z "$APP_URL" ]] || echo "REGISTA_APP_URL=$APP_URL" >> "$ENV_FILE"

log "Done"
# Show which settings were written, never their values: the token and the connection string are secrets.
sed -E 's/^(REGISTA_ADMIN_TOKEN|REGISTA_STUDIO_VIEW_TOKEN|APPLICATIONINSIGHTS_CONNECTION_STRING)=.*/\1=<hidden>/' "$ENV_FILE"
cat <<MSG

Next: push to main (or run the workflow) so GitHub Actions builds, tests and pushes the image, then create the app once:
  IMAGE=${ACR_LOGIN_SERVER:-<registry>}/regista:<commit sha> ./infra/deploy-app.sh
After that, every push to main deploys itself. Try the cloud pipeline locally:
  python3 -m regista.agents data/synthetic/sample/syn_0294 --player t_home_09 --cloud --query "find me Castellanos doing a nutmeg"
MSG
