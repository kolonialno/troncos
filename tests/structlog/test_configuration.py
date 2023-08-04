import sys
from typing import Any
from unittest.mock import DEFAULT, patch

import structlog


def import_without_structlog_sentry(package: str, *args: Any, **kwargs: Any) -> Any:
    """

    :param package: Name of package
    :return: None if `structlog_sentry` is part of package name, else default import
    """
    if "structlog_sentry" not in package:
        return DEFAULT
    return None


def test_processors_with_sentry() -> None:
    """
    According to structlog-sentry's docs, the SentryProcessor must come after
    add_logger_name nad add_log_level, and before format_exc_info

    https://github.com/kiwicom/structlog-sentry/blob/master/README.md

    :return: None
    """
    from troncos.contrib.structlog import shared_processors

    logger_name_index = shared_processors.index(structlog.stdlib.add_logger_name)
    log_level_index = shared_processors.index(structlog.stdlib.add_log_level)
    sentry_processor = [
        proc for proc in shared_processors if "structlog_sentry" in repr(proc)
    ][0]
    sentry_processor_index = shared_processors.index(sentry_processor)
    format_exc_info_index = shared_processors.index(
        structlog.processors.format_exc_info
    )

    assert (
        logger_name_index < sentry_processor_index
    ), "Logger name must come before Sentry processor"
    assert (
        log_level_index < sentry_processor_index
    ), "Log level must come before Sentry processor"
    assert (
        sentry_processor_index < format_exc_info_index
    ), "Format exc info must come after Sentry processor"


@patch("builtins.__import__", side_effect=import_without_structlog_sentry)
def test_processors_without_sentry(mocked: Any) -> None:
    """
    Make sure nothing bad happens when we init the processors without structlog_sentry
    installed
    :return:
    """
    del sys.modules["structlog_sentry"]

    from troncos.contrib.structlog import configure_structlog, shared_processors

    sentry_processors = [
        # This is kind of ugly, but seems to do the trick
        proc
        for proc in shared_processors
        if "structlog_sentry" in repr(proc)
    ]
    assert (
        len(sentry_processors) == 0
    ), "No Sentry processors should exist in shared processors when not installed"

    # And make sure nothing in the actual initiation blows up when we don't have
    # structlog_sentry installed
    configure_structlog()
