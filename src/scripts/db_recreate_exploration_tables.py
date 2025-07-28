import sqlalchemy
import sqlmodel

import app.db.helpers as db
import app.settings

# Import table definitions for create_all()
import app.explorations.domain  # type: ignore


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


def main() -> None:
    engine = get_engine()

    db.drop_tables(engine, "main", ["cluster", "exploration", "simulation"])
    db.drop_all_custom_types(engine, "main")

    sqlmodel.SQLModel.metadata.create_all(engine)


if __name__ == "__main__":
    main()
