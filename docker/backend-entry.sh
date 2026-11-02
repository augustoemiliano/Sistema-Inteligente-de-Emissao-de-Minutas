#!/usr/bin/env bash
set -euo pipefail

cd /app
alembic upgrade head

# Dados de demonstração (usuários admin/editor/viewer + template). Só para dev/demo.
if [[ "${SEED_DEMO_DATA:-false}" == "true" ]]; then
  python -m app.scripts.seed
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
