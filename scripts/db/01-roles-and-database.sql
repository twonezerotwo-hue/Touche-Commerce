-- ===========================================================================
-- TOUCHE COMMERCE — role + database bootstrap (run against the "postgres"
-- maintenance database as a superuser).
--
-- Usage:
--   psql -d postgres -v ON_ERROR_STOP=1 \
--        -v app_user=touche_app -v app_password=... \
--        -v migrator_user=touche_migrator -v migrator_password=... \
--        -v db_name=touche_commerce -f 01-roles-and-database.sql
--
-- Idempotent: safe to re-run. Passwords are rotated to the supplied value.
--
-- Two roles on purpose (docs/DECISIONS.md #4):
--   * migrator : owns the database/schema, runs Alembic (DDL)
--   * app      : runtime role, DML only, NOBYPASSRLS, NOSUPERUSER
-- ===========================================================================
\set ON_ERROR_STOP on

SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
  :'migrator_user', :'migrator_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migrator_user')
\gexec

SELECT format(
  'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
  :'migrator_user', :'migrator_password'
)
\gexec

SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
  :'app_user', :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
\gexec

SELECT format(
  'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
  :'app_user', :'app_password'
)
\gexec

-- Create the database owned by the migration role.
SELECT format('CREATE DATABASE %I OWNER %I', :'db_name', :'migrator_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db_name')
\gexec

SELECT format('ALTER DATABASE %I OWNER TO %I', :'db_name', :'migrator_user')
\gexec

-- Connection rights only; object rights are granted per database below.
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db_name', :'app_user')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db_name', :'migrator_user')
\gexec

-- Runtime role must never be allowed to bypass row level security.
SELECT format('ALTER ROLE %I NOBYPASSRLS', :'app_user')
\gexec

\echo 'roles and database ready'
