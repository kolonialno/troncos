PACKAGE       = troncos
POETRY        = poetry

M = $(shell printf "\033[34;1m▶\033[0m")

$(POETRY): ; $(info $(M) checking POETRY…)

.PHONY: lint
lint: lint-isort lint-black lint-flake8 lint-mypy ; @ ## Run all server linters
	$Q

.PHONY: lint-isort
lint-isort: ; $(info $(M) running isort…) @ ## Run isort linter
	$Q $(POETRY) run isort -c --diff $(PACKAGE)

.PHONY: lint-black
lint-black: ; $(info $(M) running black…) @ ## Run black linter
	$Q $(POETRY) run black --check $(PACKAGE)

.PHONY: lint-flake8
lint-flake8: ; $(info $(M) running flake8…) @ ## Run flake8 linter
	$Q $(POETRY) run flake8 $(PACKAGE)

.PHONY: lint-mypy
lint-mypy: ; $(info $(M) running mypy…) @ ## Run mypy linter
	$Q $(POETRY) run mypy $(PACKAGE)

.PHONY: fix
fix: fix-isort fix-black ; @ ## Run all fixers for the server and app
	$Q

.PHONY: fix-isort
fix-isort: .venv ; $(info $(M) running isort…) @ ## Run isort fixer
	$Q $(POETRY) run isort $(PACKAGE)

.PHONY: fix-black
fix-black: .venv ; $(info $(M) running black…) @ ## Run black fixer
	$Q $(POETRY) run black $(PACKAGE)

.PHONY: test
test:
	$Q $(POETRY) run pytest tests -v -c pytest.ini