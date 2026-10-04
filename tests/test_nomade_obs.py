from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from nomade_obs import (
    INJOIGNABLE,
    INTERNE,
    MOT_DE_PASSE,
    REQUETE,
    ConnexionOBS,
    classer_erreur,
    creer_client,
)


class FabriqueNommee:
    """Imite ReqClient des versions récentes : arguments nommés uniquement."""

    appels: list[dict] = []

    def __init__(self, *, host, port, password, timeout) -> None:
        FabriqueNommee.appels.append(
            {"host": host, "port": port, "password": password, "timeout": timeout}
        )
        self.deconnecte = False

    def disconnect(self) -> None:
        self.deconnecte = True


class ErreurRequete(Exception):
    code = 605


class ClientObsTests(unittest.TestCase):
    def setUp(self) -> None:
        FabriqueNommee.appels = []

    def test_creer_client_utilise_des_arguments_nommes(self) -> None:
        client = creer_client("127.0.0.1", 4455, "secret", 3, fabrique=FabriqueNommee)
        self.assertIsInstance(client, FabriqueNommee)
        self.assertEqual(
            FabriqueNommee.appels,
            [{"host": "127.0.0.1", "port": 4455, "password": "secret", "timeout": 3}],
        )

    def test_aucun_appel_positionnel_a_reqclient_dans_le_depot(self) -> None:
        for chemin in [*(ROOT / "scripts").glob("*.py"), *(ROOT / "tests").glob("*.py")]:
            for noeud in ast.walk(ast.parse(chemin.read_text(encoding="utf-8"))):
                if not isinstance(noeud, ast.Call):
                    continue
                nom = getattr(noeud.func, "id", getattr(noeud.func, "attr", ""))
                if nom == "ReqClient":
                    self.assertEqual(noeud.args, [], f"{chemin.name}:{noeud.lineno}")

    def test_classification_des_erreurs(self) -> None:
        self.assertEqual(classer_erreur(ConnectionRefusedError("refused"))[0], INJOIGNABLE)
        self.assertEqual(classer_erreur(TimeoutError("timed out"))[0], INJOIGNABLE)
        self.assertEqual(classer_erreur(Exception("Authentication failed"))[0], MOT_DE_PASSE)
        self.assertEqual(classer_erreur(ErreurRequete("Request X returned code 605"))[0], REQUETE)
        categorie, detail = classer_erreur(TypeError("takes 1 positional argument but 4 were given"))
        self.assertEqual(categorie, INTERNE)
        self.assertIn("TypeError", detail)
        self.assertIn("positional argument", detail)

    def test_le_detail_ne_contient_pas_le_mot_de_passe(self) -> None:
        _categorie, detail = classer_erreur(ConnectionRefusedError("refused"))
        self.assertNotIn("secret", detail)


class ConnexionPersistanteTests(unittest.TestCase):
    def setUp(self) -> None:
        FabriqueNommee.appels = []
        self.temps = [0.0]

    def test_reutilise_une_seule_connexion(self) -> None:
        connexion = ConnexionOBS(fabrique=FabriqueNommee, horloge=lambda: self.temps[0])
        premier = connexion.obtenir()
        self.assertIs(connexion.obtenir(), premier)
        self.assertEqual(len(FabriqueNommee.appels), 1)

    def test_fermeture_propre(self) -> None:
        connexion = ConnexionOBS(fabrique=FabriqueNommee)
        client = connexion.obtenir()
        connexion.fermer()
        self.assertTrue(client.deconnecte)
        connexion.obtenir()
        self.assertEqual(len(FabriqueNommee.appels), 2)

    def test_reconnexion_avec_delai_croissant(self) -> None:
        tentatives = []

        def fabrique(**_arguments):
            tentatives.append(self.temps[0])
            raise ConnectionRefusedError("refused")

        connexion = ConnexionOBS(
            fabrique=fabrique, horloge=lambda: self.temps[0], delai_initial=2, delai_maximal=5
        )
        for instant in (0, 1, 2, 3, 5, 8, 12, 13, 20):
            self.temps[0] = instant
            with self.assertRaises(ConnectionRefusedError):
                connexion.obtenir()
        self.assertEqual(tentatives[:3], [0, 2, 8])
        self.assertTrue(all(b - a <= 8 for a, b in zip(tentatives, tentatives[1:])))

    def test_reinitialiser_autorise_une_reconnexion_immediate(self) -> None:
        etat = {"echec": True}

        def fabrique(**arguments):
            if etat["echec"]:
                raise ConnectionRefusedError("refused")
            return FabriqueNommee(**arguments)

        connexion = ConnexionOBS(fabrique=fabrique, horloge=lambda: self.temps[0])
        with self.assertRaises(ConnectionRefusedError):
            connexion.obtenir()
        etat["echec"] = False
        connexion.reinitialiser()
        self.assertIsInstance(connexion.obtenir(), FabriqueNommee)


if __name__ == "__main__":
    unittest.main()
