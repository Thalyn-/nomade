#!/usr/bin/env bash
set -euo pipefail

# Lance l'ingestion locale des capteurs via MQTT, idéalement sur la liaison
# Bluetooth configurée hors de ce dépôt (PAN/BNEP ou transport équivalent).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

config_get() {
  python3 "$REPO_DIR/scripts/nomade_config.py" --repository "$REPO_DIR" --get "$1"
}

VENV_DIR="${NOMADE_VENV_DIR:-$(config_get paths.python_venv)}"
VENV_BIN="$VENV_DIR/bin/python"

if [[ ! -x "$VENV_BIN" ]]; then
  echo "Environnement Python introuvable: $VENV_BIN"
  echo "Exécutez d'abord: ./scripts/install_nomade.sh"
  exit 1
fi

exec "$VENV_BIN" "$REPO_DIR/scripts/capteurs_mqtt.py" "$@"
