#!/usr/bin/env bash
# Deploy a new image to the container app from GitHub Actions, after tests, build and the in-image smoke test passed.
# Image only: settings, secrets and roles are set by a person with infra/deploy-app.sh. The workflow signs in with a
# federated identity (no stored secret) that may push images and update this resource group, nothing else.
#
#   IMAGE=<registry>.azurecr.io/regista:<sha> AZURE_RG=regista-rg ACA_APP=regista-api ./infra/ci-deploy.sh
set -euo pipefail
. "$(dirname "$0")/lib/aca.sh"
: "${IMAGE:?set IMAGE}" "${AZURE_RG:?set AZURE_RG}" "${ACA_APP:?set ACA_APP}"

if ! az containerapp show -n "$ACA_APP" -g "$AZURE_RG" -o none 2>/dev/null; then
  echo "$ACA_APP does not exist yet: create it once with IMAGE=$IMAGE ./infra/deploy-app.sh (see infra/SETUP.md). Skipping."
  exit 0
fi
echo "deploying $IMAGE to $ACA_APP"
az containerapp update -n "$ACA_APP" -g "$AZURE_RG" --image "$IMAGE" --revision-suffix "$(revision_suffix)" -o none
wait_ready "$ACA_APP" "$AZURE_RG"
URL="https://$(az containerapp show -n "$ACA_APP" -g "$AZURE_RG" --query properties.configuration.ingress.fqdn -o tsv)"
curl -fsS -m 30 "$URL/api/health" > /dev/null && echo "health OK at $URL"
