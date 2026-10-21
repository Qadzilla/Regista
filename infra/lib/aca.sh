# Shared by infra/deploy-app.sh (a person, first deploy and secret changes) and infra/ci-deploy.sh (GitHub Actions).
#
#   . infra/lib/aca.sh && wait_ready "$ACA_APP" "$RG"
#
# A deploy is done only when the newest revision is the latest *ready* one: traffic weight alone is not proof (an old
# revision keeps serving while a broken new one fails). Prints the failing revision's logs and returns 1 otherwise.
wait_ready() {
  local app="$1" rg="$2" latest ready state i
  latest=$(az containerapp show -n "$app" -g "$rg" --query properties.latestRevisionName -o tsv)
  for i in $(seq 1 60); do
    ready=$(az containerapp show -n "$app" -g "$rg" --query properties.latestReadyRevisionName -o tsv)
    state=$(az containerapp revision show -n "$app" -g "$rg" --revision "$latest" --query properties.runningState -o tsv 2>/dev/null)
    if [[ "$ready" == "$latest" ]]; then
      echo "revision $latest is ready"
      return 0
    fi
    if [[ "$state" == "Failed" || "$state" == "Degraded" || $i -eq 60 ]]; then
      echo "revision $latest did not become ready (state: $state); traffic stays on $ready. Recent logs:" >&2
      az containerapp logs show -n "$app" -g "$rg" --revision "$latest" --tail 30 --format text 2>/dev/null | tail -30 >&2
      return 1
    fi
    sleep 10
  done
}

# A fresh revision for every deploy: secrets are read when a revision starts, so a secret change on an otherwise
# unchanged template would leave the running revision on the old value.
revision_suffix() { echo "d$(date -u +%m%d%H%M%S)"; }
