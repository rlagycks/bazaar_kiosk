"""Create and remove only fixture databases owned by this test invocation."""

from contextlib import contextmanager
from copy import deepcopy
import uuid

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connections
import psycopg
from psycopg import sql


def verify_control_database(control):
    """Verify server facts before any CREATE/DROP, not just a test-looking URL."""
    row = control.execute("""
        SELECT current_database(), current_user, d.datdba = r.oid,
               shobj_description(d.oid, 'pg_database'),
               r.rolsuper, r.rolcreatedb, r.rolcreaterole,
               r.rolreplication, r.rolbypassrls,
               current_setting('server_version_num')::integer
        FROM pg_database d JOIN pg_roles r ON r.rolname = current_user
        WHERE d.datname = current_database()
    """).fetchone()
    if (
        row is None
        or row[:9] != (
            "bk_test_control", "bk_test_runner", True,
            "bazaar-kiosk-phase-1a-local-only", False, True, False, False, False,
        )
        or not 150000 <= row[9] < 160000
    ):
        raise ImproperlyConfigured("Refusing an unverified PostgreSQL fixture target")


@contextmanager
def migration_database():
    if settings.SETTINGS_MODULE != "bazaar_kiosk.settings_test_pg":
        raise ImproperlyConfigured("Migration fixtures require settings_test_pg")
    config = settings.DATABASES["default"]
    # Parse the explicit env again; callers cannot override settings to redirect us.
    import os
    from bazaar_kiosk.settings_test_pg import test_database_config

    verified_config = test_database_config(os.environ.get("BK_TEST_DATABASE_URL", ""))
    for key in ("ENGINE", "NAME", "USER", "PASSWORD", "HOST", "PORT", "OPTIONS"):
        if config[key] != verified_config[key]:
            raise ImproperlyConfigured("PostgreSQL fixture configuration was overridden")
    with psycopg.connect(
        dbname=config["NAME"], user=config["USER"], password=config["PASSWORD"],
        host=config["HOST"], port=config["PORT"], **config["OPTIONS"], autocommit=True,
    ) as control:
        verify_control_database(control)
        name = "bk_test_migration_" + uuid.uuid4().hex
        # Original RunPython migrations use unqualified managers on `default`.
        # Route that same alias to the fresh database, never to the control DB.
        alias = "default"
        saved_connection = connections[alias]
        saved_config = connections.databases[alias]
        saved_connection.close()
        # Close the old connection before CREATE so even its failure cannot leak a DB.
        # No IF NOT EXISTS: a collision must fail, never adopt someone else's DB.
        control.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
        connection = None
        try:
            connection_config = deepcopy(saved_connection.settings_dict)
            connection_config["NAME"] = name
            connections.databases[alias] = connection_config
            connection = connections.create_connection(alias)
            connections[alias] = connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user")
                if cursor.fetchone() != (name, "bk_test_runner"):
                    raise ImproperlyConfigured("Fixture connection identity mismatch")
            yield connection
        finally:
            try:
                if connection is not None:
                    connection.close()
            finally:
                connections[alias] = saved_connection
                connections.databases[alias] = saved_config
                verify_control_database(control)
                owner = control.execute(
                    "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s", (name,)
                ).fetchone()
                if owner != ("bk_test_runner",):
                    raise ImproperlyConfigured("Fixture ownership changed; refusing cleanup")
                # Drop only the UUID database created above. No FORCE or session kills.
                control.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
