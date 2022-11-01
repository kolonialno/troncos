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
        <img src="https://img.shields.io/pypi/v/troncos.svg">
    </a>
    <img src="https://img.shields.io/pypi/pyversions/troncos">
    <a href="https://github.com/kolonialno/troncos/blob/master/LICENSE">
        <img src="https://img.shields.io/github/license/kolonialno/troncos.svg">
    </a>
</p>

<!-- TOC -->
  * [Installation](#installation)
  * [Etymology](#etymology)
  * [Setup](#setup)
    * [Plain](#plain)
    * [Starlette with uvicorn](#starlette-with-uvicorn)
    * [Django with gunicorn](#django-with-gunicorn)
    * [Using the grpc exporter](#using-the-grpc-exporter)
  * [Logging](#logging)
    * [Structlog](#structlog)
  * [Tracing](#tracing)
    * [trace_function](#trace_function)
    * [trace_block](#trace_block)
    * [trace_class](#trace_class)
    * [trace_module](#trace_module)
    * [trace_ignore](#trace_ignore)
    * [Other instrumentors for tracing](#other-instrumentors-for-tracing)
  * [Trace Propagation](#trace-propagation)
    * [Send context](#send-context)
      * [Requests](#requests)
      * [Send manually](#send-manually)
    * [Receive context](#receive-context)
      * [Using troncos middleware](#using-troncos-middleware)
      * [Receive manually](#receive-manually)
  * [Trace sampling](#trace-sampling)
<!-- TOC -->

## Installation

```console
# With pip
$ pip install troncos

# With poetry
$ poetry add troncos
```

## Etymology

"Troncos" is the plural of the spanish word "Tronco", which translates to "trunk" or "log".

## Setup

> **NOTE**: It is a good idea to use a `settings.py`-file (or similar) as an authoritative source of variables (service name, environment, whether tracing is enabled or not, log level etc.)

### Plain

Setting up logging and tracing requires some code that lives as close to the invocation of the application as possible (like in an entrypoint).

```python
from os import environ

from troncos.logs import init_logging_basic
from troncos.traces import init_tracing_basic, http_endpoint_from_env

init_logging_basic(
    level=environ.get("LOG_LEVEL", "INFO"),
    formatter=environ.get("LOG_FORMATTER", "cli")  # Use "logfmt" or "json" in k8s
)

init_tracing_basic(
    endpoint=http_endpoint_from_env("TRACE_HOST", "TRACE_PORT", "/v1/traces"),
    exporter_type="http",  # Can also be grpc
    attributes={
        "environment": environ.get("ENVIRONMENT", "localdev"),
        "service.name": "myservice",
    }
)

# Add other instrumentors here, like:
# RequestsInstrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
#     "service.name": "requests",
# }))
```

### Starlette with uvicorn

```python
from os import environ
from fastapi import FastAPI
from opentelemetry.instrumentation.requests import RequestsInstrumentor

from troncos.frameworks.starlette.uvicorn import init_uvicorn_observability
from troncos.logs import init_logging_basic
from troncos.traces import init_tracing_basic, init_tracing_provider, http_endpoint_from_env

init_logging_basic(
    level=environ.get("LOG_LEVEL", "INFO"),
    formatter=environ.get("LOG_FORMATTER", "cli")  # Use "logfmt" or "json" in k8s
)

init_tracing_basic(
    endpoint=http_endpoint_from_env("TRACE_HOST", "TRACE_PORT", "/v1/traces"),
    exporter_type="http",  # Can also be grpc
    attributes={
        "environment": environ.get("ENVIRONMENT", "localdev"),
        "service.name": "myservice",
    }
)

# Add other instrumentors here, like:
RequestsInstrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
    "service.name": "requests",
}))

app = FastAPI(title="myapp")

init_uvicorn_observability(
    app=app,
    log_access_ignored_paths=["/health", "/metrics"],  # Do not log these requests
)
```

> **Note**: If you are running starlette but not calling `init_uvicorn_observability`, you should call `init_starlette` to patch the routing api.

### Django with gunicorn

To set up tracing you have to set up some gunicorn hooks. Create a `gunicorn/config.py` file in your project:

```python
from os import environ

from troncos.frameworks.gunicorn import post_request_trace, pre_request_trace
from troncos.traces import init_tracing_basic, http_endpoint_from_env


def post_fork(server, worker):
    init_tracing_basic(
        endpoint=http_endpoint_from_env("TRACE_HOST", "TRACE_PORT", "/v1/traces"),
        exporter_type="http",  # Can also be grpc
        attributes={
            "pid": worker.pid,
            "environment": environ.get("ENVIRONMENT", "localdev"),
            "service.name": "myservice",
        }
    )

    # Add other instrumentors here, like:
    # DjangoInstrumentor().instrument()
    #
    # Psycopg2Instrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
    #     "service.name": "psycopg2",
    # }))


def pre_request(worker, req):
    pre_request_trace(worker, req, ignored_uris=["/health/"])


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

### Using the grpc exporter

Using `grpc` instead of `http` gives you significant performance gains. If you are running a critical service with high load in production, we recommend using `grpc`. To enable `grpc` install the exporter in your project:

```console
$ poetry add opentelemetry-exporter-otlp-proto-grpc
```

... and then choose it when you initialize tracing:

<!--pytest.mark.skip-->

```python
from os import environ
from troncos.traces import init_tracing_basic, http_endpoint_from_env

init_tracing_basic(
    endpoint=http_endpoint_from_env("TRACE_HOST", "TRACE_PORT"),
    exporter_type="grpc",
    attributes={
        "environment": environ.get("ENVIRONMENT", "localdev"),
        "service.name": "myservice",
    }
)
```

> **Note**: You need to change the `TRACE_PORT` depending on your choice of protocol http/grpc.

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

To include traces in your structlog logs, add this processor to your configuration.

> **NOTE**: This only adds trace information to your logs if you have set up tracing in your project.

```python
import structlog

from troncos.frameworks.structlog.processors import trace_injection_processor

structlog.configure(
    processors=[
       trace_injection_processor,
    ],
)
```

## Tracing

After initializing tracing in your project you can use different methods to trace your code.

### trace_function

This decorator adds tracing to a function. You can supply a tracer provider, if none is supplied, the global tracer provider will be used:

```python
from troncos.traces.decorate import trace_function
from troncos.traces import init_tracing_provider

custom_provider = init_tracing_provider(attributes={
    "service.name": "my_custom_provider",
})

@trace_function
def myfunc1():
    return "This will be traced"

@trace_function(tracer_provider=custom_provider)
def myfunc2():
    return "This will be traced using a custom provider"
```

### trace_block

Trace using a with statement. You can supply a tracer provider, if none is supplied, the global tracer provider will be used.

```python
from troncos.traces.decorate import trace_block

with trace_block(name="my.action", resource="some thing", attributes={"some": "attribute"}):
    print("... do an action to a thing...")
```

### trace_class

This decorator adds a tracing decorator to every method of the decorated class. If you don't want some methods to be traced, you can add the [trace_ignore](#trace_ignore) decorator to them. You can supply a tracer provider, if none is supplied, the global tracer provider will be used:

```python
from troncos.traces.decorate import trace_class, trace_ignore
from troncos.traces import init_tracing_provider

custom_provider = init_tracing_provider(attributes={
    "service.name": "my_custom_provider",
})

@trace_class
class MyClass1:

    def m1(self):
        return "This will be traced"

    @trace_ignore
    def m2(self):
        return "This will not traced"


@trace_class(tracer_provider=custom_provider)
class MyClass2:

    def m3(self):
        return "This will be traced using a custom provider"
```

### trace_module

This function adds a tracing decorator to every function of the calling module. If you don't want some functions to be traced, you can add the [trace_ignore](#trace_ignore) decorator to them. You can supply a tracer provider, if none is supplied, the global tracer provider will be used:

```python
from troncos.traces.decorate import trace_ignore, trace_module

def my_function():
    return "This func will be traced"

@trace_ignore
def my_function():
    return "This func will not be traced"

trace_module()
```

### trace_ignore

A decorator that will make [trace_class](#trace_class) and [trace_module](#trace_module) ignore the decorated function/method.

### Other instrumentors for tracing

You can add extra instrumentors to you app for even more tracing. You have to install the relevant packages yourself.

<!--pytest.mark.skip-->

```python
from troncos.traces import init_tracing_provider

DjangoInstrumentor().instrument()

Psycopg2Instrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
    "service.name": "psycopg2",
}))

RedisInstrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
    "service.name": "redis",
}))

CeleryInstrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
    "service.name": "celery",
}))

ElasticsearchInstrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
    "service.name": "elasticsearch",
}))

RequestsInstrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
    "service.name": "requests",
}))

HTTPXClientInstrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
    "service.name": "requests",  # Async requests
}))
```

## Trace Propagation

If you want to propagate your trace to the next service, you need to send/receive the `traceparent` header with your requests/message. Here are examples on how to do that.

### Send context

#### Requests

In general, if you have the `RequestsInstrumentor` setup you do not have to think about this. If you are not using that for some reason, you can propagate with this method:

```python
import requests
from troncos.frameworks.requests import traced_session

# Using a new session
with traced_session() as s:
    response = s.get("http://postman-echo.com/get")


# Using an old session
my_session = requests.session()
with traced_session(my_session) as s:
    response = s.get("http://postman-echo.com/get")
```

#### Send manually

```python
from troncos.traces.propagation import get_propagation_value

# Get traceparent
traceparent = get_propagation_value()

# Send it somewhere
```

or

```python
from troncos.traces.propagation import add_context_to_dict

some_dict = {}

# Add traceparent to dict
add_context_to_dict(some_dict)

# Send it somewhere
```

### Receive context

#### Using troncos middleware

Troncos defines middleware for some frameworks that does this automatically for you. If your framework is missing in troncos, please create an issue or PR.

#### Receive manually

```python
from troncos.traces.propagation import get_context_from_dict
from opentelemetry.trace import get_tracer

some_dict = {} 
context = get_context_from_dict(some_dict)

with get_tracer(__name__).start_as_current_span(
        "span.name",
        attributes={"some": "attrs"},
        context=context,
):
    print("... do something ...")
```

## Trace sampling

You can turn on [trace sampling](https://opentelemetry-python.readthedocs.io/en/latest/sdk/trace.sampling.html) by setting the following environmental variables:

```console
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.05
```
