"""Synthetic JWT credentials and real HTTP authentication for regression tests."""
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.urls import reverse

ROLE_PASSWORDS = {"ORDER": "test-order-password", "B1_COUNTER": "test-counter-password", "KITCHEN": "test-kitchen-password"}
ROLE_ACCOUNTS = {
    role: {"id": role.lower(), "password_hash": PBKDF2PasswordHasher().encode(password, "synthetic-regression-salt", iterations=1)}
    for role, password in ROLE_PASSWORDS.items()
}

def credentials(role):
    return {"account_id": ROLE_ACCOUNTS[role]["id"], "password": ROLE_PASSWORDS[role]}

def login_client(client, role):
    csrf = client.get(reverse("orders:login")).cookies["csrftoken"].value
    response = client.post(reverse("orders:login"), credentials(role), HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 302, response.status_code
    refreshed = client.post("/orders/auth/refresh/", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
    assert refreshed.status_code == 200, refreshed.content
    client.defaults["HTTP_AUTHORIZATION"] = "Bearer " + refreshed.json()["access_token"]
    return response
