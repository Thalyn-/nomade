#!/usr/bin/env bash
set -euo pipefail

# Lance OBS Studio avec la surcharge OpenGL nécessaire sur le GPU du
# Raspberry Pi 4B, faute de quoi OBS peut ne pas s'initialiser correctement.

exec env MESA_GL_VERSION_OVERRIDE=3.3 obs
