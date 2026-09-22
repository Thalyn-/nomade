#!/usr/bin/env python3
"""Utilitaires partagés pour Nomade."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


LANGUE_PAR_DEFAUT = "fr"


def charger_traductions(langue: str, dossier_locales: Path) -> dict[str, str]:
    """Charge la langue demandée avec repli systématique sur le français."""
    base = _charger_fichier_json(dossier_locales / f"{LANGUE_PAR_DEFAUT}.json")
    langue_normalisee = (langue or LANGUE_PAR_DEFAUT).strip().lower()
    if langue_normalisee == LANGUE_PAR_DEFAUT:
        return base

    cible = dossier_locales / f"{langue_normalisee}.json"
    if not cible.exists():
        return base

    traductions = base.copy()
    traductions.update(_charger_fichier_json(cible))
    return traductions


def _charger_fichier_json(chemin: Path) -> dict[str, str]:
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    if not isinstance(donnees, dict):
        raise ValueError(f"Fichier de traduction invalide : {chemin}")

    return {str(cle): str(valeur) for cle, valeur in donnees.items()}


def est_hote_obs_local(hote: str) -> bool:
    """Valide les hôtes locaux explicitement autorisés."""
    return hote in {"127.0.0.1", "localhost", "::1"}


def valider_charge_capteurs(donnees: Any) -> dict[str, Any]:
    """Valide la forme minimale attendue pour le fichier des capteurs."""
    if not isinstance(donnees, dict):
        raise ValueError("Le message JSON doit être un objet.")

    _valider_objet_optionnel(donnees, "position")
    _valider_objet_optionnel(donnees, "reseau")
    _valider_objet_optionnel(donnees, "meteo")

    return donnees


def _valider_objet_optionnel(donnees: dict[str, Any], cle: str) -> None:
    if cle in donnees and not isinstance(donnees[cle], dict):
        raise ValueError(f"Le champ '{cle}' doit être un objet JSON.")


def ecrire_json_atomique(chemin: Path, donnees: dict[str, Any]) -> None:
    """Écrit un JSON UTF-8 de façon atomique sur le même système de fichiers."""
    chemin.parent.mkdir(parents=True, exist_ok=True)

    contenu = json.dumps(donnees, ensure_ascii=False, sort_keys=True)
    descripteur, chemin_temporaire = tempfile.mkstemp(
        prefix=f".{chemin.name}.",
        suffix=".tmp",
        dir=str(chemin.parent),
        text=True,
    )

    try:
        os.chmod(chemin_temporaire, 0o600)
        with os.fdopen(descripteur, "w", encoding="utf-8") as fichier:
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())
        os.replace(chemin_temporaire, chemin)
    except Exception:
        try:
            os.unlink(chemin_temporaire)
        except FileNotFoundError:
            pass
        raise
