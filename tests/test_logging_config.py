import logging

from oai_to_circuit.logging_config import RenameLoggerFilter, configure_logging


def test_rename_logger_filter_renames_exact_match():
    f = RenameLoggerFilter(from_name="uvicorn.error", to_name="uvicorn")
    record = logging.LogRecord(
        name="uvicorn.error",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    assert f.filter(record) is True
    assert record.name == "uvicorn"


def test_configure_logging_does_not_raise():
    configure_logging()


