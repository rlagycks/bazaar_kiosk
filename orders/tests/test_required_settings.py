"""D-039: a deployment missing required configuration must refuse to start.

Booting settings in this process would prove nothing -- the module is already
imported and cached. Every case below starts a fresh interpreter with a hostile
synthetic environment and reads what it printed.

These are the values BK-R002 and BK-R028 are about: the published demo PINs and
the development secret. Falling back to them silently is how they reach a public
host, so "unset" and "still the published default" have to fail the same way.
"""

import json
import os
from pathlib import Path
import subprocess
import sys

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[2]

# The synthetic stand-ins a correctly configured deployment would use. None of
# these is a real credential and none is read by anything but this probe.
DEPLOYMENT = {
    "DEBUG": "0",
    "SECRET_KEY": "synthetic-deployment-secret-long-enough-for-a-probe",
    "ALLOWED_HOSTS": "deployment.invalid",
    "CSRF_TRUSTED_ORIGINS": "https://deployment.invalid",
    "ROLE_PINS": "ORDER:synthetic-order,B1_COUNTER:synthetic-counter,KITCHEN:synthetic-kitchen",
    "DATABASE_URL": "postgresql://runner:synthetic-probe-password@127.0.0.1:5432/synthetic",
}

PUBLISHED_DEMO_PINS = (
    "ORDER:1001,B1_COUNTER:2001,KITCHEN:3001,KITCHEN_HALL:4001,KITCHEN_TAKEOUT:5001"
)
DEV_SECRET_KEY = "dev-only-not-for-prod"

PROBE = """
import json
from django.core.exceptions import ImproperlyConfigured
try:
    import bazaar_kiosk.settings as s
except ImproperlyConfigured as exc:
    print(json.dumps({"refused": str(exc)}))
else:
    print(json.dumps({"started": True, "debug": s.DEBUG}))
"""


class RequiredSettingsTests(SimpleTestCase):
    def boot(self, **overrides):
        """Start settings in a clean interpreter. A value of None unsets."""
        env = {
            k: v for k, v in os.environ.items()
            # libpq vars and a leftover settings module would steer the probe.
            if not k.startswith("PG") and k not in ("DJANGO_SETTINGS_MODULE",)
        }
        env.pop("DEBUG", None)
        for key, value in {**DEPLOYMENT, **overrides}.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        result = subprocess.run(
            [sys.executable, "-c", PROBE], env=env, cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    # --- the probe itself has to be able to succeed ----------------------

    def test_a_fully_configured_deployment_starts(self):
        """The positive control. Without it every refusal below could be
        caused by the probe rather than by the setting under test."""
        self.assertEqual(self.boot(), {"started": True, "debug": False})

    def test_development_is_untouched(self):
        """The refusal is a deployment gate. DEBUG=1 with nothing else set must
        still start, or local work stops."""
        result = self.boot(
            DEBUG="1", SECRET_KEY=None, ALLOWED_HOSTS=None,
            CSRF_TRUSTED_ORIGINS=None, ROLE_PINS=None,
        )
        self.assertEqual(result, {"started": True, "debug": True})

    # --- DEBUG has no default --------------------------------------------

    def test_an_unstated_debug_refuses_to_start(self):
        """A default of "on" would let a deployment that sets nothing run with
        development values and never reach the checks below."""
        for value in (None, "", "true", "True", "yes", "2", " 0"):
            with self.subTest(debug=value):
                result = self.boot(DEBUG=value)
                self.assertIn("refused", result)
                self.assertIn("DEBUG", result["refused"])

    # --- each required setting, one at a time -----------------------------

    def test_each_required_setting_is_required_on_its_own(self):
        """One at a time, with everything else valid. Checking them only in
        combination would not show which ones are actually enforced."""
        for name in ("SECRET_KEY", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS", "ROLE_PINS"):
            for value in (None, ""):
                with self.subTest(setting=name, value=value):
                    result = self.boot(**{name: value})
                    self.assertIn("refused", result, f"{name}={value!r} started anyway")
                    self.assertIn(name, result["refused"])

    def test_the_published_demo_credentials_are_refused_even_when_set(self):
        """Unset and "still the value printed in this repository" are the same
        failure. Requiring only presence would accept a copied .env.example."""
        for name, value in (("ROLE_PINS", PUBLISHED_DEMO_PINS),
                            ("SECRET_KEY", DEV_SECRET_KEY)):
            with self.subTest(setting=name):
                result = self.boot(**{name: value})
                self.assertIn("refused", result, f"{name} default was accepted")
                self.assertIn(name, result["refused"])

    def test_a_malformed_role_pins_string_is_refused(self):
        """A value that parses to nothing leaves every role unloginable, which
        looks like a broken app rather than a configuration mistake."""
        result = self.boot(ROLE_PINS="no-colons-here")
        self.assertIn("refused", result)
        self.assertIn("ROLE_PINS", result["refused"])

    # --- the refusal must not become the leak -----------------------------

    def test_the_refusal_names_the_variable_and_never_the_value(self):
        """This exception can reach an error report, and the values are exactly
        what BK-R028 says must not appear there."""
        result = self.boot(ALLOWED_HOSTS=None)
        self.assertIn("refused", result)
        message = result["refused"]
        for secret in (DEPLOYMENT["SECRET_KEY"], DEPLOYMENT["ROLE_PINS"],
                       DEPLOYMENT["DATABASE_URL"], "synthetic-probe-password",
                       "synthetic-order", "synthetic-counter", "synthetic-kitchen"):
            self.assertNotIn(secret, message)
        self.assertIn("ALLOWED_HOSTS", message)

    def test_the_refusal_lists_every_missing_setting_at_once(self):
        """Reporting one at a time would make a fresh deployment a guessing
        game of restart, read, fix, restart."""
        result = self.boot(
            SECRET_KEY=None, ALLOWED_HOSTS=None,
            CSRF_TRUSTED_ORIGINS=None, ROLE_PINS=None,
        )
        self.assertIn("refused", result)
        for name in ("SECRET_KEY", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS", "ROLE_PINS"):
            self.assertIn(name, result["refused"])

    # --- the example file is the thing the message points at --------------

    def test_the_example_file_documents_every_required_setting(self):
        """The refusal says "see .env.example". That is only useful if the file
        actually names them, and it holds no real value."""
        text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        for name in ("DEBUG", "SECRET_KEY", "ALLOWED_HOSTS",
                     "CSRF_TRUSTED_ORIGINS", "ROLE_PINS", "DATABASE_URL"):
            with self.subTest(setting=name):
                self.assertIn(f"{name}=", text)
        self.assertIn("[필수]", text)
        self.assertIn("[생성]", text)
        # A generation procedure, since D-039 said keys that can just be
        # generated should not be something the operator has to invent.
        self.assertIn("secrets.token_urlsafe", text)
