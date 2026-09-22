#!/usr/bin/env bash
# 12A1 -- render the proxy configuration for this host into ./tls/conf.d/.
#
#   scripts/deploy/render_nginx.sh              # http + https (certificate present)
#   scripts/deploy/render_nginx.sh --bootstrap  # http only, for the first certbot run
#
# The templates live in scripts/nginx_tls/. Only ${BK_DOMAIN} and
# ${BK_HSTS_MAX_AGE} are substituted; nginx's own $variables are left alone.
# The output directory is mounted read-only over /etc/nginx/conf.d by
# compose.tls.yaml. Run it again after changing .env, then reload the proxy:
#   docker compose -f compose.prod.yaml -f compose.tls.yaml exec proxy nginx -s reload

. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
bk_load_env

mode="full"
case "${1:-}" in
    "") ;;
    --bootstrap) mode="bootstrap" ;;
    *) bk_die "usage: render_nginx.sh [--bootstrap]" ;;
esac

command -v envsubst >/dev/null || bk_die "envsubst is missing (apt install gettext-base)"
case "$BK_DOMAIN" in
    *[!A-Za-z0-9.-]*|"") bk_die "BK_DOMAIN must be a bare hostname, got: $BK_DOMAIN" ;;
esac
case "$BK_HSTS_MAX_AGE" in
    *[!0-9]*|"") bk_die "BK_HSTS_MAX_AGE must be a number of seconds" ;;
esac

out="$BK_ROOT/tls/conf.d"
src="$BK_ROOT/scripts/nginx_tls"
mkdir -p "$out"

if [ "$mode" = "full" ] && [ ! -r "/etc/letsencrypt/live/$BK_DOMAIN/fullchain.pem" ]; then
    bk_die "no certificate for $BK_DOMAIN yet; render with --bootstrap and run issue_cert.sh first"
fi

# A stale https file from an earlier full render would make a bootstrap proxy
# fail to start (missing certificate), so the directory is rebuilt each time.
rm -f "$out"/*.conf
envsubst '${BK_DOMAIN}' < "$src/00_http.conf.template" > "$out/00_http.conf"
if [ "$mode" = "full" ]; then
    envsubst '${BK_DOMAIN} ${BK_HSTS_MAX_AGE}' < "$src/10_https.conf.template" > "$out/10_https.conf"
fi

bk_say "rendered $mode configuration for $BK_DOMAIN into tls/conf.d/"
ls -1 "$out"
