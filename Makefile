.DEFAULT_GOAL:=help

PACKAGE       = troncos
POETRY        = poetry

M = $(shell printf "\033[34;1m▶\033[0m")

$(POETRY): ; $(info $(M) checking POETRY…)

.venv: pyproject.toml poetry.lock ; $(info $(M) retrieving dependencies…) @ ## Install python dependencies
	$Q $(POETRY) run pip install -U pip
	$Q $(POETRY) install --no-interaction
	$Q $(POETRY) run mypy --install-types --non-interactive
	@touch $@

.PHONY: lint
lint: .venv lint-isort lint-black lint-flake8 lint-mypy ; @ ## Run all linters
	$Q

.PHONY: lint-isort
lint-isort: .venv ; $(info $(M) running isort…) @ ## Run isort linter
	$Q $(POETRY) run isort -c --diff $(PACKAGE)

.PHONY: lint-black
lint-black: .venv ; $(info $(M) running black…) @ ## Run black linter
	$Q $(POETRY) run black --check $(PACKAGE)

.PHONY: lint-flake8
lint-flake8: .venv ; $(info $(M) running flake8…) @ ## Run flake8 linter
	$Q $(POETRY) run flake8 $(PACKAGE)

.PHONY: lint-mypy
lint-mypy: .venv ; $(info $(M) running mypy…) @ ## Run mypy linter
	$Q $(POETRY) run mypy $(PACKAGE)

.PHONY: fix
fix: .venv fix-isort fix-black ; @ ## Run all fixers
	$Q

.PHONY: fix-isort
fix-isort: .venv ; $(info $(M) running isort…) @ ## Run isort fixer
	$Q $(POETRY) run isort $(PACKAGE)

.PHONY: fix-black
fix-black: .venv ; $(info $(M) running black…) @ ## Run black fixer
	$Q $(POETRY) run black $(PACKAGE)

.PHONY: test
test: .venv ; $(info $(M) running tests…) @ ## Run tests
	$Q $(POETRY) run pytest tests -v -c pytest.ini

.PHONY: help
help: ## Show this help
	$(eval HELP_COL_WIDTH:=13)
	@echo "Makefile targets:"
	@grep -E '[^\s]+:.*?## .*$$' ${MAKEFILE_LIST} | grep -v grep | envsubst | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-${HELP_COL_WIDTH}s\033[0m %s\n", $$1, $$2}'
