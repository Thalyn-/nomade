from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from nomade_utils import charger_traductions, ecrire_json_atomique, est_hote_obs_local, valider_charge_capteurs


class NomadeUtilsTests(unittest.TestCase):
    def test_charger_traductions_replie_sur_francais(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            locales = Path(dossier)
            (locales / "fr.json").write_text(
                json.dumps({"titre": "Titre FR", "bouton": "Bouton FR"}),
                encoding="utf-8",
            )
            (locales / "en.json").write_text(
                json.dumps({"bouton": "Button EN"}),
                encoding="utf-8",
            )

            traductions = charger_traductions("en", locales)

            self.assertEqual(traductions["titre"], "Titre FR")
            self.assertEqual(traductions["bouton"], "Button EN")

    def test_hote_obs_local_reste_limite_a_la_boucle_locale(self) -> None:
        self.assertTrue(est_hote_obs_local("127.0.0.1"))
        self.assertTrue(est_hote_obs_local("localhost"))
        self.assertFalse(est_hote_obs_local("0.0.0.0"))
        self.assertFalse(est_hote_obs_local("192.168.1.10"))

    def test_validation_capteurs_refuse_un_objet_invalide(self) -> None:
        with self.assertRaisesRegex(ValueError, "position"):
            valider_charge_capteurs({"position": "erreur"})

    def test_ecriture_atomique_remplace_le_contenu(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            sortie = Path(dossier) / "capteurs.json"
            sortie.write_text('{"ancien": true}', encoding="utf-8")

            ecrire_json_atomique(sortie, {"vitesse_kmh": 18.4, "position": {"latitude": 1}})

            self.assertEqual(
                json.loads(sortie.read_text(encoding="utf-8")),
                {"position": {"latitude": 1}, "vitesse_kmh": 18.4},
            )


if __name__ == "__main__":
    unittest.main()
