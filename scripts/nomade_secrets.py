"""Gestion des secrets présents uniquement sur la machine."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path


def charger_secret_obs(chemin: Path) -> None:
    if os.environ.get("OBS_MDP") or not Path(chemin).is_file():
        return
    chemin = Path(chemin)
    if chemin.stat().st_mode & 0o077:
        os.chmod(chemin, 0o600)
    contenu = json.loads(chemin.read_text(encoding="utf-8"))
    if not isinstance(contenu, dict):
        raise ValueError("invalid_local_secrets")
    mot_de_passe = contenu.get("OBS_MDP", "")
    if isinstance(mot_de_passe, str):
        os.environ["OBS_MDP"] = mot_de_passe


def enregistrer_secret_obs(chemin: Path, mot_de_passe: str) -> Path | None:
    if not mot_de_passe or any(ord(caractere) < 32 for caractere in mot_de_passe):
        raise ValueError("invalid_obs_password")
    resultat = enregistrer_secrets(chemin, {"OBS_MDP": mot_de_passe})
    os.environ["OBS_MDP"] = mot_de_passe
    return resultat


def enregistrer_secrets(chemin: Path, nouvelles_valeurs: dict[str, str]) -> Path | None:
    chemin = Path(chemin)
    existants = {}
    if chemin.exists():
        try:
            existants = json.loads(chemin.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise ValueError("invalid_local_secrets")
        if not isinstance(existants, dict):
            raise ValueError("invalid_local_secrets")
    for nom, valeur in nouvelles_valeurs.items():
        if not nom.isidentifier() or not isinstance(valeur, str):
            raise ValueError("invalid_local_secrets")
        existants[nom] = valeur
    sauvegarde = None
    if chemin.exists():
        horodatage = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        sauvegarde = chemin.with_name(f"{chemin.name}.{horodatage}.bak")
        shutil.copy2(chemin, sauvegarde)
        os.chmod(sauvegarde, 0o600)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    descripteur, temporaire = tempfile.mkstemp(dir=chemin.parent, prefix=".nomade.secrets.")
    try:
        with os.fdopen(descripteur, "w", encoding="utf-8") as fichier:
            json.dump(existants, fichier)
            fichier.write("\n")
            fichier.flush()
            os.fsync(fichier.fileno())
        os.chmod(temporaire, 0o600)
        os.replace(temporaire, chemin)
    except Exception:
        Path(temporaire).unlink(missing_ok=True)
        raise
    return sauvegarde
