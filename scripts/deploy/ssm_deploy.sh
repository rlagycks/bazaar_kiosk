#!/usr/bin/env bash
# 12A1 (D-072) -- the host side of a CD run over AWS SSM Run Command.
#
#   ssm_deploy.sh <repo-dir> <config-sha> <ref> <deploy|config-only> <region>
#
# The deploy workflow assumes an IAM role through GitHub OIDC, stores the
# configuration payload (the same `<name> <base64>` lines install_config.sh
# reads) as a SecureString parameter, and runs this file as ec2-user through
# SSM -- taken, like install_config.sh, from the workflow's own commit.
#
# The payload is read with the instance role and deleted at once, so it rests
# in Parameter Store only for the seconds between the two calls; the SSM
# command history holds refs and names, never values. From here it is the
# same path as a manual run: install_config.sh, then deploy.sh.

set -euo pipefail

die() { printf 'ssm_deploy: %s\n' "$*" >&2; exit 1; }

PARAMETER=/bazaar-kiosk/production/deploy-payload

[ $# -eq 5 ] || die "usage: ssm_deploy.sh <repo-dir> <config-sha> <ref> <deploy|config-only> <region>"
root="$1" config_sha="$2" ref="$3" mode="$4" region="$5"
[[ "$config_sha" =~ ^[0-9a-f]{40}$ ]] || die "config sha must be a full commit id"
case "$mode" in deploy|config-only) ;; *) die "mode must be deploy or config-only" ;; esac
cd "$root"
command -v aws >/dev/null || die "aws cli is missing"

payload="$(aws ssm get-parameter --region "$region" --name "$PARAMETER" \
    --with-decryption --query Parameter.Value --output text)" \
    || die "could not read $PARAMETER (instance role, or the workflow did not stage it)"
aws ssm delete-parameter --region "$region" --name "$PARAMETER" >/dev/null \
    || printf 'ssm_deploy: could not delete %s; the workflow deletes it too\n' "$PARAMETER" >&2

printf '%s\n' "$payload" | bash <(git show "$config_sha:scripts/deploy/install_config.sh") "$root"
unset payload

if [ "$mode" = "deploy" ]; then
    bash scripts/deploy/deploy.sh --yes "$ref"
else
    printf '==> configuration only; nothing deployed\n'
fi
