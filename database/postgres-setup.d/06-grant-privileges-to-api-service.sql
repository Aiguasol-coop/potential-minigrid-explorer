\set db_name `echo $DB_NAME`
\set db_role_db_owner_username :db_name
\set db_role_api_service_username `echo $DB_ROLE_API_SERVICE_USERNAME`

\connect :db_name

-- We grant privileges on future objects with ALTER DEFAULT PRIVILEGES:

ALTER DEFAULT PRIVILEGES FOR ROLE :db_role_db_owner_username IN SCHEMA main
GRANT
SELECT ON TABLES TO :db_role_api_service_username
;

-- Usage on sequences is needed for accessing tables that use them (i.e., all tables).
ALTER DEFAULT PRIVILEGES FOR ROLE :db_role_db_owner_username IN SCHEMA main
GRANT
USAGE ON SEQUENCES TO :db_role_api_service_username
;

ALTER DEFAULT PRIVILEGES FOR ROLE :db_role_db_owner_username IN SCHEMA main
GRANT
INSERT, UPDATE, DELETE ON TABLES TO :db_role_api_service_username
;

-- Redundant: functions and procedures are executable by PUBLIC (aka anyone) by default. Note that,
-- if these functions and procedures are declared as SECURITY DEFINER, they can do things than the
-- executing user cannot do by themselves.
ALTER DEFAULT PRIVILEGES FOR ROLE :db_role_db_owner_username IN SCHEMA main
GRANT
EXECUTE ON ROUTINES TO :db_role_api_service_username
;
