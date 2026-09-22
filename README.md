# nomade

Solution mobile de diffusion en direct pilotée localement sur Raspberry Pi 4B (DietPi Bookworm), avec caméra HDMI principale, caméra selfie du téléphone, capteurs (position, vitesse), et commandes de scènes/éléments visuels.

## Objectif

Ce dépôt fournit une base **simple, locale et robuste** pour :

- lancer/couper un direct ;
- activer ou désactiver des éléments visuels (selfie, carte, vitesse, pulsations, météo, heure) ;
- afficher l’état réseau et les dernières lignes d’un chat unifié ;
- préparer une structure évolutive pour mini-jeux en direct.

## Architecture recommandée

- **Caméra principale** : Panasonic Lumix G7 connecté en HDMI à une clé ou un boîtier de capture, lui-même connecté au Raspberry.
- **Caméra secondaire** : Xiaomi 11T (application caméra IP ou WebRTC) connecté comme source réseau dans OBS.
- **Capteurs** : Xiaomi 11T (position, vitesse) enregistrés dans un fichier JSON local.
- **Direct** : OBS (ou OBS en mode allégé) sur Raspberry, sortie RTMPS/SRT.
- **Interface locale** : script Python `scripts/interface_nomade.py` sur écran tactile 7 pouces.

## Fichiers ajoutés

- `scripts/install_nomade.sh` : installation des dépendances principales sur DietPi.
- `scripts/installer_obs_navigateur.sh` : installation d'OBS Studio avec la Source Navigateur (Browser Source) fonctionnelle sur Raspberry Pi 4.
- `scripts/lancer_obs.sh` : lancement d'OBS avec l'accélération graphique adaptée au Raspberry Pi 4.
- `scripts/lancer_nomade.sh` : lancement de l’interface locale.
- `scripts/interface_nomade.py` : interface graphique locale de pilotage OBS + état capteurs/chat.

## Installation (DietPi)

```bash
cd /chemin/vers/le/depot/nomade
chmod +x scripts/install_nomade.sh scripts/installer_obs_navigateur.sh scripts/lancer_obs.sh scripts/lancer_nomade.sh
./scripts/install_nomade.sh
```

Le script `install_nomade.sh` installe automatiquement OBS avec la Source Navigateur via `installer_obs_navigateur.sh` (voir section dédiée ci-dessous).

## Installation d'OBS avec la Source Navigateur (Browser Source)

### Le problème d'origine

Par défaut, le paquet officiel fourni par `apt install obs-studio` sur l'architecture ARM64 de Debian n'inclut **pas** le plugin navigateur (Source Navigateur / Browser Source). L'intégration de Chromium (CEF) y est désactivée par les mainteneurs, car jugée trop lourde ou trop complexe à compiler pour cette cible.

De plus, le GPU du Raspberry Pi 4 nécessite de simuler une version spécifique d'OpenGL pour lancer OBS correctement.

### La solution retenue

Le dépôt fournit deux scripts dédiés :

- `scripts/installer_obs_navigateur.sh` : supprime une éventuelle ancienne installation d'OBS, puis télécharge et installe un paquet `.deb` pré-compilé pour Debian Bookworm ARM64, maintenu par la communauté *Pi-Apps*, qui intègre nativement la Source Navigateur optimisée pour le processeur du Raspberry Pi.
- `scripts/lancer_obs.sh` : lance OBS avec la surcharge `MESA_GL_VERSION_OVERRIDE=3.3`, nécessaire à l'initialisation correcte d'OBS sur le GPU du Raspberry Pi 4.

Ce script est appelé automatiquement par `install_nomade.sh`, mais peut aussi être exécuté seul :

```bash
sudo ./scripts/installer_obs_navigateur.sh
```

Pour démarrer OBS ensuite (avec la Source Navigateur pleinement fonctionnelle) :

```bash
./scripts/lancer_obs.sh
```

> Remarque : ce paquet provient d'un dépôt communautaire tiers (Pi-Apps) et non des dépôts officiels Debian/DietPi. C'est un choix assumé pour disposer d'une Source Navigateur fonctionnelle sur Raspberry Pi 4 ; à réévaluer si Debian propose un jour un paquet officiel équivalent.

## Utilisation

1. Activer `obs-websocket` dans OBS (port 4455) et définir un mot de passe.
2. Créer les scènes/sources dans OBS avec des noms cohérents (exemples ci-dessous).
3. Lancer l’interface :

```bash
export OBS_MDP='votre_mot_de_passe'
./scripts/lancer_nomade.sh
```

## Noms conseillés dans OBS

Le script utilise ces noms (modifiables via arguments) :

- Scène principale : `Scene principale`
- Source selfie : `Selfie`
- Carte : `Carte`
- Vitesse : `Vitesse`
- Pulsations : `Pulsations`
- Météo : `Meteo`
- Heure : `Heure`

## Données capteurs/chat (fichiers locaux)

Par défaut :

- Capteurs : `/var/lib/nomade/capteurs.json`
- Chat : `/var/lib/nomade/chat_unifie.log`

Exemple `capteurs.json` :

```json
{
  "position": {"latitude": 48.8566, "longitude": 2.3522},
  "vitesse_kmh": 18.4,
  "pulsations": 121,
  "reseau": {"type": "5G", "signal_dbm": -92},
  "meteo": {"temperature_c": 22.1, "description": "nuageux"}
}
```

## Limites actuelles

- La récupération directe des pulsations de la montre Xiaomi Watch 5 Lite peut être limitée selon le protocole exposé.
- Le script lit des fichiers locaux pour rester stable hors ligne ; l’ingestion réseau (Traccar/SensorCast/Botrix) peut être ajoutée ensuite.
- Les mini-jeux sont prévus comme extension (zone dédiée dans l’interface).
- L'installation d'OBS avec la Source Navigateur repose sur un paquet tiers (Pi-Apps) et non sur les dépôts officiels Debian/DietPi (voir section dédiée ci-dessus).
