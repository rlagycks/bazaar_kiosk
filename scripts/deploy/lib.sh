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

# Loads .env as data: KEY=VALUE lines only, no shell expansion, no sourcing.
# Comments and blank lines are skipped; anything else is a refused line, so a
# pasted value with $( ) or backticks can never run as code here. (docker
# compose reads the same file with the same plain semantics.)
bk_load_env() {
    local env_file="$BK_ROOT/.env" line key value
    [ -f "$env_file" ] || bk_die ".env not found at $env_file (copy .env.prod.example and fill it in)"
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ''|'#'*) continue ;;
        esac
        key="${line%%=*}"
        value="${line#*=}"
        case "$key" in
            BK_[A-Z0-9_]*) ;;
            *) bk_die ".env line is not BK_KEY=VALUE: ${line%%=*}" ;;
        esac
        export "$key=$value"
    done < "$env_file"
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
