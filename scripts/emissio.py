#!/usr/bin/env python3
"""Assistant de choix de destination de diffusion OBS."""

from __future__ import annotations

import json
import os
import shutil
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
from nomade_secrets import charger_secret_obs, enregistrer_secrets
from nomade_utils import charger_traductions


def charger_plateformes(chemin: Path) -> list[dict[str, Any]]:
    with Path(chemin).open("rb") as fichier:
        plateformes = tomllib.load(fichier).get("plateformes", [])
    if not plateformes or any(not {"id", "profil", "libelle", "protocole", "aide"} <= p.keys() for p in plateformes):
        raise ValueError("invalid_platform_definitions")
    return plateformes


def chemin_service_obs(repertoire: Path, profil: str) -> Path:
    if not profil or Path(profil).name != profil or profil in {".", ".."}:
        raise ValueError("invalid_obs_profile")
    home = Path(repertoire).expanduser().resolve()
    xdg = os.environ.get("XDG_CONFIG_HOME") if home == Path.home().resolve() else None
    configuration = Path(xdg or home / ".config").expanduser()
    racine = configuration.resolve() / "obs-studio" / "basic" / "profiles"
    chemin = (racine / profil / "service.json").resolve()
    if not chemin.is_relative_to(racine.resolve()):
        raise ValueError("invalid_obs_profile")
    return chemin


def ecrire_service_plateforme(
    repertoire: Path,
    profil_base: str,
    profil_plateforme: str,
    serveur: str,
    cle: str,
    protocole: str = "RTMP",
) -> Path | None:
    """Crée un profil dédié depuis le profil direct et y enregistre son service."""
    base = chemin_service_obs(repertoire, profil_base).parent
    destination = chemin_service_obs(repertoire, profil_plateforme).parent
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not destination.exists():
        if base.is_dir():
            shutil.copytree(
                base,
                destination,
                ignore=shutil.ignore_patterns("service.json"),
            )
        else:
            destination.mkdir(parents=True, mode=0o700)
    os.chmod(destination, 0o700)
    return ecrire_service_obs(destination / "service.json", serveur, cle, protocole)


def profil_plateforme_existe(repertoire: Path, profil: str) -> bool:
    return chemin_service_obs(repertoire, profil).is_file()


def valider_destination(serveur: str, protocole: str) -> tuple[str, int] | None:
    adresse = serveur.strip()
    try:
        if protocole.upper() == "SRT":
            parse = urlparse(adresse)
            if parse.scheme.lower() != "srt" or not parse.hostname:
                return None
            return parse.hostname, parse.port or 9001
        parse = urlparse(adresse if "://" in adresse else f"rtmp://{adresse}")
        if parse.scheme.lower() not in {"rtmp", "rtmps"} or not parse.hostname:
            return None
        return parse.hostname, parse.port or (443 if parse.scheme.lower() == "rtmps" else 1935)
    except ValueError:
        return None


def tester_serveur(serveur: str, protocole: str, timeout: float = 3) -> bool:
    cible = valider_destination(serveur, protocole)
    if cible is None:
        return False
    try:
        with socket.create_connection(cible, timeout=timeout):
            return True
    except OSError:
        return False


def ecrire_service_obs(chemin: Path, serveur: str, cle: str, protocole: str = "RTMP") -> Path | None:
    if not serveur.strip() or not cle:
        raise ValueError("missing_stream_credentials")
    protocole = protocole.upper()
    if protocole not in {"RTMP", "RTMPS"}:
        raise ValueError("invalid_stream_protocol")
    if valider_destination(serveur, protocole) is None:
        raise ValueError("invalid_stream_destination")
    chemin = Path(chemin)
    contenu = json.dumps(
        {
            "type": "rtmp_custom",
            "settings": {"server": serveur.strip(), "key": cle},
        },
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
        shutil.copy2(chemin, sauvegarde)
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


def ecrire_destination_srt(chemin_secrets: Path, serveur: str, cle: str) -> Path | None:
    if valider_destination(serveur, "SRT") is None or not cle:
        raise ValueError("invalid_stream_destination")
    return enregistrer_secrets(
        chemin_secrets,
        {"STREAM_PROTOCOL": "SRT", "STREAM_SERVER": serveur.strip(), "STREAM_KEY": cle},
    )


def _interface(textes: dict[str, str], plateformes: list[dict[str, Any]], profil: Path) -> None:
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
    protocole = tk.StringVar(value="RTMP")
    enregistrement_effectue = False
    aide = ttk.Label(cadre, text="", wraplength=740)
    aide.pack(anchor="w", pady=6)
    ttk.Label(cadre, text=textes["emissio_server"]).pack(anchor="w", pady=(8, 2))
    entree_serveur = ttk.Combobox(
        cadre, textvariable=serveur, state="normal",
        values=plateformes[0].get("serveurs", []), font=("TkDefaultFont", 14),
    )
    entree_serveur.pack(fill="x")
    ttk.Label(cadre, text=textes["emissio_protocol"]).pack(anchor="w", pady=(8, 2))
    choix_protocole = ttk.Combobox(
        cadre,
        textvariable=protocole,
        state="readonly",
        values=("RTMP", "RTMPS", "SRT"),
        font=("TkDefaultFont", 14),
    )
    choix_protocole.pack(fill="x")
    ttk.Label(cadre, text=textes["emissio_key"]).pack(anchor="w", pady=(8, 2))
    entree_cle = ttk.Entry(cadre, textvariable=cle, show="•", font=("TkDefaultFont", 14))
    entree_cle.pack(fill="x")
    ttk.Label(
        cadre, text=textes["emissio_key_storage_warning"], wraplength=740
    ).pack(anchor="w", pady=3)
    statut = tk.StringVar()
    ttk.Label(cadre, textvariable=statut, wraplength=740).pack(anchor="w", pady=8)

    def plateforme_selectionnee() -> dict[str, Any]:
        valeur = plateforme.get()
        return next(p for p in plateformes if textes[p["libelle"]] == valeur)

    def charger_service_selectionne() -> None:
        nonlocal enregistrement_effectue
        definition = plateforme_selectionnee()
        chemin = chemin_service_obs(Path.home(), definition["profil"])
        if chemin.is_file():
            try:
                donnees = json.loads(chemin.read_text(encoding="utf-8"))
                parametres = donnees.get("settings", {})
                serveur.set(str(parametres.get("server", "")))
                cle.set(str(parametres.get("key", "")))
                enregistrement_effectue = bool(serveur.get() and cle.get())
            except (OSError, ValueError, TypeError):
                serveur.set("")
                cle.set("")
                enregistrement_effectue = False
        else:
            serveur.set("")
            cle.set("")
            enregistrement_effectue = False

    def mettre_a_jour_aide(_: Any = None) -> None:
        definition = plateforme_selectionnee()
        aide.configure(text=textes[definition["aide"]])
        entree_serveur.configure(values=definition.get("serveurs", []))
        protocoles = ("RTMP", "RTMPS", "SRT") if "SRT" in definition["protocole"] else ("RTMP", "RTMPS")
        choix_protocole.configure(values=protocoles)
        if protocole.get() not in protocoles:
            protocole.set("RTMP")
        charger_service_selectionne()
        statut.set("")

    choix.bind("<<ComboboxSelected>>", mettre_a_jour_aide)
    mettre_a_jour_aide()

    def destination_modifiee(*_: Any) -> None:
        nonlocal enregistrement_effectue
        enregistrement_effectue = False
        statut.set("")

    serveur.trace_add("write", destination_modifiee)
    cle.trace_add("write", destination_modifiee)
    protocole.trace_add("write", destination_modifiee)

    def basculer_cle() -> None:
        entree_cle.configure(show="" if entree_cle.cget("show") else "•")

    def tester() -> None:
        if protocole.get() == "SRT":
            statut.set(textes["emissio_srt_test"])
            return
        cible = valider_destination(serveur.get(), protocole.get())
        if not cible:
            statut.set(textes["emissio_invalid"])
            return
        fenetre.configure(cursor="watch")
        fenetre.update_idletasks()
        joignable = tester_serveur(serveur.get(), protocole.get())
        fenetre.configure(cursor="")
        statut.set(textes["emissio_reachable"] if joignable else textes["emissio_unreachable"])

    def sauvegarder() -> None:
        nonlocal enregistrement_effectue
        if not serveur.get().strip() or not cle.get():
            messagebox.showwarning(
                textes["emissio_title"], textes["emissio_credentials_required"], parent=fenetre
            )
            return
        try:
            if protocole.get() == "SRT":
                sauvegarde = ecrire_destination_srt(
                    REPO_DIR / "config" / "nomade.secrets", serveur.get(), cle.get()
                )
                statut.set(
                    textes["emissio_srt_saved"].format(
                        backup=sauvegarde or textes["emissio_no_backup"]
                    )
                )
                enregistrement_effectue = True
                return
            definition = plateforme_selectionnee()
            chemin = chemin_service_obs(Path.home(), definition["profil"])
            if chemin.exists() and not messagebox.askyesno(
                textes["emissio_title"], textes["emissio_replace_profile"], parent=fenetre
            ):
                return
            profil_direct = profil.parent.name
            sauvegarde = ecrire_service_plateforme(
                Path.home(),
                profil_direct,
                definition["profil"],
                serveur.get(),
                cle.get(),
                protocole.get(),
            )
        except ValueError as erreur:
            cle_message = (
                "emissio_credentials_required" if str(erreur) == "missing_stream_credentials"
                else "emissio_invalid"
            )
            messagebox.showerror(textes["emissio_title"], textes[cle_message], parent=fenetre)
            return
        except OSError as erreur:
            messagebox.showerror(textes["emissio_title"], textes["emissio_save_error"].format(error=erreur), parent=fenetre)
            return
        statut.set(textes["emissio_saved"].format(backup=sauvegarde or textes["emissio_no_backup"]))
        enregistrement_effectue = True

    def lancer(mode_direct: bool) -> None:
        import subprocess

        if mode_direct and not enregistrement_effectue:
            if not serveur.get().strip() or not cle.get():
                messagebox.showwarning(
                    textes["emissio_title"], textes["emissio_credentials_required"], parent=fenetre
                )
                return
            if not messagebox.askyesno(
                textes["emissio_title"], textes["emissio_save_confirm"], parent=fenetre
            ):
                return
            sauvegarder()
            if not enregistrement_effectue:
                return
        if mode_direct and protocole.get() == "SRT":
            if not messagebox.askyesno(
                textes["emissio_title"], textes["emissio_srt_direct"], parent=fenetre
            ):
                return
        if mode_direct and subprocess.run(
            ["pgrep", "-x", "obs"], check=False, capture_output=True
        ).returncode == 0:
            messagebox.showwarning(
                textes["emissio_title"], textes["emissio_close_obs"], parent=fenetre
            )
            return
        try:
            if mode_direct:
                environnement = dict(os.environ)
                environnement["NOMADE_OBS_AUTOSTART_DIFFUSION"] = "1"
                environnement["NOMADE_OBS_PROFIL_DIRECT"] = plateforme_selectionnee()["profil"]
                subprocess.Popen(
                    [str(SCRIPT_DIR / "lancer_nomade.sh")],
                    cwd=REPO_DIR,
                    env=environnement,
                    start_new_session=True,
                )
            elif subprocess.run(
                ["pgrep", "-x", "obs"], check=False, capture_output=True
            ).returncode != 0:
                subprocess.Popen(
                    [str(SCRIPT_DIR / "lancer_obs_preparation.sh")],
                    cwd=REPO_DIR,
                    start_new_session=True,
                )
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
        charger_secret_obs(REPO_DIR / "config" / "nomade.secrets")
        configuration = charger_configuration(repertoire_depot=REPO_DIR)
        plateformes = charger_plateformes(REPO_DIR / "config" / "plateformes.toml")
        chemin = chemin_service_obs(
            Path.home(), configuration["obs"]["profile_direct"]
        )
        _interface(textes, plateformes, chemin)
    except Exception as erreur:
        if str(erreur) == "invalid_platform_definitions":
            print(textes["emissio_platform_error"])
            return 1
        if str(erreur) == "invalid_obs_profile":
            print(textes["emissio_profile_error"])
            return 1
        print(textes["diagnostic_error"].format(error=erreur))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
