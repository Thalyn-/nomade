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


if __name__ == "__main__":
    unittest.main()
