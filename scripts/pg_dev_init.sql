-- Public synthetic credentials for loopback development only, never deployment.
CREATE ROLE bazaar_dev LOGIN PASSWORD 'synthetic-local-dev-only'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER DATABASE bazaar_dev OWNER TO bazaar_dev;
