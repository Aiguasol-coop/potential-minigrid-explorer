import collections.abc
import contextlib
import fastapi
import functools
import logging
import sqlalchemy
import sqlmodel
import typing

import app.settings


# Just for debugging:
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,  # or sys.stderr
)


@functools.lru_cache  # We memoize the result
def get_engine() -> sqlalchemy.Engine:
    """The only sqlalchemy engine in the app, as the result of this function is memoized (using
    functools.lru_cache).
    """
    settings = app.settings.get_settings()

    host = settings.db_host
    port = settings.db_port
    username = settings.db_role_api_service_username
    password = settings.db_role_api_service_password
    database = settings.db_name

    db_url = f"postgresql+psycopg://{username}:{password}@{host}:{port}/{database}"

    # SERIALIZABLE gives maximum ACID transactional guarantees, see
    # https://www.postgresql.org/docs/current/transaction-iso.html
    engine = sqlalchemy.create_engine(
        db_url,
        isolation_level="READ COMMITTED",  # TODO: READ COMMITTED??
        pool_size=10,
        max_overflow=10,
    )

    return engine


def get_session() -> collections.abc.Generator[sqlmodel.Session]:
    with sqlmodel.Session(get_engine()) as session:
        yield session


@contextlib.contextmanager
def get_logging_session(
    name: str = "Unnamed session",
) -> collections.abc.Generator[sqlmodel.Session]:
    logging.info(f"DB session {name}: BEFORE OPENING, pool status: {get_engine().pool.status()}")
    session = sqlmodel.Session(get_engine())
    try:
        yield session
    finally:
        session.close()
        logging.info(f"DB session {name}: CLOSED, pool status: {get_engine().pool.status()}")


Session = typing.Annotated[sqlmodel.Session, fastapi.Depends(get_session)]
