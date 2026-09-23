#!/usr/bin/env python3
"""Chargement et validation de la configuration globale Nomade."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("Python 3.11 ou plus récent est requis pour lire la configuration TOML.") from exc

from nomade_utils import est_hote_obs_local


SERVICES_CHAT = {"none", "velora", "botrix", "custom"}
TYPES_SOURCES_VIDEO = {"capture_usb", "srt", "webcam"}
IDENTIFIANTS_OVERLAYS = {"selfie", "carte", "vitesse", "pulsations", "meteo", "heure", "chat_multicanal"}


class ErreurConfiguration(ValueError):
    """Erreur métier pour une configuration invalide."""


def repertoire_depot_par_defaut() -> Path:
    return Path(__file__).resolve().parent.parent


def chemins_configuration(repertoire_depot: Path | None = None) -> tuple[Path, Path]:
    depot = Path(repertoire_depot) if repertoire_depot else repertoire_depot_par_defaut()
    dossier = depot / "config"
    return dossier / "nomade.toml", dossier / "nomade.local.toml"


def charger_configuration(
    *,
    repertoire_depot: Path | None = None,
    fichier_config: Path | None = None,
    fichier_local: Path | None = None,
) -> dict[str, Any]:
    depot = Path(repertoire_depot) if repertoire_depot else repertoire_depot_par_defaut()
    config_par_defaut, config_local = chemins_configuration(depot)
    config_path = Path(fichier_config) if fichier_config else config_par_defaut
    local_path = Path(fichier_local) if fichier_local else config_local

    configuration = _charger_toml(config_path)
    if local_path.exists():
        configuration = _fusionner(configuration, _charger_toml(local_path))

    return _normaliser_configuration(configuration, depot)


def url_chat_active(configuration: dict[str, Any]) -> str | None:
    chat = configuration["chat"]
    service = chat["service"]
    if service == "none":
        return None
    if service == "custom":
        return chat["custom_url"] or None
    return chat[f"{service}_url"] or None


def afficher_diagnostic(
    configuration: dict[str, Any],
    *,
    fichier_config: Path | None = None,
    fichier_local: Path | None = None,
) -> str:
    config_path = fichier_config or chemins_configuration(Path(configuration["paths"]["repository"]))[0]
    local_path = fichier_local or chemins_configuration(Path(configuration["paths"]["repository"]))[1]
    url_chat = url_chat_active(configuration)
    hote_chat = urlparse(url_chat).netloc if url_chat else "aucune URL"
    lignes = [
        f"Configuration Nomade valide : {config_path}",
        f"Surcharge locale : {'présente' if Path(local_path).exists() else 'absente'} ({local_path})",
        f"Langue interface : {configuration['general']['language']}",
        f"OBS local : {configuration['obs']['host']}:{configuration['obs']['port']}",
        f"Profil direct OBS : {configuration['obs']['profile_direct']}",
        f"MQTT capteurs : {configuration['mqtt']['host']}:{configuration['mqtt']['port']} sur interface {configuration['mqtt']['network_interface']}",
        f"Chat multicanal : {configuration['chat']['service']} ({hote_chat})",
        f"Sources vidéo configurées : {len(configuration['video_sources'])}",
        f"Presets configurés : {len(configuration['presets'])}",
        f"Venv Python : {configuration['paths']['python_venv']}",
        f"Répertoire données : {configuration['paths']['data_dir']}",
        "Tkinter reste l'interface locale principale ; aucune interface web obligatoire n'est activée.",
        "Multistream complet non automatisé : préparez encore les destinations directement dans OBS.",
    ]
    return "\n".join(lignes)


def lire_cle(configuration: dict[str, Any], chemin_cle: str) -> Any:
    valeur: Any = configuration
    for segment in chemin_cle.split("."):
        if not isinstance(valeur, dict) or segment not in valeur:
            raise ErreurConfiguration(f"Clé de configuration introuvable : {chemin_cle}")
        valeur = valeur[segment]
    return valeur


def _charger_toml(chemin: Path) -> dict[str, Any]:
    if not chemin.exists():
        raise ErreurConfiguration(f"Fichier de configuration introuvable : {chemin}")
    with chemin.open("rb") as fichier:
        donnees = tomllib.load(fichier)
    if not isinstance(donnees, dict):
        raise ErreurConfiguration(f"Configuration TOML invalide : {chemin}")
    return donnees


def _fusionner(base: dict[str, Any], surcharge: dict[str, Any]) -> dict[str, Any]:
    resultat = dict(base)
    for cle, valeur in surcharge.items():
        if isinstance(valeur, dict) and isinstance(resultat.get(cle), dict):
            resultat[cle] = _fusionner(resultat[cle], valeur)
        else:
            resultat[cle] = valeur
    return resultat


def _normaliser_configuration(configuration: dict[str, Any], repertoire_depot: Path) -> dict[str, Any]:
    general = dict(configuration.get("general", {}))
    paths = dict(configuration.get("paths", {}))
    obs = dict(configuration.get("obs", {}))
    mqtt = dict(configuration.get("mqtt", {}))
    chat = dict(configuration.get("chat", {}))
    display = dict(configuration.get("display", {}))
    features = dict(configuration.get("features", {}))
    streaming = dict(configuration.get("streaming", {}))
    video_sources = configuration.get("video_sources", [])
    presets = configuration.get("presets", [])

    paths["repository"] = str(Path(paths.get("repository") or repertoire_depot).expanduser())
    paths["python_venv"] = str(Path(paths["python_venv"]).expanduser())
    paths["data_dir"] = str(Path(paths["data_dir"]).expanduser())
    paths["log_dir"] = str(Path(paths["log_dir"]).expanduser())
    paths["capteurs_file"] = str(Path(paths["data_dir"]) / "capteurs.json")
    paths["chat_file"] = str(Path(paths["data_dir"]) / "chat_unifie.log")
    paths["obs_direct_log"] = str(Path(paths["log_dir"]) / "obs-direct.log")

    general["language"] = str(general.get("language", "fr")).strip().lower() or "fr"

    obs["host"] = str(obs.get("host", "127.0.0.1")).strip()
    obs["port"] = int(obs.get("port", 4455))
    obs["wait_seconds"] = int(obs.get("wait_seconds", 30))
    obs["collection"] = str(obs.get("collection", "")).strip()
    obs["scene"] = str(obs.get("scene", "Scene principale")).strip() or "Scene principale"
    obs["profile_preparation"] = str(obs.get("profile_preparation", "Nomade preparation")).strip() or "Nomade preparation"
    obs["profile_direct"] = str(obs.get("profile_direct", "Nomade direct fixe")).strip() or "Nomade direct fixe"
    for cle in ("source_selfie", "source_carte", "source_vitesse", "source_pulsations", "source_meteo", "source_heure"):
        obs[cle] = str(obs.get(cle, "")).strip()

    mqtt["host"] = str(mqtt.get("host", "127.0.0.1")).strip()
    mqtt["port"] = int(mqtt.get("port", 1883))
    mqtt["topic"] = str(mqtt.get("topic", "nomade/capteurs")).strip() or "nomade/capteurs"
    mqtt["client_id"] = str(mqtt.get("client_id", "nomade-capteurs")).strip() or "nomade-capteurs"
    mqtt["keepalive"] = int(mqtt.get("keepalive", 30))
    mqtt["network_interface"] = str(mqtt.get("network_interface", "bnep0")).strip() or "bnep0"
    mqtt["bluetooth_device_name"] = str(mqtt.get("bluetooth_device_name", "")).strip()
    mqtt["bluetooth_device_address"] = str(mqtt.get("bluetooth_device_address", "")).strip()

    chat["service"] = str(chat.get("service", "none")).strip().lower() or "none"
    chat["source_name"] = str(chat.get("source_name", "Chat multicanal")).strip() or "Chat multicanal"
    chat["enabled_by_default"] = bool(chat.get("enabled_by_default", False))
    chat["velora_url"] = str(chat.get("velora_url", "")).strip()
    chat["botrix_url"] = str(chat.get("botrix_url", "")).strip()
    chat["custom_url"] = str(chat.get("custom_url", "")).strip()

    display["window_geometry"] = str(display.get("window_geometry", "1024x600")).strip() or "1024x600"
    display["show_chat_panel"] = bool(display.get("show_chat_panel", True))

    features["autostart_obs"] = bool(features.get("autostart_obs", True))
    features["sync_chat_browser_source"] = bool(features.get("sync_chat_browser_source", True))
    features["autostart_stream_on_launch"] = bool(features.get("autostart_stream_on_launch", False))

    streaming["active_destination"] = str(streaming.get("active_destination", "")).strip()
    streaming["notes"] = str(streaming.get("notes", "")).strip()
    destinations = streaming.get("destinations", [])
    if not isinstance(destinations, list):
        raise ErreurConfiguration("La section [streaming] doit définir des destinations sous forme de liste.")
    streaming["destinations"] = destinations

    if not isinstance(video_sources, list):
        raise ErreurConfiguration("La section [[video_sources]] doit être une liste d'objets TOML.")
    video_sources_normalisees: list[dict[str, Any]] = []
    for source in video_sources:
        if not isinstance(source, dict):
            raise ErreurConfiguration("Chaque entrée [[video_sources]] doit être un objet TOML.")
        source_normalisee = dict(source)
        source_normalisee["id"] = str(source_normalisee.get("id", "")).strip()
        source_normalisee["label"] = str(source_normalisee.get("label", "")).strip()
        source_normalisee["type"] = str(source_normalisee.get("type", "")).strip().lower()
        source_normalisee["obs_source_name"] = str(source_normalisee.get("obs_source_name", "")).strip()
        source_normalisee["group"] = str(source_normalisee.get("group", "")).strip()
        source_normalisee["enabled_by_default"] = source_normalisee.get("enabled_by_default", False)
        source_normalisee["srt_port"] = source_normalisee.get("srt_port", None)
        if source_normalisee["srt_port"] in ("", None):
            source_normalisee["srt_port"] = None
        video_sources_normalisees.append(source_normalisee)

    if not isinstance(presets, list):
        raise ErreurConfiguration("La section [[presets]] doit être une liste d'objets TOML.")
    presets_normalises: list[dict[str, Any]] = []
    for preset in presets:
        if not isinstance(preset, dict):
            raise ErreurConfiguration("Chaque entrée [[presets]] doit être un objet TOML.")
        preset_normalise = dict(preset)
        preset_normalise["id"] = str(preset_normalise.get("id", "")).strip()
        preset_normalise["label"] = str(preset_normalise.get("label", "")).strip()
        activer = preset_normalise.get("activer", [])
        desactiver = preset_normalise.get("desactiver", [])
        if not isinstance(activer, list) or not isinstance(desactiver, list):
            raise ErreurConfiguration("Les champs presets.activer et presets.desactiver doivent être des listes.")
        preset_normalise["activer"] = [str(identifiant).strip() for identifiant in activer]
        preset_normalise["desactiver"] = [str(identifiant).strip() for identifiant in desactiver]
        presets_normalises.append(preset_normalise)

    configuration_normalisee = {
        "general": general,
        "paths": paths,
        "obs": obs,
        "mqtt": mqtt,
        "chat": chat,
        "display": display,
        "features": features,
        "streaming": streaming,
        "video_sources": video_sources_normalisees,
        "presets": presets_normalises,
    }
    _valider_configuration(configuration_normalisee)
    return configuration_normalisee


def _valider_configuration(configuration: dict[str, Any]) -> None:
    erreurs: list[str] = []

    obs = configuration["obs"]
    if not est_hote_obs_local(obs["host"]):
        erreurs.append("obs.host doit rester local (127.0.0.1, localhost ou ::1).")
    if not 1 <= obs["port"] <= 65535:
        erreurs.append("obs.port doit être compris entre 1 et 65535.")
    if obs["wait_seconds"] < 0:
        erreurs.append("obs.wait_seconds doit être positif ou nul.")

    mqtt = configuration["mqtt"]
    if not 1 <= mqtt["port"] <= 65535:
        erreurs.append("mqtt.port doit être compris entre 1 et 65535.")
    if mqtt["keepalive"] <= 0:
        erreurs.append("mqtt.keepalive doit être strictement positif.")

    chat = configuration["chat"]
    if chat["service"] not in SERVICES_CHAT:
        erreurs.append("chat.service doit valoir none, velora, botrix ou custom.")
    if chat["service"] != "none":
        url = url_chat_active(configuration)
        if not url:
            erreurs.append(f"chat.service={chat['service']} requiert une URL locale correspondante dans nomade.local.toml.")
        else:
            _valider_url_chat(url, erreurs)

    for destination in configuration["streaming"]["destinations"]:
        if not isinstance(destination, dict):
            erreurs.append("Chaque destination streaming doit être un objet TOML.")
            continue
        if not str(destination.get("name", "")).strip():
            erreurs.append("Chaque destination streaming doit avoir un nom.")
        if not str(destination.get("obs_profile", "")).strip():
            erreurs.append(f"La destination streaming '{destination.get('name', '?')}' doit référencer un profil OBS.")

    ids_sources_video: set[str] = set()
    sources_par_id: dict[str, dict[str, Any]] = {}
    sources_actives_par_groupe: dict[str, list[str]] = {}
    for source in configuration["video_sources"]:
        identifiant = source["id"]
        if not identifiant:
            erreurs.append("Chaque source vidéo doit définir un id non vide.")
            continue
        if identifiant in ids_sources_video:
            erreurs.append(f"video_sources contient un id dupliqué : '{identifiant}'.")
        ids_sources_video.add(identifiant)
        sources_par_id[identifiant] = source

        if source["type"] not in TYPES_SOURCES_VIDEO:
            types_valides = ", ".join(sorted(TYPES_SOURCES_VIDEO))
            erreurs.append(
                f"video_sources '{identifiant}' a un type invalide '{source['type']}' (types autorisés : {types_valides}).",
            )
        if not source["obs_source_name"]:
            erreurs.append(f"video_sources '{identifiant}' doit définir obs_source_name.")
        if not source["group"]:
            erreurs.append(f"video_sources '{identifiant}' doit définir group.")
        if not isinstance(source["enabled_by_default"], bool):
            erreurs.append(f"video_sources '{identifiant}' doit définir enabled_by_default avec un booléen.")
        if source["type"] == "srt":
            if source["srt_port"] is not None:
                try:
                    port = int(source["srt_port"])
                except (TypeError, ValueError):
                    erreurs.append(f"video_sources '{identifiant}' a un srt_port invalide (entier attendu).")
                else:
                    if not 1 <= port <= 65535:
                        erreurs.append(f"video_sources '{identifiant}' a un srt_port invalide (1-65535).")
                    else:
                        source["srt_port"] = port
        elif source["srt_port"] is not None:
            erreurs.append(f"video_sources '{identifiant}' ne peut définir srt_port que pour type='srt'.")
        if source["enabled_by_default"]:
            sources_actives_par_groupe.setdefault(source["group"], []).append(identifiant)

    for groupe, identifiants in sources_actives_par_groupe.items():
        if len(identifiants) > 1:
            liste = ", ".join(sorted(identifiants))
            erreurs.append(f"Le groupe vidéo '{groupe}' ne peut avoir qu'une seule source enabled_by_default (trouvées : {liste}).")

    identifiants_connus = set(IDENTIFIANTS_OVERLAYS) | ids_sources_video
    ids_presets: set[str] = set()
    for preset in configuration["presets"]:
        identifiant = preset["id"]
        if not identifiant:
            erreurs.append("Chaque preset doit définir un id non vide.")
            continue
        if identifiant in ids_presets:
            erreurs.append(f"presets contient un id dupliqué : '{identifiant}'.")
        ids_presets.add(identifiant)
        if identifiant in identifiants_connus:
            erreurs.append(f"preset '{identifiant}' ne doit pas réutiliser un identifiant de source/overlay existant.")

    for preset in configuration["presets"]:
        identifiant = preset["id"]
        if not identifiant:
            continue
        sources_activees_par_groupe: dict[str, str] = {}
        for cle_liste in ("activer", "desactiver"):
            for cible in preset[cle_liste]:
                if not cible:
                    erreurs.append(f"preset '{identifiant}' contient un identifiant vide dans {cle_liste}.")
                    continue
                if cible in ids_presets and cible not in identifiants_connus:
                    erreurs.append(f"preset '{identifiant}' ne peut pas référencer un autre preset ('{cible}').")
                    continue
                if cible not in identifiants_connus:
                    erreurs.append(
                        f"preset '{identifiant}' référence '{cible}' dans {cle_liste}, mais cet identifiant est inconnu.",
                    )
                    continue
                if cle_liste == "activer" and cible in sources_par_id:
                    groupe = sources_par_id[cible]["group"]
                    deja = sources_activees_par_groupe.get(groupe)
                    if deja and deja != cible:
                        erreurs.append(
                            f"preset '{identifiant}' active plusieurs sources du groupe '{groupe}' ({deja}, {cible}).",
                        )
                    else:
                        sources_activees_par_groupe[groupe] = cible

    if erreurs:
        raise ErreurConfiguration("Configuration Nomade invalide :\n- " + "\n- ".join(erreurs))


def _valider_url_chat(url: str, erreurs: list[str]) -> None:
    analyse = urlparse(url)
    if analyse.scheme not in {"http", "https"} or not analyse.netloc:
        erreurs.append("L'URL du chat doit être une URL HTTP(S) complète.")
    if analyse.username or analyse.password:
        erreurs.append("L'URL du chat ne doit pas embarquer d'identifiant ni de mot de passe.")


def _creer_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diagnostic et lecture de la configuration Nomade.")
    parser.add_argument("--repository", default=str(repertoire_depot_par_defaut()), help="Chemin absolu du dépôt Nomade.")
    parser.add_argument("--config", help="Chemin d'un fichier TOML principal alternatif.")
    parser.add_argument("--local-config", help="Chemin d'une surcharge locale alternative.")
    parser.add_argument("--diagnostic", action="store_true", help="Affiche un résumé de la configuration résolue.")
    parser.add_argument("--get", help="Affiche une clé de configuration, par ex. paths.python_venv")
    return parser


def main() -> int:
    args = _creer_parser().parse_args()
    try:
        configuration = charger_configuration(
            repertoire_depot=Path(args.repository),
            fichier_config=Path(args.config) if args.config else None,
            fichier_local=Path(args.local_config) if args.local_config else None,
        )
    except ErreurConfiguration as exc:
        print(exc)
        return 1

    if args.get:
        valeur = lire_cle(configuration, args.get)
        if isinstance(valeur, (dict, list)):
            print(json.dumps(valeur, ensure_ascii=False))
        elif isinstance(valeur, bool):
            print("true" if valeur else "false")
        else:
            print(valeur)
        return 0

    print(
        afficher_diagnostic(
            configuration,
            fichier_config=Path(args.config) if args.config else None,
            fichier_local=Path(args.local_config) if args.local_config else None,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
