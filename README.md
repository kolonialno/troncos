<h1 align="center" style="border-bottom: 0">
  🪵<br>
  Troncos <br/>
</h1>

<p align="center">
    <em>
        Collection of Python logging, tracing and profiling tools
    </em>
    <br>
    <a href="https://github.com/kolonialno/troncos/actions?workflow=CI">
        <img src="https://github.com/kolonialno/troncos/actions/workflows/ci.yml/badge.svg" alt="CI status">
    </a>
    <a href="https://pypi.python.org/pypi/troncos">
        <img src="https://img.shields.io/pypi/v/troncos.svg">
    </a>
    <img src="https://img.shields.io/pypi/pyversions/troncos">
    <a href="https://github.com/kolonialno/troncos/blob/master/LICENSE">
        <img src="https://img.shields.io/github/license/kolonialno/troncos.svg">
    </a>
</p>

<!-- TOC -->
  * [Etymology](#etymology)
  * [Installation](#installation)
  * [Setup](#setup)
    * [Choosing an exporter](#choosing-an-exporter)
      * [gRPC](#grpc)
      * [http](#http)
    * [Import order](#import-order)
    * [Plain setup](#plain-setup)
    * [Starlette with uvicorn](#starlette-with-uvicorn)
    * [Django with gunicorn](#django-with-gunicorn)
  * [Logging](#logging)
    * [Structlog](#structlog)
  * [Tracing](#tracing)
    * [Tracing your code](#tracing-your-code)
      * [trace_function](#tracefunction)
      * [trace_block](#traceblock)
      * [trace_class](#traceclass)
      * [trace_module](#tracemodule)
      * [trace_ignore](#traceignore)
    * [Trace Propagation](#trace-propagation)
      * [Send context](#send-context)
      * [Receive context](#receive-context)
    * [Trace sampling](#trace-sampling)
    * [Trace debugging](#trace-debugging)
    * [Context detach exceptions](#context-detach-exceptions)
  * [Profiling](#profiling)
    * [Setup endpoint](#setup-endpoint)
    * [Enable scraping](#enable-scraping)
  * [Development](#development)
<!-- TOC -->

## Etymology

"Troncos" is the plural of the spanish word "Tronco", which translates to "trunk" or "log".

## Installation

```console
# With pip
$ pip install troncos

# With poetry (grpc trace exporter)
$ poetry add troncos -E grpc

# With poetry (http trace exporter)
$ poetry add troncos -E http
```

## Setup

> **NOTE**: It is a good idea to use a `settings.py`-file (or similar) as an authoritative source of variables (service name, environment, whether tracing is enabled or not, log level, etc). In this README we use `os.environ` for the sake of clarity.

### Choosing an exporter

To export your traces, you have to pick either `grpc` or `http`. Using `grpc` gives you significant performance gains. If you are running a critical service with high load in production, we recommend using `grpc`.

#### gRPC

```toml
[tool.poetry.dependencies]
troncos = {version="?", extras = ["grpc"]}
```

#### http

```toml
[tool.poetry.dependencies]
troncos = {version="?", extras = ["http"]}
```

> **Note**: You need to change the `TRACE_PORT` depending on your choice of protocol `http`/`grpc`.

### Import order

It is very important that you do **NOT** import `ddtrace` anywhere before you have initialized troncos! Troncos should give you a warning if this is the case.

### Plain setup

```python
from os import environ

from troncos.logs import init_logging_basic
from troncos.traces import init_tracing_basic, http_endpoint_from_env
from troncos.profiling import init_profiling_basic

init_logging_basic(
    level=environ.get("LOG_LEVEL", "INFO"),
    formatter=environ.get("LOG_FORMATTER", "cli")  # Use "logfmt" or "json" in production
)
init_tracing_basic(
    endpoint=http_endpoint_from_env("TRACE_HOST", "TRACE_PORT", "/v1/traces"),
    # endpoint_dd=http_endpoint_from_env("TRACE_DD_HOST", "TRACE_DD_PORT"),
    service_name="my_service",
    service_env=environ.get("ENVIRONMENT", "localdev"),
)
profiler = init_profiling_basic()

# Import all your other stuff ...
```

### Starlette with uvicorn

```python
from os import environ

from troncos.logs import init_logging_basic
from troncos.traces import init_tracing_basic, http_endpoint_from_env
from troncos.profiling import init_profiling_basic

init_logging_basic(
    level=environ.get("LOG_LEVEL", "INFO"),
    formatter=environ.get("LOG_FORMATTER", "cli")  # Use "logfmt" or "json" in production
)
init_tracing_basic(
    endpoint=http_endpoint_from_env("TRACE_HOST", "TRACE_PORT", "/v1/traces"),
    # endpoint_dd=http_endpoint_from_env("TRACE_DD_HOST", "TRACE_DD_PORT"),
    service_name="my_service",
    service_env=environ.get("ENVIRONMENT", "localdev"),
)
profiler = init_profiling_basic()

# Import all your other stuff ...

from fastapi import FastAPI
from troncos.frameworks.starlette.uvicorn import init_uvicorn_logging

app = FastAPI(title="my_service")
init_uvicorn_logging(
    app=app,
    log_access_ignored_paths=["/health", "/metrics"],
)
```

> **Note**: If you are running starlette but not calling `init_uvicorn_logging`, trace ids might not be logged.

### Django with gunicorn

To set up tracing you have to set up some gunicorn hooks. Create a `gunicorn/config.py` file in your project:

```python
from os import environ

from troncos.frameworks.gunicorn import post_request_trace, pre_request_trace
from troncos.traces import init_tracing_basic, http_endpoint_from_env


def post_fork(server, worker):
    init_tracing_basic(
        endpoint=http_endpoint_from_env("TRACE_HOST", "TRACE_PORT", "/v1/traces"),
        # endpoint_dd=http_endpoint_from_env("TRACE_DD_HOST", "TRACE_DD_PORT"),
        service_name="my_service",
        service_env=environ.get("ENVIRONMENT", "localdev"),
    )


def pre_request(worker, req):
    pre_request_trace(worker, req)


def post_request(worker, req, environ, resp):
    post_request_trace(worker, req, environ, resp)
```

Then when running gunicorn, specify what config file to use:

```console
gunicorn myapp.wsgi:application --config python:myapp.gunicorn.config ...
```

You have to manually configure logging in your `settings.py`. You should adhere to the principle described in [the logging section](#logging).

Make sure that you add the `TraceIdFilter` to all handlers. Your logging configuration should look roughly like this:

```python
from os import environ

LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "filters": {
        "trace_id": {"()": "troncos.logs.filters.TraceIdFilter"},
    },
    "formatters": {
        "cli": {"()": "troncos.logs.formatters.PrettyFormatter"},
        "json": {"()": "troncos.logs.formatters.JsonFormatter"},
        "logfmt": {"()": "troncos.logs.formatters.LogfmtFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": environ.get("LOG_FORMATTER", "logfmt"),
            "filters": ["trace_id"],
        }
    },
    "loggers": {
        "interno": {"handlers": ["console"], "level": environ.get("LOG_LEVEL", "INFO")},
        "django": {"handlers": ["console"], "level": environ.get("LOG_LEVEL", "INFO")},
        "django.server": {
            "handlers": ["console"],
            "level": environ.get("LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "gunicorn.error": {
            "handlers": ["console"], 
            "level": environ.get("LOG_LEVEL", "INFO")
        },
    },
}
```

## Logging

More often then not, you want all loggers to propagate their records to the `root` logger and make the `root` logger handle everything. Depending on your project, this might require some additional configuration. Looking at the [python logging flow](https://docs.python.org/3/howto/logging.html#logging-flow) can help you understand how child loggers can propagate records to the `root` logger. Note that propagating to `root` is the default behaviour.

There is a nice helper function that will print all loggers in troncos called `print_loggers`:

```python
from troncos.logs import print_loggers

print_loggers(verbose=False)  # To visualize loggers
```

After calling the `init_logging_basic` function in a simple project you should see something like this printed `print_loggers`:

```console
Loggers:
[ root                 ] logging.RootLogger LEVEL: 20 PROPAGATE: True
  └ HANDLER logging.StreamHandler  LEVEL: 20
    └ FILTER troncos.logs.filters.TraceIdFilter
    └ FORMATTER troncos.logs.formatters.PrettyFormatter
```

So in general, after the initial setup you can use any logger and that will propagate the log record to root:

```python
import logging

logging.getLogger("my.random.logger").info("Root will handle this record")
```

### Structlog

You can substitute `init_logging_basic` with `init_logging_structlog` to setup structlog:

```python
from os import environ
from troncos.frameworks.structlog.setup import init_logging_structlog

init_logging_structlog(
    level=environ.get("LOG_LEVEL", "INFO"),
    formatter=environ.get("LOG_FORMATTER", "cli"),  # Use "logfmt" in production
)
```

Alternatively you can add trace injection into your own structlog setup:

```python
import structlog
from troncos.frameworks.structlog.processors import trace_injection_processor

structlog.configure(
    processors=[
       trace_injection_processor,
    ],
)
```

> **NOTE**: This only adds trace information to your logs if you have set up tracing in your project.

## Tracing

### Tracing your code

After initializing tracing in your project you can use different methods to trace your code.

#### trace_function

This decorator adds tracing to a function. You can supply a tracer provider, if none is supplied, the global tracer provider will be used:

```python
from troncos.traces.decorate import trace_function

@trace_function
def myfunc1():
    return "This will be traced"

@trace_function(service="my_custom_service")
def myfunc2():
    return "This will be traced as my_custom_service"
```

#### trace_block

Trace using a with statement. You can supply a tracer provider, if none is supplied, the global tracer provider will be used.

```python
from troncos.traces.decorate import trace_block

with trace_block(name="action", resource="thing", attributes={"some": "attribute"}):
    print("... do an action to a thing...")
```

#### trace_class

This decorator adds a tracing decorator to every method of the decorated class. If you don't want some methods to be traced, you can add the [trace_ignore](#traceignore) decorator to them. You can supply a tracer provider, if none is supplied, the global tracer provider will be used:

```python
from troncos.traces.decorate import trace_class, trace_ignore

@trace_class
class MyClass1:

    def m1(self):
        return "This will be traced"

    @trace_ignore
    def m2(self):
        return "This will not traced"


@trace_class(service="my_custom_service")
class MyClass2:

    def m3(self):
        return "This will be traced as my_custom_service"
```

#### trace_module

This function adds a tracing decorator to every function of the calling module. If you don't want some functions to be traced, you can add the [trace_ignore](#traceignore) decorator to them. You can supply a tracer provider, if none is supplied, the global tracer provider will be used:

```python
from troncos.traces.decorate import trace_ignore, trace_module

def my_function():
    return "This func will be traced"

@trace_ignore
def my_function():
    return "This func will not be traced"

trace_module()
```

#### trace_ignore

A decorator that will make [trace_class](#traceclass) and [trace_module](#tracemodule) ignore the decorated function/method.

### Trace Propagation

If you want to propagate your trace to the next service, you need to send/receive special headers with your request/message. If you are using plain `requests` that should be handled automatically by troncos. Here is how you do this manually:

#### Send context

```python
from troncos.traces.propagation import get_propagation_value

# Get header value
value = get_propagation_value()

# Send it somewhere
```

or

```python
from troncos.traces.propagation import add_context_to_dict

some_dict = {}

# Add propagation headers to dict
add_context_to_dict(some_dict)

# Send it somewhere
```

#### Receive context

Again, troncos should in most cases do this automatically for you, but here is how you do it manually:

```python
from troncos.traces.propagation import activate_context_from_dict
from troncos.traces.decorate import trace_block

some_dict = {} 
activate_context_from_dict(some_dict)

with trace_block("my_block"):
    print("... do something ...")
```

### Trace sampling

Set these variables to turn on trace sampling:

```console
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.05
DD_TRACE_SAMPLE_RATE=0.05
```

### Trace debugging

You can enable trace debugging by setting the environmental variable `OTEL_TRACE_DEBUG=true`. That will print all spans to the console. If you would rather get the spans in a file you can also provide the variable `OTEL_TRACE_DEBUG_FILE=/tmp/traces`.

### Context detach exceptions

We have observed the following exception in some services:

```console
Traceback (most recent call last):
  File "opentelemetry/context/__init__.py", line 157, in detach
    _RUNTIME_CONTEXT.detach(token)  # type: ignore
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "opentelemetry/context/contextvars_context.py", line 50, in detach
    self._current_context.reset(token)  # type: ignore
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
ValueError: <Token> was created in a different Context
```

This is caused by a [bug in OTEL](https://github.com/open-telemetry/opentelemetry-python/issues/2606). In these cases the first (or root) span of an incoming starlette request fails to detach its context when it finishes. This does not seem to affect tracing, nor to cause any memory leaks. It just floods the logs with exceptions.

The solution is to set the environmental variable `TRONCOS_OMIT_ROOT_CONTEXT_DETACH=true`. You can also set up the logging filter `ContextDetachExceptionDropFilter` to suppress those exceptions in the logs.

## Profiling

> **Warning**: There is a [bug in ddtrace](https://github.com/DataDog/dd-trace-py/issues/4899) that causes a memory leak when running the profiler with python 3.11!

### Setup endpoint

Simply add a `/debug/pprof` endpoint that returns the profile:

```python
from fastapi import FastAPI
from starlette.responses import Response
from troncos.profiling import init_profiling_basic

profiler = init_profiling_basic()

app = FastAPI(title="my_service")

@app.get("/debug/pprof", response_model=str)
async def debug_pprof() -> Response:
    content, headers = profiler()
    return Response(content=content, headers=headers)
```

You can verify that your setup works with the [pprof](https://github.com/google/pprof) cli:

```console
$ pprof -http :6060 "http://localhost:8080/debug/pprof"
```

> **Note**: You will get an empty string from `profiler()` until the first profile has been collected.

### Enable scraping

When you deploy your application, be sure to use the custom oda annotation for scraping:

```yaml
annotations:
    phlare.oda.com/port: "8080"
    phlare.oda.com/scrape: "true"
```

## Development

When developing troncos you should be constantly aware of the fact that under no circumstances should you import `ddtrace` into your module. That would cause the tracer to initialize with default values that would not change when the user initializes the tracer.

For this reason, if you need to use any parts of `ddtrace` in your code, consider using the `_ddlazy` module, that gives you access lazily. If that does not satisfy your requirements you can always import `ddtrace` in your functions (not at the top of your module).
