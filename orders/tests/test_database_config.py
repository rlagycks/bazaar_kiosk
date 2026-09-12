"""PostgreSQL-only startup and numbering: reject fallback before any DB access."""

import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock, patch

from django.db import NotSupportedError
from django.test import SimpleTestCase

from orders.services import numbering


class DatabaseConfigTests(SimpleTestCase):
    def probe(self, url):
        script = """
import json
from django.core.exceptions import ImproperlyConfigured
try:
    from bazaar_kiosk.settings import DATABASES
except ImproperlyConfigured as exc:
    print(json.dumps({'error': str(exc)}))
else:
    config = DATABASES['default']
    print(json.dumps({k: config[k] for k in ('ENGINE','NAME','HOST','PORT')}))
"""
        env = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
        env['DATABASE_URL'] = url
        result = subprocess.run(
            [sys.executable, '-c', script], env=env,
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_missing_sqlite_and_incomplete_urls_are_rejected(self):
        for url in ('', '  ', 'sqlite:///db.sqlite3', 'postgresql:///db',
                    'postgresql://runner:secret-marker@localhost:wrong/db',
                    'postgresql://runner:secret-marker@localhost:5432/'):
            with self.subTest(url=url):
                result = self.probe(url)
                self.assertIn('error', result)
                self.assertNotIn('secret-marker', result['error'])

    def test_postgresql_url_selects_only_postgresql_backend(self):
        self.assertEqual(self.probe('postgresql://runner:synthetic@127.0.0.1:55436/bazaar_dev?sslmode=disable'), {
            'ENGINE': 'django.db.backends.postgresql', 'NAME': 'bazaar_dev',
            'HOST': '127.0.0.1', 'PORT': '55436',
        })

    def test_numbering_rejects_unsupported_backend_without_fallback(self):
        connection = Mock(vendor='sqlite')
        with patch.object(numbering, 'connection', connection):
            with self.assertRaises(NotSupportedError):
                numbering.allocate_floor_order_no(Mock())
        connection.cursor.assert_not_called()
