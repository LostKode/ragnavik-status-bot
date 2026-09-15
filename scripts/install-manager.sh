#!/usr/bin/env bash
set -euo pipefail

install -d -m 0755 /opt/ragnavik-status
install -m 0644 /tmp/ragnavik-status_monitor.py /opt/ragnavik-status/status_monitor.py
install -m 0644 /tmp/ragnavik-status.service /etc/systemd/system/ragnavik-status.service
install -d -m 0700 -o klastic -g klastic /etc/ragnavik-status

for token in hook control; do
  file="/etc/ragnavik-status/$token-token"
  if [[ ! -s "$file" ]]; then
    openssl rand -hex 32 > "$file"
  fi
  chown klastic:klastic "$file"
  chmod 0600 "$file"
done

if ! docker secret inspect ragnavik_status_hook_token >/dev/null 2>&1; then
  docker secret create ragnavik_status_hook_token /etc/ragnavik-status/hook-token >/dev/null
fi
if ! docker secret inspect ragnavik_bot_control_token >/dev/null 2>&1; then
  docker secret create ragnavik_bot_control_token /etc/ragnavik-status/control-token >/dev/null
fi

cat > /etc/ragnavik-status/status.env <<'EOF'
RAGNAVIK_STATUS_DIR=/var/lib/ragnavik-status
RAGNAVIK_HOOK_BIND=192.168.86.21
RAGNAVIK_HOOK_TOKEN_FILE=/etc/ragnavik-status/hook-token
RAGNAVIK_CONTROL_TOKEN_FILE=/etc/ragnavik-status/control-token
EOF
chown klastic:klastic /etc/ragnavik-status/status.env
chmod 0600 /etc/ragnavik-status/status.env

systemctl daemon-reload
systemctl enable --now ragnavik-status.service
