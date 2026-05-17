SHELL := /bin/bash
.DEFAULT_GOAL := help

# --- Tool Configuration ---
PYTHON       ?= python3
PYTEST       ?= $(PYTHON) -m pytest
COVERAGE     ?= $(PYTHON) -m coverage
PIP          ?= $(PYTHON) -m pip
RUFF         ?= $(PYTHON) -m ruff
COVERAGE_MIN ?= 90

# Where the source under test lives (single-file script in repo root).
SRC_FILES    := newRepos.py

# --- Colors (conditional on terminal) ---
ifneq ($(TERM),)
  GREEN  := \033[0;32m
  RED    := \033[0;31m
  YELLOW := \033[0;33m
  RESET  := \033[0m
else
  GREEN  :=
  RED    :=
  YELLOW :=
  RESET  :=
endif

.PHONY: help test test-unit test-integration coverage coverage-html \
        coverage-check lint clean install-test-deps

help: ## Show this help message
	@echo "Available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

install-test-deps: ## Install testing dependencies (pytest, coverage, ruff)
	@echo "$(YELLOW)Installing test dependencies...$(RESET)"
	$(PIP) install -e ".[test]"

test: ## Run all tests (unit + integration)
	@echo "$(YELLOW)Running all tests...$(RESET)"
	$(PYTEST) tests/ -v
	@echo "$(GREEN)All tests passed.$(RESET)"

test-unit: ## Run unit tests only (exclude integration marker)
	@echo "$(YELLOW)Running unit tests...$(RESET)"
	$(PYTEST) tests/ -v -m "not integration"
	@echo "$(GREEN)Unit tests passed.$(RESET)"

test-integration: ## Run integration tests only
	@echo "$(YELLOW)Running integration tests...$(RESET)"
	$(PYTEST) tests/ -v -m integration
	@echo "$(GREEN)Integration tests passed.$(RESET)"

coverage: ## Run tests with coverage measurement
	@echo "$(YELLOW)Running tests with coverage...$(RESET)"
	$(PYTEST) tests/ \
		--cov=newRepos \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--cov-report=xml:coverage.xml
	@echo "$(GREEN)Coverage report generated.$(RESET)"

coverage-html: coverage ## Generate HTML coverage report and try to open it
	@echo "Opening coverage report..."
	@$(PYTHON) -m webbrowser htmlcov/index.html 2>/dev/null || \
		echo "Open htmlcov/index.html in your browser."

coverage-check: ## Fail if coverage is below $(COVERAGE_MIN)%
	@echo "$(YELLOW)Checking coverage threshold ($(COVERAGE_MIN)%)...$(RESET)"
	$(PYTEST) tests/ \
		--cov=newRepos \
		--cov-fail-under=$(COVERAGE_MIN) \
		--cov-report=term-missing
	@echo "$(GREEN)Coverage meets the $(COVERAGE_MIN)% threshold.$(RESET)"

lint: ## Run ruff on source and tests
	@echo "$(YELLOW)Running linter...$(RESET)"
	$(RUFF) check $(SRC_FILES) tests/
	@echo "$(GREEN)Linting passed.$(RESET)"

clean: ## Remove generated files and caches
	@echo "$(YELLOW)Cleaning...$(RESET)"
	rm -rf htmlcov/ .coverage coverage.xml .pytest_cache .ruff_cache
	find . -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
	@echo "$(GREEN)Clean.$(RESET)"
