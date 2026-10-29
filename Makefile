# tablet-wall-ai developer tasks. Run `make` with no target to list them.
#
# Every recipe cds to the repository root first, because main.py mounts its
# static directories by relative path and therefore only imports from there.

ROOT := $(dir $(realpath $(firstword $(MAKEFILE_LIST))))
PORT ?= 8000
HOST ?= 127.0.0.1

.DEFAULT_GOAL := help

.PHONY: help sync dev run test sim guide clean

help: ## Show this help
	@echo "tablet-wall-ai:"
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-6s\033[0m %s\n", $$1, $$2}'

sync: ## Create .venv and install all dependencies
	@cd "$(ROOT)" && uv sync

dev: ## Run the dev server with auto-reload
	@cd "$(ROOT)" && uv run fastapi dev main.py --port $(PORT)

run: ## Run the server without auto-reload
	@cd "$(ROOT)" && uv run fastapi run main.py --host $(HOST) --port $(PORT)

test: ## Run Python and client JavaScript tests
	@command -v node >/dev/null 2>&1 || { echo "make test needs Node.js for the client tests"; exit 1; }
	@cd "$(ROOT)" && uv run pytest
	@cd "$(ROOT)" && for test in tests/*.test.js; do node "$$test" || exit $$?; done

sim: ## Exercise 18 virtual tablets against an isolated app/database
	@cd "$(ROOT)" && uv run python simulator/run.py
	@cd "$(ROOT)" && uv run pytest -q simulator/test_simulator_selftest.py

guide: ## Rebuild the field guide from GUIDE.md
	@cd "$(ROOT)" && uv run --group docs python docs/field-guide/build.py

clean: ## Remove the virtualenv and Python caches
	@cd "$(ROOT)" && rm -rf .venv .pytest_cache
	@find "$(ROOT)" -name __pycache__ -type d -prune -exec rm -rf {} +
