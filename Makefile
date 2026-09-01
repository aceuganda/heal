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
# `make up` starts everything: api_server, web_server, relational_db, qdrant
# and nginx. There is no second command and no opt-in profile -- a stack you
# have to remember to start twice is a stack that boots half broken.
#
# Vespa, the `background` supervisord fleet and the model server are gone from
# the runtime -- see docker-compose.local.yml for what each one used to do.
# ---------------------------------------------------------------------------

# Build attempts before giving up. Each one keeps whatever it downloaded:
# pip and npm caches are BuildKit cache mounts, so a network timeout costs the
# time already spent, not the bytes already fetched. Override with RETRIES=n.
RETRIES ?= 5

# Retry a compose build, resuming from the cache each time.
# $(1) is any extra compose arguments (profiles, service names).
define build_with_retry
@set -e; \
for i in $$(seq 1 $(RETRIES)); do \
	echo ""; \
	echo "==> build attempt $$i of $(RETRIES)"; \
	if $(COMPOSE) $(1) build; then \
		echo "==> build succeeded"; \
		exit 0; \
	fi; \
	echo "==> attempt $$i failed. Downloaded packages are cached; retrying."; \
	sleep 5; \
done; \
echo ""; \
echo "Build failed after $(RETRIES) attempts."; \
echo "The cache is kept, so 'make up' will resume rather than restart."; \
exit 1
endef

.PHONY: build
build: ## Build both images, retrying on network failure (cache is kept)
	$(call build_with_retry,)

.PHONY: build-web
build-web: ## Build only the web image, with retries
	$(call build_with_retry,web_server)

.PHONY: build-api
build-api: ## Build only the API image, with retries
	$(call build_with_retry,api_server)

.PHONY: rebuild
rebuild: ## Full rebuild ignoring the layer cache (slow; downloads are still cached)
	$(COMPOSE) build --no-cache

.PHONY: up
up: ## Build (with retries) and start the whole stack (web on :3000)
	$(call build_with_retry,)
	$(COMPOSE) up -d
	@echo ""
	@echo "Web    http://localhost:3000"
	@echo "API    http://localhost:8080"
	@echo "Admin  http://localhost:3000/admin/sources  (upload and index here)"

# ---------------------------------------------------------------------------
# Restarting one service
#
# Both of these REBUILD before recreating. A plain `docker compose restart`
# reuses the existing image, so it picks up an environment change but not a
# code change -- which looks exactly like your edit having no effect.
#
# Dependencies are started if they are down but never recreated, so Postgres
# and Qdrant keep running (and keep their data) either way.
# ---------------------------------------------------------------------------

.PHONY: restart-api
restart-api: ## Rebuild and restart ONLY the API (backend code changes)
	$(call build_with_retry,api_server)
	$(COMPOSE) up -d api_server
	@echo "API http://localhost:8080  --  make api-logs to watch it"

.PHONY: restart-web
restart-web: ## Rebuild and restart ONLY the frontend (web code changes)
	$(call build_with_retry,web_server)
	$(COMPOSE) up -d web_server
	@echo "Web http://localhost:3000  --  make web-logs to watch it"

.PHONY: bounce-api
bounce-api: ## Restart the API container WITHOUT rebuilding (env or state only)
	$(COMPOSE) restart api_server

.PHONY: bounce-web
bounce-web: ## Restart the web container WITHOUT rebuilding
	$(COMPOSE) restart web_server

.PHONY: cache-size
cache-size: ## Show how much build cache is being kept
	@docker system df -v 2>/dev/null | awk '/Build Cache/,0' | head -5

.PHONY: cache-clear
cache-clear: ## Delete the build cache, including downloaded packages
	@echo "This discards every cached wheel and npm package; the next build re-downloads them."
	docker builder prune -af

# ---------------------------------------------------------------------------
# Knowledge base (RAG)
#
# There are no make targets for uploading, approving or searching. All of it
# lives in the admin UI at /admin/sources, which is where an admin who is not
# holding a terminal has to be able to do it. `heal.knowledge.cli` still exists
# for scripted bulk loads.
# ---------------------------------------------------------------------------

.PHONY: config
config: ## Validate the compose file without starting anything
	$(COMPOSE) config -q
	@echo "compose file is valid"

.PHONY: smoke
smoke: ## Check every service in the running stack answers
	@curl -fsS http://localhost:8080/health && echo "  <- api_server ok"
	@curl -fsSo /dev/null http://localhost:3000 && echo "web_server ok"
	@curl -fsS http://localhost:8080/manage/knowledge/status \
		&& echo "  <- knowledge ok"

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

.PHONY: web-logs
web-logs: ## Tail only the web server
	$(COMPOSE) logs -f --tail=100 web_server

.PHONY: ingest-logs
ingest-logs: ## Tail only indexing activity (progress, failures)
	$(COMPOSE) logs -f --tail=200 api_server \
		| grep --line-buffered -iE "ingest|embedding model|qdrant collection"

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
