#!/usr/bin/env bash
set -euo pipefail

# Compatibilité historique : lance OBS Studio complet pour la préparation
# via le nouveau script dédié.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/lancer_obs_preparation.sh" "$@"
