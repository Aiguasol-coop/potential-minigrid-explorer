import sqlalchemy
import sqlmodel

import app.db.helpers as db
import app.settings

# Import table definitions for create_all()
import app.grid.domain  # type: ignore
import app.explorations.domain  # type: ignore

from scripts.db_populate import populate_db


def get_engine() -> sqlalchemy.Engine:
    settings = app.settings.get_settings()

    # Connect as DB_OWNER
    host = settings.db_host
    port = settings.db_port
    username = settings.db_name  # We deliberately use the db_name as the DB_OWNER role name
    password = settings.db_role_db_owner_password
    database = settings.db_name

    db_url = f"postgresql+psycopg://{username}:{password}@{host}:{port}/{database}"

    # SERIALIZABLE gives maximum ACID transactional guarantees, see
    # https://www.postgresql.org/docs/current/transaction-iso.html
    engine = sqlmodel.create_engine(db_url, isolation_level="SERIALIZABLE", echo=True)

    return engine


def main(drop_all: bool = False) -> None:
    engine = get_engine()

    if drop_all:
        db.drop_all_tables(engine, "main")
        db.drop_all_custom_types(engine, "main")
    sqlmodel.SQLModel.metadata.create_all(engine)

    with sqlmodel.Session(bind=engine) as session:
        # TODO: Add roads to DB
        # Load data from shp files:
        populate_db(db_session=session)


if __name__ == "__main__":
    main(drop_all=False)
