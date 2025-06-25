import collections.abc
import functools
import typing
import fastapi
import sqlalchemy
import sqlmodel

import app.settings


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
    engine = sqlalchemy.create_engine(db_url, isolation_level="SERIALIZABLE")

    return engine


def get_session() -> collections.abc.Generator[sqlmodel.Session]:
    with sqlmodel.Session(get_engine()) as session:
        yield session


Session = typing.Annotated[sqlmodel.Session, fastapi.Depends(get_session)]
