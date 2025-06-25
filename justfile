# Just commands that are convenient for development

set dotenv-load
set unstable
set script-interpreter := ['uv', 'run', '--script']

default:
    just --list

[group('database')]
psql-superadmin:
    PGPASSWORD=`cat /run/secrets/db_superadmin_password` psql -h $DB_HOST -U $DB_SUPERADMIN_USERNAME

[group('database')]
psql:
    PGPASSWORD=test psql -h $DB_HOST -U test -d $DB_NAME

[group('database')]
db-run-sql-files:
    uv run db_run_sql_files database/postgres-setup.d/

# pass a comma-separated table list to generate their SQLAlchemy models
[group('database')]
db-generate tables:
    uv run sqlacodegen --tables {{tables}} postgresql://test:test@db:5432/test

[group('database')]
load-data drop_all:
    uv run db_load_data(drop_all= {{drop_all | default('false')}})

# run the API backend service with reload
[group('fastapi')]
dev:
    uv run fastapi dev src/app/main.py

# Alternatives to the above command:
# - uv run potential-minigrid-explorer
# - python -m app.main_alt
# - uv run uvicorn app.main:api --reload     # This one fails to find the favicon

# run the API backend service with no reload
[group('fastapi')]
prod:
    uv run fastapi run src/app/main.py
