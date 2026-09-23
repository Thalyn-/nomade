# nomade

Solution locale de diffusion en direct pour Raspberry Pi 4B sous DietPi Bookworm, pensée pour un direct nomade avec OBS Studio, un téléphone Xiaomi 11T et une liaison capteurs la plus indépendante possible de la 5G.

## Objectif

Ce dépôt fournit une base **simple, locale, robuste et traduisible** pour :

- préparer les scènes et sources OBS avec l’interface complète quand c’est nécessaire ;
- lancer le direct avec un démarrage OBS allégé, sans dépendre d’OBS Studio ouvert manuellement en mode complet ;
- piloter localement la diffusion et quelques sources depuis un écran tactile relié au Raspberry ;
- recevoir des capteurs via MQTT sur une liaison Bluetooth distincte du tethering 5G, puis les écrire dans un fichier JSON local ;
- garder `obs-websocket` en boucle locale (`127.0.0.1`) pour ne pas exposer le contrôle OBS sur le réseau mobile.

## Architecture retenue

- **Préparation OBS** : `scripts/lancer_obs_preparation.sh`
  - interface OBS complète ;
  - profil de préparation dédié ;
  - même surcharge `MESA_GL_VERSION_OVERRIDE=3.3`.
- **Direct OBS** : `scripts/lancer_obs_direct.sh`
  - profil de direct fixe dédié ;
  - options OBS natives réellement disponibles sur OBS 30.2.x : `--profile`, `--collection`, `--scene`, `--minimize-to-tray`, `--disable-missing-files-check`, `--startstreaming` en option ;
  - **pas de vrai mode headless** : OBS Studio ne fournit pas ici de mode sans interface adapté à ce besoin. Le meilleur compromis natif reste donc un démarrage réduit, avec profil figé et fenêtre minimisée si l’environnement graphique le permet.
- **Interface locale** : `scripts/lancer_nomade.sh` puis `scripts/interface_nomade.py`
  - démarre l’interface Python ;
  - démarre aussi OBS direct allégé si OBS n’est pas déjà lancé ;
  - attend la disponibilité d’`obs-websocket` sur `127.0.0.1`.
- **Configuration centralisée** : `config/nomade.toml` puis `config/nomade.local.toml`
  - valeurs par défaut suivies dans Git ;
  - surcharge locale ignorée par Git ;
  - validation légère au démarrage et diagnostic via `scripts/nomade_config.py`.
- **Capteurs** : `scripts/lancer_capteurs_mqtt.sh` puis `scripts/capteurs_mqtt.py`
  - abonnement MQTT local ;
  - validation minimale des messages JSON ;
  - écriture atomique de `/var/lib/nomade/capteurs.json`.

## Distinction préparation / direct

### 1. Préparation des scènes et des sources

À utiliser hors direct pour créer ou modifier les scènes, profils et sources :

```bash
./scripts/lancer_obs_preparation.sh
```

Variables utiles :

- `NOMADE_OBS_PROFIL_PREPARATION` : nom du profil de préparation (défaut : `Nomade preparation`)
- `NOMADE_OBS_COLLECTION` : collection de scènes à ouvrir

### 2. Direct allégé

À utiliser pendant le direct, ou automatiquement via `scripts/lancer_nomade.sh` :

```bash
./scripts/lancer_obs_direct.sh
```

Variables utiles :

- `NOMADE_OBS_PROFIL_DIRECT` : nom du profil préparé/fixe (défaut : `Nomade direct fixe`)
- `NOMADE_OBS_COLLECTION` : collection de scènes à ouvrir
- `NOMADE_OBS_SCENE` : scène initiale
- `NOMADE_OBS_AUTOSTART_DIFFUSION=1` : ajoute `--startstreaming` si l’on veut démarrer la diffusion dès l’ouverture d’OBS

### Limite connue sur le « headless »

Cette version ne prétend pas fournir un « OBS headless » complet, car OBS Studio n’offre pas ici un mode sans interface réellement adapté à la préparation puis au direct. Le dépôt fournit donc :

- **OBS complet** pour la préparation ;
- **OBS allégé au maximum avec les options natives disponibles** pour le direct.

## Sécurité réseau et `obs-websocket`

- Le contrôle OBS doit rester **local au Raspberry**.
- L’interface utilise `127.0.0.1` par défaut et refuse les hôtes distants par sécurité.
- Il ne faut **pas** exposer `obs-websocket` sur `0.0.0.0`, sur l’interface 5G, ni sur une interface de tethering.
- Le transport des capteurs du téléphone ne doit pas être confondu avec le contrôle OBS : ce sont deux chemins distincts.

## Configuration centralisée

Nomade privilégie maintenant **un fichier de configuration TOML unique** plutôt que des modifications réparties dans plusieurs scripts.

- configuration suivie : `config/nomade.toml`
- modèle local : `config/nomade.local.toml.example`
- surcharge locale ignorée par Git : `config/nomade.local.toml`

Mise en route :

```bash
cp config/nomade.local.toml.example config/nomade.local.toml
python3 scripts/nomade_config.py --diagnostic
```

La configuration couvre notamment :

- la langue de l’interface ;
- les adresses et ports OBS/MQTT ;
- l’interface réseau capteurs (`bnep0` par défaut) et les informations Bluetooth utiles ;
- les scènes, profils et sources OBS ;
- le service de chat multicanal et la source Navigateur OBS associée ;
- quelques préférences d’affichage et fonctions activables ;
- les emplacements du dépôt, du venv Python, des données et des journaux.

### Sources vidéo interchangeables et groupes exclusifs

La configuration accepte désormais une liste `[[video_sources]]` :

- `id` : identifiant stable côté Nomade ;
- `label` : libellé affiché dans l’interface tactile ;
- `type` : `capture_usb`, `srt` ou `webcam` ;
- `obs_source_name` : nom exact de la source dans OBS ;
- `group` : groupe fonctionnel exclusif ;
- `enabled_by_default` : état initial ;
- `srt_port` : optionnel (informatif) pour les sources `srt`.

Les sources d’un même `group` sont mutuellement exclusives dans l’interface : sélectionner une source désactive automatiquement les autres du même groupe dans OBS.

Exemple typique :

- groupe `camera_principale` : G7 principal, G7 secours, Xiaomi grand angle ;
- groupe `vignette_visage` : Xiaomi selfie.

### Sources SRT Xiaomi via OBS (sans relais Python)

Nomade ne décode pas lui-même les flux SRT : OBS reste le moteur vidéo unique.

Pour une source SRT (ex. Larix Broadcaster sur Xiaomi), configurez côté OBS une **Source Média** en écoute :

`srt://0.0.0.0:9000?mode=listener`

Le flux est reçu nativement par OBS, puis Nomade ne fait qu’activer/désactiver la source via websocket.

### Presets (préréglages)

La liste `[[presets]]` permet d’appliquer en un clic plusieurs actions :

- `id`, `label`
- `activer` : identifiants à activer
- `desactiver` : identifiants à désactiver

Ces identifiants peuvent cibler les overlays existants (`selfie`, `carte`, `vitesse`, `pulsations`, `meteo`, `heure`, `chat_multicanal`) et les `id` de `video_sources`.

Exemples inclus :

- `sans_reperes` : masque `carte` et `vitesse`
- `trajet` : affiche `carte` et `vitesse`

### À propos de `/opt/nomade-venv`

Le chemin par défaut du venv reste `/opt/nomade-venv`. C’est un **choix d’organisation** classique pour une application tierce sous Debian/DietPi, pas un gain de performances. Le dépôt évite ainsi d’encourager une installation de l’application sous `/root`.

Si une installation existante a déjà été préparée sous `/root/nomade`, elle peut être conservée en surchargeant localement :

```toml
[paths]
python_venv = "/root/nomade/myvenv"
```

Cette surcharge permet une migration progressive sans casser l’installation actuelle.

## Interface locale : Tkinter conservé

L’interface principale reste **Python/Tkinter**. Ce choix est volontaire pour un Raspberry Pi 4B en direct :

- pas de serveur web supplémentaire à maintenir ;
- pas de navigateur obligatoire à ouvrir pendant le live ;
- moins de RAM et de moteur de rendu qu’une page Firefox/Chromium dédiée.

Une interface web locale pourrait être étudiée plus tard comme extension facultative, mais elle n’est **pas** implémentée dans cette évolution.

## Installation (DietPi Bookworm)

```bash
cd /chemin/vers/le/depot/nomade
chmod +x \
  scripts/install_nomade.sh \
  scripts/installer_obs_navigateur.sh \
  scripts/nomade_config.py \
  scripts/lancer_obs.sh \
  scripts/lancer_obs_preparation.sh \
  scripts/lancer_obs_direct.sh \
  scripts/lancer_nomade.sh \
  scripts/lancer_capteurs_mqtt.sh
sudo ./scripts/install_nomade.sh
```

Le script installe notamment :

- Python et Tk ;
- les dépendances Python du dépôt ;
- `mosquitto` et `mosquitto-clients` pour un courtier MQTT local ;
- OBS Studio avec Source Navigateur via le paquet communautaire Pi-Apps ;
- les répertoires de données et journaux définis dans `config/nomade.toml`.

## Installation d’OBS avec Source Navigateur

Le paquet officiel `apt install obs-studio` fourni sur Debian Bookworm ARM64 n’inclut pas la Source Navigateur sur cette cible. Le dépôt conserve donc `scripts/installer_obs_navigateur.sh`, qui installe le paquet communautaire Pi-Apps `obs-studio-30.2.2-1-arm64-bookworm.deb`.

Ce choix est volontaire :

- **on ne supprime pas** la Source Navigateur ;
- on garde l’accélération `MESA_GL_VERSION_OVERRIDE=3.3` nécessaire au Raspberry Pi 4 ;
- on évite de faire croire qu’un paquet Debian standard suffirait à reproduire le même comportement.

## Interface locale de pilotage

Exemple minimal :

```bash
export OBS_MDP='votre_mot_de_passe'
./scripts/lancer_nomade.sh
```

Comportement :

- si aucun processus `obs` n’est déjà lancé, le script démarre `scripts/lancer_obs_direct.sh` ;
- l’interface attend ensuite `obs-websocket` pendant `30` secondes par défaut ;
- l’hôte OBS reste fixé à `127.0.0.1` via le script de lancement.

Variables utiles :

- `OBS_MDP` : mot de passe `obs-websocket`
- `NOMADE_LANGUE=fr` ou `NOMADE_LANGUE=en`

Pour diagnostiquer la configuration réellement chargée :

```bash
python3 scripts/nomade_config.py --diagnostic
```

## Internationalisation

Les textes visibles de l’interface sont externalisés dans :

- `locales/fr.json` (par défaut)
- `locales/en.json` (repli anglais minimal)

Pour choisir la langue :

```bash
NOMADE_LANGUE=en ./scripts/lancer_nomade.sh
```

Les **noms de scènes**, **noms de sources** et **messages d’erreur techniques détaillés** restent configurables et ne sont pas traduits automatiquement.

Le français reste la langue par défaut des textes destinés à l’utilisateur.

Pour ajouter une autre langue :

1. copier `locales/fr.json` ;
2. traduire les valeurs ;
3. enregistrer le fichier sous `locales/<code>.json` ;
4. lancer avec `NOMADE_LANGUE=<code>`.

## Noms OBS conseillés

Les noms restent modifiables par arguments si besoin :

- scène principale : `Scene principale`
- source selfie : `Selfie`
- carte : `Carte`
- vitesse : `Vitesse`
- pulsations : `Pulsations`
- météo : `Meteo`
- heure : `Heure`

## Capteurs via MQTT sur liaison Bluetooth

### Principe retenu

Le dépôt privilégie une ingestion capteurs **MQTT locale** pour éviter autant que possible :

- les WebSocket venant du téléphone ;
- le Wi-Fi du hotspot/tethering ;
- l’USB tethering.

Le cas visé est une liaison Bluetooth indépendante, par exemple :

- **Bluetooth PAN / BNEP** entre téléphone et Raspberry ;
- ou un autre transport Bluetooth réellement compatible avec SensorCast et un courtier MQTT accessible côté Raspberry.

### Important : ce qui n’est pas supposé automatiquement

Cette version **ne prétend pas** que SensorCast, Bluetooth PAN, BNEP ou Mosquitto seraient configurés automatiquement par le dépôt. Il faut préparer explicitement :

1. le jumelage Bluetooth ;
2. le profil réseau Bluetooth réellement utilisé ;
3. l’adresse IP de l’interface Bluetooth côté Raspberry ;
4. la configuration de SensorCast pour publier en MQTT vers ce courtier local.

### Lancement de l’ingestion

```bash
./scripts/lancer_capteurs_mqtt.sh \
  --mqtt-hote 192.168.44.1 \
  --mqtt-port 1883 \
  --mqtt-sujet nomade/capteurs
```

Variables ou options disponibles :

- `NOMADE_MQTT_HOTE` (ou `config/nomade.local.toml`)
- `NOMADE_MQTT_PORT`
- `NOMADE_MQTT_SUJET`
- `NOMADE_MQTT_CLIENT_ID`
- `NOMADE_MQTT_UTILISATEUR`
- `NOMADE_MQTT_MOT_DE_PASSE`
- `NOMADE_FICHIER_CAPTEURS`

### Garantie fonctionnelle de l’ingestion

Le service :

- accepte des messages JSON ;
- vérifie au minimum que la charge utile est un objet JSON, et que `position`, `reseau` et `meteo` sont des objets s’ils existent ;
- écrit `/var/lib/nomade/capteurs.json` de façon atomique ;
- ignore un message invalide sans arrêter le processus ;
- tente de se reconnecter automatiquement si la liaison MQTT tombe.

### Exemple de configuration Mosquitto

Le dépôt fournit un exemple minimal dans `examples/mosquitto-bluetooth.conf.example`.

Principe recommandé :

- écouter **uniquement** sur l’adresse IP de l’interface Bluetooth (par exemple `bnep0`) ;
- ne pas écouter sur l’interface 5G ni sur toutes les interfaces.

## Chat multicanal via Source Navigateur OBS

Nomade ne réimplémente pas le chat dans Python. Le dépôt réutilise la **Source Navigateur OBS** déjà requise pour afficher une page de discussion multicanal distante.

Services prévus dans la configuration :

- `none`
- `velora`
- `botrix`
- `custom`

Exemple de surcharge locale :

```toml
[chat]
service = "velora"
source_name = "Chat multicanal"
enabled_by_default = false
velora_url = "https://velora.tv/overlay/chat-multi/identifiant-exemple"
```

Points importants :

- ne versionnez jamais vos URL personnelles Velora/Botrix ;
- l’interface Tkinter peut activer/désactiver la source OBS correspondante ;
- si `sync_chat_browser_source = true`, Nomade met à jour l’URL de la source Navigateur au démarrage ;
- une URL distante reste une dépendance réseau supplémentaire : vérifiez toujours la confiance accordée au service tiers ;
- une panne du service de chat ne doit pas empêcher le contrôle local OBS ni l’ingestion MQTT/Bluetooth.

## Diffusion multi-plateforme : préparation seulement

Cette évolution **n’automatise pas** encore le multistream complet, Restream ni la gestion de clés de diffusion.

La section `[streaming]` du TOML sert seulement à **préparer des destinations nommées** pour une évolution future, sans secrets. Pour l’instant :

- préparez vos profils et destinations dans `OBS-Preparation` ;
- choisissez ensuite le bon profil OBS pour le direct ;
- ne stockez ni clé de diffusion ni URL privée dans le dépôt.

## Données locales

Par défaut :

- capteurs : `/var/lib/nomade/capteurs.json`
- chat : `/var/lib/nomade/chat_unifie.log`

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

## Vérifications

Vérifications prévues avant demande de fusion :

- syntaxe shell avec `bash -n`
- compilation Python
- tests légers ciblés
- validation sécurité/secrets sur les fichiers modifiés

## Dépannage

- **L’interface dit que la connexion OBS est impossible**
  Vérifier que `obs-websocket` est activé dans OBS, avec mot de passe, sur `127.0.0.1:4455`.

- **OBS s’ouvre mais reste lourd**
  C’est une limite d’OBS Studio : il n’existe pas ici de mode headless complet pour le direct. Utiliser `scripts/lancer_obs_direct.sh` avec un profil fixe, déjà préparé.

- **Les capteurs n’arrivent pas**
  Vérifier d’abord la liaison Bluetooth/PAN, puis le courtier MQTT local, puis le sujet réellement publié par SensorCast.

- **Je veux vérifier ma configuration sans lancer le direct**
  Exécuter `python3 scripts/nomade_config.py --diagnostic` puis corriger `config/nomade.local.toml` si nécessaire.

- **Le direct 5G se coupe quand SensorCast tourne**
  Revenir à une topologie où MQTT ne passe pas par le tethering Wi-Fi ou USB, mais par une liaison Bluetooth réellement séparée.

## Limites connues

- pas de vrai mode headless OBS dans ce dépôt ;
- la configuration exacte de SensorCast et du profil réseau Bluetooth dépend du matériel et n’est donc pas imposée silencieusement ;
- la récupération directe des pulsations de certains objets connectés peut rester limitée selon leurs protocoles ;
- l’installation OBS repose toujours sur un paquet communautaire Pi-Apps pour conserver la Source Navigateur ;
- le multistream complet reste volontairement reporté à une évolution séparée.
