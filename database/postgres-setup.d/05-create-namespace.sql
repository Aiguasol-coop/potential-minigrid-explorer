\set db_name `echo $DB_NAME`
\set db_role_db_owner_username :db_name
\set db_role_api_service_username `echo $DB_ROLE_API_SERVICE_USERNAME`

\connect :db_name

\set namespace_exists false
SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = 'main') AS namespace_exists \gset
\if :namespace_exists
    \echo 'Schema (aka namespace)' "main" 'already exists.'
\else
    CREATE SCHEMA main AUTHORIZATION :db_role_db_owner_username;
\endif

GRANT USAGE ON SCHEMA main TO :db_role_api_service_username;

-- We need to keep schema 'public' in the search path because it's where PostGIS creates its types.
ALTER ROLE :db_role_db_owner_username SET search_path TO main, public;
ALTER ROLE :db_role_api_service_username SET search_path TO main, public;
