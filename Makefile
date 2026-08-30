# Heal -- developer entry points.
#
# Everything here runs the same commands CI runs, so `make check` passing
# locally means the pull request is green. See docs/architecture-decisions.md.

SHELL       := /bin/bash
BACKEND     := backend
WEB         := web
VENV        := .venv
PY          := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
COMPOSE     := docker compose -f deployment/docker_compose/docker-compose.local.yml -p heal-stack

.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

.PHONY: help
help: ## Show this help
	@echo "Heal — make targets"
	@echo
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

$(VENV)/bin/activate: $(BACKEND)/requirements/default.txt $(BACKEND)/requirements/dev.txt
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r $(BACKEND)/requirements/default.txt
	$(PIP) install -r $(BACKEND)/requirements/dev.txt
	@touch $(VENV)/bin/activate

.PHONY: venv
venv: $(VENV)/bin/activate ## Create the Python venv and install backend deps

.PHONY: install
install: venv ## Install backend and web dependencies
	cd $(WEB) && npm install

# ---------------------------------------------------------------------------
# Code quality — these are exactly the CI steps
# ---------------------------------------------------------------------------

.PHONY: test
test: venv ## Run backend unit tests
	cd $(BACKEND) && ../$(PY) -m pytest tests/unit

.PHONY: test-heal
test-heal: venv ## Run only the heal/ tests (fast: no external deps)
	cd $(BACKEND) && PYTHONPATH=. ../$(PY) -m pytest tests/unit/heal -q

.PHONY: lint
lint: venv ## Run ruff
	cd $(BACKEND) && ../$(VENV)/bin/ruff .

.PHONY: typecheck
typecheck: venv ## Run mypy
	cd $(BACKEND) && ../$(VENV)/bin/mypy .

.PHONY: format
format: venv ## Apply black and reorder-python-imports
	cd $(BACKEND) && ../$(VENV)/bin/black .
	cd $(BACKEND) && find ./heal_app ./heal -name "*.py" \
		| xargs ../$(VENV)/bin/reorder-python-imports --py311-plus || true

.PHONY: format-check
format-check: venv ## Check formatting without changing files
	cd $(BACKEND) && ../$(VENV)/bin/black --check .

.PHONY: deprecated-gate
deprecated-gate: ## Fail if live code imports anything under deprecated/
	@cd $(BACKEND) && ! grep -rnE "^\s*(from|import)\s+deprecated\b" heal_app heal \
		&& echo "deprecated/ is not imported by live code"

.PHONY: check
check: format-check lint typecheck test deprecated-gate ## Everything CI runs

# ---------------------------------------------------------------------------
# Local stack
#
# Four services: api_server, web_server, relational_db, nginx. Vespa, the
# `background` supervisord fleet and the model server are all gone from the
# runtime -- see docker-compose.local.yml for what each one used to do.
#
# Qdrant sits behind the `knowledge` profile: `make up` does not start it,
# `make up-knowledge` does. Phase 1 runs with KNOWLEDGE_ENABLED=false.
# ---------------------------------------------------------------------------

.PHONY: build
build: ## Build both images without starting anything
	$(COMPOSE) build

.PHONY: up
up: ## Build and start the local stack (web on :3000)
	$(COMPOSE) up -d --build
	@echo "Web http://localhost:3000   API http://localhost:8080"

.PHONY: up-knowledge
up-knowledge: ## Start the stack with Qdrant as well (Phase 2)
	$(COMPOSE) --profile knowledge up -d --build
	@echo "Qdrant on 127.0.0.1:6333 -- set KNOWLEDGE_ENABLED=true to use it"

# ---------------------------------------------------------------------------
# Knowledge base (RAG)
#
# Retrieval only answers from APPROVED sources. Ingesting a document and
# approving it are deliberately two separate acts.
# ---------------------------------------------------------------------------

.PHONY: kb-up
kb-up: ## Start the stack with Qdrant and retrieval switched ON
	KNOWLEDGE_ENABLED=true $(COMPOSE) --profile knowledge up -d --build
	@echo "Qdrant on 127.0.0.1:6333 -- next: make kb-init"

.PHONY: kb-init
kb-init: ## Create the Qdrant collection (dense + sparse named vectors)
	$(COMPOSE) exec api_server python -m heal.knowledge.cli init

.PHONY: kb-ingest
kb-ingest: ## Ingest a document. FILE=... TITLE=... ACTOR=... [VERSION=1] [APPROVE=1]
	@test -n "$(FILE)"  || (echo "FILE=path/to/document.txt is required"  && exit 1)
	@test -n "$(TITLE)" || (echo "TITLE=\"Document title\" is required"   && exit 1)
	@test -n "$(ACTOR)" || (echo "ACTOR=who.is.doing.this is required"    && exit 1)
	$(COMPOSE) cp "$(FILE)" api_server:/tmp/ingest_input
	$(COMPOSE) exec api_server python -m heal.knowledge.cli ingest \
		--file /tmp/ingest_input --title "$(TITLE)" --actor "$(ACTOR)" \
		--version "$(or $(VERSION),1)" $(if $(APPROVE),--approve,)

.PHONY: kb-approve
kb-approve: ## Approve a source so answers may cite it. SOURCE=<source-id>
	@test -n "$(SOURCE)" || (echo "SOURCE=<source-id> is required" && exit 1)
	$(COMPOSE) exec api_server python -m heal.knowledge.cli approve --source-id "$(SOURCE)"

.PHONY: kb-search
kb-search: ## Run a query exactly as the agent would. Q="500mg BD"
	@test -n "$(Q)" || (echo "Q=\"your query\" is required" && exit 1)
	$(COMPOSE) exec api_server python -m heal.knowledge.cli search "$(Q)"

.PHONY: kb-admin
kb-admin: ## Open the approved-sources admin screen
	@echo "http://localhost:3000/admin/sources"
	@command -v open >/dev/null && open http://localhost:3000/admin/sources || true

.PHONY: kb-status
kb-status: ## Show Qdrant collection info
	$(COMPOSE) exec api_server python -c "from heal.knowledge.store import build_client; from heal import config; c=build_client(); print(c.get_collection(config.QDRANT_COLLECTION))"

.PHONY: test-knowledge
test-knowledge: venv ## Run only the retrieval tests
	cd $(BACKEND) && PYTHONPATH=. ../$(PY) -m pytest tests/unit/heal/knowledge -q

.PHONY: config
config: ## Validate the compose files without starting anything
	$(COMPOSE) config -q
	$(COMPOSE) --profile knowledge config -q
	@echo "compose files are valid"

.PHONY: smoke
smoke: ## Check the running stack answers on /health
	@curl -fsS http://localhost:8080/health && echo "  <- api_server ok"
	@curl -fsSo /dev/null http://localhost:3000 && echo "web_server ok"

.PHONY: down
down: ## Stop the local stack, keeping volumes
	$(COMPOSE) down

.PHONY: reset
reset: ## Stop the local stack and DELETE its volumes (destroys local data)
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Tail logs from the local stack
	$(COMPOSE) logs -f --tail=100

.PHONY: ps
ps: ## Show local stack status
	$(COMPOSE) ps

.PHONY: api-logs
api-logs: ## Tail only the API server
	$(COMPOSE) logs -f --tail=100 api_server

# ---------------------------------------------------------------------------
# Web
# ---------------------------------------------------------------------------

.PHONY: web-dev
web-dev: ## Run the Next.js dev server against a running API
	cd $(WEB) && npm run dev

.PHONY: web-build
web-build: ## Production build of the web app
	cd $(WEB) && npm run build

# ---------------------------------------------------------------------------
# Database
#
# `migrate` is safe on an empty database. NEVER run it against production
# during the Alembic rebaseline -- production is stamped, not upgraded.
# See docs/architecture-decisions.md § Database migrations.
# ---------------------------------------------------------------------------

.PHONY: migrate
migrate: ## Apply migrations to the local database
	$(COMPOSE) exec api_server alembic upgrade head

.PHONY: db-shell
db-shell: ## psql into the local database
	$(COMPOSE) exec relational_db psql -U postgres

.PHONY: db-dump
db-dump: ## Schema-only dump of the local database, for the rebaseline diff
	$(COMPOSE) exec -T relational_db pg_dump --schema-only -U postgres postgres

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

.PHONY: clean
clean: ## Remove the venv and Python caches
	rm -rf $(VENV) $(BACKEND)/.mypy_cache $(BACKEND)/.pytest_cache
	find $(BACKEND) -name "__pycache__" -type d -prune -exec rm -rf {} +
