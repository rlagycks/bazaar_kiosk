"""4A3: how a deployment hands the app its secrets, and what it exposes.

D-046 decided the deployment shape: one Docker Compose stack on EC2, secrets
delivered as files, the database reachable only on the internal network, and a
single database role. These tests pin the parts of that contract that live in
this repository -- the settings reader and the deployment candidate files --
because none of it is exercised by the application tests.

Like test_required_settings, the settings cases boot a fresh interpreter: this
module's settings are already imported and cached, so asserting on them here
would prove nothing about what a deployment reads at startup.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from django.test import SimpleTestCase
from orders.tests.auth_support import ROLE_ACCOUNTS

REPO_ROOT = Path(__file__).resolve().parents[2]

DEPLOYMENT = {
    "DEBUG": "0",
    "SECRET_KEY": "synthetic-deployment-secret-long-enough-to-clear-the-length-floor",
    "ALLOWED_HOSTS": "deployment.invalid",
    "CSRF_TRUSTED_ORIGINS": "https://deployment.invalid",
    "ROLE_ACCOUNTS": json.dumps(ROLE_ACCOUNTS),
    "JWT_SIGNING_KEY": "synthetic-jwt-signing-key-distinct-and-at-least-fifty-characters",
    "DATABASE_URL": "postgresql://runner:synthetic-probe-password@127.0.0.1:5432/synthetic",
}

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
        "secret_key": s.SECRET_KEY,
        "jwt_signing_key": s.JWT_SIGNING_KEY,
        "roles": sorted(s.ROLE_ACCOUNTS),
        "db_name": s.DATABASES["default"]["NAME"],
        "db_user": s.DATABASES["default"]["USER"],
    }))
"""


class SecretFileSettingsTests(SimpleTestCase):
    """A deployment supplies secrets as files, not environment variables."""

    def boot(self, files=None, **overrides):
        """Start settings in a clean interpreter. None unsets a variable.

        `files` maps a variable name to file content; each becomes a real file
        and its path is passed as `<NAME>_FILE`.
        """
        env = {
            k: v for k, v in os.environ.items()
            if not k.startswith("PG") and k not in ("DJANGO_SETTINGS_MODULE",)
        }
        env.pop("DEBUG", None)
        with tempfile.TemporaryDirectory() as directory:
            for name, content in (files or {}).items():
                path = Path(directory) / name.lower()
                path.write_text(content, encoding="utf-8")
                env[name + "_FILE"] = str(path)
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

    def test_every_deployment_secret_can_arrive_as_a_file(self):
        """The whole point of D-046's file delivery: a value that never appears
        in the process environment, where `docker inspect` and a crash dump of
        os.environ would carry it."""
        result = self.boot(
            files={
                "SECRET_KEY": DEPLOYMENT["SECRET_KEY"],
                "JWT_SIGNING_KEY": DEPLOYMENT["JWT_SIGNING_KEY"],
                "ROLE_ACCOUNTS": DEPLOYMENT["ROLE_ACCOUNTS"],
                "DATABASE_URL": DEPLOYMENT["DATABASE_URL"],
            },
            SECRET_KEY=None, JWT_SIGNING_KEY=None, ROLE_ACCOUNTS=None, DATABASE_URL=None,
        )
        self.assertTrue(result.get("started"), result)
        self.assertEqual(result["secret_key"], DEPLOYMENT["SECRET_KEY"])
        self.assertEqual(result["jwt_signing_key"], DEPLOYMENT["JWT_SIGNING_KEY"])
        self.assertEqual(result["roles"], sorted(ROLE_ACCOUNTS))
        self.assertEqual(result["db_name"], "synthetic")
        self.assertEqual(result["db_user"], "runner")

    def test_a_trailing_newline_in_the_file_is_not_part_of_the_secret(self):
        """Every editor and most secret managers end a file with a newline. A
        signing key or password that silently carries it fails authentication
        in a way that looks like a wrong credential."""
        result = self.boot(
            files={"JWT_SIGNING_KEY": DEPLOYMENT["JWT_SIGNING_KEY"] + "\n"},
            JWT_SIGNING_KEY=None,
        )
        self.assertTrue(result.get("started"), result)
        self.assertEqual(result["jwt_signing_key"], DEPLOYMENT["JWT_SIGNING_KEY"])

    def test_setting_both_the_variable_and_the_file_is_refused(self):
        """Picking one silently is how a rotated secret in the file is ignored
        because a stale environment variable won. Neither order is obvious
        enough to guess on a deployment's behalf."""
        result = self.boot(files={"JWT_SIGNING_KEY": DEPLOYMENT["JWT_SIGNING_KEY"]})
        self.assertIn("refused", result)
        self.assertIn("JWT_SIGNING_KEY", result["refused"])

    def test_an_unreadable_secret_file_refuses_to_start(self):
        """A missing mount must not degrade into "unset", which for DEBUG=0
        means the deployment refusal names a variable the operator did set --
        and for a value with a default would mean running on the default."""
        result = self.boot(SECRET_KEY=None, **{"SECRET_KEY_FILE": "/nonexistent/secret-key"})
        self.assertIn("refused", result)
        self.assertIn("SECRET_KEY_FILE", result["refused"])

    def test_the_refusal_never_prints_the_file_content(self):
        """Same property test_required_settings pins for the environment: the
        message travels to logs, so the secret must not travel with it."""
        result = self.boot(files={"SECRET_KEY": DEPLOYMENT["SECRET_KEY"]})
        self.assertIn("refused", result)
        self.assertNotIn(DEPLOYMENT["SECRET_KEY"], result["refused"])


class DeploymentCandidateTests(SimpleTestCase):
    """What compose.prod.yaml exposes. D-046: only the proxy is published."""

    def setUp(self):
        # PyYAML is pinned in requirements-ci.txt for this test. Skipping when
        # it is absent would turn the exposure checks below into a silent pass.
        import yaml

        self.text = (REPO_ROOT / "compose.prod.yaml").read_text(encoding="utf-8")
        self.compose = yaml.safe_load(self.text)

    def test_only_the_proxy_publishes_a_port(self):
        """BK-R044 is about the database and the application server being
        reachable from the internet. A published port on either is exactly
        that, and it is one line in a compose file."""
        published = {
            name: service.get("ports")
            for name, service in self.compose["services"].items()
            if service.get("ports")
        }
        self.assertEqual(sorted(published), ["proxy"])

    def test_the_application_and_database_stay_on_an_internal_network(self):
        for name in ("app", "postgres"):
            with self.subTest(service=name):
                self.assertIn("internal", self.compose["services"][name]["networks"])
        self.assertIs(self.compose["networks"]["internal"]["internal"], True)

    def test_no_secret_value_is_written_into_the_candidate(self):
        """The file is committed. D-046 delivers secrets as mounted files, so
        the compose file names paths and never values."""
        for name in ("SECRET_KEY=", "JWT_SIGNING_KEY=", "ROLE_ACCOUNTS=",
                     "DATABASE_URL=", "POSTGRES_PASSWORD:"):
            with self.subTest(fragment=name):
                self.assertNotIn(name, self.text)
        for name in ("SECRET_KEY_FILE", "JWT_SIGNING_KEY_FILE",
                     "ROLE_ACCOUNTS_FILE", "DATABASE_URL_FILE"):
            with self.subTest(variable=name):
                self.assertIn(name, self.text)

    def test_the_application_trusts_forwarded_headers_only_from_the_proxy(self):
        """Issue #61: gunicorn leaves REMOTE_ADDR as the socket peer, so behind
        this proxy the login throttle needs the proxy named explicitly or every
        failure in the world shares one bucket. A wildcard is the other
        failure: anyone could then choose their own bucket."""
        app = self.compose["services"]["app"]
        trusted = app["environment"]["TRUSTED_PROXY_IPS"]
        self.assertIn("10.89.0.10", trusted)
        self.assertNotIn("*", trusted)
        self.assertNotIn("0.0.0.0/0", trusted)
        # The forwarded scheme is what lets the app know the request was HTTPS.
        self.assertIn("--forwarded-allow-ips", app["command"])
        self.assertNotIn("--forwarded-allow-ips=*", app["command"])

    def test_the_proxy_replaces_any_inbound_forwarded_header(self):
        """The trust boundary above is only worth anything if the proxy sets the
        header from the peer it saw rather than passing the client's through."""
        conf = (REPO_ROOT / "scripts" / "nginx_prod.conf").read_text(encoding="utf-8")
        self.assertIn("proxy_set_header X-Forwarded-For $remote_addr;", conf)
        self.assertNotIn("$proxy_add_x_forwarded_for", conf)

    def test_the_database_role_cannot_create_databases_or_roles(self):
        """D-046 keeps one role, so it owns its schema and can change it. It
        still must not be able to reach outside its own database."""
        init = (REPO_ROOT / "scripts" / "pg_prod_init.sql").read_text(encoding="utf-8")
        for clause in ("NOSUPERUSER", "NOCREATEDB", "NOCREATEROLE",
                       "NOREPLICATION", "NOBYPASSRLS"):
            with self.subTest(clause=clause):
                self.assertIn(clause, init)
        self.assertNotIn("PASSWORD '", init)
