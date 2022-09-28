import io
import logging
import traceback
from copy import copy
from datetime import datetime
from types import TracebackType
from typing import Optional, Tuple, Type, Union


class LogfmtFormatter(logging.Formatter):
    """
    Formatter that spits out logs parsable by logfmt in Loki. It has pretty sane
    defaults, but you can pass in what fields of the log record you want to expose. Any
    fields not found are just ignored. You pass in your custom fields as a list of
    tuples, that set the exposed name, and the field name in the record respectively.
    For example if you want to just expose the loglevel and call it "mycustomlevelname"
    in the logs you would do it like so:

        LogfmtFormatter([
            ("mycustomlevelname", "levelname"),
        ])
    """

    def __init__(self, fields: list[Tuple[str, str]] | None = None):
        super().__init__()
        if fields:
            self._fields = fields
        else:
            self._fields = [
                ("level", "levelname"),
                ("logger", "name"),
                ("http_client_addr", "http_client_addr"),
                ("http_method", "http_method"),
                ("http_path", "http_path"),
                ("http_version", "http_version"),
                ("http_status_code", "http_status_code"),
                ("trace_id", "trace_id"),
                ("span_id", "span_id"),
                ("msg", "msg"),
            ]

    def format(self, record: logging.LogRecord) -> str:
        record.asctime = datetime.fromtimestamp(record.created).isoformat()

        s = self.formatMessage(record)
        if record.exc_info:
            s += self.formatException(record.exc_info)
        if record.stack_info:
            s += self.formatStack(record.stack_info)
        return s

    def formatMessage(self, record: logging.LogRecord) -> str:
        s = f'time="{record.asctime}"'
        record_dict = record.__dict__
        for expose_key, record_key in self._fields:
            field = record_dict.get(record_key)
            if field:
                if record_key != "msg":
                    s += f' {expose_key}="{str(field)}"'
                else:
                    msg = record.msg % record.args
                    s += f' {expose_key}="{self._escape(msg)}"'
        return s

    def formatException(
        self,
        ei: Union[
            Tuple[Type[BaseException], BaseException, Optional[TracebackType]],
            Tuple[None, None, None],
        ],
    ) -> str:
        e_type, e_msg, e_trace = ei

        s = f' exception_type="{str(e_type)[8:-2]}"'
        s += f' exception_message="{self._escape(str(e_msg))}"'

        if e_trace:
            sio = io.StringIO()
            traceback.print_exception(e_type, e_msg, e_trace, None, sio)
            trace_s = sio.getvalue()
            sio.close()
            s += f' exception_trace="{self._escape(trace_s)}"'

        return s

    def formatStack(self, stack_info: str) -> str:
        return f' stack_info="{self._escape(stack_info)}"'

    @staticmethod
    def _escape(s: str) -> str:
        """
        Use unicode_escape on the string, and also escape quotes.
        https://docs.python.org/3/library/codecs.html#text-encodings
        """

        return s.encode("unicode_escape").decode("utf-8").replace('"', '\\"')


class PrettyFormatter(logging.Formatter):
    """
    Simple logging formatter for development and debugging
    """

    # This is inspired by the color logger in uvicorn
    _lvl_colors = {
        5: "\x1b[34m",  # Trace
        logging.DEBUG: "\x1b[36m",
        logging.INFO: "\x1b[32m",
        logging.WARNING: "\x1b[33m",
        logging.ERROR: "\x1b[31m",
        logging.CRITICAL: "\x1b[31m",
    }
    _color_reset = "\x1b[0m"

    def __init__(self, fmt: str | None = None, **kwargs: dict) -> None:
        super().__init__(
            fmt or "%(levelname)s %(message)s", **kwargs  # type: ignore[arg-type]
        )

    def formatMessage(self, record: logging.LogRecord) -> str:
        rc = copy(record)

        # Set level
        indent_message_start = 9
        separator = " " * (indent_message_start - len(rc.levelname))
        color = PrettyFormatter._lvl_colors.get(rc.levelno, "")
        reset = PrettyFormatter._color_reset if color != "" else ""
        rc.levelname = f"{color}{rc.levelname}{reset}:{separator}"

        # Make nice access logs if http attributes are present
        if (
            hasattr(rc, "http_client_addr")
            and hasattr(rc, "http_method")
            and hasattr(rc, "http_path")
            and hasattr(rc, "http_status_code")
        ):
            rc.message = f"{rc.http_client_addr}"  # type: ignore[attr-defined]
            rc.message += " - "
            rc.message += f"{rc.http_method}"  # type: ignore[attr-defined]
            rc.message += f" {rc.http_path}"  # type: ignore[attr-defined]
            rc.message += f" {rc.http_status_code}"  # type: ignore[attr-defined]
        if hasattr(rc, "trace_id"):
            rc.message += f" [trace_id: {rc.trace_id}]"  # type: ignore[attr-defined]

        return super().formatMessage(rc)