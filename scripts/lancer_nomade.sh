#!/usr/bin/env bash
set -euo pipefail

# Lance l'interface locale de contrôle du direct.
# OBS doit être ouvert et obs-websocket activé.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_BIN="/opt/nomade-venv/bin/python"

if [[ ! -x "$VENV_BIN" ]]; then
  echo "Environnement Python introuvable: $VENV_BIN"
  echo "Exécutez d'abord: ./scripts/install_nomade.sh"
  exit 1
fi

exec "$VENV_BIN" "$REPO_DIR/scripts/interface_nomade.py" "$@"
