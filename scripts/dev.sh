#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$root"
uv run --directory backend uvicorn younique.main_api:app --reload --host 127.0.0.1 --port 8000 &
api=$!
uv run --directory backend uvicorn younique.main_worker:app --reload --host 127.0.0.1 --port 8001 &
worker=$!
pnpm --filter @younique/web dev &
web=$!
trap 'kill $api $worker $web' INT TERM EXIT
wait
