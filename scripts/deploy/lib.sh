#!/usr/bin/env bash
# 12A1 -- shared pieces of the deployment scripts. Sourced, not run.
#
# Every script here works from the repository root on the deployment host and
# reads its configuration from `.env` there (see .env.prod.example). Nothing in
# this directory prints a secret, and nothing here runs unless a person (or the
# manual workflow they trigger) invokes it.

set -euo pipefail

BK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BK_COMPOSE=(docker compose -f "$BK_ROOT/compose.prod.yaml" -f "$BK_ROOT/compose.tls.yaml")
BK_SECRET_FILES=(secret_key jwt_signing_key event_password_hash database_url
                 postgres_bootstrap_password postgres_app_password)

bk_die() { printf 'deploy: %s\n' "$*" >&2; exit 1; }
bk_say() { printf '==> %s\n' "$*"; }

# Loads .env (KEY=VALUE lines, no shell expansion) so BK_* is available.
bk_load_env() {
    local env_file="$BK_ROOT/.env"
    [ -f "$env_file" ] || bk_die ".env not found at $env_file (copy .env.prod.example and fill it in)"
    set -a
    # shellcheck disable=SC1090
    . "$env_file"
    set +a
    : "${BK_DOMAIN:?BK_DOMAIN must be set in .env}"
    : "${BK_ALLOWED_HOSTS:?BK_ALLOWED_HOSTS must be set in .env}"
    : "${BK_CSRF_TRUSTED_ORIGINS:?BK_CSRF_TRUSTED_ORIGINS must be set in .env}"
    BK_CERTBOT_WEBROOT="${BK_CERTBOT_WEBROOT:-/var/lib/bazaar_kiosk/certbot-www}"
    BK_HSTS_MAX_AGE="${BK_HSTS_MAX_AGE:-300}"
    export BK_CERTBOT_WEBROOT BK_HSTS_MAX_AGE
}

bk_require_secrets() {
    local name missing=0
    for name in "${BK_SECRET_FILES[@]}"; do
        if [ ! -s "$BK_ROOT/secrets/$name" ]; then
            printf 'deploy: secrets/%s is missing or empty\n' "$name" >&2
            missing=1
        fi
    done
    [ "$missing" -eq 0 ] || bk_die "run scripts/deploy/make_secrets.sh first"
}

bk_require_docker() {
    command -v docker >/dev/null || bk_die "docker is not installed (scripts/deploy/server_setup.sh)"
    docker compose version >/dev/null 2>&1 || bk_die "docker compose v2 is not available"
}
