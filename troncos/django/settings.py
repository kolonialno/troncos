import structlog


def get_logging_config():
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json_formatter": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.JSONRenderer(),
            },
            "plain_console": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.dev.ConsoleRenderer(),
            },
            "key_value": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.KeyValueRenderer(key_order=['timestamp', 'level', 'event', 'logger']),
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "plain_console",
            },
            "json_file": {
                "class": "logging.handlers.WatchedFileHandler",
                "filename": "logs/json.log",
                "formatter": "json_formatter",
            },
            "flat_line_file": {
                "class": "logging.handlers.WatchedFileHandler",
                "filename": "logs/flat_line.log",
                "formatter": "key_value",
            },
        },
        "loggers": {
            "django_structlog": {
                "handlers": ["console", "flat_line_file", "json_file"],
                "level": "INFO",
            },
            # Make sure to replace the following logger's name for yours
            "django_structlog_demo_project": {
                "handlers": ["console", "flat_line_file", "json_file"],
                "level": "INFO",
            },
        }
    }
    return LOGGING