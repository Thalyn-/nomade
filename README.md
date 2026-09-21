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
- `scripts/lancer_nomade.sh` : lancement de l’interface locale.
- `scripts/interface_nomade.py` : interface graphique locale de pilotage OBS + état capteurs/chat.

## Installation (DietPi)

```bash
cd /chemin/vers/le/depot/nomade
chmod +x scripts/install_nomade.sh scripts/lancer_nomade.sh
./scripts/install_nomade.sh
```

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
