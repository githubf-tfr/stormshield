# CLAUDE.md — stormshield

**Feuille.** Aucun projet en dessous : ne lis pas le `README.md` au démarrage.

Outillage Python d'injection en lot sur firewall Stormshield SNS : utilisateurs de la base
LDAP interne, blacklists (groupes d'objets réseau/URL), depuis des fichiers plats.

## Invariants

- **Français dans le code** — noms, docstrings, commentaires, messages.
- **Idempotence** : rejouer une injection sur un firewall déjà à jour ne change rien.
  L'état se lit sur le boîtier, jamais dans un fichier d'état local.
- **Aucun identifiant dans le repo** — ni mot de passe, ni clé, ni `.env` commité.
  Fournis à l'exécution ; que des `*.example` suivis.
- **Écriture sur le firewall toujours explicite** : un mode « simulation » par défaut, et
  l'application effective derrière un drapeau. Un lot mal formé ne doit pas partir seul.

## Tests

- Unitaires : `pytest`, aucun firewall requis. Tout appel réseau passe par une dépendance
  injectable.
- Ce qui exige un boîtier joignable porte le marqueur `firewall`, exclu par défaut.
- `tests/test_fenetre.py` construit la vraie fenêtre : exige `python3-tk` **et** un
  affichage. Lancer la suite sous **`xvfb-run -a pytest`** ; sans affichage ce fichier se
  saute, `pytest` nu reste vert et ne prouve donc rien de l'interface.
- Analyse statique avant tout commit : `ruff check .` puis `mypy`.
