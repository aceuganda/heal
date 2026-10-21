#!/usr/bin/env bash
# One-time setup of a k3s node for `make deploy` (README § Kubernetes). On the
# node, from a copy of this directory:
#
#   sudo ALLOW_FROM=<network>/<mask> TLS_SAN=<name you deploy against> ./setup-server.sh
#
# Everything goes in the `heal` namespace. Safe to re-run: the settings
# ConfigMap and the secrets are created once and never overwritten.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
K3S=/usr/local/bin/k3s
NS=heal
k() { "$K3S" kubectl "$@"; }
say() { printf '\n== %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
[ -x "$K3S" ] || { echo "k3s is not installed at $K3S" >&2; exit 1; }

restart=no

# Writes $2 to $1 only if it differs, and marks k3s for a restart if so.
install_config() {
  if ! printf '%s\n' "$2" | cmp -s - "$1" 2>/dev/null; then
    mkdir -p "$(dirname "$1")"
    printf '%s\n' "$2" > "$1"
    restart=yes
    echo "wrote $1"
  fi
}

say "k3s settings"
# containerd may pull the loopback-only registry over plain HTTP.
install_config /etc/rancher/k3s/registries.yaml 'mirrors:
  "localhost:5050":
    endpoint:
      - "http://localhost:5050"'
if [ -n "${TLS_SAN:-}" ]; then
  # A drop-in, so an existing config.yaml is left untouched.
  install_config /etc/rancher/k3s/config.yaml.d/heal-tls-san.yaml "tls-san+: [\"$TLS_SAN\"]"
fi
if [ "$restart" = yes ]; then
  systemctl restart k3s
  echo "restarted k3s"
fi
for _ in $(seq 60); do k get --raw /readyz >/dev/null 2>&1 && break; sleep 2; done
k get --raw /readyz >/dev/null

say "namespace, deployer account, registry"
k apply -f "$HERE/rbac/deployer.yaml" -f "$HERE/registry/registry.yaml"

say "settings and secrets (created once, never overwritten)"
if k -n "$NS" get configmap env-configmap >/dev/null 2>&1; then
  echo "env-configmap exists; change it with: sudo k3s kubectl -n $NS edit configmap env-configmap"
elif [ -f "$HERE/env-configmap.yaml" ]; then
  k -n "$NS" apply -f "$HERE/env-configmap.yaml"
else
  echo "no env-configmap yet; copy env-configmap.yaml here and re-run" >&2
fi
if k -n "$NS" get secret heal-secrets >/dev/null 2>&1; then
  echo "heal-secrets exists"
else
  k -n "$NS" create secret generic heal-secrets \
    --from-literal=postgres_user=postgres \
    --from-literal=postgres_password="$(openssl rand -base64 24)" \
    --from-literal=gen_ai_api_key=""
fi

if [ -n "${ALLOW_FROM:-}" ]; then
  say "firewall: API port 6443 from $ALLOW_FROM only"
  ufw allow from "$ALLOW_FROM" to any port 6443 proto tcp
fi

say "waiting for the registry"
k -n "$NS" rollout status deployment/heal-registry --timeout=180s

# The token controller fills the Secret asynchronously.
token=""
for _ in $(seq 30); do
  token="$(k -n "$NS" get secret heal-deployer-token -o jsonpath='{.data.token}' | base64 -d)"
  [ -n "$token" ] && break
  sleep 1
done
[ -n "$token" ] || { echo "the deployer token was not issued" >&2; exit 1; }

owner="${SUDO_USER:-root}"
ca="$(getent passwd "$owner" | cut -d: -f6)/heal-ca.crt"
k -n "$NS" get secret heal-deployer-token -o jsonpath='{.data.ca\.crt}' | base64 -d > "$ca"
chown "$owner" "$ca"

say "done"
echo "API certificate names:"
openssl x509 -noout -ext subjectAltName \
  -in /var/lib/rancher/k3s/server/tls/serving-kube-apiserver.crt | tail -n +2
cat <<EOF

CA certificate: $ca   (copy it to ~/.config/heal-deploy/ca.crt on your machine)
Deploy token -- a password, paste it into DEPLOY_KUBE_TOKEN and nowhere else:

$token

EOF
