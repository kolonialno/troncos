<h1 align="center" style="border-bottom: 0">
  🪵<br>
  Troncos <br/>
</h1>

<h2>Welcome to Troncos</h2>

Collection of Python logging and tracing tools.

<!-- TOC -->
  * [Etymology](#etymology)
  * [Setup](#setup)
    * [Plain](#plain)
    * [Starlette (with uvicorn)](#starlette--with-uvicorn-)
    * [Django (with gunicorn)](#django--with-gunicorn-)
  * [Logging](#logging)
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
      * [Manually](#manually)
    * [Receive context](#receive-context)
      * [Using troncos middleware](#using-troncos-middleware)
      * [Manually](#manually)
<!-- TOC -->

## Etymology

"Troncos" is the plural of the spanish "Tronco", which translates to "trunk" or "log".

## Setup

> Tip: It's a good idea to use a `settings.py`-file (or similar) as an authorative source of variables (service name,
> environment, whether tracing is enabled or not, log level etc.)

### Plain

Setting up logging and tracing requires some code that lives as close to the invocation of the application as possible (like in an entrypoint).

```python
from os import environ

from troncos.logs import init_logging_basic
from troncos.traces import init_tracing_basic

init_logging_basic(
    level=environ.get("LOG_LEVEL", "INFO"),
    formatter=environ.get("LOG_FORMATTER", "cli")  # Use "logfmt" or "json" in k8s
)

init_tracing_basic(
    endpoint=environ.get("TRACING_PATH", "http://localhost:4317"), # Can be a list
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

### Starlette (with uvicorn)

```python
from os import environ

from troncos.frameworks.starlette.uvicorn import init_uvicorn_observability
from troncos.logs import init_logging_basic
from troncos.traces import init_tracing_basic

init_logging_basic(
    level=environ.get("LOG_LEVEL", "INFO"),
    formatter=environ.get("LOG_FORMATTER", "cli")  # Use "logfmt" or "json" in k8s
)

init_tracing_basic(
    endpoint=environ.get("TRACING_PATH", "http://localhost:4317"),  # Can be a list
    attributes={
        "environment": environ.get("ENVIRONMENT", "localdev"),
        "service.name": "myservice",
    }
)

# Add other instrumentors here, like:
# RequestsInstrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
#     "service.name": "requests",
# }))

app = ...  # Setup your app

init_uvicorn_observability(
    app=app,
    log_access_ignored_paths=["/health", "/metrics"],  # Do not log these requests
)
```

### Django (with gunicorn)

To setup tracing you have to set up some gunicorn hooks. Create a `gunicorn/config.py` file in your project:

```python
from os import environ

from troncos.frameworks.gunicorn import post_request_trace, pre_request_trace
from troncos.traces import init_tracing_basic 


def post_fork(server, worker):
    init_tracing_basic(
      endpoint=environ.get("TRACING_PATH", "http://localhost:4317"),  # Can be a list
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
    pre_request_trace(worker, req)


def post_request(worker, req, environ, resp):
    post_request_trace(worker, req, environ, resp)
```

Then when running gunicorn specify the config file used:

```console
gunicorn myapp.wsgi:application --config python:myapp.gunicorn.config ...
```

You have to manually configure logging in your `settings.py`, in general you should adhere to the principle described in [the logging section](#logging).

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

In general you want all loggers to propagate their records to the `root` logger and make the `root` logger handle everything. Depending on your project, this might require some additional configuration. Looking at the [python logging flow](https://docs.python.org/3/howto/logging.html#logging-flow) can help you understand how child loggers can propagate records to the `root` logger. Note that propagating to `root` is the default behaviour.

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
logging.getLogger("my.random.logger").info("Root will handle this record")
```

## Tracing

After you have called `init_tracing_basic` you can use different methods to trace your code.

### trace_function

This decorator adds tracing to a function. You can supply a tracer provider, if none is supplied, the global tracer provider will be used:

```python
@trace_function
def myfunc1()
    return "This will be traced"

@trace_function(tracer_provider=custom_provider)
def myfunc2()
    return "This will be traced using a custom provider"
```

### trace_block

Trace using a with statement. You can supply a tracer provider, if none is supplied, the global tracer provider will be used.

```python
with trace_block(name="my block", attributes={"some": "attribute"}):
    # Do something
```

### trace_class

This decorator adds a tracing decorator to every method of the decorated class. If you don't want some methods to be traced, you can add the [trace_ignore](#trace_ignore) decorator to them. You can supply a tracer provider, if none is supplied, the global tracer provider will be used:

```python
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
def my_function():
    return "This func will be traced"

@trace_ignore
def my_function():
    return "This func will not be traced"

trace_module()
```

### trace_ignore

A decorator that will make [trace_class](#trace_class) and [trace_module](#trace_module) ignore the decorated function.

### Other instrumentors for tracing

You can add extra instrumentors to you app for even more tracing. You have to install relevant packages yourself.

```python
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

GrpcInstrumentorClient().instrument(tracer_provider=init_tracing_provider(attributes={
    "service.name": "grpc",
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
# Using a new session
with traced_session() as s:
    response = s.get("http://postman-echo.com/get")


# Using an old session
mysession = session requests.session()
with traced_session(mysession) as s:
    response = s.get("http://postman-echo.com/get")
```

#### Manually

```python
# Get traceparent
traceparent = get_propagation_value()
# Send it somewhere
```

or

```python
some_dict = {}
# Add traceparent to dict
add_context_to_dict(some_dict)
# Send it somewhere
```

### Receive context

#### Using troncos middleware

Troncos defines middleware for some frameworks that does this automatically for you. If your framework is missing in troncos, please create an issue or PR.

#### Manually

```python
context = get_context_from_dict(some_dict)

with tracer.start_as_current_span(
        "span.name",
        attributes={"some": "attrs"},
        context=context,
):
    ... do something ...
```