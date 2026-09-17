"""4A1: synthetic credentials must stay out of Django error reports.

This covers settings and annotated login fields/locals, not arbitrary logging
or secrets interpolated into exception messages. No real mail or DB is used.
"""

import logging
import uuid
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import include, path
from django.utils.log import AdminEmailHandler
from django.views.debug import ExceptionReporter, get_default_exception_reporter_filter

from orders.views import auth
from orders.tests.auth_support import ROLE_ACCOUNTS


def report_failure(request, *args, **kwargs):
    raise RuntimeError("synthetic error-report failure")


class EarlyFailureMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Keep the parsed form in this traceback frame to exercise redaction of
        # a MultiValueDict local as well as the report's separate POST section.
        post_data = request.POST  # noqa: F841 - deliberate traceback local
        return report_failure(request)


urlpatterns = [
    path("orders/", include("orders.urls")),
    path("failure/", report_failure),
    path("login/", auth.login_view),
]


@override_settings(ROOT_URLCONF=__name__, LOGIN_MAX_FAILURES=100)
class SecurityErrorReportTests(TestCase):
    def setUp(self):
        self.configured_hash = PBKDF2PasswordHasher().encode(uuid.uuid4().hex, "synthetic-redaction-salt", iterations=1)
        self.submitted_password = uuid.uuid4().hex
        self.secret = uuid.uuid4().hex
        self.config = override_settings(
            ROLE_ACCOUNTS={"ORDER": {**ROLE_ACCOUNTS["ORDER"], "password_hash": self.configured_hash}}, SECRET_KEY=self.secret,
        )
        self.config.enable()
        self.addCleanup(self.config.disable)
        get_default_exception_reporter_filter.cache_clear()
        self.addCleanup(get_default_exception_reporter_filter.cache_clear)
        self.client = Client(raise_request_exception=False)

    def assert_no_credentials(self, output):
        # Do not echo the entire report or synthetic secrets on assertion failure.
        for label, value in (
            ("configured password hash", self.configured_hash),
            ("submitted password", self.submitted_password),
            ("SECRET_KEY", self.secret),
        ):
            self.assertFalse(value in output, f"Error report exposed {label}")

    def request_failure(self, *, login=False, accept="text/html"):
        with self.assertLogs("django.request", level="ERROR") as captured:
            if login:
                # A failed login normally renders an error. Inject a rendering
                # failure after the submitted password has been read.
                with patch.object(auth, "render", report_failure):
                    response = self.client.post(
                        "/login/", {"account_id": "order", "password": self.submitted_password},
                        HTTP_ACCEPT=accept,
                    )
            else:
                response = self.client.get("/failure/", HTTP_ACCEPT=accept)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(captured.records), 1)
        self.assert_no_credentials(logging.Formatter().format(captured.records[0]))
        if settings.DEBUG:
            # Without this, every "credential is absent" assertion below would
            # also pass against an empty body that is no report at all.
            self.assertIn("synthetic error-report failure", response.content.decode())
        return response, captured.records[0]

    def cleansed(self):
        return get_default_exception_reporter_filter().cleansed_substitute

    @override_settings(DEBUG=True)
    def test_debug_settings_are_redacted_in_html_and_non_html_errors(self):
        for accept in ("text/html", "application/json"):
            with self.subTest(accept=accept):
                response, _ = self.request_failure(accept=accept)
                text = response.content.decode()
                self.assertIn("synthetic error-report failure", text)
                self.assertIn("ROLE_ACCOUNTS", text)
                self.assert_no_credentials(text)
                # Django uses its text error report for a non-HTML client;
                # this patch does not invent a JSON exception response contract.
                expected_type = "text/html" if accept == "text/html" else "text/plain"
                self.assertTrue(response["Content-Type"].startswith(expected_type))

    @override_settings(DEBUG=True)
    def test_login_error_hides_post_password_and_local_password_in_debug(self):
        for accept in ("text/html", "application/json"):
            with self.subTest(accept=accept):
                response, record = self.request_failure(login=True, accept=accept)
                self.assert_no_credentials(response.content.decode())
                reporter = ExceptionReporter(record.request, *record.exc_info)
                data = reporter.get_traceback_data()
                login_frame = next(
                    frame for frame in data["frames"] if frame["function"] == "login_view"
                )
                variables = dict(login_frame["vars"])
                self.assert_no_credentials(str(variables))
                self.assertIn("password", variables)
                self.assertEqual(record.request.POST["password"], self.submitted_password)
                filtered = dict(data["filtered_POST_items"])
                self.assertEqual(filtered["account_id"], "order")
                # Absence of the secret plus presence of the marker: without the
                # second half, blanking every field would also pass.
                self.assertEqual(filtered["password"], self.cleansed())
                self.assertEqual(variables["password"], repr(self.cleansed()))


    @override_settings(
        DEBUG=True, MIDDLEWARE=[__name__ + ".EarlyFailureMiddleware"],
    )
    def test_post_password_is_redacted_before_login_decorators_run(self):
        response, record = self.request_failure(login=True)
        self.assertFalse(hasattr(record.request, "sensitive_post_parameters"))
        self.assert_no_credentials(response.content.decode())
        self.assertEqual(record.request.POST["password"], self.submitted_password)
        data = ExceptionReporter(record.request, *record.exc_info).get_traceback_data()
        frame = next(
            frame for frame in data["frames"]
            if "post_data" in dict(frame.get("vars", []))
        )
        post_data = dict(frame["vars"])["post_data"]
        self.assert_no_credentials(post_data)
        # The traceback local must be cleansed field by field, not blanked whole.
        self.assertIn("'account_id'", post_data)
        self.assertIn("order", post_data)
        self.assertIn(self.cleansed(), post_data)
        self.assertEqual(
            dict(
                ExceptionReporter(record.request, *record.exc_info)
                .get_traceback_data()["filtered_POST_items"]
            )["password"],
            self.cleansed(),
        )

    @override_settings(
        DEBUG=False,
        DEFAULT_EXCEPTION_REPORTER_FILTER=(
            "django.views.debug.SafeExceptionReporterFilter"
        ),
    )
    def test_login_annotation_alone_redacts_the_post_password(self):
        # Pin @sensitive_post_parameters independently. The project filter
        # redacts the field whether or not the view is annotated, so without
        # Django's stock filter here the decorator could be deleted unnoticed.
        get_default_exception_reporter_filter.cache_clear()
        _, record = self.request_failure(login=True)
        self.assertIn("password", record.request.sensitive_post_parameters)
        data = ExceptionReporter(record.request, *record.exc_info).get_traceback_data()
        filtered = dict(data["filtered_POST_items"])
        self.assertEqual(filtered["account_id"], "order")
        self.assertEqual(filtered["password"], self.cleansed())
        self.assertEqual(record.request.POST["password"], self.submitted_password)

    @override_settings(DEBUG=True, MIDDLEWARE=[__name__ + ".EarlyFailureMiddleware"])
    def test_credential_field_names_beyond_pin_are_redacted_case_insensitively(self):
        # The fallback net runs before any annotation, so it must not depend on
        # one exact lowercase field name. "password" also pins that the
        # inherited pattern flags survive: without re.IGNORECASE the uppercase
        # PASS branch would not match it.
        secrets = {name: uuid.uuid4().hex for name in ("PIN", "role_pin", "password")}
        with self.assertLogs("django.request", level="ERROR") as captured:
            response = self.client.post("/login/", {"role": "ORDER", **secrets})
        self.assertEqual(response.status_code, 500)
        body = response.content.decode()
        self.assertIn("synthetic error-report failure", body)
        for name, value in secrets.items():
            with self.subTest(field=name):
                self.assertFalse(value in body, f"Error report exposed {name}")
        record = captured.records[0]
        filtered = dict(
            ExceptionReporter(record.request, *record.exc_info)
            .get_traceback_data()["filtered_POST_items"]
        )
        self.assertEqual(filtered["role"], "ORDER")
        for name in secrets:
            with self.subTest(field=name):
                self.assertEqual(filtered[name], self.cleansed())

    @override_settings(
        DEBUG=False, ADMINS=[("Synthetic test", "synthetic-admin@example.invalid")],
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    )
    def test_production_500_and_admin_error_reports_hide_credentials(self):
        response, record = self.request_failure(login=True)
        self.assert_no_credentials(response.content.decode())
        handler = AdminEmailHandler(include_html=True)
        self.addCleanup(handler.close)
        handler.emit(record)
        self.assertEqual(len(mail.outbox), 1)
        report = mail.outbox[0]
        self.assertIn("synthetic error-report failure", report.body)
        self.assert_no_credentials(report.subject + report.body)
        self.assertEqual(len(report.alternatives), 1)
        self.assert_no_credentials(report.alternatives[0].content)
