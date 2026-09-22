#!/usr/bin/env bash
set -euo pipefail

# OBS ne fournit pas de vrai mode headless adapté à ce cas d'usage.
# On utilise donc le meilleur démarrage allégé natif disponible :
# profil figé, scène éventuellement imposée, fenêtre réduite dans la zone
# système si possible, et vérification des fichiers manquants désactivée.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

config_get() {
  python3 "$REPO_DIR/scripts/nomade_config.py" --repository "$REPO_DIR" --get "$1"
}

PROFIL_DIRECT="${NOMADE_OBS_PROFIL_DIRECT:-$(config_get obs.profile_direct)}"
COLLECTION="${NOMADE_OBS_COLLECTION:-$(config_get obs.collection)}"
SCENE="${NOMADE_OBS_SCENE:-$(config_get obs.scene)}"
AUTOSTART_DIFFUSION="${NOMADE_OBS_AUTOSTART_DIFFUSION:-$(config_get features.autostart_stream_on_launch)}"

ARGS=(
  --profile "$PROFIL_DIRECT"
  --minimize-to-tray
  --disable-missing-files-check
)

if [[ -n "$COLLECTION" ]]; then
  ARGS+=(--collection "$COLLECTION")
fi

if [[ -n "$SCENE" ]]; then
  ARGS+=(--scene "$SCENE")
fi

if [[ "$AUTOSTART_DIFFUSION" =~ ^(1|true|True)$ ]]; then
  ARGS+=(--startstreaming)
fi

exec env MESA_GL_VERSION_OVERRIDE=3.3 obs "${ARGS[@]}"
