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
lint: .venv lint-ruff-check lint-ruff-format lint-mypy ## Run all linters

.PHONY: lint-mypy
lint-mypy: .venv ; $(info $(M) running mypy...) @ ## Run mypy linter
	$Q $(POETRY) run mypy $(PACKAGE) $(TESTS)

.PHONY: lint-ruff-check
lint-ruff-check: .venv | $(BASE) ; $(info $(M) running ruff check…) @ ## Run ruff check linter
	$Q $(POETRY) run ruff check $(PACKAGE) $(TESTS)

.PHONY: lint-ruff-format
lint-ruff-format: .venv | $(BASE) ; $(info $(M) running ruff format…) @ ## Run ruff format linter
	$Q $(POETRY) run ruff format $(PACKAGE) $(TESTS) --check

.PHONY: fix
fix: .venv fix-ruff-check fix-ruff-format ## Run all fixers

.PHONY: fix-ruff-check
fix-ruff-check: .venv | $(BASE) ; $(info $(M) running ruff check…) @ ## Run ruff check fixer
	$Q $(POETRY) run ruff check $(PACKAGE) $(TESTS) --fix

.PHONY: fix-ruff-format
fix-ruff-format: .venv | $(BASE) ; $(info $(M) running ruff format…) @ ## Run ruff format fixer
	$Q $(POETRY) run ruff format $(PACKAGE) $(TESTS)

.PHONY: test
test: .venv ; $(info $(M) running tests...) @ ## Run tests
	$Q $(POETRY) run pytest --cov-report $(TEST_COV_REP) --cov $(PACKAGE) --codeblocks -v

BENCH_ARGS ?= --benchmark-enable --benchmark-only
BENCH_CMP  ?= 0001

.PHONY: benchmark
benchmark: .venv ; $(info $(M) running benchmarks...) @ ## Run and save benchmarks
	$Q $(POETRY) run pytest $(TESTS) ${BENCH_ARGS} --benchmark-autosave

.PHONY: benchmark-cmp
benchmark-cmp: .venv ; $(info $(M) comparing benchmarks to ${BENCH_CMP}...) @ ## Run benchmarks and compare to a saved run
	$Q $(POETRY) run pytest $(TESTS) ${BENCH_ARGS} --benchmark-compare=${BENCH_CMP} --benchmark-compare-fail=mean:25%

.PHONY: perf
perf: .venv ; $(info $(M) running performance gate...) @ ## Run the performance regression gate and print per-arm timings
	$Q $(POETRY) run pytest $(TESTS)/tracing/test_perf.py -v -s

PROF_DIR  := .prof
PROF_FILE := ${PROF_DIR}/$(shell date +%H%M%S).prof

.PHONY: profile
profile: .venv ; $(info $(M) profiling benchmarks...) @ ## Profile the benchmarks and open snakeviz
	$Q mkdir -p ${PROF_DIR}
	$Q $(POETRY) run python -m cProfile -o ${PROF_FILE} -m pytest $(TESTS) ${BENCH_ARGS}
	$Q $(POETRY) run snakeviz ${PROF_FILE}

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


