"""
This module is an utility tool to set up a Postgres database in order to be used by the app.

It is meant to be run after the creation of a fresh (no data) Postgres database cluster, and before
applying any migrations (aka data definition requests). It's useful to define roles, databases,
namespaces, extensions, and the like.

It runs (using psql) all the *.sql scripts found in a directory passed as an argument, in
alphabetical order.

It reads all the necessary parameters, variables, and secrets to connect and configure the database
from the environment, using module ``settings``.
"""

import os
import sys
import subprocess

import app.settings


settings = app.settings.get_settings()


def run_sql_files(directory: str):
    """Runs all .sql files in the specified directory in alphabetical order using psql."""
    if not os.path.isdir(directory):
        print(f"Error: '{directory}' is not a valid directory.")
        sys.exit(1)

    sql_files = sorted(f for f in os.listdir(directory) if f.endswith(".sql"))

    if not sql_files:
        print("No SQL files found in the directory.")
        sys.exit(0)

    for sql_file in sql_files:
        sql_path = os.path.join(directory, sql_file)
        print(f"Executing: {sql_file} ...")

        command = [
            "psql",
            "--no-psqlrc",  # aka -X
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            settings.db_host,
            "-p",
            str(settings.db_port),
            "-U",
            settings.db_superadmin_username,
            # The docker container creates a DB with the same name of the superadmin on
            # initialization, and it could be the only available DB when running the script.
            "-d",
            settings.db_superadmin_username,
            "-f",
            sql_path,
        ]

        environment = settings.model_dump()
        environment["PGPASSWORD"] = settings.db_superadmin_password

        try:
            subprocess.run(command, check=True, env=environment)
            print(f"✅ {sql_file} executed successfully.")
        except subprocess.CalledProcessError:
            print(f"❌ Error executing {sql_file}. Stopping.")
            sys.exit(1)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python db_run_sql_files.py <directory>")
        sys.exit(1)

    directory = sys.argv[1]

    run_sql_files(directory)


if __name__ == "__main__":
    main()
