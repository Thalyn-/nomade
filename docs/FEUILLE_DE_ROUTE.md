# Feuille de route Nomade (Raspberry Pi)

## Vision

Nomade vise une solution **nomade, tactile, guidée** pour lancer et piloter un direct IRL sur Raspberry Pi, avec un minimum de friction pour les créateurs ne maîtrisant pas l’administration système et réseau.

---

## Positionnement du projet

Nomade se concentre d’abord sur :

1. la **fiabilité du direct** (réseau, flux, OBS, scènes) ;
2. le **pilotage local simple** (écran tactile, gros boutons, parcours guidé) ;
3. des **surcouches utiles** (vitesse, météo, heure, capteurs).

Nomade ne cherche pas, dans un premier temps, à remplacer entièrement les outils natifs des plateformes pour :
- la modération avancée ;
- les sondages/raids/points de chaîne ;
- les fonctions communautaires complexes.

---

## Principes produit

1. **Mode guidé pas à pas** par défaut.
2. **Mode avancé** disponible sans compliquer le mode guidé.
3. **Aucun secret dans Git** (clés, mots de passe, jetons).
4. **Internationalisation** : textes centralisés dans `locales/fr.json` et `locales/en.json`.
5. **Résilience réseau** : fonctionnement prévu en box fixe comme en partage de connexion mobile.
6. **Sobriété technique** : priorité à la stabilité et à la charge raisonnable sur Raspberry Pi.

---

## Périmètre MVP (objectif court terme)

### 1) Base fiable d’installation et démarrage
- Installation reproductible sur DietPi.
- Assistant de premier démarrage robuste.
- Diagnostic lisible (réseau, OBS, WebSocket, SRT, périphériques vidéo/audio).

### 2) OBS prêt à l’emploi
- Import automatique du modèle de scènes (sans écrasement brutal).
- Gestion tolérante des différences de types de sources OBS selon versions.
- Un port SRT par source pour éviter les conflits.

### 3) Pilotage tactile minimal
- Changement de scène.
- Activation/désactivation de sources clés.
- Retour visuel clair : « prêt / à corriger ».

### 4) Diffusion multi-plateforme simple
- Profils OBS par plateforme (un profil = un service).
- Sélection rapide du profil avant direct.
- Option Restream pour la diffusion simultanée.

---

## Hors MVP (reporté)

- Modération complète multicanale directement dans Nomade.
- Points de chaîne, mini-jeux, tirages au sort.
- Gestion automatisée des raids multi-plateformes.
- Application mobile dédiée Nomade.

---

## Plan de versions

## v0.2 — Base fiable
Objectif : installation + lancement direct fiables.

- Stabiliser WebSocket OBS et messages d’erreur.
- Stabiliser import scènes/sources.
- Sécuriser la gestion des secrets.
- Clarifier README pour débutants.

## v0.3 — Pilotage tactile
Objectif : contrôle simple en situation réelle.

- Parcours guidé plus intuitif.
- Contrôles essentiels en gros boutons.
- Bilan lisible et actionnable.

## v0.4 — Capteurs exploitables
Objectif : surcouches réellement utiles.

- Chaîne capteurs stable.
- Données propres pour overlays.
- Affichage cartographique selon solution retenue (ouverte, légère, maintenable).

## v0.5 — Confort opérateur
Objectif : robustesse en mobilité.

- Reprise après coupure réseau.
- Profils qualité (éco/standard/qualité).
- Meilleure tolérance aux erreurs utilisateur.

## v1.0 — Prêt production créateur
Objectif : solution publiable et documentée.

- Parcours validé sur installation vierge.
- Documentation complète (texte + visuels).
- Validation sur sessions réelles prolongées.

---

## Méthode de décision technique

Avant d’ajouter une fonction, vérifier :

1. Apporte-t-elle une valeur directe à l’utilisateur final ?
2. Son coût CPU/RAM est-il acceptable sur Raspberry Pi ?
3. Son ajout risque-t-il de fragiliser le direct ?
4. Existe-t-il une alternative plus simple et stable ?
5. Dépend-elle d’API externes trop instables ?

Si plusieurs réponses sont défavorables, la fonction est reportée hors MVP.

---

## Priorités actuelles (mise à jour continue)

### En cours
- Fiabilisation WebSocket / import OBS / diagnostic.

### Prochaines
- Simplification du parcours guidé.
- Profils plateforme et sélection avant direct.
- Amélioration des scènes modèles et overlays capteurs.

### Plus tard
- Fonctions communautaires avancées (modération étendue, interactions complexes).

---

## Cap matériel actuel

Cible principale : **Raspberry Pi**.

Une déclinaison mini-PC (ex. Intel N100) pourra être étudiée plus tard, après stabilisation de la version Raspberry Pi.
