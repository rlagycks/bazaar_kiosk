"""Exercise settings startup in a fresh process with hostile synthetic env."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap

from django.test import SimpleTestCase


class SettingsIsolationTests(SimpleTestCase):
    def test_deployment_environment_cannot_select_test_backends_or_credentials(self):
        probe = textwrap.dedent("""\
            import os
            import socket
            import sqlite3
            from unittest.mock import patch

            before = dict(os.environ)
            def deny_network(*args, **kwargs):
                raise AssertionError('Test startup attempted network access')

            real_connect = sqlite3.dbapi2.connect
            opened = []
            def memory_only(database, *args, **kwargs):
                assert database == ':memory:', 'Test attempted persistent DB access'
                opened.append(database)
                return real_connect(database, *args, **kwargs)

            with patch.object(socket.socket, 'connect', deny_network), \
                 patch('sqlite3.dbapi2.connect', side_effect=memory_only):
                import django
                django.setup()
                from django.conf import settings
                from django.core.management import call_command
                from django.db import connection

                assert dict(os.environ) == before, 'Settings mutated caller environment'
                assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'
                assert settings.DATABASES['default']['NAME'] == ':memory:'
                assert settings.DATABASES['default']['TEST']['NAME'] == ':memory:'
                assert settings.SECRET_KEY == 'synthetic-local-tests-only-not-a-deployment-secret-key'
                assert settings.ROLE_PINS['ORDER'] == 'test-order'
                assert set(settings.ROLE_PINS.values()).isdisjoint({'synthetic-deployment-pin'})
                assert settings.DEBUG is False
                assert settings.ALLOWED_HOSTS == ['testserver', 'localhost', '127.0.0.1']
                assert settings.CSRF_TRUSTED_ORIGINS == []
                assert settings.SUPABASE_URL == settings.SUPABASE_ANON_KEY == ''
                assert settings.CACHES['default']['BACKEND'].endswith('.LocMemCache')
                assert settings.STORAGES['default']['BACKEND'].endswith('.InMemoryStorage')
                call_command('check', verbosity=0)
                with connection.cursor() as cursor:
                    cursor.execute('SELECT 1')
                    assert cursor.fetchone() == (1,)
                connection.close()
                assert opened == [':memory:']
        """)
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "bazaar_kiosk.settings_test",
            # Invalid scheme proves production settings never parse this value.
            "DATABASE_URL": "invalid://synthetic-deployment-db.invalid/db",
            "DATABASE_URL_FILE": "/must-not-read-deployment-secret",
            "SECRET_KEY": "synthetic-deployment-secret",
            "ROLE_PINS": "ORDER:synthetic-deployment-pin",
            "DEBUG": "1",
            "ALLOWED_HOSTS": "deployment.invalid",
            "CSRF_TRUSTED_ORIGINS": "https://deployment.invalid",
            "SUPABASE_URL": "https://deployment.invalid",
            "SUPABASE_ANON_KEY": "synthetic-deployment-key",
        }
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
