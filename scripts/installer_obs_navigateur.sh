#!/usr/bin/env bash
set -euo pipefail

# Installe OBS Studio avec la Source Navigateur (Browser Source) fonctionnelle
# sur Raspberry Pi 4B (DietPi / Debian Bookworm, architecture ARM64).
#
# Contexte :
# Le paquet officiel fourni par "apt install obs-studio" sur l'architecture
# ARM64 de Debian n'inclut pas le plugin navigateur : l'intégration de
# Chromium (CEF) y est désactivée par les mainteneurs, car jugée trop lourde
# ou complexe à compiler pour cette cible.
#
# Ce script installe à la place un paquet .deb pré-compilé, maintenu par la
# communauté Pi-Apps, qui intègre nativement la Source Navigateur.

export DEBIAN_FRONTEND=noninteractive
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

texte() {
  PYTHONPATH="$REPO_DIR/scripts" python3 -c \
    'import os, sys; from pathlib import Path; from nomade_utils import charger_traductions; print(charger_traductions(os.environ.get("NOMADE_LANGUE", "fr"), Path(sys.argv[1]) / "locales")[sys.argv[2]])' \
    "$REPO_DIR" "$1"
}

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Ce script doit être exécuté en root."
  exit 1
fi

# Un remplacement éventuel n'est effectué qu'après confirmation et après
# téléchargement réussi du paquet de remplacement.
OBS_EXISTANT=0
if dpkg -l | grep -q '^ii  obs-studio'; then
  echo "$(texte obs_existing)"
  read -r -p "$(texte obs_confirm_replace) " REPONSE
  if [[ ! "$REPONSE" =~ ^(o|O|oui|Oui|OUI|y|Y|yes|Yes|YES)$ ]]; then
    echo "$(texte obs_replace_cancelled)"
    exit 1
  fi
  OBS_EXISTANT=1
fi

HOTE="github.com"
DEPOT="Pi-Apps-Coders/files/releases/download/large-files"
PAQUET="obs-studio-30.2.2-1-arm64-bookworm.deb"
PAQUET_LOCAL="/tmp/obs.deb"

echo "Téléchargement du paquet OBS (Pi-Apps, avec Source Navigateur)..."
wget -O "$PAQUET_LOCAL" "https://${HOTE}/${DEPOT}/${PAQUET}"

# Ne retirez l'ancien paquet que lorsque son remplacement a bien été obtenu.
if [[ "$OBS_EXISTANT" -eq 1 ]]; then
  apt-get purge -y obs-studio obs-plugins
fi

echo "Installation du paquet et résolution automatique des dépendances..."
apt-get install -y "$PAQUET_LOCAL"

rm -f "$PAQUET_LOCAL"

echo "OBS Studio installé avec la Source Navigateur (Browser Source)."
echo "Utilisez ./scripts/lancer_obs_preparation.sh pour la préparation,"
echo "./scripts/lancer_obs_direct.sh pour le direct allégé,"
echo "ou ./scripts/lancer_obs.sh pour la compatibilité historique."
