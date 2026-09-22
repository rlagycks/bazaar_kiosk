#!/usr/bin/env bash
# 12A1 -- create the six secret files compose.prod.yaml mounts (D-046).
#
#   scripts/deploy/make_secrets.sh
#
# Writes into ./secrets/ (gitignored, mode 0700, files 0600). Refuses to
# overwrite anything that exists: a rotated key is a deliberate act, so delete
# the one file you mean to rotate first. Generated values are never printed.
#
# Only the event password is asked for interactively, and it is stored as a
# Django PBKDF2 hash (D-051): the plaintext is not written anywhere. The hash
# format matches django.contrib.auth.hashers.PBKDF2PasswordHasher (5.2:
# 1,000,000 iterations), which is what bazaar_kiosk/auth_config.py validates
# at startup, so no Django install is needed on the host to produce it.

. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

command -v python3 >/dev/null || bk_die "python3 is required"
umask 077
mkdir -p "$BK_ROOT/secrets"
chmod 700 "$BK_ROOT/secrets"
cd "$BK_ROOT/secrets"

random_token() { python3 -c 'import secrets; print(secrets.token_urlsafe(64))'; }
random_password() { python3 -c 'import secrets; print(secrets.token_urlsafe(32))'; }

write_once() {  # name, value
    if [ -e "$1" ]; then
        bk_say "secrets/$1 exists, left as is"
        return 0
    fi
    printf '%s\n' "$2" > "$1"
    chmod 600 "$1"
    bk_say "secrets/$1 written"
}

write_once secret_key "$(random_token)"
write_once jwt_signing_key "$(random_token)"
write_once postgres_bootstrap_password "$(random_password)"

if [ -e postgres_app_password ] && [ -e database_url ]; then
    bk_say "secrets/postgres_app_password and database_url exist, left as is"
elif [ -e postgres_app_password ] || [ -e database_url ]; then
    bk_die "postgres_app_password and database_url must be created together; remove the remaining one to regenerate both"
else
    app_password="$(random_password)"
    write_once postgres_app_password "$app_password"
    # Internal network only (D-046): the database is not reachable from outside
    # the compose network, so the connection is plain. Do not copy this URL to
    # an external database without revisiting that decision.
    write_once database_url "postgresql://bazaar_app:${app_password}@postgres:5432/bazaar?sslmode=disable"
    unset app_password
fi

if [ -e event_password_hash ]; then
    bk_say "secrets/event_password_hash exists, left as is"
else
    hash="$(python3 - <<'PYHASH'
import base64, hashlib, secrets, string, sys
from getpass import getpass

ITERATIONS = 1_000_000  # Django 5.2 PBKDF2PasswordHasher.iterations
password = getpass("Event password (shared by every account, D-051): ")
confirmation = getpass("Confirm: ")
if len(password) < 8 or password != confirmation:
    sys.exit("Passwords must match and be at least 8 characters.")
alphabet = string.ascii_letters + string.digits
salt = "".join(secrets.choice(alphabet) for _ in range(22))
digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS)
print(f"pbkdf2_sha256${ITERATIONS}${salt}${base64.b64encode(digest).decode()}")
PYHASH
)" || bk_die "event password hash was not created"
    write_once event_password_hash "$hash"
    unset hash
fi

bk_say "secrets/ is complete:"
ls -l "$BK_ROOT/secrets" | awk 'NR>1 {print "    " $1, $NF}'
