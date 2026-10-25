# Journal des versions

Ce projet suit une logique de versionnement simple : `MAJEUR.MINEUR.CORRECTIF`.

- **MAJEUR** : changement important, potentiellement non compatible.
- **MINEUR** : nouvelles fonctionnalités compatibles.
- **CORRECTIF** : correction de bogues, sans changement majeur d’usage.

---

## [0.2.0] - 2026-10-25

### Ajouté
- Assistant de démarrage guidé (diagnostic réseau, OBS, SRT, périphériques).
- Base d’internationalisation utilisateur (`fr` et `en`).
- Feuille de route produit : `docs/FEUILLE_DE_ROUTE.md`.

### Modifié
- Parcours d’installation et de vérification orienté débutant.
- Amélioration des messages de diagnostic et de dépannage.

### Corrigé
- Stabilisation de la connexion WebSocket OBS (cas observés sur Raspberry Pi / OBS 30.2.x).
- Ajustements liés aux ports SRT pour réduire les conflits.
- Clarifications de la documentation réseau (Wi-Fi, partage mobile, mDNS/IP).

---

## [0.1.0] - 2026-10-01

### Ajouté
- Base du projet Nomade sur Raspberry Pi.
- Scripts initiaux d’installation et de lancement.
- Première interface locale de pilotage.
