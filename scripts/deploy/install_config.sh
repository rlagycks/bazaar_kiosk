#!/usr/bin/env bash
# 12A1 (D-071) -- write the host's `.env` and `secrets/` from what the deploy
# workflow sends. GitHub's "production" environment is the source of truth;
# this is the receiving end.
#
#   install_config.sh <repo-dir>  < payload
#
# The payload arrives on stdin (never argv, never a log): one line per item,
# `<name> <base64 value>`. The workflow runs this file as it exists at the
# workflow's own commit (`git show <sha>:...`), so sender and receiver always
# agree on the format. It is self-contained on purpose -- no lib.sh.
#
# Everything is validated before anything is written, and each file is only
# replaced when its content changed. Values are never printed; only names.
# secrets/ is 0700 and its files 0444 (see the install step for why).
#
# Database passwords are the exception to "GitHub wins". PostgreSQL applies
# them once, when the data volume is first initialised, so a password that
# differs from the one already on disk would leave the database and the
# application disagreeing. This refuses whenever it differs -- with or without
# a volume, so the guard does not depend on how docker labels things. Changing
# one is the runbook's rotation procedure (ALTER ROLE, then delete the file).

set -euo pipefail

die() { printf 'install_config: %s\n' "$*" >&2; exit 1; }
say() { printf '==> %s\n' "$*" >&2; }

root="${1:-}"
[ -n "$root" ] && [ -d "$root/.git" ] || die "usage: install_config.sh <repo-dir> < payload"
cd "$root"

ITEMS=(env secret_key jwt_signing_key event_password_hash
       postgres_bootstrap_password postgres_app_password)
DB_ITEMS=(postgres_bootstrap_password postgres_app_password)

umask 077
incoming="$(mktemp -d "$root/.config-incoming.XXXXXX")"
trap 'rm -rf "$incoming"' EXIT

is_item() {
    local want="$1" item
    for item in "${ITEMS[@]}"; do [ "$item" = "$want" ] && return 0; done
    return 1
}

# --- read -------------------------------------------------------------------
while IFS=' ' read -r name encoded rest || [ -n "${name:-}" ]; do
    [ -n "$name" ] || continue
    [ -z "${rest:-}" ] || die "malformed payload line for $name"
    is_item "$name" || die "unexpected payload item: $name"
    [ ! -e "$incoming/$name" ] || die "duplicate payload item: $name"
    # Command substitution drops trailing newlines, so a value pasted into
    # GitHub with or without one ends up the same on disk.
    value="$(printf '%s' "$encoded" | base64 -d 2>/dev/null)" || die "$name is not valid base64"
    [ -n "$value" ] || die "$name is empty (is the GitHub secret/variable set?)"
    printf '%s\n' "$value" > "$incoming/$name"
done

for name in "${ITEMS[@]}"; do
    [ -s "$incoming/$name" ] || die "payload is missing $name"
done

# --- validate ---------------------------------------------------------------
single_line() {  # name, regex
    local lines
    lines="$(wc -l < "$incoming/$1")"
    [ "$lines" -eq 1 ] || die "$1 must be a single line"
    grep -Eq "$2" "$incoming/$1" || die "$1 does not have the expected form"
}

# .env: BK_KEY=VALUE only, and values limited to what hostnames, origins and
# numbers need. docker compose interpolates ${...} in .env, and lib.sh reads
# it as data -- a narrow alphabet keeps both readers harmless.
# grep's own error (status 2) must not read as "no offending line".
status=0
grep -Evq '^(#.*|BK_[A-Z0-9_]+=[A-Za-z0-9.,:/_-]*)?$' "$incoming/env" || status=$?
case "$status" in
    1) ;;
    0) die "env has a line that is not BK_KEY=<hostname/origin/number>" ;;
    *) die "env could not be validated" ;;
esac
for key in BK_DOMAIN BK_ALLOWED_HOSTS BK_CSRF_TRUSTED_ORIGINS; do
    grep -Eq "^${key}=.+$" "$incoming/env" || die "env is missing $key"
done
if grep -Eq '^BK_HSTS_MAX_AGE=' "$incoming/env"; then
    grep -Eq '^BK_HSTS_MAX_AGE=[0-9]+$' "$incoming/env" || die "BK_HSTS_MAX_AGE must be a number of seconds"
fi

single_line secret_key '^.{50,}$'
single_line jwt_signing_key '^.{50,}$'
single_line event_password_hash '^pbkdf2_sha256\$[0-9]+\$[A-Za-z0-9]+\$[A-Za-z0-9+/=]+$'
# The application password is embedded in DATABASE_URL, so it must be URL-safe.
single_line postgres_bootstrap_password '^[A-Za-z0-9_-]{24,}$'
single_line postgres_app_password '^[A-Za-z0-9_-]{24,}$'

app_password="$(cat "$incoming/postgres_app_password")"
# Internal network only (D-046): plain connection inside the compose network.
printf 'postgresql://bazaar_app:%s@postgres:5432/bazaar?sslmode=disable\n' "$app_password" \
    > "$incoming/database_url"
unset app_password

# --- database guard ---------------------------------------------------------
for name in "${DB_ITEMS[@]}"; do
    if [ -e "secrets/$name" ] && ! cmp -s "secrets/$name" "$incoming/$name"; then
        die "$name in GitHub differs from the one on this host (the database keeps the first one); nothing was written. Rotate it with the runbook procedure."
    fi
done

# --- install ----------------------------------------------------------------
mkdir -p secrets
chmod 700 secrets

# Each file is replaced with a rename, so a single file is never half
# written. Seven renames are not one transaction, though: if one fails (a full
# disk), say exactly which landed. Running the workflow again converges -- every
# value is re-sent and only differing files are replaced.
updated=()
report_partial() {
    printf 'install_config: stopped part way; updated before the failure: %s\n' \
        "${updated[*]:-none}" >&2
    printf 'install_config: re-run the workflow (config_only) once the cause is fixed\n' >&2
}
# -E so a failure inside install_file reaches the ERR trap too.
set -E
trap 'report_partial' ERR

install_file() {  # source, destination, mode
    if [ -e "$2" ] && cmp -s "$1" "$2"; then
        chmod "$3" "$2"
        return 0
    fi
    chmod "$3" "$1"
    mv -f "$1" "$2"
    updated+=("$2")
    say "$2 updated"
}

# .env is read on the host only. The secret files are bind-mounted into the
# containers, whose users are not this one (app: uid 10001, postgres: uid 70),
# so they must be readable by others; the 0700 secrets/ directory is what keeps
# other host users out -- a bind-mounted file is reached without traversing it.
install_file "$incoming/env" .env 600
for name in secret_key jwt_signing_key event_password_hash database_url \
            postgres_bootstrap_password postgres_app_password; do
    install_file "$incoming/$name" "secrets/$name" 444
done
trap - ERR
say "configuration is in place"
