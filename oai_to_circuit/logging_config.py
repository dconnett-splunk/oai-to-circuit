import logging
from logging.config import dictConfig


class RenameLoggerFilter(logging.Filter):
    """Rename a logger's name in emitted records.

    This helps normalize uvicorn's 'uvicorn.error' to simply 'uvicorn'.
    """

    def __init__(self, from_name: str, to_name: str) -> None:
        super().__init__()
        self.from_name = from_name
        self.to_name = to_name

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == self.from_name:
            record.name = self.to_name
        return True


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(levelprefix)s %(asctime)s - %(processName)-13s[%(process)5d] - %(name)-8s - %(message)s",
            "use_colors": True,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": "%(levelprefix)s %(asctime)s - %(processName)-13s[%(process)5d] - %(name)-10s - %(client_addr)s - \"%(request_line)s\" %(status_code)s",
            "use_colors": True,
        },
    },
    "handlers": {
        "default": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stderr",
            "filters": ["rename_uvicorn"],
        },
        "access": {
            "class": "logging.StreamHandler",
            "formatter": "access",
            "stream": "ext://sys.stdout",
        },
    },
    "filters": {
        "rename_uvicorn": {
            "()": "oai_to_circuit.logging_config.RenameLoggerFilter",
            "from_name": "uvicorn.error",
            "to_name": "uvicorn",
        }
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        "asyncio": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "oai_to_circuit": {"handlers": ["default"], "level": "DEBUG", "propagate": False},
    },
    "root": {"handlers": ["default"], "level": "INFO"},
}


def configure_logging() -> None:
    """Configure unified logging for the app + uvicorn."""
    dictConfig(LOGGING_CONFIG)


