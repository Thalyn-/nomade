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

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Ce script doit être exécuté en root."
  exit 1
fi

# Nettoyage d'une éventuelle ancienne installation OBS pour éviter tout
# conflit de version ou dépendance cassée.
if dpkg -l | grep -q '^ii  obs-studio'; then
  apt-get purge -y obs-studio obs-plugins || true
  apt-get autoremove -y
fi

HOTE="github.com"
DEPOT="Pi-Apps-Coders/files/releases/download/large-files"
PAQUET="obs-studio-30.2.2-1-arm64-bookworm.deb"
PAQUET_LOCAL="/tmp/obs.deb"

echo "Téléchargement du paquet OBS (Pi-Apps, avec Source Navigateur)..."
wget -O "$PAQUET_LOCAL" "https://${HOTE}/${DEPOT}/${PAQUET}"

echo "Installation du paquet et résolution automatique des dépendances..."
apt-get install -y "$PAQUET_LOCAL"

rm -f "$PAQUET_LOCAL"

echo "OBS Studio installé avec la Source Navigateur (Browser Source)."
echo "Utilisez ./scripts/lancer_obs.sh pour le démarrer avec l'accélération graphique adaptée au Raspberry Pi 4."
