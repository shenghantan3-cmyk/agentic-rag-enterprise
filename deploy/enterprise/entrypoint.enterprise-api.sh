#!/usr/bin/env bash
set -euo pipefail

cd /app

# Optionally run Alembic migrations (recommended for Postgres deployments)
if [ "${ENTERPRISE_RUN_MIGRATIONS:-1}" != "0" ]; then
  echo "[enterprise-api] running migrations (alembic upgrade head)"
  alembic -c project/enterprise_api/alembic.ini upgrade head
else
  echo "[enterprise-api] ENTERPRISE_RUN_MIGRATIONS=0, skipping migrations"
fi

# Gunicorn (recommended for production)
: "${WEB_CONCURRENCY:=2}"

exec gunicorn \
  -c deploy/enterprise/gunicorn.conf.py \
  "project.enterprise_api.app:app"
