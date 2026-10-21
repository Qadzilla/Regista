#!/usr/bin/env bash
# Put the library matches back on a new deployment: regenerate them from their seeds (the generator is
# deterministic, so they are the same matches) and upload each through the live app's token-protected workflow, so
# Foundry labels them, Cosmos DB stores them and Azure AI Search indexes them. Run once, after the first deploy.
#
#   ./infra/restore-library.sh                 # seeds 141 and 142, as on the first deployment
#   SEEDS="141 142 143" ./infra/restore-library.sh
#
# Reads REGISTA_APP_URL and REGISTA_ADMIN_TOKEN from .env; the token is sent as a header and never printed.
set -euo pipefail
. "$(dirname "$0")/lib/dotenv.sh"
load_dotenv .env
: "${REGISTA_APP_URL:?set REGISTA_APP_URL (deploy-app.sh writes it to .env)}"
: "${REGISTA_ADMIN_TOKEN:?set REGISTA_ADMIN_TOKEN (provision.sh writes it to .env)}"
: "${SEEDS:=141 142}"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

for seed in $SEEDS; do
  id=$(printf "syn_%04d" "$seed")
  if curl -fsS -m 30 "$REGISTA_APP_URL/api/matches/$id" -o /dev/null 2>/dev/null; then
    echo "$id is already there; skipped"
    continue
  fi
  python3 -m regista.synth --seed "$seed" --minutes 3 --track-hz 1 --out "$WORK" > /dev/null
  echo "uploading $id (Foundry labels it; Cosmos DB and AI Search store it; takes a minute)"
  curl -fsS -m 600 -X POST "$REGISTA_APP_URL/api/matches?player=t_home_09" \
    -H "X-Regista-Token: $REGISTA_ADMIN_TOKEN" \
    -F "events=@$WORK/$id/events.jsonl" -F "tracks=@$WORK/$id/tracks.jsonl" \
    | python3 -c "import json, sys; d = json.load(sys.stdin); print(' ', d['match_id'], 'ok' if d['pipeline_ok'] else 'FAILED', '| labels:', d['label_models'], '| cosmos:', d['cosmos'], '| search:', d['search_index'])"
done
