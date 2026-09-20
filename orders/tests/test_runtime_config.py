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
from django.urls import reverse
from orders.tests.auth_support import EVENT_PASSWORD_HASH

REPO_ROOT = Path(__file__).resolve().parents[2]

DEPLOYMENT = {
    "DEBUG": "0",
    "SECRET_KEY": "synthetic-deployment-secret-long-enough-to-clear-the-length-floor",
    "ALLOWED_HOSTS": "deployment.invalid",
    "CSRF_TRUSTED_ORIGINS": "https://deployment.invalid",
    "EVENT_PASSWORD_HASH": EVENT_PASSWORD_HASH,
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
        "event_password_hash": s.EVENT_PASSWORD_HASH,
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
                "EVENT_PASSWORD_HASH": DEPLOYMENT["EVENT_PASSWORD_HASH"],
                "DATABASE_URL": DEPLOYMENT["DATABASE_URL"],
            },
            SECRET_KEY=None, JWT_SIGNING_KEY=None, EVENT_PASSWORD_HASH=None, DATABASE_URL=None,
        )
        self.assertTrue(result.get("started"), result)
        self.assertEqual(result["secret_key"], DEPLOYMENT["SECRET_KEY"])
        self.assertEqual(result["jwt_signing_key"], DEPLOYMENT["JWT_SIGNING_KEY"])
        self.assertEqual(result["event_password_hash"], EVENT_PASSWORD_HASH)
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

    def test_a_malformed_trusted_proxy_entry_refuses_to_start(self):
        """A typo here would otherwise raise inside the login view -- a 500 on
        every login attempt for as long as the value is set. It is exactly the
        kind of value that belongs in the startup refusal."""
        for value in ("not-an-ip", "10.0.0.0/33", "10.89.0.10x", "proxy.internal"):
            with self.subTest(value=value):
                result = self.boot(TRUSTED_PROXY_IPS=value)
                self.assertIn("refused", result)
                self.assertIn("TRUSTED_PROXY_IPS", result["refused"])

    def test_a_usable_trusted_proxy_entry_starts(self):
        for value in ("10.89.0.10", "10.89.0.0/24", "10.89.0.10, 2001:db8::1"):
            with self.subTest(value=value):
                self.assertTrue(self.boot(TRUSTED_PROXY_IPS=value).get("started"))

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
        for name in ("SECRET_KEY=", "JWT_SIGNING_KEY=", "EVENT_PASSWORD_HASH=",
                     "DATABASE_URL=", "POSTGRES_PASSWORD:"):
            with self.subTest(fragment=name):
                self.assertNotIn(name, self.text)
        for name in ("SECRET_KEY_FILE", "JWT_SIGNING_KEY_FILE",
                     "EVENT_PASSWORD_HASH_FILE", "DATABASE_URL_FILE"):
            with self.subTest(variable=name):
                self.assertIn(name, self.text)

    def test_the_application_trusts_forwarded_headers_only_from_the_proxy(self):
        """Issue #61: the server leaves REMOTE_ADDR as the socket peer, so
        behind this proxy the login throttle needs the proxy named explicitly
        or every failure in the world shares one bucket. A wildcard is the
        other failure: anyone could then choose their own bucket."""
        app = self.compose["services"]["app"]
        trusted = app["environment"]["TRUSTED_PROXY_IPS"]
        self.assertIn("10.89.0.10", trusted)
        self.assertNotIn("*", trusted)
        self.assertNotIn("0.0.0.0/0", trusted)

    def test_the_server_does_not_rewrite_the_client_address(self):
        """10A: the flag that quietly moves the issue #61 boundary.

        Unlike gunicorn, uvicorn's proxy-header handling replaces the client
        address with one taken from X-Forwarded-For -- and it is on unless
        switched off. With it on, `TRUSTED_PROXY_IPS` still produces the right
        answer, but by accident: the decision would have moved to a command
        line with nothing next to it saying so. `--forwarded-allow-ips` is
        absent for the same reason; it would read as a boundary that is not
        being enforced here.
        """
        command = self.app_command()
        self.assertIn("--no-proxy-headers", command)
        self.assertNotIn("--forwarded-allow-ips", command)

    def test_the_application_is_served_over_asgi(self):
        """BK-R035: a WSGI worker collects a streaming response and sends it
        as one body, so SSE cannot work on this stack at all. The entry point
        is the difference, and it is one word in a command."""
        command = self.app_command()
        self.assertIn("bazaar_kiosk.asgi:application", command)
        self.assertNotIn("wsgi", command)

    def test_the_system_checks_run_before_the_server_does(self):
        """Otherwise orders.E001 only ever runs in CI (PR #76 review).

        uvicorn does not run Django's checks, so without this the guard that
        refuses a synchronous middleware -- the one thing keeping the request
        path async -- would not fire on a worker that starts from a change
        which skipped CI."""
        command = self.app_command()
        self.assertIn("manage.py check", command)
        self.assertLess(command.index("manage.py check"),
                        command.index("uvicorn"))

    def app_command(self):
        command = self.compose["services"]["app"]["command"]
        return command if isinstance(command, str) else " ".join(command)

    def test_a_restart_cannot_wait_forever_on_an_open_stream(self):
        """A graceful shutdown waits for connections to close. A stream is a
        connection with no reason to, so the wait has to be bounded or a
        deploy never finishes."""
        self.assertIn("--timeout-graceful-shutdown", self.app_command())

    def test_the_proxy_does_not_buffer_the_streaming_path(self):
        """nginx collects a proxied response by default and delivers it when
        it ends. Against a stream that is indistinguishable from the WSGI
        behaviour 10A removed -- the frames exist and nobody receives them."""
        conf = (REPO_ROOT / "scripts" / "nginx_prod.conf").read_text(encoding="utf-8")
        stream = conf.split("location /orders/api/stream/")[1].split("}")[0]
        self.assertIn("proxy_buffering off;", stream)
        self.assertIn("proxy_read_timeout 1h;", stream)

    def test_every_streaming_route_is_inside_that_location(self):
        """The trap 10D1 walks into otherwise (PR #76 architecture review).

        The non-buffering settings are attached to a URL prefix, not to the
        views that need them. An SSE endpoint added at, say,
        `/orders/api/kitchen/events` falls through to `location /` and gets
        `proxy_buffering on` and a 60-second read timeout -- frames collected
        and delivered at the end, connections dropped between quiet minutes.
        Nothing fails; it just behaves like the WSGI stack 10A replaced.

        So a streaming view says so (`streams = True`) and this checks the
        routes against the configuration rather than against a comment.
        """
        conf = (REPO_ROOT / "scripts" / "nginx_prod.conf").read_text(encoding="utf-8")
        prefixes = [
            block.split("{")[0].strip()
            for block in conf.split("location ")[1:]
            if "proxy_buffering off;" in block.split("}")[0]
        ]
        self.assertTrue(prefixes, "No location turns proxy buffering off.")

        streaming = [
            pattern for pattern in self.url_patterns()
            if getattr(pattern.callback, "streams", False)
        ]
        self.assertTrue(
            streaming, "Nothing is marked `streams = True`; this test would pass "
                       "silently forever once the probe is removed.",
        )
        for pattern in streaming:
            url = reverse(f"orders:{pattern.name}")
            with self.subTest(url=url):
                self.assertTrue(
                    any(url.startswith(prefix) for prefix in prefixes),
                    f"{url} streams but is not under any non-buffering "
                    f"location {prefixes}. The proxy would collect its frames.",
                )

    def url_patterns(self):
        from django.urls import get_resolver
        from django.urls.resolvers import URLPattern, URLResolver

        def walk(resolver):
            for entry in resolver.url_patterns:
                if isinstance(entry, URLResolver):
                    yield from walk(entry)
                elif isinstance(entry, URLPattern):
                    yield entry

        return list(walk(get_resolver()))

    def test_static_files_are_served_by_the_proxy_from_this_build(self):
        """10A: WhiteNoise's middleware is the only sync-only entry in the
        chain, and Django adapts one by wrapping the request path in
        async_to_sync, so the files moved to the proxy. They are copied from
        the application image rather than shared through a volume: a volume is
        populated once and would keep serving an old bundle against a new
        manifest."""
        conf = (REPO_ROOT / "scripts" / "nginx_prod.conf").read_text(encoding="utf-8")
        self.assertIn("location /static/", conf)
        dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY --from=app /app/staticfiles", dockerfile)
        self.assertEqual(
            self.compose["services"]["proxy"]["build"]["target"], "proxy"
        )
        self.assertNotIn("volumes", self.compose["services"]["proxy"])

    def test_the_proxy_replaces_any_inbound_forwarded_header(self):
        """The trust boundary above is only worth anything if the proxy sets the
        header from the peer it saw rather than passing the client's through."""
        headers = (REPO_ROOT / "scripts" / "nginx_proxy_headers.conf").read_text(encoding="utf-8")
        self.assertIn("proxy_set_header X-Forwarded-For $remote_addr;", headers)
        self.assertNotIn("$proxy_add_x_forwarded_for", headers)

    def test_every_proxied_location_sends_the_forwarded_headers(self):
        """10A, found by running it: nginx stops inheriting *every*
        `proxy_set_header` into a location that declares one of its own.

        The streaming location needs `Connection ""`, and adding it silently
        dropped Host, X-Forwarded-Proto and X-Forwarded-For -- so the
        application answered 400 from ALLOWED_HOSTS, and would have attributed
        every login failure on that path to the proxy (issue #61) if it had
        not. Keeping the headers in an included file is what makes "the
        location proxies" and "the location forwards the client address" the
        same statement, and this test is what keeps them together.
        """
        conf = (REPO_ROOT / "scripts" / "nginx_prod.conf").read_text(encoding="utf-8")
        # Server-level headers would be the trap all over again: they read as
        # if they applied everywhere.
        server_level = conf.split("location", 1)[0]
        self.assertNotIn("proxy_set_header", server_level)
        for block in conf.split("location ")[1:]:
            body = block.split("}")[0]
            if "proxy_pass" not in body:
                continue
            with self.subTest(location=block.splitlines()[0].strip()):
                self.assertIn("include /etc/nginx/bk_proxy_headers.conf;", body)
        dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("nginx_proxy_headers.conf /etc/nginx/bk_proxy_headers.conf",
                      dockerfile)

    def test_the_database_role_cannot_create_databases_or_roles(self):
        """D-046 keeps one role, so it owns its schema and can change it. It
        still must not be able to reach outside its own database."""
        init = (REPO_ROOT / "scripts" / "pg_prod_init.sql").read_text(encoding="utf-8")
        for clause in ("NOSUPERUSER", "NOCREATEDB", "NOCREATEROLE",
                       "NOREPLICATION", "NOBYPASSRLS"):
            with self.subTest(clause=clause):
                self.assertIn(clause, init)
        self.assertNotIn("PASSWORD '", init)

    def test_the_database_role_is_never_created_without_a_password(self):
        """An empty secret file would otherwise produce a role with an empty
        password on the container's first boot, where nothing looks at it."""
        init = (REPO_ROOT / "scripts" / "pg_prod_init.sql").read_text(encoding="utf-8")
        self.assertIn("RAISE EXCEPTION", init)
        self.assertIn("app_password_present", init)
