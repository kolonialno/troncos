"""Performance tests for the troncos trace pipeline.

Arm names carry the OTLP transport as a suffix: `troncos-http` and
`troncos-grpc` are the same implementation over HTTP (4318) and gRPC (4317), and
each gate compares troncos against the arm on the same transport. The `-grpc`
arms need the optional `grpc` extra; without it they drop out of the arm list and
the gate that needs them skips.

The ratio tests always run and are the regression gate: ratios between arms stay
meaningful on a shared CI runner where absolute timings do not. The
pytest-benchmark tests record absolute timings and are opt-in via
`make benchmark`.

Each arm is timed over GATE_ROUNDS rounds and summarised twice. The reported
number is the mean with its relative spread, because that is the number worth
quoting. The gates compare medians, because the round distribution has a right
tail: measured over 750 rounds, 12 ran more than 1.25x their arm's median and 10
of those coincided with a generation-2 GC pass. The tail hits every arm about
equally, so it is the runner rather than any one implementation. The mean
follows those rounds and the median does not, which makes the median the more
reproducible basis for a gate: over 12 trials the run-to-run standard deviation
of the ratio was 0.036 on medians against 0.045 on means.

    TRONCOS_PERF_ARMS=opentelemetry-http,troncos-http make perf
    TRONCOS_PERF_MAX_DDTRACE_RATIO=6 make perf
"""

import os
import statistics
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest

from tests.tracing.perf import (
    NullCollector,
    build_arm,
    selected_arms,
    spans_per_iteration,
)

ITERATIONS = 50

# 25 rounds rather than a handful, because 7 was not enough to settle: the
# run-to-run standard deviation of the gate ratio drops from 0.062 to 0.036 on
# medians, and from 0.094 to 0.045 on means. Timing all five arms costs about
# 1.2s, which the normal test run can afford.
GATE_ROUNDS = 25
GATE_WARMUP_ROUNDS = 5

# Every gate compares troncos against an arm using the same transport, so the
# ratios measure translation and encoding rather than the difference between
# HTTP and gRPC. Limits are roughly 2x what an unloaded machine measures, to
# catch order-of-magnitude regressions without flaking on a busy runner.
DEFAULT_MAX_DDTRACE_RATIO = 6.0
DEFAULT_MAX_OPENTELEMETRY_HTTP_RATIO = 2.5
DEFAULT_MAX_OPENTELEMETRY_GRPC_RATIO = 2.5


def _float_from_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    return float(raw)


@pytest.fixture(scope="module")
def collector() -> Iterator[NullCollector]:
    """One collector for the module, matching _timings_cache's scope.

    Function-scoped, every test after the first would bind two more ports and
    start two more servers for timings that were already cached against the
    first test's collector.
    """
    instance = NullCollector().start()
    try:
        yield instance
    finally:
        instance.stop()


@dataclass(frozen=True)
class ArmTiming:
    """Seconds per span for one arm, summarised over GATE_ROUNDS rounds."""

    mean: float
    median: float
    rounds: int
    relative_spread: float
    """Standard deviation as a fraction of the mean."""


def _time_arm(name: str, collector: NullCollector) -> ArmTiming:
    """Time `name` over several rounds and summarise the per-span cost."""
    arm = build_arm(name)
    arm.setup(collector)
    before = collector.request_count
    try:
        for _ in range(GATE_WARMUP_ROUNDS):
            arm.run(ITERATIONS)

        rounds = []
        for _ in range(GATE_ROUNDS):
            start = time.perf_counter()
            arm.run(ITERATIONS)
            rounds.append(time.perf_counter() - start)
    finally:
        arm.teardown()

    assert collector.request_count > before, (
        f"the {name} arm never reached the collector, so its timing excludes "
        "the export it is supposed to measure"
    )

    spans = ITERATIONS * spans_per_iteration()
    per_span = [seconds / spans for seconds in rounds]
    mean = statistics.fmean(per_span)
    return ArmTiming(
        mean=mean,
        median=statistics.median(per_span),
        rounds=len(per_span),
        relative_spread=statistics.stdev(per_span) / mean,
    )


@pytest.fixture(scope="module")
def _timings_cache() -> dict[str, ArmTiming]:
    return {}


def _timings(
    collector: NullCollector, cache: dict[str, ArmTiming]
) -> dict[str, ArmTiming]:
    for name in selected_arms():
        if name not in cache:
            cache[name] = _time_arm(name, collector)
    return cache


def test_all_selected_arms_produce_a_timing(
    collector: NullCollector, _timings_cache: dict[str, ArmTiming]
) -> None:
    timings = _timings(collector, _timings_cache)

    assert set(timings) >= set(selected_arms())
    for name, timing in timings.items():
        assert timing.rounds == GATE_ROUNDS, f"{name} was not timed fully"
        assert timing.median > 0, f"{name} reported a zero cost"
        # Bounds the same statistic the gates compare, so a pathological tail
        # cannot pass one check and fail the other. More than a millisecond per
        # span means a real network round trip landed on the measured path.
        assert timing.median < 1e-3, (
            f"{name} took {timing.median * 1e6:.1f}us per span, "
            "which suggests the collector ended up on the measured path"
        )


def test_troncos_http_overhead_over_ddtrace_is_bounded(
    collector: NullCollector, _timings_cache: dict[str, ArmTiming]
) -> None:
    if not {"ddtrace", "troncos-http"} <= set(selected_arms()):
        pytest.skip("needs both the 'ddtrace' and 'troncos-http' arms")

    timings = _timings(collector, _timings_cache)
    ratio = timings["troncos-http"].median / timings["ddtrace"].median
    limit = _float_from_env("TRONCOS_PERF_MAX_DDTRACE_RATIO", DEFAULT_MAX_DDTRACE_RATIO)

    assert ratio <= limit, (
        f"troncos is {ratio:.2f}x slower per span than ddtrace's own exporter "
        f"(limit {limit:.2f}x). "
        f"ddtrace={timings['ddtrace'].median * 1e6:.2f}us/span, "
        f"troncos-http={timings['troncos-http'].median * 1e6:.2f}us/span"
    )


def test_troncos_http_overhead_over_opentelemetry_http_is_bounded(
    collector: NullCollector, _timings_cache: dict[str, ArmTiming]
) -> None:
    if not {"opentelemetry-http", "troncos-http"} <= set(selected_arms()):
        pytest.skip("needs both the 'opentelemetry-http' and 'troncos-http' arms")

    timings = _timings(collector, _timings_cache)
    ratio = timings["troncos-http"].median / timings["opentelemetry-http"].median
    limit = _float_from_env(
        "TRONCOS_PERF_MAX_OPENTELEMETRY_HTTP_RATIO",
        DEFAULT_MAX_OPENTELEMETRY_HTTP_RATIO,
    )

    assert ratio <= limit, (
        f"troncos is {ratio:.2f}x slower per span than the OpenTelemetry SDK "
        f"over HTTP (limit {limit:.2f}x). "
        f"opentelemetry-http="
        f"{timings['opentelemetry-http'].median * 1e6:.2f}us/span, "
        f"troncos-http={timings['troncos-http'].median * 1e6:.2f}us/span"
    )


def test_troncos_grpc_overhead_over_opentelemetry_grpc_is_bounded(
    collector: NullCollector, _timings_cache: dict[str, ArmTiming]
) -> None:
    """The same gate as above, on the transport Alloy usually receives on.

    Compared against the OpenTelemetry SDK over gRPC rather than over HTTP, so a
    regression in troncos' translation shows up while the cost difference
    between the two transports cancels out.
    """
    if not {"opentelemetry-grpc", "troncos-grpc"} <= set(selected_arms()):
        pytest.skip("needs both the 'opentelemetry-grpc' and 'troncos-grpc' arms")

    timings = _timings(collector, _timings_cache)
    ratio = timings["troncos-grpc"].median / timings["opentelemetry-grpc"].median
    limit = _float_from_env(
        "TRONCOS_PERF_MAX_OPENTELEMETRY_GRPC_RATIO",
        DEFAULT_MAX_OPENTELEMETRY_GRPC_RATIO,
    )

    assert ratio <= limit, (
        f"troncos is {ratio:.2f}x slower per span than the OpenTelemetry SDK "
        f"over gRPC (limit {limit:.2f}x). "
        f"opentelemetry-grpc="
        f"{timings['opentelemetry-grpc'].median * 1e6:.2f}us/span, "
        f"troncos-grpc={timings['troncos-grpc'].median * 1e6:.2f}us/span"
    )


def test_report_arm_timings(
    collector: NullCollector,
    _timings_cache: dict[str, ArmTiming],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Print the comparison table so a CI log shows the actual numbers."""
    timings = _timings(collector, _timings_cache)
    baseline = min(timing.median for timing in timings.values())
    rounds = next(iter(timings.values())).rounds

    lines = [
        "",
        f"per-span cost by arm over {rounds} rounds (lower is better). "
        "The gates compare medians:",
        f"  {'arm':<20}{'mean':>12}{'spread':>10}{'median':>12}{'vs fastest':>12}",
    ]
    for name, timing in sorted(timings.items(), key=lambda item: item[1].median):
        lines.append(
            f"  {name:<20}"
            f"{timing.mean * 1e6:9.2f} us"
            f"{timing.relative_spread:10.1%}"
            f"{timing.median * 1e6:9.2f} us"
            f"{timing.median / baseline:11.2f}x"
        )

    with capsys.disabled():
        print("\n".join(lines))

    assert timings


@pytest.mark.benchmark(group="span-pipeline")
@pytest.mark.parametrize("arm_name", selected_arms())
def test_benchmark_span_pipeline(
    benchmark: Callable[..., None], collector: NullCollector, arm_name: str
) -> None:
    arm = build_arm(arm_name)
    arm.setup(collector)
    try:
        benchmark(arm.run, ITERATIONS)
    finally:
        arm.teardown()
