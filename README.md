<h1 align="center" style="border-bottom: 0">
  🪵<br>
  Troncos <br/>
</h1>

<p align="center">
    <em>
        Collection of Python logging and tracing tools
    </em>
    <br>
    <a href="https://github.com/kolonialno/troncos/actions?workflow=CI">
        <img src="https://github.com/kolonialno/troncos/actions/workflows/ci.yml/badge.svg" alt="CI status">
    </a>
    <a href="https://pypi.python.org/pypi/troncos">
        <img src="https://img.shields.io/pypi/v/troncos.svg" alt="Troncos version">
    </a>
    <img src="https://img.shields.io/pypi/pyversions/troncos" alt="Supported Python version">
    <a href="https://github.com/kolonialno/troncos/blob/master/LICENSE">
        <img src="https://img.shields.io/github/license/kolonialno/troncos.svg" alt="licenece">
    </a>
</p>

<!-- TOC -->
- [Etymology](#etymology)
- [Installation](#installation)
- [Tracing](#tracing)
- [Profiling](#profiling)
- [Logging](#logging)
<!-- TOC -->

## Etymology

"Troncos" is the plural of the spanish word "Tronco", which translates to "trunk" or "log".

## Installation

```console
# With pip
pip install troncos
```

## Tracing

Troncos is designed to take advantage of `ddtrace` made by DataDog.

The ddtrace docs can be found [here](https://ddtrace.readthedocs.io/en/stable/).

[Best practices for traces](https://grafana.com/docs/tempo/latest/operations/best-practices/#naming-conventions-for-span-and-resource-attributes) is a good guide to get started.

### Span vs resource attributes

- A `span attribute` is a key/value pair that provides context for its span.
- A `resource attribute` is a key/value pair that describes the context of how the span was collected.

For more information, read the [Attribute and Resource](https://opentelemetry.io/docs/specs/otel/overview/) sections in the OpenTelemetry specification.

### Enabling the tracer

 Run `configure_tracer` to send spans to Tempo and configure ddtrace as usual.

`TRACE_HOST` is usually the hostname of a trace collector, `TRACE_PORT` is usually 4318
when Grafana Alloy is used to collect spans using HTTP.

```python
import ddtrace
from ddtrace.trace import tracer

from troncos.tracing import configure_tracer, Exporter

def setup_tracing():
    # Configure the ddtrace tracer to send traces to Tempo.
    configure_tracer(
        service_name='SERVICE_NAME',
        exporter=Exporter(
            # Usually obtained from env variables.
            host = "otel-collector.monitoring.svc.cluster.local",
        ),
        resource_attributes={
            "app": "app",
            "component": "component",
            "role": "role",
            "tenant": "tenant",
            "owner": "owner",
            "version": "version",
        },
        enabled=True,
    )

    # Configure tracer as described in the ddtrace docs.
    ddtrace.config.django["service_name"] = 'SERVICE_NAME'
    # These are added as span attributes
    tracer.set_tags(
        tags={
            "key": "value",
        }
    )

    # Patch third-party modules
    ddtrace.patch(django=True)
```

Enabling tracing must be done after any subprocesses have started, or
it may cause deadlocks between processes. Dropping the code into
e.g. settings.py might be problematic.

Examples include in Celery signals, gunicon fork events, and so on.

```python
from typing import Any

from celery import signals

# gunicorn:
def post_fork(server: Any, worker: Any) -> None:
    setup_tracing()

# celery master process
@signals.worker_ready.connect  # type: ignore
def worker_ready(**kwargs: Any) -> None:
    setup_tracing()

# celery worker process
@signals.worker_process_init.connect  # type: ignore
def worker_process_init_handler(**kwargs: Any) -> None:
    setup_tracing()

# celery beat
@signals.beat_init.connect  # type: ignore
def beat_init_handler(**kwargs: Any) -> None:
    setup_tracing()

# manage.py
def main() -> None:
    setup_tracing()

    # ...
    execute_from_command_line(sys.argv)
```

ddtrace also uses env variables to configure the service name, environment and version etc.

Add the following environment variables to your application.

```console
DD_ENV="{{ environment }}"
DD_SERVICE="{{ app }}"
DD_VERSION="{{ version }}"
# tracecontext/w3c is usually used to propagate distributed traces across services.
DD_TRACE_PROPAGATION_STYLE_EXTRACT="tracecontext"
DD_TRACE_PROPAGATION_STYLE_INJECT="tracecontext"
```

#### Debugging during development

By setting the environment variable `OTEL_TRACE_DEBUG=True` you will enable traces
to be printed to `stdout` via the ConsoleSpanExporter as well as through http/grpc.
Also specifying `OTEL_TRACE_DEBUG_FILE=/some/file/path` will output traces to the
specified file path instead of the console/stdout.

### Using the GRPC span exporter

Using the GRPC span exporter gives you significant performance gains.
If you are running a critical service with high load in production,
we recommend using GRPC.

The port is usually `4317` when the Grafana agent is used to collect
spans using GRPC.

```console
uv add "troncos[grpc]"
```

or

```toml
[project]
dependencies = ["troncos[grpc]"]
```

```python
from troncos.tracing import configure_tracer, Exporter


configure_tracer(
    service_name='SERVICE_NAME',
    exporter=Exporter(
        host = "127.0.0.1", # Usually obtained from env variables.
        port = "4317",
    ),
    enabled=True,
)
```

### Setting headers for the exporter

```python
from troncos.tracing import configure_tracer, Exporter


configure_tracer(
    service_name='SERVICE_NAME',
    exporter=Exporter(
        host = "127.0.0.1", # Usually obtained from env variables.
        headers={"my": "header"},
    ),
    enabled=True,
)
```

### Instrument your code

Manual instrumentation of your code is described in the [ddtrace docs](https://ddtrace.readthedocs.io/en/stable/basic_usage.html#manual-instrumentation).

### Verifying tracing after a dependency upgrade

Troncos bridges `ddtrace` to OpenTelemetry, which means it depends on internals
of both libraries. A `ddtrace` or `opentelemetry` bump can therefore break trace
export without breaking any import.

`tests/tracing/test_e2e.py` exists to catch that. It drives only the public API
(`configure_tracer`, `Exporter`, the decorators), exports to a local collector,
and decodes the OTLP protobuf that arrives, asserting on each translated field:
resource attributes, span name, parent/child linkage, span kind, numeric span
tags, and exception events. Run it after any dependency upgrade:

```console
mise run test
# or, without the task runner:
pytest tests/tracing/test_e2e.py -v
```

> **Note**: troncos exports **traces** only; it has no OTLP metrics pipeline.
> The "metrics" it handles are ddtrace's numeric span tags (`Span.set_metric`),
> which become typed OTLP span attributes.

### Performance regression tests

`tests/tracing/test_perf.py` measures the same span workload through several
interchangeable implementations, so their cost can be compared directly:

| Arm | What it measures |
| --- | --- |
| `ddtrace` | ddtrace instrumentation exporting msgpack through its own `AgentWriter` |
| `opentelemetry-http` | the OpenTelemetry SDK over OTLP/HTTP, no ddtrace involved |
| `troncos-http` | ddtrace instrumentation plus troncos' translation and OTLP/HTTP export |
| `opentelemetry-grpc` | the OpenTelemetry SDK over OTLP/gRPC |
| `troncos-grpc` | troncos over OTLP/gRPC, the transport the Grafana agent receives on at 4317 |

The suffix is the OTLP transport, so `troncos-http` and `troncos-grpc` are the
same implementation over 4318 and 4317. `ddtrace` has no suffix because it
speaks the Datadog agent protocol rather than OTLP, so it has no transport to
choose.

Every arm exports to a local endpoint, so the comparison is between encoding
and translation costs rather than between exporting and not exporting. Each
gate compares troncos against the arm on the *same* transport, so the ratio
measures translation cost rather than the difference between HTTP and gRPC.

The `-grpc` arms need the optional `grpc` extra. Without it they drop out of the
arm list and their gate skips, so the HTTP gates keep working.

Three ratio assertions run as part of the normal test suite and fail if troncos
becomes disproportionately expensive. Ratios are used rather than absolute
timings because they stay meaningful on a shared CI runner.

Each arm is timed over 25 rounds of 50 iterations, after 5 warmup rounds. The
printed table reports the mean and its relative spread. The gates compare
medians, because roughly 1 round in 60 runs long, usually alongside a
generation-2 GC pass, and the mean follows that tail while the median does not.
Timing all five arms takes about 1.2 seconds.

Print the current numbers:

```console
mise run perf
# or, without the task runner:
pytest tests/tracing/test_perf.py -v -s
```

Record and compare absolute benchmarks (skipped during `mise run test`):

```console
mise run benchmark
BENCH_CMP=0001 mise run benchmark-cmp
# or, without the task runner:
pytest tests --benchmark-enable --benchmark-only --benchmark-autosave
pytest tests --benchmark-enable --benchmark-only --benchmark-compare=0001 \
  --benchmark-compare-fail=mean:25%
```

Choose which implementations to measure, and loosen the gates, with environment
variables:

```console
TRONCOS_PERF_ARMS=opentelemetry-http,troncos-http mise run perf
TRONCOS_PERF_ARMS=opentelemetry-grpc,troncos-grpc mise run perf
TRONCOS_PERF_MAX_DDTRACE_RATIO=15 mise run perf
TRONCOS_PERF_MAX_OPENTELEMETRY_HTTP_RATIO=3 mise run perf
TRONCOS_PERF_MAX_OPENTELEMETRY_GRPC_RATIO=3 mise run perf
```

If a gate flakes on a contended runner, raise its limit rather than removing
the check.

### Add tracing context to your log

Adding the tracing context to your log makes it easier to find relevant traces in Grafana.
Troncos include a Structlog processor designed to do this.

```python
import structlog

from troncos.contrib.structlog.processors import trace_injection_processor

structlog.configure(
    processors=[
        trace_injection_processor,
    ],
)
```

### Logging of major actions in your application

Finding relevant traces in Grafana can be difficult. One way to make finding the relevant traces
easier it to log every major action in your application. This typically means logging every
incoming HTTP request to your server or every task executed by your Celery worker.

The structlog processor above needs to be enabled before logging your major actions is relevant.

#### ASGI middleware

Log ASGI requests.

```python
from starlette.applications import Starlette

from troncos.contrib.asgi.logging.middleware import AsgiLoggingMiddleware

application = AsgiLoggingMiddleware(Starlette())
```

#### Django middleware

Log Django requests. This is not needed if you run Django with ASGI and use the
ASGI middleware.

```python
MIDDLEWARE = [
    "troncos.contrib.django.logging.middleware.DjangoLoggingMiddleware",
    ...
]
```

#### Celery signals

`
Log Celery tasks. Run the code bellow when you configure Celery.

```python
from troncos.contrib.celery.logging.signals import (
    connect_troncos_logging_celery_signals,
)

connect_troncos_logging_celery_signals()
```

## Profiling

Troncos ships a continuous profiler that pushes to [Grafana Pyroscope](https://grafana.com/docs/pyroscope/latest/),
built on Grafana's own [`pyroscope-io`](https://github.com/grafana/pyroscope-python) SDK.
Sampling is done by [py-spy](https://github.com/benfred/py-spy) in native threads that
read the interpreter's memory directly. They never execute Python or take the GIL, so
they do not show up in `threading.active_count()` and do not contend with your code.

The SDK is a compiled wheel of several megabytes, so it is an extra:

```console
uv add "troncos[profiling]"
```

or

```toml
[project]
dependencies = ["troncos[profiling]"]
```

### Enabling the profiler

`PYROSCOPE_HOST` and `PYROSCOPE_PORT` are usually the hostname and port of Pyroscope
itself, or of a Grafana Alloy instance relaying to it. The port is `4040` by default.

```python
from troncos.profiling import configure_profiler, Exporter


def setup_profiling() -> None:
    configure_profiler(
        service_name='SERVICE_NAME',
        exporter=Exporter(
            # Usually obtained from env variables.
            host="pyroscope.monitoring.svc.cluster.local",
        ),
        tags={
            "role": "web",
        },
        enabled=True,
    )
```

`service_name` is required, but it falls back to the ddtrace service name, so it
can be omitted when `DD_SERVICE` is set or tracing is already configured. There is
no default: Pyroscope groups profiles by this name, so troncos raises rather than
invent one. Profiles are tagged with the service name, hostname,
`ddtrace` env and version, and any tags already set on the tracer, which lets a
profile be filtered by the same labels as its traces.

Start the profiler after any subprocesses have forked. The SDK is
[not fork safe](https://grafana.com/docs/pyroscope/latest/configure-client/language-sdks/python/)
once its sampling threads are running. This is the same constraint tracing has, so
the same hooks work:

```python
from typing import Any

from celery import signals

# gunicorn:
def post_fork(server: Any, worker: Any) -> None:
    setup_profiling()

# celery master process
@signals.worker_ready.connect  # type: ignore
def worker_ready(**kwargs: Any) -> None:
    setup_profiling()
```

Pass `enabled=False` to turn profiling off. Nothing is imported in that case, so a
service that gates profiling on an env flag runs without the extra installed.

### Authenticating against Grafana Cloud

```python
from troncos.profiling import configure_profiler, Exporter


def setup_grafana_cloud_profiling() -> None:
    configure_profiler(
        service_name='SERVICE_NAME',
        exporter=Exporter(
            scheme="https",
            host="profiles-prod-001.grafana.net",
            port="443",
            basic_auth_username="123456",
            basic_auth_password="glc_token",
        ),
    )
```

### What is profiled

By default the profiler samples wall clock time across every thread, not just
on-CPU time in the thread holding the GIL. A request blocked on a database shows
up, which is usually what you are looking for. Both are opposite to the SDK's
own defaults, so set `oncpu=True` if you want CPU time only.

Everything else the SDK takes is on `ProfilerOptions`. Field names match the
arguments of `pyroscope.configure`, so Grafana's
[SDK documentation](https://grafana.com/docs/pyroscope/latest/configure-client/language-sdks/python/)
describes them directly.

```python
from troncos.profiling import configure_profiler, Exporter, ProfilerOptions, LineNo


def setup_detailed_profiling() -> None:
    configure_profiler(
        service_name='SERVICE_NAME',
        exporter=Exporter(host="pyroscope.monitoring.svc.cluster.local"),
        options=ProfilerOptions(
            sample_rate=200,          # Samples per second, default 100.
            upload_interval=15,       # Seconds between uploads, default 10.
            oncpu=True,               # On-CPU time only, rather than wall clock.
            report_thread_name=True,  # Split the flamegraph by thread.
            line_no=LineNo.FIRST,     # Attribute to the first line of a frame.
            mem_enabled=True,         # Also collect heap profiles.
        ),
    )
```

The options are a frozen dataclass, so a typo is caught by your type checker
rather than accepted and ignored. Values that Pyroscope would take and then do
nothing with raise `ValueError` on construction:

```python
from troncos.profiling import ProfilerOptions

try:
    ProfilerOptions(sample_rate=0)
except ValueError as error:
    print(error)
```

Turning off both collectors is rejected on the same grounds. Profiling is
switched off with `configure_profiler(enabled=False)`, which imports nothing, so
a configuration that starts a profiler in order to collect nothing is a mistake.

### Scraping is not supported

Troncos pushes profiles. It does not serve a `/debug/pprof` endpoint for Pyroscope
or Grafana Alloy to scrape, because Python has no maintained way to produce pprof
bytes in process. Point Pyroscope at your service through push instead.

### Coming from troncos v6

Profiling was absent in v7. If you are upgrading from v6:

- `start_py_spy_profiler(server_address=...)` becomes
  `configure_profiler(exporter=Exporter(...))`.
- Add the extra. `pyroscope-io` is no longer installed for everyone.
- Pass credentials as `Exporter(basic_auth_username=..., basic_auth_password=...)`
  or `Exporter(headers=...)`. The SDK dropped its `auth_token` argument.
- The pprof endpoint, `troncos.profiling.auto` and the ASGI, Django and Starlette
  profiling views have no replacement.

## Logging

Troncos is not designed to take control over your logger. But, we do include logging
related tools to make instrumenting your code easier.

### Configure Structlog

Troncos contains a helper method that lets you configure Structlog.

First, run `uv add structlog` to install structlog in your project.

You can now replace your existing logger config with

```python
from troncos.contrib.structlog import configure_structlog

configure_structlog(format="json", level="INFO")
```

### Adding tracing context to your log

Troncos has a Structlog processor that can be used to add the `span_id` and `trace_id`
properties to your log. More information can be found in the [Tracing](#tracing)
section in this document. This is used by the `configure_structlog` helper method
by default.

### Request logging middleware

Finding the relevant traces in Tempo and Grafana can be difficult. The request logging
middleware exist to make it easier to connect HTTP requests to traces. More information
can be found in the [Tracing](#tracing) section in this document.
