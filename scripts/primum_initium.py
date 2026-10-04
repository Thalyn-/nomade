#!/usr/bin/env python3
"""Assistant de premier démarrage Nomade : diagnostic, puis actions confirmées."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from installer_scenes_obs import (
    formater_compte_rendu,
    formater_erreur_import,
    importer_depuis_depot,
    sauvegarder_collections,
)
from nomade_config import charger_configuration
from nomade_obs import (
    INJOIGNABLE,
    INTERNE,
    MOT_DE_PASSE,
    ConnexionOBS,
    classer_erreur,
    creer_client,
    fermer_client,
)
from nomade_secrets import enregistrer_secret_obs, charger_secret_obs
from nomade_utils import charger_traductions


def repertoire_config_utilisateur() -> Path:
    return Path(
        os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    ).expanduser()


@dataclass(frozen=True)
class Verification:
    cle: str
    etat: str
    message: str


@dataclass(frozen=True)
class Rapport:
    verifications: list[Verification]
    reseau: dict[str, Any]


def _commande(*arguments: str) -> str:
    try:
        return subprocess.run(
            arguments, check=False, capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def reconnecter_wifi(executer: Any = subprocess.run) -> list[tuple[str, int, str]]:
    """Exécute une séquence de reconnexion, injectable pour les tests."""
    etapes = [
        ("systemctl", "restart", "networking"),
        ("rfkill", "unblock", "wifi"),
        ("iw", "dev", "wlan0", "scan"),
        ("wpa_cli", "-i", "wlan0", "reconfigure"),
        ("ifdown", "wlan0"),
        ("ifup", "wlan0"),
    ]
    resultats = []
    for commande in etapes:
        try:
            resultat = executer(commande, check=False, capture_output=True, text=True, timeout=20)
            sortie = (getattr(resultat, "stdout", "") or getattr(resultat, "stderr", "") or "").strip()
            code = resultat.returncode
        except FileNotFoundError:
            code, sortie = 2, "outil_absent"
        except (OSError, subprocess.TimeoutExpired) as erreur:
            code, sortie = 1, str(erreur)
        resultats.append((commande[0], code, sortie))
    return resultats


def construire_adresses_srt(nom_local: str, adresse_ip: str, port: int = 9001) -> tuple[str, str]:
    """Construit les deux adresses Larix sans dépendre de la résolution mDNS du téléphone."""
    hote = nom_local.strip().removesuffix(".local")
    adresse = f"srt://{hote}.local:{port}?mode=caller" if hote else ""
    ip = adresse_ip.strip()
    if ":" in ip and not (ip.startswith("[") and ip.endswith("]")):
        ip = f"[{ip}]"
    adresse_ip_srt = f"srt://{ip}:{port}?mode=caller" if ip else ""
    return adresse, adresse_ip_srt


PORT_SRT_PAR_DEFAUT = 9001


def sources_srt_configurees(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Liste les sources SRT de la configuration avec leur port d'écoute."""
    return [
        {
            "nom": source["obs_source_name"],
            "label": source.get("label", source["obs_source_name"]),
            "port": source.get("srt_port") or PORT_SRT_PAR_DEFAUT,
        }
        for source in config.get("video_sources", [])
        if source.get("type") == "srt"
    ]


def ports_en_ecoute(sortie_ss: str, ports: list[int]) -> list[int]:
    """Retourne ceux des ports demandés qui apparaissent en écoute UDP."""
    return [port for port in ports if re.search(rf"(?<!\d){port}(?!\d)", sortie_ss)]


def port_depuis_adresse_srt(adresse: str) -> int | None:
    correspondance = re.match(r"srt://[^:/?]*:(\d+)", adresse.strip())
    return int(correspondance.group(1)) if correspondance else None


def ecarts_ports_srt(sources: list[dict[str, Any]], adresses_obs: dict[str, str]) -> list[str]:
    """Signale les ports en double et les écarts entre `srt_port` et l'URL OBS."""
    ecarts = []
    vus: dict[int, str] = {}
    for source in sources:
        if source["port"] in vus:
            ecarts.append(f"{source['nom']} / {vus[source['port']]} : {source['port']}")
        vus.setdefault(source["port"], source["nom"])
        reel = port_depuis_adresse_srt(adresses_obs.get(source["nom"], ""))
        if reel is not None and reel != source["port"]:
            ecarts.append(f"{source['nom']} : {source['port']} / {reel}")
    return ecarts


def etape_suivante(
    faits: dict[str, Any],
    confort_valide: bool,
    configuration_a_jour: bool = False,
    profils_configures: bool = False,
) -> str:
    """Retourne la première étape du parcours guidé qui reste à accomplir."""
    if not faits.get("internet") or not faits.get("ip"):
        return "network"
    attendus = ("python3", "python3-venv", "python3-tk", "ffmpeg", "mosquitto", "obs-studio", "avahi-daemon", "avahi-utils", "onboard")
    if not faits.get("venv") or not all(faits.get("paquets", {}).get(nom, False) for nom in attendus):
        return "install"
    if not confort_valide:
        return "tablet"
    if not faits.get("obs_actif"):
        return "obs"
    if faits.get("websocket") != "joignable":
        return "websocket"
    config = faits.get("config", {})
    obs_config = config.get("obs", {})
    sources_attendues = {
        obs_config.get("scene", ""),
        *(obs_config.get(f"source_{nom}", "") for nom in (
            "selfie", "carte", "vitesse", "pulsations", "meteo", "heure"
        )),
        config.get("chat", {}).get("source_name", ""),
        *(source.get("obs_source_name", "") for source in config.get("video_sources", [])),
    } - {""}
    presentes = set(faits.get("scenes", [])) | set(faits.get("sources", []))
    if not sources_attendues <= presentes:
        return "scenes"
    if not configuration_a_jour:
        return "configuration"
    if not profils_configures:
        return "keys"
    return "launch"


def etat_bouton_obs(obs_actif: bool) -> str:
    """Grise le lancement OBS si le processus existe déjà."""
    return "disabled" if obs_actif else "normal"


def marquer_premier_lancement_obs(chemin: Path) -> Path | None:
    """Déclare le premier lancement OBS traité, en sauvegardant toute configuration présente."""
    chemin = Path(chemin)
    contenu = chemin.read_text(encoding="utf-8") if chemin.exists() else ""
    general = re.search(r"(?m)^\[General\][ \t]*$", contenu)
    if general:
        debut = general.end()
        section_suivante = re.search(r"(?m)^\[", contenu[debut:])
        fin = debut + section_suivante.start() if section_suivante else len(contenu)
        bloc = contenu[debut:fin]
        if re.search(r"(?m)^FirstRun\s*=\s*true\s*$", bloc, re.IGNORECASE):
            return None
        if re.search(r"(?m)^FirstRun\s*=", bloc):
            bloc = re.sub(r"(?m)^FirstRun\s*=.*$", "FirstRun=true", bloc, count=1)
        else:
            bloc = bloc.rstrip() + "\nFirstRun=true\n"
        contenu = contenu[:debut] + bloc + contenu[fin:]
    else:
        contenu = contenu.rstrip() + "\n\n[General]\nFirstRun=true\n"
    sauvegarde = None
    if chemin.exists():
        sauvegarde = chemin.with_name(
            f"{chemin.name}.{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.bak"
        )
        shutil.copy2(chemin, sauvegarde)
        os.chmod(sauvegarde, 0o600)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    descripteur, temporaire = tempfile.mkstemp(dir=chemin.parent, prefix=".obs-global.")
    try:
        with os.fdopen(descripteur, "w", encoding="utf-8") as fichier:
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())
        os.chmod(temporaire, 0o600)
        os.replace(temporaire, chemin)
    except Exception:
        Path(temporaire).unlink(missing_ok=True)
        raise
    return sauvegarde


def ecrire_configuration_wifi(
    chemin: Path, ssid: str, mot_de_passe: str, pays: str = "FR"
) -> Path | None:
    """Ajoute un réseau après sauvegarde, sans afficher ni journaliser la clé."""
    longueur_cle = len(mot_de_passe.encode("utf-8"))
    if (
        not ssid.strip()
        or len(ssid.strip().encode("utf-8")) > 32
        or any(ord(caractere) < 32 for caractere in ssid + mot_de_passe)
        or not (8 <= longueur_cle <= 63 or (longueur_cle == 64 and re.fullmatch(r"[0-9a-fA-F]{64}", mot_de_passe)))
        or not re.fullmatch(r"[A-Z]{2}", pays)
    ):
        raise ValueError("invalid_wifi_parameters")
    chemin = Path(chemin)
    contenu = chemin.read_text(encoding="utf-8") if chemin.exists() else (
        f"country={pays}\nctrl_interface=DIR=/run/wpa_supplicant GROUP=netdev\nupdate_config=1\n"
    )
    premiere_network = re.search(r"(?m)^network\s*=", contenu)
    if premiere_network:
        prefixe, reseaux = contenu[:premiere_network.start()], contenu[premiere_network.start():]
    else:
        prefixe, reseaux = contenu, ""
    pays_existant = re.search(r"(?m)^country=.*$", prefixe)
    if pays_existant:
        prefixe = prefixe[:pays_existant.start()] + f"country={pays}" + prefixe[pays_existant.end():]
    else:
        prefixe = prefixe.rstrip() + f"\ncountry={pays}\n"
    contenu = prefixe + reseaux
    sauvegarde = None
    if chemin.exists():
        horodatage = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        sauvegarde = chemin.with_name(f"{chemin.name}.{horodatage}.bak")
        shutil.copy2(chemin, sauvegarde)
        os.chmod(sauvegarde, 0o600)
    psk = mot_de_passe if longueur_cle == 64 else json.dumps(mot_de_passe, ensure_ascii=False)
    bloc = (
        "\nnetwork={\n"
        f"    ssid={json.dumps(ssid.strip(), ensure_ascii=False)}\n"
        f"    psk={psk}\n"
        "    key_mgmt=WPA-PSK\n"
        "    priority=99\n}\n"
    )
    contenu = contenu.rstrip() + "\n" + bloc
    chemin.parent.mkdir(parents=True, exist_ok=True)
    descripteur, temporaire = tempfile.mkstemp(dir=chemin.parent, prefix=".wpa_supplicant.")
    try:
        with os.fdopen(descripteur, "w", encoding="utf-8") as fichier:
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())
        os.chmod(temporaire, 0o600)
        os.replace(temporaire, chemin)
    except Exception:
        Path(temporaire).unlink(missing_ok=True)
        raise
    return sauvegarde


def collecter_faits(repertoire: Path = REPO_DIR, connexion: ConnexionOBS | None = None) -> dict[str, Any]:
    """Collecte les observations système sans modifier l'installation.

    Une `connexion` persistante évite d'ouvrir puis fermer le WebSocket à chaque cycle.
    """
    config = charger_configuration(repertoire_depot=repertoire)
    paquets = {
        nom: "install ok installed" in _commande("dpkg-query", "-W", "-f=${Status}", nom)
        for nom in ("python3", "python3-venv", "python3-tk", "ffmpeg", "mosquitto", "obs-studio", "avahi-daemon", "avahi-utils", "onboard")
    }
    obs_actif = bool(_commande("pgrep", "-x", "obs"))
    websocket = "absent"
    scenes: list[str] = []
    sources: list[str] = []
    navigateur = False
    reception_srt: bool | None = None
    avahi_actif = _commande("systemctl", "is-active", "avahi-daemon") == "active"
    nom_hote = _commande("hostname") or "dietpi"
    avahi_resolu: bool | None = None if avahi_actif else False
    if avahi_actif and shutil.which("avahi-resolve-host-name"):
        avahi_resolu = bool(_commande("avahi-resolve-host-name", f"{nom_hote}.local"))
    websocket_erreur = ""
    adresses_srt_obs: dict[str, str] = {}
    propre = connexion is None
    if connexion is None:
        connexion = ConnexionOBS(config["obs"]["host"], config["obs"]["port"])
    if obs_actif:
        try:
            client = connexion.obtenir()
            websocket = "joignable"
            scenes = [scene["sceneName"] for scene in client.get_scene_list().scenes]
            entrees = client.get_input_list().inputs
            sources = [source["inputName"] for source in entrees]
            types_disponibles = getattr(client.get_version(), "available_input_kinds", []) or []
            navigateur = (
                any("browser_source" in type_source for type_source in types_disponibles)
                or Path("/usr/lib/obs-plugins/obs-browser.so").is_file()
                or any(Path("/usr/lib").glob("*/obs-plugins/obs-browser.so"))
            )
            etats_srt = []
            for source in config["video_sources"]:
                if source["type"] == "srt" and source["obs_source_name"] in sources:
                    try:
                        parametres = client.get_input_settings(input_name=source["obs_source_name"])
                        adresses_srt_obs[source["obs_source_name"]] = str(
                            parametres.input_settings.get("input", "")
                        )
                        etat_media = client.get_media_input_status(
                            input_name=source["obs_source_name"]
                        ).media_state
                        etats_srt.append(etat_media == "OBS_MEDIA_STATE_PLAYING")
                    except Exception:
                        pass
            reception_srt = any(etats_srt) if etats_srt else None
        except Exception as exc:
            connexion.invalider()
            categorie, websocket_erreur = classer_erreur(exc)
            websocket = {MOT_DE_PASSE: "mot_de_passe", INJOIGNABLE: "indisponible"}.get(categorie, "erreur")
            scenes, sources, reception_srt = [], [], None
    else:
        connexion.invalider()
    if propre:
        connexion.fermer()

    ip = _commande("hostname", "-I").split()
    route = _commande("ip", "-j", "route", "show", "default")
    try:
        routes = json.loads(route) if route else []
        passerelle = routes[0].get("gateway", "") if routes else ""
        interface = routes[0].get("dev", "") if routes else ""
    except (ValueError, IndexError, AttributeError):
        passerelle = ""
        interface = ""
    etat_wifi = _commande("iw", "dev", "wlan0", "link")
    ssid = next(
        (ligne.split(":", 1)[1].strip() for ligne in etat_wifi.splitlines()
         if ligne.strip().startswith("SSID:")),
        "",
    )
    internet = bool(_commande("ping", "-c", "1", "-W", "2", "deb.debian.org"))
    voisins = _commande("ip", "neigh")
    video = sorted(str(path) for path in Path("/dev").glob("video*"))
    sources_srt = sources_srt_configurees(config)
    ports_srt = sorted({source["port"] for source in sources_srt})
    ports_ecoute = ports_en_ecoute(_commande("ss", "-lun"), ports_srt)
    audio = _commande("pactl", "list", "short", "sources")
    bluetooth = _commande("bluetoothctl", "show")
    interfaces_bluetooth = sorted(Path("/sys/class/net").glob("bnep*"))
    return {
        "config": config,
        "venv": Path(config["paths"]["python_venv"]).is_dir(),
        "paquets": paquets,
        "obs_actif": obs_actif,
        "websocket": websocket,
        "scenes": scenes,
        "sources": sources,
        "navigateur": navigateur,
        "ip": ip[0] if ip else "",
        "passerelle": passerelle,
        "interface_reseau": interface,
        "ssid": ssid,
        "internet": internet,
        "nom_local": f"{nom_hote}.local",
        "avahi_actif": avahi_actif,
        "avahi_resolu": avahi_resolu,
        "voisins": voisins,
        "video": video,
        "websocket_erreur": websocket_erreur,
        "sources_srt": sources_srt,
        "ports_srt": ports_srt,
        "ports_srt_ecoute": ports_ecoute,
        "ecarts_srt": ecarts_ports_srt(sources_srt, adresses_srt_obs),
        "ecoute_srt": bool(ports_ecoute),
        "reception_srt": reception_srt,
        "audio": audio,
        "bluetooth": bluetooth,
        "bnep": bool(interfaces_bluetooth),
        "interface_bluetooth": interfaces_bluetooth[0].name if interfaces_bluetooth else config["mqtt"]["network_interface"],
        "mqtt_actif": _commande("systemctl", "is-active", "mosquitto") == "active",
    }


def construire_rapport(faits: dict[str, Any], textes: dict[str, str]) -> Rapport:
    """Transforme des observations en lignes d'état traduisibles."""
    verifications: list[Verification] = []

    def ajouter(cle: str, etat: str, message: str, **variables: str) -> None:
        verifications.append(Verification(cle, etat, textes[message].format(**variables)))

    paquets = faits["paquets"]
    for nom in ("python3", "python3-venv", "python3-tk", "ffmpeg", "mosquitto", "obs-studio", "avahi-daemon", "avahi-utils", "onboard"):
        ajouter(f"paquet_{nom}", "ok" if paquets[nom] else "alerte", f"check_{nom}_ok" if paquets[nom] else f"check_{nom}_missing")
    ajouter("venv", "ok" if faits["venv"] else "alerte", "check_venv_ok" if faits["venv"] else "check_venv_missing")
    ajouter("obs_actif", "ok" if faits["obs_actif"] else "alerte", "check_obs_running" if faits["obs_actif"] else "check_obs_stopped")
    websocket = faits["websocket"]
    if websocket == "joignable":
        ajouter("websocket", "ok", "check_websocket_ok")
    else:
        cle = {
            "mot_de_passe": "check_websocket_password",
            "indisponible": "check_websocket_unreachable",
            "erreur": "check_websocket_internal",
        }.get(websocket, "check_websocket_missing")
        ajouter("websocket", "erreur", cle, error=faits.get("websocket_erreur", ""))

    config_obs = faits["config"]["obs"]
    attendues = [
        config_obs["scene"],
        *[config_obs[f"source_{cle}"] for cle in ("selfie", "carte", "vitesse", "pulsations", "meteo", "heure")],
        faits["config"]["chat"]["source_name"],
        *[source["obs_source_name"] for source in faits["config"]["video_sources"]],
    ]
    manquantes = [nom for nom in attendues if nom and nom not in faits["scenes"] and nom not in faits["sources"]]
    ajouter("scenes_sources", "ok" if not manquantes else "alerte", "check_scenes_ok" if not manquantes else "check_scenes_missing")
    ajouter("source_navigateur", "ok" if faits["navigateur"] else "alerte", "check_browser_ok" if faits["navigateur"] else "check_browser_missing")
    mdns_resolu = faits.get("avahi_resolu")
    if mdns_resolu is True:
        ajouter("mdns", "ok", "check_mdns_ok")
    elif mdns_resolu is False:
        ajouter("mdns", "alerte", "check_mdns_failed")
    else:
        ajouter("mdns", "alerte", "check_mdns_unknown")
    ajouter("bluetooth", "ok" if "Powered: yes" in faits["bluetooth"] else "alerte", "check_bluetooth_ok" if "Powered: yes" in faits["bluetooth"] else "check_bluetooth_missing")
    ajouter("bnep_mqtt", "ok" if faits["bnep"] and faits["mqtt_actif"] else "alerte", "check_bnep_ok" if faits["bnep"] and faits["mqtt_actif"] else "check_bnep_missing")
    ajouter(
        "capture_usb", "ok" if faits["video"] else "alerte",
        "check_video_ok" if faits["video"] else "check_video_missing",
        devices=", ".join(faits["video"]),
    )
    ports_srt = ", ".join(str(port) for port in faits.get("ports_srt", [PORT_SRT_PAR_DEFAUT]))
    ajouter(
        "srt", "ok" if faits["ecoute_srt"] else "alerte",
        "check_srt_listening" if faits["ecoute_srt"] else "check_srt_missing",
        ports=", ".join(str(port) for port in faits.get("ports_srt_ecoute", [])) or ports_srt,
        configured=ports_srt,
    )
    ecarts = faits.get("ecarts_srt", [])
    if ecarts:
        ajouter("srt_ports", "alerte", "check_srt_ports_mismatch", details="; ".join(ecarts))
    else:
        ajouter("srt_ports", "ok", "check_srt_ports_ok", ports=ports_srt)
    reception = faits["reception_srt"]
    if reception is True:
        ajouter("srt_reception", "ok", "check_srt_received")
    elif reception is False:
        ajouter("srt_reception", "alerte", "check_srt_no_caller")
    else:
        ajouter("srt_reception", "alerte", "check_srt_caller")
    ajouter(
        "audio", "ok" if faits["audio"] else "alerte",
        "check_audio_ok" if faits["audio"] else "check_audio_missing",
        devices=", ".join(faits["audio"].splitlines()),
    )
    sources_srt = faits.get("sources_srt") or [
        {"nom": "", "label": "", "port": PORT_SRT_PAR_DEFAUT}
    ]
    adresses_par_source = []
    for source in sources_srt:
        adresse_nom, adresse_ip = construire_adresses_srt(faits["nom_local"], faits["ip"], source["port"])
        adresses_par_source.append({
            "label": source["label"], "port": source["port"],
            "nom": adresse_nom or textes["unknown"], "ip": adresse_ip or textes["unknown"],
        })
    srt_nom, srt_ip = construire_adresses_srt(faits["nom_local"], faits["ip"], sources_srt[0]["port"])
    reseau = {
        "srt_adresses": adresses_par_source,
        "ip": faits["ip"] or textes["unknown"],
        "passerelle": faits["passerelle"] or textes["unknown"],
        "nom_local": faits["nom_local"] if faits["avahi_actif"] else textes["mdns_unavailable"].format(host=faits["nom_local"]),
        "telephone": _trouver_voisin(faits["voisins"], faits["passerelle"]) or textes["unknown"],
        "srt": srt_nom if faits["avahi_actif"] else srt_ip or srt_nom,
        "srt_nom": srt_nom or textes["unknown"],
        "srt_ip": srt_ip or textes["unknown"],
        "interface": (
            textes["network_wifi"].format(interface=faits["interface_reseau"])
            if faits.get("interface_reseau", "").startswith("wl")
            else textes["network_ethernet"].format(interface=faits["interface_reseau"])
            if faits.get("interface_reseau")
            else textes["unknown"]
        ),
        "ssid": faits.get("ssid", "") or textes["unknown"],
        "internet": textes["network_internet_ok"] if faits.get("internet", False) else textes["network_internet_lost"],
    }
    return Rapport(verifications, reseau)


def essentiels_valides(faits: dict[str, Any], confort_valide: bool) -> bool:
    """Décide si le premier assistant peut passer à la configuration du direct."""
    paquets = faits.get("paquets", {})
    attendus = ("python3", "python3-venv", "python3-tk", "ffmpeg", "mosquitto", "obs-studio", "avahi-daemon", "avahi-utils", "onboard")
    config = faits.get("config", {})
    obs_config = config.get("obs", {})
    attendues = {
        obs_config.get("scene", ""),
        *(obs_config.get(f"source_{nom}", "") for nom in (
            "selfie", "carte", "vitesse", "pulsations", "meteo", "heure"
        )),
        config.get("chat", {}).get("source_name", ""),
        *(source.get("obs_source_name", "") for source in config.get("video_sources", [])),
    } - {""}
    presentes = set(faits.get("scenes", [])) | set(faits.get("sources", []))
    return bool(
        faits.get("internet")
        and all(paquets.get(nom, False) for nom in attendus)
        and faits.get("venv")
        and faits.get("obs_actif")
        and faits.get("websocket") == "joignable"
        and faits.get("navigateur")
        and faits.get("ip")
        and faits.get("avahi_actif")
        and confort_valide
        and config.get("mqtt", {}).get("network_interface")
        and attendues <= presentes
    )


def reseaux_detectes(sortie: str) -> list[str]:
    """Extrait les noms de réseaux d'une sortie iw sans répéter les entrées."""
    noms = re.findall(r'ESSID:"((?:[^"\\]|\\.)*)"', sortie)
    noms.extend(
        valeur.strip().strip('"')
        for valeur in re.findall(r"(?m)^\s*SSID:\s*(.*)$", sortie)
        if valeur.strip()
    )
    return sorted(set(noms))


def _trouver_voisin(voisins: str, passerelle: str) -> str:
    candidats = []
    for ligne in voisins.splitlines():
        adresse = ligne.split()[0] if ligne.split() else ""
        if adresse and adresse != passerelle and "FAILED" not in ligne:
            candidats.append(adresse)
    return candidats[0] if len(candidats) == 1 else ""


def calculer_modifications(local_path: Path, informations: dict[str, str]) -> dict[str, str]:
    contenu = local_path.read_text(encoding="utf-8") if local_path.exists() else ""
    changements = {}
    for cle, valeur in informations.items():
        section, cle_section = _section_cle(cle)
        existant = _contenu_section(contenu, section)
        trouve = re.search(rf"(?m)^\s*{re.escape(cle_section)}\s*=\s*(.+?)\s*$", existant)
        if not trouve or _valeur_toml(trouve.group(1)) != valeur:
            changements[cle] = valeur
    return changements


def _section_cle(cle: str) -> tuple[str, str]:
    if cle.startswith("mqtt."):
        return "mqtt", cle.partition(".")[2]
    return "network", cle


def _contenu_section(contenu: str, section: str) -> str:
    trouve = re.search(
        rf"(?m)^\[{re.escape(section)}\][ \t]*(?:\r?\n|$)([\s\S]*?)(?=^\[|\Z)",
        contenu,
    )
    return trouve.group(1) if trouve else ""


def decrire_modifications(
    local_path: Path, informations: dict[str, str], textes: dict[str, str]
) -> str:
    contenu = local_path.read_text(encoding="utf-8") if local_path.exists() else ""
    changements = []
    for cle, valeur in calculer_modifications(local_path, informations).items():
        section, cle_section = _section_cle(cle)
        existant = _contenu_section(contenu, section)
        trouve = re.search(rf"(?m)^\s*{re.escape(cle_section)}\s*=\s*(.+?)\s*$", existant)
        avant = _valeur_toml(trouve.group(1)) if trouve else textes["not_configured"]
        changements.append(textes["diff_line"].format(key=cle, before=avant, after=valeur))
    return "\n".join(changements)


def _valeur_toml(valeur: str) -> str:
    try:
        import tomllib

        return tomllib.loads(f"value = {valeur}")["value"]
    except (ValueError, TypeError):
        return ""


def ecrire_configuration_locale(local_path: Path, changements: dict[str, str]) -> Path | None:
    """Sauvegarde l'existant puis met à jour les clés réseau choisies."""
    if local_path.name != "nomade.local.toml" or not changements:
        return None
    contenu = local_path.read_text(encoding="utf-8") if local_path.exists() else ""
    sauvegarde = None
    if local_path.exists():
        horodatage = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        sauvegarde = local_path.with_name(f"{local_path.name}.{horodatage}.bak")
        shutil.copy2(local_path, sauvegarde)
        os.chmod(sauvegarde, 0o600)
    modifications_sections: dict[str, dict[str, str]] = {}
    for cle, valeur in changements.items():
        section, cle_section = _section_cle(cle)
        modifications_sections.setdefault(section, {})[cle_section] = valeur
    for section_nom, valeurs in modifications_sections.items():
        section = re.search(
            rf"(?m)^\[{re.escape(section_nom)}\][ \t]*(?:\r?\n|$)([\s\S]*?)(?=^\[|\Z)",
            contenu,
        )
        lignes = {
            cle: f'{cle} = {json.dumps(valeur, ensure_ascii=False)}'
            for cle, valeur in valeurs.items()
        }
        if section:
            debut, fin = section.span(1)
            corps = section.group(1)
            for cle, ligne in lignes.items():
                motif = re.compile(rf"(?m)^\s*{re.escape(cle)}\s*=.*$")
                corps = motif.sub(ligne, corps, count=1) if motif.search(corps) else corps.rstrip() + "\n" + ligne + "\n"
            contenu = contenu[:debut] + corps + contenu[fin:]
        else:
            contenu = contenu.rstrip() + f"\n\n[{section_nom}]\n" + "\n".join(lignes.values()) + "\n"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    descripteur, temporaire = tempfile.mkstemp(dir=local_path.parent, prefix=".nomade.local.")
    try:
        with os.fdopen(descripteur, "w", encoding="utf-8") as fichier:
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())
        os.chmod(temporaire, 0o600)
        os.replace(temporaire, local_path)
    except Exception:
        Path(temporaire).unlink(missing_ok=True)
        raise
    return sauvegarde


def _lancer_interface(textes: dict[str, str], rapport: Rapport, repertoire: Path) -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    config_obs = charger_configuration(repertoire_depot=repertoire)["obs"]
    connexion_obs = ConnexionOBS(config_obs["host"], config_obs["port"])
    fenetre = tk.Tk()
    fenetre.title(textes["title"])
    fenetre.geometry("1024x600")
    fenetre.minsize(800, 540)
    cadre = ttk.Frame(fenetre, padding=12)
    cadre.pack(fill="both", expand=True)
    ttk.Style(fenetre).configure("TButton", padding=(12, 9), font=("TkDefaultFont", 12))
    ttk.Label(cadre, text=textes["intro"], wraplength=850).pack(anchor="w", pady=6)
    parcours = ttk.Frame(cadre)
    parcours.pack(fill="x", pady=4)
    progression_var = tk.StringVar()
    ttk.Label(parcours, textvariable=progression_var, font=("TkDefaultFont", 13, "bold")).pack(anchor="w")
    bouton_parcours = ttk.Button(
        parcours, text=textes["guided_next"].format(step=textes["step_network"]),
        command=lambda: avancer_parcours(),
    )
    bouton_parcours.pack(fill="x", pady=5, ipady=8)
    bouton_mode = ttk.Button(
        parcours, text=textes["mode_advanced"], command=lambda: basculer_mode()
    )
    bouton_mode.pack(anchor="e")
    ttk.Button(
        parcours, text=textes["button_refresh"],
        command=lambda: actualiser(force=True),
    ).pack(anchor="e")
    et_apres_obs = ttk.Label(parcours, text="", wraplength=940, justify="left")
    reseau_var = tk.StringVar()
    reseau_label = ttk.Label(cadre, textvariable=reseau_var, wraplength=940, font=("TkDefaultFont", 12))
    reseau_label.pack(anchor="w", pady=6)
    adresses_srt = ttk.Frame(cadre)
    adresses_srt.pack(fill="x", pady=2)
    adresses_srt.columnconfigure(0, weight=1)
    adresses_srt.columnconfigure(2, weight=1)
    adresses_affichees: list[Any] = []

    def afficher_adresses_srt(liste: list[dict[str, Any]]) -> None:
        """Affiche une adresse SRT par source (nom `.local` et adresse IP), avec « Copier »."""
        if liste == adresses_affichees:
            return
        adresses_affichees[:] = liste
        for enfant in adresses_srt.winfo_children():
            enfant.destroy()
        for rang, adresse in enumerate(liste):
            ttk.Label(adresses_srt, text=textes["srt_source_name_label"].format(
                label=adresse["label"], port=adresse["port"]
            )).grid(row=2 * rang, column=0, sticky="w")
            ttk.Label(adresses_srt, text=textes["srt_source_ip_label"].format(
                label=adresse["label"], port=adresse["port"]
            )).grid(row=2 * rang, column=2, sticky="w")
            for colonne, cle in ((0, "nom"), (2, "ip")):
                variable = tk.StringVar(value=adresse[cle])
                ttk.Entry(
                    adresses_srt, textvariable=variable, state="readonly", font=("TkDefaultFont", 11)
                ).grid(row=2 * rang + 1, column=colonne, sticky="ew", padx=(0, 4))
                ttk.Button(
                    adresses_srt, text=textes["srt_copy"],
                    command=lambda v=variable: copier_adresse(v.get()),
                ).grid(row=2 * rang + 1, column=colonne + 1, padx=(0, 12))

    afficher_adresses_srt(rapport.reseau.get("srt_adresses", []))
    aide_srt = ttk.Label(cadre, text=textes["srt_phone_hint"], wraplength=940)
    aide_srt.pack(anchor="w", pady=(0, 4))
    derniere_verification = tk.StringVar()
    etiquette_derniere_verification = ttk.Label(cadre, textvariable=derniere_verification)
    etiquette_derniere_verification.pack(anchor="w")
    banniere = ttk.Label(cadre, text="", wraplength=940, font=("TkDefaultFont", 14, "bold"))
    banniere.pack(anchor="w", pady=4)
    onglets = ttk.Notebook(cadre)
    onglets.pack(fill="both", expand=True)
    lignes_par_onglet: dict[str, Any] = {}
    for cle in ("essential", "recommended", "optional"):
        page = ttk.Frame(onglets)
        onglets.add(page, text=textes[f"section_{cle}"])
        canevas = tk.Canvas(page, highlightthickness=0)
        barre = ttk.Scrollbar(page, orient="vertical", command=canevas.yview)
        canevas.configure(yscrollcommand=barre.set)
        canevas.pack(side="left", fill="both", expand=True)
        barre.pack(side="right", fill="y")
        lignes = ttk.Frame(canevas)
        fenetre_lignes = canevas.create_window((0, 0), window=lignes, anchor="nw")
        lignes.bind(
            "<Configure>",
            lambda _event, c=canevas: c.configure(scrollregion=c.bbox("all")),
        )
        canevas.bind(
            "<Configure>",
            lambda evenement, c=canevas, f=fenetre_lignes: c.itemconfigure(f, width=evenement.width),
        )
        lignes_par_onglet[cle] = lignes
    groupes = {
        "essential": {"venv", "obs_actif", "websocket", "scenes_sources", "source_navigateur"},
        "recommended": {"capture_usb", "srt", "srt_ports", "srt_reception", "audio", "mdns"},
        "optional": {"bluetooth", "bnep_mqtt"},
    }
    etiquette_lignes: dict[str, Any] = {}
    for ligne in rapport.verifications:
        onglet = next((nom for nom, valeurs in groupes.items() if ligne.cle in valeurs), "essential")
        if ligne.cle.startswith("paquet_"):
            onglet = "essential"
        symbole = {"ok": "✔", "alerte": "⚠", "erreur": "✘"}[ligne.etat]
        etiquette = ttk.Label(
            lignes_par_onglet[onglet],
            text=f"{symbole}  {textes.get('label_' + ligne.cle, ligne.cle)} : {ligne.message}",
            wraplength=900,
        )
        etiquette.pack(anchor="w", pady=3, padx=8)
        etiquette_lignes[ligne.cle] = etiquette
    etiquette_tactile = ttk.Label(
        lignes_par_onglet["essential"],
        text="",
        wraplength=900,
    )
    etiquette_tactile.pack(anchor="w", pady=3, padx=8)

    faits_courants: dict[str, Any] = {}
    rapport_courant = rapport
    etat_scan: dict[str, Any] = {"en_cours": False, "faits": None, "manuelle": False}
    statut_actions = tk.StringVar()
    obs_demarrage = False
    reconnexion_en_cours = False
    ttk.Label(cadre, textvariable=statut_actions, wraplength=940).pack(anchor="w", pady=4)
    mode_avance = True

    fichier_confort = repertoire_config_utilisateur() / "nomade" / "primum-initium-tablette.ok"
    confort_valide = fichier_confort.is_file()
    reseau_var.set(textes["network_info"].format(**rapport.reseau))
    banniere.configure(
        text=textes["network_connected"] if rapport.reseau["internet"] == textes["network_internet_ok"]
        else textes["network_disconnected"]
    )

    def confirmer(message: str) -> bool:
        return messagebox.askyesno(textes["confirm_title"], message, parent=fenetre)

    def copier_adresse(adresse: str) -> None:
        if not adresse or adresse == textes["unknown"]:
            return
        fenetre.clipboard_clear()
        fenetre.clipboard_append(adresse)
        statut_actions.set(textes["srt_copied"])

    def lancer_administrateur(*commande: str) -> bool:
        if not shutil.which("pkexec"):
            messagebox.showerror(textes["title"], textes["admin_missing"], parent=fenetre)
            return False
        try:
            resultat = subprocess.run(["pkexec", *commande], check=False, capture_output=True, text=True, timeout=180)
            if resultat.returncode:
                messagebox.showerror(
                    textes["title"],
                    textes["action_error"].format(error=resultat.stderr.strip() or resultat.returncode),
                    parent=fenetre,
                )
            return resultat.returncode == 0
        except subprocess.TimeoutExpired:
            messagebox.showerror(textes["title"], textes["action_error"].format(error=textes["timeout"]), parent=fenetre)
            return False
        except OSError as exc:
            messagebox.showerror(textes["title"], textes["action_error"].format(error=exc), parent=fenetre)
            return False

    def demarrer_obs() -> None:
        nonlocal obs_demarrage
        if _commande("pgrep", "-x", "obs"):
            statut_actions.set(textes["obs_already_running"])
            return
        if obs_demarrage:
            statut_actions.set(textes["obs_launching"])
            return
        choix = messagebox.askyesnocancel(
            textes["obs_button"],
            textes["obs_launch_choice"],
            parent=fenetre,
        )
        if choix is None:
            return
        if not confirmer(textes["confirm_obs_first_run"]):
            return
        try:
            sauvegarde_global = marquer_premier_lancement_obs(
                repertoire_config_utilisateur() / "obs-studio" / "global.ini"
            )
        except OSError as exc:
            messagebox.showerror(textes["title"], textes["action_error"].format(error=exc), parent=fenetre)
            return
        chemin = repertoire / "scripts" / (
            "lancer_obs_preparation.sh" if choix else "lancer_obs_direct.sh"
        )
        try:
            obs_demarrage = True
            subprocess.Popen([str(chemin)], cwd=repertoire, start_new_session=True)
            statut_actions.set(textes["obs_launching"].format(
                backup=sauvegarde_global or textes["new_file"]
            ))
        except OSError as exc:
            messagebox.showerror(textes["title"], textes["action_error"].format(error=exc), parent=fenetre)

    def installer() -> None:
        if confirmer(textes["confirm_install"]):
            lancer_administrateur(str(repertoire / "scripts" / "install_nomade.sh"))

    def informations_configuration() -> dict[str, str]:
        faits = faits_courants
        return {
            "raspberry_ip": faits.get("ip", ""),
            "local_hostname": faits.get("nom_local", ""),
            "srt_address": rapport_courant.reseau.get("srt", ""),
            "mqtt.network_interface": faits.get("interface_bluetooth")
            or faits.get("config", {}).get("mqtt", {}).get("network_interface", "bnep0"),
        }

    def sauvegarder_configuration(afficher: bool = True) -> bool:
        chemin = repertoire / "config" / "nomade.local.toml"
        modifs = calculer_modifications(chemin, informations_configuration())
        if not modifs:
            if afficher:
                messagebox.showinfo(textes["title"], textes["no_config_change"], parent=fenetre)
            return True
        try:
            sauvegarde = ecrire_configuration_locale(chemin, modifs)
        except OSError as exc:
            obs_demarrage = False
            messagebox.showerror(textes["title"], textes["action_error"].format(error=exc), parent=fenetre)
            return False
        if afficher:
            messagebox.showinfo(textes["title"], textes["config_saved"].format(backup=sauvegarde or textes["new_file"]), parent=fenetre)
        return True

    def ecrire_local() -> None:
        resume = decrire_modifications(
            repertoire / "config" / "nomade.local.toml",
            informations_configuration(),
            textes,
        )
        if not resume:
            messagebox.showinfo(textes["title"], textes["no_config_change"], parent=fenetre)
            return
        if confirmer(textes["confirm_config"].format(
            changes=resume
        )):
            sauvegarder_configuration()

    def importer_modele() -> None:
        if not confirmer(textes["guided_scene_confirm"]):
            return
        client = None
        try:
            client = creer_client(
                faits_courants["config"]["obs"]["host"], faits_courants["config"]["obs"]["port"]
            )
            scene_dir = repertoire_config_utilisateur() / "obs-studio" / "basic" / "scenes"
            sauvegardes = sauvegarder_collections(scene_dir)
            compte_rendu = importer_depuis_depot(client, repertoire, faits_courants["config"], textes)
            statut_actions.set(textes["guided_scene_done"].format(
                added=len(compte_rendu.creees), skipped=len(compte_rendu.presentes),
                backups=", ".join(map(str, sauvegardes)) or textes["scene_backup_none"]
            ))
            if compte_rendu.ignorees or compte_rendu.avertissements:
                messagebox.showwarning(
                    textes["title"], formater_compte_rendu(compte_rendu, textes), parent=fenetre
                )
            actualiser()
        except Exception as erreur:
            messagebox.showerror(textes["title"], formater_erreur_import(erreur, textes), parent=fenetre)
        finally:
            fermer_client(client)

    def corriger_wifi() -> None:
        services = _commande("systemctl", "list-units", "--all", "--no-legend")
        service = next(
            (ligne.split()[0] for ligne in services.splitlines()
             if "dietpi-wifi-monitor" in ligne and ligne.split()),
            "",
        )
        if not service:
            messagebox.showinfo(textes["title"], textes["wifi_service_absent"], parent=fenetre)
            return
        if confirmer(textes["confirm_wifi"].format(service=service)):
            if lancer_administrateur("systemctl", "disable", "--now", service):
                statut_actions.set(textes["wifi_disabled"].format(service=service))

    def basculer_watchdog() -> None:
        actif = _commande("systemctl", "is-enabled", "nomade-wifi-watchdog.timer") == "enabled"
        action = "uninstall" if actif else "install"
        message = textes["confirm_watchdog_remove" if actif else "confirm_watchdog_install"]
        if confirmer(message):
            script = repertoire / "scripts" / "installer_watchdog_wifi.sh"
            if lancer_administrateur(str(script), action):
                statut_actions.set(textes["watchdog_removed" if actif else "watchdog_installed"])

    def configurer_mot_de_passe_obs() -> None:
        import tkinter.simpledialog as simpledialog

        mot_de_passe = simpledialog.askstring(
            textes["obs_password_title"], textes["obs_password_prompt"], show="•", parent=fenetre
        )
        if mot_de_passe is None:
            return
        if not confirmer(textes["obs_password_confirm"]):
            return
        try:
            sauvegarde = enregistrer_secret_obs(
                repertoire / "config" / "nomade.secrets", mot_de_passe
            )
        except (OSError, ValueError) as erreur:
            cle_erreur = (
                "obs_password_invalid" if str(erreur) == "invalid_obs_password"
                else "obs_password_file_error" if str(erreur) == "invalid_local_secrets"
                else "action_error"
            )
            message = (
                textes[cle_erreur] if cle_erreur != "action_error"
                else textes[cle_erreur].format(error=erreur)
            )
            messagebox.showerror(textes["title"], message, parent=fenetre)
            return
        statut_actions.set(
            textes["obs_password_saved"].format(backup=sauvegarde or textes["new_file"])
        )
        connexion_obs.reinitialiser()
        tester_connexion_obs()
        actualiser()

    def tester_connexion_obs() -> None:
        obs_config = faits_courants.get("config", {}).get("obs", {})
        client = None
        try:
            client = creer_client(obs_config.get("host", "127.0.0.1"), obs_config.get("port", 4455))
            version = client.get_version().obs_version
            statut_actions.set(textes["obs_password_test_ok"].format(version=version))
        except Exception as erreur:
            categorie, detail = classer_erreur(erreur)
            cle = {
                INJOIGNABLE: "check_websocket_unreachable",
                MOT_DE_PASSE: "check_websocket_password",
                INTERNE: "check_websocket_internal",
            }.get(categorie, "check_websocket_internal")
            messagebox.showerror(
                textes["title"], textes[cle].format(error=detail), parent=fenetre
            )
        finally:
            fermer_client(client)

    def reconnecter() -> None:
        nonlocal reconnexion_en_cours
        if reconnexion_en_cours:
            return
        if not confirmer(textes["confirm_reconnect"]):
            return
        if not shutil.which("pkexec"):
            messagebox.showerror(textes["title"], textes["admin_missing"], parent=fenetre)
            return
        reconnexion_en_cours = True

        def travail() -> None:
            nonlocal reconnexion_en_cours
            try:
                resultat = subprocess.run(
                    ["pkexec", sys.executable, str(SCRIPT_DIR / "primum_initium.py"), "--reconnect"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=150,
                )
                sortie = resultat.stdout.strip() or resultat.stderr.strip() or str(resultat.returncode)
                fenetre.after(0, lambda: statut_actions.set(sortie))
                fenetre.after(0, actualiser)
            except (OSError, subprocess.TimeoutExpired) as erreur:
                fenetre.after(0, lambda: statut_actions.set(textes["action_error"].format(error=erreur)))
            finally:
                reconnexion_en_cours = False

        threading.Thread(target=travail, daemon=True).start()

    def afficher_reseaux() -> None:
        statut_actions.set(textes["wifi_scanning"])

        def travail() -> None:
            noms = reseaux_detectes(_commande("iw", "dev", "wlan0", "scan"))

            def afficher() -> None:
                if noms:
                    ssid_var.set(noms[0])
                    choix_ssid.configure(values=noms)
                statut_actions.set(textes["wifi_networks_found"].format(count=len(noms)))

            fenetre.after(0, afficher)

        threading.Thread(target=travail, daemon=True).start()

    def choisir_reseau() -> None:
        import tkinter.simpledialog as simpledialog

        ssid = ssid_var.get().strip()
        if not ssid:
            messagebox.showerror(textes["title"], textes["wifi_ssid_missing"], parent=fenetre)
            return
        mot_de_passe = simpledialog.askstring(
            textes["wifi_password_title"], textes["wifi_password_prompt"], show="•", parent=fenetre
        )
        if mot_de_passe is None:
            return
        if not confirmer(textes["wifi_write_confirm"]):
            return
        donnee = json.dumps({"ssid": ssid, "password": mot_de_passe, "country": pays_var.get().upper()})
        mot_de_passe = ""
        try:
            resultat = subprocess.run(
                ["pkexec", sys.executable, str(SCRIPT_DIR / "primum_initium.py"), "--write-wifi"],
                input=donnee,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as erreur:
            messagebox.showerror(textes["title"], textes["action_error"].format(error=erreur), parent=fenetre)
            return
        if resultat.returncode:
            messagebox.showerror(textes["title"], textes["action_error"].format(error=resultat.stderr.strip()), parent=fenetre)
        else:
            statut_actions.set(resultat.stdout.strip() or textes["wifi_written"])
            reconnecter()

    def confort_tablette() -> None:
        if not confirmer(textes["confirm_tablet"]):
            return
        if not shutil.which("onboard"):
            try:
                resultat = subprocess.run(["pkexec", "apt-get", "install", "-y", "onboard"], check=False)
            except OSError as exc:
                messagebox.showerror(textes["title"], textes["action_error"].format(error=exc), parent=fenetre)
                return
            if resultat.returncode != 0:
                messagebox.showerror(textes["title"], textes["action_error"].format(error=resultat.returncode), parent=fenetre)
                return
        conf = repertoire_config_utilisateur() / "libfm" / "libfm.conf"
        conf.parent.mkdir(parents=True, exist_ok=True)
        avant = conf.read_text(encoding="utf-8") if conf.exists() else ""
        if conf.exists():
            horodatage = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            shutil.copy2(conf, conf.with_name(f"{conf.name}.{horodatage}.bak"))
        section = re.search(r"(?m)^\[config\][ \t]*$", avant)
        if section:
            fin = re.search(r"(?m)^\[", avant[section.end():])
            debut_corps = section.end()
            fin_corps = debut_corps + fin.start() if fin else len(avant)
            corps = avant[debut_corps:fin_corps]
            if re.search(r"(?m)^single_click\s*=", corps):
                corps = re.sub(r"(?m)^single_click\s*=.*$", "single_click=1", corps, count=1)
            else:
                corps = corps.rstrip() + "\nsingle_click=1\n"
            avant = avant[:debut_corps] + corps + avant[fin_corps:]
        else:
            avant = avant.rstrip() + "\n\n[config]\nsingle_click=1\n"
        conf.write_text(avant, encoding="utf-8")
        demarrage = repertoire_config_utilisateur() / "autostart" / "onboard.desktop"
        if not demarrage.exists():
            demarrage.parent.mkdir(parents=True, exist_ok=True)
            demarrage.write_text(
                "[Desktop Entry]\nType=Application\nName=Onboard\nExec=onboard\nX-LXDE-Autostart-enabled=true\n",
                encoding="utf-8",
            )
        messagebox.showinfo(textes["title"], textes["tablet_done"], parent=fenetre)
        valider_confort()

    def valider_confort() -> None:
        nonlocal confort_valide
        if not confirmer(textes["tablet_validate"]):
            return
        fichier_confort.parent.mkdir(parents=True, exist_ok=True)
        fichier_confort.write_text("confirmé\n", encoding="utf-8")
        os.chmod(fichier_confort, 0o600)
        confort_valide = True
        actualiser()

    def suivant() -> None:
        if not essentiels_valides(faits_courants, confort_valide):
            messagebox.showwarning(textes["title"], textes["next_missing"], parent=fenetre)
            return
        valeurs = informations_configuration()
        resume = decrire_modifications(
            repertoire / "config" / "nomade.local.toml", valeurs, textes
        )
        if not confirmer(textes["next_confirm"].format(changes=resume)):
            return
        statut_actions.set(textes["next_saving"])
        if not sauvegarder_configuration(afficher=False):
            return
        try:
            statut_actions.set(textes["next_opening"])
            subprocess.Popen(
                [sys.executable, str(repertoire / "scripts" / "emissio.py")],
                cwd=repertoire,
                start_new_session=True,
            )
        except OSError as exc:
            messagebox.showerror(textes["title"], textes["action_error"].format(error=exc), parent=fenetre)
            return
        fenetre.destroy()

    def avancer_parcours() -> None:
        etape = etape_suivante(
            faits_courants,
            confort_valide,
            configuration_a_jour=not calculer_modifications(
                repertoire / "config" / "nomade.local.toml", informations_configuration()
            ),
            profils_configures=any(
                (repertoire_config_utilisateur() / "obs-studio" / "basic" / "profiles" / f"Nomade - {nom}" / "service.json").is_file()
                for nom in ("Twitch", "Kick", "YouTube", "Facebook Live", "Velora", "Restream.io", "Personnalisé")
            ),
        )
        if etape == "network":
            reconnecter()
        elif etape == "install":
            installer()
        elif etape == "tablet":
            confort_tablette()
        elif etape == "obs":
            demarrer_obs()
        elif etape == "websocket":
            messagebox.showinfo(textes["title"], textes["guided_websocket_help"], parent=fenetre)
            configurer_mot_de_passe_obs()
        elif etape == "scenes":
            importer_modele()
        elif etape == "configuration":
            ecrire_local()
        else:
            try:
                subprocess.Popen(
                    [sys.executable, str(repertoire / "scripts" / "emissio.py")],
                    cwd=repertoire,
                    start_new_session=True,
                )
                statut_actions.set(textes["guided_open_emissio"])
            except OSError as exc:
                messagebox.showerror(textes["title"], textes["action_error"].format(error=exc), parent=fenetre)

    def basculer_mode() -> None:
        nonlocal mode_avance
        mode_avance = not mode_avance
        widgets = (
            reseau_label, adresses_srt, aide_srt, banniere, onglets,
            panneau_reseau, etiquette_tactile, actions, bouton_suivant,
        )
        if mode_avance:
            reseau_label.pack(anchor="w", pady=6)
            adresses_srt.pack(fill="x", pady=2)
            aide_srt.pack(anchor="w", pady=(0, 4))
            banniere.pack(anchor="w", pady=4)
            onglets.pack(fill="both", expand=True)
            panneau_reseau.pack(fill="x", pady=2)
            etiquette_tactile.pack(anchor="w", pady=3, padx=8)
            actions.pack(fill="x", pady=8)
            bouton_suivant.pack(fill="x", pady=4)
            bouton_mode.configure(text=textes["mode_guided"])
        else:
            for widget in widgets:
                widget.pack_forget()
            bouton_mode.configure(text=textes["mode_advanced"])

    def autostart() -> None:
        chemin = repertoire_config_utilisateur() / "autostart" / "nomade-primum-initium.desktop"
        if chemin.exists():
            if confirmer(textes["confirm_autostart_remove"]):
                chemin.unlink()
            return
        if confirmer(textes["confirm_autostart"]):
            chemin.parent.mkdir(parents=True, exist_ok=True)
            executable = sys.executable
            chemin.write_text(
                "[Desktop Entry]\nType=Application\n"
                f"Name={textes['autostart_name']}\n"
                f"Exec={executable} {SCRIPT_DIR / 'primum_initium.py'}\n"
                "X-LXDE-Autostart-enabled=true\n",
                encoding="utf-8",
            )

    ssid_var = tk.StringVar(value=rapport.reseau["ssid"])
    pays_var = tk.StringVar(value="FR")
    panneau_reseau = ttk.Frame(cadre)
    panneau_reseau.pack(fill="x", pady=2)
    choix_ssid = ttk.Combobox(panneau_reseau, textvariable=ssid_var, font=("TkDefaultFont", 12))
    choix_ssid.grid(row=0, column=0, sticky="ew", padx=2)
    ttk.Button(panneau_reseau, text=textes["wifi_scan"], command=afficher_reseaux).grid(row=0, column=1, padx=2)
    ttk.Button(panneau_reseau, text=textes["wifi_connect"], command=choisir_reseau).grid(row=0, column=2, padx=2)
    ttk.Label(panneau_reseau, text=textes["wifi_country"]).grid(row=1, column=0, sticky="w", padx=2)
    ttk.Entry(panneau_reseau, textvariable=pays_var, width=5).grid(row=1, column=1, sticky="w")
    panneau_reseau.columnconfigure(0, weight=1)

    actions = ttk.Frame(cadre)
    actions.pack(fill="x", pady=8)
    commandes = (
        ("button_reconnect", reconnecter),
        ("button_refresh", lambda: actualiser(force=True)),
        ("obs_button", demarrer_obs),
        ("obs_password_button", configurer_mot_de_passe_obs),
        ("button_install", installer),
        ("button_config", ecrire_local),
        ("button_wifi", corriger_wifi),
        ("button_watchdog", basculer_watchdog),
        ("button_tablet", confort_tablette),
        ("tablet_validate_button", valider_confort),
        ("button_autostart", autostart),
    )
    boutons_actions: dict[str, Any] = {}
    for index, (cle, commande) in enumerate(commandes):
        bouton = ttk.Button(actions, text=textes[cle], command=commande)
        bouton.grid(row=index // 4, column=index % 4, sticky="ew", padx=4, pady=4)
        boutons_actions[cle] = bouton
    for colonne in range(4):
        actions.columnconfigure(colonne, weight=1)
    bouton_suivant = ttk.Button(cadre, text=textes["button_next"], command=suivant, state="disabled")
    bouton_suivant.pack(fill="x", pady=4)

    def appliquer_faits(nouveaux: dict[str, Any]) -> None:
        nonlocal obs_demarrage
        nonlocal rapport_courant, faits_courants
        faits_courants = nouveaux
        if nouveaux.get("obs_actif"):
            obs_demarrage = False
        rapport_courant = construire_rapport(nouveaux, textes)
        reseau_var.set(textes["network_info"].format(**rapport_courant.reseau))
        afficher_adresses_srt(rapport_courant.reseau["srt_adresses"])
        derniere_verification.set(
            textes["diagnostic_last_updated"].format(
                time=datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S")
            )
        )
        if nouveaux.get("internet"):
            banniere.configure(text=textes["network_connected"])
        else:
            banniere.configure(text=textes["network_disconnected"])
        if nouveaux.get("obs_actif"):
            et_apres_obs.configure(text=textes["after_obs"])
            if not et_apres_obs.winfo_manager():
                et_apres_obs.pack(anchor="w", pady=4)
        else:
            et_apres_obs.pack_forget()
        for ligne in rapport_courant.verifications:
            etiquette = etiquette_lignes.get(ligne.cle)
            if etiquette:
                symbole = {"ok": "✔", "alerte": "⚠", "erreur": "✘"}[ligne.etat]
                etiquette.configure(text=f"{symbole}  {textes.get('label_' + ligne.cle, ligne.cle)} : {ligne.message}")
        if nouveaux.get("obs_actif"):
            boutons_actions["obs_button"].configure(
                text=textes["obs_already_running_status"], state=etat_bouton_obs(True)
            )
        else:
            boutons_actions["obs_button"].configure(
                text=textes["obs_button"], state=etat_bouton_obs(False)
            )
        configuration_a_jour = not calculer_modifications(
            repertoire / "config" / "nomade.local.toml", informations_configuration()
        )
        profiles_configures = any(
            (repertoire_config_utilisateur() / "obs-studio" / "basic" / "profiles" / f"Nomade - {nom}" / "service.json").is_file()
            for nom in ("Twitch", "Kick", "YouTube", "Facebook Live", "Velora", "Restream.io", "Personnalisé")
        )
        ordre_etapes = (
            "network", "install", "tablet", "obs", "websocket",
            "scenes", "configuration", "keys", "launch",
        )
        etape = etape_suivante(nouveaux, confort_valide, configuration_a_jour, profiles_configures)
        numero = ordre_etapes.index(etape) + 1
        faits_accomplis = " ".join("✔" for _ in range(numero - 1)) or "—"
        progression_var.set(textes["guided_progress"].format(
            number=numero, total=len(ordre_etapes), done=faits_accomplis
        ))
        bouton_parcours.configure(text=textes["guided_next"].format(step=textes[f"step_{etape}"]))
        etiquette_tactile.configure(
            text=f"{'✔' if confort_valide else '⚠'}  {textes['tablet_status_' + ('ready' if confort_valide else 'pending')]}"
        )
        bouton_suivant.configure(
            state="normal" if essentiels_valides(faits_courants, confort_valide) else "disabled"
        )
        if nouveaux.get("ssid"):
            ssid_var.set(nouveaux["ssid"])

    def actualiser(force: bool = False) -> None:
        if etat_scan["en_cours"]:
            return
        etat_scan["en_cours"] = True
        etat_scan["manuelle"] = force
        if force:
            connexion_obs.reinitialiser()
            statut_actions.set(textes["diagnostic_refreshing"])

        def travail() -> None:
            try:
                etat_scan["faits"] = collecter_faits(repertoire, connexion_obs)
            except Exception:
                etat_scan["faits"] = None
            etat_scan["en_cours"] = False

        threading.Thread(target=travail, daemon=True).start()

    def verifier_actualisation() -> None:
        nouveaux = etat_scan.get("faits")
        if nouveaux:
            manuelle = etat_scan["manuelle"]
            etat_scan["faits"] = None
            appliquer_faits(nouveaux)
            if manuelle:
                statut_actions.set(textes["diagnostic_updated"])
        fenetre.after(250, verifier_actualisation)

    actualiser()
    verifier_actualisation()
    basculer_mode()

    def programmer_actualisation() -> None:
        actualiser()
        try:
            intervalle = max(3, min(60, int(os.environ.get("NOMADE_DIAGNOSTIC_INTERVALLE", "4"))))
        except ValueError:
            intervalle = 4
        fenetre.after(intervalle * 1000, programmer_actualisation)

    fenetre.after(4000, programmer_actualisation)
    try:
        fenetre.mainloop()
    finally:
        connexion_obs.fermer()


def main() -> int:
    langue = os.environ.get("NOMADE_LANGUE", "fr")
    textes = charger_traductions(langue, REPO_DIR / "locales")
    parser = argparse.ArgumentParser(add_help=False, description=textes["cli_description"])
    parser.add_argument("--diagnostic", action="store_true", help=textes["cli_help"])
    parser.add_argument("--reconnect", action="store_true", help=textes["cli_reconnect"])
    parser.add_argument("--write-wifi", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--help", action="help", help=textes["help"])
    args = parser.parse_args()
    try:
        charger_secret_obs(REPO_DIR / "config" / "nomade.secrets")
    except (OSError, ValueError, json.JSONDecodeError):
        print(textes["obs_password_file_error"])
        return 1
    if args.write_wifi:
        try:
            donnees = json.load(sys.stdin)
            ecrire_configuration_wifi(
                Path("/etc/wpa_supplicant/wpa_supplicant.conf"),
                donnees["ssid"],
                donnees["password"],
                donnees.get("country", "FR"),
            )
        except json.JSONDecodeError as exc:
            print(textes["wifi_write_error"].format(error=exc), file=sys.stderr)
            return 1
        except ValueError as exc:
            print(textes["wifi_invalid"] if str(exc) == "invalid_wifi_parameters" else textes["wifi_write_error"].format(error=exc), file=sys.stderr)
            return 1
        except (OSError, KeyError) as exc:
            print(textes["wifi_write_error"].format(error=exc), file=sys.stderr)
            return 1
        print(textes["wifi_written"])
        return 0
    if args.reconnect:
        etapes = {
            "systemctl": "wifi_step_networking",
            "rfkill": "wifi_step_unblock",
            "iw": "wifi_step_scan",
            "wpa_cli": "wifi_step_reconfigure",
            "ifdown": "wifi_step_down",
            "ifup": "wifi_step_up",
        }
        for _commande_nom, code, sortie in reconnecter_wifi():
            etat = (
                textes["wifi_step_missing"] if code == 2
                else textes["wifi_step_ok"] if code == 0
                else textes["wifi_step_failed"]
            )
            detail = "" if sortie == "outil_absent" else sortie
            print(textes["wifi_step_result"].format(
                step=textes[etapes[_commande_nom]], status=etat, output=detail
            ))
        return 0
    try:
        faits = collecter_faits()
        rapport = construire_rapport(faits, textes)
    except Exception as exc:
        print(textes["diagnostic_error"].format(error=exc))
        return 1
    if args.diagnostic:
        for ligne in rapport.verifications:
            etat = textes.get(f"status_{ligne.etat}", ligne.etat)
            print(f"{etat:12} {textes.get('label_' + ligne.cle, ligne.cle)} : {ligne.message}")
        print(textes["network_cli"].format(**rapport.reseau))
        return 0
    _lancer_interface(textes, rapport, REPO_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
