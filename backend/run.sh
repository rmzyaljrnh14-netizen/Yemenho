#!/usr/bin/env bash
# Start the backend (v0.1): migrations, demo seed, then the API server.
set -euo pipefail

cd "$(dirname "$0")"
VENV="../.venv"
PY="$VENV/bin/python"

if [ ! -x "$PY" ]; then
  echo "Virtualenv not found at $VENV. Create it and install requirements first:"
  echo "  python3 -m venv .venv && ./.venv/bin/pip install -r backend/requirements.txt"
  exit 1
fi

echo "== applying migrations =="
"$PY" -m app.db.migrate

echo "== seeding demo data (idempotent) =="
"$PY" -m app.db.seed_demo

echo "== starting API on http://127.0.0.1:8000 =="
exec "$VENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000
