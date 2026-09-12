-- Public synthetic credentials for a loopback-only, disposable test cluster.
CREATE ROLE bk_test_runner LOGIN PASSWORD 'synthetic-local-runner-only'
    NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER DATABASE bk_test_control OWNER TO bk_test_runner;
COMMENT ON DATABASE bk_test_control IS 'bazaar-kiosk-phase-1a-local-only';
