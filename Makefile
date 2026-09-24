# tablet-wall developer tasks. Run `make` with no target to list them.
#
# Every recipe cds to the repository root first, because main.py mounts its
# static directories by relative path and therefore only imports from there.

ROOT := $(dir $(realpath $(firstword $(MAKEFILE_LIST))))
PORT ?= 8000

.DEFAULT_GOAL := help

.PHONY: help sync dev run test clean

help: ## Show this help
	@echo "tablet-wall:"
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-6s\033[0m %s\n", $$1, $$2}'

sync: ## Create .venv and install all dependencies
	@cd "$(ROOT)" && uv sync

dev: ## Run the dev server with auto-reload
	@cd "$(ROOT)" && uv run fastapi dev main.py --port $(PORT)

run: ## Run the server without auto-reload
	@cd "$(ROOT)" && uv run fastapi run main.py --port $(PORT)

test: ## Run the test suite
	@cd "$(ROOT)" && uv run pytest

clean: ## Remove the virtualenv and Python caches
	@cd "$(ROOT)" && rm -rf .venv .pytest_cache
	@find "$(ROOT)" -name __pycache__ -type d -prune -exec rm -rf {} +
