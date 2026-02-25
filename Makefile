.PHONY: install lint format test test-unit test-integration test-e2e test-benchmark test-slow migrate docker-up docker-down clean backup restore test-backup-restore

install:
	cd core_engine && poetry install
	cd ai_engine && poetry install
	cd api && poetry install
	cd cli && poetry install
	cd frontend && npm install

lint:
	cd core_engine && poetry run ruff check core_engine/ tests/
	cd ai_engine && poetry run ruff check ai_engine/ tests/
	cd api && poetry run ruff check api/ tests/
	cd cli && poetry run ruff check cli/ tests/
	cd core_engine && poetry run mypy core_engine/
	cd ai_engine && poetry run mypy ai_engine/
	cd api && poetry run mypy api/
	cd cli && poetry run mypy cli/

format:
	cd core_engine && poetry run black core_engine/ tests/ && poetry run isort core_engine/ tests/
	cd ai_engine && poetry run black ai_engine/ tests/ && poetry run isort ai_engine/ tests/
	cd api && poetry run black api/ tests/ && poetry run isort api/ tests/
	cd cli && poetry run black cli/ tests/ && poetry run isort cli/ tests/

test: test-unit test-integration

test-unit:
	cd core_engine && poetry run pytest tests/unit/ -v --cov=core_engine --cov-report=term-missing --cov-fail-under=70
	cd ai_engine && poetry run pytest tests/ -v --cov=ai_engine --cov-report=term-missing
	cd api && poetry run pytest tests/ -v --cov=api --cov-report=term-missing
	cd cli && poetry run pytest tests/ -v --cov=cli --cov-report=term-missing

test-integration:
	cd core_engine && poetry run pytest tests/integration/ -v

test-e2e:
	cd core_engine && poetry run pytest tests/e2e/ -v

migrate:
	cd core_engine && poetry run alembic -c core_engine/state/migrations/alembic.ini upgrade head

migrate-create:
	cd core_engine && poetry run alembic -c core_engine/state/migrations/alembic.ini revision --autogenerate -m "$(msg)"

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
	cd core_engine && poetry run pytest tests/benchmark/ -v -m benchmark

test-slow:
	cd ai_engine && poetry run pytest tests/ -v -m slow

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
