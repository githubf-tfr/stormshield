# Spécification — alignement sur un boîtier déjà peuplé (v2)

Date : 2026-09-17.

Cette spec **amende** `2026-09-16-injection-utilisateurs-design.md` (v1), qui fait autorité sur
tout ce qu'elle ne change pas : contrat du fichier CSV, motifs de rejet, génération et
restitution des mots de passe, annuaire LDAP interne, certificat, empaquetage. Ce document ne
répète la v1 que là où il la contredit ou la prolonge.

## Ce que la v1 garantissait et que la v2 abandonne

La v1 promettait : **« l'outil ajoute, et rien d'autre. Aucune suppression, aucune
modification d'un compte existant, jamais. »** Un compte déjà présent sur le boîtier était
ignoré *entièrement*, appartenances de groupes comprises.

**Une seule moitié de cette phrase tombe** : « aucune modification d'un compte existant ». La
v2 ajoute des adhésions de groupe à des comptes qui existaient avant elle, et c'est le seul
geste qu'elle pose sur eux. L'invariant ne disparaît pas, il se déplace et s'élargit :

> L'outil crée des comptes, crée des groupes, ajoute des adhésions — et **n'enlève jamais
> rien**.

Ce qui reste vrai, et qui borne l'abandon :

| Garantie v1 | v2 |
|---|---|
| Aucun compte supprimé | **inchangée** — `USER REMOVE` n'entrera pas dans l'outil |
| Aucun compte désactivé | **inchangée** — aucun verbe de désactivation n'existe (voir « Ce qui est vérifié ») |
| Aucune appartenance de groupe retirée | **inchangée** — aucun verbe de retrait n'entre dans l'outil |
| Aucun attribut d'un compte existant modifié | **inchangée** — et l'outil ne lit même plus les attributs d'un compte existant |
| Le mot de passe d'un compte existant n'est jamais touché | **inchangée, et désormais exigée structurellement** |
| Un compte existant est ignoré *entièrement*, adhésions comprises | **abandonnée** — ses adhésions manquantes sont ajoutées |

Le fichier fait autorité **sur ce qu'il décrit, jamais sur ce qu'il ne mentionne pas**. C'est
la règle qui gouverne tout le reste : un CSV tronqué à la copie, un export RH partiel, une
colonne oubliée n'entraînent aucune action sur ce qu'ils passent sous silence.

## Ce que la v2 corrige

Trois défauts que la v1 assumait tant que le boîtier était vierge, et qui interdisent la
reprise d'un boîtier existant :

1. **La casse des identifiants n'est pas reconnue.** `Jean.Dupont` créé à la main dans
   l'interface web n'est pas vu par la ligne `jean.dupont` : l'outil tente de le créer.
2. **Les adhésions de groupe ne sont jamais ajoutées** pour un compte existant.
3. **Les orphelins noient le rapport.** 500 comptes listés au-dessus du plan et des rejets,
   c'est-à-dire au-dessus de ce sur quoi l'opérateur doit se prononcer avant d'écrire.

Et rien d'autre. En particulier, aucun retrait — voir ci-dessous.

## Pourquoi la v2 n'enlève rien

Une version antérieure de cette spec faisait de la v2 un outil d'alignement : le fichier
devenait autorité complète sur les adhésions d'un compte, les adhésions absentes du fichier
étaient retirées. Ce périmètre est abandonné, pour un motif chiffrable.

**Le coût de lecture.** Avec retraits, l'état se lit en `4 + G + M` commandes — `G` groupes du
boîtier, `M` comptes du fichier reconnus —, soit **224** pour un lot de 200 comptes sur un
boîtier de 20 groupes. Sans retraits, il se lit en `4 + g`, où `g` est le nombre de groupes
**cités dans le fichier**, soit **9** sur le même exemple, le fichier en citant cinq. Vingt-cinq
fois moins, et la simulation redevient quasi instantanée.

L'effondrement tient à une asymétrie entre les deux opérations. Un rattachement raté entre un
membre rendu par le boîtier et un compte connu de l'outil n'a pas le même poids :

- pour un **retrait**, se tromper est destructeur — on ôte un accès à quelqu'un sur la foi
  d'une comparaison qu'on a mal faite. D'où la règle « un membre non rattaché n'est jamais
  retiré », et d'où le besoin d'un DN exact, donc d'un `USER SHOW` par compte reconnu ;
- pour un **ajout**, se tromper est bénin : au pire l'outil émet un `USER GROUP ADDUSER` sur
  quelqu'un qui était déjà membre. Le boîtier l'accepte ou le refuse, rien n'est cassé.

Donc, sans retraits, **le `USER SHOW` par compte disparaît entièrement** : le rattachement des
membres peut se faire en lisant le DN rendu par `USER GROUP SHOW`, avec ses approximations.

Second gain, du même ordre : pour retirer, il fallait lire **tous** les groupes du boîtier —
c'est justement dans ceux que le fichier ne cite pas qu'on cherchait les adhésions à ôter. Pour
ajouter, **seuls comptent les groupes cités dans le fichier**.

Ce que la v2 paie en échange, et qu'il faut lire avant d'aller plus loin :

- le **signalement des divergences d'attributs** disparaît. Il était le sous-produit du
  `USER SHOW` par compte ; sans cette commande il est impossible, `USER LIST` ne rendant que
  des identifiants. Cette capacité, que ce document promettait encore, sort du périmètre ;
- l'idempotence stricte repose désormais sur un rattachement approximatif (voir
  « Idempotence »).

## Rapprochement des identités

### Casse

La reconnaissance d'un compte est **insensible à la casse**. La règle v1 de lecture ne bouge
pas : l'identifiant du fichier est basculé en minuscules, et les motifs de rejet restent ceux
de la v1, jeu `[a-z0-9._-]` compris.

La clé de rapprochement est `str.casefold()` appliqué des deux côtés — à l'identifiant du
fichier (déjà en minuscules, que `casefold` laisse inchangé sur ce jeu de caractères) et à
l'identifiant rendu par le boîtier. Une seule fonction, un seul sens de comparaison.

**L'outil s'adresse toujours au compte sous l'orthographe rendue par le boîtier**, jamais sous
celle du fichier : c'est la seule dont on sache qu'elle existe chez lui. Un compte `Jean.Dupont`
reconnu par la ligne `jean.dupont` reçoit ses `USER GROUP ADDUSER` sous `Jean.Dupont`. Cela rend
**sans objet, pour l'outil**, la question non tranchée de la sensibilité à la casse de l'`uid`
côté SNS : l'outil ne demande jamais au boîtier de retrouver un compte sous une orthographe
qu'il n'a pas lui-même rendue.

Un compte **à créer** n'a pas d'orthographe côté boîtier : il est créé, puis adressé, sous
l'identifiant du fichier — en minuscules, comme en v1.

**Deux graphies vivantes pour un même compte.** Si `USER LIST` rend `Jean.Dupont` **et**
`jean.dupont`, l'outil ne sait pas auquel s'adresser, et **l'ordre dans lequel le boîtier rend sa
liste n'est garanti par rien** : trancher sur la première graphie rendue ferait écrire sur un
compte différent d'une exécution à l'autre. La résolution est donc celle des groupes, mot pour
mot (voir « Groupes ») : si l'identifiant du fichier correspond **exactement** à l'une des
graphies, c'est ce compte-là qui est adressé — l'outil a sous les yeux un compte qui s'écrit tel
quel sur le boîtier, il n'a rien à deviner. L'identifiant du fichier étant toujours en
minuscules, cette correspondance exacte désigne la graphie minuscule du doublon lorsqu'elle
existe : `Jean.Dupont` et `jean.dupont` se résolvent en `jean.dupont` ; `Jean.Dupont` et
`JEAN.DUPONT` ne se résolvent pas. Sinon le compte est **signalé comme ambigu** et rien ne lui
est fait : ni création, ni adhésion, ni mot de passe. Même traitement qu'un échec isolé —
signalé, le lot continue, aucun concept nouveau n'entre dans le produit. Le doublon ne se lève
qu'à la main, sur le boîtier.

La même règle — un seul `casefold()`, un seul sens de comparaison, **et la même résolution d'une
collision de casse** — gouverne le rapprochement des noms de groupes (voir « Groupes ») : une
seule fonction pour les deux rapprochements de ce produit, comptes et groupes, plutôt que deux
règles à retenir et à tester séparément.

### Tableau de rapprochement

| Situation | Action |
|---|---|
| Compte du fichier, absent du boîtier | Créé, puis mot de passe, puis ses adhésions ajoutées |
| Compte du fichier, présent (casse quelconque) | Conservé tel quel ; ses adhésions manquantes ajoutées |
| Compte du fichier, présent sous deux graphies que seule la casse distingue | Correspondance exacte : ce compte-là ; sinon **signalé, rien ne lui est fait**, le lot continue |
| Compte du boîtier, absent du fichier (orphelin) | Conservé, **jamais touché**, compté dans le rapport |

Aucune suppression de compte, aucune désactivation, aucune correction d'attribut, aucun retrait
d'adhésion.

## Groupes

### Autorité conditionnée par la colonne

| Colonne `groupes` de la ligne | Adhésions du compte |
|---|---|
| **non vide** | les adhésions qu'elle nomme et qui manquent sont **ajoutées** |
| **vide** | **aucune** adhésion ajoutée |

La colonne vide ne signifie pas « aucun groupe » mais « je ne me prononce pas ». Elle ne protège
plus d'un retrait de masse — il n'y a plus de retrait ; elle dit simplement que le fichier ne
décrit pas les adhésions de ce compte, et l'outil n'agit que sur ce que le fichier décrit.

Les noms de groupes sont comparés **insensibles à la casse**, exactement comme les identifiants
de comptes (voir « Casse ») : même `casefold()`, même sens de comparaison. Un groupe `Compta`
sur le boîtier est reconnu par une ligne portant `compta` : aucun groupe n'est créé en double.
**L'outil s'adresse au groupe sous l'orthographe rendue par le boîtier**, jamais sous celle du
fichier — même règle, même raison que pour les comptes : c'est la seule graphie dont on sache
qu'elle existe chez lui. Un groupe du fichier absent sous toute casse est créé sous
l'orthographe **du fichier**, la seule disponible.

Risque assumé : si un boîtier porte réellement `Compta` et `compta` comme deux groupes distincts
et vivants, l'outil ne sait pas auquel des deux ajouter. Il ne s'arrête pas — signalé, ce groupe
n'est touché pour aucun compte, le lot continue (voir « Points non vérifiés », point 4, pour la
résolution exacte).

### Lecture des adhésions existantes

**Aucune commande SNS ne rend « les groupes d'un utilisateur ».** `USER GROUP LIST` rend des
groupes, pas leurs membres ; `USER SHOW` n'est pas prouvé les rendre. Le chemin est l'inverse :
**un `USER GROUP SHOW` par groupe cité dans le fichier et reconnu sur le boîtier**.

Un groupe que le fichier ne cite pas n'est pas lu : aucune adhésion n'y sera ajoutée, ses membres
n'apprennent rien. Un groupe cité mais absent du boîtier n'est pas lu non plus : il est à créer,
il n'a pas de membre.

La liste des groupes cités se calcule hors ligne, à partir des seules lignes valides à colonne
non vide — fonction pure, connue avant toute connexion, et c'est elle qui donne le majorant de la
phase de lecture. Le croisement avec `USER GROUP LIST` la réduit ensuite à ceux qui existent.
Chaque groupe retenu est interrogé avec l'identité que `USER GROUP LIST` a rendue, transmise
verbatim.

### Rattachement des membres

`USER GROUP SHOW` rend ses membres sous forme de **DN**. L'outil en extrait l'`uid` — le premier
composant, de forme `uid=<valeur>` — et le rapproche des comptes **que `USER LIST` a rendus**, par
la même clé de `casefold()` que partout ailleurs. Un membre ainsi rattaché à un compte que le
fichier cite ne fait naître aucune adhésion pour ce groupe : elle existe déjà.

Un membre que l'outil ne sait relier à **aucun compte connu du boîtier** — sous-groupe, compte
d'un autre annuaire, DN dont la forme n'est pas celle qu'on croit — ne déclenche **aucune
action** : l'outil n'a rien à lui faire. Il n'est pas signalé nommément, mais il est **compté** :
le plan porte le nombre de membres ainsi non rattachés (voir « Ce que le plan produit »), seul
moyen de savoir, sans lire le code, si l'hypothèse sur la forme du DN tient (voir « Points non
vérifiés », point 1). Le point de comparaison est bien la liste des comptes du boîtier, jamais
celle du fichier : un groupe peuplé contient forcément des gens légitimes qu'un CSV du jour ne
cite pas, et les compter noierait le signal dans le bruit qu'il doit détecter. La seule
conséquence sur l'écriture est un `ADDUSER` redondant si ce membre était en réalité un compte du
fichier (voir « Idempotence »).

## Lecture d'état : de 4 commandes à `4 + g`

La phase de lecture passe de quatre commandes fixes à :

| Lot de commandes | Nombre |
|---|---|
| `CONFIG LDAP LIST`, `CONFIG PASSWDPOLICY SHOW`, `USER LIST`, `USER GROUP LIST` | 4 |
| `USER GROUP SHOW` — un par groupe cité dans le fichier et reconnu sur le boîtier | `g` |

Le nombre exact de lectures est connu **après la quatrième commande** : `USER GROUP LIST` dit
lesquels des groupes cités existent déjà. Un majorant — le nombre de groupes distincts cités par
les lignes valides à colonne non vide — est connu dès la lecture du CSV, avant toute connexion.

Sur l'exemple de 200 comptes et cinq groupes cités, la lecture passe donc de 4 commandes à 9 :
la simulation reste ce qu'elle était en v1, l'affaire d'un instant. Conséquences concrètes :

- `NOMBRE_LECTURES = 4` cesse d'être une constante : le nombre de lectures se calcule.
- L'arrêt demandé est consulté **entre deux lectures d'inventaire** — entre deux
  `USER GROUP SHOW` —, jamais au milieu d'une commande. La fenêtre est courte, le point d'arrêt
  garde son sens : une lecture interrompue ne construit aucun plan et n'écrit rien ; son bilan
  est celui d'un arrêt demandé à zéro compte créé.
- Le motif d'armement du bouton *Arrêter* en simulation reste celui de la v1, et lui seul :
  l'état des deux boutons ne doit pas dépendre du mode. La simulation n'est pas devenue longue.

### Barre de progression

Elle couvre les lectures, en simulation comme en lot réel, et son total se fixe :

1. **après la quatrième commande**, à `4 + g` ; en simulation il ne bougera plus ;
2. **en lot réel, une fois le plan construit et l'écriture confirmée**, à
   `lectures accomplies + écritures planifiées`.

Le second temps n'existe qu'en lot réel et reste la **seule** croissance admise du total :
l'amendement de l'invariant v1 « le total ne croît jamais » survit, réduit à ce seul moment. Il
ne peut pas être supprimé — le budget des écritures dépend du plan, qui dépend de l'inventaire —
mais il est sans ambiguïté pour l'opérateur : il survient juste après qu'il a lu, dans la boîte
de confirmation, le nombre d'opérations qu'il autorise.

Après une reconnexion, le total ne peut que **baisser**, comme en v1 : le plan reconstruit ne
compte plus que le reste.

## Ce que le plan produit

En plus de la v1 (comptes à créer, comptes déjà présents, groupes à créer, rejets) :

| Sortie | Contenu |
|---|---|
| Adhésions à ajouter | pour un compte à créer comme pour un compte déjà là |
| **Nombre** d'orphelins | un entier, pas une liste |
| **Nombre** de membres non rattachés | un entier, pas une liste — même traitement, même raison |
| Ambiguïtés de casse signalées | groupes et comptes que deux graphies du boîtier revendiquent : ni créés, ni touchés, le lot continue |

### Orphelins : un nombre, et plus aucune liste

Le plan porte un **entier** et rien d'autre : aucun nom d'orphelin ne survit à la construction
du plan, donc rien ne peut réimprimer la liste par inadvertance. Sur un boîtier de 500 comptes
et un fichier de 20, la liste noyait le plan et les rejets — ce sur quoi l'opérateur doit se
prononcer avant d'écrire.

```
480 comptes du boîtier ne figurent pas dans le fichier : ils ne seront pas touchés.
```

### Membres non rattachés : le canari de l'hypothèse sur le DN

Le plan porte, à côté du nombre d'orphelins, le nombre de membres de groupe que le rattachement
(voir « Rattachement des membres ») n'a su relier à **aucun compte connu du boîtier** — même
choix que pour les orphelins, et pour la même raison : un entier, jamais la liste des membres en
cause.

**Sur un boîtier sain, ce nombre vaut zéro**, quel que soit le contenu du fichier : tout membre
d'un groupe est un compte que `USER LIST` a rendu, et l'outil dispose de cette liste entière. Un
membre légitime que le CSV du jour ne cite pas n'y compte donc pas — le compteur ne porte aucun
bruit, et c'est ce qui le rend lisible. Une forme de DN inattendue, elle, le fait bondir d'un
coup.

Quand ce nombre n'est pas nul, le journal porte une ligne dédiée, lisible sans connaître le
code :

```
7 membres de groupes n'ont pas pu être reconnus : les adhésions
correspondantes seront renvoyées à chaque exécution.
```

Elle dit vrai sans réserve, et c'est la définition ci-dessus qui le permet : un membre non
rattaché est une adhésion que l'outil ignore, et qu'il tiendra donc pour manquante à chaque
lecture — le fichier la décrivant, elle repartira à chaque exécution.

Cette ligne ne provoque ni arrêt, ni refus, ni écriture en moins : un boîtier dont les membres ne
se rattachent pas reste parfaitement utilisable, seule l'idempotence stricte s'en trouve dégradée
(voir « Idempotence »). C'est aussi, concrètement, le seul signal qui confirme ou infirme
l'hypothèse sur la forme du DN rendu par `USER GROUP SHOW` (voir « Points non vérifiés », point
1) : à zéro sur un boîtier dont les groupes cités ont des membres, elle tient ; non nul, elle est
fausse en tout ou partie. Aucune autre lecture n'est à faire de ce nombre — il n'y a pas de seuil
« normal » au-dessus de zéro.

### Groupes à créer

La liste se calcule désormais sur **toutes les adhésions à ajouter**, celles des comptes déjà
présents comprises — sans quoi leurs `USER GROUP ADDUSER` échoueraient sur un groupe inexistant.
Un groupe du fichier compte comme existant dès qu'il est reconnu sous quelque casse par
`USER GROUP LIST` (voir « Groupes ») ; c'est cette reconnaissance, jamais une égalité de chaîne,
qui l'écarte de cette liste. Le nombre de membres annoncé pour un groupe neuf est le nombre
d'adhésions à y ajouter.

Restent hors du calcul, comme en v1 : les groupes référencés seulement par des lignes rejetées,
et ceux référencés par un compte dont la colonne `groupes` est vide — ces deux cas ne produisent
aucune adhésion. S'y ajoute, pour la même raison, le groupe qu'un compte signalé ambigu est seul
à citer : ce compte ne reçoit aucune adhésion, ce groupe n'aurait aucun membre.

Le garde-fou v1 du groupe neuf à un seul membre est conservé tel quel.

### Le plan porte un travail par compte

Le plan expose, pour chaque compte concerné, **un seul objet** portant : le compte, s'il est à
créer ou déjà présent, ses adhésions à ajouter. Il ne porte plus deux listes parallèles de
comptes ; « à créer » et « déjà présent » se lisent sur ces travaux, et l'affichage du plan s'en
déduit.

La boucle d'écriture est ainsi **une seule boucle sur les comptes**, ce qui garde le point
d'arrêt là où la v1 l'a posé : entre deux comptes.

## Ordre d'écriture

Groupes manquants d'abord, comme en v1. Puis, **par compte** :

1. `USER CREATE` si le compte est absent ;
2. `USER PASSWORD` si et seulement si la création vient de réussir ;
3. les ajouts d'adhésion.

### Mot de passe : jamais sur un compte existant, et structurellement

Un compte déjà présent ne voit **jamais** son mot de passe touché. C'est la garantie que le
nouveau périmètre met le plus à l'épreuve : l'outil écrit désormais sur des comptes existants.

Aujourd'hui ce n'est pas une règle mais une conséquence du code : `USER PASSWORD` n'est
appelable qu'après un `USER CREATE` réussi dans la même itération. **La v2 exige que cela reste
structurel** :

- le plan ne porte **aucune** liste « comptes dont le mot de passe est à poser » ; la seule
  donnée qui autorise un `USER PASSWORD` est le succès, dans le tour de boucle courant, du
  `USER CREATE` du même compte ;
- il n'existe aucun chemin d'appel de `definir_mot_de_passe` depuis une branche traitant un
  compte existant ;
- un test le prouve : sur un boîtier où tous les comptes du fichier existent déjà, le journal
  d'appels du double ne contient aucun `definir_mot_de_passe`.

La génération du secret reste au moment de la création effective, comme en v1 : un compte qui
n'est pas créé ne consomme aucun secret.

### Arrêt demandé

La garantie v1 est inchangée : quand l'opérateur clique *Arrêter*, **le compte en cours va
jusqu'à son terme**, ses ajouts d'adhésion compris, et le suivant n'est pas entamé.

L'arrêt est consulté à quatre endroits, et nulle part ailleurs : entre deux lectures
d'inventaire, après l'affichage du plan — avant la demande de confirmation, comme en v1, pour
ne pas demander l'autorisation d'écrire un lot déjà arrêté —, entre deux groupes à créer, et
entre deux comptes.

### Garde-fou : la confirmation

La boîte de confirmation qui précède déjà tout lot réel annonce, **à côté du nombre de comptes
à créer, le nombre d'adhésions à ajouter** et le nombre de groupes neufs. C'est le seul endroit
où l'opérateur voit, avant qu'elle ne parte, l'ampleur de ce que l'outil va poser sur des
comptes qu'il n'a pas créés.

```
Ce lot va écrire sur le firewall 10.0.0.1.

12 comptes à créer, 1 groupe neuf.
31 adhésions à ajouter.

Rien n'a encore été écrit sur le firewall. Cet outil n'enlève rien : aucun
compte supprimé ni désactivé, aucune appartenance de groupe retirée.

Écrire maintenant ?
```

### Échec isolé

Un `USER GROUP ADDUSER` refusé est **signalé, et le lot continue**, sans réessais dédiés — règle
v1 inchangée : une adhésion manquante ne rend pas un compte inutilisable.

Un refus est mémorisé au même titre que les refus de création de la v1 : le plan reconstruit
après une reconnexion ne le rejoue pas, sans quoi le rapport porterait deux fois le même échec.

## Idempotence

**Rejouer le même fichier sur le même boîtier ne doit produire aucune écriture** : ni création,
ni ajout. Zéro commande d'écriture émise, pas « des commandes sans effet ». Elle est une
**exigence explicite**, éprouvée par un test dédié : deuxième exécution sur l'état laissé par la
première, journal d'appels du double exempt de toute écriture.

**Elle repose désormais sur le rattachement des membres rendus par `USER GROUP SHOW`**, et c'est
une dépendance qu'il faut écrire telle quelle. Si ce rattachement échoue — forme de DN
inattendue, `uid` absent du premier composant —, l'outil ne voit aucune adhésion existante et
réémet les mêmes `USER GROUP ADDUSER` à chaque exécution. L'état du boîtier ne change pas, le
boîtier absorbe ou refuse, mais des écritures partent et le journal les montre. Rien, dans ce
scénario, ne le dit à l'opérateur autrement : un lot qui réémet les mêmes `ADDUSER` à chaque
passage a toutes les apparences d'un lot qui réussit. **Le nombre de membres non rattachés (voir
« Ce que le plan produit ») est le seul signal de cette dégradation** — sans lui, l'hypothèse
fausse ne se révèle jamais.

C'est une dégradation progressive, pas un effondrement : plus le rattachement rate, plus il part
d'`ADDUSER` inutiles, et rien d'autre ne se détériore. Le produit ne promet donc pas une
idempotence que cette inconnue ne garantit pas — il promet qu'un rattachement raté coûte des
commandes redondantes et jamais un dommage. Le compteur qui l'annonce ne change rien à ce
comportement : ni arrêt, ni refus, ni écriture en moins — il informe, il n'intervient pas.

L'état se lit sur le boîtier à chaque exécution, jamais dans un fichier d'état local.

## Reprise après coupure réseau

La relecture qui suit une reconnexion doit reconstruire **tout** l'inventaire des adhésions :
`USER LIST`, `USER GROUP LIST`, puis les membres de chaque groupe cité. L'annuaire et le plancher
de politique restent ceux du premier état, comme en v1.

Réutiliser un inventaire d'adhésions antérieur à la coupure ferait rejouer des ajouts déjà
passés, ou manquer ceux qu'un autre chemin aurait posés entre-temps. Le coût de cette relecture
est celui décrit plus haut — quelques commandes ; le garde-fou v1 des tours de reconnexion sans
progrès ferme toujours la boucle.

## Architecture : ce qui change

La décision reste dans `plan.py`, **pur** : tout le rapprochement — casse, DN, adhésions,
orphelins — se calcule hors ligne et se teste sans firewall.

### `boitier.py` — une opération de plus au `Protocol`

| Opération | Commande | Rend |
|---|---|---|
| `lister_membres(groupe)` | `USER GROUP SHOW group=<identité rendue par LIST>` | les DN des membres |

`boitier_sdk.py` reste le seul module à importer le SDK, et reste mince : la surface non prouvée
doit être la plus petite possible. Le périmètre resserré la laisse à une seule commande nouvelle,
en lecture seule.

### `modele.py`

- `EtatBoitier` porte désormais : les comptes **et les groupes** du boîtier indexés par clé de
  casefold avec leur orthographe réelle, et les membres (DN) de chaque groupe cité par le
  fichier.
- `Plan` porte : un travail par compte (à créer ou déjà présent, adhésions à ajouter), les
  groupes à créer, le **nombre** d'orphelins, le **nombre** de membres non rattachés, et les
  ambiguïtés de casse signalées — groupes comme comptes. Un compte signalé ambigu n'a **pas** de
  travail : c'est ainsi que ni création, ni adhésion, ni mot de passe ne peuvent l'atteindre.
- `Plan.nombre_operations()` compte : les groupes à créer, puis par compte la création et le mot
  de passe s'il est à créer, plus ses ajouts.
- `comptes_a_creer` et `comptes_ignores` disparaissent au profit de ces travaux : un compte déjà
  présent n'est plus « ignoré », et le journal dit ce qui lui arrive plutôt que « ignoré ».
- `Rapport.comptes_prevus` reste figé à la construction du plan — il se compte désormais sur les
  travaux portant une création — et le bilan d'un arrêt demandé garde sa forme v1.

### `presentation.py`

Le journal affiche, par compte, ce que l'outil va lui faire — rien, ou des ajouts —, une ligne
par ambiguïté de casse signalée — groupe comme compte —, puis le nombre d'orphelins en une ligne,
puis, s'il n'est pas nul, le nombre de membres non rattachés (voir « Membres non rattachés : le
canari de l'hypothèse sur le DN »).

```
12 lignes lues, 0 rejet
Groupes à créer : compta_bis (1 membre)
dupont       : à créer, rattaché à compta, rh
Jean.Dupont  : présent — ajouté à rh
legrand      : présent — rien à faire
480 comptes du boîtier ne figurent pas dans le fichier : ils ne seront pas touchés.
```

## Tests

Tout ce qui suit tourne **sans firewall**.

### `plan.py`, pur

- un compte du boîtier orthographié `Jean.Dupont` est reconnu par une ligne `jean.dupont`, et
  toutes les opérations planifiées le visent sous `Jean.Dupont` ;
- un compte que deux graphies du boîtier revendiquent, sans correspondance exacte, est signalé et
  ne produit aucun travail — ni création, ni adhésion ; avec correspondance exacte, c'est cette
  graphie-là qui est visée et rien n'est signalé ;
- colonne `groupes` non vide : les adhésions manquantes sont planifiées ; colonne vide : aucune ;
- une adhésion déjà portée par le boîtier n'est pas replanifiée — le cœur de l'idempotence, dans
  la seule fonction pure qui la décide ;
- un membre dont le DN ne se rattache à aucun compte **du boîtier** ne provoque ni erreur ni
  action, mais est compté : le plan porte ce nombre, jamais la liste — même traitement que les
  orphelins ;
- un membre qui est un compte du boîtier **absent du fichier** n'est pas compté : le compteur
  vaut zéro sur un boîtier sain, quel que soit le contenu du fichier ;
- la liste des groupes à interroger ne retient que ceux des lignes valides à colonne non vide :
  ni ceux d'une ligne rejetée, ni ceux qu'aucune ligne ne cite ;
- orphelins comptés, jamais listés ;
- groupes à créer calculés sur toutes les adhésions à ajouter.

### `BoitierMemoire`, qui doit grandir

Il gagne la lecture des membres d'un groupe.

**Et il doit porter des cas que le code doit savoir traiter** — comptes dont la casse diffère,
membres non rattachables. Un double qui ne peut pas mettre le code en défaut ne prouve rien ; ce
défaut a déjà coûté cher sur ce produit.

Deux exigences en découlent, sans lesquelles le double serait complaisant :

- **il rend des DN, jamais des identifiants** : ses membres de groupe sont stockés et rendus
  sous une forme `uid=<orthographe du boîtier>,ou=users,dc=…`. Un code qui comparerait un
  identifiant à un membre échouerait sur chaque test au lieu d'en passer quelques-uns ;
- **il se construit avec des comptes à casse arbitraire** (`Jean.Dupont`), avec **deux comptes
  que seule la casse distingue** (`Jean.Dupont` et `jean.dupont`), et avec des membres dont le DN
  ne désigne aucun compte qu'il connaît.

### `execution.py` contre le double

- l'ordre par compte : création, mot de passe, ajouts ;
- arrêt demandé pendant un compte : ce compte va à son terme, ses ajouts compris, le suivant
  n'est pas entamé ;
- arrêt demandé pendant l'inventaire : aucun plan, aucune écriture, bilan d'arrêt ;
- **idempotence** : deuxième exécution sur l'état laissé par la première, aucune écriture ;
- **aucun `definir_mot_de_passe`** quand tous les comptes du fichier existent déjà ;
- un ajout refusé est signalé et le lot continue ;
- reprise après coupure : l'inventaire des adhésions est relu, les refus ne sont pas rejoués.

Comme en v1 : on teste des comportements, pas des rouages. Les tests observent l'état final du
double et les événements émis.

**Analyse statique avant tout commit** : `ruff check .` puis `mypy`.

**Cahier de recette** : les cas ci-dessus y sont repris, plus ceux que seul un boîtier peut
trancher — la forme réelle de la réponse de `USER GROUP SHOW`, celle de `USER GROUP LIST`, et la
vérification qu'une seconde exécution n'émet aucune écriture sur un boîtier réel.

## Ce qui est vérifié

Dans `cmd.complete` — le fichier de complétion livré par Stormshield avec le SDK, identique à
celui de leur dépôt officiel, qui liste les 1420 verbes acceptés par `serverd` :

- `USER REMOVE` **existe** — et n'entrera pas dans l'outil ;
- **aucun verbe de désactivation de compte n'existe.** Il n'y avait donc pas de troisième voie
  entre « supprimer » et « conserver » : la recherche a été faite, et le choix de conserver
  n'est pas un repli faute d'avoir cherché.

## Points non vérifiés

Extraits de la documentation SNS, **non lus en source brute** — Cloudflare bloque l'accès
direct aux pages. Chacun est porté par un comportement qui échoue proprement, jamais par une
hypothèse cachée.

**1. La forme des membres rendus par `USER GROUP SHOW`.** C'est le seul point structurant de la
v2. La documentation donne une section `[Group]` avec les membres en champs répétés `member=`,
`member_2=`, …, **sous forme de DN** dont le premier composant est `uid=`. *Si l'hypothèse est
fausse* : aucun membre n'est rattaché, l'outil croit toutes les adhésions manquantes et émet des
`USER GROUP ADDUSER` redondants que le boîtier absorbe ou refuse. **L'idempotence stricte est
perdue**, et c'est le nombre de membres non rattachés (voir « Ce que le plan produit ») qui la
rend visible sans attendre un second relancement : dès la première lecture, ce compteur dit
combien de membres le boîtier a rendus sans que l'outil sache les relier à un compte **de la
liste que ce même boîtier lui a donnée** — il vaut donc zéro tant que l'hypothèse tient, et
saute d'un coup dès qu'elle est fausse ; sans lui, un lot qui réémet les mêmes ajouts a toutes
les apparences d'un lot qui réussit. **Aucun dommage n'en découle** : rien n'est retiré, rien
n'est écrasé, aucun compte ne change d'état. Le repli tient dans une fonction isolée :
l'extraction de l'`uid` depuis un DN est le seul endroit à corriger quand la forme réelle sera
connue. **C'est ce compteur, et lui seul, qui confirme ou
infirme cette hypothèse — c'est la première chose que le cahier de recette observera au premier
boîtier**, avant même de juger l'idempotence sur pièce. Non tranché également : ce que rend `USER GROUP SHOW` sur un groupe sans membre — section vide ou refus ; les
deux se traitent comme « aucun membre connu pour ce groupe ».

**2. La forme rendue par `USER GROUP LIST`** — nom de groupe ou DN. Héritée de la v1, mais elle
pèse davantage ici puisque cette identité sert aussi d'argument à `USER GROUP SHOW`. *Si ce sont
des DN* : les groupes du fichier ne s'y retrouvent pas, l'outil planifie leur création, le
boîtier la refuse (« existe déjà »), l'échec est signalé et le lot continue ; les adhésions sont
alors adressées par le nom du fichier, comme en v1. Rien n'est détruit.

**3. La sensibilité à la casse de l'`uid` côté SNS.** Non tranchée : signaux contradictoires, et
la page de l'annexe A du guide n'a pas pu être lue. **Rendue sans objet par construction** :
l'outil n'adresse un compte existant que sous l'orthographe que `USER LIST` lui a rendue, et
n'émet plus aucune commande citant un compte sous une autre graphie. Reste le cas où `USER LIST`
rendrait deux comptes que seule la casse distingue. *Si l'hypothèse est fausse* — un boîtier réel
porte `Jean.Dupont` **et** `JEAN.DUPONT` —, la clé de casefold les confond et l'outil ne sait pas
auquel écrire. **Il ne s'arrête pas** : même règle qu'au point 4 pour les groupes, et pour la
même raison — l'ordre dans lequel le boîtier rend sa liste n'est garanti par rien, et trancher
sur la première rendue ferait écrire sur un compte différent d'une exécution à l'autre.
Correspondance exacte avec l'identifiant du fichier — toujours en minuscules : c'est ce compte-là.
Sinon le compte est signalé comme ambigu, il n'est ni créé — il existe, sous deux graphies — ni
rattaché à quoi que ce soit, et son mot de passe n'est pas touché ; le lot continue. Le doublon
ne peut être levé qu'à la main, sur le boîtier.

**4. La sensibilité à la casse des noms de groupe côté SNS.** Non tranchée, comme celle de
l'`uid` (point 3) : rien n'indique si `Compta` et `compta` peuvent coexister comme deux groupes
vivants et distincts. *Si l'hypothèse est fausse* — un boîtier réel porte un tel doublon —
`USER GROUP LIST` rend deux groupes que la clé de casefold confond, et l'outil ne sait pas
auquel ajouter. **Il ne s'arrête pas** sur ce motif : un boîtier mal rangé ne doit pas priver les
deux cents autres comptes du lot. Si la graphie de la colonne du fichier correspond
**exactement** à l'un des deux groupes, c'est celui-là qui est adressé — l'opérateur a écrit ce
nom-là, il existe tel quel sur le boîtier. Sinon, la collision est signalée et ce groupe n'est
touché pour aucun compte ; il n'est pas créé non plus, puisqu'il existe déjà, sous deux graphies.
Même traitement qu'un échec isolé : signalé, le lot continue — aucun concept nouveau n'entre dans
le produit, et c'est mot pour mot la règle du point 3 pour les comptes : **une seule règle pour
les deux rapprochements**. Le doublon ne peut être levé qu'à la main, sur le boîtier.

Les points non vérifiés de la v1 restent ouverts et inchangés.

## Hors périmètre v2

- **Retrait d'appartenance de groupe** (`USER GROUP DELUSER`, `USER GROUP REMOVEFROM`). Les deux
  verbes existent ; aucun n'entre dans l'outil. Motif complet en « Pourquoi la v2 n'enlève
  rien » : le coût de lecture qu'un retrait sûr impose — 224 commandes contre 9 — n'est pas payé.
- **Signalement des divergences d'attributs** (`nom`, `prenom`). Capacité que ce document
  promettait avant le resserrement du périmètre : elle était le sous-produit du `USER SHOW` par
  compte, qui n'existait que pour sécuriser les retraits. Sans lui elle est impossible,
  `USER LIST` ne rendant que des identifiants. L'outil ne lit plus les attributs d'un compte
  existant, donc ne peut plus en signaler l'écart.
- **Suppression de comptes** (`USER REMOVE`). Existe, n'entrera pas dans l'outil.
- **Désactivation de comptes.** Aucun verbe n'existe ; il n'y a rien à mettre en œuvre.
- **Correction des attributs** (`USER UPDATE`). Jamais envoyé.
- **Modification du mot de passe d'un compte existant.** Structurellement impossible, par
  exigence de cette spec.
- **Suppression de groupes.** L'outil ne crée et ne peuple des groupes que dans le sens où le
  fichier les décrit.
- **Boîtiers déclarant plusieurs annuaires LDAP.** Arrêt net, comme en v1.
- **Blacklists** — groupes d'objets réseau et d'URL. Suite prévue du dépôt.
- Tout le hors-périmètre v1 non repris ici demeure : signature du `.exe`, `cabundle`,
  mémorisation des identifiants, journal sur disque, écriture de la politique de mot de passe.
