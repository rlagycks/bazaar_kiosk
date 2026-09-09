"""4A1: synthetic credentials must stay out of Django error reports.

This covers settings and annotated login fields/locals, not arbitrary logging
or secrets interpolated into exception messages. No real mail or DB is used.
"""

import logging
import uuid
from unittest.mock import patch

from django.core import mail
from django.test import Client, SimpleTestCase, override_settings
from django.urls import include, path
from django.utils.log import AdminEmailHandler
from django.views.debug import ExceptionReporter, get_default_exception_reporter_filter

from orders.views import auth


def report_failure(request, *args, **kwargs):
    raise RuntimeError("synthetic error-report failure")


class EarlyFailureMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Keep the parsed form in this traceback frame to exercise redaction of
        # a MultiValueDict local as well as the report's separate POST section.
        post_data = request.POST
        return report_failure(request)


urlpatterns = [
    path("orders/", include("orders.urls")),
    path("failure/", report_failure),
    path("login/", auth.login_view),
]


@override_settings(ROOT_URLCONF=__name__)
class SecurityErrorReportTests(SimpleTestCase):
    def setUp(self):
        self.configured_pin = uuid.uuid4().hex
        self.submitted_pin = uuid.uuid4().hex
        self.secret = uuid.uuid4().hex
        self.config = override_settings(
            ROLE_PINS={"ORDER": self.configured_pin}, SECRET_KEY=self.secret,
        )
        self.config.enable()
        self.addCleanup(self.config.disable)
        get_default_exception_reporter_filter.cache_clear()
        self.addCleanup(get_default_exception_reporter_filter.cache_clear)
        self.client = Client(raise_request_exception=False)

    def assert_no_credentials(self, output):
        # Do not echo the entire report or synthetic secrets on assertion failure.
        for label, value in (
            ("configured PIN", self.configured_pin),
            ("submitted PIN", self.submitted_pin),
            ("SECRET_KEY", self.secret),
        ):
            self.assertFalse(value in output, f"Error report exposed {label}")

    def request_failure(self, *, login=False, accept="text/html"):
        with self.assertLogs("django.request", level="ERROR") as captured:
            if login:
                # A failed login normally renders an error. Inject a rendering
                # failure after both submitted and expected PINs have been read.
                with patch.object(auth, "render", report_failure):
                    response = self.client.post(
                        "/login/", {"role": "ORDER", "pin": self.submitted_pin},
                        HTTP_ACCEPT=accept,
                    )
            else:
                response = self.client.get("/failure/", HTTP_ACCEPT=accept)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(captured.records), 1)
        self.assert_no_credentials(logging.Formatter().format(captured.records[0]))
        return response, captured.records[0]

    @override_settings(DEBUG=True)
    def test_debug_settings_are_redacted_in_html_and_non_html_errors(self):
        for accept in ("text/html", "application/json"):
            with self.subTest(accept=accept):
                response, _ = self.request_failure(accept=accept)
                text = response.content.decode()
                self.assertIn("synthetic error-report failure", text)
                self.assertIn("ROLE_PINS", text)
                self.assert_no_credentials(text)
                # Django uses its text error report for a non-HTML client;
                # this patch does not invent a JSON exception response contract.
                expected_type = "text/html" if accept == "text/html" else "text/plain"
                self.assertTrue(response["Content-Type"].startswith(expected_type))

    @override_settings(DEBUG=True)
    def test_login_error_hides_post_pin_and_local_expected_pin_in_debug(self):
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
                self.assertIn("pin", variables)
                self.assertIn("expected", variables)
                self.assertEqual(record.request.POST["pin"], self.submitted_pin)
                self.assertEqual(dict(data["filtered_POST_items"])["role"], "ORDER")

    @override_settings(
        DEBUG=True, MIDDLEWARE=[__name__ + ".EarlyFailureMiddleware"],
    )
    def test_post_pin_is_redacted_before_login_decorators_run(self):
        response, record = self.request_failure(login=True)
        self.assertFalse(hasattr(record.request, "sensitive_post_parameters"))
        self.assert_no_credentials(response.content.decode())
        self.assertEqual(record.request.POST["pin"], self.submitted_pin)
        data = ExceptionReporter(record.request, *record.exc_info).get_traceback_data()
        frame = next(
            frame for frame in data["frames"]
            if "post_data" in dict(frame.get("vars", []))
        )
        self.assert_no_credentials(dict(frame["vars"])["post_data"])

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
