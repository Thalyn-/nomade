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

    configuration_normalisee = {
        "general": general,
        "paths": paths,
        "obs": obs,
        "mqtt": mqtt,
        "chat": chat,
        "display": display,
        "features": features,
        "streaming": streaming,
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
