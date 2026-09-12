"""Guard project discovery and never adopt an existing application test DB."""

import unittest
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import SimpleTestCase

from scripts.test_postgres import partition_suite, verify_target


class PostgreSQLRunnerTests(SimpleTestCase):
    def test_nested_application_tests_remain_in_the_discovery_partition(self):
        class NamedCase(unittest.TestCase):
            def __init__(self, name):
                super().__init__()
                self.name = name

            def id(self):
                return self.name

        migration = NamedCase('orders.tests.test_migration_paths.Paths.test_fresh')
        nested = NamedCase('another_app.tests.nested.Cases.test_behavior')
        suite = unittest.TestSuite([unittest.TestSuite([migration]), unittest.TestSuite([nested])])
        self.assertEqual(partition_suite(suite), ([migration.id()], [nested.id()]))
        with self.assertRaisesRegex(RuntimeError, 'nonempty'):
            partition_suite(unittest.TestSuite([nested]))

    def test_existing_application_database_is_rejected_without_writes(self):
        control = MagicMock()
        control.execute.return_value.fetchone.side_effect = [
            ('bk_test_control', 'bk_test_runner', True, 'bazaar-kiosk-phase-1a-local-only',
             False, True, False, False, False, 150018),
            (1,),
        ]
        with patch('psycopg.connect') as connect:
            connect.return_value.__enter__.return_value = control
            with self.assertRaisesRegex(RuntimeError, 'already exists'):
                verify_target(settings.DATABASES['default'])
        self.assertTrue(all(call.args[0].lstrip().startswith('SELECT')
                            for call in control.execute.call_args_list))

    def test_unverified_target_stops_before_app_database_lookup(self):
        control = MagicMock()
        control.execute.return_value.fetchone.return_value = None
        from django.core.exceptions import ImproperlyConfigured
        with patch('psycopg.connect') as connect:
            connect.return_value.__enter__.return_value = control
            with self.assertRaises(ImproperlyConfigured):
                verify_target(settings.DATABASES['default'])
        self.assertEqual(control.execute.call_count, 1)
