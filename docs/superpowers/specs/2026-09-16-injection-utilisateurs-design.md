# Spécification — injection d'utilisateurs LDAP (v1)

Date : 2026-09-16.

## Objet et périmètre

Un outil Windows à interface graphique, livré en `.exe` autonome, crée en lot des comptes
utilisateurs dans la base LDAP **interne** d'un firewall Stormshield SNS, à partir d'un
fichier CSV.

Le périmètre v1 s'arrête aux utilisateurs et à leurs groupes. Les blacklists (groupes
d'objets réseau et d'URL), second usage du dépôt, viendront ensuite et ne contraignent rien
ici au-delà du découpage en modules.

Le développement se fait sans firewall joignable : aucune ligne de code n'est prouvée contre
un boîtier réel. Cette contrainte gouverne l'architecture — tout ce qui parle au boîtier est
isolé derrière une interface, et tout le reste se teste hors ligne.

## Contrat du fichier d'entrée

CSV, séparateur `;`, ligne d'en-tête obligatoire.

Colonnes attendues : `identifiant`, `nom`, `prenom`, `groupes`. Elles sont reconnues par leur
nom, dans n'importe quel ordre. Les colonnes supplémentaires sont ignorées sans avertissement.

Une colonne attendue absente fait échouer le fichier entier : c'est une erreur de structure,
pas un rejet ligne à ligne. L'outil n'injecte rien et affiche le nom de la colonne manquante.
Un fichier dont la structure est fausse est un fichier dont on ne sait pas lire une seule
ligne ; le rejeter en bloc évite de créer des comptes à partir d'une interprétation devinée.

La colonne `groupes` liste zéro, un ou plusieurs groupes séparés par `|`. La valeur vide est
licite : un utilisateur sans groupe est créé sans appartenance.

Encodage, dans cet ordre : BOM présent → l'encodage qu'il désigne ; sinon tentative UTF-8 ;
sinon repli cp1252. Le repli couvre les fichiers produits par Excel en français, qui restent
le cas courant.

Les espaces en tête et en fin de chaque champ sont supprimés avant toute validation. Une fois
cette suppression faite, l'identifiant est basculé en minuscules : `Jean.Dupont` devient
`jean.dupont` et la ligne passe. Un export RH porte couramment des majuscules ; rejeter 200
lignes d'un coup pour une convention de casse serait un obstacle sans contrepartie. Chaque
bascule est signalée dans le journal — l'identifiant créé diffère de celui du fichier,
l'opérateur doit le voir — sans être un rejet.

Les numéros de ligne affichés sont des numéros d'enregistrement : l'en-tête compte pour la
ligne 1, le premier enregistrement de données pour la ligne 2, et ainsi de suite. L'opérateur
doit pouvoir aller directement à la ligne fautive dans son tableur, et un tableur numérote les
enregistrements, non les sauts de ligne. Les deux ne diffèrent que si un champ entre guillemets
contient lui-même un saut de ligne, cas où le numéro d'enregistrement reste le bon.

### Exemple

```
identifiant;nom;prenom;groupes
dupont;Dupont;Marie;compta|rh
legrand;Legrand;Paul;
```

## Règles de validation et de rejet

Une ligne rejetée ne bloque pas le lot : les autres lignes sont injectées. Chaque rejet est
affiché avec son numéro de ligne, son identifiant et son motif.

Motifs de rejet, et les seuls :

1. `identifiant` vide, ou contenant, après bascule en minuscules, un caractère hors de
   `[a-z0-9._-]`. Espaces, accents et tout autre caractère hors de ce jeu restent rejetés.
2. `nom` vide, ou `prenom` vide.
3. `identifiant` en doublon dans le fichier, comparaison faite après bascule en minuscules.

Sur un doublon, **les deux lignes sont rejetées**, pas seulement la seconde. Conserver « la
première » serait un arbitrage sur une donnée dont rien ne dit laquelle est juste ; l'outil
refuse de trancher à la place de l'opérateur. La comparaison portant sur l'identifiant après
bascule, `Jean.Dupont` et `jean.dupont` sur deux lignes constituent un doublon, et les deux
lignes sont rejetées.

Le jeu `[a-z0-9._-]` exclut les majuscules ; l'identifiant étant basculé en minuscules avant
toute comparaison, celle-ci — entre eux et avec ceux du boîtier — reste une égalité de chaînes
exacte, sans repli sur une insensibilité à la casse.

Conséquence non traitée en v1 : un compte créé à la main sur le boîtier sous `Jean.Dupont` ne
serait pas reconnu par une ligne `jean.dupont`, et l'outil tenterait de le créer. Le boîtier
ciblé est vierge et tous ses comptes viendront de l'outil, donc en minuscules ; le cas ne peut
pas se présenter tant que c'est vrai. Il est à rouvrir le jour où l'outil vise un boîtier déjà
peuplé par un autre chemin.

Dans la colonne `groupes`, les segments vides (`compta||rh`, `compta|`) sont ignorés et les
doublons à l'intérieur d'une même ligne sont dédupliqués en silence. Ni l'un ni l'autre n'est
une erreur : ce sont des artefacts de saisie sans conséquence.

Aucune contrainte de caractères n'est imposée aux noms de groupes ; la liste des motifs de
rejet est close. Un nom de groupe est transmis verbatim entre guillemets doubles à
`USER GROUP CREATE` ; un nom contenant lui-même un guillemet double ne peut donc pas être
transmis et provoque un échec de création de groupe, signalé à l'exécution, non un rejet de
ligne.

## Rapprochement avec le boîtier

L'outil ajoute, et rien d'autre.

| Situation | Action |
|---|---|
| Compte dans le fichier, absent du boîtier | Créé |
| Compte dans le fichier, présent sur le boîtier | Ignoré, signalé |
| Compte sur le boîtier, absent du fichier (orphelin) | Conservé, signalé dans le rapport |

Aucune suppression, aucune modification d'un compte existant, jamais. Un outil de lot qui
modifie l'existant peut détruire en une exécution ce qu'un administrateur a réglé à la main.

Conséquence assumée : un compte déjà présent est ignoré **entièrement**, appartenances de
groupes comprises. Si le CSV place un compte existant dans un groupe auquel le boîtier ne
l'a pas rattaché, l'outil ne le rattache pas et le signale comme « déjà présent, ignoré ».
Corriger les appartenances d'un compte existant n'entre pas dans la v1.

Les orphelins sont listés en fin de rapport, sous leur propre intitulé, distinct des rejets et
des comptes ignorés. Ils n'ont aucun effet sur l'exécution.

### Groupes

Un groupe référencé par un compte **à créer** et absent du boîtier est créé.

La liste des groupes à créer se calcule à partir des seuls comptes à créer : un groupe
uniquement référencé par des lignes rejetées ou par des comptes déjà présents n'est pas créé.

Les groupes à créer sont affichés avant toute écriture, en simulation comme en réel, avec leur
nombre de membres — ce nombre étant celui des comptes à créer dans ce groupe :

```
Groupes à créer : compta_bis (1 membre)
```

Un groupe neuf à un seul membre est la signature d'une coquille de saisie. L'afficher avant que
l'opérateur ne décoche Simulation est le garde-fou contre la création d'un groupe fantôme.

## Génération et restitution des mots de passe

L'outil génère les mots de passe avec le module `secrets` de la bibliothèque standard.

La génération a lieu **au moment de la création effective du compte**, pas à la construction du
plan : un compte planifié mais jamais créé — simulation, coupure réseau, échec de
`USER CREATE` — ne consomme aucun secret et n'apparaît nulle part.

### Politique

L'écran expose la longueur et les classes de caractères. Ces champs sont **pré-remplis depuis
la politique lue sur le boîtier** par `CONFIG PASSWDPOLICY SHOW` (`MinLength`,
`MinSetOfChars`, `MinEntropy`). L'opérateur peut durcir ; l'outil refuse toute valeur
inférieure à la politique du boîtier. Sans ce plancher, `USER PASSWORD` échouerait compte par
compte avec un message que rien ne relie à sa cause.

Le pré-remplissage n'a lieu qu'à la première lecture de la politique. Les lectures suivantes
— chaque lancement relit le boîtier — ne mettent à jour que le plancher affiché et ne
réécrivent jamais des valeurs que l'opérateur a durcies : un réglage effacé par un
rafraîchissement silencieux serait pire que pas de rafraîchissement du tout.

La génération garantit la longueur demandée et au moins un caractère par classe requise.
`MinEntropy` est affiché pour information et non contraint par construction : l'entropie croît
avec la longueur, et la longueur par défaut proposée est suffisamment généreuse pour couvrir
les politiques usuelles. Un refus du boîtier reste possible et se manifeste comme un échec de
`USER PASSWORD` sur le compte concerné.

L'outil ne modifie jamais la politique du boîtier : `CONFIG PASSWDPOLICY SET` n'est jamais
envoyé, en v1. La politique du firewall est une décision d'administration, pas un réglage de
l'outil.

### Restitution

Un bouton *Enregistrer les mots de passe…* ouvre un sélecteur de fichier et écrit un CSV
`identifiant;mot_de_passe` limité aux comptes **réellement créés**, en UTF-8 avec BOM et
séparateur `;`, pour qu'Excel en français l'ouvre sans manipulation.

Aucune écriture automatique : ni à côté de l'exécutable, ni dans le dossier du fichier
d'entrée, ni ailleurs. Un fichier de secrets ne doit exister qu'à un emplacement que
l'opérateur a désigné.

Un compte créé dont `USER PASSWORD` a échoué, même après réessais, **est** inscrit dans ce
fichier, avec un champ `mot_de_passe` vide : c'est de ce fichier que l'opérateur repart pour
savoir quels comptes reprendre à la main, l'en omettre reviendrait à le perdre. Il figure aussi
dans la section dédiée du journal (voir « Comportement en panne »).

## Interface graphique

tkinter, bibliothèque standard, une seule fenêtre. Le choix tient à l'empaquetage : tkinter
se fige proprement en `.exe`, sans dépendance externe à embarquer.

```
┌─ Injection utilisateurs SNS ─────────────────────────┐
│ Firewall  [10.0.0.1_________]                        │
│ Compte    [admin____________]                        │
│ Mot passe [•••••••••••••••••]                        │
│ Fichier   [users.csv________] [Parcourir]            │
│                                                      │
│ Mot de passe généré : longueur [16]                  │
│   [x] minuscules [x] majuscules [x] chiffres         │
│   [x] caractères spéciaux                            │
│   (politique du boîtier : MinLength=12, MinSet=3)    │
│                                                      │
│ [x] Simulation (aucune écriture)                     │
│ [x] Vérifier le certificat du firewall               │
│                            [ Lancer ] [ Arrêter ]    │
│ ┌──────────────────────────────────────────────────┐ │
│ │ 12 lignes lues, 0 rejet                          │ │
│ │ Groupes à créer : compta_bis (1 membre)          │ │
│ │ dupont  : à créer                                │ │
│ │ legrand : déjà présent, ignoré                   │ │
│ │ Orphelins sur le boîtier : martin                │ │
│ └──────────────────────────────────────────────────┘ │
│ [████████████░░░░░░░░]  12 / 33                      │
│                  [Enregistrer les mots de passe…]    │
└──────────────────────────────────────────────────────┘
```

Les champs de politique restent grisés tant qu'aucune connexion n'a renseigné les valeurs du
boîtier : on ne propose pas un réglage dont on ignore le plancher. Ils s'activent donc au
premier *Lancer*, une fois `CONFIG PASSWDPOLICY SHOW` lu.

Régler la politique suppose ainsi un premier lancement — en simulation ou en réel, peu
importe : un premier lot réel n'exige plus de simulation préalable, une boîte de confirmation
affichant le plan précédant désormais toute écriture.

Le bouton *Enregistrer les mots de passe…* reste inactif tant qu'aucun compte n'a été créé ; il
s'active dès la première création, avec ou sans mot de passe.

Le journal est sélectionnable et copiable. L'outil n'écrit aucun fichier de journal : la
seule écriture sur disque est le CSV des mots de passe, à un emplacement choisi.

### Arrêter un lot en cours

Le bouton *Arrêter* est posé **à côté** de *Lancer*, jamais à sa place : l'état de l'outil se
lit ainsi d'un coup d'œil. Au repos, *Lancer* est actif et *Arrêter* grisé ; pendant un lot,
l'inverse. Les deux ne sont jamais actifs ensemble — *Arrêter* n'a rien à arrêter au repos, et
*Lancer* ferait partir un second lot sur le même boîtier pendant que le premier y écrit.

Le clic ne demande **aucune confirmation** : qui clique sur *Arrêter* est déjà pressé, et
relancer ne coûte rien puisque l'outil est idempotent.

L'exécution regarde si l'arrêt a été demandé **entre deux comptes et entre deux groupes**,
jamais au milieu de l'un d'eux : **le compte déjà entamé va jusqu'à son terme** —
`USER CREATE`, `USER PASSWORD`, puis les rattachements. C'est tout l'intérêt de ce bouton. La
seule issue qu'il remplace était de fermer la fenêtre, ce qui tue le fil n'importe où, y
compris entre `USER CREATE` et `USER PASSWORD` : le compte resterait créé sans mot de passe
utilisable, et la règle d'ajout seul interdit qu'un relancement le corrige.

Le bouton agit aussi **en simulation**, et non parce qu'elle serait longue : `USER LIST` rend
tout d'un coup, une simulation compte quatre commandes que le CSV porte deux lignes ou deux
cents, et elle s'achève en une seconde ou deux. Le motif est l'interface : l'état des deux
boutons ne doit pas dépendre du mode, et un bouton qui ne réagirait que dans un cas sur deux
serait déroutant. N'ayant rien à écrire ensuite, la simulation n'offre qu'un point d'arrêt :
la fin de sa lecture, une fois le plan affiché.

Le bilan est une **troisième fin possible**, distincte du lot mené à terme et du lot
interrompu par une panne. Il dit combien de comptes sont nés, que les suivants n'ont pas été
touchés, et que relancer est sans danger :

```
Arrêt demandé.
37 comptes créés sur 200 prévus.
Les 163 restants n'ont pas été touchés.
Relancez quand vous voulez : les 37 seront vus comme déjà présents.
```

Le bouton *Enregistrer les mots de passe…* reste disponible pour les comptes créés, comme sur
tous les autres chemins d'arrêt.

### Simulation

La case **Simulation** est cochée par défaut.

Cochée, l'outil se connecte quand même et lit le boîtier — sans cette lecture il ne pourrait
pas dire « déjà présent ». Il lit, planifie, affiche, et n'écrit pas.

Décochée, le même plan part en exécution. La simulation n'est pas une approximation du
traitement réel : elle en est la première moitié, exécutée telle quelle.

## Sécurité

### Certificat

Depuis SNS 5.0, le boîtier présente un certificat signé par une autorité qui lui est propre ;
la vérification échoue donc tant que cette autorité n'a pas été récupérée.

La case **Vérifier le certificat du firewall** est cochée par défaut et pilote
`sslverifypeer` / `sslverifyhost`. Décochée, son libellé indique explicitement que les
identifiants d'administration et les mots de passe générés transitent alors dans une session
interceptable.

Le contournement n'est jamais câblé en dur : il n'existe que comme une case que l'opérateur
décoche lui-même, à chaque session.

La v1 n'expose pas de champ `cabundle` — fournir l'autorité du boîtier est reporté (voir
« Hors périmètre v1 »).

### Secrets

Aucun identifiant n'est stocké : ni dans le repo, ni dans un fichier de configuration, ni
entre deux lancements. Le compte et le mot de passe d'administration sont saisis à chaque
exécution.

Les mots de passe générés vivent en mémoire le temps de la session et ne quittent l'outil que
par l'enregistrement explicite décrit plus haut.

`USER PASSWORD` a la propriété, documentée, de ne pas journaliser ses arguments côté boîtier.

### Annuaire LDAP interne

À la connexion, l'outil lit `CONFIG LDAP LIST`. Trois cas.

**Aucun annuaire** : une fenêtre séparée s'ouvre — l'écran principal reste nu — et demande
`domainname`, `o`, `dc`, et le mot de passe du compte `cn=StormshieldAdmin`. Ce mot de passe
est saisi par l'opérateur : l'outil ne le génère pas et ne le conserve pas. Le bouton est
libellé *Créer l'annuaire* et un texte indique que l'opération ne se refait pas.

La séquence est : `CONFIG LDAP INITIALIZE`, puis `CONFIG LDAP ACTIVATE`, puis une relecture de
`CONFIG LDAP LIST` pour confirmer. Le lot ne reprend la main qu'après cette confirmation.

L'argument optionnel `realbind` n'est pas transmis : la v1 s'en remet au défaut du boîtier
plutôt que d'imposer une valeur sur un comportement qu'elle ne peut pas éprouver.

**Exactement un annuaire** : fonctionnement normal. L'option d'initialisation n'apparaît
jamais et `CONFIG LDAP INITIALIZE` n'est jamais envoyé. C'est la protection principale : une
commande qui écrase ne doit pas être atteignable quand il y a quelque chose à écraser.

Le nom de domaine de cet annuaire, lu dans `CONFIG LDAP LIST`, est passé explicitement en
`domainname=` à `USER CREATE` : nommer l'annuaire plutôt que s'en remettre à un défaut
implicite, alors même qu'un seul est garanti présent à ce stade.

**Plus d'un annuaire** : arrêt net, message explicite à l'écran, aucune écriture. `USER CREATE`
accepte `domainname=`, mais ni `USER GROUP CREATE` ni `USER GROUP ADDUSER` ne l'acceptent dans
la syntaxe retenue : sur un boîtier multi-annuaires, les comptes iraient au bon endroit et les
groupes on ne sait où. Traiter ce cas à moitié serait pire que le refuser (voir « Hors
périmètre v1 »).

## Architecture et modules

Paquet `stormshield_utilisateurs/`. Français dans le code : noms, docstrings, commentaires,
messages.

| Module | Rôle |
|---|---|
| `modele.py` | dataclasses : `Utilisateur`, `Rejet`, `Plan`, `Rapport`, `PolitiqueMotDePasse` |
| `lecture.py` | CSV → (utilisateurs valides, rejets). Pur, aucun réseau |
| `motdepasse.py` | génération selon `PolitiqueMotDePasse`. Pur |
| `boitier.py` | `Protocol` `Boitier` + implémentation SDK `sslclient` |
| `plan.py` | état boîtier + lignes valides → `Plan`. Pur, aucune écriture |
| `execution.py` | applique un `Plan` sur un `Boitier`, émet la progression |
| `sortie.py` | écrit le CSV des mots de passe des comptes créés |
| `fenetre.py` | tkinter, une fenêtre, câble le tout |

Deux frontières portent tout le reste.

**`Boitier` est un `Protocol`.** Il déclare `lister_utilisateurs`, `lister_groupes`,
`creer_groupe`, `creer_utilisateur`, `definir_mot_de_passe`, `ajouter_membre`, plus les
opérations qu'exigent la politique de mot de passe (lecture) et l'annuaire (liste,
initialisation, activation). Son implémentation SDK est le **seul** module du paquet à
importer `stormshield.sns.sslclient`.

**`plan.py` n'écrit rien.** Il reçoit l'état lu du boîtier et les lignes valides, et rend un
`Plan` : comptes à créer, comptes ignorés, groupes à créer avec leur nombre de membres,
orphelins. Toute la logique de décision est donc une fonction pure, testable sans réseau.

Les tests tournent contre un `BoitierMemoire` qui implémente le même `Protocol`. La totalité de
la logique métier se teste donc sans firewall.

### Exécution en arrière-plan

Aucune commande de lot n'existe côté SNS : 200 comptes représentent environ 600 allers-retours
séquentiels, soit plusieurs minutes.

L'exécution part donc dans un thread. Ce thread ne touche jamais un widget tkinter — il publie
ses événements de progression dans une file que la fenêtre vide périodiquement via `after()`.
Une seule chose circule en sens inverse, l'ordre d'arrêt, porté par un `threading.Event` : sa
pose et sa lecture sont atomiques et la bascule est publiée au fil qui lit, ce qu'un attribut
ordinaire ne promet pas.
La barre de progression est fonctionnelle, pas décorative : elle affiche le nombre d'opérations
accomplies sur le total planifié. En simulation elle couvre les seules lectures et s'arrête à
l'affichage du plan ; Simulation décochée, elle couvre en outre les écritures — créations de
groupes, et par compte `USER CREATE`, `USER PASSWORD`, un `USER GROUP ADDUSER` par groupe.

## Dialogue avec le boîtier

Le SDK expose `SSLClient(user=, password=, host=, port=443, cabundle=, sslverifypeer=True,
sslverifyhost=True, …)` et `send_command(commande)`. La réponse est un objet `Response`
portant `code`, `ret`, `msg`, `output`, `xml`, `data`, `format`. Son `__bool__` est vrai
lorsque `100 <= ret < 200` : le test de succès s'écrit `if reponse:`.

Le champ Firewall de l'écran ne contient qu'un hôte : le port reste 443, valeur par défaut du
SDK, et n'est pas exposé. Un champ de plus pour une valeur que personne ne change coûte plus
qu'il ne rapporte ; l'exposer viendra si le besoin se présente.

Codes connus : 100 OK, 200 erreur de commande, 202 échec d'authentification, 203 idle,
204 limite d'authentification, 205 privilège insuffisant, 206 restriction de licence.
`client.disconnect()` ferme la session.

Le patron officiel Stormshield pour l'injection en lot — leur script `python/blacklist/blacklist.py`
du dépôt `stormshield/sns-scripting` — est exactement celui-ci : ouvrir une session, boucler les
commandes, fermer. L'outil ne s'en écarte pas.

Commandes utilisées, une par aller-retour, et aucune autre :

| Commande | Usage |
|---|---|
| `USER LIST` | état des comptes |
| `USER GROUP LIST` | état des groupes |
| `USER CREATE uid=<uid> name=<nom> [gname=<prenom>] [domainname=<ldap>]` | création ; `uid` et `name` requis |
| `USER PASSWORD dn=<UserID>\|<UserDN> password=<mdp> [hash=…]` | mot de passe ; arguments non journalisés |
| `USER GROUP CREATE "<nom>"` | création de groupe |
| `USER GROUP ADDUSER "<groupe>" <UserId>` | appartenance ; groupe cité, voir ci-dessous |
| `CONFIG PASSWDPOLICY SHOW` | lecture de la politique (lecture seule) |
| `CONFIG LDAP LIST` | présence de l'annuaire interne |
| `CONFIG LDAP INITIALIZE domainname= o= dc= password= [realbind=on\|off]` | création de l'annuaire, chemin conditionnel |
| `CONFIG LDAP ACTIVATE` | activation de l'annuaire |

**Déviation actée : le groupe d'`ADDUSER` part entre guillemets doubles**, alors que la
documentation SNS l'écrit nu. `USER GROUP CREATE` cite le nom — un nom de groupe peut porter un
espace —, et un groupe créé sous `"compta bis"` serait définitivement inadressable si l'ajout de
membre, lui, envoyait `compta bis` nu : le boîtier y verrait deux jetons et découperait la
commande autrement, en silence. Citer des deux côtés ou d'aucun ; l'outil cite. Le `uid`, lui,
reste nu : il est contraint en amont à `^[a-z0-9._-]+$`. Ce choix est repris dans
`stormshield_utilisateurs/boitier_sdk.py` et figé par `tests/test_boitier_sdk.py`.

Certains `uid` sont interdits par le boîtier (`admin`, `ha`, …). L'outil ne tient pas de liste
locale de ces interdits (voir « Points non vérifiés ») : un `uid` refusé se manifeste comme un
échec de `USER CREATE` sur ce compte, signalé, sans arrêter le lot.

`USER GROUP NEW`, également documenté, n'est pas utilisé : sa différence avec
`USER GROUP CREATE` n'est pas établie, et une seule des deux suffit.

### Flux d'exécution

1. Lecture du CSV. Hors ligne, aucune connexion.
2. Connexion, puis lecture du boîtier : `CONFIG LDAP LIST`, `CONFIG PASSWDPOLICY SHOW`,
   `USER LIST`, `USER GROUP LIST`. Lecture seule. Si `CONFIG LDAP LIST` rend plus d'un
   annuaire, le lot s'arrête ici (voir « Annuaire LDAP interne »).
3. Construction du `Plan`.
4. Affichage du plan et des rejets : lignes lues, rejets motivés, groupes à créer avec leur
   nombre de membres, comptes à créer, comptes ignorés, orphelins.
5. Si Simulation est décochée : création des groupes manquants, puis, compte par compte,
   `USER CREATE`, `USER PASSWORD`, `USER GROUP ADDUSER` — un appel par groupe.
6. Déconnexion.

Les étapes 1 à 4 se déroulent à l'identique dans les deux modes.

L'arrêt demandé par l'opérateur est consulté à la fin de l'étape 4 — seul point d'arrêt
d'une simulation, et ce qui évite de demander l'autorisation d'écrire un lot déjà arrêté —
puis avant chaque groupe et avant chaque compte de l'étape 5 (voir « Arrêter un lot en
cours »).

## Comportement en panne et idempotence

**Panne réseau** : trois tentatives de reconnexion, espacées de deux secondes, puis arrêt net.
Ce qui est créé reste créé, le journal le dit, et le fichier de mots de passe couvre les
comptes réellement créés.

Une reconnexion réussie ne rejoue pas la commande interrompue : l'outil relit `USER LIST` et
`USER GROUP LIST`, reconstruit le plan sur ce qui reste, et poursuit. Rejouer à l'aveugle une
commande dont on ignore si le boîtier l'a exécutée avant la coupure ferait exactement ce que la
reconstruction du plan évite.

**Reprise** : au relancement, l'état du boîtier est relu. Les comptes déjà créés tombent en
« déjà présent, ignoré » et le lot se poursuit sur le reste. L'idempotence découle de la
reconstruction du plan à chaque exécution, jamais d'un fichier d'état local — un fichier
d'état ment dès que quelqu'un touche au boîtier par un autre chemin.

**Échec sur un compte isolé** (`uid` interdit, erreur de commande) : le compte est signalé, le
lot continue. Un lot de 200 comptes ne s'arrête pas sur une ligne fautive.

**Échec de `USER PASSWORD` après un `USER CREATE` réussi** : trois réessais, espacés de deux
secondes — même cadence que la reconnexion —, puis abandon pour ce compte. Le compte existe
alors sans mot de passe utilisable ; il est inscrit dans le CSV des mots de passe avec un champ
`mot_de_passe` vide (voir « Restitution ») et regroupé dans une section dédiée du journal,
intitulée « Comptes créés sans mot de passe — à reprendre », distincte des rejets, des échecs
et des orphelins. La règle « aucune modification d'un compte existant » implique qu'un
relancement ne corrigera pas ce compte : il tombera en « déjà présent, ignoré ». La reprise en
main est manuelle — limitation assumée, pas un défaut à corriger. Le plancher de politique lu
sur le boîtier rend ce cas peu probable, mais il n'est pas impossible et l'outil ne le masque
pas.

**Échec de `USER GROUP ADDUSER`** : même traitement — signalé, lot poursuivi, non rattrapé par
un relancement. Pas de réessais dédiés ici : contrairement à un mot de passe absent, une
appartenance de groupe manquante ne rend pas le compte inutilisable, et le signaler simplement
suffit.

## Tests

**Unitaires, pytest, sans firewall** : `lecture` (structure, encodages, bascule de
l'identifiant en minuscules, motifs de rejet, doublons y compris inter-casse), `motdepasse`
(respect de la politique), `plan` (les quatre situations de rapprochement, le calcul des
groupes à créer et de leurs membres), `execution` contre le `BoitierMemoire` (ordre des
appels, échec isolé, arrêt après reconnexions, reprise, arrêt demandé — compte en cours
mené à son terme, suivant non entamé, simulation comprise), `sortie` (contenu et encodage du CSV,
restriction aux comptes créés).

On teste des comportements, pas des rouages : aucun test ne vérifie qu'une fonction interne a
été appelée. Les tests de `execution` observent l'état final du `BoitierMemoire` et les
événements de progression émis, qui sont l'interface publique du module.

**Adaptateur SDK** : marqueur `firewall`, exclu par défaut. Il est écrit contre la
documentation et **n'est prouvé par rien** tant qu'aucun boîtier n'est joignable. C'est
précisément pourquoi il est mince — traduction d'appels en chaînes de commande et lecture de
`Response` — et isolé derrière le `Protocol` : la surface non prouvée doit être la plus petite
possible, et tout ce qui peut en sortir doit en sortir.

**Analyse statique avant tout commit** : `ruff check .` puis `mypy`.

**Cahier de recette** fonctionnel, écrit avec la v1, exécuté par un humain quand un boîtier
sera joignable. Il couvre tous les cas d'usage, y compris ceux déjà couverts en unitaire :
l'un prouve que le code fait ce qu'on a écrit, l'autre que le produit fait ce qu'on attend.

## Livraison et empaquetage

`.github/workflows/qualite.yml` — à chaque poussée : `ruff check .`, `mypy`, `pytest` hors
marqueur `firewall`.

`.github/workflows/exe.yml` — sur tag `v*` : `windows-latest`, PyInstaller
`--onefile --windowed`, `.exe` publié en release GitHub. Le `--windowed` empêche une console
noire de s'ouvrir derrière la fenêtre tkinter.

Le `.exe` n'est pas signé. SmartScreen avertira au premier lancement. La signature exige un
certificat payant, hors périmètre v1 ; le `README.md` doit le dire, faute de quoi
l'avertissement passera pour un défaut.

## Points non vérifiés

Ces points sont connus comme incertains. Aucun n'empêche la v1 ; chacun est porté par un
comportement qui échoue proprement plutôt que par une hypothèse cachée.

1. **Longueur maximale et jeu de caractères exact autorisés pour le `uid`.** La page
   « Allowed or prohibited characters » (annexe A du guide SNS) n'a pas pu être consultée. Le
   jeu `[a-z0-9._-]` retenu est restrictif par prudence ; un `uid` trop long échouerait à la
   création et serait signalé.
2. **Liste exhaustive des `uid` interdits.** Seuls `admin` et `ha` sont attestés. L'outil ne
   tient donc pas de liste locale et s'en remet au refus du boîtier.
3. **Différence fonctionnelle entre `USER GROUP CREATE` et `USER GROUP NEW`.** Les deux sont
   documentés. La v1 n'utilise que `CREATE`.
4. **Champ mail sur `USER UPDATE`** : son existence et sa disponibilité ne sont pas établies.
   Sans objet en v1, le mail étant abandonné, mais à reprendre si le besoin revient.
5. **Limite de sessions simultanées ou de débit de l'API serverd.** Les codes `SRV_RET_IDLE`
   et `SRV_RET_AUTHLIMIT` suggèrent des garde-fous côté serveur, sans valeur chiffrée connue.
   L'outil n'ouvre qu'une session et n'émet qu'une commande à la fois, ce qui est la posture
   la plus sûre en l'absence de chiffre.
6. **Comportement de `CONFIG LDAP INITIALIZE` rejoué sur une base déjà initialisée.** La
   parade retenue n'est pas de le tester : c'est de rendre ce chemin inatteignable dès qu'un
   annuaire répond à `CONFIG LDAP LIST`.

## Hors périmètre v1

- **Blacklists** — groupes d'objets réseau et d'URL. Suite prévue du dépôt.
- **Champ mail.** `USER CREATE` ne le prend pas ; abandonné en v1 plutôt que contourné.
- **Modification ou suppression de comptes existants**, appartenances de groupes comprises.
  L'outil ajoute seulement.
- **Écriture de la politique de mot de passe** (`CONFIG PASSWDPOLICY SET`). Lecture seule.
- **Fourniture de l'autorité de certification du boîtier** (`cabundle`). La v1 offre deux
  états : vérifier, ou ne pas vérifier.
- **Signature du `.exe`.** Certificat payant.
- **Mémorisation des identifiants de connexion** entre deux lancements.
- **Journal sur disque.** Le journal vit dans la fenêtre et se copie.
- **Boîtiers déclarant plusieurs annuaires LDAP.** L'outil s'arrête au lieu de choisir entre
  eux (voir « Annuaire LDAP interne »).
