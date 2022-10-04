import logging

from troncos.logs import LogfmtFormatter


def test_logfmt_formatter_unicode():
    fmt = LogfmtFormatter()
    res = fmt.format(logging.LogRecord(
        "test",
        level=0,
        pathname="path",
        lineno=42,
        msg="æøå \" \n %s",
        args=("þæö",),
        exc_info=None
    ))
    assert res.__contains__('msg="æøå \\" \\n þæö"')


def test_logfmt_formatter_bad_msg():
    fmt = LogfmtFormatter()
    res = fmt.format(logging.LogRecord(
        "test",
        level=0,
        pathname="path",
        lineno=42,
        msg="no args",
        args=("test",),
        exc_info=None
    ))
    assert res.__contains__('msg="no args % (\'test\',)"')


def test_logfmt_formatter_empty_msg():
    fmt = LogfmtFormatter()
    res = fmt.format(logging.LogRecord(
        "test",
        level=0,
        pathname="path",
        lineno=42,
        msg="",
        args=(),
        exc_info=None
    ))
    assert not res.__contains__('msg=""')


def test_logfmt_formatter_short_msg():
    fmt = LogfmtFormatter()
    res = fmt.format(logging.LogRecord(
        "test",
        level=0,
        pathname="path",
        lineno=42,
        msg="!",
        args=(),
        exc_info=None
    ))
    assert res.__contains__('msg="!"')
