-- Deployment candidate database role (4A3, D-046). Runs once, on an empty data
-- directory, as the bootstrap superuser created by the postgres image.
--
-- D-046 keeps ONE role for the application: it owns the schema and may change
-- it, so a compromised application can drop its own tables. That residual risk
-- is recorded in docs/modernization/DEPLOYMENT_CANDIDATE.md; splitting migrate
-- and runtime roles is the mitigation if it is revisited.
--
-- What it still cannot do: become superuser, create databases or roles,
-- replicate, or bypass row security. Nothing here reaches outside this database.
--
-- No password literal appears in this file. The value is read from the file
-- given by BK_APP_DB_PASSWORD_FILE, mounted as a Docker secret.
\set ON_ERROR_STOP on
\set app_password `cat "$BK_APP_DB_PASSWORD_FILE"`

-- An unset or empty secret file would otherwise create a role with an empty
-- password, which PostgreSQL accepts and which then authenticates nobody --
-- or everybody, depending on pg_hba. Failing the container's first boot is the
-- only moment this is cheap to notice.
SELECT :'app_password' <> '' AS app_password_present \gset
\if :app_password_present
\else
DO $$ BEGIN
    RAISE EXCEPTION 'BK_APP_DB_PASSWORD_FILE is empty or unset; refusing to create a passwordless role';
END $$;
\endif

CREATE ROLE bazaar_app LOGIN PASSWORD :'app_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

ALTER DATABASE bazaar OWNER TO bazaar_app;

-- The bootstrap role owns the public schema created with the database. Handing
-- it over is what lets the application run its own migrations as bazaar_app.
ALTER SCHEMA public OWNER TO bazaar_app;

-- PUBLIC keeps no create right on the schema: every other role that might be
-- added later starts with nothing in this database.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO bazaar_app;

-- The database itself is not open to everyone either. Only the application
-- role connects; a future backup role is granted explicitly (12A2).
REVOKE ALL ON DATABASE bazaar FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE bazaar TO bazaar_app;
