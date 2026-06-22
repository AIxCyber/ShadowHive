# =============================================================================
# ShadowHive — Makefile
# =============================================================================
# Common commands for development and production operations.

.DEFAULT_GOAL := help

PROFILE ?= dev
COMPOSE_FILES = -f docker-compose.yml

ifeq ($(PROFILE),prod)
	COMPOSE_FILES += -f docker-compose.prod.yml
endif

ifneq ($(findstring gpu,$(PROFILE)),)
	COMPOSE_FILES += -f docker-compose.gpu.yml
endif

# ── Help ──────────────────────────────────────────────────────────────────────

help: ## Show this help message
	@printf "\n\033[1mShadowHive — Available Commands\033[0m\n\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@printf "\n  \033[33mUsage:\033[0m\n"
	@printf "    make up              # Start with dev profile\n"
	@printf "    make PROFILE=prod up # Start with production profile\n"
	@printf "    make PROFILE=prod-gpu up  # Start with production + GPU\n\n"

# ── Lifecycle ─────────────────────────────────────────────────────────────────

up: ## Start all services (use PROFILE=prod for production)
	docker compose $(COMPOSE_FILES) up -d --build
	@printf "\n  \033[32m✔ Services started\033[0m\n"
	@printf "    Frontend: http://localhost:3000\n"
	@printf "    API:      http://localhost:8000\n"
	@printf "    Neo4j:    http://localhost:7474\n\n"

down: ## Stop all services
	docker compose $(COMPOSE_FILES) down

restart: ## Restart all services
	docker compose $(COMPOSE_FILES) restart

logs: ## Tail logs from all services
	docker compose $(COMPOSE_FILES) logs -f

ps: ## Show service status
	docker compose $(COMPOSE_FILES) ps

# ── Build ─────────────────────────────────────────────────────────────────────

build: ## Rebuild all images
	docker compose $(COMPOSE_FILES) build

build-api: ## Rebuild only the API image
	docker compose $(COMPOSE_FILES) build api

build-frontend: ## Rebuild only the frontend image
	docker compose $(COMPOSE_FILES) build frontend

# ── Maintenance ───────────────────────────────────────────────────────────────

pull: ## Pull latest images
	docker compose $(COMPOSE_FILES) pull

update: ## Pull images and recreate services
	docker compose $(COMPOSE_FILES) pull
	docker compose $(COMPOSE_FILES) up -d --build

clean: ## Remove all containers, networks, and unused volumes (WARNING: destroys data!)
	docker compose $(COMPOSE_FILES) down -v --remove-orphans 2>/dev/null || true
	docker system prune -af --volumes 2>/dev/null || true
	@printf "\n  \033[33m⚠  All data destroyed\033[0m\n\n"

# ── Backups ───────────────────────────────────────────────────────────────────

BACKUP_DIR ?= ./backups
BACKUP_NAME ?= shadowhive-$(shell date +%Y%m%d-%H%M%S)

backup: ## Backup all volumes (set BACKUP_DIR to change destination)
	@mkdir -p $(BACKUP_DIR)
	@printf "\n  \033[36mCreating backup: $(BACKUP_DIR)/$(BACKUP_NAME)\033[0m\n\n"

	@printf "  ⏺  PostgreSQL... "
	@docker compose exec -T postgres pg_dump -U shadowhive shadowhive > $(BACKUP_DIR)/$(BACKUP_NAME)-pgdump.sql 2>/dev/null && \
		gzip $(BACKUP_DIR)/$(BACKUP_NAME)-pgdump.sql && \
		printf "\033[32mdone\033[0m\n" || printf "\033[31mfailed\033[0m\n"

	@printf "  ⏺  Neo4j... "
	@docker compose exec -T neo4j cypher-shell -u neo4j -p "${NEO4J_PASSWORD:-shadowhive}" \
		"CALL apoc.export.csv.all('/tmp/neo4j-dump.csv', {})" 2>/dev/null; \
		docker compose cp neo4j:/tmp/neo4j-dump.csv $(BACKUP_DIR)/$(BACKUP_NAME)-neo4j.csv 2>/dev/null && \
		gzip $(BACKUP_DIR)/$(BACKUP_NAME)-neo4j.csv && \
		printf "\033[32mdone\033[0m\n" || printf "\033[33mskipped (APOC may not be installed)\033[0m\n"

	@printf "  ⏺  Volumes (pgdata, neodata, ollamadata)... "
	@for vol in pgdata neodata ollamadata; do \
		docker run --rm -v shadowhive_$${vol}:/source -v $(BACKUP_DIR):/backup alpine \
			tar czf /backup/$(BACKUP_NAME)-$${vol}.tar.gz -C /source . ; \
	done 2>/dev/null && printf "\033[32mdone\033[0m\n" || printf "\033[31mfailed\033[0m\n"

	@printf "\n  \033[32m✔ Backup complete: $(BACKUP_DIR)/$(BACKUP_NAME)-*\033[0m\n"

restore: ## Restore from backup (set BACKUP_NAME=shadowhive-20240101-120000)
	@printf "\n  \033[33m⚠  Restore will overwrite current data\033[0m\n"
	@printf "  Backups in: $(BACKUP_DIR)/\n"
	@printf "  Backup name: $(BACKUP_NAME)\n\n"
	@read -p "  Continue? [y/N] " confirm; \
	if [ "$$confirm" != "y" ] && [ "$$confirm" != "Y" ]; then \
		printf "\n  Aborted.\n\n"; exit 1; fi

	@if [ -f "$(BACKUP_DIR)/$(BACKUP_NAME)-pgdump.sql.gz" ]; then \
		printf "  ⏺  PostgreSQL... "; \
		gunzip -c $(BACKUP_DIR)/$(BACKUP_NAME)-pgdump.sql.gz | docker compose exec -T postgres \
			psql -U shadowhive shadowhive 2>/dev/null && \
			printf "\033[32mdone\033[0m\n" || printf "\033[31mfailed\033[0m\n"; \
	fi

	@if [ -f "$(BACKUP_DIR)/$(BACKUP_NAME)-pgdata.tar.gz" ]; then \
		printf "  ⏺  pgdata volume... "; \
		docker run --rm -v shadowhive_pgdata:/target -v $(BACKUP_DIR):/backup alpine \
			sh -c "rm -rf /target/* && tar xzf /backup/$(BACKUP_NAME)-pgdata.tar.gz -C /target" 2>/dev/null && \
			printf "\033[32mdone\033[0m\n" || printf "\033[31mfailed\033[0m\n"; \
	fi

	@printf "\n  \033[32m✔ Restore complete. Restart services: make restart\033[0m\n\n"

# ── Utilities ─────────────────────────────────────────────────────────────────

pull-model: ## Pull the default Ollama model
	docker compose exec ollama ollama pull llama3.2:3b

list-models: ## List downloaded Ollama models
	docker compose exec ollama ollama list

shell-api: ## Open a shell in the API container
	docker compose exec api sh

shell-db: ## Open a PostgreSQL shell
	docker compose exec postgres psql -U shadowhive shadowhive

logs-api: ## Tail API logs only
	docker compose logs -f api

logs-frontend: ## Tail frontend logs only
	docker compose logs -f frontend

# ── Quality of Life ───────────────────────────────────────────────────────────

prune: ## Remove unused Docker resources (safe — keeps volumes)
	docker system prune -af

prune-all: ## Remove EVERYTHING including volumes (WARNING!)
	docker system prune -af --volumes

# ── Development ────────────────────────────────────────────────────────────────

dev-install: ## Install dev dependencies
	pip install -e ".[dev]"

test: ## Run all tests
	pytest tests/ -v --tb=short $(ARGS)

test-cov: ## Run tests with coverage
	pytest tests/ -v --tb=short --cov=backend --cov-report=term --cov-report=html $(ARGS)

lint: ## Run ruff linter
	ruff check backend/ tests/ $(ARGS)

lint-fix: ## Auto-fix lint errors
	ruff check --fix backend/ tests/ $(ARGS)

format: ## Format code with ruff
	ruff format backend/ tests/ $(ARGS)

format-check: ## Check formatting without changing files
	ruff format --check backend/ tests/ $(ARGS)

typecheck: ## Run mypy type checker
	mypy --ignore-missing-imports backend/ $(ARGS)

check-all: lint format-check typecheck test ## Run all checks (lint + format + typecheck + test)

pre-commit-install: ## Install pre-commit hooks
	pre-commit install

pre-commit-run: ## Run pre-commit hooks on all files
	pre-commit run --all-files

clean-pyc: ## Remove Python cache files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	rm -rf .pytest_cache htmlcov

# ── Housekeeping ──────────────────────────────────────────────────────────────

.PHONY: help up down restart logs ps build build-api build-frontend pull update
.PHONY: clean backup restore pull-model list-models shell-api shell-db
.PHONY: logs-api logs-frontend prune prune-all
