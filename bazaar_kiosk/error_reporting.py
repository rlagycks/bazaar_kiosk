"""Redact role credentials in Django's standard exception reports."""

import re

from django.views.debug import SafeExceptionReporterFilter


class CredentialExceptionReporterFilter(SafeExceptionReporterFilter):
    # Extend Django's password/token/cookie protections instead of replacing them.
    # Anchor the PIN branch so it matches ROLE_PINS, pin, role_pin and pin_confirm
    # without swallowing unrelated names that merely contain the letters, such as
    # Django's own NUMBER_GROUPING or an application field named pinned_note.
    hidden_settings = re.compile(
        SafeExceptionReporterFilter.hidden_settings.pattern
        + r"|(?:^|[^A-Za-z])PINS?(?:$|[^A-Za-z])",
        SafeExceptionReporterFilter.hidden_settings.flags,
    )

    def is_active(self, request):
        # Honor sensitive POST/local annotations even during local debugging.
        # This does not make DEBUG appropriate for a public deployment.
        return True

    def _redact_pin_fields(self, values):
        # Middleware can fail before a view marks POST fields as sensitive.
        # Match with the same pattern used for settings, META and cookies so a
        # renamed or added credential field is covered without a code change.
        # Copy so reporting never changes the request used by the application.
        try:
            cleansed = values.copy()
            for name in cleansed:
                if isinstance(name, str) and self.hidden_settings.search(name):
                    cleansed[name] = self.cleansed_substitute
            return cleansed
        except Exception:
            # Never let redaction fail open, and never let it replace a handled
            # 500 with an unhandled one: report nothing rather than the values.
            return {"": self.cleansed_substitute}

    def get_post_parameters(self, request):
        return self._redact_pin_fields(super().get_post_parameters(request))

    def get_cleansed_multivaluedict(self, request, multivaluedict):
        return self._redact_pin_fields(
            super().get_cleansed_multivaluedict(request, multivaluedict)
        )
