import os
import sys

import sqlalchemy
import sqlalchemy.engine.reflection
import sqlalchemy.schema

from app.utils import CustomError


# This whole function is copied from
# https://github.com/pallets-eco/flask-sqlalchemy/issues/722#issuecomment-705672929.
# It drops foreign key constraints first, so then it can drop all tables.
#
# The function has been adapted in two ways:
#
#   * We've added the check that avoids running the function if not in a testing scenario.
#   * We only drop constraints and tables from a specific schema (aka namespace).
def drop_tables(
    engine: sqlalchemy.Engine, schema: str, table_names: list[str] | None = None
) -> None:
    """(On a live db) drops all foreign key constraints before dropping all tables.
    Workaround for SQLAlchemy not doing DROP ## CASCADE for drop_all()
    (https://github.com/pallets/flask-sqlalchemy/issues/722)
    """

    cmdline_arguments = " ".join(sys.argv)
    if (
        "db_load_data" not in cmdline_arguments
        and "db_recreate_exploration_tables" not in cmdline_arguments
        and "PYTEST_CURRENT_TEST" not in os.environ
    ):
        raise CustomError("We're trying to drop all tables from a non-test environment!!")

    con = engine.connect()
    trans = con.begin()
    inspector = sqlalchemy.engine.reflection.Inspector.from_engine(engine)

    # We need to re-create a minimal metadata with only the required things to
    # successfully emit drop constraints and tables commands for postgres (based
    # on the actual schema of the running instance)
    meta = sqlalchemy.schema.MetaData()
    tables = []
    all_fkeys = []

    existing_tables = set(inspector.get_table_names(schema=schema))
    if table_names:
        tables_to_drop = list(set(table_names) & existing_tables)
    else:
        tables_to_drop = list(existing_tables)

    for table_name in tables_to_drop:
        fkeys = []

        for fkey in inspector.get_foreign_keys(table_name, schema=schema):
            if not fkey["name"]:
                continue

            fkeys.append(sqlalchemy.schema.ForeignKeyConstraint((), (), name=fkey["name"]))  # type: ignore

        tables.append(sqlalchemy.schema.Table(table_name, meta, *fkeys))  # type: ignore
        all_fkeys.extend(fkeys)  # type: ignore

    for fkey in all_fkeys:  # type: ignore
        con.execute(sqlalchemy.schema.DropConstraint(fkey))  # type: ignore

    for table in tables:  # type: ignore
        con.execute(sqlalchemy.schema.DropTable(table))  # type: ignore

    trans.commit()


def drop_all_custom_types(engine: sqlalchemy.Engine, schema: str) -> None:
    """
    Drop every user-defined type in the given schema.
    Works for enums, composite types, domains, etc.
    """
    query = sqlalchemy.text(
        """
        SELECT format('%I.%I', n.nspname, t.typname)          -- fully-qualified type name
        FROM pg_type t
        JOIN pg_namespace n  ON n.oid = t.typnamespace
        WHERE n.nspname = :schema
          AND t.typtype IN ('e', 'd')     -- e = enum, d = domain. WE IGNORE c = composite types!
        """
    )

    with engine.begin() as conn:  # autocommit block
        type_names = conn.execute(query, {"schema": schema}).scalars().all()

        for fullname in type_names:
            conn.execute(sqlalchemy.text(f"DROP TYPE IF EXISTS {fullname} CASCADE;"))
