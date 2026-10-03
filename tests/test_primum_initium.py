from __future__ import annotations

import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from nomade_utils import charger_traductions
from installer_scenes_obs import ajouter_modele
from nomade_config import charger_configuration
from primum_initium import (
    calculer_modifications,
    construire_rapport,
    ecrire_configuration_locale,
)


class PrimumInitiumTests(unittest.TestCase):
    def setUp(self) -> None:
        self.textes = charger_traductions("fr", ROOT / "locales")
        self.faits = {
            "config": {
                "obs": {
                    "scene": "Scene principale",
                    "source_selfie": "Selfie",
                    "source_carte": "Carte",
                    "source_vitesse": "Vitesse",
                    "source_pulsations": "Pulsations",
                    "source_meteo": "Meteo",
                    "source_heure": "Heure",
                },
                "chat": {"source_name": "Chat multicanal"},
                "video_sources": [
                    {"obs_source_name": "G7 Principal"},
                    {"obs_source_name": "G7 Secours"},
                    {"obs_source_name": "Xiaomi Arriere"},
                    {"obs_source_name": "Xiaomi Selfie"},
                ],
            },
            "paquets": {nom: True for nom in (
                "python3", "python3-venv", "python3-tk", "ffmpeg", "mosquitto",
                "obs-studio", "avahi-daemon",
            )},
            "venv": True,
            "obs_actif": True,
            "websocket": "joignable",
            "scenes": ["Scene principale"],
            "sources": [
                "Selfie", "Carte", "Vitesse", "Pulsations", "Meteo", "Heure",
                "Chat multicanal", "G7 Principal", "G7 Secours", "Xiaomi Arriere", "Xiaomi Selfie",
            ],
            "navigateur": True,
            "bluetooth": "Powered: yes",
            "bnep": True,
            "mqtt_actif": True,
            "video": ["/dev/video0"],
            "ecoute_srt": True,
            "reception_srt": None,
            "audio": "1 source",
            "ip": "10.0.0.2",
            "passerelle": "10.0.0.1",
            "nom_local": "dietpi.local",
            "avahi_actif": True,
            "voisins": "10.0.0.5 dev wlan0 lladdr aa:bb:cc:dd:ee:ff REACHABLE",
        }

    def test_construit_un_rapport_structure_et_traduit(self) -> None:
        rapport = construire_rapport(self.faits, self.textes)

        self.assertEqual(rapport.verifications[0].etat, "ok")
        self.assertIn("/dev/video0", next(
            ligne.message for ligne in rapport.verifications if ligne.cle == "capture_usb"
        ))
        self.assertEqual(rapport.reseau["srt"], "srt://dietpi.local:9001?mode=caller")
        self.assertEqual(rapport.reseau["telephone"], "10.0.0.5")

    def test_configuration_locale_est_sauvegardee_et_seules_cles_reseau_modifiees(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "nomade.local.toml"
            chemin.write_text('[chat]\nservice = "none"\n\n[network]\nraspberry_ip = "10.0.0.1"\n', encoding="utf-8")
            informations = {"raspberry_ip": "10.0.0.2", "srt_address": "dietpi.local"}

            changements = calculer_modifications(chemin, informations)
            sauvegarde = ecrire_configuration_locale(chemin, changements)

            self.assertIsNotNone(sauvegarde)
            self.assertTrue(sauvegarde.is_file())
            self.assertIn('raspberry_ip = "10.0.0.1"', sauvegarde.read_text(encoding="utf-8"))
            resultat = tomllib.loads(chemin.read_text(encoding="utf-8"))
            self.assertEqual(resultat["chat"]["service"], "none")
            self.assertEqual(resultat["network"]["raspberry_ip"], "10.0.0.2")
            self.assertEqual(resultat["network"]["srt_address"], "dietpi.local")

    def test_configuration_locale_identique_ne_cree_pas_de_sauvegarde(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "nomade.local.toml"
            chemin.write_text('[network]\nraspberry_ip = "10.0.0.2"\n', encoding="utf-8")

            changements = calculer_modifications(chemin, {"raspberry_ip": "10.0.0.2"})

            self.assertEqual(changements, {})
            self.assertIsNone(ecrire_configuration_locale(chemin, changements))

    def test_modele_obs_contient_les_noms_et_le_port_de_configuration(self) -> None:
        modele = json.loads((ROOT / "examples/nomade-scenes.json").read_text(encoding="utf-8"))
        configuration = charger_configuration(repertoire_depot=ROOT)
        noms = {source["name"] for source in modele["sources"]}

        self.assertIn(configuration["obs"]["scene"], modele["scenes"])
        self.assertIn(configuration["chat"]["source_name"], noms)
        self.assertTrue(all(source["obs_source_name"] in noms for source in configuration["video_sources"]))
        sources_srt = [source for source in modele["sources"] if source["kind"] == "ffmpeg_source"]
        self.assertTrue(sources_srt)
        self.assertTrue(all(source["settings"]["input"] == "srt://:9001?mode=listener" for source in sources_srt))

    def test_import_modele_conserve_les_sources_deja_presentes(self) -> None:
        class ClientFactice:
            def __init__(self) -> None:
                self.scenes = []
                self.sources = [{"inputName": "Selfie"}]
                self.creations = []

            def get_scene_list(self):
                return type("Reponse", (), {"scenes": self.scenes})()

            def get_input_list(self):
                return type("Reponse", (), {"inputs": self.sources})()

            def send(self, requete, donnees):
                self.creations.append((requete, donnees))
                if requete == "CreateScene":
                    self.scenes.append({"sceneName": donnees["sceneName"]})
                else:
                    self.sources.append({"inputName": donnees["inputName"]})

        client = ClientFactice()
        modele = {"scenes": ["Scene principale"], "sources": [
            {"name": "Selfie", "kind": "color_source_v3", "settings": {}, "enabled": False},
            {"name": "Carte", "kind": "color_source_v3", "settings": {}, "enabled": False},
        ]}

        ajoutes, ignores = ajouter_modele(client, modele)

        self.assertEqual((ajoutes, ignores), (1, 1))
        self.assertEqual([appel[0] for appel in client.creations], ["CreateScene", "CreateInput"])
        self.assertEqual(client.sources[0]["inputName"], "Selfie")


if __name__ == "__main__":
    unittest.main()
