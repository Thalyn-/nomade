#!/usr/bin/env bash
set -euo pipefail

# Installation minimale pour DietPi Bookworm sur Raspberry Pi 4B.
# Ce script reste volontairement court pour limiter les risques de dérive.

export DEBIAN_FRONTEND=noninteractive

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Ce script doit être exécuté en root."
  exit 1
fi

apt-get update
apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  python3-tk \
  obs-studio

# Répertoire local de données capteurs/chat (données potentiellement sensibles).
install -d -m 700 /var/lib/nomade

# Environnement Python isolé pour éviter de polluer le système.
python3 -m venv /opt/nomade-venv
/opt/nomade-venv/bin/pip install --upgrade pip
/opt/nomade-venv/bin/pip install "obsws-python>=1.7.0,<2.0.0"

echo "Installation terminée."
echo "Définissez OBS_MDP puis lancez ./scripts/lancer_nomade.sh"
