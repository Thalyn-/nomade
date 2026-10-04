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
  wpasupplicant \
  iw \
  rfkill \
  ifupdown \
  iproute2 \
  iputils-ping \
  onboard \
  avahi-daemon \
  avahi-utils \
  ffmpeg \
  wget

config_get() {
  python3 "$REPO_DIR/scripts/nomade_config.py" --repository "$REPO_DIR" --get "$1"
}

VENV_DIR="${NOMADE_VENV_DIR:-$(config_get paths.python_venv)}"
DATA_DIR="${NOMADE_DATA_DIR:-$(config_get paths.data_dir)}"
LOG_DIR="${NOMADE_LOG_DIR:-$(config_get paths.log_dir)}"

# OBS Studio n'est volontairement pas installé via "apt install obs-studio" :
# le paquet officiel ARM64 de Debian Bookworm ne contient pas la Source
# Navigateur (Browser Source), car l'intégration Chromium (CEF) y est
# désactivée par les mainteneurs. Voir scripts/installer_obs_navigateur.sh
# et la section dédiée du README pour l'installation d'un paquet OBS
# incluant la Source Navigateur.
"$SCRIPT_DIR/installer_obs_navigateur.sh"

# Répertoires locaux de données et journaux (données potentiellement sensibles).
install -d -m 700 "$DATA_DIR" "$LOG_DIR"

# Environnement Python isolé pour éviter de polluer le système.
if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$REPO_DIR/requirements.txt"

if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
  GROUPE_UTILISATEUR="$(id -gn "$SUDO_USER")"
  HOME_UTILISATEUR="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
  if [[ "$DATA_DIR" == "/var/lib/nomade" && ! -L "$DATA_DIR" ]]; then
    chown "$SUDO_USER:$GROUPE_UTILISATEUR" "$DATA_DIR"
  fi
  if [[ "$LOG_DIR" == "/var/log/nomade" && ! -L "$LOG_DIR" ]]; then
    chown "$SUDO_USER:$GROUPE_UTILISATEUR" "$LOG_DIR"
  fi
  runuser -u "$SUDO_USER" -- env \
    HOME="$HOME_UTILISATEUR" \
    NOMADE_LANGUE="$(config_get general.language)" \
    "$VENV_DIR/bin/python" "$SCRIPT_DIR/capteurs_mqtt.py" --initialiser-affichages
else
  "$VENV_DIR/bin/python" "$SCRIPT_DIR/capteurs_mqtt.py" --initialiser-affichages
fi

echo "Installation terminée."
echo "Configuration locale : copiez config/nomade.local.toml.example vers config/nomade.local.toml si besoin."
echo "Préparation OBS complète : ./scripts/lancer_obs_preparation.sh"
echo "Direct OBS allégé : ./scripts/lancer_obs_direct.sh"
echo "Interface locale : définissez OBS_MDP puis lancez ./scripts/lancer_nomade.sh"
echo "Ingestion capteurs MQTT : ./scripts/lancer_capteurs_mqtt.sh"
echo "Assistant de premier démarrage : ./scripts/primum_initium.sh"
if [[ -n "${DISPLAY:-}" && -n "${SUDO_USER:-}" ]]; then
  runuser -u "$SUDO_USER" -- env \
    DISPLAY="$DISPLAY" \
    XAUTHORITY="${XAUTHORITY:-/home/$SUDO_USER/.Xauthority}" \
    HOME="/home/$SUDO_USER" \
    "$VENV_DIR/bin/python" "$SCRIPT_DIR/primum_initium.py"
else
  "$VENV_DIR/bin/python" "$SCRIPT_DIR/primum_initium.py" --diagnostic
fi
