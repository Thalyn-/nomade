from __future__ import annotations

import json
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from nomade_utils import charger_traductions
from installer_scenes_obs import (
    ajouter_modele,
    charger_modele,
    choisir_type,
    formater_compte_rendu,
    formater_erreur_import,
    importer_modele,
    preparer_affichages,
    sauvegarder_collections,
)
from nomade_config import charger_configuration
from primum_initium import (
    calculer_modifications,
    construire_rapport,
    etape_suivante,
    etat_bouton_obs,
    ecrire_configuration_locale,
    ecrire_configuration_wifi,
    decrire_modifications,
    essentiels_valides,
    construire_adresses_srt,
    marquer_premier_lancement_obs,
    reconnecter_wifi,
    ecarts_ports_srt,
    reseaux_detectes,
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
                "obs-studio", "avahi-daemon", "avahi-utils", "onboard",
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
        self.assertEqual(rapport.reseau["srt_nom"], "srt://dietpi.local:9001?mode=caller")
        self.assertEqual(rapport.reseau["srt_ip"], "srt://10.0.0.2:9001?mode=caller")
        self.assertEqual(rapport.reseau["telephone"], "10.0.0.5")

    def test_rapport_affiche_une_adresse_srt_par_source(self) -> None:
        faits = dict(self.faits)
        faits["sources_srt"] = [
            {"nom": "Xiaomi Arriere", "label": "Arrière", "port": 9001},
            {"nom": "Xiaomi Selfie", "label": "Selfie", "port": 9002},
        ]
        faits["ports_srt"] = [9001, 9002]
        faits["ports_srt_ecoute"] = [9001]
        rapport = construire_rapport(faits, self.textes)

        adresses = rapport.reseau["srt_adresses"]
        self.assertEqual([a["port"] for a in adresses], [9001, 9002])
        self.assertEqual(adresses[1]["nom"], "srt://dietpi.local:9002?mode=caller")
        self.assertEqual(adresses[1]["ip"], "srt://10.0.0.2:9002?mode=caller")
        srt = next(ligne for ligne in rapport.verifications if ligne.cle == "srt")
        self.assertEqual(srt.etat, "ok")

    def test_ecarts_de_port_srt_sont_signales(self) -> None:
        sources = [
            {"nom": "A", "label": "A", "port": 9001},
            {"nom": "B", "label": "B", "port": 9001},
            {"nom": "C", "label": "C", "port": 9003},
        ]
        ecarts = ecarts_ports_srt(sources, {"A": "srt://:9001?mode=listener", "C": "srt://:9002?mode=listener"})
        self.assertEqual(len(ecarts), 2)
        self.assertTrue(any("B / A" in e for e in ecarts))
        self.assertTrue(any("C : 9003 / 9002" in e for e in ecarts))
        self.assertEqual(ecarts_ports_srt(sources[:1], {"A": "srt://:9001?mode=listener"}), [])

        faits = dict(self.faits)
        faits["ecarts_srt"] = ecarts
        ligne = next(l for l in construire_rapport(faits, self.textes).verifications if l.cle == "srt_ports")
        self.assertEqual(ligne.etat, "alerte")

    def test_rapport_distingue_les_erreurs_websocket(self) -> None:
        for etat, mot in (
            ("mot_de_passe", "Mot de passe"),
            ("indisponible", "injoignable"),
            ("erreur", "interne"),
        ):
            faits = dict(self.faits, websocket=etat, websocket_erreur="TypeError: détail exact")
            ligne = next(
                l for l in construire_rapport(faits, self.textes).verifications if l.cle == "websocket"
            )
            self.assertEqual(ligne.etat, "erreur")
            self.assertIn(mot, ligne.message)
        self.assertIn("TypeError: détail exact", ligne.message)


    def test_construit_les_deux_adresses_srt_sans_nom_dhote_en_dur(self) -> None:
        self.assertEqual(
            construire_adresses_srt("raspberry.local", "10.0.0.2"),
            ("srt://raspberry.local:9001?mode=caller", "srt://10.0.0.2:9001?mode=caller"),
        )
        self.assertEqual(construire_adresses_srt("", ""), ("", ""))
        self.assertEqual(
            construire_adresses_srt("raspberry", "2001:db8::1")[1],
            "srt://[2001:db8::1]:9001?mode=caller",
        )

    def test_parcours_guide_choisit_la_premiere_etape_inachevee(self) -> None:
        faits = dict(self.faits)
        faits["internet"] = True
        self.assertEqual(etape_suivante(faits, False), "tablet")
        faits["internet"] = False
        self.assertEqual(etape_suivante(faits, False), "network")
        faits["internet"] = True
        faits["obs_actif"] = False
        self.assertEqual(etape_suivante(faits, True), "obs")
        faits["obs_actif"] = True
        faits["websocket"] = "absent"
        self.assertEqual(etape_suivante(faits, True), "websocket")
        faits["websocket"] = "joignable"
        self.assertEqual(
            etape_suivante(faits, True, configuration_a_jour=True, profils_configures=True),
            "launch",
        )

    def test_bouton_obs_est_grise_si_obs_est_deja_lance(self) -> None:
        self.assertEqual(etat_bouton_obs(True), "disabled")
        self.assertEqual(etat_bouton_obs(False), "normal")

    def test_premier_lancement_obs_est_marque_apres_sauvegarde(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "global.ini"
            chemin.write_text("[General]\nFirstRun=false\nTheme=Dark\n", encoding="utf-8")

            sauvegarde = marquer_premier_lancement_obs(chemin)

            self.assertIsNotNone(sauvegarde)
            self.assertEqual(sauvegarde.read_text(encoding="utf-8"), "[General]\nFirstRun=false\nTheme=Dark\n")
            self.assertEqual(chemin.read_text(encoding="utf-8"), "[General]\nFirstRun=true\nTheme=Dark\n")
            self.assertEqual(chemin.stat().st_mode & 0o777, 0o600)
            self.assertIsNone(marquer_premier_lancement_obs(chemin))

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

    def test_configuration_wifi_sauvegarde_et_protege_le_mot_de_passe(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "wpa_supplicant.conf"
            chemin.write_text("country=FR\nnetwork={\n    ssid=\"ancien\"\n}\n", encoding="utf-8")

            sauvegarde = ecrire_configuration_wifi(chemin, "nouveau", "mot-de-passe-test")

            self.assertIsNotNone(sauvegarde)
            self.assertIn('ssid="nouveau"', chemin.read_text(encoding="utf-8"))
            self.assertIn('psk="mot-de-passe-test"', chemin.read_text(encoding="utf-8"))
            self.assertEqual(os.stat(chemin).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(sauvegarde).st_mode & 0o777, 0o600)

    def test_configuration_wifi_refuse_les_entrees_invalides(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            with self.assertRaises(ValueError):
                ecrire_configuration_wifi(Path(dossier) / "wpa.conf", "x" * 33, "court")

    def test_configuration_wifi_accepte_une_cle_hexadecimale_wpa(self) -> None:
        cle = "a" * 64
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "wpa.conf"
            ecrire_configuration_wifi(chemin, "reseau", cle)
            self.assertIn(f"psk={cle}", chemin.read_text(encoding="utf-8"))

    def test_reconnexion_wifi_relance_le_reseau_en_premier(self) -> None:
        appels = []

        def executer(commande, **_options):
            appels.append(commande)
            code = 1 if commande[0] == "ifup" else 0
            return type("Resultat", (), {"returncode": code, "stdout": "", "stderr": ""})()

        resultat = reconnecter_wifi(executer)

        self.assertEqual(len(resultat), 6)
        self.assertEqual(appels[0], ("systemctl", "restart", "networking"))

    def test_reconnexion_wifi_ignore_rfkill_absent_sans_bloquer(self) -> None:
        appels = []

        def executer(commande, **_options):
            appels.append(commande)
            if commande[0] == "rfkill":
                raise FileNotFoundError("rfkill")
            return type("Resultat", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        resultat = reconnecter_wifi(executer)

        self.assertEqual(resultat[1], ("rfkill", 2, "outil_absent"))
        self.assertEqual(len(appels), 6)

    def test_reseaux_wifi_sont_extraits_sans_doublons(self) -> None:
        sortie = 'ESSID:"Reseau A"\nESSID:"Reseau B"\nESSID:"Reseau A"'
        self.assertEqual(reseaux_detectes(sortie), ["Reseau A", "Reseau B"])

    def test_suivant_est_bloque_tant_que_les_essentiels_manquent(self) -> None:
        essentiels = {
            "python3", "python3-venv", "python3-tk", "ffmpeg",
            "mosquitto", "obs-studio", "avahi-daemon", "avahi-utils", "onboard",
        }
        faits = {
            "internet": True,
            "paquets": {nom: True for nom in essentiels},
            "venv": True,
            "obs_actif": True,
            "websocket": "joignable",
            "navigateur": True,
            "ip": "10.0.0.2",
            "avahi_actif": True,
            "config": {
                "mqtt": {"network_interface": "bnep0"},
                "obs": {"scene": "Scene", "source_selfie": "Selfie"},
                "chat": {"source_name": "Chat"},
                "video_sources": [],
            },
            "scenes": ["Scene"],
            "sources": ["Selfie", "Chat"],
        }

        self.assertFalse(essentiels_valides(faits, False))
        self.assertTrue(essentiels_valides(faits, True))
        faits["internet"] = False
        self.assertFalse(essentiels_valides(faits, True))

    def test_diff_configuration_locale_affiche_ancienne_et_nouvelle_valeur(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "nomade.local.toml"
            chemin.write_text('[network]\nraspberry_ip = "10.0.0.1"\n', encoding="utf-8")
            diff = decrire_modifications(
                chemin,
                {"raspberry_ip": "10.0.0.2"},
                {"diff_line": "{key} : {before} -> {after}", "not_configured": "non défini"},
            )
            self.assertEqual(diff, "raspberry_ip : 10.0.0.1 -> 10.0.0.2")

    def test_interface_bluetooth_met_a_jour_le_parametre_mqtt_effectif(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "nomade.local.toml"
            chemin.write_text('[mqtt]\nnetwork_interface = "bnep0"\n', encoding="utf-8")
            modifications = calculer_modifications(
                chemin, {"mqtt.network_interface": "bnep1"}
            )
            ecrire_configuration_locale(chemin, modifications)
            configuration = tomllib.loads(chemin.read_text(encoding="utf-8"))
            self.assertEqual(configuration["mqtt"]["network_interface"], "bnep1")

    def test_modele_obs_contient_les_noms_et_le_port_de_configuration(self) -> None:
        modele = charger_modele(ROOT / "examples/nomade-scenes.json", Path("/tmp/nomade-data"))
        configuration = charger_configuration(repertoire_depot=ROOT)
        noms = {source["name"] for source in modele["sources"]}

        self.assertIn(configuration["obs"]["scene"], modele["scenes"])
        self.assertIn(configuration["chat"]["source_name"], noms)
        self.assertTrue(all(source["obs_source_name"] in noms for source in configuration["video_sources"]))
        sources_srt = [source for source in modele["sources"] if source["kind"] == "ffmpeg_source"]
        self.assertTrue(sources_srt)
        ports_modele = {
            source["name"]: int(source["settings"]["input"].split(":")[2].split("?")[0])
            for source in sources_srt
        }
        self.assertEqual(len(set(ports_modele.values())), len(ports_modele))
        self.assertNotIn(4455, ports_modele.values())
        for source in configuration["video_sources"]:
            if source["type"] == "srt":
                self.assertEqual(ports_modele[source["obs_source_name"]], source["srt_port"])
        self.assertEqual(ports_modele["Xiaomi Arriere"], 9001)
        sources_texte = [source for source in modele["sources"] if source["kind"] == "text_ft2_source_v2"]
        self.assertTrue(sources_texte)
        self.assertTrue(all("/tmp/nomade-data/overlays/" in source["settings"]["text_file"] for source in sources_texte))
        self.assertIn("Guide Nomade", modele["scenes"])

    def test_import_modele_place_la_source_guide_dans_sa_scene(self) -> None:
        class ClientFactice:
            def __init__(self) -> None:
                self.scenes = []
                self.inputs = []

            def get_scene_list(self):
                return type("Reponse", (), {"scenes": self.scenes})()

            def get_input_list(self):
                return type("Reponse", (), {"inputs": self.inputs})()

            def send(self, requete, donnees):
                if requete == "CreateScene":
                    self.scenes.append({"sceneName": donnees["sceneName"]})
                elif requete == "CreateInput":
                    self.inputs.append(donnees)

        client = ClientFactice()
        modele = {
            "scenes": ["Scene principale", "Guide Nomade"],
            "sources": [{
                "name": "Guide Nomade", "scene": "Guide Nomade",
                "kind": "text_ft2_source", "settings": {}, "enabled": True,
            }],
        }

        ajouter_modele(client, modele)

        self.assertEqual(client.inputs[0]["sceneName"], "Guide Nomade")

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

    def test_sauvegarde_des_collections_est_creee_avant_import(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            collection = Path(dossier) / "collection.json"
            collection.write_text('{"name":"Ma collection"}', encoding="utf-8")

            sauvegardes = sauvegarder_collections(Path(dossier))

            self.assertEqual(len(sauvegardes), 1)
            self.assertIn(".bak", sauvegardes[0].name)
            self.assertEqual(sauvegardes[0].read_text(encoding="utf-8"), '{"name":"Ma collection"}')

    def test_sauvegarde_des_collections_accepte_un_dossier_vide(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            self.assertEqual(sauvegarder_collections(Path(dossier)), [])


class ClientObsFactice:
    """Faux OBS : types disponibles configurables, échecs par source."""

    def __init__(self, types=None, echecs=None, scenes=None, sources=None, elements=None) -> None:
        self.types = types
        self.echecs = echecs or {}
        self.scenes = [{"sceneName": nom} for nom in (scenes or [])]
        self.sources = [{"inputName": nom} for nom in (sources or [])]
        self.elements = elements or {}
        self.creations: list[dict] = []
        self.requetes: list[tuple[str, dict]] = []

    def get_scene_list(self):
        return type("R", (), {"scenes": self.scenes})()

    def get_input_list(self):
        return type("R", (), {"inputs": self.sources})()

    def get_input_kind_list(self, unversioned):
        if self.types is None:
            raise AttributeError("indisponible")
        return type("R", (), {"input_kinds": self.types})()

    def get_scene_item_list(self, scene_name):
        return type("R", (), {"scene_items": [
            {"sourceName": nom} for nom in self.elements.get(scene_name, [])
        ]})()

    def send(self, requete, donnees):
        self.requetes.append((requete, donnees))
        if requete == "CreateScene":
            self.scenes.append({"sceneName": donnees["sceneName"]})
        elif requete == "CreateInput":
            echec = self.echecs.get(donnees["inputName"])
            if echec:
                raise echec
            self.sources.append({"inputName": donnees["inputName"]})
            self.creations.append(donnees)
        elif requete == "CreateSceneItem":
            self.elements.setdefault(donnees["sceneName"], []).append(donnees["sourceName"])


class ErreurObs(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"Request CreateInput returned code {code}. With message: kind not supported")
        self.code = code


class ImportScenesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.textes = charger_traductions("fr", ROOT / "locales")

    @staticmethod
    def source(nom: str, kind: str = "text_ft2_source_v2") -> dict:
        return {"name": nom, "kind": kind, "settings": {"from_file": True, "text_file": "/x"}, "enabled": False}

    def test_type_absent_utilise_le_repli(self) -> None:
        client = ClientObsFactice(types=["text_ft2_source", "v4l2_input"])
        compte_rendu = importer_modele(client, {"scenes": ["S"], "sources": [self.source("Carte")]})

        self.assertEqual(client.creations[0]["inputKind"], "text_ft2_source")
        self.assertEqual(compte_rendu.creees, ["Carte"])
        self.assertEqual(compte_rendu.remplacements, {"Carte": "text_ft2_source"})
        self.assertEqual(compte_rendu.ignorees, [])

    def test_type_par_defaut_prefere_quand_disponible(self) -> None:
        self.assertEqual(choisir_type("text_ft2_source_v2", ["text_ft2_source", "text_ft2_source_v2"]), "text_ft2_source_v2")
        self.assertEqual(choisir_type("ffmpeg_source", None), "ffmpeg_source")

    def test_type_absent_sans_repli_ignore_la_source_et_continue(self) -> None:
        client = ClientObsFactice(types=["color_source_v3"])
        modele = {"scenes": ["S"], "sources": [
            self.source("Chat", "browser_source"), self.source("Selfie", "color_source_v3"),
        ]}
        compte_rendu = importer_modele(client, modele)

        self.assertEqual(compte_rendu.creees, ["Selfie"])
        self.assertEqual([(s.nom, s.type_demande) for s in compte_rendu.ignorees], [("Chat", "browser_source")])
        rapport = formater_compte_rendu(compte_rendu, self.textes)
        self.assertIn("Chat", rapport)
        self.assertIn("browser_source", rapport)
        self.assertIn("1 ignorée", rapport)

    def test_echec_de_creation_n_arrete_pas_l_import(self) -> None:
        client = ClientObsFactice(types=None, echecs={"Carte": ErreurObs(605)})
        modele = {"scenes": ["S"], "sources": [self.source("Carte"), self.source("Vitesse")]}
        compte_rendu = importer_modele(client, modele)

        self.assertEqual(compte_rendu.creees, ["Vitesse"])
        self.assertEqual(compte_rendu.ignorees[0].code, 605)
        rapport = formater_compte_rendu(compte_rendu, self.textes)
        self.assertIn("605", rapport)
        self.assertIn("type de source non pris en charge", rapport)

    def test_reprise_apres_echec_partiel_sans_doublon(self) -> None:
        client = ClientObsFactice(echecs={"Carte": ErreurObs(605)})
        modele = {"scenes": ["S"], "sources": [self.source("Carte"), self.source("Vitesse")]}
        importer_modele(client, modele)
        client.echecs = {}

        compte_rendu = importer_modele(client, modele)

        self.assertEqual(compte_rendu.creees, ["Carte"])
        self.assertEqual(compte_rendu.presentes, ["Vitesse"])
        self.assertEqual([c["inputName"] for c in client.creations], ["Vitesse", "Carte"])
        self.assertEqual([r for r in client.requetes if r[0] == "CreateScene"], [("CreateScene", {"sceneName": "S"})])

    def test_source_existante_est_rattachee_a_la_scene_voulue(self) -> None:
        client = ClientObsFactice(sources=["Guide"], scenes=["S", "Guide Nomade"], elements={"Guide Nomade": []})
        source = dict(self.source("Guide"), scene="Guide Nomade")
        compte_rendu = importer_modele(client, {"scenes": ["S", "Guide Nomade"], "sources": [source]})

        self.assertEqual(compte_rendu.rattachees, ["Guide"])
        self.assertEqual(client.elements["Guide Nomade"], ["Guide"])
        self.assertEqual(client.creations, [])
        self.assertEqual(importer_modele(client, {"scenes": ["S", "Guide Nomade"], "sources": [source]}).rattachees, [])

    def test_erreur_de_connexion_interrompt_l_import_avec_consigne_websocket(self) -> None:
        class Coupe(ClientObsFactice):
            def send(self, requete, donnees):
                raise ConnectionRefusedError("refused")

        with self.assertRaises(ConnectionRefusedError) as contexte:
            importer_modele(Coupe(), {"scenes": ["S"], "sources": []})
        self.assertIn("127.0.0.1:4455", formater_erreur_import(contexte.exception, self.textes))
        message = formater_erreur_import(TypeError("boom"), self.textes)
        self.assertNotIn("127.0.0.1:4455", message)
        self.assertIn("TypeError", message)

    def test_fichiers_d_exemple_des_affichages_sont_crees_sans_ecraser(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            self.assertIsNone(preparer_affichages(Path(dossier), self.textes))
            vitesse = Path(dossier) / "overlays" / "vitesse.txt"
            self.assertTrue(vitesse.is_file())
            vitesse.write_text("42 km/h\n", encoding="utf-8")
            preparer_affichages(Path(dossier), self.textes)
            self.assertEqual(vitesse.read_text(encoding="utf-8"), "42 km/h\n")


if __name__ == "__main__":
    unittest.main()
