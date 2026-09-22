#!/usr/bin/env bash
# 12A1 -- deploy a git ref on the host: build, migrate, restart, verify.
#
#   scripts/deploy/deploy.sh [--yes] [<git-ref>]      default ref: develop (on origin)
#
# Run on the deployment host from the repository checkout (or through the
# manual GitHub workflow, which does exactly that over ssh). Steps:
#
#   1. check out the ref (detached; the checkout is not a working branch)
#   2. build the app and proxy images from it
#   3. `manage.py check` and `migrate` with the new image, old app still serving
#   4. `up -d` -- postgres is untouched, app and proxy are replaced
#   5. wait until https://BK_DOMAIN/orders/login/ answers 200
#
# Rollback is the same command with the previous ref (deploy.log keeps them);
# migrations are not rolled back automatically -- see the runbook.
#
# Operating rule (10E, D-067): no deployment during event hours. A replaced
# app drops every open kitchen stream; screens reconnect within seconds but
# the rule exists so that nobody has to trust that under load. The prompt
# below is the reminder; --yes is for the workflow, which asks on its side.

. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

assume_yes=0
ref="develop"
for arg in "$@"; do
    case "$arg" in
        --yes) assume_yes=1 ;;
        --*) bk_die "unknown option: $arg" ;;
        *) ref="$arg" ;;
    esac
done

bk_load_env
bk_require_docker
bk_require_secrets
[ -f "$BK_ROOT/tls/conf.d/10_https.conf" ] || bk_die "tls/conf.d has no https configuration; run issue_cert.sh (first time) or render_nginx.sh"

cd "$BK_ROOT"
git fetch -q --tags origin
# A bare branch name means the branch on origin, never a stale local one.
sha="$(git rev-parse --verify --quiet "origin/${ref}^{commit}" 2>/dev/null \
      || git rev-parse --verify --quiet "${ref}^{commit}")" || bk_die "unknown ref: $ref"
current="$(git rev-parse HEAD)"
bk_say "deploying $ref ($sha)"
bk_say "currently checked out: $current"

if [ "$assume_yes" -ne 1 ]; then
    printf 'Not during event hours (D-067). Continue? [y/N] '
    read -r answer
    [ "$answer" = "y" ] || [ "$answer" = "Y" ] || bk_die "aborted"
fi

[ -z "$(git status --porcelain --untracked-files=no)" ] || bk_die "checkout has local modifications; refusing to switch"
# The host checkout is a place to run refs from origin, never to commit in.
if [ -n "$(git log --oneline HEAD --not --remotes=origin 2>/dev/null | head -1)" ]; then
    bk_die "HEAD has commits that are not on origin; push or discard them before deploying"
fi
git checkout -q --detach "$sha"

bk_say "building images"
"${BK_COMPOSE[@]}" build --quiet app proxy

bk_say "configuration check and migrations with the new image"
"${BK_COMPOSE[@]}" run --rm --no-deps -T app python manage.py check --deploy --fail-level ERROR
"${BK_COMPOSE[@]}" run --rm -T app python manage.py migrate --noinput

bk_say "restarting app and proxy"
"${BK_COMPOSE[@]}" up -d --remove-orphans

bk_say "waiting for https://$BK_DOMAIN/orders/login/"
ok=0
for _ in $(seq 1 30); do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "https://$BK_DOMAIN/orders/login/" || true)"
    if [ "$code" = "200" ]; then ok=1; break; fi
    sleep 2
done
printf '%s deploy %s -> %s status=%s\n' "$(date -u +%FT%TZ)" "$current" "$sha" "${code:-none}" >> "$BK_ROOT/deploy.log"
[ "$ok" -eq 1 ] || bk_die "login page did not answer 200 within 60 s (last: ${code:-none}); check '${BK_COMPOSE[*]} logs app proxy'"

"${BK_COMPOSE[@]}" ps
bk_say "deployed $sha"
