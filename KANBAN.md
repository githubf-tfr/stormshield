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
- Ajout seul : jamais de suppression, jamais de retrait d'appartenance. Un compte
  existant n'est ni supprimé, ni désactivé, ni modifié dans ses attributs, et son mot
  de passe reste hors d'atteinte ; depuis la v2 il reçoit les adhésions de groupe que
  le fichier lui donne et que le boîtier n'a pas. Les orphelins sont signalés, pas
  touchés.
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
  joignable.** 139 cas, dont 22 jouables sans boîtier sur un poste Windows et le `.exe` de
  la release, et 117 exigeant un boîtier joignable. Depuis le 2026-09-18 il n'est plus la
  seule couverture de `fenetre.py` — voir « Couverture de `fenetre.py` » — mais il reste le
  seul moyen de confirmer les hypothèses de `boitier_sdk.py` (sections F et R du cahier),
  et le seul juge de l'apparence, des vraies boîtes modales et de `lancer()`.
- **Lancer le `.exe` sous Windows.** `exe.yml` a tourné deux fois et publié un binaire de
  14 Mo, ce qui prouve que PyInstaller collecte le paquet — rien ne prouve que la fenêtre
  s'ouvre. C'est le premier pas de la recette, et il ne demande aucun boîtier.
- Spec de l'injection de blacklists : granularité (objet réseau vs groupe URL), purge ou
  ajout seul.

## Points à lever dès qu'un boîtier est joignable

Tous sont portés par le cahier de recette, avec le cas qui les tranche — sauf la
complétude de `USER LIST`, relevée après son écriture et qu'aucun cas ne couvre encore.

- **La forme des membres rendus par `USER GROUP SHOW`** — seul point structurant de la
  v2. Le nombre de membres non rattachés affiché au plan **l'infirme** dès la première
  lecture — il ne la confirme jamais seul, voir les pièges datés du 2026-09-17 : il vaut
  **zéro sur un boîtier sain**, les membres se comparant aux comptes du boîtier et non au
  fichier (cahier de recette, cas 122, à jouer en premier).
  Faux : l'outil réémet des `ADDUSER` redondants, sans dommage, et le repli tient dans
  `uid_du_dn`.
- **La complétude de `USER LIST`** — troncature ou pagination au-delà d'un certain nombre
  de comptes. Jamais évoquée nulle part jusqu'ici, alors que le `README.md` promet
  « quelques milliers de lignes » et que la spec v2 raisonne sur un boîtier de 500
  comptes. Si serverd tronque, les comptes au-delà de la coupure sont vus **absents**,
  `USER CREATE` est refusé « existe déjà », et le refus écarte toutes leurs adhésions —
  la troncature étant persistante, **à chaque exécution, définitivement**. Le compte
  d'orphelins est faux du même coup, et une ambiguïté de casse dont une graphie tombe
  hors de la réponse devient invisible. Rien ne le détecte : le seul indice est un nombre
  anormal de refus « existe déjà » sur des comptes annoncés à créer. À trancher en
  comparant le nombre de comptes rendus à celui qu'affiche l'administration web.
- **La forme rendue par `USER GROUP LIST`** — nom de groupe ou DN. Elle sert désormais
  d'argument à `USER GROUP SHOW`.
- **La coexistence de deux groupes — ou de deux comptes — que la casse seule distingue.**
  Si elle est possible, la collision est signalée sans correspondance exacte, et ni le
  groupe ni le compte en cause n'est touché (cas 129 et 138).
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

### Couverture de `fenetre.py` (2026-09-18)

`fenetre.py` était le seul module qu'aucun test n'avait jamais touché : **328
instructions jamais exécutées**, sur la foi d'une affirmation fausse — « `tkinter` est
absent de cette machine ». Le paquet n'était pas installé, voilà tout. Avec `python3-tk`
et `xvfb` : **98 %** (351/358), 65 tests dans `tests/test_fenetre.py`.

Ce qui a rendu la chose possible, deux coutures sur `Fenetre`, toutes deux au défaut de
production : `Dialogues`, qui regroupe les six boîtes modales — une modale Tk n'en sort
qu'au clic d'un humain —, et `fabriquer_boitier`, qui ouvrirait sinon une vraie session
SSL. Mêmes titres, mêmes textes, même icône et même bouton *Non* par défaut : rien de ce
que voit l'opérateur n'a changé.

Ce qui résiste, et pourquoi c'est définitif : les six défauts de `Dialogues` (un appel
chacun à `messagebox`/`filedialog`) et le corps de `lancer()`, qui construit la fenêtre
de production puis entre dans `mainloop`. Sept instructions, toutes couvertes par le
cahier de recette.

**`pytest` nu reste vert sans affichage** — le fichier se saute avec la raison que Tk
donne lui-même — et `qualite.yml` installe `python3-tk` + `xvfb` puis échoue si un test
a été sauté : un saut sur le runner voudrait dire que l'interface est verte sans avoir
rien prouvé.

Le garde qui interdisait à `presentation.py` d'importer `tkinter` est **gardé** : c'est
une frontière d'architecture, indépendante de toute machine. Celui qui vérifie ce qui
part dans un fil est **gardé et étendu** ; les deux objets qui franchissent la frontière
(la demande d'arrêt, la fabrique) sont recopiés dans des variables locales et ne portent
aucun widget. La « garde qui interdisait aux tests d'importer `tkinter` » n'a jamais
existé comme test : c'était une affirmation dans trois docstrings, devenue fausse et
corrigée.

Cette garde a été élargie deux fois, chaque fois sur un trou trouvé en cherchant à la
contourner et non en la relisant. D'abord le **blanchiment par variable locale** —
`publieur = self._appliquer` puis `args=(…, publieur)` — que la campagne venait
justement d'introduire comme idiome de production. Ensuite le **déballage de tuple** :
`publieur, _rien = self._appliquer, 1` range ses cibles dans un unique `ast.Tuple`, et
la garde ne lisait que les `ast.Name` de premier niveau — aucun nom n'en sortait, à
aucune profondeur. Les cibles sont désormais aplaties récursivement, et un déballage
entaché entache **tous** les noms qu'il pose : la garde ne tente pas d'apparier source
et cibles. Sur-refuser ne coûte rien tant qu'un tel nom ne part pas dans un fil ; un
faux négatif, lui, ne se voit jamais.

### Le workflow que personne n'avait fait tourner (2026-09-18)

La campagne de couverture réécrivait `qualite.yml` — installation de `python3-tk` et
`xvfb`, refus d'un saut, plancher de tests. **Sa branche n'a jamais été poussée** : le
workflow est arrivé sur `main` sans avoir jamais vu un runner, et il a échoué au premier
tour. Une branche qui modifie l'intégration continue se pousse avant de fusionner, sinon
la fusion *est* le premier essai.

L'étape ne disait rien de ce qui l'avait tuée : `Process completed with exit code 1`, et
rien d'autre. Elle tourne sous `bash -e`, et `resultat=$(xvfb-run -a pytest …)` mourait
à l'affectation dès que `pytest` sortait en non-zéro — **avant** le premier `echo`. Les
trois garde-fous étaient donc muets par construction, y compris celui qui venait de se
déclencher. Le verdict passe désormais par une variable et les causes sortent en
annotations `::error::`.

Les annotations, et pas le journal, parce que **les logs de job sont inaccessibles
depuis le bac à sable de développement** : `blob.core.windows.net` répond
`x509: certificate signed by unknown authority`. Les annotations passent par l'API
`github.com`, elles. C'est le seul canal de diagnostic disponible d'ici, et c'est pour
ça que le workflow doit se raconter lui-même.

Une annotation `::error::` s'arrête à la première fin de ligne : un message multi-ligne
perd tout sauf sa première ligne s'il n'encode pas ses sauts en `%0A`. Ça nous a trompés
une fois.

La cause du rouge, une fois visible : un seul test, `fenetre.py`, **sous 3.12
seulement**. Une `tkinter.Variable` orpheline d'une fenêtre de test détruite se faisait
ramasser par le GC cyclique sur le fil d'un lot ; son `__del__` interroge le Tcl de sa
racine morte, et tkinter, appelé hors du fil principal, poste l'appel à la boucle
d'événements puis **attend** — boucle qui n'existe plus. `gc.collect()` après
`destroy()` rend la collecte synchrone et la garde sur le fil principal.

Rien à corriger en production : il y faut une racine détruite pendant qu'un fil tourne.
La suite crée et détruit ~500 racines dans un même processus, la production n'en crée
qu'une et ne la détruit qu'en partant. Le seuil du GC générationnel diffère assez entre
versions pour que la collecte tombe sur un fil différent selon la version — d'où 3.12
seul, et d'où l'invisibilité totale en local, où le Python est 3.14. **Une suite verte
sur une version que la CI ne teste pas ne prouve rien de celles qu'elle teste.**

### Numérotation des releases (2026-09-17)

Les tags suivent les vagues de conception, pas un décompte de releases : la
première publiée est `v2.0.0`, parce que le produit qu'elle contient est la v2 au
sens de ce dépôt. Il n'y a jamais eu de `v1.0.0` — la v1 n'a pas été publiée, faute
d'avoir jamais rencontré un boîtier. Un `v0.0.1-rc1` jetable a servi une fois à
prouver que le workflow de construction du `.exe` fonctionnait, puis a été supprimé
avec son tag.

Deux numérotations concurrentes sur un même dépôt se contredisent tôt ou tard :
celle-ci est alignée sur la documentation, qui parle partout de v1 et de v2.

### Alignement sur un boîtier déjà peuplé — v2 (2026-09-17)

Spec `docs/superpowers/specs/2026-09-17-boitier-peuple-design.md`, plan
`docs/superpowers/plans/2026-09-17-boitier-peuple-plan.md`. L'invariant v1 « aucune
modification d'un compte existant » se déplace : l'outil crée des comptes, crée des
groupes, ajoute des adhésions — et n'enlève jamais rien.

- Reconnaissance insensible à la casse des comptes **et** des groupes, avec adressage
  systématique sous l'orthographe rendue par le boîtier (`rapprochement.py`). Une même
  règle pour les deux : correspondance exacte d'abord, sinon l'ambiguïté est signalée et
  rien n'est touché — jamais tranchée sur l'ordre de la liste rendue.
- Les adhésions manquantes d'un compte déjà présent sont ajoutées ; colonne `groupes`
  vide = « je ne me prononce pas », donc aucune adhésion.
- Lecture d'état à `4 + g` commandes, `g` comptant les groupes cités par le fichier et
  déjà présents ; arrêt consulté entre deux lectures d'inventaire.
- Orphelins et membres non rattachés sont des **nombres**, jamais des listes.
- Le mot de passe d'un compte existant est structurellement hors d'atteinte : un seul
  appelant de `_definir_mot_de_passe`, sous garde de structure.
- **Écarté** : le retrait d'appartenance. Un retrait sûr coûtait `4 + G + M` commandes
  (224 pour 200 comptes sur 20 groupes) contre `4 + g` (9) — voir « Pourquoi la v2
  n'enlève rien » dans la spec. Le signalement des divergences d'attributs tombe avec
  lui : il était le sous-produit du `USER SHOW` par compte.
- Revue finale de branche : un refus se comparait à la casse près, dans la branche dont
  tout le sujet est l'insensibilité à la casse — le sort d'une écriture dépendait de la
  graphie que le boîtier rendait à la relecture ; un `USER CREATE` refusé emportait en
  silence toutes les adhésions du compte, que le journal nomme désormais ; une graphie
  rendue deux fois passait pour une ambiguïté ; les comptes et groupes ambigus
  n'atteignaient ni la boîte de confirmation ni le bilan final, qui annonçait « 0 échec »
  pendant qu'un compte n'avait rien reçu ; et le mélange du générateur de mots de passe
  ne déplaçait jamais le dernier caractère — un mutant sur onze survit encore après
  correctif (mélange à l'envers).
- **405 tests** passent (marqueur `firewall` exclu), `ruff` et `mypy` verts, aucun
  `# type: ignore`. Cahier de recette porté à 139 cas, `README.md` aligné sur la v2.

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
- Le bouton agit aussi en simulation, dont le seul point d'arrêt est la fin de la lecture —
  non qu'elle soit longue (quatre commandes quel que soit le CSV), mais parce que l'état
  des deux boutons ne doit pas dépendre du mode.
- Revue de branche : le bilan avait deux formes là où il en fallait trois — sur zéro compte
  créé, cas le plus fréquent d'un arrêt demandé, il affirmait qu'un compte était né ; le
  clic n'écrivait aucune ligne de journal, alors que l'arrêt effectif peut se faire attendre
  une quinzaine de secondes ; et les deux boutons, posés dans les colonnes du cadre
  principal, auraient été séparés par la largeur de la colonne des libellés.
- **299 tests**, `ruff` et `mypy` verts, aucun `# type: ignore`. Spécification amendée,
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
| `fenetre` | Seul module à importer `tkinter`. Testé sous `xvfb-run` depuis le 2026-09-18 |
| `__main__` | Point d'entrée, cible de PyInstaller, filet de démarrage |

- **505 tests** passent sous `xvfb-run` (marqueur `firewall` exclu), `ruff` et `mypy`
  verts, aucun `# type: ignore`. Ce compte est celui du produit entier, v2 comprise ; il
  était de 273 à la livraison de la v1.
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
- (2026-09-17) **Le compteur des membres non rattachés est aveugle à un mauvais *format*
  de réponse, il ne détecte qu'une mauvaise *forme* de DN** : il compare les `uid` que
  `uid_du_dn` a su extraire aux comptes connus du boîtier, mais ne voit rien si
  `USER GROUP SHOW` rend un format inattendu, ou répète le champ `member=` sans le
  suffixe numérique attendu (`member_2=`, `member_3=`, …) — les membres au-delà du
  premier sont alors perdus avant même d'être comparés, et le compteur affiche zéro, lu
  à tort comme « tout va bien ». Dans ce cas précis, seul le texte brut de la réponse
  garde la vérité : à confronter à la trace brute dès le premier boîtier joignable, sans
  se fier au compteur seul.
