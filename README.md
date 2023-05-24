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
$ pip install troncos
```

## Tracing

Troncos is designed to take advantage of `ddtrace` made by DataDog.

The ddtrace docs can be found [here](https://ddtrace.readthedocs.io/en/stable/).

### Enabling the tracer

Configure ddtrace as usual and run `configure_tracer` to send spans to Tempo.

This is typically done in `settings.py` of you want to profile a Django application,
or in `__init__.py` in the root project package.

`TRACE_HOST` is usually the host IP of the K8s pod, `TRACE_PORT` is usually 4318
when the Grafana agent is used to collect spans using HTTP.

```python
import ddtrace

from troncos.tracing import configure_tracer

# Configure tracer as described in the ddtrace docs.
ddtrace.config.django["service_name"] = 'SERVICE_NAME'
ddtrace.tracer.set_tags(
    tags={
        "fulfillment_center": 'osl2',
    }
)

# Patch third-party modules
ddtrace.patch_all()

# Configure the ddtrace tracer to send traces to Tempo.
TRACE_HOST = "127.0.0.1" # Usually obtained from env variables.
TRACE_PORT = "4318"
configure_tracer(
    enabled=True,
    service_name='SERVICE_NAME',
    endpoint=f"http://{TRACE_HOST}:{TRACE_PORT}/v1/traces",
)
```

ddtrace also uses env variables to configure the service name, environment and version etc.

Add the following environment variables to your application.

```
DD_ENV="{{ environment }}"
DD_SERVICE="{{ app }}"
DD_VERSION="{{ version }}"
# b3 is usually used to propagate distributed traces across services.
DD_TRACE_PROPAGATION_STYLE_EXTRACT="b3"
DD_TRACE_PROPAGATION_STYLE_INJECT="b3"
```

### Instrument your code

Manual instrumentation of your code is described in the [ddtrace docs](https://ddtrace.readthedocs.io/en/stable/basic_usage.html#manual-instrumentation).

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

### Enabling the profiler

Start the profiler by importing the profiler module early in your application. This is
typically done in `settings.py` of you want to profile a Django application, or in `__init__.py`
in the root project package.

```python
import troncos.profiling.auto
```

### Setup profile endpoint

Use one of the methods bellow based on your selected framework.

#### Django

Add the profile view to the url config.

```python
from django.urls import path

from troncos.contrib.django.profiling.views import profiling_view

urlpatterns = [
    path("/debug/pprof", profiling_view, name="profiling"),
]
```

#### Starlette

Add the profile view to your router.

```python
from starlette.routing import Route

from troncos.contrib.starlette.profiling.views import profiling_view

routes = [
    Route("/debug/pprof", profiling_view),
]
```

#### ASGI

Mount the generic ASGI profiling application. There is no generic way to do this,
please check the relevant ASGI framework documentation.

```python
from troncos.contrib.asgi.profiling.app import profiling_asgi_app

# FastAPI example
from fastapi import FastAPI

app = FastAPI()

app.mount("/debug/pprof", profiling_asgi_app)
```

### Verify setup

You can verify that your setup works with the [pprof](https://github.com/google/pprof) cli:

```console
$ pprof -http :6060 "http://localhost:8080/debug/pprof"
```

### Enable scraping

When you deploy your application, be sure to use the custom oda annotation for scraping:

```yaml
annotations:
  phlare.oda.com/port: "8080"
  phlare.oda.com/scrape: "true"
```

## Logging

Troncos is not designed to take control over your logger. But, we do include logging
related tools to make instrumenting your code easer.

### Adding tracing context to your log

Troncos has a Structlog processor that can be used to add the `span_id` and `trace_id`
properties to your log. More infomation can be found in the [Tracing](#tracing)
section in this document.

### Request logging middleware

Finding the relevant traces in Tempo and Grafana can be difficult. The request logging
middleware exist to make it easier to connect HTTP requests to traces. More infomation
can be found in the [Tracing](#tracing) section in this document.
