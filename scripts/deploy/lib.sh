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
    [ "$missing" -eq 0 ] || bk_die "secrets/ is incomplete; the deploy workflow writes it (install_config.sh, D-071)"
}

# 12A1 (D-071): the root volume is 8 GB and every deploy builds on the host.
# A full disk stops PostgreSQL from writing -- orders stop saving -- so a deploy
# refuses to start without room for a build, after reclaiming what it safely can.
BK_MIN_FREE_MB="${BK_MIN_FREE_MB:-2560}"

bk_free_mb() {
    df -Pm "$BK_ROOT" | awk 'NR==2 {print $4}'
}

# Removes what no container uses: dangling images (the previous app/proxy build
# once a new one carries the tag) and build cache. Running containers, the
# pinned postgres image and every volume are untouched. A rollback rebuilds.
bk_reclaim_docker_space() {
    docker image prune -f >/dev/null
    docker builder prune -f >/dev/null
}

bk_require_disk() {
    local free
    free="$(bk_free_mb)"
    if [ "$free" -lt "$BK_MIN_FREE_MB" ]; then
        bk_say "only ${free} MB free; removing unused images and all build cache"
        docker image prune -f >/dev/null
        docker builder prune -af >/dev/null
        free="$(bk_free_mb)"
    fi
    [ "$free" -ge "$BK_MIN_FREE_MB" ] \
        || bk_die "only ${free} MB free on $(df -P "$BK_ROOT" | awk 'NR==2 {print $6}'), need ${BK_MIN_FREE_MB} MB to build; check 'docker system df' and journal/log sizes"
    bk_say "${free} MB free"
}

# certbot keeps live/ and archive/ root-only (0700), so the deploy user cannot
# test the certificate itself. The renewal file for the domain is readable and
# exists exactly when certbot manages a certificate for it.
bk_have_certificate() {
    [ -e "/etc/letsencrypt/renewal/$BK_DOMAIN.conf" ]
}

bk_require_docker() {
    command -v docker >/dev/null || bk_die "docker is not installed (scripts/deploy/server_setup.sh)"
    docker compose version >/dev/null 2>&1 || bk_die "docker compose v2 is not available"
}
