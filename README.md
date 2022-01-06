<h1 align="center" style="border-bottom: 0">
  🚨 Work in progress 🚨 <br />
  <br />
  🪵<br>
  Troncos <br/>
</h1>

## Welcome to Troncos
Collection of Python logging and tracing tools.

## Etymology
"Troncos" is the plural of the spanish "Tronco", which translates to "trunk" or "log".

## Usage

> Tip: It's a good idea to use a `settings.py`-file (or similar) as an authorative source of variables (service name,
> environment, whether tracing is enabled or not, log level etc.)

### Plain python
Setting up the logger (with tracer) requires some code that lives as close to the invocation of the application as
possible (like in an entrypoint),

```python
from troncos.base import tracing, logging


def main():
    tracing.configure_tracer(
        service="app",
        environment="dev",
        enabled=True,
    )
    logging.configure_logging(
        environment="dev",
        release="0.0.1",
        log_level="DEBUG"
    )

    # ... the rest of entrypoint code ...
```

Using the logger is easy -- just use `troncos.get_logger`in place of `logging.get_logger`.

```python
from troncos import get_logger
logger = get_logger()

logger.debug('foo')
logger.warning('bar', baz='1234')
```

### Django
Set up logging config in settings file to enable native use of Django logging facilities through structlog.

```python
from troncos.django.settings import get_logging_config

LOGGING = get_logging_config()
LOGGING['handlers']['file']['filename'] = '/path/to/log'
```

> TODO: Setting up tracing in Django (w/middleware)


### Starlette
Make sure your app is set up with the tracing middleware.

```python
from starlette.applications import Starlette
from starlette.middleware import Middleware

from troncos.base import tracer
from troncos.starlette import DDTraceMiddleware

middleware = [
    # The tracing middleware must be the first one defined
    Middleware(DDTraceMiddleware, middleware_tracer=tracer),
    # ...
]

app = Starlette(
    # ...
    middleware=middleware,
    # ...
)
```

About the same as plain Python, but we'll be using the async tracer instead.

```python
import asyncio

from troncos.base import tracing, logging

from app import webserver


def main():
    tracing.configure_tracer(
        service="app",
        environment="dev",
        enabled=True,
    )

    logging.configure_logging(
        environment="dev",
        release="0.0.1",
        log_level="DEBUG"
    )

    asyncio.run(webserver.run())
```