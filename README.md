# stormshield

Outillage Python d'injection **en lot** sur firewall Stormshield SNS, à partir de fichiers
plats : utilisateurs de la base LDAP interne et blacklists (groupes d'objets réseau/URL).

La cible est l'exploitation courante : ce que l'interface web fait un objet à la fois, cet
outil le fait pour quelques milliers de lignes, de façon rejouable.

## État

La v1 couvre l'**injection d'utilisateurs dans l'annuaire LDAP interne** : lecture d'un CSV,
rapprochement avec ce que le boîtier porte déjà, création des comptes manquants et des
groupes qu'ils réclament, génération des mots de passe. Elle se présente en fenêtre unique,
livrée en `.exe` Windows — l'opérateur visé n'a pas de terminal.

L'injection de blacklists reste à faire. L'avancement se lit dans
[`KANBAN.md`](./KANBAN.md), les conventions pour qui modifie dans
[`CLAUDE.md`](./CLAUDE.md).

## Installation

Télécharger `injection-utilisateurs-sns.exe` depuis les
[releases GitHub](https://github.com/githubf-tfr/stormshield/releases) et le poser où l'on
veut. **Rien d'autre à installer** : l'exécutable embarque son interpréteur Python et ses
dépendances. Il n'écrit aucun fichier de configuration et ne laisse aucune trace sur le
poste.

### Avertissement SmartScreen — attendu, ce n'est pas un défaut

Le `.exe` **n'est pas signé** : la signature exige un certificat payant, hors périmètre v1.

Au premier lancement, Windows SmartScreen affiche « Windows a protégé votre ordinateur ».
Cliquer sur **« Informations complémentaires »**, puis sur **« Exécuter quand même »**.

Cet avertissement est attendu. Il dit que l'éditeur n'est pas identifié par un certificat,
pas que le fichier est défectueux ou malveillant.

## Format du CSV attendu

En-tête **obligatoire**, séparateur `;` :

```
identifiant;nom;prenom;groupes
jean.dupont;Dupont;Jean;compta|lecture-seule
marie.martin;Martin;Marie;compta
paul.durand;Durand;Paul;
```

- Les colonnes se retrouvent **par leur nom** : leur ordre est libre, et toute colonne en
  trop est ignorée. Une colonne attendue absente fait **refuser le fichier entier**, sans
  qu'aucune ligne ne parte.
- `groupes` : plusieurs groupes séparés par `|`, colonne vide acceptée. Les segments vides
  et les doublons internes sont écartés.
- Les espaces de début et de fin sont supprimés de chaque champ.
- L'identifiant est **basculé en minuscules**, et ce changement est écrit au journal :
  `Jean.Dupont` crée le compte `jean.dupont`. Caractères admis après bascule :
  `a-z 0-9 . _ -`.
- Si deux lignes portent le même identifiant après bascule, **les deux sont rejetées** :
  l'outil ne choisit pas laquelle est la bonne.
- Encodages acceptés : UTF-8 avec ou sans BOM, et cp1252 — celui qu'Excel en français écrit
  par défaut. Les accents des noms sont donc conservés sans manipulation préalable.
- Il n'y a **pas de colonne d'adresse de courriel** : `USER CREATE` ne la prend pas.

Les lignes rejetées sont listées une à une au journal, avec leur numéro d'enregistrement
(l'en-tête est la ligne 1) et le motif du rejet. Le reste du lot part quand même.

## Ce que l'outil fait, et ce qu'il ne fait pas

Il **ajoute, et rien d'autre** :

- il crée les comptes du CSV absents du boîtier, et les groupes que ces seuls comptes
  réclament ;
- un compte déjà présent est classé « déjà présent, ignoré » : il n'est **ni modifié, ni
  supprimé**, ses appartenances de groupe comprises. Un groupe réclamé uniquement par un
  compte déjà présent n'est donc pas créé ;
- un compte présent sur le boîtier et absent du CSV est listé comme **orphelin** : il est
  signalé, jamais touché.

Il n'y a **aucun fichier d'état local** : l'outil relit le boîtier à chaque lancement.
Rejouer le même CSV sur un firewall déjà à jour n'écrit donc rien.

L'outil ne modifie jamais la politique de mot de passe du boîtier : il la lit, il s'y
conforme, il ne l'écrit pas.

## Simulation

La case **Simulation est cochée par défaut**. Cochée, l'outil se connecte, lit le boîtier et
affiche le plan complet — comptes à créer, groupes à créer, comptes ignorés, orphelins —
mais **n'écrit rien**.

Simulation permet de relire le plan avant de se décider, mais un premier lancement en réel
n'est pas bloqué : avant tout lot réel, une boîte de confirmation nomme l'hôte visé, le
nombre de comptes à créer et les groupes neufs — en signalant ceux qui n'auraient qu'un seul
membre, signature d'une coquille de saisie dans la colonne des groupes. Rien n'est encore
écrit à ce moment : l'opérateur peut renoncer.

## Mots de passe

Les mots de passe sont générés **au moment de la création effective de chaque compte**,
jamais à l'avance, et ils n'existent que dans la mémoire de l'outil.

Le bouton **« Enregistrer les mots de passe… »** s'active dès le premier compte créé et
écrit un CSV `identifiant;mot_de_passe` **à l'emplacement que vous désignez** — rien n'est
écrit automatiquement, nulle part. Ce CSV s'ouvre dans Excel en français sans manipulation.

**Un mot de passe vide dans ce CSV signale un compte créé dont la pose du mot de passe a
échoué** : le compte existe sur le boîtier, il n'a pas de mot de passe utilisable, et aucun
relancement ne le réparera — il sera classé « déjà présent, ignoré ». Ces comptes sont à
reprendre à la main ; le rapport final les regroupe sous « Comptes créés sans mot de passe
— à reprendre ».

Lancer un nouveau lot, ou fermer la fenêtre, efface les mots de passe non enregistrés :
l'outil le demande avant, et la réponse par défaut est **Non**. Enregistrez avant de
relancer.

La longueur et les classes de caractères se règlent dans la fenêtre. Les champs restent
grisés tant qu'aucune lecture du boîtier n'a eu lieu, puis s'activent pré-remplis sur ce que
le firewall exige. Vous pouvez **durcir** ce réglage ; une relecture du boîtier ne
l'écrasera pas. Descendre sous ce que le boîtier exige fait refuser le lot avant tout envoi.

## Certificat

La case **« Vérifier le certificat du firewall » est cochée par défaut**. Décochée, la
session devient interceptable : les identifiants d'administration et les mots de passe
générés y transitent. Ne la décocher que sur un boîtier dont l'autorité de certification
n'est pas installée sur le poste, et en connaissance de cause.

Aucun identifiant n'est stocké : hôte, compte et mot de passe sont saisis à chaque
exécution et disparaissent avec la fenêtre.

## Annuaire LDAP interne

- Le boîtier n'en déclare **aucun** : une fenêtre propose d'en créer un
  (`CONFIG LDAP INITIALIZE` puis `CONFIG LDAP ACTIVATE`). Cette opération **ne se refait
  pas** — c'est le seul cas où ce chemin est atteignable, précisément parce que la commande
  écraserait la base d'un annuaire existant.
- Le boîtier en déclare **un** : c'est celui que le lot vise.
- Le boîtier en déclare **plusieurs** : arrêt net, aucune écriture. `USER GROUP CREATE` ne
  sait pas viser un annuaire ; l'outil s'arrête plutôt que de choisir.

## Dialogue avec le firewall

Le SDK officiel [`stormshield.sns.sslclient`](https://pypi.org/project/stormshield.sns.sslclient/)
encapsule l'API SSL du boîtier (`nsrpc` sur HTTPS) et ses commandes CLI SNS. Aucun
identifiant n'est stocké dans le repo : ils sont fournis à l'exécution.

## Pour qui développe

```bash
pip install -e '.[dev]'
ruff check .          # avant tout commit
mypy                  # avant tout commit
pytest                # marqueur firewall exclu par défaut
pytest -m firewall    # exige un boîtier SNS joignable
```

Aucun test n'exige de firewall ni de `tkinter` : tout appel réseau passe par une dépendance
injectable, et toute la logique de l'interface vit dans `presentation.py`, que
`fenetre.py` se contente de câbler sur des widgets.

Ce que les tests ne couvrent pas — la fenêtre elle-même et l'adaptateur SDK face à un vrai
boîtier — relève du cahier de recette, sous [`docs/recette/`](./docs/recette/), à exécuter à
la main dès qu'un SNS est joignable.

Le `.exe` se construit **uniquement** par le workflow
[`.github/workflows/exe.yml`](./.github/workflows/exe.yml), déclenché par un tag `v*` :
PyInstaller ne produit un binaire Windows que sous Windows, et le poste de développement est
sous Linux.

Conventions et invariants : [`CLAUDE.md`](./CLAUDE.md). Spécification et plan :
[`docs/superpowers/`](./docs/superpowers/).
