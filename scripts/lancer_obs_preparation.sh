#!/usr/bin/env bash
set -euo pipefail

# Lance OBS Studio complet pour préparer les scènes, sources et profils.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

config_get() {
  python3 "$REPO_DIR/scripts/nomade_config.py" --repository "$REPO_DIR" --get "$1"
}

PROFIL_PREPARATION="${NOMADE_OBS_PROFIL_PREPARATION:-$(config_get obs.profile_preparation)}"
COLLECTION="${NOMADE_OBS_COLLECTION:-$(config_get obs.collection)}"

ARGS=(--profile "$PROFIL_PREPARATION")
if [[ -n "$COLLECTION" ]]; then
  ARGS+=(--collection "$COLLECTION")
fi

exec env MESA_GL_VERSION_OVERRIDE=3.3 obs "${ARGS[@]}"
