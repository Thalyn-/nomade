#!/usr/bin/env python3
"""Ajoute le modèle de scènes Nomade à OBS sans remplacer les éléments existants."""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "scripts"))
from nomade_obs import INJOIGNABLE, MOT_DE_PASSE, classer_erreur, code_erreur_obs, creer_client, fermer_client
from nomade_secrets import charger_secret_obs
from nomade_utils import charger_traductions, ecrire_affichages_capteurs
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


# Types de repli, du plus souhaitable au moins souhaitable. Sous Linux, depuis
# OBS 28, le texte FreeType2 s'appelle « text_ft2_source_v2 ».
ALTERNATIVES_TYPES: dict[str, tuple[str, ...]] = {
    "text_ft2_source_v2": ("text_ft2_source_v2", "text_ft2_source", "text_gdiplus_v3", "text_gdiplus_v2", "text_gdiplus"),
    "text_ft2_source": ("text_ft2_source_v2", "text_ft2_source", "text_gdiplus_v3", "text_gdiplus_v2", "text_gdiplus"),
    "color_source_v3": ("color_source_v3", "color_source_v2", "color_source"),
}
CODES_ERREUR_OBS = {600: "obs_code_600", 601: "obs_code_601", 602: "obs_code_602", 604: "obs_code_604", 605: "obs_code_605"}
REGLAGES_GDIPLUS = {"from_file": "read_from_file", "text_file": "file"}


@dataclass
class SourceIgnoree:
    nom: str
    type_demande: str
    code: int | None
    message: str


@dataclass
class CompteRendu:
    creees: list[str] = field(default_factory=list)
    presentes: list[str] = field(default_factory=list)
    rattachees: list[str] = field(default_factory=list)
    ignorees: list[SourceIgnoree] = field(default_factory=list)
    remplacements: dict[str, str] = field(default_factory=dict)
    avertissements: list[str] = field(default_factory=list)


def choisir_type(demande: str, disponibles: list[str] | None) -> str | None:
    """Retourne le type à utiliser, ou None s'il n'existe aucune alternative."""
    if disponibles is None:
        return demande
    for candidat in ALTERNATIVES_TYPES.get(demande, (demande,)):
        if candidat in disponibles:
            return candidat
    return None


def adapter_reglages(reglages: dict[str, object], type_final: str) -> dict[str, object]:
    if not type_final.startswith("text_gdiplus"):
        return reglages
    return {REGLAGES_GDIPLUS.get(cle, cle): valeur for cle, valeur in reglages.items()}


def lister_types_disponibles(client: object) -> list[str] | None:
    try:
        reponse = client.get_input_kind_list(unversioned=False)
        return list(reponse.input_kinds)
    except Exception:
        return None


def _rattacher(client: object, source: dict[str, object], scene: str, compte_rendu: CompteRendu) -> None:
    try:
        elements = client.get_scene_item_list(scene_name=scene).scene_items
        if any(element.get("sourceName") == source["name"] for element in elements):
            return
        client.send(
            "CreateSceneItem",
            {"sceneName": scene, "sourceName": source["name"], "sceneItemEnabled": source.get("enabled", False)},
        )
        compte_rendu.rattachees.append(source["name"])
    except Exception as erreur:
        if code_erreur_obs(erreur) is None and classer_erreur(erreur)[0] == INJOIGNABLE:
            raise
        compte_rendu.avertissements.append(f"{source['name']} : {erreur}")


def importer_modele(client: object, modele: dict[str, object]) -> CompteRendu:
    """Importe le modèle sans doublon ; une source en échec n'arrête pas l'import."""
    compte_rendu = CompteRendu()
    noms_scenes = {scene["sceneName"] for scene in client.get_scene_list().scenes}
    noms_sources = {source["inputName"] for source in client.get_input_list().inputs}
    disponibles = lister_types_disponibles(client)
    for nom in modele["scenes"]:
        if nom in noms_scenes:
            continue
        try:
            client.send("CreateScene", {"sceneName": nom})
        except Exception as erreur:
            code = code_erreur_obs(erreur)
            if code is None:
                raise
            if code != 601:
                compte_rendu.avertissements.append(f"{nom} : {erreur}")
                continue
        noms_scenes.add(nom)
    scene_cible = modele["scenes"][0]
    for source in modele["sources"]:
        scene = source.get("scene", scene_cible)
        if source["name"] in noms_sources:
            compte_rendu.presentes.append(source["name"])
            _rattacher(client, source, scene, compte_rendu)
            continue
        type_final = choisir_type(source["kind"], disponibles)
        if type_final is None:
            compte_rendu.ignorees.append(SourceIgnoree(source["name"], source["kind"], None, ""))
            continue
        try:
            client.send(
                "CreateInput",
                {
                    "sceneName": scene,
                    "inputName": source["name"],
                    "inputKind": type_final,
                    "inputSettings": adapter_reglages(source["settings"], type_final),
                    "sceneItemEnabled": source.get("enabled", False),
                },
            )
        except Exception as erreur:
            code = code_erreur_obs(erreur)
            if code is None:
                raise
            compte_rendu.ignorees.append(SourceIgnoree(source["name"], type_final, code, str(erreur)))
            continue
        noms_sources.add(source["name"])
        compte_rendu.creees.append(source["name"])
        if type_final != source["kind"]:
            compte_rendu.remplacements[source["name"]] = type_final
    return compte_rendu


def ajouter_modele(client: object, modele: dict[str, object]) -> tuple[int, int]:
    """Importe le modèle et retourne (sources créées, sources déjà présentes)."""
    compte_rendu = importer_modele(client, modele)
    return len(compte_rendu.creees), len(compte_rendu.presentes)


def preparer_affichages(repertoire_donnees: Path, textes: dict[str, str]) -> str | None:
    """Crée les fichiers texte d'exemple absents ; retourne une erreur éventuelle."""
    try:
        ecrire_affichages_capteurs(repertoire_donnees, {}, textes, seulement_absents=True)
    except OSError as erreur:
        return str(erreur)
    return None


def decrire_cause(source: SourceIgnoree, textes: dict[str, str]) -> str:
    if source.code is None:
        return textes["scene_cause_kind_missing"].format(kind=source.type_demande)
    cle = CODES_ERREUR_OBS.get(source.code)
    cause = textes[cle] if cle else textes["obs_code_other"]
    return f"{cause} ({source.message})" if source.message else cause


def formater_compte_rendu(compte_rendu: CompteRendu, textes: dict[str, str]) -> str:
    lignes = [textes["scene_report_summary"].format(
        created=len(compte_rendu.creees), present=len(compte_rendu.presentes),
        skipped=len(compte_rendu.ignorees),
    )]
    for nom, type_final in compte_rendu.remplacements.items():
        lignes.append(textes["scene_report_replaced"].format(name=nom, kind=type_final))
    for nom in compte_rendu.rattachees:
        lignes.append(textes["scene_report_attached"].format(name=nom))
    for source in compte_rendu.ignorees:
        lignes.append(textes["scene_report_skipped"].format(
            name=source.nom, kind=source.type_demande,
            code=source.code if source.code is not None else "-",
            cause=decrire_cause(source, textes),
        ))
    for avertissement in compte_rendu.avertissements:
        lignes.append(textes["scene_report_warning"].format(warning=avertissement))
    if compte_rendu.ignorees:
        lignes.append(textes["scene_report_hint"])
    return "\n".join(lignes)


def formater_erreur_import(erreur: BaseException, textes: dict[str, str]) -> str:
    categorie, detail = classer_erreur(erreur)
    if categorie == INJOIGNABLE:
        return textes["scene_error_connection"].format(error=detail)
    if categorie == MOT_DE_PASSE:
        return textes["scene_error_password"].format(error=detail)
    return textes["scene_error"].format(error=detail)


def importer_depuis_depot(
    client: object, repertoire_depot: Path, configuration: dict[str, object], textes: dict[str, str]
) -> CompteRendu:
    """Prépare les fichiers d'exemple des affichages puis importe le modèle du dépôt."""
    repertoire_donnees = Path(configuration["paths"]["data_dir"])
    erreur = preparer_affichages(repertoire_donnees, textes)
    modele = charger_modele(repertoire_depot / "examples/nomade-scenes.json", repertoire_donnees)
    compte_rendu = importer_modele(client, modele)
    if erreur:
        compte_rendu.avertissements.append(textes["scene_overlays_error"].format(error=erreur))
    return compte_rendu


def main() -> int:
    langue = os.environ.get("NOMADE_LANGUE", "fr")
    textes = charger_traductions(langue, REPO_DIR / "locales")
    client = None
    try:
        charger_secret_obs(REPO_DIR / "config" / "nomade.secrets")
        client = creer_client()
        scene_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "obs-studio/basic/scenes"
        print(textes["scene_notice"])
        if input(textes["scene_confirm"] + " ").strip().lower() not in {"o", "oui", "y", "yes"}:
            print(textes["scene_cancelled"])
            return 0
        sauvegardes = sauvegarder_collections(scene_dir)
        print(textes["scene_backup"].format(path=", ".join(map(str, sauvegardes)) or textes["scene_backup_none"]))
        configuration = charger_configuration(repertoire_depot=REPO_DIR)
        compte_rendu = importer_depuis_depot(client, REPO_DIR, configuration, textes)
        print(formater_compte_rendu(compte_rendu, textes))
        return 0
    except Exception as exc:
        print(formater_erreur_import(exc, textes))
        return 1
    finally:
        fermer_client(client)


if __name__ == "__main__":
    raise SystemExit(main())
