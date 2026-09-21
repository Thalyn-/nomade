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
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any

from obsws_python import ReqClient


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

    def __init__(self, controle_obs: ControleOBS, fichier_capteurs: Path, fichier_chat: Path, scene: str, sources: dict[str, str]) -> None:
        super().__init__()
        self.title("Nomade - Contrôle du direct")
        self.geometry("1024x600")

        self.controle_obs = controle_obs
        self.fichier_capteurs = fichier_capteurs
        self.fichier_chat = fichier_chat
        self.scene = scene
        self.sources = sources

        self.messages_chat: deque[str] = deque(maxlen=5)
        self._chat_position = 0
        self._chat_signature: tuple[int, int] | None = None

        self._creer_interface()
        self._rafraichir()

    def _creer_interface(self) -> None:
        cadre_actions = ttk.LabelFrame(self, text="Actions direct")
        cadre_actions.pack(fill="x", padx=8, pady=8)

        ttk.Button(cadre_actions, text="Démarrer direct", command=self._demarrer).pack(side="left", padx=4, pady=4)
        ttk.Button(cadre_actions, text="Couper direct", command=self._stopper).pack(side="left", padx=4, pady=4)

        cadre_overlays = ttk.LabelFrame(self, text="Éléments visuels")
        cadre_overlays.pack(fill="x", padx=8, pady=8)

        self.variables: dict[str, tk.BooleanVar] = {}
        for cle, nom_source in self.sources.items():
            var = tk.BooleanVar(value=True)
            self.variables[cle] = var
            ttk.Checkbutton(
                cadre_overlays,
                text=nom_source,
                variable=var,
                command=lambda c=cle: self._basculer_source(c),
            ).pack(side="left", padx=6, pady=4)

        cadre_etat = ttk.LabelFrame(self, text="État capteurs")
        cadre_etat.pack(fill="x", padx=8, pady=8)
        self.texte_etat = tk.StringVar(value="Aucune donnée")
        ttk.Label(cadre_etat, textvariable=self.texte_etat).pack(anchor="w", padx=6, pady=6)

        cadre_chat = ttk.LabelFrame(self, text="Derniers messages chat unifié")
        cadre_chat.pack(fill="both", expand=True, padx=8, pady=8)

        cadre_zone_chat = ttk.Frame(cadre_chat)
        cadre_zone_chat.pack(fill="both", expand=True, padx=6, pady=6)

        self.zone_chat = tk.Text(cadre_zone_chat, height=10)
        barre_defilement = ttk.Scrollbar(cadre_zone_chat, orient="vertical", command=self.zone_chat.yview)
        self.zone_chat.configure(yscrollcommand=barre_defilement.set)
        self.zone_chat.pack(side="left", fill="both", expand=True)
        barre_defilement.pack(side="right", fill="y")
        self.zone_chat.configure(state="disabled")

        self.texte_statut = tk.StringVar(value="Prêt")
        ttk.Label(self, textvariable=self.texte_statut).pack(anchor="w", padx=8, pady=(0, 8))

    def _demarrer(self) -> None:
        try:
            self.controle_obs.demarrer_diffusion()
            self.texte_statut.set("Diffusion démarrée")
        except Exception as exc:  # pragma: no cover
            self.texte_statut.set(f"Erreur démarrage: {exc}")

    def _stopper(self) -> None:
        try:
            self.controle_obs.stopper_diffusion()
            self.texte_statut.set("Diffusion arrêtée")
        except Exception as exc:  # pragma: no cover
            self.texte_statut.set(f"Erreur arrêt: {exc}")

    def _basculer_source(self, cle: str) -> None:
        actif = self.variables[cle].get()
        nom_source = self.sources[cle]
        try:
            self.controle_obs.activer_source(self.scene, nom_source, actif)
            action = "activé" if actif else "désactivé"
            self.texte_statut.set(f"{nom_source} {action}")
        except Exception as exc:  # pragma: no cover
            self.texte_statut.set(f"Erreur source {nom_source}: {exc}")

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
                or signature != self._chat_signature
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
        position = donnees.get("position", {})
        reseau = donnees.get("reseau", {})
        meteo = donnees.get("meteo", {})

        return (
            f"Latitude: {position.get('latitude', 'n/d')} | "
            f"Longitude: {position.get('longitude', 'n/d')} | "
            f"Vitesse: {donnees.get('vitesse_kmh', 'n/d')} km/h | "
            f"Pulsations: {donnees.get('pulsations', 'n/d')} bpm | "
            f"Réseau: {reseau.get('type', 'n/d')} ({reseau.get('signal_dbm', 'n/d')} dBm) | "
            f"Météo: {meteo.get('temperature_c', 'n/d')}°C {meteo.get('description', '')}"
        )

    def _rafraichir(self) -> None:
        donnees = self._lire_capteurs()
        self.texte_etat.set(self._format_etat(donnees))

        anciens_messages = list(self.messages_chat)
        derniers = self._lire_chat()
        if derniers != anciens_messages:
            self.zone_chat.configure(state="normal")
            self.zone_chat.delete("1.0", tk.END)
            self.zone_chat.insert(tk.END, "\n".join(derniers))
            self.zone_chat.see(tk.END)
            self.zone_chat.configure(state="disabled")

        self.after(1000, self._rafraichir)


def analyser_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interface locale Nomade")
    parser.add_argument("--obs-hote", default="127.0.0.1", help="Hôte OBS WebSocket")
    parser.add_argument("--obs-port", type=int, default=4455, help="Port OBS WebSocket")
    parser.add_argument(
        "--obs-mdp",
        default=os.environ.get("OBS_MDP", ""),
        help="Mot de passe OBS WebSocket (ou variable OBS_MDP)",
    )
    parser.add_argument("--scene", default="Scene principale", help="Nom de la scène principale")
    parser.add_argument("--source-selfie", default="Selfie")
    parser.add_argument("--source-carte", default="Carte")
    parser.add_argument("--source-vitesse", default="Vitesse")
    parser.add_argument("--source-pulsations", default="Pulsations")
    parser.add_argument("--source-meteo", default="Meteo")
    parser.add_argument("--source-heure", default="Heure")
    parser.add_argument("--fichier-capteurs", default="/var/lib/nomade/capteurs.json")
    parser.add_argument("--fichier-chat", default="/var/lib/nomade/chat_unifie.log")
    return parser.parse_args()


def main() -> int:
    args = analyser_arguments()

    cfg = ConfigurationOBS(
        hote=args.obs_hote,
        port=args.obs_port,
        mot_de_passe=args.obs_mdp,
        scene_principale=args.scene,
    )

    sources = {
        "selfie": args.source_selfie,
        "carte": args.source_carte,
        "vitesse": args.source_vitesse,
        "pulsations": args.source_pulsations,
        "meteo": args.source_meteo,
        "heure": args.source_heure,
    }

    try:
        controle_obs = ControleOBS(cfg)
    except Exception as exc:
        print("Connexion OBS impossible. Vérifiez OBS ouvert et module obs-websocket actif.")
        if os.environ.get("NOMADE_DEBUG", "0") == "1":
            print(f"Détail debug: {exc}")
        return 1

    app = ApplicationNomade(
        controle_obs=controle_obs,
        fichier_capteurs=Path(args.fichier_capteurs),
        fichier_chat=Path(args.fichier_chat),
        scene=args.scene,
        sources=sources,
    )
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
