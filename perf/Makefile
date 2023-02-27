NR_RUNS:=50
OUTPUT_FOLDER:=test
OUTPUT_JSON:=${OUTPUT_FOLDER}/res.json
OUTPUT_JSON_ADJ:=${OUTPUT_FOLDER}/res_adj.json

STATS_SCRIPTS:=.stats

TEST_BASE:=test_base
TEST_NOOP:=test_noop

OTEL_VERSION:=1.16.0
TEST_OTEL_BASE:=test_otel_base
TEST_OTEL_MEDIUM:=test_otel_medium
TEST_OTEL_SLOW:=test_otel_slow

DDTRACE_VERSION:=1.8.0
TEST_DD_BASE:=test_dd_base
TEST_DD_MEDIUM:=test_dd_medium
TEST_DD_SLOW:=test_dd_slow

TRONCOLD_VERSION:=3.0.5
TEST_TRONCOLD_BASE:=test_troncold_base
TEST_TRONCOLD_MEDIUM:=test_troncold_medium
TEST_TRONCOLD_SLOW:=test_troncold_slow

TEST_TRONCOS_BASE:=test_troncos_base
TEST_TRONCOS_MEDIUM:=test_troncos_medium
TEST_TRONCOS_SLOW:=test_troncos_slow

#TO_RUN:=${TEST_NOOP}
#TO_RUN:=${TEST_BASE},${TEST_OTEL_BASE},${TEST_DD_BASE},${TEST_TRONCOS_BASE},${TEST_TRONCOLD_BASE}
#TO_RUN:=${TEST_OTEL_BASE},${TEST_DD_BASE},${TEST_TRONCOS_BASE},${TEST_TRONCOLD_BASE}
#TO_RUN:=${TEST_OTEL_MEDIUM},${TEST_DD_MEDIUM},${TEST_TRONCOS_MEDIUM},${TEST_TRONCOLD_MEDIUM}
#TO_RUN:=${TEST_OTEL_SLOW},${TEST_DD_SLOW},${TEST_TRONCOS_SLOW},${TEST_TRONCOLD_SLOW}
TO_RUN:=${TEST_NOOP},${TEST_BASE},${TEST_OTEL_MEDIUM},${TEST_DD_MEDIUM},${TEST_TRONCOS_MEDIUM},${TEST_TRONCOLD_MEDIUM}

HYPERFINE:=hyperfine
POETRY:=poetry

.DEFAULT_GOAL:=${OUTPUT_FOLDER}

.PHONY: _setup_${TEST_BASE}
_setup_${TEST_BASE}:
	# Running _setup_${TEST_BASE}
	rm -rf .venv || true
	cp pyproject.tmpl pyproject.toml
	${POETRY} install -q

.PHONY: _setup_${TEST_NOOP}
_setup_${TEST_NOOP}: _setup_${TEST_BASE}

.PHONY: _setup_${TEST_OTEL_BASE} _setup_${TEST_OTEL_MEDIUM} _setup_${TEST_OTEL_SLOW}
_setup_${TEST_OTEL_BASE}: _setup_${TEST_BASE}
	# Running _setup_${TEST_OTEL_BASE}
	${POETRY} add opentelemetry-api@${OTEL_VERSION} -q
	${POETRY} add opentelemetry-sdk@${OTEL_VERSION} -q
_setup_${TEST_OTEL_MEDIUM}: _setup_${TEST_OTEL_BASE}
_setup_${TEST_OTEL_SLOW}: _setup_${TEST_OTEL_BASE}

.PHONY: _setup_${TEST_DD_BASE} _setup_${TEST_DD_MEDIUM} _setup_${TEST_DD_SLOW}
_setup_${TEST_DD_BASE}: _setup_${TEST_BASE}
	# Running _setup_${TEST_DD_BASE}
	${POETRY} add ddtrace@${DDTRACE_VERSION} -q
_setup_${TEST_DD_MEDIUM}: _setup_${TEST_DD_BASE}
_setup_${TEST_DD_SLOW}: _setup_${TEST_DD_BASE}

.PHONY: _setup_${TEST_TRONCOLD_BASE} _setup_${TEST_TRONCOLD_MEDIUM} _setup_${TEST_TRONCOLD_SLOW}
_setup_${TEST_TRONCOLD_BASE}: _setup_${TEST_BASE}
	# Running _setup_${TEST_TRONCOLD_BASE}
	${POETRY} add troncos@${TRONCOLD_VERSION} -q
_setup_${TEST_TRONCOLD_MEDIUM}: _setup_${TEST_TRONCOLD_BASE}
_setup_${TEST_TRONCOLD_SLOW}: _setup_${TEST_TRONCOLD_BASE}

.PHONY: _setup_${TEST_TRONCOS_BASE} _setup_${TEST_TRONCOS_MEDIUM} _setup_${TEST_TRONCOS_SLOW}
_setup_${TEST_TRONCOS_BASE}: _setup_${TEST_BASE}
	# Running _setup_${TEST_TRONCOS_BASE}
	${POETRY} add ../ -q
_setup_${TEST_TRONCOS_MEDIUM}: _setup_${TEST_TRONCOS_BASE}
_setup_${TEST_TRONCOS_SLOW}: _setup_${TEST_TRONCOS_BASE}

.PHONY: _setup
_setup:
	$(MAKE) _setup_${TEST}

.PHONY: _run
_run:
	##################################
	#### Running _run_${TEST}
	##################################
	${POETRY} run python -u -m troncos_perf ${TEST}

${OUTPUT_FOLDER}: ## Run test
	mkdir -p ${OUTPUT_FOLDER}
	${HYPERFINE} \
		--show-output \
		--warmup 3 \
		--time-unit millisecond \
		--command-name "{test}" \
		--parameter-list test ${TO_RUN} \
		--setup "make --no-print-directory _setup_{test}" \
		--runs ${NR_RUNS} \
		--export-json ${OUTPUT_JSON} \
		".venv/bin/python -u -m troncos_perf {test}"

.PHONY: _graph_dep
_graph_dep:
	${POETRY} add numpy matplotlib scipy -q

${OUTPUT_FOLDER}/plots: ${OUTPUT_FOLDER} ${STATS_SCRIPTS} _graph_dep
	mkdir -p ${OUTPUT_FOLDER}/plots
	${POETRY} run python -m troncos_perf.offset ${OUTPUT_JSON} ${OUTPUT_JSON_ADJ}
	${POETRY} run python ${STATS_SCRIPTS}/plot_whisker.py ${OUTPUT_JSON_ADJ} -o ${OUTPUT_FOLDER}/plots/whisker.png 2> /dev/null
	${POETRY} run python ${STATS_SCRIPTS}/plot_histogram.py ${OUTPUT_JSON_ADJ} --type barstacked -o ${OUTPUT_FOLDER}/plots/histogram.png 2> /dev/null
	${POETRY} run python ${STATS_SCRIPTS}/welch_ttest.py ${OUTPUT_JSON_ADJ} || true

${STATS_SCRIPTS}:
	mkdir ${STATS_SCRIPTS}
	cd ${STATS_SCRIPTS} && wget -q https://raw.githubusercontent.com/sharkdp/hyperfine/master/scripts/plot_whisker.py
	cd ${STATS_SCRIPTS} && wget -q https://raw.githubusercontent.com/sharkdp/hyperfine/master/scripts/plot_histogram.py
	cd ${STATS_SCRIPTS} && wget -q https://raw.githubusercontent.com/sharkdp/hyperfine/master/scripts/welch_ttest.py

clean:
	rm -rf ${OUTPUT_FOLDER}
	rm -f pyproject.toml
	rm -f poetry.lock
