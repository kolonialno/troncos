<h1>Troncos performance tests</h1>

## Setup

We will spawn processes that recursively calculate a number in the fibonacci sequence. Those processes are split into 3 categories:

- `test_noop`: Does nothing
- `test_base`: Does no tracing
- `test_otel`: Traces with the otel libraries
- `test_ddtrace`: Traces with the ddtrace libraries
- `test_troncold`: Traces with old version of troncos
- `test_troncos`: Traces with current version of troncos

Additionally, the latter two groups have 3 sub categories:

- `*_base`: Setup tracing and create `1` span
- `*_medium`: Setup tracing and create `69` spans
- `*_slow`: Setup tracing and create `8729` spans

We will use [hyperfine](https://github.com/sharkdp/hyperfine) to do `50` rounds (+ `3` warmup rounds) of tests to compare different methods.

For each test we will only install minimal amount of packages, and account for different bootstrap times. We will also only export spans to a custom exporter, not an external endpoint.

Each test allocates `500` ms to boostrap everything, so at the end of each test run, we will subtract `500` ms of the test time, and plot the result.

## Run tests

> **Warning**: The console output that hyperfine provides is not entirely accurate because we always allocate `500` ms for bootstrapping the tests. Look at the `test/res_adj.json` file instead!

```console
$ make clean test/plots
rm -rf test
rm -f pyproject.toml
mkdir -p test
hyperfine \
	--warmup 3 \
	--time-unit millisecond \
	--command-name "{test}" \
	--parameter-list test test_noop,test_base,test_otel_medium,test_dd_medium,test_troncos_medium,test_troncold_medium \
	--setup "make --no-print-directory _setup_{test}" \
	--runs 50 \
	--export-json test/res.json \
	".venv/bin/python -u -m troncos_perf {test}"
Benchmark 1: test_noop
  Time (mean ± σ):     516.2 ms ±   1.0 ms    [User: 513.8 ms, System: 2.3 ms]
  Range (min … max):   513.6 ms … 517.9 ms    50 runs

Benchmark 2: test_base
  Time (mean ± σ):     535.9 ms ±   2.4 ms    [User: 532.7 ms, System: 3.0 ms]
  Range (min … max):   529.6 ms … 540.8 ms    50 runs

Benchmark 3: test_otel_medium
  Time (mean ± σ):     549.6 ms ±   4.0 ms    [User: 536.7 ms, System: 12.8 ms]
  Range (min … max):   545.2 ms … 559.1 ms    50 runs

Benchmark 4: test_dd_medium
  Time (mean ± σ):     556.6 ms ±   3.9 ms    [User: 536.2 ms, System: 20.2 ms]
  Range (min … max):   550.6 ms … 569.0 ms    50 runs

Benchmark 5: test_troncos_medium
  Time (mean ± σ):     563.1 ms ±   6.0 ms    [User: 532.0 ms, System: 30.8 ms]
  Range (min … max):   557.6 ms … 585.4 ms    50 runs

Benchmark 6: test_troncold_medium
  Time (mean ± σ):     582.0 ms ±   7.7 ms    [User: 545.4 ms, System: 36.4 ms]
  Range (min … max):   573.1 ms … 614.0 ms    50 runs

Summary
  'test_noop' ran
    1.04 ± 0.01 times faster than 'test_base'
    1.06 ± 0.01 times faster than 'test_otel_medium'
    1.08 ± 0.01 times faster than 'test_dd_medium'
    1.09 ± 0.01 times faster than 'test_troncos_medium'
    1.13 ± 0.02 times faster than 'test_troncold_medium'
poetry add numpy matplotlib scipy -q
mkdir -p test/plots
poetry run python -m troncos_perf.offset test/res.json test/res_adj.json
poetry run python .stats/plot_whisker.py test/res_adj.json -o test/plots/whisker.png 2> /dev/null
poetry run python .stats/plot_histogram.py test/res_adj.json --type barstacked -o test/plots/histogram.png 2> /dev/null
poetry run python .stats/welch_ttest.py test/res_adj.json || true
The input file has to contain exactly two benchmarks
```

> **Note**: You can change the `TO_RUN` variable in the [Makefile](./Makefile) to run different tests!

