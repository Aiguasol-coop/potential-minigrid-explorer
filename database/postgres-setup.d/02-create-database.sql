\set db_name `echo $DB_NAME`
\set db_locale `echo $DB_LOCALE`
\set db_icu_locale `echo $DB_ICU_LOCALE`
\set db_role_db_owner_username :db_name

\set db_exists false
SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_database WHERE datname = :'db_name') AS db_exists \gset
\if :db_exists
    \echo 'Database' :"db_name" 'already exists.'
\else
    CREATE DATABASE :db_name WITH
        OWNER :db_role_db_owner_username
        LOCALE_PROVIDER 'icu'
        ICU_LOCALE :'db_icu_locale'
        LOCALE :'db_locale'
        TEMPLATE 'template0';
\endif
