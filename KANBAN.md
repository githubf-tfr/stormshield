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

- **Exécuter `docs/recette/2026-09-16-cahier-recette-v1.md` dès qu'un boîtier est
  joignable.** 121 cas, dont 22 jouables sans boîtier sur un poste Windows et le `.exe` de
  la release. C'est la seule couverture de `fenetre.py` et le seul moyen de confirmer les
  hypothèses de `boitier_sdk.py` (section F du cahier).
- Poser le tag `v1.0.0` pour déclencher la première construction du `.exe`. Le workflow
  `exe.yml` n'a jamais tourné : aucun runner ne l'a validé avant ce tag.
- Spec de l'injection de blacklists : granularité (objet réseau vs groupe URL), purge ou
  ajout seul.

## Points à lever dès qu'un boîtier est joignable

Tous sont portés par le cahier de recette, avec le cas qui les tranche.

- Longueur et caractères autorisés pour le `uid`, liste des `uid` interdits (cas 58).
- Différence entre `USER GROUP CREATE` et `USER GROUP NEW`. `NEW` n'est utilisée nulle part.
- Limite de sessions simultanées de l'API serverd (`SRV_RET_AUTHLIMIT`) — cas 41.
- L'adaptateur SDK est écrit contre la documentation, prouvé par rien jusque-là.
- **Forme exacte du `data` rendu par `USER LIST`, `USER GROUP LIST`, `CONFIG LDAP LIST` et
  `CONFIG PASSWDPOLICY SHOW`** : l'aplatissement de `boitier_sdk._lignes` /
  `_section_unique` est une hypothèse, et les clés de champ (`name`, `domain`) en sont une
  autre. Cas 35, 36, 37. Une clé fausse fait voir le boîtier comme vierge — le défaut le
  plus coûteux qui reste.
- Table de traduction de `MinSetOfChars` (`None`→1, `AlphaNum`→2, `AlphaSpecial`→3) : tout
  le plancher de politique affiché et vérifié en dépend. Cas 31.
- `CONFIG LDAP LIST` liste aussi les annuaires **externes**, qu'aucun filtre ne distingue.
  Cas 39.

## En cours

_(rien)_

## Terminé

### Arrêt d'un lot en cours (2026-09-17)

`feat/arret-du-lot`. Un bouton *Arrêter* à côté de *Lancer* remplace la seule sortie qui
existait — fermer la fenêtre, qui tue le fil n'importe où, y compris entre `USER CREATE`
et `USER PASSWORD`.

- L'arrêt est consulté **entre deux comptes et entre deux groupes**, jamais au milieu de
  l'un d'eux : le compte entamé va jusqu'à son terme, rattachements compris. C'est ce qui
  distingue ce bouton de la fermeture qu'il remplace.
- `MotifArret.OPERATEUR` est une troisième fin, avec son bilan propre : comptes créés,
  comptes non touchés, et que relancer est sans danger. `Rapport.comptes_prevus` fige ce
  que le plan prévoyait, sans quoi le second chiffre n'existerait pas.
- Un `threading.Event` (`presentation.DemandeArret`) porte l'ordre du fil de l'interface
  au fil d'exécution : seul objet partagé entre les deux, et le seul message à circuler
  dans ce sens. Le garde de structure de `test_presentation` refuse toujours la version
  qui prendrait cet objet sur `self`.
- Le bouton agit aussi en simulation, dont le seul point d'arrêt est la fin de la lecture.
- **296 tests**, `ruff` et `mypy` verts, aucun `# type: ignore`. Spécification amendée,
  cahier de recette porté à 121 cas (section Q).

### Injection d'utilisateurs v1 (2026-09-16)

Plan d'implémentation de la v1 exécuté en douze tâches, à partir de
`docs/superpowers/specs/2026-09-16-injection-utilisateurs-design.md`.

Modules livrés, du plus pur au plus impur :

| Module | Rôle |
|---|---|
| `modele` | Structures partagées, aucune logique |
| `lecture` | CSV → utilisateurs valides + rejets. Pur |
| `motdepasse` | Génération par `secrets`, violations, proposition. Pur |
| `plan` | État lu + lignes valides → `Plan`. Pur |
| `boitier` | `Protocol` du firewall, et les trois exceptions qui séparent un refus de commande, une liaison perdue et ce qu'aucune reconnexion ne résout |
| `boitier_memoire` | Double de test, seul « boîtier » que les tests connaissent |
| `boitier_sdk` | Seul module à importer `stormshield.sns.sslclient` |
| `execution` | Lecture d'état, application du plan, reconnexions, émission d'événements |
| `sortie` | CSV de restitution des mots de passe |
| `presentation` | Toute la logique de l'interface, sans un seul widget. N'importe jamais `tkinter` |
| `fenetre` | Seul module à importer `tkinter`, et le seul qu'aucun test n'importe |
| `__main__` | Point d'entrée, cible de PyInstaller, filet de démarrage |

- **273 tests** passent (marqueur `firewall` exclu), `ruff` et `mypy` verts, aucun
  `# type: ignore`.
- Workflows : `qualite.yml` (`ruff`, `mypy`, `pytest` en matrice 3.11 / 3.12) et `exe.yml`
  (PyInstaller `--onefile --windowed` sur `windows-latest`, release sur tag `v*`).
- `README.md` refondu pour l'opérateur : format du CSV, simulation, mots de passe,
  certificat, et l'avertissement SmartScreen que le binaire non signé provoque.
- Cahier de recette écrit : `docs/recette/2026-09-16-cahier-recette-v1.md`.

### Revue finale de branche (2026-09-16)

Revue finale de `feat/injection-utilisateurs` avant fusion : verdict favorable sous
réserve de quatre points, tous traités dans la foulée — une garantie de test manquante,
deux trous de couverture mineurs, deux oublis de documentation.

Le plus sérieux des quinze commits de cette vague est un correctif `Critique` :
`dict(ligne)` convertissait chaque ligne rendue par serverd en dictionnaire nu, effaçant
l'insensibilité à la casse que le SDK construit lui-même dans ses `dict` de section — il
fallait envelopper chaque ligne dans une `CaseInsensitiveDict`, pas seulement s'abstenir
de la convertir en `dict` nu. Une étiquette `Domain` là où l'outil lit `domain` rendait
`lister_annuaires()` vide, boîtier vu comme vierge : les deux gardes qui protègent
`CONFIG LDAP INITIALIZE` — la seule commande du produit qui écrase une base LDAP
existante — tombaient ensemble sur une clé dont personne ne connaît la casse réelle.

Une boîte de confirmation nomme désormais l'hôte visé, le nombre de comptes à créer et
les groupes neufs avant tout lot réel : elle rétablit l'intention de la spec — le
garde-fou contre un groupe fantôme, lu avant que la décision d'écrire ne soit prise —
après que le passage obligé par la simulation, qui portait seul ce rôle, a été retiré.

Une seule coupure réseau, survenant avant la toute première écriture du lot, avortait le
lot entier : le garde anti-boucle comparait le plan restant à celui d'avant la coupure, et
« aucun progrès » y est l'état normal tant qu'aucune écriture n'a encore abouti.

### Amorçage (2026-09-16)

- Repo créé, documentation initiale (`README.md`, `CLAUDE.md`, ce journal).

## Pièges rencontrés

- (2026-09-16) **PyInstaller ne se construit pas sur ce poste** : `objdump` (paquet
  `binutils`) est absent, et PyInstaller s'arrête avant même d'analyser le programme. Le
  `.exe` ne pouvait de toute façon venir que de `windows-latest` ; la cible et les drapeaux
  ont donc été prouvés par `pyi-makespec`, qui n'a pas besoin d'`objdump` et confirme que
  `--windowed` produit bien `console=False`.
- (2026-09-16) **`gh release create --notes "… : …"` dans un scalaire YAML nu** : un `:`
  suivi d'une espace y est interdit, la commande devient illisible ou se scinde. Écrite en
  bloc `|` dans `exe.yml`, avec `shell: bash` — les runners Windows lancent PowerShell par
  défaut, qui ne lit pas la même syntaxe de continuation.
