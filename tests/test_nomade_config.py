from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from nomade_config import ErreurConfiguration, charger_configuration, url_chat_active


CONFIG_TOML_MINIMAL = textwrap.dedent(
    """
    [general]
    language = "fr"

    [paths]
    repository = ""
    python_venv = "/opt/nomade-venv"
    data_dir = "/var/lib/nomade"
    log_dir = "/var/log/nomade"

    [obs]
    host = "127.0.0.1"
    port = 4455
    wait_seconds = 30
    collection = ""
    scene = "Scene principale"
    profile_preparation = "Nomade preparation"
    profile_direct = "Nomade direct fixe"
    source_selfie = "Selfie"
    source_carte = "Carte"
    source_vitesse = "Vitesse"
    source_pulsations = "Pulsations"
    source_meteo = "Meteo"
    source_heure = "Heure"

    [mqtt]
    host = "127.0.0.1"
    port = 1883
    topic = "nomade/capteurs"
    client_id = "nomade-capteurs"
    keepalive = 30
    network_interface = "bnep0"
    bluetooth_device_name = ""
    bluetooth_device_address = ""

    [chat]
    service = "none"
    source_name = "Chat multicanal"
    enabled_by_default = false
    velora_url = ""
    botrix_url = ""
    custom_url = ""

    [display]
    window_geometry = "1024x600"
    show_chat_panel = true

    [features]
    autostart_obs = true
    sync_chat_browser_source = true
    autostart_stream_on_launch = false

    [streaming]
    active_destination = ""
    notes = "Préparation seulement"

    [[streaming.destinations]]
    name = "twitch"
    service = "twitch"
    obs_profile = "Nomade direct fixe"
    enabled = false
    """
).strip()


class NomadeConfigTests(unittest.TestCase):
    def test_charge_configuration_et_calcule_les_chemins_derives(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")

            configuration = charger_configuration(repertoire_depot=repo)

            self.assertEqual(configuration["paths"]["repository"], str(repo))
            self.assertEqual(configuration["paths"]["python_venv"], "/opt/nomade-venv")
            self.assertEqual(configuration["paths"]["capteurs_file"], "/var/lib/nomade/capteurs.json")
            self.assertEqual(configuration["paths"]["chat_file"], "/var/lib/nomade/chat_unifie.log")
            self.assertEqual(configuration["paths"]["obs_direct_log"], "/var/log/nomade/obs-direct.log")

    def test_surcharge_locale_active_le_service_velora(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")
            (config_dir / "nomade.local.toml").write_text(
                textwrap.dedent(
                    """
                    [chat]
                    service = "velora"
                    enabled_by_default = true
                    velora_url = "https://velora.tv/overlay/chat-multi/identifiant-exemple"
                    """
                ).strip(),
                encoding="utf-8",
            )

            configuration = charger_configuration(repertoire_depot=repo)

            self.assertEqual(configuration["chat"]["service"], "velora")
            self.assertTrue(configuration["chat"]["enabled_by_default"])
            self.assertEqual(
                url_chat_active(configuration),
                "https://velora.tv/overlay/chat-multi/identifiant-exemple",
            )

    def test_refuse_un_hote_obs_non_local(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")
            (config_dir / "nomade.local.toml").write_text(
                textwrap.dedent(
                    """
                    [obs]
                    host = "0.0.0.0"
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ErreurConfiguration, "obs.host"):
                charger_configuration(repertoire_depot=repo)

    def test_refuse_un_service_chat_sans_url_associee(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")
            (config_dir / "nomade.local.toml").write_text(
                textwrap.dedent(
                    """
                    [chat]
                    service = "botrix"
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ErreurConfiguration, "nomade.local.toml"):
                charger_configuration(repertoire_depot=repo)

    def test_valide_video_sources_et_presets(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")
            (config_dir / "nomade.local.toml").write_text(
                textwrap.dedent(
                    """
                    [[video_sources]]
                    id = "g7_principal"
                    label = "Lumix G7 principal"
                    type = "capture_usb"
                    obs_source_name = "G7 Principal"
                    group = "camera_principale"
                    enabled_by_default = true

                    [[video_sources]]
                    id = "xiaomi_arriere"
                    label = "Xiaomi 11T grand angle"
                    type = "srt"
                    obs_source_name = "Xiaomi Arriere"
                    group = "camera_principale"
                    enabled_by_default = false
                    srt_port = 9001

                    [[presets]]
                    id = "sans_reperes"
                    label = "Sans repères"
                    activer = []
                    desactiver = ["carte", "vitesse"]
                    """
                ).strip(),
                encoding="utf-8",
            )

            configuration = charger_configuration(repertoire_depot=repo)

            self.assertEqual(len(configuration["video_sources"]), 2)
            self.assertEqual(configuration["video_sources"][1]["type"], "srt")
            self.assertEqual(configuration["video_sources"][1]["srt_port"], 9001)
            self.assertEqual(configuration["presets"][0]["id"], "sans_reperes")

    def test_refuse_un_type_video_source_invalide(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")
            (config_dir / "nomade.local.toml").write_text(
                textwrap.dedent(
                    """
                    [[video_sources]]
                    id = "camera_test"
                    label = "Camera Test"
                    type = "ndi"
                    obs_source_name = "Camera Test"
                    group = "camera_principale"
                    enabled_by_default = true
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ErreurConfiguration, "type invalide"):
                charger_configuration(repertoire_depot=repo)

    def test_refuse_une_video_source_sans_group(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")
            (config_dir / "nomade.local.toml").write_text(
                textwrap.dedent(
                    """
                    [[video_sources]]
                    id = "camera_test"
                    label = "Camera Test"
                    type = "capture_usb"
                    obs_source_name = "Camera Test"
                    enabled_by_default = true
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ErreurConfiguration, "doit définir group"):
                charger_configuration(repertoire_depot=repo)

    def test_refuse_des_ids_video_sources_dupliques(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")
            (config_dir / "nomade.local.toml").write_text(
                textwrap.dedent(
                    """
                    [[video_sources]]
                    id = "camera_test"
                    label = "Camera Test 1"
                    type = "capture_usb"
                    obs_source_name = "Camera Test 1"
                    group = "camera_principale"
                    enabled_by_default = true

                    [[video_sources]]
                    id = "camera_test"
                    label = "Camera Test 2"
                    type = "webcam"
                    obs_source_name = "Camera Test 2"
                    group = "camera_principale"
                    enabled_by_default = false
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ErreurConfiguration, "id dupliqué"):
                charger_configuration(repertoire_depot=repo)

    def test_refuse_un_preset_avec_identifiant_inconnu(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")
            (config_dir / "nomade.local.toml").write_text(
                textwrap.dedent(
                    """
                    [[presets]]
                    id = "preset_test"
                    label = "Preset test"
                    activer = ["source_inconnue"]
                    desactiver = []
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ErreurConfiguration, "identifiant est inconnu"):
                charger_configuration(repertoire_depot=repo)

    def test_refuse_un_enabled_by_default_non_booleen(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")
            (config_dir / "nomade.local.toml").write_text(
                textwrap.dedent(
                    """
                    [[video_sources]]
                    id = "camera_test"
                    label = "Camera Test"
                    type = "capture_usb"
                    obs_source_name = "Camera Test"
                    group = "camera_principale"
                    enabled_by_default = "false"
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ErreurConfiguration, "booléen"):
                charger_configuration(repertoire_depot=repo)

    def test_refuse_un_srt_port_non_numerique(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")
            (config_dir / "nomade.local.toml").write_text(
                textwrap.dedent(
                    """
                    [[video_sources]]
                    id = "xiaomi_arriere"
                    label = "Xiaomi"
                    type = "srt"
                    obs_source_name = "Xiaomi Arriere"
                    group = "camera_principale"
                    enabled_by_default = true
                    srt_port = "abc"
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ErreurConfiguration, "srt_port invalide"):
                charger_configuration(repertoire_depot=repo)

    def test_refuse_un_identifiant_vide_dans_un_preset(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")
            (config_dir / "nomade.local.toml").write_text(
                textwrap.dedent(
                    """
                    [[presets]]
                    id = "preset_test"
                    label = "Preset test"
                    activer = [" "]
                    desactiver = []
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ErreurConfiguration, "identifiant vide"):
                charger_configuration(repertoire_depot=repo)

    def test_refuse_un_srt_port_sur_source_non_srt(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")
            (config_dir / "nomade.local.toml").write_text(
                textwrap.dedent(
                    """
                    [[video_sources]]
                    id = "webcam"
                    label = "Webcam"
                    type = "webcam"
                    obs_source_name = "Webcam"
                    group = "camera_principale"
                    enabled_by_default = true
                    srt_port = 9000
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ErreurConfiguration, "ne peut définir srt_port"):
                charger_configuration(repertoire_depot=repo)

    def test_refuse_des_ids_presets_dupliques(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")
            (config_dir / "nomade.local.toml").write_text(
                textwrap.dedent(
                    """
                    [[presets]]
                    id = "preset_test"
                    label = "Preset 1"
                    activer = []
                    desactiver = []

                    [[presets]]
                    id = "preset_test"
                    label = "Preset 2"
                    activer = []
                    desactiver = []
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ErreurConfiguration, "presets contient un id dupliqué"):
                charger_configuration(repertoire_depot=repo)

    def test_refuse_un_id_preset_vide(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            repo = Path(dossier)
            config_dir = repo / "config"
            config_dir.mkdir()
            (config_dir / "nomade.toml").write_text(CONFIG_TOML_MINIMAL, encoding="utf-8")
            (config_dir / "nomade.local.toml").write_text(
                textwrap.dedent(
                    """
                    [[presets]]
                    id = ""
                    label = "Preset sans id"
                    activer = []
                    desactiver = []
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ErreurConfiguration, "preset doit définir un id non vide"):
                charger_configuration(repertoire_depot=repo)


if __name__ == "__main__":
    unittest.main()
