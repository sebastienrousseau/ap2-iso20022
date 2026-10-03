# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: Apache-2.0 OR MIT

.PHONY: help install dev test lint format type-check security clean examples demo check

PYTHON ?= python3
POETRY ?= poetry

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install production dependencies
	$(POETRY) install --only main

dev: ## Install all dependencies (including dev)
	$(POETRY) install --extras oracle

test: ## Run tests
	$(POETRY) run pytest tests/ -v

lint: ## Run linters (ruff + black check)
	$(POETRY) run ruff check ap2_iso20022/ tests/
	$(POETRY) run black --check ap2_iso20022/ tests/

format: ## Auto-format code (ruff fix + black)
	$(POETRY) run ruff check --fix ap2_iso20022/ tests/
	$(POETRY) run black ap2_iso20022/ tests/

type-check: ## Run mypy type checking
	$(POETRY) run mypy ap2_iso20022/

security: ## Run security scan (bandit)
	$(POETRY) run bandit -r ap2_iso20022/ -c pyproject.toml 2>/dev/null || \
		$(POETRY) run bandit -r ap2_iso20022/ -ll

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .eggs/
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/ htmlcov/
	rm -rf coverage.xml .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true

examples: ## Verify example scripts run
	$(POETRY) run python examples/01_ap2_to_pain001.py
	$(POETRY) run python examples/02_x402_to_pacs008.py
	$(POETRY) run python examples/03_guardrails.py

demo: ## Render the README demo GIF with VHS
	vhs .github/demo.tape

check: lint type-check test examples ## Run all gates: lint + type-check + test + examples
