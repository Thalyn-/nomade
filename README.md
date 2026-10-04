# nomade

Solution locale de diffusion en direct pour Raspberry Pi 4B sous DietPi Bookworm, pensée pour un direct nomade avec OBS Studio, un téléphone Xiaomi 11T et une liaison capteurs la plus indépendante possible du réseau mobile utilisé pour la diffusion.

## Avant de commencer : une connexion internet stable

Internet est nécessaire pour télécharger DietPi, récupérer ce dépôt et installer les paquets. Une box reliée en Ethernet est la solution la plus simple. À défaut, un partage de connexion Wi-Fi de téléphone fonctionne, mais son adresse IP et sa passerelle peuvent changer : laissez le Raspberry en DHCP.

### Se connecter au Wi-Fi

1. Si DietPi est accessible, lancez `dietpi-config`, ouvrez le menu réseau, choisissez le Wi-Fi, sélectionnez votre réseau et saisissez sa clé. Redémarrez ou relancez l'interface si DietPi le demande.
2. Sinon, ouvrez la configuration en administrateur. La commande `sudoedit` conserve le fichier existant et permet de le modifier sans le remplacer à l'aveugle :

```bash
sudo cp -a /etc/wpa_supplicant/wpa_supplicant.conf \
  "/etc/wpa_supplicant/wpa_supplicant.conf.bak.$(date +%Y%m%d-%H%M%S)"
sudoedit /etc/wpa_supplicant/wpa_supplicant.conf
```

Dans l'éditeur, utilisez ce modèle et remplacez les deux valeurs sur le Raspberry uniquement :

```ini
country=FR
ctrl_interface=DIR=/run/wpa_supplicant GROUP=netdev
update_config=1
network={
    ssid="NOM_DU_RESEAU"
    psk="MOT_DE_PASSE"
    key_mgmt=WPA-PSK
}
```

Remplacez `FR` par le code pays de votre installation si vous êtes ailleurs. N'ajoutez pas `ieee80211d=1` dans la section globale. Gardez le mot de passe entre guillemets et aucun espace avant `psk=`. Les caractères accentués peuvent être mal interprétés par certains éditeurs ; préférez un nom de réseau et un mot de passe sans accents si vous pouvez les choisir. Ne collez jamais le vrai mot de passe dans le dépôt ou dans un journal.

Avec le pilote Wi-Fi `brcmfmac`, évitez que deux gestionnaires pilotent la même interface. Si `ifupdown` utilise `wpa-conf` dans `/etc/network/interfaces.d/wlan0.conf`, laissez-le gérer le Wi-Fi et n'activez pas en parallèle un service `wpa_supplicant-wlan0.service` créé manuellement. Vérifiez d'abord son origine et sa configuration ; désactivez-le seulement s'il a été créé pour cette interface :

```bash
systemctl status wpa_supplicant-wlan0.service
sudo systemctl disable --now wpa_supplicant-wlan0.service
```

Utilisez le DHCP, sans fixer l'adresse du Raspberry : c'est particulièrement important avec un partage 5G dont le réseau peut être en `10.x.x.x`. Si le téléphone le permet, réservez l'adresse du Raspberry dans les appareils connectés. Sur Xiaomi/HyperOS, cherchez **Paramètres > Point d'accès mobile > Appareils connectés** ; cette fonction n'est pas présente sur toutes les versions. Essayez ensuite le nom `.local` affiché par l'assistant ; certains téléphones ne le résolvent pas et nécessitent l'adresse IP courante.

### Déconnexions répétées : correctif conditionnel

N'appliquez ceci que si vous constatez réellement une boucle « CONNECTED / DISCONNECTED ». Identifiez d'abord le service ou script Wi-Fi présent sur votre installation :

```bash
systemctl list-units --all | grep -i wifi
```

Si `dietpi-wifi-monitor.service` est bien actif et que vous suspectez ses alertes erronées, arrêtez-le après confirmation :

```bash
sudo systemctl disable --now dietpi-wifi-monitor.service
```

Si le nom affiché est différent, adaptez la commande au nom réellement trouvé ; ne désactivez pas un service réseau au hasard.

### Kit de secours réseau

Depuis un terminal local, ces commandes permettent de débloquer et relancer le Wi-Fi. Elles peuvent couper brièvement la connexion ; gardez un écran et un clavier à disposition :

```bash
sudo systemctl restart networking
sudo rfkill unblock wifi
sudo wpa_cli -i wlan0 reconfigure
sudo ifdown wlan0 && sudo ifup wlan0
ip a
ping -c 3 deb.debian.org
```

Commencez par `sudo systemctl restart networking` : c'est la relance qui a rétabli le Wi-Fi lors du test réel. Cette commande peut couper brièvement les connexions. Si `rfkill` est introuvable, passez cette étape sans bloquer le dépannage ; vous pouvez l'installer avec `sudo apt install rfkill`, puis réessayer. Les commandes `wpa_cli`, `ifdown` et `ifup` peuvent elles aussi être absentes selon l'installation.

Enfin, ne confondez pas les deux flux : SRT transporte la vidéo en **UDP**, sur le port `9001` par défaut ; le contrôle obs-websocket utilise **TCP**, sur `127.0.0.1:4455`. Ces ports et protocoles sont indépendants.

## Objectif

Ce dépôt fournit une base **simple, locale, robuste et traduisible** pour :

- préparer les scènes et sources OBS avec l'interface complète quand c'est nécessaire ;
- lancer le direct avec un démarrage OBS allégé, sans dépendre d'OBS Studio ouvert manuellement en mode complet ;
- piloter localement la diffusion et quelques sources depuis un écran tactile relié au Raspberry ;
- recevoir des capteurs via MQTT sur une liaison Bluetooth distincte du tethering 5G, puis les écrire dans un fichier JSON local ;
- garder `obs-websocket` en boucle locale (`127.0.0.1`) pour ne pas exposer le contrôle OBS sur le réseau mobile.

## 1. Démarrage rapide (environ 10 minutes)

Cette durée suppose que DietPi, le bureau LXDE et le dépôt sont déjà installés. Une première installation de DietPi prend davantage de temps.

1. Branchez le Raspberry Pi, son écran et son alimentation ; connectez la clé d'acquisition et le téléphone si vous les utilisez.
2. Depuis le dépôt, lancez `sudo ./scripts/install_nomade.sh`. Le script installe les dépendances, OBS avec sa Source Navigateur, puis ouvre l'assistant de premier démarrage (ou affiche son diagnostic dans le terminal).
3. Dans PrimumInitium, suivez le grand bouton **Étape suivante**. Il guide le réseau, l'installation, le confort tactile, OBS, les scènes, les informations locales et les clés de diffusion. **Mode avancé** conserve les commandes et le bilan détaillé.
4. Configurez obs-websocket sur `127.0.0.1:4455` et importez le modèle Nomade lorsque l'assistant le propose. Adaptez ensuite les sources à votre matériel.
5. Dans Larix, essayez l'adresse SRT `.local` affichée par l'assistant ; si le téléphone ne résout pas ce nom, copiez l'adresse IP affichée à côté. SRT utilise le port UDP `9001`.
6. Une fois une plateforme configurée, sélectionnez-la dans Emissio et lancez le direct. OBS utilise alors son profil dédié.

Les préréglages Nomade ne font qu'activer ou désactiver des **sources et scènes déjà créées** : ils n'en créent aucune. L'import du modèle OBS depuis le parcours guidé ou `./scripts/installer_scenes_obs.sh` est donc indispensable.

## 2. Matériel nécessaire

- **Raspberry Pi 4B**, avec une alimentation fiable adaptée (5 V / 3 A recommandés).
- Carte microSD de bonne qualité, écran et clavier pour l'installation initiale ; un écran tactile est recommandé pour le contrôle du direct et du chat.
- Connexion réseau pour installer les paquets, puis Wi-Fi ou partage de connexion du téléphone. Une IP fixe sur le Raspberry n'est pas requise.
- Téléphone Android compatible avec Larix Broadcaster pour l'envoi SRT. IP Webcam peut convenir à un usage plus simple et moins exigeant en énergie ; NDI HX Camera est une alternative propriétaire, non recommandée par défaut.
- Facultatif : caméra HDMI et clé d'acquisition USB reconnue comme périphérique vidéo Linux (`/dev/video*`), microphone ou casque Bluetooth, ainsi qu'un système de refroidissement adapté aux longs directs.

L'encodage matériel du téléphone et l'arrêt de l'aperçu écran réduisent sa chauffe. Larix est généralement plus robuste sur un réseau instable, mais plus gourmand ; vérifiez la température lors des essais.

## 3. Installation fraîche de DietPi

Cette section s'adresse à une personne qui repart d'une carte mémoire vierge, sans DietPi déjà installé. Elle décrit uniquement les étapes nécessaires pour obtenir un Raspberry Pi 4B prêt à recevoir nomade. Pour les cas non couverts ici, reportez-vous au site officiel de DietPi.

1. **Récupérer l'image DietPi**
   - Téléchargez l'image DietPi correspondant au Raspberry Pi 4B (base Bookworm/Debian 12) depuis le site officiel : https://dietpi.com/
2. **Créer la carte mémoire de démarrage**
   - Utilisez un outil d'écriture d'image disque pour copier le fichier téléchargé sur la carte mémoire.
   - Plusieurs outils conviennent, au choix selon votre système : Raspberry Pi Imager, balenaEtcher ou Win32 Disk Imager. Aucun de ces choix n'est obligatoire, retenez celui qui vous convient.
3. **Premier démarrage du Raspberry Pi**
   - Insérez la carte mémoire dans le Raspberry Pi, branchez un écran et un clavier (ou préparez un accès par le réseau si vous maîtrisez déjà cette méthode), puis mettez sous tension.
4. **Première connexion**
   - Valeurs testées sur l'installation fraîche : nom d'utilisateur `root` (ou `dietpi`), mot de passe initial `dietpi`. Ces valeurs peuvent varier selon la version de DietPi téléchargée.
   - DietPi vous demandera normalement de changer ce mot de passe par défaut dès la première connexion : faites-le, pour votre sécurité.
5. **Paramétrage initial (`dietpi-config`)**
   - Réglez au minimum la langue du clavier, le fuseau horaire, ainsi que la connexion réseau (Wi-Fi ou câble Ethernet) si ce n'est pas déjà fait automatiquement.
6. **Installation des logiciels de base (`dietpi-software`)**
   - Cet outil se lance normalement tout seul après le premier paramétrage. S'il ne se lance pas automatiquement, tapez la commande `dietpi-software`.
   - Dans la liste des logiciels proposés, section « Desktop », choisissez **LXDE**. Valeur testée : LXDE est l'entrée n° 23, premier élément sélectionnable sous « Desktop » ; le numéro peut varier selon la version de DietPi. C'est ce bureau qui permettra ensuite d'afficher OBS et l'interface tactile de nomade.
   - Vous pouvez également installer ici des outils utiles comme `git`, si la liste vous le propose.
7. **Mise à jour du système**
   - Une fois le bureau installé, mettez le système à jour avant d'aller plus loin :

```bash
apt-get update && apt-get upgrade -y
```

8. **Récupération du dépôt nomade**
   - Installez `git` si nécessaire (`apt-get install -y git`), puis récupérez le dépôt :

```bash
git clone https://github.com/Thalyn-/nomade.git
cd nomade
```

9. **Installation d'OBS et des dépendances de nomade**
   - Le paquet OBS fourni par défaut sur cette architecture ne contient pas la Source Navigateur : le dépôt installe donc le paquet communautaire Pi-Apps qui l'inclut. Cette étape, ainsi que Python et les autres dépendances, est prise en charge par l'installation en une commande, ci-dessous.

Une fois ces neuf étapes réalisées, votre Raspberry Pi dispose d'un environnement graphique fonctionnel et du dépôt nomade en place.

## 4. Installer Nomade en une commande

Dans un terminal ouvert dans le dépôt :

```bash
sudo ./scripts/install_nomade.sh
```

Le script installe les outils système, Python/Tk, `ffmpeg`, `avahi-daemon`, `avahi-utils`, Mosquitto et OBS avec la Source Navigateur, puis crée l'environnement Python Nomade. Il lance ensuite PrimumInitium : fenêtre graphique si l'installation est lancée depuis LXDE, rapport de diagnostic dans le terminal sinon. Il ne désactive aucun service système.

L'installation ajoute aussi les outils Wi-Fi (`wpasupplicant`, `iw`, `rfkill`), Avahi et le clavier virtuel libre Onboard. PrimumInitium propose les réglages tactiles et attend une validation explicite avant de permettre de passer à Emissio. La correction du Wi-Fi et les autres changements système restent des actions explicites de l'assistant.

## 5. Premier lancement validé

Les essais rapportés sur une installation fraîche de DietPi ont validé `scripts/install_nomade.sh`, OBS installé par Pi-Apps avec la Source Navigateur et Larix en SRT sur un partage 5G à IP dynamique de type `10.x.x.x`. Le résultat peut varier selon les versions de DietPi, OBS et les téléphones.

À l'ouverture de PrimumInitium, OBS est lancé en mode préparation s'il ne l'est pas déjà. Avant d'attendre un changement dans OBS, vérifiez chaque élément de cette liste :

- [ ] OBS est ouvert et utilise la collection contenant la scène **Scene principale**.
- [ ] Les sources attendues (caméra USB, sources SRT et éléments visuels) ont été créées et ajoutées à la bonne scène. Importez le modèle avec `./scripts/installer_scenes_obs.sh` si besoin ; ce sont des modèles à adapter à la clé d'acquisition et au téléphone réellement utilisés.
- [ ] Dans OBS > Outils > Paramètres du serveur WebSocket, le serveur est activé, lié à `127.0.0.1`, sur le port `4455` ; le mot de passe correspond à `OBS_MDP`.
- [ ] Si vous testez SRT, Larix est lancé en mode émetteur (caller) et la Source Média OBS en mode écoute (listener). Pour des capteurs, SensorCast et le courtier MQTT doivent également être lancés/configurés.
- [ ] Le téléphone, la clé vidéo, le micro/casque et le réseau sont connectés si votre scène les utilise.

L'assistant graphique et son mode terminal se lancent avec `./scripts/primum_initium.sh` et `./scripts/primum_initium.sh --diagnostic`. Quand les prérequis essentiels sont validés, PrimumInitium ouvre Emissio pour choisir une plateforme et préparer le service OBS. Une proposition d'ouverture automatique au démarrage de LXDE est facultative et peut être retirée depuis le même bouton.

Emissio (`./scripts/emissio.py`) propose Twitch, Kick, YouTube, Facebook Live, Velora, Restream.io et une destination personnalisée. Il crée un **profil OBS par plateforme** (`Nomade - Twitch`, `Nomade - Kick`, etc.) en copiant les réglages vidéo/audio de `Nomade direct fixe` ; seule la destination et la clé diffèrent. Saisissez chaque clé une fois ; Emissio la recharge depuis le profil local lorsqu'on revient sur cette plateforme. Les adresses de serveur ne sont volontairement pas préremplies : consultez la documentation de la plateforme et saisissez le serveur actuel, qui peut dépendre de la région.

Les clés sont conservées en clair dans `service.json` du profil OBS local. Nomade sauvegarde l'ancien fichier et protège profils, clés et sauvegardes avec les droits `600`/`700`. Elles ne sont ni suivies par Git ni écrites dans les journaux. **Ne partagez pas une sauvegarde de la carte microSD** sans retirer au préalable les profils OBS et leurs clés. Pour lancer un direct natif, choisissez une plateforme dans Emissio : une seule plateforme à la fois est prise en charge nativement. Pour diffuser simultanément vers plusieurs plateformes, configurez **un seul flux sortant vers Restream.io**, qui assure ensuite la redistribution ; Nomade n'installe aucun greffon multi-RTMP non garanti sur ARM64.

Le test Emissio vérifie uniquement la joignabilité du serveur ; il ne démarre pas de diffusion. Pour SRT en émission, configurez et vérifiez la sortie correspondante dans OBS avant de lancer le direct ; Emissio ne peut pas appliquer cette sortie automatiquement.

Le bouton de PrimumInitium dédié à `OBS_MDP` aide à choisir puis enregistrer ce secret dans `config/nomade.secrets`. Saisissez ensuite le même mot de passe dans les paramètres obs-websocket d'OBS. Le fichier local n'est jamais suivi par Git ; le programme le protège avec les droits `600` et le charge pour les lancements ultérieurs.

Au premier lancement OBS, PrimumInitium propose de sauvegarder puis régler `~/.config/obs-studio/global.ini`, section `[General]`, clé `FirstRun=true`. Dans le code OBS 30.2.3, l'assistant automatique est lancé si `FirstRun` est faux, qu'aucune version précédente n'est enregistrée et qu'OBS n'est pas déjà actif ; la valeur vraie évite donc cette ouverture ([source OBSBasic](https://github.com/obsproject/obs-studio/blob/30.2.3/UI/window-basic-main.cpp)). Les autres paramètres OBS ne sont pas remplacés. OBS crée toutefois lui-même sa collection de base au démarrage ([création de collection](https://github.com/obsproject/obs-studio/blob/30.2.3/UI/window-basic-main-scene-collections.cpp)) : l'import du modèle Nomade s'effectue ensuite par l'étape guidée, via obs-websocket, après confirmation et sauvegarde des collections présentes. La création préalable d'une collection OBS complète et portable sans démarrer OBS n'est pas implémentée ; le premier affichage ne peut donc pas garantir que les scènes Nomade existent avant le lancement du processus OBS.

### Affichage des capteurs dans les scènes OBS

Le modèle utilise la source Texte FreeType2 native d'OBS (`text_ft2_source`) en mode **Lire depuis un fichier** (`from_file=true`, `text_file=...`). `capteurs_mqtt.py` lit et valide `/var/lib/nomade/capteurs.json`, puis écrit atomiquement de petits fichiers (`overlays/vitesse.txt`, `pulsations.txt`, `carte.txt`, `meteo.txt`). Des exemples traduits sont créés à l'installation et restent affichés en attendant les premières mesures. La source FreeType2 d'OBS 30.2.3 relit le fichier environ une fois par seconde ; cette vérification a été faite dans le code amont [`text-freetype2.c`](https://github.com/obsproject/obs-studio/blob/30.2.3/plugins/text-freetype2/text-freetype2.c), source `text_ft2_source`, propriétés `from_file` et `text_file`.

Cette option évite CEF, les restrictions `file://`/CORS et tout serveur HTTP ; aucun port supplémentaire n'est ouvert. Les fichiers sont atomiques et protégés en mode `600`, dans le répertoire de données local ; OBS et l'ingestion des capteurs doivent être exécutés sous le même compte. La présence réelle de cette source et son rendu avec le paquet Pi-Apps sur un Raspberry Pi 4B n'ont pas été testés ici.

### Droits administrateur pour les actions de l'assistant

PrimumInitium demande des droits avec `pkexec` uniquement après confirmation pour écrire la configuration Wi-Fi, relancer le réseau, installer des paquets ou installer la surveillance facultative. Un agent PolicyKit graphique doit être actif dans LXDE pour afficher la demande d'autorisation. Si l'interface n'en dispose pas, ne lancez pas toute l'interface en administrateur : utilisez les commandes de secours de la section réseau dans un terminal avec `sudo`, puis relancez le diagnostic. L'écriture d'informations locales dans le dépôt se fait, elle, avec les droits de l'utilisateur.

Les messages VAAPI « Failed to initialize display » ou « H264 encoding not supported » affichés dans la console d'OBS sont informatifs et normaux sur Raspberry Pi 4 : cette machine ne fournit pas VAAPI.

## 6. Dépannage express

### Connexion obs-websocket refusée

Vérifiez qu'OBS est ouvert, que son serveur WebSocket est activé, qu'il écoute sur **`127.0.0.1`**, au port **`4455`**, et que le mot de passe est exactement celui de `OBS_MDP`. Relancez ensuite `./scripts/primum_initium.sh --diagnostic`. N'exposez jamais ce serveur sur `0.0.0.0` ou le réseau du téléphone.

### Wi-Fi instable

Ce correctif est **conditionnel** : ne désactivez `dietpi-wifi-monitor` que si vous constatez réellement une boucle de déconnexions. Confirmez l'action dans PrimumInitium ou exécutez explicitement `sudo systemctl disable --now dietpi-wifi-monitor.service`.

La surveillance automatique Nomade est une autre option, distincte et désactivée par défaut. Installez-la ou retirez-la depuis le bouton correspondant de PrimumInitium ; en terminal, après avoir vérifié le script :

```bash
sudo ./scripts/installer_watchdog_wifi.sh install
sudo ./scripts/installer_watchdog_wifi.sh uninstall
```

Le minuteur réessaie le Wi-Fi toutes les minutes. Il peut interrompre momentanément les connexions : ne l'activez qu'après confirmation.

Si le Wi-Fi ne démarre toujours pas, vérifiez que `/etc/wpa_supplicant/wpa_supplicant.conf` suit cette structure (remplacez les deux valeurs d'exemple sur le Raspberry, jamais dans ce dépôt) :

```ini
country=FR
ctrl_interface=DIR=/run/wpa_supplicant GROUP=netdev
update_config=1
network={
    ssid="NOM_DU_RESEAU"
    psk="MOT_DE_PASSE"
    key_mgmt=WPA-PSK
}
```

Ne placez pas `ieee80211d=1` dans la section globale ; gardez les guillemets autour de `psk`, sans espace avant `psk=`. Si `ifupdown` gère déjà le pilote `brcmfmac` avec `wpa-conf` dans `/etc/network/interfaces.d/wlan0.conf`, ne lancez pas en parallèle un service `wpa_supplicant-wlan0.service` créé manuellement.

Avant de modifier cette configuration système, faites une copie de sauvegarde, puis utilisez `sudoedit` plutôt que de remplacer le fichier à l'aveugle. Dans les essais rapportés, des espaces mal placés, une clé sans guillemets ou certains caractères accentués mal enregistrés empêchaient la connexion : vérifiez le format et l'encodage si le Wi-Fi ne démarre pas. Ne copiez jamais votre vraie clé dans le dépôt.

### SRT ne reçoit rien

SRT transporte la vidéo en **UDP** ; obs-websocket contrôle OBS en **TCP** sur `127.0.0.1:4455`. Dans OBS, utilisez `srt://:9001?mode=listener` (sans IP avant les deux-points) ; dans Larix, utilisez `srt://<ADRESSE_DU_RASPBERRY>:9001?mode=caller`. Ne réutilisez jamais un port déjà occupé. Vérifiez l'aperçu de la source OBS et désactivez l'aperçu du téléphone si celui-ci chauffe.

Une adresse 5G dynamique n'empêche pas SRT de fonctionner. Utilisez l'adresse `.local` ou l'IP courante affichée par l'assistant ; privilégiez l'IP si le téléphone ne résout pas mDNS.

## 7. Annexes avancées

## Architecture retenue

- **Préparation OBS** : `scripts/lancer_obs_preparation.sh`
  - interface OBS complète ;
  - profil de préparation dédié ;
  - même surcharge `MESA_GL_VERSION_OVERRIDE=3.3`.
- **Direct OBS** : `scripts/lancer_obs_direct.sh`
  - profil de direct fixe dédié ;
  - options OBS natives réellement disponibles sur OBS 30.2.x : `--profile`, `--collection`, `--scene`, `--minimize-to-tray`, `--disable-missing-files-check`, `--startstreaming` en option ;
  - **pas de vrai mode headless** : OBS Studio ne fournit pas ici de mode sans interface adapté à ce besoin. Le meilleur compromis natif reste donc un démarrage réduit, avec profil figé et fenêtre réduite.
- **Interface locale** : `scripts/lancer_nomade.sh` puis `scripts/interface_nomade.py`
  - démarre l'interface Python ;
  - démarre aussi OBS direct allégé si OBS n'est pas déjà lancé ;
  - attend la disponibilité d'`obs-websocket` sur `127.0.0.1`.
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
- `NOMADE_OBS_AUTOSTART_DIFFUSION=1` : ajoute `--startstreaming` si l'on veut démarrer la diffusion dès l'ouverture d'OBS

### Limite connue sur le « headless »

Cette version ne prétend pas fournir un « OBS headless » complet, car OBS Studio n'offre pas ici un mode sans interface réellement adapté à la préparation puis au direct. Le dépôt fournit donc :

- **OBS complet** pour la préparation ;
- **OBS allégé au maximum avec les options natives disponibles** pour le direct.

## Sécurité réseau et `obs-websocket`

- Le contrôle OBS doit rester **local au Raspberry**.
- L'interface utilise `127.0.0.1` par défaut et refuse les hôtes distants par sécurité.
- Il ne faut **pas** exposer `obs-websocket` sur `0.0.0.0`, sur l'interface 5G, ni sur une interface de tethering.
- Le transport des capteurs du téléphone ne doit pas être confondu avec le contrôle OBS : ce sont deux chemins distincts.

### Réseau mobile, DHCP et mDNS

Le partage de connexion 5G peut fournir une passerelle et une adresse qui changent (par exemple une adresse en `10.x.x.x`). Laissez le Raspberry en **DHCP pur** ; ne configurez pas d'adresse IP statique dessus. Si le téléphone le permet, réservez l'adresse du Raspberry dans « Appareils connectés ». Sur un Xiaomi 11T sous HyperOS cette option peut manquer ; après redémarrage, le même appareil conserve souvent son adresse grâce à son adresse MAC.

Pour éviter de saisir une adresse changeante, installez/activez `avahi-daemon` (installé par Nomade) et essayez le nom réel affiché par l'assistant, par exemple `srt://dietpi.local:9001?mode=caller`. PrimumInitium affiche côte à côte cette adresse et `srt://<IP-du-Raspberry>:9001?mode=caller`, avec des boutons de copie. C'est mDNS via Avahi, sans Bonjour. Certains téléphones, dont des configurations Xiaomi/HyperOS, ne résolvent pas toujours `.local` : utilisez alors l'adresse IP courante affichée par l'assistant. L'IP attribuée par DHCP peut changer après un redémarrage.

Sur Xiaomi 11T/HyperOS, l'option de réservation se trouve, lorsqu'elle existe, dans **Paramètres > Point d'accès mobile > Appareils connectés > Raspberry Pi > IP fixe/réservée**.

### Wi-Fi instable (correctif conditionnel)

Une boucle CONNECTED/DISCONNECTED peut venir de `dietpi-wifi-monitor` et de faux positifs de latence. Désactivez ce service seulement si vous observez cette instabilité, avec l'accord explicite demandé par PrimumInitium. Le modèle de `wpa_supplicant.conf` et les précautions `brcmfmac` sont décrits dans le dépannage express.

Le pilote `brcmfmac` peut aussi entrer en conflit si `ifupdown` et systemd gèrent la même interface. Si `ifupdown` utilise `wpa-conf` dans `/etc/network/interfaces.d/wlan0.conf`, désactivez seulement le service `wpa_supplicant-wlan0.service` créé manuellement et après vérification de la configuration.

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

- la langue de l'interface ;
- les adresses et ports OBS/MQTT ;
- l'interface réseau capteurs (`bnep0` par défaut) et les informations Bluetooth utiles ;
- les scènes, profils et sources OBS ;
- le service de chat multicanal et la source Navigateur OBS associée ;
- quelques préférences d'affichage et fonctions activables ;
- les emplacements du dépôt, du venv Python, des données et des journaux.

### Sources vidéo interchangeables et groupes exclusifs

La configuration accepte désormais une liste `[[video_sources]]` :

- `id` : identifiant stable côté Nomade ;
- `label` : libellé affiché dans l'interface tactile ;
- `type` : `capture_usb`, `srt` ou `webcam` ;
- `obs_source_name` : nom exact de la source dans OBS ;
- `group` : groupe fonctionnel exclusif ;
- `enabled_by_default` : état initial ;
- `srt_port` : optionnel (informatif) pour les sources `srt`.

Les sources d'un même `group` sont mutuellement exclusives dans l'interface : sélectionner une source désactive automatiquement les autres du même groupe dans OBS.

Exemple typique :

- groupe `camera_principale` : G7 principal, G7 secours, Xiaomi grand angle ;
- groupe `vignette_visage` : Xiaomi selfie.

### Sources SRT Xiaomi via OBS (sans relais Python)

Nomade ne décode pas lui-même les flux SRT : OBS reste le moteur vidéo unique.

Pour une source SRT (ex. Larix Broadcaster sur Xiaomi), configurez côté OBS une **Source Média** en écoute :

`srt://:9001?mode=listener`

Le flux arrive en **UDP**, port `9001`. Côté téléphone, Larix Broadcaster émet en mode caller vers l'une des deux adresses copiables du bilan : `srt://<nom-hôte>.local:9001?mode=caller` ou `srt://<IP-courante>:9001?mode=caller`. Si le nom ne fonctionne pas sur le téléphone, utilisez l'adresse avec les chiffres. Ne codez pas en dur une IP dynamique ; n'utilisez pas le port s'il est déjà pris.

Le contrôle `obs-websocket` est différent : il reste en **TCP**, sur `127.0.0.1:4455`, et ne doit jamais être exposé sur le réseau.

Larix est plus tolérant aux réseaux instables mais peut chauffer davantage le téléphone. Privilégiez l'encodage matériel et coupez l'aperçu de l'écran. IP Webcam est une option plus simple et généralement moins exigeante ; NDI HX Camera reste une option non recommandée par défaut en raison de son SDK propriétaire.

### Presets (préréglages)

La liste `[[presets]]` permet d'appliquer en un clic plusieurs actions :

- `id`, `label`
- `activer` : identifiants à activer
- `desactiver` : identifiants à désactiver

Ces identifiants peuvent cibler les overlays existants (`selfie`, `carte`, `vitesse`, `pulsations`, `meteo`, `heure`, `chat_multicanal`) et les `id` de `video_sources`.

Exemples inclus :

- `sans_reperes` : masque `carte` et `vitesse`
- `trajet` : affiche `carte` et `vitesse`

Les préréglages pilotent uniquement des scènes et sources **existantes** : ils ne créent pas de scène ni de source OBS. Les noms de scènes et de sources sont configurables dans `config/nomade.toml` puis, pour les adaptations locales, dans `config/nomade.local.toml`.

### À propos de `/opt/nomade-venv`

Le chemin par défaut du venv reste `/opt/nomade-venv`. C'est un **choix d'organisation** classique pour une application tierce sous Debian/DietPi, pas un gain de performances. Le dépôt évite ainsi de mélanger l'environnement Python de nomade avec le système.

Si une installation existante a déjà été préparée sous `/root/nomade`, elle peut être conservée en surchargeant localement :

```toml
[paths]
python_venv = "/root/nomade/myvenv"
```

Cette surcharge permet une migration progressive sans casser l'installation actuelle.

## Interface locale : Tkinter conservé

L'interface principale reste **Python/Tkinter**. Ce choix est volontaire pour un Raspberry Pi 4B en direct :

- pas de serveur web supplémentaire à maintenir ;
- pas de navigateur obligatoire à ouvrir pendant le live ;
- moins de RAM et de moteur de rendu qu'une page Firefox/Chromium dédiée.

Une interface web locale pourrait être étudiée plus tard comme extension facultative, mais elle n'est **pas** implémentée dans cette évolution.

PrimumInitium peut aussi activer le simple clic dans PCManFM, après confirmation. La création d'un affichage virtuel n'est pas automatisée : le bon réglage dépend de l'écran tactile, du pilote graphique et de la résolution utilisée.

## Installation détaillée (DietPi Bookworm)

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
  scripts/lancer_capteurs_mqtt.sh \
  scripts/primum_initium.sh \
  scripts/emissio.py \
  scripts/installer_watchdog_wifi.sh \
  scripts/watchdog_wifi.sh \
  scripts/installer_scenes_obs.sh
sudo ./scripts/install_nomade.sh
```

Le script installe notamment :

- Python et Tk, ainsi que les outils Wi-Fi (`wpasupplicant`, `iw`, `rfkill`, `ifupdown`) ;
- Onboard, requis pour le clavier virtuel tactile ;
- `ffmpeg`, `avahi-daemon` et `avahi-utils` ;
- les dépendances Python du dépôt ;
- `mosquitto` et `mosquitto-clients` pour un courtier MQTT local ;
- OBS Studio avec Source Navigateur via le paquet communautaire Pi-Apps ;
- les répertoires de données et journaux définis dans `config/nomade.toml`.

Onboard est installé par le script ; les ajustements PCManFM et les autres changements tactiles nécessitent une confirmation dans PrimumInitium.

## Installation d'OBS avec Source Navigateur

Le paquet officiel `apt install obs-studio` fourni sur Debian Bookworm ARM64 n'inclut pas la Source Navigateur sur cette cible. Le dépôt conserve donc `scripts/installer_obs_navigateur.sh`, qui installe à la place un paquet communautaire (Pi-Apps) incluant cette fonctionnalité.

Ce choix est volontaire :

- **on ne supprime pas** la Source Navigateur ;
- on garde l'accélération `MESA_GL_VERSION_OVERRIDE=3.3` nécessaire au Raspberry Pi 4 ;
- on évite de faire croire qu'un paquet Debian standard suffirait à reproduire le même comportement.

## Interface locale de pilotage

Exemple minimal :

```bash
export OBS_MDP='votre_mot_de_passe'
./scripts/lancer_nomade.sh
```

Comportement :

- si aucun processus `obs` n'est déjà lancé, le script démarre `scripts/lancer_obs_direct.sh` ;
- l'interface attend ensuite `obs-websocket` pendant `30` secondes par défaut ;
- l'hôte OBS reste fixé à `127.0.0.1` via le script de lancement.

Variables utiles :

- `OBS_MDP` : mot de passe `obs-websocket`
- `NOMADE_LANGUE=fr` ou `NOMADE_LANGUE=en`

Pour diagnostiquer la configuration réellement chargée :

```bash
python3 scripts/nomade_config.py --diagnostic
```

## Internationalisation

Les textes visibles de l'interface sont externalisés dans :

- `locales/fr.json` (par défaut)
- `locales/en.json` (repli anglais minimal)

Pour choisir la langue :

```bash
NOMADE_LANGUE=en ./scripts/lancer_nomade.sh
```

Les **noms de scènes**, **noms de sources** et **messages d'erreur techniques détaillés** restent configurables et ne sont pas traduits automatiquement.

Le français reste la langue par défaut des textes destinés à l'utilisateur.

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

Le fichier `examples/nomade-scenes.json` décrit le modèle utilisé par `./scripts/installer_scenes_obs.sh`. OBS doit être ouvert avec son WebSocket actif sur la boucle locale ; exportez `OBS_MDP` avant l'import. Le script sauvegarde les collections OBS présentes, demande confirmation, crée les scènes/sources absentes et ne remplace aucun nom existant. Les entrées caméra, overlays et téléphone sont des modèles à adapter à votre matériel ; pour plusieurs réceptions SRT simultanées, attribuez un port distinct à chaque source et mettez à jour `srt_port`.

## Capteurs via MQTT sur liaison Bluetooth

### Principe retenu

Le dépôt privilégie une ingestion capteurs **MQTT locale** pour éviter autant que possible :

- les WebSocket venant du téléphone ;
- le Wi-Fi du hotspot/tethering ;
- l'USB tethering.

Le cas visé est une liaison Bluetooth indépendante, par exemple :

- **Bluetooth PAN / BNEP** entre téléphone et Raspberry ;
- ou un autre transport Bluetooth réellement compatible avec SensorCast et un courtier MQTT accessible côté Raspberry.

### Important : ce qui n'est pas supposé automatiquement

Cette version **ne prétend pas** que SensorCast, Bluetooth PAN, BNEP ou Mosquitto seraient configurés automatiquement par le dépôt. Il faut préparer explicitement :

1. le jumelage Bluetooth ;
2. le profil réseau Bluetooth réellement utilisé ;
3. l'adresse IP de l'interface Bluetooth côté Raspberry ;
4. la configuration de SensorCast pour publier en MQTT vers ce courtier local.

### Lancement de l'ingestion

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

### Garantie fonctionnelle de l'ingestion

Le service :

- accepte des messages JSON ;
- vérifie au minimum que la charge utile est un objet JSON, et que `position`, `reseau` et `meteo` sont des objets s'ils existent ;
- écrit `/var/lib/nomade/capteurs.json` de façon atomique ;
- ignore un message invalide sans arrêter le processus ;
- tente de se reconnecter automatiquement si la liaison MQTT tombe.

### Exemple de configuration Mosquitto

Le dépôt fournit un exemple minimal dans `examples/mosquitto-bluetooth.conf.example`.

Principe recommandé :

- écouter **uniquement** sur l'adresse IP de l'interface Bluetooth (par exemple `bnep0`) ;
- ne pas écouter sur l'interface 5G ni sur toutes les interfaces.

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
- l'interface Tkinter peut activer/désactiver la source OBS correspondante ;
- si `sync_chat_browser_source = true`, Nomade met à jour l'URL de la source Navigateur au démarrage ;
- une URL distante reste une dépendance réseau supplémentaire : vérifiez toujours la confiance accordée au service tiers ;
- une panne du service de chat ne doit pas empêcher le contrôle local OBS ni l'ingestion MQTT/Bluetooth.

## Diffusion multi-plateforme

Emissio enregistre les clés et serveurs dans un profil OBS local par plateforme. Chaque profil est créé depuis `Nomade direct fixe` pour conserver les mêmes réglages vidéo/audio. La sélection de plateforme fournit le profil à OBS sans ressaisie de la clé déjà enregistrée.

La section `[streaming]` du TOML reste une configuration de compatibilité, sans secrets. À retenir :

- le direct natif diffuse vers **une plateforme à la fois** ;
- Restream.io permet plusieurs plateformes avec un seul flux sortant depuis le Raspberry ;
- les clés sont en clair dans les profils OBS locaux protégés (droits `600`), jamais dans Git ou les journaux ;
- ne partagez pas de sauvegarde de carte microSD contenant ces profils.

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

- **L'interface dit que la connexion OBS est impossible**
  Vérifier que `obs-websocket` est activé dans OBS, avec mot de passe, sur `127.0.0.1:4455`.

- **OBS s'ouvre mais reste lourd**
  C'est une limite d'OBS Studio : il n'existe pas ici de mode headless complet pour le direct. Utiliser `scripts/lancer_obs_direct.sh` avec un profil fixe, déjà préparé.

- **Les capteurs n'arrivent pas**
  Vérifier d'abord la liaison Bluetooth/PAN, puis le courtier MQTT local, puis le sujet réellement publié par SensorCast.

- **Je veux vérifier ma configuration sans lancer le direct**
  Exécuter `python3 scripts/nomade_config.py --diagnostic` puis corriger `config/nomade.local.toml` si nécessaire.

- **Le direct 5G se coupe quand SensorCast tourne**
  Revenir à une topologie où MQTT ne passe pas par le tethering Wi-Fi ou USB, mais par une liaison Bluetooth réellement séparée.

## Limites connues

- pas de vrai mode headless OBS dans ce dépôt ;
- la configuration exacte de SensorCast et du profil réseau Bluetooth dépend du matériel et n'est donc pas imposée silencieusement ;
- la récupération directe des pulsations de certains objets connectés peut rester limitée selon leurs protocoles ;
- l'installation OBS repose toujours sur un paquet communautaire Pi-Apps pour conserver la Source Navigateur ;
- le multistream complet reste volontairement reporté à une évolution séparée.

## Feuille de route

- étudier une image DietPi `.img` prête à graver, seulement après stabilisation et validation matérielle ;
- enrichir les scènes OBS par défaut sans écraser les collections personnelles ;
- étudier un assistant graphique plus complet et des réglages pour limiter la chauffe et préserver la batterie du téléphone.
