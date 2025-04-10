\set db_name `echo $DB_NAME`

\connect :db_name

-- Extension for case independent text
CREATE EXTENSION IF NOT EXISTS citext;
