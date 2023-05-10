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
lint: .venv lint-isort lint-black lint-flake8 lint-mypy ## Run all linters

.PHONY: lint-isort
lint-isort: .venv ; $(info $(M) running isort...) @ ## Run isort linter
	$Q $(POETRY) run isort -c --diff $(PACKAGE)
	$Q $(POETRY) run isort -c --diff $(TESTS)

.PHONY: lint-black
lint-black: .venv ; $(info $(M) running black...) @ ## Run black linter
	$Q $(POETRY) run black --check $(PACKAGE)
	$Q $(POETRY) run black --check $(TESTS)

.PHONY: lint-flake8
lint-flake8: .venv ; $(info $(M) running flake8...) @ ## Run flake8 linter
	$Q $(POETRY) run flake8 $(PACKAGE)
	$Q $(POETRY) run flake8 $(TESTS)

.PHONY: lint-mypy
lint-mypy: .venv ; $(info $(M) running mypy...) @ ## Run mypy linter
	$Q $(POETRY) run mypy $(PACKAGE)
	$Q $(POETRY) run mypy $(TESTS)

.PHONY: fix
fix: .venv fix-isort fix-black ## Run all fixers

.PHONY: fix-isort
fix-isort: .venv ; $(info $(M) running isort...) @ ## Run isort fixer
	$Q $(POETRY) run isort $(PACKAGE)
	$Q $(POETRY) run isort $(TESTS)

.PHONY: fix-black
fix-black: .venv ; $(info $(M) running black...) @ ## Run black fixer
	$Q $(POETRY) run black $(PACKAGE)
	$Q $(POETRY) run black $(TESTS)

.PHONY: test
test: .venv ; $(info $(M) running tests...) @ ## Run tests
	$Q $(POETRY) run pytest --cov-report $(TEST_COV_REP) --cov $(PACKAGE) --codeblocks -v

BENCH_ARGS?=--benchmark-only
BENCH_CMP?=0001

.PHONY: benchmark
benchmark: .venv ; $(info $(M) running benchmarks...) @ ## Run and save benchmark
	$Q $(POETRY) run pytest ${BENCH_ARGS} --benchmark-autosave

.PHONY: benchmark-cmp
benchmark-cmp: .venv ; $(info $(M) running benchmark and comparing to ${BENCH_CMP}...) @ ## Run a benchmark and compare it to a previous one
	$Q $(POETRY) run pytest ${BENCH_ARGS} --benchmark-compare=${BENCH_CMP}

PROF_DIR:=.prof
PROF_FILE:=${PROF_DIR}/$(shell date +%H%M%S).prof

.PHONY: profile
profile: .venv ; $(info $(M) running profiling...) @ ## Create profile with benchmarks and visualize with snakeviz
	$Q mkdir -p ${PROF_DIR}
	$Q $(POETRY) run python -m cProfile -o ${PROF_FILE} -m pytest ${BENCH_ARGS}
	$Q $(POETRY) run snakeviz ${PROF_FILE}

.PHONY: release
release: lint test ; $(info $(M) running tests...) @ ## Release to PYPI
	$Q $(POETRY) publish --build --username=__token__ --password=$(PYPI_TOKEN)

.PHONY: help
help: ## Show this help
	$(eval HELP_COL_WIDTH:=13)
	$Q echo "Makefile targets:"
	$Q grep -E '[^\s]+:.*?## .*$$' ${MAKEFILE_LIST} | grep -v grep | envsubst | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-${HELP_COL_WIDTH}s\033[0m %s\n", $$1, $$2}'
