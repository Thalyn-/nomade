#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Ce script doit être exécuté avec les droits administrateur."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION="${1:-}"
SERVICE="/etc/systemd/system/nomade-wifi-watchdog.service"
TIMER="/etc/systemd/system/nomade-wifi-watchdog.timer"
PROGRAM="/usr/local/sbin/nomade-watchdog-wifi"

backup_if_present() {
  local target="$1"
  if [[ -e "$target" ]]; then
    cp -a "$target" "$target.bak.$(date +%Y%m%d-%H%M%S)"
  fi
}

case "$ACTION" in
  install)
    backup_if_present "$SERVICE"
    backup_if_present "$TIMER"
    backup_if_present "$PROGRAM"
    install -m 755 "$SCRIPT_DIR/watchdog_wifi.sh" "$PROGRAM"
    cat >"$SERVICE" <<'EOF'
[Unit]
Description=Réessai réseau Nomade

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/nomade-watchdog-wifi
EOF
    cat >"$TIMER" <<'EOF'
[Unit]
Description=Vérification réseau périodique Nomade

[Timer]
OnBootSec=60s
OnUnitActiveSec=60s
Unit=nomade-wifi-watchdog.service

[Install]
WantedBy=timers.target
EOF
    chmod 644 "$SERVICE" "$TIMER"
    systemctl daemon-reload
    systemctl enable --now nomade-wifi-watchdog.timer
    echo "Surveillance réseau Nomade installée."
    ;;
  uninstall)
    systemctl disable --now nomade-wifi-watchdog.timer || true
    rm -f "$TIMER" "$SERVICE" "$PROGRAM"
    systemctl daemon-reload
    echo "Surveillance réseau Nomade désinstallée."
    ;;
  *)
    echo "Usage : $0 install|uninstall" >&2
    exit 2
    ;;
esac
