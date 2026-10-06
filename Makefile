.PHONY: setup dev test lint types migrate revision openapi seed validate-connectors new-connector test-authz

UV := uv run --directory backend
PNPM := pnpm

setup:
	$(PNPM) install
	uv sync --all-groups --directory backend
	uv sync --directory connectors/_sdk
	@test -f .env || cp .env.example .env
	uv run --directory backend python -m younique.scripts.ensure_dev_key

dev:
	docker compose up -d --wait
	$(UV) alembic upgrade head
	$(UV) python -m younique.scripts.seed
	./scripts/dev.sh

test:
	$(UV) pytest
	$(PNPM) --filter @younique/web test --if-present
	$(PNPM) --filter @younique/api-client test --if-present

test-authz:
	$(UV) pytest tests/authz

lint:
	$(UV) ruff check src tests
	$(UV) ruff format --check src tests
	$(PNPM) exec prettier --check "apps/**/*.{ts,tsx,css,json}" "packages/**/*.{ts,tsx,json}" "docs/site/**/*.mdx" || true
	$(PNPM) --filter @younique/web lint
	python3 scripts/check_forbidden_imports.py
	python3 scripts/check_money.py
	python3 scripts/check_routes.py

types:
	$(UV) mypy src
	$(PNPM) --filter @younique/web typecheck

migrate:
	$(UV) alembic upgrade head

revision:
	$(UV) alembic revision --autogenerate -m "$(m)"

openapi:
	$(UV) python -m younique.scripts.export_openapi
	python3 scripts/generate_api_client.py

seed:
	$(UV) python -m younique.scripts.seed

validate-connectors:
	$(UV) python -m younique.scripts.validate_connectors

new-connector:
	python3 scripts/new_connector.py $(name)
