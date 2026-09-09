"""Redact role credentials in Django's standard exception reports."""

import re

from django.views.debug import SafeExceptionReporterFilter


class CredentialExceptionReporterFilter(SafeExceptionReporterFilter):
    # Extend Django's password/token/cookie protections instead of replacing them.
    hidden_settings = re.compile(
        SafeExceptionReporterFilter.hidden_settings.pattern + r"|PIN",
        SafeExceptionReporterFilter.hidden_settings.flags,
    )

    def is_active(self, request):
        # Honor sensitive POST/local annotations even during local debugging.
        # This does not make DEBUG appropriate for a public deployment.
        return True

    def _redact_pin_fields(self, values):
        # Middleware can fail before a view marks POST fields as sensitive.
        # Copy so reporting never changes the request used by the application.
        cleansed = values.copy()
        for name in cleansed:
            if isinstance(name, str) and name.lower() == "pin":
                cleansed[name] = self.cleansed_substitute
        return cleansed

    def get_post_parameters(self, request):
        return self._redact_pin_fields(super().get_post_parameters(request))

    def get_cleansed_multivaluedict(self, request, multivaluedict):
        return self._redact_pin_fields(
            super().get_cleansed_multivaluedict(request, multivaluedict)
        )
