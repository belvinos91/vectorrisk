#!/usr/bin/env bash
# Launch the VectorRisk backend.  Usage: ./run_api.sh [port]
set -e
PORT="${1:-8000}"
python -m pip install -e ".[full]" >/dev/null 2>&1 || true
echo "VectorRisk API -> http://127.0.0.1:${PORT}  (docs at /docs)"
exec vectorrisk serve --host 0.0.0.0 --port "${PORT}" --reload
