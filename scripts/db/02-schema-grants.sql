-- ===========================================================================
-- TOUCHE COMMERCE — per-database schema grants (run against the application
-- database). Idempotent.
--
-- Usage:
--   psql -d touche_commerce -v ON_ERROR_STOP=1 \
--        -v app_user=touche_app -v migrator_user=touche_migrator \
--        -f 02-schema-grants.sql
--
-- * public schema: migration role may create (Alembic version table),
--   runtime role gets USAGE only.
-- * touche schema: created by the initial Alembic migration, which also
--   grants DML to the runtime role.
-- ===========================================================================
\set ON_ERROR_STOP on

REVOKE ALL ON SCHEMA public FROM PUBLIC;

SELECT format('GRANT USAGE, CREATE ON SCHEMA public TO %I', :'migrator_user')
\gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_user')
\gexec

-- Default privileges for objects the migration role creates in public.
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
  :'migrator_user', :'app_user'
)
\gexec

\echo 'schema grants applied'
