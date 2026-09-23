#!/usr/bin/env python3
"""Interface locale de pilotage d'un direct mobile (Raspberry Pi).

Ce module fournit une interface graphique simple pour :
- démarrer/arrêter la diffusion dans OBS ;
- activer/désactiver des sources visuelles (selfie, carte, vitesse...) ;
- afficher l'état de capteurs et les derniers messages du chat unifié.
"""

from __future__ import annotations

import argparse
import json
import time
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any

from obsws_python import ReqClient
from nomade_config import ErreurConfiguration, afficher_diagnostic, charger_configuration, url_chat_active
from nomade_utils import LANGUE_PAR_DEFAUT, charger_traductions, est_hote_obs_local


@dataclass
class ConfigurationOBS:
    hote: str
    port: int
    mot_de_passe: str
    scene_principale: str


class ControleOBS:
    """Encapsule les appels OBS pour simplifier l'interface graphique."""

    def __init__(self, cfg: ConfigurationOBS) -> None:
        self.cfg = cfg
        parametres_connexion = {"password": cfg.mot_de_passe}
        self.client = ReqClient(host=cfg.hote, port=cfg.port, timeout=3, **parametres_connexion)

    def demarrer_diffusion(self) -> None:
        self.client.start_stream()

    def stopper_diffusion(self) -> None:
        self.client.stop_stream()

    def configurer_source_navigateur(self, nom_source: str, url: str) -> None:
        self.client.send(
            "SetInputSettings",
            {
                "inputName": nom_source,
                "inputSettings": {"url": url},
                "overlay": True,
            },
        )

    def activer_source(self, nom_scene: str, nom_source: str, actif: bool) -> None:
        scene = self.client.get_scene_item_list(scene_name=nom_scene)
        for element in scene.scene_items:
            if element["sourceName"] == nom_source:
                self.client.set_scene_item_enabled(
                    scene_name=nom_scene,
                    scene_item_id=element["sceneItemId"],
                    scene_item_enabled=actif,
                )
                return
        raise RuntimeError(f"Source introuvable dans la scène '{nom_scene}': {nom_source}")


class ApplicationNomade(tk.Tk):
    """Fenêtre principale de contrôle local."""

    def __init__(
        self,
        controle_obs: ControleOBS,
        fichier_capteurs: Path,
        fichier_chat: Path,
        scene: str,
        sources_overlays: dict[str, str],
        sources_video: list[dict[str, Any]],
        presets: list[dict[str, Any]],
        etat_initial_sources: dict[str, bool],
        textes: dict[str, str],
        geometrie: str,
        afficher_chat: bool,
    ) -> None:
        super().__init__()
        self.textes = textes
        self.title(self._texte("app_title"))
        self.geometry(geometrie)

        self.controle_obs = controle_obs
        self.fichier_capteurs = fichier_capteurs
        self.fichier_chat = fichier_chat
        self.scene = scene
        self.sources_overlays = sources_overlays
        self.sources_video = [dict(source) for source in sources_video]
        self.presets = [dict(preset) for preset in presets]
        self.etat_initial_sources = etat_initial_sources
        self.afficher_chat = afficher_chat
        self.groupes_video: dict[str, list[str]] = {}
        self.sources_video_par_id: dict[str, dict[str, Any]] = {}
        self.variables_groupes_video: dict[str, tk.StringVar] = {}
        self.variables_overlays: dict[str, tk.BooleanVar] = {}

        self.messages_chat: deque[str] = deque(maxlen=5)
        self._chat_position = 0
        self._chat_signature: tuple[int, int] | None = None
        self.zone_chat: tk.Text | None = None

        self._indexer_sources_video()
        self._configurer_style_tactile()
        self._creer_interface()
        self._rafraichir()

    def _indexer_sources_video(self) -> None:
        for source in self.sources_video:
            identifiant = source["id"]
            self.sources_video_par_id[identifiant] = source
            self.groupes_video.setdefault(source["group"], []).append(identifiant)

    def _configurer_style_tactile(self) -> None:
        style = ttk.Style(self)
        style.configure("TButton", padding=(12, 8))
        style.configure("TCheckbutton", padding=(8, 6))
        style.configure("TRadiobutton", padding=(10, 8))
        style.configure("TLabelframe.Label", padding=(4, 2))
        style.configure("TLabel", padding=(2, 2))

    def _creer_interface(self) -> None:
        conteneur = ttk.Frame(self)
        conteneur.pack(fill="both", expand=True)
        canevas = tk.Canvas(conteneur, highlightthickness=0)
        barre_defilement = ttk.Scrollbar(conteneur, orient="vertical", command=canevas.yview)
        canevas.configure(yscrollcommand=barre_defilement.set)
        canevas.pack(side="left", fill="both", expand=True)
        barre_defilement.pack(side="right", fill="y")

        contenu = ttk.Frame(canevas)
        fenetre_contenu = canevas.create_window((0, 0), window=contenu, anchor="nw")

        def _ajuster_zone_defilement(_: Any) -> None:
            canevas.configure(scrollregion=canevas.bbox("all"))

        def _ajuster_largeur_fenetre(_: Any) -> None:
            canevas.itemconfigure(fenetre_contenu, width=canevas.winfo_width())

        contenu.bind("<Configure>", _ajuster_zone_defilement)
        canevas.bind("<Configure>", _ajuster_largeur_fenetre)

        cadre_actions = ttk.LabelFrame(contenu, text=self._texte("frame_actions"))
        cadre_actions.pack(fill="x", padx=8, pady=8)

        ttk.Button(cadre_actions, text=self._texte("button_start"), command=self._demarrer).pack(side="left", padx=8, pady=8)
        ttk.Button(cadre_actions, text=self._texte("button_stop"), command=self._stopper).pack(side="left", padx=8, pady=8)

        if self.presets:
            cadre_presets = ttk.LabelFrame(contenu, text=self._texte("frame_presets"))
            cadre_presets.pack(fill="x", padx=8, pady=8)
            for preset in self.presets:
                identifiant = preset["id"]
                libelle = preset["label"] or self._texte("preset_default_label", id=identifiant)
                ttk.Button(
                    cadre_presets,
                    text=libelle,
                    command=lambda p=identifiant: self._appliquer_preset(p),
                ).pack(side="left", padx=8, pady=8)

        self._creer_groupes_video(contenu)

        cadre_overlays = ttk.LabelFrame(contenu, text=self._texte("frame_overlays"))
        cadre_overlays.pack(fill="x", padx=8, pady=8)

        for cle, nom_source in self.sources_overlays.items():
            var = tk.BooleanVar(value=self.etat_initial_sources.get(cle, True))
            self.variables_overlays[cle] = var
            ttk.Checkbutton(
                cadre_overlays,
                text=nom_source,
                variable=var,
                command=lambda c=cle: self._basculer_overlay(c),
            ).pack(side="left", padx=8, pady=8)

        cadre_etat = ttk.LabelFrame(contenu, text=self._texte("frame_sensors"))
        cadre_etat.pack(fill="x", padx=8, pady=8)
        self.texte_etat = tk.StringVar(value=self._texte("sensor_no_data"))
        ttk.Label(cadre_etat, textvariable=self.texte_etat).pack(anchor="w", padx=6, pady=6)

        if self.afficher_chat:
            cadre_chat = ttk.LabelFrame(contenu, text=self._texte("frame_chat"))
            cadre_chat.pack(fill="both", expand=True, padx=8, pady=8)

            cadre_zone_chat = ttk.Frame(cadre_chat)
            cadre_zone_chat.pack(fill="both", expand=True, padx=6, pady=6)

            self.zone_chat = tk.Text(cadre_zone_chat, height=10)
            barre_defilement = ttk.Scrollbar(cadre_zone_chat, orient="vertical", command=self.zone_chat.yview)
            self.zone_chat.configure(yscrollcommand=barre_defilement.set)
            self.zone_chat.pack(side="left", fill="both", expand=True)
            barre_defilement.pack(side="right", fill="y")
            self.zone_chat.configure(state="disabled")

        self.texte_statut = tk.StringVar(value=self._texte("status_ready"))
        ttk.Label(self, textvariable=self.texte_statut).pack(anchor="w", padx=8, pady=(0, 8))

    def _creer_groupes_video(self, parent: ttk.Frame) -> None:
        groupes_specifiques = [("camera_principale", "frame_video_main"), ("vignette_visage", "frame_video_face")]
        groupes_traites: set[str] = set()
        for identifiant_groupe, cle_titre in groupes_specifiques:
            if identifiant_groupe not in self.groupes_video:
                continue
            self._creer_cadre_groupe_video(parent, identifiant_groupe, self._texte(cle_titre))
            groupes_traites.add(identifiant_groupe)

        for identifiant_groupe in sorted(self.groupes_video):
            if identifiant_groupe in groupes_traites:
                continue
            self._creer_cadre_groupe_video(
                parent,
                identifiant_groupe,
                self._texte("frame_video_group", group=identifiant_groupe),
            )

    def _creer_cadre_groupe_video(self, parent: ttk.Frame, identifiant_groupe: str, titre: str) -> None:
        cadre_groupe = ttk.LabelFrame(parent, text=titre)
        cadre_groupe.pack(fill="x", padx=8, pady=8)

        selection_initiale = ""
        for identifiant in self.groupes_video.get(identifiant_groupe, []):
            if self.sources_video_par_id[identifiant]["enabled_by_default"]:
                selection_initiale = identifiant
                break
        variable = tk.StringVar(value=selection_initiale)
        self.variables_groupes_video[identifiant_groupe] = variable

        for identifiant in self.groupes_video.get(identifiant_groupe, []):
            source = self.sources_video_par_id[identifiant]
            libelle = source["label"] or self._texte("video_source_default_label", id=identifiant)
            ttk.Radiobutton(
                cadre_groupe,
                text=libelle,
                variable=variable,
                value=identifiant,
                command=lambda groupe=identifiant_groupe: self._selectionner_source_groupe(groupe),
            ).pack(side="left", padx=8, pady=8)

    def _texte(self, cle: str, **variables: str) -> str:
        modele = self.textes.get(cle, cle)
        return modele.format(**variables) if variables else modele

    def _demarrer(self) -> None:
        try:
            self.controle_obs.demarrer_diffusion()
            self.texte_statut.set(self._texte("status_started"))
        except Exception as exc:  # pragma: no cover
            self.texte_statut.set(self._texte("status_start_error", error=str(exc)))

    def _stopper(self) -> None:
        try:
            self.controle_obs.stopper_diffusion()
            self.texte_statut.set(self._texte("status_stopped"))
        except Exception as exc:  # pragma: no cover
            self.texte_statut.set(self._texte("status_stop_error", error=str(exc)))

    def _basculer_overlay(self, cle: str) -> None:
        actif = self.variables_overlays[cle].get()
        nom_source = self.sources_overlays[cle]
        try:
            self.controle_obs.activer_source(self.scene, nom_source, actif)
            cle_statut = "status_source_enabled" if actif else "status_source_disabled"
            self.texte_statut.set(self._texte(cle_statut, source=nom_source))
        except Exception as exc:  # pragma: no cover
            self.texte_statut.set(self._texte("status_source_error", source=nom_source, error=str(exc)))

    def _selectionner_source_groupe(self, identifiant_groupe: str) -> None:
        selection = self.variables_groupes_video[identifiant_groupe].get()
        try:
            for identifiant_source in self.groupes_video.get(identifiant_groupe, []):
                source = self.sources_video_par_id[identifiant_source]
                actif = identifiant_source == selection
                self.controle_obs.activer_source(self.scene, source["obs_source_name"], actif)
            if not selection:
                self.texte_statut.set(self._texte("status_group_disabled", group=identifiant_groupe))
                return
            nom_source = self.sources_video_par_id[selection]["label"] or self._texte("video_source_default_label", id=selection)
            self.texte_statut.set(self._texte("status_source_enabled", source=nom_source))
        except Exception as exc:  # pragma: no cover
            source = self.sources_video_par_id.get(selection, {})
            nom_source = source.get("label") or self._texte("video_source_default_label", id=selection or identifiant_groupe)
            self.texte_statut.set(self._texte("status_source_error", source=nom_source, error=str(exc)))

    def _appliquer_etat_identifiant(self, identifiant: str, actif: bool) -> None:
        if identifiant in self.variables_overlays:
            self.variables_overlays[identifiant].set(actif)
            self._basculer_overlay(identifiant)
            return
        if identifiant not in self.sources_video_par_id:
            return
        source = self.sources_video_par_id[identifiant]
        identifiant_groupe = source["group"]
        if actif:
            self.variables_groupes_video[identifiant_groupe].set(identifiant)
            self._selectionner_source_groupe(identifiant_groupe)
            return
        if self.variables_groupes_video[identifiant_groupe].get() == identifiant:
            self.variables_groupes_video[identifiant_groupe].set("")
        self._selectionner_source_groupe(identifiant_groupe)

    def _appliquer_preset(self, identifiant_preset: str) -> None:
        preset = next((element for element in self.presets if element["id"] == identifiant_preset), None)
        if preset is None:
            return
        try:
            groupes_a_recalculer: dict[str, str] = {}
            sources_desactivees_par_groupe: dict[str, set[str]] = {}
            source_activee_par_groupe: dict[str, str] = {}

            for identifiant in preset["desactiver"]:
                if identifiant in self.variables_overlays:
                    self.variables_overlays[identifiant].set(False)
                    self._basculer_overlay(identifiant)
                    continue
                if identifiant not in self.sources_video_par_id:
                    continue
                source = self.sources_video_par_id[identifiant]
                identifiant_groupe = source["group"]
                sources_desactivees_par_groupe.setdefault(identifiant_groupe, set()).add(identifiant)
                groupes_a_recalculer.setdefault(identifiant_groupe, self.variables_groupes_video[identifiant_groupe].get())

            for identifiant in preset["activer"]:
                if identifiant in self.variables_overlays:
                    self.variables_overlays[identifiant].set(True)
                    self._basculer_overlay(identifiant)
                    continue
                if identifiant not in self.sources_video_par_id:
                    continue
                source = self.sources_video_par_id[identifiant]
                identifiant_groupe = source["group"]
                source_activee_par_groupe[identifiant_groupe] = identifiant
                groupes_a_recalculer.setdefault(identifiant_groupe, self.variables_groupes_video[identifiant_groupe].get())

            for identifiant_groupe, selection_initiale in groupes_a_recalculer.items():
                selection_courante = selection_initiale
                if selection_courante in sources_desactivees_par_groupe.get(identifiant_groupe, set()):
                    selection_courante = ""
                if identifiant_groupe in source_activee_par_groupe:
                    selection_courante = source_activee_par_groupe[identifiant_groupe]
                self.variables_groupes_video[identifiant_groupe].set(selection_courante)
                self._selectionner_source_groupe(identifiant_groupe)

            nom_preset = preset["label"] or self._texte("preset_default_label", id=identifiant_preset)
            self.texte_statut.set(self._texte("status_preset_applied", preset=nom_preset))
        except Exception as exc:  # pragma: no cover
            nom_preset = preset["label"] or self._texte("preset_default_label", id=identifiant_preset)
            self.texte_statut.set(self._texte("status_preset_error", preset=nom_preset, error=str(exc)))

    def _lire_capteurs(self) -> dict[str, Any]:
        if not self.fichier_capteurs.exists():
            return {}
        try:
            return json.loads(self.fichier_capteurs.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _lire_chat(self) -> list[str]:
        if not self.fichier_chat.exists():
            self._chat_position = 0
            self._chat_signature = None
            return []
        try:
            infos = self.fichier_chat.stat()
            signature = (infos.st_ino, infos.st_mtime_ns)

            if (
                self._chat_signature is None
                or self._chat_signature[0] != infos.st_ino
                or infos.st_size < self._chat_position
            ):
                self._chat_position = 0

            with self.fichier_chat.open("r", encoding="utf-8") as fichier:
                fichier.seek(self._chat_position)
                nouvelles_lignes = fichier.read().splitlines()
                self._chat_position = fichier.tell()

            self._chat_signature = signature
            for ligne in nouvelles_lignes:
                self.messages_chat.append(ligne)
            return list(self.messages_chat)
        except Exception:
            return []

    def _format_etat(self, donnees: dict[str, Any]) -> str:
        if not donnees:
            return self._texte("sensor_no_data")

        position = donnees.get("position", {})
        reseau = donnees.get("reseau", {})
        meteo = donnees.get("meteo", {})
        indisponible = self._texte("sensor_not_available")

        return (
            f"{self._texte('sensor_latitude')}: {position.get('latitude', indisponible)} | "
            f"{self._texte('sensor_longitude')}: {position.get('longitude', indisponible)} | "
            f"{self._texte('sensor_speed')}: {donnees.get('vitesse_kmh', indisponible)} km/h | "
            f"{self._texte('sensor_heart_rate')}: {donnees.get('pulsations', indisponible)} bpm | "
            f"{self._texte('sensor_network')}: {reseau.get('type', indisponible)} ({reseau.get('signal_dbm', indisponible)} dBm) | "
            f"{self._texte('sensor_weather')}: {meteo.get('temperature_c', indisponible)}°C {meteo.get('description', '')}"
        )

    def _rafraichir(self) -> None:
        donnees = self._lire_capteurs()
        self.texte_etat.set(self._format_etat(donnees))

        anciens_messages = list(self.messages_chat)
        derniers = self._lire_chat()
        if self.zone_chat is not None and derniers != anciens_messages:
            self.zone_chat.configure(state="normal")
            self.zone_chat.delete("1.0", tk.END)
            self.zone_chat.insert(tk.END, "\n".join(derniers))
            self.zone_chat.see(tk.END)
            self.zone_chat.configure(state="disabled")

        self.after(1000, self._rafraichir)


def analyser_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interface locale Nomade")
    parser.add_argument("--config", help="Chemin d'un fichier TOML principal alternatif.")
    parser.add_argument("--local-config", help="Chemin d'une surcharge locale alternative.")
    parser.add_argument("--diagnostic-config", action="store_true", help="Affiche la configuration résolue puis quitte.")
    parser.add_argument("--obs-hote", help="Surcharge ponctuelle de l'hôte OBS WebSocket.")
    parser.add_argument("--obs-port", type=int, help="Surcharge ponctuelle du port OBS WebSocket.")
    parser.add_argument(
        "--obs-mdp",
        default=os.environ.get("OBS_MDP", ""),
        help="Mot de passe OBS WebSocket (ou variable OBS_MDP)",
    )
    parser.add_argument("--scene", help="Surcharge ponctuelle du nom de la scène principale")
    parser.add_argument("--source-selfie")
    parser.add_argument("--source-carte")
    parser.add_argument("--source-vitesse")
    parser.add_argument("--source-pulsations")
    parser.add_argument("--source-meteo")
    parser.add_argument("--source-heure")
    parser.add_argument("--fichier-capteurs", help="Fichier JSON capteurs alternatif.")
    parser.add_argument("--fichier-chat", help="Fichier log chat alternatif.")
    parser.add_argument(
        "--langue",
        help="Surcharge ponctuelle de langue de l'interface.",
    )
    parser.add_argument("--obs-attente", type=int, help="Durée maximale d'attente OBS en secondes.")
    return parser.parse_args()


def connecter_obs(cfg: ConfigurationOBS, attente_secondes: int) -> ControleOBS:
    deadline = time.monotonic() + max(attente_secondes, 0)

    while True:
        try:
            return ControleOBS(cfg)
        except Exception as exc:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)


def main() -> int:
    args = analyser_arguments()
    try:
        configuration = charger_configuration(
            repertoire_depot=Path(__file__).resolve().parent.parent,
            fichier_config=Path(args.config) if args.config else None,
            fichier_local=Path(args.local_config) if args.local_config else None,
        )
    except ErreurConfiguration as exc:
        print(exc)
        return 1

    if args.diagnostic_config:
        print(
            afficher_diagnostic(
                configuration,
                fichier_config=Path(args.config) if args.config else None,
                fichier_local=Path(args.local_config) if args.local_config else None,
            ),
        )
        return 0

    langue = args.langue or os.environ.get("NOMADE_LANGUE") or configuration["general"]["language"] or LANGUE_PAR_DEFAUT
    textes = charger_traductions(langue, Path(__file__).resolve().parent.parent / "locales")
    obs_hote = args.obs_hote or configuration["obs"]["host"]
    if not est_hote_obs_local(obs_hote):
        print(textes["obs_host_local_only"])
        return 1

    scene = args.scene or configuration["obs"]["scene"]

    cfg = ConfigurationOBS(
        hote=obs_hote,
        port=args.obs_port or configuration["obs"]["port"],
        mot_de_passe=args.obs_mdp,
        scene_principale=scene,
    )

    sources_overlays = {
        "selfie": args.source_selfie or configuration["obs"]["source_selfie"],
        "carte": args.source_carte or configuration["obs"]["source_carte"],
        "vitesse": args.source_vitesse or configuration["obs"]["source_vitesse"],
        "pulsations": args.source_pulsations or configuration["obs"]["source_pulsations"],
        "meteo": args.source_meteo or configuration["obs"]["source_meteo"],
        "heure": args.source_heure or configuration["obs"]["source_heure"],
    }
    etat_initial_sources = {cle: True for cle in sources_overlays}
    url_chat = url_chat_active(configuration)
    if configuration["chat"]["service"] != "none":
        sources_overlays["chat_multicanal"] = configuration["chat"]["source_name"]
        etat_initial_sources["chat_multicanal"] = configuration["chat"]["enabled_by_default"]
    sources_video = configuration.get("video_sources", [])
    presets = configuration.get("presets", [])

    try:
        attente_obs = args.obs_attente or int(os.environ.get("NOMADE_OBS_ATTENTE", configuration["obs"]["wait_seconds"]))
        controle_obs = connecter_obs(cfg, attente_obs)
    except Exception as exc:
        print(textes["obs_connection_error"])
        if os.environ.get("NOMADE_DEBUG", "0") == "1":
            print(f"Détail debug: {exc}")
        return 1

    if url_chat and configuration["features"]["sync_chat_browser_source"]:
        try:
            controle_obs.configurer_source_navigateur(configuration["chat"]["source_name"], url_chat)
        except Exception as exc:  # pragma: no cover
            if os.environ.get("NOMADE_DEBUG", "0") == "1":
                print(f"Source navigateur non synchronisée: {exc}")
    if configuration["chat"]["service"] != "none":
        try:
            controle_obs.activer_source(
                scene,
                configuration["chat"]["source_name"],
                configuration["chat"]["enabled_by_default"],
            )
        except Exception as exc:  # pragma: no cover
            if os.environ.get("NOMADE_DEBUG", "0") == "1":
                print(f"Source chat non initialisée: {exc}")

    app = ApplicationNomade(
        controle_obs=controle_obs,
        fichier_capteurs=Path(args.fichier_capteurs or configuration["paths"]["capteurs_file"]),
        fichier_chat=Path(args.fichier_chat or configuration["paths"]["chat_file"]),
        scene=scene,
        sources_overlays=sources_overlays,
        sources_video=sources_video,
        presets=presets,
        etat_initial_sources=etat_initial_sources,
        textes=textes,
        geometrie=configuration["display"]["window_geometry"],
        afficher_chat=configuration["display"]["show_chat_panel"],
    )
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
