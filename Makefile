.PHONY: install lint format test test-unit test-integration test-e2e test-benchmark test-slow migrate docker-up docker-down clean backup restore test-backup-restore

install:
	uv sync --all-packages
	cd frontend && npm install

lint:
	uv run ruff check core_engine/ ai_engine/ api/ cli/
	uv run --package ironlayer-core mypy core_engine/
	uv run --package ai-engine mypy ai_engine/
	uv run --package ironlayer-api mypy api/
	uv run --package ironlayer mypy cli/

format:
	uv run ruff format core_engine/ ai_engine/ api/ cli/
	uv run ruff check --fix core_engine/ ai_engine/ api/ cli/

test: test-unit test-integration

test-unit:
	uv run --package ironlayer-core pytest core_engine/tests/unit/ -v --cov=core_engine --cov-report=term-missing --cov-fail-under=70
	uv run --package ai-engine pytest ai_engine/tests/ -v --cov=ai_engine --cov-report=term-missing
	uv run --package ironlayer-api pytest api/tests/ -v --cov=api --cov-report=term-missing
	uv run --package ironlayer pytest cli/tests/ -v --cov=cli --cov-report=term-missing

test-integration:
	uv run --package ironlayer-core pytest core_engine/tests/integration/ -v

test-e2e:
	uv run --package ironlayer-core pytest core_engine/tests/e2e/ -v

migrate:
	uv run --package ironlayer-core alembic -c core_engine/state/migrations/alembic.ini upgrade head

migrate-create:
	uv run --package ironlayer-core alembic -c core_engine/state/migrations/alembic.ini revision --autogenerate -m "$(msg)"

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-build:
	docker compose build

backup:
	bash infra/scripts/backup.sh

restore:
	bash infra/scripts/restore.sh $(BACKUP_FILE)

test-backup-restore:
	bash infra/scripts/test_backup_restore.sh

test-benchmark:
	uv run --package ironlayer-core pytest core_engine/tests/benchmark/ -v -m benchmark

test-slow:
	uv run --package ai-engine pytest ai_engine/tests/ -v -m slow

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
