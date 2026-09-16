# KANBAN — stormshield

Journal daté du repo. Le *comment* générique est dans `README.md`, les conventions
dans `CLAUDE.md` ; ici, l'avancement, les décisions et les pièges rencontrés.
Tenu à la main.

## Décisions actées

- (2026-09-16) Python plutôt qu'Ansible : le besoin est de l'injection de lots
  (utilisateurs, blacklists), pas de la convergence de configuration.
- (2026-09-16) Feuille sous `~/claude`, remote `githubf-tfr/stormshield`.

## À faire

- Spec de l'injection d'utilisateurs : format du fichier d'entrée, champs obligatoires,
  comportement sur doublon.
- Spec de l'injection de blacklists : granularité (objet réseau vs groupe URL), purge ou
  ajout seul.
- Choix du mode d'accès : SDK `stormshield.sns.sslclient` ou API REST directe.

## En cours

_(rien)_

## Terminé

### Amorçage (2026-09-16)

- Repo créé, documentation initiale (`README.md`, `CLAUDE.md`, ce journal).

## Pièges rencontrés

_(vide)_
