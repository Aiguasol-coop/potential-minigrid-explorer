\set db_role_api_service_username `echo $DB_ROLE_API_SERVICE_USERNAME`
\set db_role_api_service_password `cat /run/secrets/db_role_api_service_password || echo $DB_ROLE_API_SERVICE_PASSWORD`

\set role_exists false
SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'db_role_api_service_username') AS role_exists \gset
\if :role_exists
    \echo 'Role' :"db_role_api_service_username" 'already exists.'
\else
    CREATE ROLE :db_role_api_service_username WITH LOGIN PASSWORD :'db_role_api_service_password';
\endif
