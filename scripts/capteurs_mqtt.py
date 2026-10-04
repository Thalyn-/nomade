#!/usr/bin/env python3
"""Ingestion robuste des capteurs Nomade via MQTT."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

from nomade_config import ErreurConfiguration, charger_configuration
from nomade_utils import (
    charger_traductions,
    ecrire_affichages_capteurs,
    ecrire_json_atomique,
    valider_charge_capteurs,
)


def analyser_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Réception des capteurs Nomade via MQTT local, idéalement sur la liaison Bluetooth.",
    )
    parser.add_argument("--config", help="Chemin d'un fichier TOML principal alternatif.")
    parser.add_argument("--local-config", help="Chemin d'une surcharge locale alternative.")
    parser.add_argument("--mqtt-hote")
    parser.add_argument("--mqtt-port", type=int)
    parser.add_argument("--mqtt-sujet")
    parser.add_argument(
        "--mqtt-client-id",
        help="Identifiant MQTT alternatif.",
    )
    parser.add_argument("--mqtt-utilisateur", default=os.environ.get("NOMADE_MQTT_UTILISATEUR"))
    parser.add_argument("--mqtt-mot-de-passe", default=os.environ.get("NOMADE_MQTT_MOT_DE_PASSE"))
    parser.add_argument("--mqtt-keepalive", type=int)
    parser.add_argument("--fichier-sortie")
    parser.add_argument("--initialiser-affichages", action="store_true")
    return parser.parse_args()


def creer_client_mqtt(client_id: str) -> mqtt.Client:
    if hasattr(mqtt, "CallbackAPIVersion"):
        return mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
    return mqtt.Client(client_id=client_id)


class ServiceCapteursMQTT:
    """Abonné MQTT robuste : valide et persiste les capteurs sans casser le direct."""

    def __init__(
        self,
        hote: str,
        port: int,
        sujet: str,
        keepalive: int,
        fichier_sortie: Path,
        client_id: str,
        repertoire_donnees: Path | None = None,
        textes: dict[str, str] | None = None,
        utilisateur: str | None = None,
        mot_de_passe: str | None = None,
    ) -> None:
        self.hote = hote
        self.port = port
        self.sujet = sujet
        self.keepalive = keepalive
        self.fichier_sortie = fichier_sortie
        self.repertoire_donnees = Path(repertoire_donnees or fichier_sortie.parent)
        self.textes = textes or charger_traductions("fr", Path(__file__).resolve().parent.parent / "locales")
        self.client = creer_client_mqtt(client_id)
        if utilisateur:
            self.client.username_pw_set(utilisateur, mot_de_passe)
        self.client.on_connect = self._sur_connexion
        self.client.on_disconnect = self._sur_deconnexion
        self.client.on_message = self._sur_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

    def executer(self) -> int:
        print(
            f"Connexion MQTT vers {self.hote}:{self.port}, sujet '{self.sujet}', sortie '{self.fichier_sortie}'.",
        )
        self.client.connect_async(self.hote, self.port, keepalive=self.keepalive)
        self.client.loop_forever(retry_first_connection=True)
        return 0

    def _sur_connexion(self, client: mqtt.Client, _userdata: Any, _flags: Any, code_retour: int) -> None:
        if code_retour != 0:
            print(f"Connexion MQTT refusée (code {code_retour}). Nouvelle tentative automatique.")
            return

        client.subscribe(self.sujet)
        print(f"Abonnement MQTT actif sur '{self.sujet}'.")

    def _sur_deconnexion(self, _client: mqtt.Client, _userdata: Any, code_retour: int) -> None:
        if code_retour != 0:
            print("Liaison MQTT interrompue. Reconnexion automatique en cours.")

    def _sur_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            donnees = json.loads(message.payload.decode("utf-8"))
            charge = valider_charge_capteurs(donnees)
            ecrire_json_atomique(self.fichier_sortie, charge)
            ecrire_affichages_capteurs(self.repertoire_donnees, charge, self.textes)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            print(f"Message capteurs ignoré : {exc}")
        except OSError:
            print("Les fichiers locaux d’affichage des capteurs n’ont pas pu être actualisés.")


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

    service = ServiceCapteursMQTT(
        hote=args.mqtt_hote or os.environ.get("NOMADE_MQTT_HOTE") or configuration["mqtt"]["host"],
        port=args.mqtt_port or int(os.environ.get("NOMADE_MQTT_PORT", configuration["mqtt"]["port"])),
        sujet=args.mqtt_sujet or os.environ.get("NOMADE_MQTT_SUJET") or configuration["mqtt"]["topic"],
        keepalive=args.mqtt_keepalive or int(os.environ.get("NOMADE_MQTT_KEEPALIVE", configuration["mqtt"]["keepalive"])),
        fichier_sortie=Path(args.fichier_sortie or os.environ.get("NOMADE_FICHIER_CAPTEURS") or configuration["paths"]["capteurs_file"]),
        client_id=args.mqtt_client_id or os.environ.get("NOMADE_MQTT_CLIENT_ID") or configuration["mqtt"]["client_id"],
        repertoire_donnees=Path(configuration["paths"]["data_dir"]),
        textes=charger_traductions(
            os.environ.get("NOMADE_LANGUE", configuration["general"]["language"]),
            Path(__file__).resolve().parent.parent / "locales",
        ),
        utilisateur=args.mqtt_utilisateur,
        mot_de_passe=args.mqtt_mot_de_passe,
    )
    if args.initialiser_affichages:
        ecrire_affichages_capteurs(
            Path(configuration["paths"]["data_dir"]),
            {},
            service.textes,
            seulement_absents=True,
        )
        return 0
    ecrire_affichages_capteurs(
        Path(configuration["paths"]["data_dir"]), {}, service.textes, seulement_absents=True
    )
    return service.executer()


if __name__ == "__main__":
    raise SystemExit(main())
