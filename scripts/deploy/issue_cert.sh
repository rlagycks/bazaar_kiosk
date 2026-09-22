#!/usr/bin/env bash
# 12A1 -- obtain the Let's Encrypt certificate for BK_DOMAIN (first time only).
#
#   scripts/deploy/issue_cert.sh <contact-email> [--staging]
#
# Sequence: render the http-only proxy configuration, start the proxy so the
# ACME http-01 challenge can be answered from the webroot, run certbot on the
# host in webroot mode, then render the full configuration and reload. Renewal
# needs nothing further: certbot.timer renews with the same webroot and the
# hook installed by server_setup.sh reloads the proxy.
#
# Requires: DNS for BK_DOMAIN already pointing at this host, ports 80/443 open
# in the security group, and .env filled in. Use --staging for a dry run
# against Let's Encrypt's staging CA (untrusted certificate, no rate limits).

. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
bk_load_env
bk_require_docker

email="${1:-}"
[ -n "$email" ] || bk_die "usage: issue_cert.sh <contact-email> [--staging]"
extra=()
[ "${2:-}" = "--staging" ] && extra+=(--staging)

command -v certbot >/dev/null || bk_die "certbot is missing (scripts/deploy/server_setup.sh)"
[ -d "$BK_CERTBOT_WEBROOT" ] || bk_die "webroot $BK_CERTBOT_WEBROOT does not exist (server_setup.sh)"

if [ -r "/etc/letsencrypt/live/$BK_DOMAIN/fullchain.pem" ]; then
    bk_die "a certificate for $BK_DOMAIN already exists; certbot renews it on its own"
fi

bk_say "bootstrap proxy (http only) for the ACME challenge"
"$BK_ROOT/scripts/deploy/render_nginx.sh" --bootstrap
"${BK_COMPOSE[@]}" up -d --no-deps proxy

bk_say "requesting certificate for $BK_DOMAIN"
sudo certbot certonly --webroot -w "$BK_CERTBOT_WEBROOT" -d "$BK_DOMAIN" \
    --email "$email" --agree-tos --no-eff-email --non-interactive "${extra[@]}"

bk_say "switching the proxy to https"
"$BK_ROOT/scripts/deploy/render_nginx.sh"
"${BK_COMPOSE[@]}" exec -T proxy nginx -t
"${BK_COMPOSE[@]}" exec -T proxy nginx -s reload
bk_say "done; https://$BK_DOMAIN/ is served by the proxy container"
