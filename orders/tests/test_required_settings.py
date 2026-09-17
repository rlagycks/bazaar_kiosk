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
from orders.tests.auth_support import ROLE_ACCOUNTS

REPO_ROOT = Path(__file__).resolve().parents[2]

# The synthetic stand-ins a correctly configured deployment would use. None of
# these is a real credential and none is read by anything but this probe.
DEPLOYMENT = {
    "DEBUG": "0",
    "SECRET_KEY": "synthetic-deployment-secret-long-enough-to-clear-the-length-floor",
    "ALLOWED_HOSTS": "deployment.invalid",
    "CSRF_TRUSTED_ORIGINS": "https://deployment.invalid",
    "ROLE_ACCOUNTS": json.dumps(ROLE_ACCOUNTS),
    "JWT_SIGNING_KEY": "synthetic-jwt-signing-key-distinct-and-at-least-fifty-characters",
    "DATABASE_URL": "postgresql://runner:synthetic-probe-password@127.0.0.1:5432/synthetic",
}

PUBLISHED_DEMO_PINS = (
    "ORDER:1001,B1_COUNTER:2001,KITCHEN:3001,KITCHEN_HALL:4001,KITCHEN_TAKEOUT:5001"
)
DEV_SECRET_KEY = "dev-only-not-for-prod"
# What .env.example actually ships. Someone who copies that file and fills in
# the rest carries this one to the server, so it is the likeliest of the two.
EXAMPLE_FILE_SECRET_KEY = "replace-with-a-long-random-development-secret"

PROBE = """
import json
from django.core.exceptions import ImproperlyConfigured
try:
    import bazaar_kiosk.settings as s
except ImproperlyConfigured as exc:
    print(json.dumps({"refused": str(exc)}))
else:
    print(json.dumps({
        "started": True,
        "debug": s.DEBUG,
        "roles": sorted(s.ROLE_ACCOUNTS),
        # The deployment-only security block. Reporting it here is what lets a
        # test assert those cookies are actually hardened; nothing else in the
        # repository boots real settings with DEBUG off.
        "session_cookie_secure": getattr(s, "SESSION_COOKIE_SECURE", None),
        "csrf_cookie_secure": getattr(s, "CSRF_COOKIE_SECURE", None),
        "proxy_ssl_header": getattr(s, "SECURE_PROXY_SSL_HEADER", None),
        "login_policy": [s.LOGIN_MAX_FAILURES, s.LOGIN_WINDOW_SECONDS, s.LOGIN_BLOCK_SECONDS],
    }))
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
        result = self.boot()
        self.assertTrue(result.get("started"), result)
        self.assertIs(result["debug"], False)

    def test_a_deployment_hardens_the_cookies(self):
        """The DEBUG=0 branch that sets these has never been exercised: the test
        profile overrides all three to off. This is the only place real settings
        boot as a deployment, so it is the only place that can check them."""
        result = self.boot()
        self.assertIs(result["session_cookie_secure"], True)
        self.assertIs(result["csrf_cookie_secure"], True)
        self.assertEqual(result["proxy_ssl_header"], ["HTTP_X_FORWARDED_PROTO", "https"])

    def test_development_is_untouched(self):
        """The refusal is a deployment gate. DEBUG=1 with nothing else set must
        still start, or local work stops."""
        result = self.boot(
            DEBUG="1", SECRET_KEY=None, ALLOWED_HOSTS=None,
            CSRF_TRUSTED_ORIGINS=None, ROLE_PINS=None,
        )
        self.assertTrue(result.get("started"), result)
        self.assertIs(result["debug"], True)

    # --- DEBUG has no default --------------------------------------------

    def test_an_unstated_debug_refuses_to_start(self):
        """A default of "on" would let a deployment that sets nothing run with
        development values and never reach the checks below."""
        for value in (None, "", "true", "True", "yes", "2", " 0"):
            with self.subTest(debug=value):
                result = self.boot(DEBUG=value)
                self.assertIn("refused", result)
                # The deployment refusal also contains the substring "DEBUG=0",
                # so match the phrase only this refusal uses.
                self.assertIn("has no default", result["refused"])

    # --- each required setting, one at a time -----------------------------

    def test_each_required_setting_is_required_on_its_own(self):
        """One at a time, with everything else valid. Checking them only in
        combination would not show which ones are actually enforced."""
        for name in ("SECRET_KEY", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS",
                     "ROLE_ACCOUNTS", "JWT_SIGNING_KEY", "DATABASE_URL"):
            for value in (None, ""):
                with self.subTest(setting=name, value=value):
                    result = self.boot(**{name: value})
                    self.assertIn("refused", result, f"{name}={value!r} started anyway")
                    self.assertIn(name, result["refused"])

    def test_the_published_demo_credentials_are_refused_even_when_set(self):
        """Unset and "still the value printed in this repository" are the same
        failure. Requiring only presence would accept a copied .env.example."""
        for name, value in (("SECRET_KEY", DEV_SECRET_KEY),
                            ("SECRET_KEY", EXAMPLE_FILE_SECRET_KEY)):
            with self.subTest(setting=name, value=value):
                result = self.boot(**{name: value})
                self.assertIn("refused", result, f"{name}={value!r} was accepted")
                self.assertIn(name, result["refused"])

    def test_invalid_account_configuration_is_refused(self):
        good = ROLE_ACCOUNTS["ORDER"]
        cases = {
            "invalid JSON": "not-json",
            "empty mapping": "{}",
            "non mapping": "[]",
            "blank id": json.dumps({"ORDER": {**good, "id": ""}}),
            "blank hash": json.dumps({"ORDER": {**good, "password_hash": ""}}),
            "plaintext": json.dumps({"ORDER": {**good, "password_hash": "synthetic-password"}}),
            "unusable": json.dumps({"ORDER": {**good, "password_hash": "!unusable"}}),
            "unknown role": json.dumps({"ADMIN": good}),
            "duplicate ids": json.dumps({"ORDER": good, "KITCHEN": good}),
        }
        for label, value in cases.items():
            with self.subTest(case=label):
                self.assertIn("ROLE_ACCOUNTS", self.boot(ROLE_ACCOUNTS=value).get("refused", ""))

    def test_malformed_pbkdf2_digest_is_refused_without_leaking_it(self):
        # A recognizable algorithm label does not make the digest usable.
        for digest in ("%%%synthetic-invalid-base64%%%", "YQ==", "A" * 48):
            encoded = "pbkdf2_sha256$1$synthetic-salt$" + digest
            raw = json.dumps({"ORDER": {"id": "synthetic-order", "password_hash": encoded}})
            with self.subTest(digest=digest):
                result = self.boot(ROLE_ACCOUNTS=raw)
                self.assertIn("ROLE_ACCOUNTS", result.get("refused", ""))
                self.assertNotIn(encoded, result["refused"])

    def test_duplicate_json_keys_are_refused(self):
        account = json.dumps(ROLE_ACCOUNTS["ORDER"])
        encoded = json.dumps(ROLE_ACCOUNTS["ORDER"]["password_hash"])
        cases = (
            '{"ORDER":' + account + ',"ORDER":' + account + '}',
            '{"ORDER":{"id":"first","id":"second","password_hash":' + encoded + '}}',
        )
        for raw in cases:
            with self.subTest(raw=raw):
                result = self.boot(ROLE_ACCOUNTS=raw)
                self.assertIn("ROLE_ACCOUNTS", result.get("refused", ""))

    def test_retired_kitchen_roles_are_refused_at_startup(self):
        for role in ("KITCHEN_HALL", "KITCHEN_TAKEOUT"):
            with self.subTest(role=role):
                result = self.boot(ROLE_ACCOUNTS=json.dumps({role: ROLE_ACCOUNTS["KITCHEN"]}))
                self.assertIn("ROLE_ACCOUNTS", result.get("refused", ""))

    def test_a_deployment_with_a_withdrawn_role_still_starts(self):
        for roles in (("ORDER", "KITCHEN"), ("B1_COUNTER",)):
            result = self.boot(ROLE_ACCOUNTS=json.dumps({role: ROLE_ACCOUNTS[role] for role in roles}))
            self.assertTrue(result.get("started"), result)
            self.assertEqual(result["roles"], sorted(roles))

    def test_jwt_key_must_be_strong_and_distinct(self):
        for value in (" ", "x" * 49, DEPLOYMENT["SECRET_KEY"]):
            with self.subTest(value=value):
                self.assertIn("JWT_SIGNING_KEY", self.boot(JWT_SIGNING_KEY=value).get("refused", ""))
        self.assertTrue(self.boot(JWT_SIGNING_KEY="b" * 50).get("started"))

    def test_login_limit_is_the_approved_policy_and_not_an_environment_setting(self):
        """D-045: 10 failures within 5 minutes block for 5 minutes. The number
        was an operator input only while the policy was undecided; a deployment
        must neither need it nor be able to weaken it through the environment."""
        for value in (None, "0", "-1", "nonnumeric", "99999"):
            with self.subTest(value=value):
                result = self.boot(LOGIN_MAX_FAILURES=value)
                self.assertTrue(result.get("started"), result)
                self.assertEqual(result["login_policy"], [10, 300, 300])

    def test_a_short_or_blank_secret_key_is_refused(self):
        """Set-but-worthless is not configured. Django's own check --deploy
        uses 50 characters, so this uses the same threshold."""
        for value in (" ", "x", "short", "a" * 49):
            with self.subTest(secret_key=value):
                result = self.boot(SECRET_KEY=value)
                self.assertIn("refused", result, f"{value!r} was accepted")
                self.assertIn("SECRET_KEY", result["refused"])
        self.assertTrue(self.boot(SECRET_KEY="b" * 50).get("started"))

    def test_a_wildcard_allowed_hosts_is_refused(self):
        """The reason DEBUG has no default is to keep ALLOWED_HOSTS=['*'] off a
        public host. Accepting a literal '*' would permit by hand exactly what
        that refuses by accident."""
        for value in ("*", "example.com,*"):
            with self.subTest(allowed_hosts=value):
                result = self.boot(ALLOWED_HOSTS=value)
                self.assertIn("refused", result, f"{value!r} was accepted")
                self.assertIn("ALLOWED_HOSTS", result["refused"])

    def test_a_schemeless_csrf_origin_is_refused(self):
        """Django reports this only through a system check, and gunicorn does
        not run system checks at boot. Without the refusal the app starts and
        silently rejects the origins it was configured to trust."""
        for value in ("example.com", "https://ok.invalid,bad.invalid"):
            with self.subTest(origins=value):
                result = self.boot(CSRF_TRUSTED_ORIGINS=value)
                self.assertIn("refused", result, f"{value!r} was accepted")
                self.assertIn("CSRF_TRUSTED_ORIGINS", result["refused"])

    # --- the refusal must not become the leak -----------------------------

    def test_the_refusal_names_the_variable_and_never_the_value(self):
        """The message travels wherever a boot failure travels -- a process
        manager's log, a container inspector, a deploy transcript -- and the
        values are what BK-R028 says must not travel with it.

        Nothing renders a Django error report here: settings never finish
        importing, so the credential filter is not active either. That makes the
        message itself the only thing standing between these values and the log.
        """
        # The offending values first. Booting with only an *unset* setting
        # would leave nothing for a leaky message to echo, so a message that
        # printed exactly what it rejected would pass. These two are the
        # credentials BK-R028 is about, and both are non-empty.
        offenders = self.boot(
            ROLE_ACCOUNTS="synthetic-invalid-credential-config", SECRET_KEY=DEV_SECRET_KEY,
        )
        self.assertIn("refused", offenders)
        for value in ("synthetic-invalid-credential-config", DEV_SECRET_KEY):
            with self.subTest(offending=value):
                self.assertNotIn(value, offenders["refused"])

        # Then the correctly configured values, in case a message echoes a
        # setting other than the one it is complaining about.
        result = self.boot(ALLOWED_HOSTS=None)
        self.assertIn("refused", result)
        message = result["refused"]
        # DEBUG is excluded: the message states the mode on purpose and "0"
        # is not a credential.
        for name, value in DEPLOYMENT.items():
            if name == "DEBUG":
                continue
            with self.subTest(setting=name):
                self.assertNotIn(value, message)
        for fragment in ("synthetic-probe-password", "synthetic-order",
                         "synthetic-counter", "synthetic-kitchen",
                         "synthetic-hall", "synthetic-takeout",
                         "deployment.invalid"):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, message)
        for account in ROLE_ACCOUNTS.values():
            self.assertNotIn(account["password_hash"], message)
        self.assertIn("ALLOWED_HOSTS", message)

    def test_the_refusal_lists_every_missing_setting_at_once(self):
        """Reporting one at a time would make a fresh deployment a guessing
        game of restart, read, fix, restart. DATABASE_URL is included even
        though it is parsed later, so the very first refusal is complete."""
        result = self.boot(
            SECRET_KEY=None, ALLOWED_HOSTS=None, CSRF_TRUSTED_ORIGINS=None,
            ROLE_ACCOUNTS=None, JWT_SIGNING_KEY=None, DATABASE_URL=None,
        )
        self.assertIn("refused", result)
        for name in ("SECRET_KEY", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS",
                     "ROLE_ACCOUNTS", "JWT_SIGNING_KEY", "DATABASE_URL"):
            with self.subTest(setting=name):
                self.assertIn(name, result["refused"])

    # --- the example file is the thing the message points at --------------

    def test_the_example_file_documents_every_required_setting(self):
        """The refusal says "see .env.example". That is only useful if the file
        actually names them, and it holds no real value."""
        text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        # Anchored to the start of a line. A bare substring search is satisfied
        # by the name appearing inside a comment, so the property that makes
        # README's `cp .env.example .env; source .env` work -- that the file
        # actually *assigns* these -- would go unguarded.
        assignments = {
            line.split("=", 1)[0]
            for line in text.splitlines()
            if "=" in line and not line.lstrip().startswith("#")
        }
        for name in ("DEBUG", "SECRET_KEY", "ALLOWED_HOSTS",
                     "CSRF_TRUSTED_ORIGINS", "ROLE_ACCOUNTS", "JWT_SIGNING_KEY", "DATABASE_URL"):
            with self.subTest(setting=name):
                self.assertIn(name, assignments)
        self.assertIn("[필수]", text)
        self.assertIn("[생성]", text)
        # A generation procedure, since D-039 said keys that can just be
        # generated should not be something the operator has to invent.
        self.assertIn("secrets.token_urlsafe", text)
