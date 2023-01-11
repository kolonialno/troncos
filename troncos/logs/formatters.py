import io
import json
import logging
import traceback
from copy import copy
from datetime import datetime
from types import TracebackType
from typing import Any, Optional, Tuple, Type, Union


class JsonFormatter(logging.Formatter):
    """
    Logging formatter for creating log entries in a JSON logstash-friendly format.
    Example:
        {
            "msg": ""GET / HTTP/1.1" 404 2327",
            "status_code": "404",
            "message": ""GET / HTTP/1.1" 404 2327",
            "server_time": "14/Sep/2016 11:13:00",
            "@timestamp": "2016-09-14 11:13:00,667"
        }
    """

    RESERVED_ATTRS = (
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "trace_id",
        "span_id",
        "dd_trace_id",
        "dd_span_id",
    )

    DEFAULT_FIELDS = (
        "asctime",
        "levelname",
        "filename",
        "funcName",
        "msg",
        "exc_info",
    )

    DEFAULT_MAPPING = {
        "asctime": "@timestamp",
    }

    converter = datetime.fromtimestamp  # type: ignore[assignment]
    default_time_format = "%Y-%m-%dT%H:%M:%S.%f"

    def __init__(
        self,
        *args: Any,
        rename: dict[str, str] | None = None,
        version: str = "1",
        fields: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Builds the formatter.
        param fmt: list or tuple containing default fields to include in every entry
        param datefmt: date format as a string to be passed to formatTime().
            Defaults to ISO8601 format.
        param rename: dictionary with {old_key: new_key} to be renamed in the log
            entries. Defaults to {'asctime':'@timestamp'}.
        param version: version as for @version field in logging, always included.
            Defaults to "1".
        """

        super().__init__(*args, **kwargs)

        self.fields = (
            [f for f in fields if f in self.RESERVED_ATTRS]
            if fields
            else self.RESERVED_ATTRS
        )

        self.rename_map = rename or self.DEFAULT_MAPPING
        self.version = version

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> Any:
        """
        Overriding formatTime to add milliseconds parsing
        :param record:
        :param datefmt:
        :return:
        """

        ct = self.converter(record.created)  # type: ignore[has-type]
        _format = datefmt or self.default_time_format

        # noinspection PyUnresolvedReferences
        s = ct.strftime(_format)

        return s

    def format(self, record: logging.LogRecord) -> str:
        _msg = record.msg

        record.asctime = self.formatTime(record, self.datefmt)

        if isinstance(_msg, dict):
            msg_dict = _msg
        else:
            msg_dict = {}  # type: ignore[var-annotated]
            record.message = record.getMessage()

        extra_dict = {
            k: v
            for k, v in record.__dict__.items()
            if k not in self.RESERVED_ATTRS and not k.startswith("_")
        }

        # Fields specified at "fmt"
        fields_dict = {k: v for k, v in record.__dict__.items() if k in self.fields}

        # Adding fields coming from base message
        fields_dict.update(msg_dict)

        # Adding extra fields
        fields_dict.update(extra_dict)

        # Replacing fields names if rename mapping exists
        for k, v in self.rename_map.items():
            if k in fields_dict.keys():
                fields_dict[v] = fields_dict.pop(k)

        # Adding logging schema version if exists
        if self.version:
            fields_dict["@version"] = self.version

        return json.dumps(fields_dict, default=str)


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
                ("duration", "duration"),
                ("trace_id", "trace_id"),
                ("span_id", "span_id"),
                ("dd_trace_id", "dd_trace_id"),
                ("dd_span_id", "dd_span_id"),
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
                    # noinspection PyBroadException
                    try:
                        msg = record.msg % record.args
                    except Exception:
                        msg = f"{record.msg} % {record.args}"
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
        Use json dumps to escape strings
        """

        escaped = json.dumps(s, ensure_ascii=False)
        return escaped[1 : len(escaped) - 1]  # noqa: E203


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

    def __init__(self, fmt: str | None = None, **kwargs: dict[str, Any]) -> None:
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
            and hasattr(rc, "duration")
        ):
            rc.message = f"{rc.http_client_addr}"  # type: ignore[attr-defined]
            rc.message += " - "
            rc.message += f"{rc.http_method}"  # type: ignore[attr-defined]
            rc.message += f" {rc.http_path}"  # type: ignore[attr-defined]
            rc.message += f" {rc.http_status_code}"  # type: ignore[attr-defined]
            rc.message += f" {rc.duration}"  # type: ignore[attr-defined]
        if hasattr(rc, "trace_id"):
            rc.message += f" [trace_id: {rc.trace_id}]"  # type: ignore[attr-defined]
        if hasattr(rc, "dd_trace_id"):
            rc.message += f" [dd_trace_id: {rc.dd_trace_id}]"  # type: ignore[attr-defined] # noqa: E501

        return super().formatMessage(rc)
