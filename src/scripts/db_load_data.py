import argparse

import sqlalchemy
import sqlmodel

import app.db.helpers as db
import app.settings

# Import table definitions for create_all()
import app.explorations.domain  # type: ignore
import app.grid.domain  # type: ignore


from scripts.db_populate import populate_db, populate_default_db


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


# Keys: table names
# Values: (1) whether they have initial data to populate them,
#         (2) their related custom database types
ALL_TABLES: dict[str, tuple[bool, list[str]]] = {
    "buildings": (True, []),
    "grid_distribution_lines": (True, []),
    "mini_grids": (True, ["minigridstatus"]),
    "cluster": (False, []),
    "exploration": (False, ["explorationstatus"]),
    "simulation": (False, []),
    "roads": (True, []),
    "category_distribution": (True, []),
    "household_data": (True, []),
    "enterprise_data": (True, []),
    "public_service_data": (True, []),
    "household_hourly_profile": (True, []),
    "enterprise_hourly_profile": (True, []),
    "public_service_hourly_profile": (True, []),
}


def main(selected_tables: dict[str, tuple[bool, list[str]]]) -> None:
    engine = get_engine()

    db.drop_tables(engine, "main", list(selected_tables.keys()))

    custom_types = [t for _, (_, types) in selected_tables.items() for t in types]
    db.drop_custom_types(engine, "main", custom_types)

    sqlmodel.SQLModel.metadata.create_all(engine)

    # Populate if there is some table that needs initial data
    if any([b for _, (b, _) in selected_tables.items()]):
        with sqlmodel.Session(bind=engine) as session:
            # Load data from shp files:
            populate_db(db_session=session)

            # Load default data from JSON file:
            populate_default_db(db_session=session)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Re-create and re-populate selected tables in the database."
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        required=True,
        help="List of table names to re-create and populate (e.g., buildings or simulation), "
        "or 'all' for all tables.",
    )
    args = parser.parse_args(["--tables", "mini_grids"])

    # Handle the special "all" keyword
    if len(args.tables) == 1 and args.tables[0].lower() == "all":
        selected_tables = ALL_TABLES
    else:
        selected_tables = {k: ALL_TABLES[k] for k in args.tables if k in ALL_TABLES}

    main(selected_tables)
