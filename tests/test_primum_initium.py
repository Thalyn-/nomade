from __future__ import annotations

import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from nomade_utils import charger_traductions
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
                }
            },
            "paquets": {nom: True for nom in (
                "python3", "python3-venv", "python3-tk", "ffmpeg", "mosquitto",
                "obs-studio", "avahi-daemon",
            )},
            "venv": True,
            "obs_actif": True,
            "websocket": "joignable",
            "scenes": ["Scene principale"],
            "sources": ["Selfie", "Carte", "Vitesse", "Pulsations", "Meteo", "Heure"],
            "navigateur": True,
            "bluetooth": "Powered: yes",
            "bnep": True,
            "mqtt_actif": True,
            "video": ["/dev/video0"],
            "ecoute_srt": True,
            "audio": "1 source",
            "ip": "10.0.0.2",
            "passerelle": "10.0.0.1",
            "nom_local": "dietpi.local",
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


if __name__ == "__main__":
    unittest.main()
