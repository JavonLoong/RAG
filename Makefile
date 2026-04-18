.PHONY: install
install: ## Install dependencies and pre-commit hooks
	@echo "Setting up the workspace with uv"
	@uv sync
	@uv run pre-commit install

.PHONY: check
check: ## Run lockfile, lint, type, and dependency checks
	@echo "Checking lockfile consistency"
	@uv lock --locked
	@echo "Running pre-commit checks"
	@uv run pre-commit run -a
	@echo "Running mypy"
	@uv run mypy
	@echo "Running deptry"
	@uv run deptry src

.PHONY: test
test: ## Run the root workspace tests
	@echo "Running tests"
	@uv run python -m pytest tests --cov --cov-config=pyproject.toml --cov-report=xml

.PHONY: build
build: clean-build ## Build the root package wheel
	@echo "Building wheel"
	@uvx --from build pyproject-build --installer uv

.PHONY: clean-build
clean-build: ## Remove build artifacts
	@echo "Removing build artifacts"
	@uv run python -c "import os, shutil; shutil.rmtree('dist') if os.path.exists('dist') else None"

.PHONY: docs-test
docs-test: ## Build docs without serving
	@uv run mkdocs build -s

.PHONY: docs
docs: ## Serve docs locally
	@uv run mkdocs serve

.PHONY: help
help:
	@uv run python -c "import re; [[print(f'\033[36m{m[0]:<20}\033[0m {m[1]}') for m in re.findall(r'^([a-zA-Z_-]+):.*?## (.*)$$', open(makefile).read(), re.M)] for makefile in ('$(MAKEFILE_LIST)').strip().split()]"

.DEFAULT_GOAL := help
