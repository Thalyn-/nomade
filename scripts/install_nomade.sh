#!/usr/bin/env bash
set -euo pipefail

# Installation minimale pour DietPi Bookworm sur Raspberry Pi 4B.
# Ce script reste volontairement court pour limiter les risques de dérive.

export DEBIAN_FRONTEND=noninteractive

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Ce script doit être exécuté en root."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

apt-get update
apt-get install -y \
  mosquitto \
  mosquitto-clients \
  python3 \
  python3-venv \
  python3-pip \
  python3-tk \
  wget

# OBS Studio n'est volontairement pas installé via "apt install obs-studio" :
# le paquet officiel ARM64 de Debian Bookworm ne contient pas la Source
# Navigateur (Browser Source), car l'intégration Chromium (CEF) y est
# désactivée par les mainteneurs. Voir scripts/installer_obs_navigateur.sh
# et la section dédiée du README pour l'installation d'un paquet OBS
# incluant la Source Navigateur.
"$SCRIPT_DIR/installer_obs_navigateur.sh"

# Répertoire local de données capteurs/chat (données potentiellement sensibles).
install -d -m 700 /var/lib/nomade

# Environnement Python isolé pour éviter de polluer le système.
if [[ ! -d /opt/nomade-venv ]]; then
  python3 -m venv /opt/nomade-venv
fi
/opt/nomade-venv/bin/pip install --upgrade pip
/opt/nomade-venv/bin/pip install -r "$REPO_DIR/requirements.txt"

echo "Installation terminée."
echo "Préparation OBS complète : ./scripts/lancer_obs_preparation.sh"
echo "Direct OBS allégé : ./scripts/lancer_obs_direct.sh"
echo "Interface locale : définissez OBS_MDP puis lancez ./scripts/lancer_nomade.sh"
echo "Ingestion capteurs MQTT : ./scripts/lancer_capteurs_mqtt.sh"
