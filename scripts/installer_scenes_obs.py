#!/usr/bin/env python3
"""Ajoute le modèle de scènes Nomade à OBS sans remplacer les éléments existants."""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "scripts"))
from nomade_utils import charger_traductions
from nomade_config import charger_configuration


def charger_modele(chemin: Path, repertoire_donnees: Path) -> dict[str, object]:
    modele = json.loads(Path(chemin).read_text(encoding="utf-8"))
    for source in modele.get("sources", []):
        fichier = source.get("settings", {}).get("text_file")
        if fichier:
            source["settings"]["text_file"] = fichier.replace("{data_dir}", str(repertoire_donnees))
    return modele


def sauvegarder_collections(repertoire: Path) -> list[Path]:
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    sauvegardes = []
    for fichier in Path(repertoire).glob("*.json"):
        destination = fichier.with_name(f"{fichier.name}.{horodatage}.bak")
        shutil.copy2(fichier, destination)
        sauvegardes.append(destination)
    return sauvegardes


def ajouter_modele(client: object, modele: dict[str, object]) -> tuple[int, int]:
    scenes = client.get_scene_list().scenes
    sources = client.get_input_list().inputs
    noms_scenes = {scene["sceneName"] for scene in scenes}
    noms_sources = {source["inputName"] for source in sources}
    ajouts = 0
    ignores = 0
    for nom in modele["scenes"]:
        if nom not in noms_scenes:
            client.send("CreateScene", {"sceneName": nom})
            noms_scenes.add(nom)
    scene_cible = modele["scenes"][0]
    for source in modele["sources"]:
        if source["name"] in noms_sources:
            ignores += 1
            continue
        client.send(
            "CreateInput",
            {
                "sceneName": source.get("scene", scene_cible),
                "inputName": source["name"],
                "inputKind": source["kind"],
                "inputSettings": source["settings"],
                "sceneItemEnabled": source.get("enabled", False),
            },
        )
        noms_sources.add(source["name"])
        ajouts += 1
    return ajouts, ignores


def main() -> int:
    langue = os.environ.get("NOMADE_LANGUE", "fr")
    textes = charger_traductions(langue, REPO_DIR / "locales")
    try:
        from obsws_python import ReqClient

        client = ReqClient(
            "127.0.0.1", 4455, os.environ.get("OBS_MDP", ""), timeout=3
        )
        scene_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "obs-studio/basic/scenes"
        print(textes["scene_notice"])
        if input(textes["scene_confirm"] + " ").strip().lower() not in {"o", "oui", "y", "yes"}:
            print(textes["scene_cancelled"])
            return 0
        sauvegardes = sauvegarder_collections(scene_dir)
        print(textes["scene_backup"].format(path=", ".join(map(str, sauvegardes)) or textes["scene_backup_none"]))
        configuration = charger_configuration(repertoire_depot=REPO_DIR)
        modele = charger_modele(
            REPO_DIR / "examples/nomade-scenes.json",
            Path(configuration["paths"]["data_dir"]),
        )
        ajouts, ignores = ajouter_modele(client, modele)
        print(textes["scene_done"].format(added=ajouts, skipped=ignores))
        return 0
    except Exception as exc:
        print(textes["scene_error"].format(error=exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
