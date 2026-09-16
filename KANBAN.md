# KANBAN — stormshield

Journal daté du repo. Le *comment* générique est dans `README.md`, les conventions
dans `CLAUDE.md` ; ici, l'avancement, les décisions et les pièges rencontrés.
Tenu à la main.

## Décisions actées

- (2026-09-16) Python plutôt qu'Ansible : le besoin est de l'injection de lots
  (utilisateurs, blacklists), pas de la convergence de configuration.
- (2026-09-16) Feuille sous `~/claude`, remote `githubf-tfr/stormshield`.

### Brainstorming v1 (2026-09-16)

- Périmètre v1 : utilisateurs LDAP seuls. Blacklists renvoyées à une v2.
- Interface graphique tkinter, fenêtre unique, livrée en `.exe` — pas de CLI.
  L'opérateur visé n'a pas de terminal.
- SDK officiel `stormshield.sns.sslclient` derrière un `Protocol` injectable.
  L'authentification `nsrpc` ne se réimplémente pas en REST à la main.
- Entrée CSV `identifiant;nom;prenom;groupes`. Pas de colonne mail : `USER CREATE`
  ne la prend pas.
- Ajout seul : jamais de suppression, jamais de modification d'un compte existant.
  Les orphelins sont signalés, pas touchés.
- Mots de passe générés à la création effective, politique pré-remplie depuis
  `CONFIG PASSWDPOLICY SHOW`, restitués dans un CSV choisi par l'opérateur.
- `CONFIG LDAP INITIALIZE` n'est atteignable que si aucun annuaire ne répond —
  la commande écrase, le chemin doit être fermé quand il y a quelque chose à écraser.
- Contournement de la vérification du certificat : case décochée par défaut,
  jamais câblé en dur.
- `.exe` construit par GitHub Actions sur `windows-latest` (PyInstaller) : le poste
  de développement est sous Linux.

## À faire

- Plan d'implémentation de la v1, à partir de
  `docs/superpowers/specs/2026-09-16-injection-utilisateurs-design.md`.
- Spec de l'injection de blacklists : granularité (objet réseau vs groupe URL), purge ou
  ajout seul.

## Points à lever dès qu'un boîtier est joignable

- Longueur et caractères autorisés pour le `uid`, liste des `uid` interdits.
- Différence entre `USER GROUP CREATE` et `USER GROUP NEW`.
- Limite de sessions simultanées de l'API serverd (`SRV_RET_AUTHLIMIT`).
- L'adaptateur SDK est écrit contre la documentation, prouvé par rien jusque-là.

## En cours

_(rien)_

## Terminé

### Amorçage (2026-09-16)

- Repo créé, documentation initiale (`README.md`, `CLAUDE.md`, ce journal).

## Pièges rencontrés

_(vide)_
