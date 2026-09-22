#!/usr/bin/env bash
set -euo pipefail

# OBS ne fournit pas de vrai mode headless adapté à ce cas d'usage.
# On utilise donc le meilleur démarrage allégé natif disponible :
# profil figé, scène éventuellement imposée, fenêtre réduite dans la zone
# système si possible, et vérification des fichiers manquants désactivée.

PROFIL_DIRECT="${NOMADE_OBS_PROFIL_DIRECT:-Nomade direct fixe}"
COLLECTION="${NOMADE_OBS_COLLECTION:-}"
SCENE="${NOMADE_OBS_SCENE:-}"
AUTOSTART_DIFFUSION="${NOMADE_OBS_AUTOSTART_DIFFUSION:-0}"

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

if [[ "$AUTOSTART_DIFFUSION" == "1" ]]; then
  ARGS+=(--startstreaming)
fi

exec env MESA_GL_VERSION_OVERRIDE=3.3 obs "${ARGS[@]}"
