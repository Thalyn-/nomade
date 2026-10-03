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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from nomade_config import charger_configuration
from nomade_utils import charger_traductions


@dataclass(frozen=True)
class Verification:
    cle: str
    etat: str
    message: str


@dataclass(frozen=True)
class Rapport:
    verifications: list[Verification]
    reseau: dict[str, str]


def _commande(*arguments: str) -> str:
    try:
        return subprocess.run(
            arguments, check=False, capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def collecter_faits(repertoire: Path = REPO_DIR) -> dict[str, Any]:
    """Collecte les observations système sans modifier l'installation."""
    config = charger_configuration(repertoire_depot=repertoire)
    paquets = {
        nom: "install ok installed" in _commande("dpkg-query", "-W", "-f=${Status}", nom)
        for nom in ("python3", "python3-venv", "python3-tk", "ffmpeg", "mosquitto", "obs-studio", "avahi-daemon")
    }
    obs_actif = bool(_commande("pgrep", "-x", "obs"))
    websocket = "absent"
    scenes: list[str] = []
    sources: list[str] = []
    navigateur = False
    if obs_actif:
        try:
            from obsws_python import ReqClient

            client = ReqClient(
                "127.0.0.1",
                4455,
                os.environ.get("OBS" + "_MDP", ""),
                timeout=3,
            )
            websocket = "joignable"
            scenes = [scene["sceneName"] for scene in client.get_scene_list().scenes]
            sources = [source["inputName"] for source in client.get_input_list().inputs]
            navigateur = any(
                "browser" in source.get("unversionedInputKind", "").lower()
                for source in client.get_input_list().inputs
            )
        except Exception as exc:
            websocket = "mot_de_passe" if "auth" in str(exc).lower() else "indisponible"

    ip = _commande("hostname", "-I").split()
    route = _commande("ip", "-j", "route", "show", "default")
    try:
        passerelle = json.loads(route)[0].get("gateway", "") if route else ""
    except (ValueError, IndexError, AttributeError):
        passerelle = ""
    voisins = _commande("ip", "neigh")
    video = sorted(str(path) for path in Path("/dev").glob("video*"))
    ecoute_srt = "9001" in _commande("ss", "-lun")
    audio = _commande("pactl", "list", "short", "sources")
    bluetooth = _commande("bluetoothctl", "show")
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
        "nom_local": f"{_commande('hostname') or 'dietpi'}.local",
        "voisins": voisins,
        "video": video,
        "ecoute_srt": ecoute_srt,
        "audio": audio,
        "bluetooth": bluetooth,
        "bnep": Path("/sys/class/net/bnep0").exists(),
        "mqtt_actif": "active" in _commande("systemctl", "is-active", "mosquitto"),
    }


def construire_rapport(faits: dict[str, Any], textes: dict[str, str]) -> Rapport:
    """Transforme des observations en lignes d'état traduisibles."""
    verifications: list[Verification] = []

    def ajouter(cle: str, etat: str, message: str, **variables: str) -> None:
        verifications.append(Verification(cle, etat, textes[message].format(**variables)))

    paquets = faits["paquets"]
    for nom in ("python3", "python3-venv", "python3-tk", "ffmpeg", "mosquitto", "obs-studio", "avahi-daemon"):
        ajouter(f"paquet_{nom}", "ok" if paquets[nom] else "alerte", f"check_{nom}_ok" if paquets[nom] else f"check_{nom}_missing")
    ajouter("venv", "ok" if faits["venv"] else "alerte", "check_venv_ok" if faits["venv"] else "check_venv_missing")
    ajouter("obs_actif", "ok" if faits["obs_actif"] else "alerte", "check_obs_running" if faits["obs_actif"] else "check_obs_stopped")
    websocket = faits["websocket"]
    if websocket == "joignable":
        ajouter("websocket", "ok", "check_websocket_ok")
    else:
        cle = "check_websocket_password" if websocket == "mot_de_passe" else "check_websocket_missing"
        ajouter("websocket", "erreur", cle)

    config_obs = faits["config"]["obs"]
    attendues = [config_obs["scene"], *[config_obs[f"source_{cle}"] for cle in ("selfie", "carte", "vitesse", "pulsations", "meteo", "heure")]]
    manquantes = [nom for nom in attendues if nom and nom not in faits["scenes"] and nom not in faits["sources"]]
    ajouter("scenes_sources", "ok" if not manquantes else "alerte", "check_scenes_ok" if not manquantes else "check_scenes_missing")
    ajouter("source_navigateur", "ok" if faits["navigateur"] else "alerte", "check_browser_ok" if faits["navigateur"] else "check_browser_missing")
    ajouter("bluetooth", "ok" if "Powered: yes" in faits["bluetooth"] else "alerte", "check_bluetooth_ok" if "Powered: yes" in faits["bluetooth"] else "check_bluetooth_missing")
    ajouter("bnep_mqtt", "ok" if faits["bnep"] and faits["mqtt_actif"] else "alerte", "check_bnep_ok" if faits["bnep"] and faits["mqtt_actif"] else "check_bnep_missing")
    ajouter(
        "capture_usb", "ok" if faits["video"] else "alerte",
        "check_video_ok" if faits["video"] else "check_video_missing",
        devices=", ".join(faits["video"]),
    )
    ajouter("srt", "ok" if faits["ecoute_srt"] else "alerte", "check_srt_listening" if faits["ecoute_srt"] else "check_srt_missing")
    ajouter("srt_reception", "alerte", "check_srt_caller")
    ajouter(
        "audio", "ok" if faits["audio"] else "alerte",
        "check_audio_ok" if faits["audio"] else "check_audio_missing",
        devices=", ".join(faits["audio"].splitlines()),
    )
    reseau = {
        "ip": faits["ip"] or textes["unknown"],
        "passerelle": faits["passerelle"] or textes["unknown"],
        "nom_local": faits["nom_local"],
        "telephone": _trouver_voisin(faits["voisins"], faits["passerelle"]) or textes["unknown"],
        "srt": f"srt://{faits['nom_local'] if faits['ip'] else 'ADRESSE_DU_RASPBERRY'}:9001?mode=caller",
    }
    return Rapport(verifications, reseau)


def _trouver_voisin(voisins: str, passerelle: str) -> str:
    candidats = []
    for ligne in voisins.splitlines():
        adresse = ligne.split()[0] if ligne.split() else ""
        if adresse and adresse != passerelle and "FAILED" not in ligne:
            candidats.append(adresse)
    return candidats[0] if len(candidats) == 1 else ""


def calculer_modifications(local_path: Path, informations: dict[str, str]) -> dict[str, str]:
    contenu = local_path.read_text(encoding="utf-8") if local_path.exists() else ""
    section = re.search(r"(?m)^\[network\][ \t]*(?:\r?\n|$)([\s\S]*?)(?=^\[|\Z)", contenu)
    existant = section.group(1) if section else ""
    changements = {}
    for cle, valeur in informations.items():
        trouve = re.search(rf"(?m)^\s*{re.escape(cle)}\s*=\s*(.+?)\s*$", existant)
        if not trouve or _valeur_toml(trouve.group(1)) != valeur:
            changements[cle] = valeur
    return changements


def _valeur_toml(valeur: str) -> str:
    try:
        import tomllib

        return tomllib.loads(f"value = {valeur}")["value"]
    except (ValueError, TypeError):
        return ""


def ecrire_configuration_locale(local_path: Path, changements: dict[str, str]) -> Path | None:
    """Sauvegarde l'existant puis met à jour uniquement les clés de [network]."""
    if local_path.name != "nomade.local.toml" or not changements:
        return None
    contenu = local_path.read_text(encoding="utf-8") if local_path.exists() else ""
    sauvegarde = None
    if local_path.exists():
        horodatage = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        sauvegarde = local_path.with_name(f"{local_path.name}.{horodatage}.bak")
        shutil.copy2(local_path, sauvegarde)
    section = re.search(r"(?m)^\[network\][ \t]*(?:\r?\n|$)([\s\S]*?)(?=^\[|\Z)", contenu)
    lignes = [f'{cle} = {json.dumps(valeur, ensure_ascii=False)}' for cle, valeur in changements.items()]
    if section:
        debut, fin = section.span(1)
        corps = section.group(1)
        for cle, ligne in zip(changements, lignes):
            motif = re.compile(rf"(?m)^\s*{re.escape(cle)}\s*=.*$")
            corps = motif.sub(ligne, corps, count=1) if motif.search(corps) else corps.rstrip() + "\n" + ligne + "\n"
        contenu = contenu[:debut] + corps + contenu[fin:]
    else:
        contenu = contenu.rstrip() + "\n\n[network]\n" + "\n".join(lignes) + "\n"
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

    fenetre = tk.Tk()
    fenetre.title(textes["title"])
    fenetre.geometry("900x700")
    cadre = ttk.Frame(fenetre, padding=12)
    cadre.pack(fill="both", expand=True)
    ttk.Label(cadre, text=textes["intro"], wraplength=850).pack(anchor="w", pady=6)
    liste = ttk.Frame(cadre)
    liste.pack(fill="both", expand=True)
    for ligne in rapport.verifications:
        symbole = {"ok": "✔", "alerte": "⚠", "erreur": "✘"}[ligne.etat]
        ttk.Label(liste, text=f"{symbole}  {textes.get('label_' + ligne.cle, ligne.cle)} : {ligne.message}", wraplength=850).pack(anchor="w", pady=3)
    ttk.Label(cadre, text=textes["network_info"].format(**rapport.reseau), wraplength=850).pack(anchor="w", pady=8)

    def confirmer(message: str) -> bool:
        return messagebox.askyesno(textes["confirm_title"], message, parent=fenetre)

    def installer() -> None:
        if confirmer(textes["confirm_install"]):
            subprocess.Popen(["pkexec", str(repertoire / "scripts" / "install_nomade.sh")])

    def ecrire_local() -> None:
        chemin = repertoire / "config" / "nomade.local.toml"
        modifs = calculer_modifications(chemin, rapport.reseau)
        if not modifs:
            messagebox.showinfo(textes["title"], textes["no_config_change"], parent=fenetre)
            return
        resume = "\n".join(f"{cle} : {valeur}" for cle, valeur in modifs.items())
        if confirmer(textes["confirm_config"].format(changes=resume)):
            sauvegarde = ecrire_configuration_locale(chemin, modifs)
            messagebox.showinfo(textes["title"], textes["config_saved"].format(backup=sauvegarde or textes["new_file"]), parent=fenetre)

    def corriger_wifi() -> None:
        if confirmer(textes["confirm_wifi"]):
            subprocess.Popen(["pkexec", "systemctl", "disable", "--now", "dietpi-wifi-monitor.service"])

    def confort_tablette() -> None:
        if not confirmer(textes["confirm_tablet"]):
            return
        subprocess.run(["pkexec", "apt-get", "install", "-y", "onboard"], check=False)
        conf = Path.home() / ".config" / "libfm" / "libfm.conf"
        conf.parent.mkdir(parents=True, exist_ok=True)
        avant = conf.read_text(encoding="utf-8") if conf.exists() else ""
        if conf.exists():
            shutil.copy2(conf, conf.with_suffix(".conf.bak"))
        if not re.search(r"(?m)^single_click\s*=", avant):
            avant += "\n[config]\nsingle_click=1\n"
        conf.write_text(avant, encoding="utf-8")
        messagebox.showinfo(textes["title"], textes["tablet_done"], parent=fenetre)

    def autostart() -> None:
        chemin = Path.home() / ".config" / "autostart" / "nomade-primum-initium.desktop"
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

    actions = ttk.Frame(cadre)
    actions.pack(fill="x", pady=8)
    for cle, commande in (
        ("button_install", installer),
        ("button_config", ecrire_local),
        ("button_wifi", corriger_wifi),
        ("button_tablet", confort_tablette),
        ("button_autostart", autostart),
    ):
        ttk.Button(actions, text=textes[cle], command=commande).pack(side="left", padx=4, pady=4)
    fenetre.mainloop()


def main() -> int:
    langue = os.environ.get("NOMADE_LANGUE", "fr")
    textes = charger_traductions(langue, REPO_DIR / "locales")
    parser = argparse.ArgumentParser(add_help=False, description=textes["cli_description"])
    parser.add_argument("--diagnostic", action="store_true", help=textes["cli_help"])
    parser.add_argument("--help", action="help", help=textes["help"])
    args = parser.parse_args()
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
