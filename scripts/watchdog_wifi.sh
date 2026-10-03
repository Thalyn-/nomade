#!/usr/bin/env bash
set -euo pipefail

if ping -c 1 -W 3 deb.debian.org >/dev/null 2>&1; then
  exit 0
fi

rfkill unblock wifi || true
wpa_cli -i wlan0 reconfigure || true
ifdown wlan0 || true
ifup wlan0 || systemctl restart networking || true
