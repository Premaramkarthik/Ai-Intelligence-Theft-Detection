# ── Project Orchestration ─────────────────────────────────────────────────────

.PHONY: build up down restart logs ps lint test clean dev-install

# ── Docker ────────────────────────────────────────────────────────────────────

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

ps:
	docker compose ps

# ── Development ───────────────────────────────────────────────────────────────

lint:
	ruff check .
	mypy .

test:
	pytest tests/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +

dev-install:
	pip install -r requirements.txt
	pip install -e ./libs/shared
	pip install -e ./services/signaling
	pip install -e ./services/inference
	pip install -e ./services/mediabridge
	pip install -e ./services/alerting
	pip install -e ./services/persistence
