# FILE: orders/views/auth.py
"""The identification flow: proving who the caller is.

What an identified caller may then do lives in `guards.py`. This file owns the
login and logout requests and, per BLUEPRINT 4A2, is the file that D-035's
id/password + JWT replacement edits; keeping enforcement out of it is what lets
that work proceed without touching the authorization matrix phase 3 settled.
"""
from __future__ import annotations

from django.conf import settings
from django.middleware.csrf import rotate_token
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.debug import (
    sensitive_post_parameters,
    sensitive_variables,
)

from orders.roles import ROLE_DEFINITIONS, ROLE_LABELS, ROLE_TO_URLNAME


@sensitive_variables("pin", "expected")
@sensitive_post_parameters("pin")
def login_view(request):
    role_codes = [code for code, *_ in ROLE_DEFINITIONS]
    role_choices = [(code, ROLE_LABELS.get(code, code)) for code in role_codes]
    role_cards = [
        {
            "code": code,
            "label": label,
            "desc": desc,
            "next": reverse(urlname),
        }
        for code, label, desc, urlname in ROLE_DEFINITIONS
    ]
    if request.method == "POST":
        role = (request.POST.get("role") or "").upper()
        pin  = (request.POST.get("pin") or "").strip()
        expected = settings.ROLE_PINS.get(role)
        if expected and pin == expected and role in ROLE_TO_URLNAME:
            # Start a clean session at the privilege transition. `flush` rather
            # than `cycle_key` because the latter carries the old contents into
            # the new key: only `role` lives here today, but anything an
            # anonymous caller could plant would otherwise ride across the
            # boundary. This also matches what logout does.
            request.session.flush()
            # The session key is only half the credential pair. Django's own
            # login rotates the CSRF token alongside it; without this the secret
            # bound to the fresh session is still the pre-login one.
            rotate_token(request)
            request.session["role"] = role
            return redirect(reverse(ROLE_TO_URLNAME[role]))
        return render(request, "orders/login.html", {
            "roles": role_codes,
            "role_choices": role_choices,
            "role_cards": role_cards,
            "error": "역할 또는 PIN이 올바르지 않습니다.",
            "last_role": role,
        }, status=200)
    return render(request, "orders/login.html", {
        "roles": role_codes,
        "role_choices": role_choices,
        "role_cards": role_cards,
    })

def logout_view(request):
    request.session.flush()
    rotate_token(request)
    return redirect(reverse("orders:login"))
