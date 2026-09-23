#!/usr/bin/env bash
# 12A1 (D-071) -- create the application secrets and store them in the
# repository's GitHub "production" environment. Run on an operator machine
# with `gh` logged in, not on the host.
#
#   scripts/deploy/init_github_secrets.sh [--deploy-key <public-key-out>]
#
# Generated values go straight from this process into `gh secret set` on
# stdin: they are never printed, written to disk or put on a command line
# (the one exception is the deploy key pair below, which exists only in a
# private temporary directory until it has been stored).
# Only the event password is typed, and only its PBKDF2 hash leaves this
# machine (D-051). Secrets that already exist are left alone -- a rotation is
# a deliberate act (delete the one secret first; the two database passwords
# need the runbook procedure, because the database keeps the old ones).
#
# --deploy-key also creates the deploy-only ssh key pair: the private half
# becomes BK_DEPLOY_SSH_KEY, the public half is written to the given path for
# the host's ~/.ssh/authorized_keys. It refuses if BK_DEPLOY_SSH_KEY exists.
#
# The environment itself (and its protection rules) is created in GitHub's
# settings first; this script refuses to create it implicitly.

set -euo pipefail

die() { printf 'init_github_secrets: %s\n' "$*" >&2; exit 1; }
say() { printf '==> %s\n' "$*"; }

ENVIRONMENT=production
pubkey_out=""
while [ $# -gt 0 ]; do
    case "$1" in
        --deploy-key) [ $# -ge 2 ] || die "--deploy-key needs a path"; pubkey_out="$2"; shift 2 ;;
        *) die "usage: init_github_secrets.sh [--deploy-key <public-key-out>]" ;;
    esac
done

command -v gh >/dev/null || die "gh (GitHub CLI) is required"
command -v python3 >/dev/null || die "python3 is required"
repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)" || die "run inside the repository checkout"
gh api "repos/$repo/environments/$ENVIRONMENT" >/dev/null 2>&1 \
    || die "environment '$ENVIRONMENT' does not exist in $repo; create it in Settings > Environments first"

existing="$(gh secret list --env "$ENVIRONMENT" --repo "$repo" --json name -q '.[].name')"
exists() { printf '%s\n' "$existing" | grep -qx "$1"; }

set_secret() {  # name; value on stdin
    if exists "$1"; then
        say "$1 exists in $ENVIRONMENT, left as is"
        cat >/dev/null
        return 0
    fi
    gh secret set "$1" --env "$ENVIRONMENT" --repo "$repo" >/dev/null
    say "$1 set"
}

token() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }

token 64 | set_secret BK_SECRET_KEY
token 64 | set_secret BK_JWT_SIGNING_KEY
token 32 | set_secret BK_POSTGRES_BOOTSTRAP_PASSWORD
token 32 | set_secret BK_POSTGRES_APP_PASSWORD

if exists BK_EVENT_PASSWORD_HASH; then
    say "BK_EVENT_PASSWORD_HASH exists in $ENVIRONMENT, left as is"
else
    # Same format as django.contrib.auth.hashers.PBKDF2PasswordHasher (5.2:
    # 1,000,000 iterations), which bazaar_kiosk/auth_config.py validates at
    # startup. The prompt goes to the terminal, the hash to stdout -- captured
    # first, so a mismatched confirmation never reaches `gh secret set`.
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
)" || die "event password hash was not created"
    printf '%s\n' "$hash" | set_secret BK_EVENT_PASSWORD_HASH
    unset hash
fi

if [ -n "$pubkey_out" ]; then
    exists BK_DEPLOY_SSH_KEY && die "BK_DEPLOY_SSH_KEY exists; delete it first to replace the deploy key"
    [ ! -e "$pubkey_out" ] || die "$pubkey_out exists"
    command -v ssh-keygen >/dev/null || die "ssh-keygen is required"
    keydir="$(mktemp -d)"
    trap 'rm -rf "$keydir"' EXIT
    ssh-keygen -q -t ed25519 -N "" -C "bazaar-kiosk-deploy" -f "$keydir/id" >/dev/null
    set_secret BK_DEPLOY_SSH_KEY < "$keydir/id"
    cp "$keydir/id.pub" "$pubkey_out"
    say "deploy public key written to $pubkey_out (add it to the host user's ~/.ssh/authorized_keys)"
fi

say "done. Secret names in $ENVIRONMENT:"
gh secret list --env "$ENVIRONMENT" --repo "$repo" --json name -q '.[].name' | sed 's/^/    /'
