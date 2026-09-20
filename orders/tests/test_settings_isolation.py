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
            from unittest.mock import patch

            before = dict(os.environ)
            def deny_network(*args, **kwargs):
                raise AssertionError('Test startup attempted network access')

            with patch.object(socket.socket, 'connect', deny_network), \
                 patch('psycopg.connect', side_effect=deny_network):
                import django
                django.setup()
                from django.conf import settings
                from django.core.management import call_command
                from django.db import connection

                assert dict(os.environ) == before, 'Settings mutated caller environment'
                assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql'
                assert settings.DATABASES['default']['NAME'] == 'bk_test_control'
                assert settings.DATABASES['default']['HOST'] == '127.0.0.1'
                assert settings.DATABASES['default']['USER'] == 'bk_test_runner'
                assert settings.DATABASES['default']['PASSWORD'] == 'synthetic-local-runner-only'
                assert settings.SECRET_KEY == 'synthetic-local-tests-only-not-a-deployment-secret-key'
                from django.contrib.auth.hashers import check_password
                assert check_password('test-event-password', settings.EVENT_PASSWORD_HASH)
                assert 'synthetic-deployment' not in settings.EVENT_PASSWORD_HASH
                assert settings.JWT_SIGNING_KEY != 'synthetic-deployment-jwt-key'
                assert settings.JWT_COOKIE_SECURE is False
                assert settings.LOGIN_MAX_FAILURES == 10
                assert settings.DEBUG is False
                assert settings.ALLOWED_HOSTS == ['testserver', 'localhost', '127.0.0.1']
                assert settings.CSRF_TRUSTED_ORIGINS == []
                # 4B2 removed these settings; the probe proves they cannot
                # come back through the environment.
                assert not hasattr(settings, 'SUPABASE_URL')
                assert not hasattr(settings, 'SUPABASE_ANON_KEY')
                assert settings.CACHES['default']['BACKEND'].endswith('.LocMemCache')
                assert settings.STORAGES['default']['BACKEND'].endswith('.InMemoryStorage')
                call_command('check', verbosity=0)
                assert connection.connection is None
        """)
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "bazaar_kiosk.settings_test_pg",
            "BK_TEST_DATABASE_URL": "postgresql://bk_test_runner:synthetic-local-runner-only@127.0.0.1:55437/bk_test_control",
            # Invalid scheme proves production settings never parse this value.
            "DATABASE_URL": "invalid://synthetic-deployment-db.invalid/db",
            "DATABASE_URL_FILE": "/must-not-read-deployment-secret",
            "SECRET_KEY": "synthetic-deployment-secret",
            "EVENT_PASSWORD_HASH": "invalid synthetic-deployment-hash",
            "JWT_SIGNING_KEY": "synthetic-deployment-jwt-key",
            "LOGIN_MAX_FAILURES": "99999",
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
