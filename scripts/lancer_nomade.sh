#!/usr/bin/env bash
set -euo pipefail

# Lance l'interface locale de contrôle du direct et démarre OBS en mode
# direct allégé si aucun processus OBS local n'est déjà actif.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_BIN="/opt/nomade-venv/bin/python"
AUTOSTART_OBS="${NOMADE_AUTOSTART_OBS:-1}"
LOG_OBS_DIRECT="/tmp/nomade-obs-direct.log"

if [[ ! -x "$VENV_BIN" ]]; then
  echo "Environnement Python introuvable: $VENV_BIN"
  echo "Exécutez d'abord: ./scripts/install_nomade.sh"
  exit 1
fi

if [[ "$AUTOSTART_OBS" == "1" ]] && ! pgrep -x obs >/dev/null 2>&1; then
  nohup "$SCRIPT_DIR/lancer_obs_direct.sh" >"$LOG_OBS_DIRECT" 2>&1 &
fi

exec "$VENV_BIN" "$REPO_DIR/scripts/interface_nomade.py" --obs-hote 127.0.0.1 "$@"
