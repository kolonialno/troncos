<h1 align="center" style="border-bottom: 0">
  🚨 Work in progress 🚨 <br />
  <br />
  🪵<br>
  Troncos <br/>
</h1>

<h2>Welcome to Troncos</h2>

Collection of Python logging and tracing tools.

- [Etymology](#etymology)
- [Setup](#setup)
  - [Plain](#plain)
  - [Starlette (with uvicorn)](#starlette-with-uvicorn)
  - [Django](#django)
- [Logging](#logging)
- [Tracing](#tracing)
  - [trace_function](#trace_function)
  - [trace_block](#trace_block)
  - [trace_class](#trace_class)
  - [trace_module](#trace_module)
  - [trace_ignore](#trace_ignore)
  - [Other instrumentors for tracing](#other-instrumentors-for-tracing)
- [Trace Propagation](#trace-propagation)
  - [Requests session](#requests-session)

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
    formatter=environ.get("LOG_FORMATTER", "cli")  # Use "logfmt" in k8s
)

init_tracing_basic(
    endpoint=environ.get("TRACING_PATH", "http://localhost:4317"),
    attributes={
        "environment": environ.get("ENVIRONMENT", "localdev"),
        "service.name": "myservice",
    }
)
```

### Starlette (with uvicorn)

```python
from os import environ

from troncos.frameworks.starlette.uvicorn import init_uvicorn
from troncos.logs import init_logging_basic
from troncos.traces import init_tracing_basic

init_logging_basic(
    level=environ.get("LOG_LEVEL", "INFO"),
    formatter=environ.get("LOG_FORMATTER", "cli")  # Use "logfmt" in k8s
)

init_tracing_basic(
    endpoint=environ.get("TRACING_PATH", "http://localhost:4317"),
    attributes={
        "environment": environ.get("ENVIRONMENT", "localdev"),
        "service.name": "myservice",
    }
)

app = ... # Setup your app

init_uvicorn(
    app=app,
    log_access_ignored_paths=["/health", "/metrics"],  # Do not log these requests
)
```

### Django

TODO

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
Psycopg2Instrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
    "service.name": "psycopg2",
}, global_provider=False))

RedisInstrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
    "service.name": "redis",
}, global_provider=False))

CeleryInstrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
    "service.name": "celery",
}, global_provider=False))

RequestsInstrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
    "service.name": "requests",
}, global_provider=False))

HTTPXClientInstrumentor().instrument(tracer_provider=init_tracing_provider(attributes={
    "service.name": "requests",  # Async requests
}, global_provider=False))
```

## Trace Propagation

If you want to propagate your trace to the next service, you need to send the `traceparent` header with your requests/message. Here are examples on how to do that.

### Requests session

```python
# Using a new session
with traced_session() as s:
    response = s.get("http://postman-echo.com/get")


# Using an old session
mysession = session requests.session()
with traced_session(mysession) as s:
    response = s.get("http://postman-echo.com/get")
```