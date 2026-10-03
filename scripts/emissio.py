#!/usr/bin/env python3
"""Assistant de choix de destination de diffusion OBS."""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from nomade_config import charger_configuration
from nomade_utils import charger_traductions


def charger_plateformes(chemin: Path) -> list[dict[str, str]]:
    with Path(chemin).open("rb") as fichier:
        plateformes = tomllib.load(fichier).get("plateformes", [])
    if not plateformes or any(not {"id", "libelle", "protocole", "aide"} <= p.keys() for p in plateformes):
        raise ValueError("Définitions de plateformes incomplètes.")
    return plateformes


def chemin_service_obs(repertoire: Path, profil: str) -> Path:
    return Path(repertoire) / ".config" / "obs-studio" / "basic" / "profiles" / profil / "service.json"


def valider_destination(serveur: str, protocole: str) -> tuple[str, int] | None:
    adresse = serveur.strip()
    if protocole.upper() == "SRT":
        parse = urlparse(adresse)
        if parse.scheme.lower() != "srt" or not parse.hostname:
            return None
        return parse.hostname, parse.port or 9000
    parse = urlparse(adresse if "://" in adresse else f"rtmp://{adresse}")
    if parse.scheme.lower() not in {"rtmp", "rtmps"} or not parse.hostname:
        return None
    return parse.hostname, parse.port or (443 if parse.scheme.lower() == "rtmps" else 1935)


def tester_serveur(serveur: str, protocole: str, timeout: float = 3) -> bool:
    cible = valider_destination(serveur, protocole)
    if cible is None:
        return False
    try:
        with socket.create_connection(cible, timeout=timeout):
            return True
    except OSError:
        return False


def ecrire_service_obs(chemin: Path, serveur: str, cle: str) -> Path | None:
    if not serveur.strip() or not cle:
        raise ValueError("Le serveur et la clé sont requis.")
    chemin = Path(chemin)
    contenu = json.dumps(
        {"type": "rtmp_custom", "settings": {"server": serveur.strip(), "key": cle}},
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    sauvegarde = None
    if chemin.exists():
        sauvegarde = chemin.with_name("service.json.bak")
        suffixe = 1
        while sauvegarde.exists():
            sauvegarde = chemin.with_name(f"service.json.{suffixe}.bak")
            suffixe += 1
        os.replace(chemin, sauvegarde)
        os.chmod(sauvegarde, 0o600)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    descripteur, temporaire = tempfile.mkstemp(prefix=".service.", dir=chemin.parent)
    try:
        with os.fdopen(descripteur, "w", encoding="utf-8") as fichier:
            fichier.write(contenu)
            fichier.flush()
            os.fsync(fichier.fileno())
        os.chmod(temporaire, 0o600)
        os.replace(temporaire, chemin)
    except Exception:
        Path(temporaire).unlink(missing_ok=True)
        if sauvegarde and sauvegarde.exists():
            os.replace(sauvegarde, chemin)
        raise
    return sauvegarde


def _interface(textes: dict[str, str], plateformes: list[dict[str, str]], profil: Path) -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    fenetre = tk.Tk()
    fenetre.title(textes["emissio_title"])
    fenetre.geometry("800x560")
    fenetre.minsize(600, 480)
    cadre = ttk.Frame(fenetre, padding=18)
    cadre.pack(fill="both", expand=True)
    ttk.Style(fenetre).configure("TButton", padding=(14, 10), font=("TkDefaultFont", 12))

    plateforme = tk.StringVar(value=textes[plateformes[0]["libelle"]])
    choix = ttk.Combobox(cadre, textvariable=plateforme, state="readonly", values=[
        textes[p["libelle"]] for p in plateformes
    ], font=("TkDefaultFont", 14))
    ttk.Label(cadre, text=textes["emissio_platform"]).pack(anchor="w")
    choix.pack(fill="x", pady=(4, 12))
    serveur = tk.StringVar()
    cle = tk.StringVar()
    aide = ttk.Label(cadre, text="", wraplength=740)
    aide.pack(anchor="w", pady=6)
    ttk.Label(cadre, text=textes["emissio_server"]).pack(anchor="w", pady=(8, 2))
    ttk.Entry(cadre, textvariable=serveur, font=("TkDefaultFont", 14)).pack(fill="x")
    ttk.Label(cadre, text=textes["emissio_key"]).pack(anchor="w", pady=(8, 2))
    entree_cle = ttk.Entry(cadre, textvariable=cle, show="•", font=("TkDefaultFont", 14))
    entree_cle.pack(fill="x")
    statut = tk.StringVar()
    ttk.Label(cadre, textvariable=statut, wraplength=740).pack(anchor="w", pady=8)

    def plateforme_selectionnee() -> dict[str, str]:
        valeur = plateforme.get()
        return next(p for p in plateformes if textes[p["libelle"]] == valeur)

    def mettre_a_jour_aide(_: Any = None) -> None:
        definition = plateforme_selectionnee()
        aide.configure(text=textes[definition["aide"]])
        statut.set("")

    choix.bind("<<ComboboxSelected>>", mettre_a_jour_aide)
    mettre_a_jour_aide()

    def basculer_cle() -> None:
        entree_cle.configure(show="" if entree_cle.cget("show") else "•")

    def tester() -> None:
        definition = plateforme_selectionnee()
        if definition["protocole"].endswith("SRT"):
            statut.set(textes["emissio_srt_test"])
            return
        cible = valider_destination(serveur.get(), "RTMP")
        if not cible:
            statut.set(textes["emissio_invalid"])
            return
        fenetre.configure(cursor="watch")
        fenetre.update_idletasks()
        joignable = tester_serveur(serveur.get(), "RTMP")
        fenetre.configure(cursor="")
        statut.set(textes["emissio_reachable"] if joignable else textes["emissio_unreachable"])

    def sauvegarder() -> None:
        try:
            sauvegarde = ecrire_service_obs(profil, serveur.get(), cle.get())
        except (OSError, ValueError) as erreur:
            messagebox.showerror(textes["emissio_title"], textes["emissio_save_error"].format(error=erreur), parent=fenetre)
            return
        statut.set(textes["emissio_saved"].format(backup=sauvegarde or textes["emissio_no_backup"]))
        cle.set("")

    def lancer(mode_direct: bool) -> None:
        lanceur = SCRIPT_DIR / ("lancer_obs_direct.sh" if mode_direct else "lancer_obs_preparation.sh")
        import subprocess

        try:
            subprocess.Popen([str(lanceur)], cwd=REPO_DIR, start_new_session=True)
            if mode_direct:
                subprocess.Popen([str(SCRIPT_DIR / "lancer_nomade.sh")], cwd=REPO_DIR, start_new_session=True)
        except OSError as erreur:
            messagebox.showerror(textes["emissio_title"], textes["emissio_save_error"].format(error=erreur), parent=fenetre)
            return
        fenetre.destroy()

    barre = ttk.Frame(cadre)
    barre.pack(fill="x", pady=5)
    ttk.Button(barre, text=textes["emissio_show"], command=basculer_cle).pack(side="left", padx=3)
    ttk.Button(barre, text=textes["emissio_test"], command=tester).pack(side="left", padx=3)
    ttk.Button(barre, text=textes["emissio_save"], command=sauvegarder).pack(side="left", padx=3)
    ttk.Button(cadre, text=textes["emissio_prepare"], command=lambda: lancer(False)).pack(fill="x", pady=(12, 4))
    ttk.Button(cadre, text=textes["emissio_live"], command=lambda: lancer(True)).pack(fill="x", pady=4)
    fenetre.mainloop()


def main() -> int:
    langue = os.environ.get("NOMADE_LANGUE", "fr")
    textes = charger_traductions(langue, REPO_DIR / "locales")
    try:
        configuration = charger_configuration(repertoire_depot=REPO_DIR)
        plateformes = charger_plateformes(REPO_DIR / "config" / "plateformes.toml")
        chemin = chemin_service_obs(
            Path.home(), configuration["obs"]["profile_direct"]
        )
        _interface(textes, plateformes, chemin)
    except Exception as erreur:
        print(textes["diagnostic_error"].format(error=erreur))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
