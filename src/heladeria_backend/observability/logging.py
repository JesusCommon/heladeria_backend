import logging
import sys
import structlog
from heladeria_backend.config.settings import settings

def setup_logging() -> None:
    is_production = settings.app.environment == "production"
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    if is_production:
        shared_processors.append(structlog.processors.dict_tracebacks)
    else:
        shared_processors.append(structlog.processors.format_exc_info)

    renderer = (
        structlog.processors.JSONRenderer()
        if is_production
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if settings.app.debug else logging.INFO)

    # pymongo: WARNING por defecto; ERROR para los emisores de alta frecuencia.
    # pymongo.topology se deja en WARNING: ahí aparecen failovers y
    # server selection, que en prod sí quieres ver.
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("pymongo.topology").setLevel(logging.WARNING)
    logging.getLogger("pymongo.command").setLevel(logging.ERROR)
    logging.getLogger("pymongo.connection").setLevel(logging.ERROR)
    logging.getLogger("pymongo.serverSelection").setLevel(logging.ERROR)


def reconfigure_uvicorn_loggers() -> None:
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True