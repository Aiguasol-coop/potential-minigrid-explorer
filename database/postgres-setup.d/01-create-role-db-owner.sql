\set db_name `echo $DB_NAME`
\set db_role_db_owner_username :db_name
\set db_role_db_owner_password `cat /run/secrets/db_role_db_owner_password || echo $DB_ROLE_DB_OWNER_PASSWORD`

\set role_exists false
SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'db_role_db_owner_username') AS role_exists \gset
\if :role_exists
    \echo 'Role' :"db_role_db_owner_username" 'already exists.'
\else
    CREATE ROLE :db_role_db_owner_username WITH LOGIN PASSWORD :'db_role_db_owner_password';
\endif
