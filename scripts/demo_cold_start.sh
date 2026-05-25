#!/usr/bin/env bash
#
# Cold-start the CodebaseOS demo (`make demo-cold`).
#
# Kills stale ports, starts the backend + dashboard, ingests the demo repos,
# and verifies the Merkle chain. Logs go to /tmp/cbos-*.log.
#
# Requires a .env with HYDRADB_API_KEY + GITHUB_TOKEN (+ OPENAI_API_KEY for the
# /why family). For a no-credential dashboard demo, run with:
#
#     CBOS_OFFLINE_DEMO=1 make demo-cold
#
# which skips ingestion and serves the bundled fixture instead.

set -euo pipefail
cd "$(dirname "$0")/.."

BACKEND_LOG=/tmp/cbos-backend.log
DASH_LOG=/tmp/cbos-dash.log
DEMO_REPOS=${DEMO_REPOS:-"tokio-rs/tokio tokio-rs/bytes"}

echo "▸ Clearing stale ports 8000, 3000…"
lsof -ti:8000,3000 2>/dev/null | xargs kill -9 2>/dev/null || true

echo "▸ Starting backend (uvicorn) → $BACKEND_LOG"
uvicorn backend.api:app --host 0.0.0.0 --port 8000 >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

echo "▸ Waiting for backend /status…"
for _ in $(seq 1 40); do
  if curl -sf http://localhost:8000/status >/dev/null 2>&1; then
    echo "  backend up (pid $BACKEND_PID)"
    break
  fi
  sleep 0.5
done

echo "▸ Starting dashboard (next dev) → $DASH_LOG"
( cd dashboard && npm run dev >"$DASH_LOG" 2>&1 & )

if [ "${CBOS_OFFLINE_DEMO:-0}" = "1" ]; then
  echo "▸ CBOS_OFFLINE_DEMO=1 → serving bundled fixture, skipping ingestion."
else
  echo "▸ Ingesting demo repos: $DEMO_REPOS"
  FIRST=1
  for repo in $DEMO_REPOS; do
    if [ "$FIRST" = "1" ]; then
      cbos ingest "$repo" --limit 10 --prs 5 --issues 5 || echo "  (ingest $repo failed — check creds)"
      FIRST=0
    else
      cbos ingest "$repo" --limit 8 --prs 3 || echo "  (ingest $repo failed — check creds)"
    fi
  done
  echo "▸ Verifying Merkle chain…"
  cbos verify || true
fi

echo ""
echo "✓ Demo up:"
echo "    Dashboard → http://localhost:3000"
echo "    Backend   → http://localhost:8000   (logs: $BACKEND_LOG)"
echo "    Chaos     → make break"
