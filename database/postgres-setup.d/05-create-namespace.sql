\set db_name `echo $DB_NAME`
\set db_role_db_owner_username :db_name

\connect :db_name

\set namespace_exists false
SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = 'main') AS namespace_exists \gset
\if :namespace_exists
    \echo 'Schema (aka namespace)' "main" 'already exists.'
\else
    CREATE SCHEMA main AUTHORIZATION :db_role_db_owner_username;
\endif

ALTER ROLE :db_role_db_owner_username SET search_path TO main;
