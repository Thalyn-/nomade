#!/usr/bin/env bash
set -euo pipefail

# Lance OBS Studio complet pour préparer les scènes, sources et profils.

PROFIL_PREPARATION="${NOMADE_OBS_PROFIL_PREPARATION:-Nomade preparation}"
COLLECTION="${NOMADE_OBS_COLLECTION:-}"

ARGS=(--profile "$PROFIL_PREPARATION")
if [[ -n "$COLLECTION" ]]; then
  ARGS+=(--collection "$COLLECTION")
fi

exec env MESA_GL_VERSION_OVERRIDE=3.3 obs "${ARGS[@]}"
