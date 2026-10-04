from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from emissio import (
    charger_plateformes,
    chemin_service_obs,
    ecrire_destination_srt,
    ecrire_service_obs,
    ecrire_service_plateforme,
    tester_serveur,
    valider_destination,
)


class EmissioTests(unittest.TestCase):
    def test_definitions_des_plateformes_sont_extensibles_et_traduisibles(self) -> None:
        plateformes = charger_plateformes(ROOT / "config" / "plateformes.toml")

        self.assertEqual(
            {plateforme["id"] for plateforme in plateformes},
            {"twitch", "kick", "youtube", "facebook", "velora", "restream", "personnalise"},
        )
        self.assertTrue(all(plateforme["libelle"].startswith("platform_") for plateforme in plateformes))
        self.assertTrue(all(not plateforme["serveurs"] for plateforme in plateformes))
        self.assertTrue(all(plateforme["profil"].startswith("Nomade - ") for plateforme in plateformes))

    def test_validation_du_serveur_rtmp_et_srt(self) -> None:
        self.assertEqual(valider_destination("rtmps://stream.example/live", "RTMP"), ("stream.example", 443))
        self.assertEqual(valider_destination("srt://stream.example:9001?mode=caller", "SRT"), ("stream.example", 9001))
        self.assertEqual(valider_destination("srt://stream.example", "SRT"), ("stream.example", 9001))
        self.assertIsNone(valider_destination("https://stream.example", "RTMP"))
        self.assertFalse(tester_serveur("not a server", "RTMP"))

    def test_profile_obs_ne_peut_pas_sortir_du_dossier_des_profils(self) -> None:
        with self.assertRaises(ValueError):
            chemin_service_obs(Path("/home/user"), "../outside")

    def test_service_obs_est_sauvegarde_localement_avec_droits_restraints(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "profile" / "service.json"
            chemin.parent.mkdir()
            chemin.write_text('{"ancien": true}\n', encoding="utf-8")

            sauvegarde = ecrire_service_obs(chemin, "rtmps://serveur.example/live", "cle-factice")

            self.assertIsNotNone(sauvegarde)
            self.assertTrue(sauvegarde.is_file())
            self.assertEqual(os.stat(chemin).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(sauvegarde).st_mode & 0o777, 0o600)
            resultat = json.loads(chemin.read_text(encoding="utf-8"))
            self.assertEqual(resultat["settings"]["server"], "rtmps://serveur.example/live")
            self.assertEqual(resultat["settings"]["key"], "cle-factice")

    def test_profil_plateforme_copie_les_reglages_video_et_protege_la_cle(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            home = Path(dossier)
            base = chemin_service_obs(home, "Nomade direct fixe")
            base.parent.mkdir(parents=True)
            (base.parent / "basic.ini").write_text("[Output]\nMode=Advanced\n", encoding="utf-8")
            base.write_text('{"settings":{"key":"ancienne-cle"}}\n', encoding="utf-8")

            destination = ecrire_service_plateforme(
                home, "Nomade direct fixe", "Nomade - Twitch",
                "rtmps://serveur.example/live", "cle-factice",
            )

            profil = chemin_service_obs(home, "Nomade - Twitch")
            donnees = json.loads(profil.read_text(encoding="utf-8"))
            self.assertEqual(donnees["settings"]["key"], "cle-factice")
            self.assertEqual((profil.parent / "basic.ini").read_text(encoding="utf-8"), "[Output]\nMode=Advanced\n")
            self.assertFalse((profil.parent / "service.json.bak").exists())
            self.assertEqual(os.stat(profil).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(profil.parent).st_mode & 0o777, 0o700)
            self.assertIsNone(destination)
            self.assertEqual(json.loads(base.read_text(encoding="utf-8"))["settings"]["key"], "ancienne-cle")

    def test_destination_srt_est_stockee_dans_le_fichier_secret_local(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            fichier = Path(dossier) / "nomade.secrets"
            ecrire_destination_srt(fichier, "srt://serveur.example:9001", "cle-factice")
            valeurs = json.loads(fichier.read_text(encoding="utf-8"))
            self.assertEqual(valeurs["STREAM_PROTOCOL"], "SRT")
            self.assertEqual(valeurs["STREAM_SERVER"], "srt://serveur.example:9001")
            self.assertEqual(valeurs["STREAM_KEY"], "cle-factice")
            self.assertEqual(os.stat(fichier).st_mode & 0o777, 0o600)

    def test_secret_obs_est_local_securise_et_charge_dans_environnement(self) -> None:
        from nomade_secrets import charger_secret_obs, enregistrer_secret_obs

        with tempfile.TemporaryDirectory() as dossier, patch.dict(os.environ, {}, clear=True):
            chemin = Path(dossier) / "nomade.secrets"
            enregistrer_secret_obs(chemin, "mot-de-passe-factice")
            self.assertEqual(os.stat(chemin).st_mode & 0o777, 0o600)
            charger_secret_obs(chemin)
            self.assertEqual(os.environ["OBS_MDP"], "mot-de-passe-factice")


if __name__ == "__main__":
    unittest.main()
