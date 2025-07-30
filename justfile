# Just commands that are convenient for development

set dotenv-load
set unstable
set script-interpreter := ['uv', 'run', '--script']

default:
    just --list

[group('models')]
gen-model grid_or_supply input_or_output:
    datamodel-codegen \
      --input-file-type jsonschema \
      --url https://optimizer-offgridplanner-app.apps2.rl-institut.de/schema/{{grid_or_supply}}/{{input_or_output}} \
      --output-model-type pydantic_v2.BaseModel \
      --field-constraints \
      --use-standard-collections \
      --use-subclass-enum \
      --use-union-operator \
      --use-schema-description


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

# pass a space-separated list of tables, such as "buildings exploration", or "all"
[group('database')]
load-data *tables:
    uv run -- python src/scripts/db_load_data.py --tables {{tables}}

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
