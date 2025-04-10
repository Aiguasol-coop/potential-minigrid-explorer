# Database cluster configuration

The .sql scripts in this directory set up all the following objects:

* A **database** called `$DB_NAME`. It can be used to setup a different database for each instance of 
  this project. The actual value of `$DB_NAME` can be configured in `src/app/settings.py`.

* A **schema** (aka namespace) `main` in that database. All relevant users are configured to use this
  schema by default (instead of `public`, that has many historical default behaviors that may be
  occasionally surprising).

* The following distinguished **roles** and users:

  - The owner of the database, named also `$DB_NAME`. It has login access with a password. It also
    owns the schema `main` and all the objects (tables, types, etc.) created in the database.
    Migration scripts have to connect to the database using this role.

* Some extensions.

> [!IMPORTANT] All the configuration in this directory is meant to be run, intact, in both
> development/testing and production deployments.
>
## Running the scripts

They can be executed in different ways, including:

* Using script ``uv run db_run_sql_files``.

* Copying/mounting the files into directory ``/docker-entrypoint-initdb.d`` of a Postgres Docker
  container (this could require small adjustments to the scripts, specially for handling secrets).

The scripts assume they are running as the superadmin of the cluster (usually called `postgres`, but
can be changed).

> [!IMPORTANT] The scripts are supposed to be idempotent.
