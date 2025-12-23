.PHONY: help install setup up down logs test clean migrate build

# Load environment variables from .env file
-include .env
export

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install Python dependencies
	uv sync

dev: ## Run bot locally (not in Docker)
	uv run fastapi dev app/main.py 

example: ## Run example script
	uv run python scripts/massive-ex.py

format: ## Format code
	uv run ruff format .

lint: ## Lint code
	uv run ruff check . --fix

typecheck: ## Type check code
	uv run mypy .