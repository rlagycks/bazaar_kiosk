#!/usr/bin/env bash
# 12A1 -- one-time preparation of a fresh Ubuntu 24.04 host (EC2).
#
#   sudo bash scripts/deploy/server_setup.sh [deploy-user]
#
# Installs Docker (Ubuntu's docker.io + compose v2 plugin), certbot and
# envsubst, creates the certbot webroot the proxy mounts, and installs the
# renewal hook that reloads the proxy after each certificate renewal.
# Idempotent: safe to run again. It does not touch the repository checkout,
# secrets, or start anything.
#
# Network exposure is the security group's job, not this script's: inbound
# 80/443 from anywhere, 22 from the operator's address only, nothing else.

set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
deploy_user="${1:-${SUDO_USER:-ubuntu}}"
id "$deploy_user" >/dev/null 2>&1 || { echo "no such user: $deploy_user" >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q ca-certificates curl git gettext-base certbot docker.io docker-compose-v2

systemctl enable --now docker
usermod -aG docker "$deploy_user"

webroot=/var/lib/bazaar_kiosk/certbot-www
mkdir -p "$webroot"
chmod 755 /var/lib/bazaar_kiosk "$webroot"

# certbot's own timer (certbot.timer) renews; this hook makes the running proxy
# pick the new files up. The compose project directory is whatever the deploy
# user checked out; the default matches the runbook.
repo_dir="${BK_REPO_DIR:-/srv/bazaar_kiosk}"
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/bazaar-kiosk-reload.sh <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$repo_dir"
docker compose -f compose.prod.yaml -f compose.tls.yaml exec -T proxy nginx -s reload
EOF
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/bazaar-kiosk-reload.sh

if [ ! -d "$repo_dir" ]; then
    mkdir -p "$(dirname "$repo_dir")"
    chown "$deploy_user":"$deploy_user" "$(dirname "$repo_dir")"
    echo "==> clone the repository as $deploy_user into $repo_dir, then continue with the runbook"
fi

echo "==> done. Log out and back in as $deploy_user so the docker group applies."
