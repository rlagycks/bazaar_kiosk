"""Negative target guards run without PostgreSQL or any DB connection."""

import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from .pg_support import verify_control_database
from . import pg_support


class PostgreSQLTargetGuardTests(SimpleTestCase):
    def test_invalid_urls_and_libpq_overrides_fail_before_connecting(self):
        good = (
            "postgresql://bk_test_runner:synthetic-local-runner-only"
            "@127.0.0.1:55437/bk_test_control"
        )
        cases = [
            ("", {}),
            (good.replace("127.0.0.1", "db.example.invalid"), {}),
            (good.replace("bk_test_control", "production"), {}),
            (good.replace("bk_test_runner", "postgres"), {}),
            (good.replace(":55437", ""), {}),
            (good.replace(":55437", ":wrong"), {}),
            (good + "?host=remote.invalid", {}),
            (good + "#ignored", {}),
            (good, {"PGHOSTADDR": "192.0.2.1"}),
            (good, {"PGSERVICE": "production"}),
            (good, {"PGOPTIONS": "-c search_path=public"}),
        ]
        probe = """
import os
from unittest.mock import patch
from django.core.exceptions import ImproperlyConfigured
with patch('psycopg.connect', side_effect=AssertionError('unexpected connection')):
    try:
        import bazaar_kiosk.settings_test_pg
    except ImproperlyConfigured as exc:
        assert 'synthetic-local-runner-only' not in str(exc)
    else:
        raise AssertionError('unsafe configuration was accepted')
"""
        base_env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
        for index, (url, extra) in enumerate(cases):
            with self.subTest(case=index):
                result = subprocess.run(
                    [sys.executable, "-c", probe],
                    cwd=Path(__file__).resolve().parents[2],
                    env={**base_env, "BK_TEST_DATABASE_URL": url, **extra},
                    capture_output=True, text=True, timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_server_identity_owner_marker_and_privileges_are_required(self):
        valid = [
            "bk_test_control", "bk_test_runner", True,
            "bazaar-kiosk-phase-1a-local-only", False, True, False, False, False, 150018,
        ]
        control = Mock()
        control.execute.return_value.fetchone.return_value = tuple(valid)
        verify_control_database(control)
        for index, bad in enumerate([
            "other_db", "other_role", False, "missing-marker", True,
            False, True, True, True, 160000,
        ]):
            with self.subTest(field=index):
                row = valid.copy()
                row[index] = bad
                control.execute.return_value.fetchone.return_value = tuple(row)
                with self.assertRaisesMessage(ImproperlyConfigured, "unverified"):
                    verify_control_database(control)
        control.execute.return_value.fetchone.return_value = None
        with self.assertRaises(ImproperlyConfigured):
            verify_control_database(control)

    def test_close_failures_restore_default_and_limit_cleanup_to_owned_database(self):
        url = (
            "postgresql://bk_test_runner:synthetic-local-runner-only"
            "@127.0.0.1:55437/bk_test_control"
        )
        name = "bk_test_migration_" + "a" * 32
        for failure in ("saved_close", "fixture_close", "ownership_changed"):
            with self.subTest(failure=failure), patch.dict(
                os.environ, {"BK_TEST_DATABASE_URL": url}, clear=True
            ):
                from bazaar_kiosk.settings_test_pg import test_database_config

                config = test_database_config(url)
                saved = Mock(settings_dict=config)
                fresh = MagicMock()
                fresh.cursor.return_value.__enter__.return_value.fetchone.return_value = (
                    name, "bk_test_runner"
                )
                registry = MagicMock()
                registry.databases = {"default": config}
                registry.__getitem__.return_value = saved
                registry.create_connection.return_value = fresh
                control = MagicMock()
                control.execute.return_value.fetchone.return_value = (
                    "other_owner" if failure == "ownership_changed" else "bk_test_runner",
                )
                if failure == "saved_close":
                    saved.close.side_effect = RuntimeError("synthetic close failure")
                elif failure == "fixture_close":
                    fresh.close.side_effect = RuntimeError("synthetic close failure")
                fake_settings = Mock(
                    SETTINGS_MODULE="bazaar_kiosk.settings_test_pg",
                    DATABASES={"default": config},
                )
                expected_error = (
                    ImproperlyConfigured if failure == "ownership_changed" else RuntimeError
                )
                with (
                    patch.object(pg_support, "settings", fake_settings),
                    patch.object(pg_support, "connections", registry),
                    patch.object(pg_support, "verify_control_database"),
                    patch.object(pg_support.uuid, "uuid4", return_value=Mock(hex="a" * 32)),
                    patch.object(pg_support.psycopg, "connect") as connect,
                ):
                    connect.return_value.__enter__.return_value = control
                    with self.assertRaises(expected_error):
                        with pg_support.migration_database():
                            pass
                self.assertIs(registry.databases["default"], config)
                if failure == "saved_close":
                    control.execute.assert_not_called()
                    registry.__setitem__.assert_not_called()
                    continue
                registry.__setitem__.assert_called_with("default", saved)
                statements = [
                    call.args[0] if isinstance(call.args[0], str) else call.args[0].as_string()
                    for call in control.execute.call_args_list
                ]
                self.assertEqual(statements[0], f'CREATE DATABASE "{name}" TEMPLATE template0')
                drops = [statement for statement in statements if statement.startswith("DROP")]
                self.assertEqual(
                    drops, [f'DROP DATABASE "{name}"'] if failure == "fixture_close" else []
                )
