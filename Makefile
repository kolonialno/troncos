.DEFAULT_GOAL:=help

PACKAGE       = troncos
TESTS         = tests
POETRY        = poetry
TEST_COV_REP  ?= html

Q = $(if $(filter 1,$V),,@)
M = $(shell printf "\033[34;1m▶\033[0m")

$(POETRY): ; $(info $(M) checking POETRY...)

.venv: pyproject.toml poetry.lock ; $(info $(M) retrieving dependencies...) @ ## Install python dependencies
	$Q $(POETRY) run pip install -U pip
	$Q $(POETRY) install --all-extras --no-interaction
	@touch $@

.PHONY: lint
lint: .venv lint-isort lint-black lint-ruff-check lint-ruff-format lint-mypy ## Run all linters

.PHONY: lint-isort
lint-isort: .venv ; $(info $(M) running isort...) @ ## Run isort linter
	$Q $(POETRY) run isort -c --diff $(PACKAGE)
	$Q $(POETRY) run isort -c --diff $(TESTS)

.PHONY: lint-black
lint-black: .venv ; $(info $(M) running black...) @ ## Run black linter
	$Q $(POETRY) run black --check $(PACKAGE)
	$Q $(POETRY) run black --check $(TESTS)

.PHONY: lint-mypy
lint-mypy: .venv ; $(info $(M) running mypy...) @ ## Run mypy linter
	$Q $(POETRY) run mypy $(PACKAGE)
	$Q $(POETRY) run mypy $(TESTS)

.PHONY: lint-ruff-check
lint-ruff-check: .venv | $(BASE) ; $(info $(M) running ruff check…) @ ## Run ruff check linter
	$Q $(POETRY) run ruff check $(PACKAGE)

.PHONY: lint-ruff-format
lint-ruff-format: .venv | $(BASE) ; $(info $(M) running ruff format…) @ ## Run ruff format linter
	$Q $(POETRY) run ruff format $(PACKAGE) --check

.PHONY: fix
fix: .venv fix-isort fix-black fix-ruff-check fix-ruff-format ## Run all fixers

.PHONY: fix-isort
fix-isort: .venv ; $(info $(M) running isort...) @ ## Run isort fixer
	$Q $(POETRY) run isort $(PACKAGE)
	$Q $(POETRY) run isort $(TESTS)

.PHONY: fix-black
fix-black: .venv ; $(info $(M) running black...) @ ## Run black fixer
	$Q $(POETRY) run black $(PACKAGE)
	$Q $(POETRY) run black $(TESTS)

.PHONY: fix-ruff-check
fix-ruff-check: .venv | $(BASE) ; $(info $(M) running ruff check…) @ ## Run ruff check fixer
	$Q $(POETRY) run ruff check $(PACKAGE) --fix

.PHONY: fix-ruff-format
fix-ruff-format: .venv | $(BASE) ; $(info $(M) running ruff format…) @ ## Run ruff format fixer
	$Q $(POETRY) run ruff format $(PACKAGE)

.PHONY: test
test: .venv ; $(info $(M) running tests...) @ ## Run tests
	$Q $(POETRY) run pytest --cov-report $(TEST_COV_REP) --cov $(PACKAGE) --codeblocks -v

.PHONY: release
release: lint test ; $(info $(M) running tests...) @ ## Release to PYPI
	$Q $(POETRY) publish --build --username=__token__ --password=$(PYPI_TOKEN)

.PHONY: copy_docs
copy_docs: .venv ; $(info $(M) copy docs...) @
	$Q mkdir -p docs && cp README.md docs/

.PHONY: docs
docs: .venv ; $(info $(M) generating docs...) @
	$Q ./.venv/bin/mkdocs serve --verbose

.PHONY: help
help: ## Show this help
	$(eval HELP_COL_WIDTH:=13)
	$Q echo "Makefile targets:"
	$Q grep -E '[^\s]+:.*?## .*$$' ${MAKEFILE_LIST} | grep -v grep | envsubst | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-${HELP_COL_WIDTH}s\033[0m %s\n", $$1, $$2}'


