#!/usr/bin/env bash
# One command: API (8000, seeded) + edge pipeline (looping the demo clip, syncing) + web (3000).
# Usage: scripts/dev.sh [--no-edge] [--webcam] [--site edge/sites/greenlam_unit1.yaml]
set -euo pipefail
cd "$(dirname "$0")/.."

EDGE=1; SOURCE=""; SITE="edge/sites/retail_demo.yaml"; SEED_DAYS="${SEED_DAYS:-21}"
for a in "$@"; do
  case "$a" in
    --no-edge) EDGE=0 ;;
    --webcam) SOURCE="--source webcam" ;;
    --site) shift_next=1 ;;
    *) if [[ "${shift_next:-0}" == 1 ]]; then SITE="$a"; shift_next=0; fi ;;
  esac
done

[[ -f .env ]] && set -a && source .env && set +a
export DATABASE_URL="${DATABASE_URL:-sqlite:///./raqib.db}"
export CLIPS_DIR="${CLIPS_DIR:-./clips}"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8000}"

pids=()
cleanup() { echo; echo "stopping…"; for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

echo "▶ api      http://localhost:8000  (docs at /docs)"
( cd cloud && uv run --no-sync uvicorn raqib_api.main:app --port 8000 --reload ) & pids+=($!)

for _ in $(seq 1 60); do curl -sf http://localhost:8000/health >/dev/null && break; sleep 1; done
SITE_NAME=$(python3 -c "import yaml,sys;print(yaml.safe_load(open('$SITE'))['name'])" 2>/dev/null || echo raqib_demo_store)
echo "▶ seeding  $SITE_NAME with $SEED_DAYS days of labelled history"
curl -s -X POST "http://localhost:8000/admin/seed?site=$SITE_NAME&days=$SEED_DAYS&run_agent_last_hours=6" >/dev/null || true

if [[ "$EDGE" == 1 ]]; then
  echo "▶ edge     $SITE $SOURCE → syncing to the API"
  ( cd edge && uv run --no-sync raqib-edge run --site "../$SITE" $SOURCE --api http://localhost:8000 --no-verbose ) & pids+=($!)
fi

echo "▶ web      http://localhost:3000/en"
( cd web && npm run dev ) & pids+=($!)

wait
