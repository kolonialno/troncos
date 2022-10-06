from contextlib import contextmanager
from typing import Generator

try:
    from requests import Session, session
except ImportError:
    raise Exception("This feature is only available if 'requests' is installed")

from troncos.traces.propagation import add_context_to_dict


@contextmanager
def traced_session(sess: Session | None = None) -> Generator[Session, None, None]:
    """
    Creates a requests session that propagates the traceparent forward to the next
    service. Example:

    with traced_session() as session:
        response = session.get("http://postman-echo.com/get")
    """

    s = sess or session()
    add_context_to_dict(s.headers)
    yield s
    s.headers.pop("traceparent", None)
