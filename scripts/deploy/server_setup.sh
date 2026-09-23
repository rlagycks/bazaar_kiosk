#!/usr/bin/env bash
# 12A1 -- one-time preparation of a fresh Amazon Linux 2023 host (EC2, D-071).
#
#   sudo bash scripts/deploy/server_setup.sh [deploy-user]     default: ec2-user
#
# Installs Docker (the distribution's engine + buildx, and the compose v2
# plugin from its release, checksum-pinned), git, certbot and envsubst,
# enables certbot's renewal timer, creates the certbot webroot the proxy
# mounts, and installs the renewal hook that reloads the proxy after each
# certificate renewal. Idempotent: safe to run again. It does not touch the
# repository checkout, the configuration (the deploy workflow writes .env and
# secrets/), or start the application.
#
# Network exposure is the security group's job, not this script's: inbound
# 80/443 from anywhere, 22 as decided in the runbook, nothing else.

set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
. /etc/os-release
[ "${ID:-}" = "amzn" ] && [ "${VERSION_ID:-}" = "2023" ] \
    || { echo "this script targets Amazon Linux 2023 (found: ${PRETTY_NAME:-unknown})" >&2; exit 1; }
deploy_user="${1:-${SUDO_USER:-ec2-user}}"
id "$deploy_user" >/dev/null 2>&1 || { echo "no such user: $deploy_user" >&2; exit 1; }

dnf install -y -q docker git gettext certbot

# Compose v2 is not packaged for AL2023. The release binary is pinned by
# version and sha256; bump both together.
COMPOSE_VERSION=v5.5.1
case "$(uname -m)" in
    aarch64) compose_arch=aarch64
             COMPOSE_SHA256=732e3a84c1a0f67256ce80bc2598a24546b10ca05f9faa97efceb1171ece2ef7 ;;
    *) echo "no pinned compose checksum for $(uname -m); add one next to COMPOSE_VERSION" >&2; exit 1 ;;
esac
plugin_dir=/usr/local/lib/docker/cli-plugins
plugin="$plugin_dir/docker-compose"
if ! { [ -x "$plugin" ] && echo "$COMPOSE_SHA256  $plugin" | sha256sum -c --status; }; then
    mkdir -p "$plugin_dir"
    tmp="$(mktemp)"
    curl -fsSL -o "$tmp" \
        "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-${compose_arch}"
    echo "$COMPOSE_SHA256  $tmp" | sha256sum -c --status \
        || { rm -f "$tmp"; echo "docker compose download failed its checksum" >&2; exit 1; }
    install -m 755 "$tmp" "$plugin"
    rm -f "$tmp"
fi

systemctl enable --now docker
usermod -aG docker "$deploy_user"
docker compose version
docker buildx version

# AL2023's certbot ships the timer but does not enable it.
systemctl enable --now certbot-renew.timer

webroot=/var/lib/bazaar_kiosk/certbot-www
mkdir -p "$webroot"
chmod 755 /var/lib/bazaar_kiosk "$webroot"

# certbot's timer renews; this hook makes the running proxy pick the new
# files up. The compose project directory is whatever the deploy user checked
# out; the default matches the runbook.
repo_dir="${BK_REPO_DIR:-/srv/bazaar_kiosk}"
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/bazaar-kiosk-reload.sh <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$repo_dir"
docker compose -f compose.prod.yaml -f compose.tls.yaml exec -T proxy nginx -t
docker compose -f compose.prod.yaml -f compose.tls.yaml exec -T proxy nginx -s reload
EOF
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/bazaar-kiosk-reload.sh

if [ ! -d "$repo_dir" ]; then
    mkdir -p "$repo_dir"
    chown "$deploy_user":"$deploy_user" "$repo_dir"
    echo "==> clone the repository as $deploy_user into $repo_dir, then continue with the runbook"
fi

echo "==> done. Log out and back in as $deploy_user so the docker group applies."
