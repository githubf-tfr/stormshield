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

**Cette garantie tombe.** La v2 retire des appartenances de groupe à des comptes qui existaient
avant elle. C'est un changement de nature du produit : d'injecteur, il devient outil
d'alignement. Le fichier fait autorité sur ce qu'il décrit.

Ce qui reste vrai, et qui borne l'abandon :

| Garantie v1 | v2 |
|---|---|
| Aucun compte supprimé | **inchangée** — `USER REMOVE` n'entrera pas dans l'outil |
| Aucun compte désactivé | **inchangée** — aucun verbe de désactivation n'existe (voir « Ce qui est vérifié ») |
| Aucun attribut d'un compte existant modifié | **inchangée** — les divergences sont signalées, jamais corrigées |
| Le mot de passe d'un compte existant n'est jamais touché | **inchangée, et désormais exigée structurellement** |
| Aucune appartenance de groupe retirée | **abandonnée** — voir « Groupes » |

Le fichier fait autorité **sur ce qu'il décrit, jamais sur ce qu'il ne mentionne pas**. C'est
la règle qui gouverne tout le reste : un CSV tronqué à la copie, un export RH partiel, une
colonne oubliée ne doivent rien pouvoir détruire.

## Ce que la v2 corrige

Quatre défauts que la v1 assumait tant que le boîtier était vierge, et qui interdisent la
reprise d'un boîtier existant :

1. **La casse des identifiants n'est pas reconnue.** `Jean.Dupont` créé à la main dans
   l'interface web n'est pas vu par la ligne `jean.dupont` : l'outil tente de le créer.
2. **Les appartenances de groupe ne bougent jamais** pour un compte existant.
3. **Les orphelins noient le rapport.** 500 comptes listés au-dessus du plan et des rejets,
   c'est-à-dire au-dessus de ce sur quoi l'opérateur doit se prononcer avant d'écrire.
4. **Les attributs divergents sont ignorés**, et même invisibles : `USER LIST` ne rend que des
   identifiants.

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
reconnu par la ligne `jean.dupont` reçoit ses `USER GROUP ADDUSER` et ses `USER SHOW` sous
`Jean.Dupont`. Cela rend **sans objet, pour l'outil**, la question non tranchée de la
sensibilité à la casse de l'`uid` côté SNS : l'outil ne demande jamais au boîtier de retrouver
un compte sous une orthographe qu'il n'a pas lui-même rendue.

Un compte **à créer** n'a pas d'orthographe côté boîtier : il est créé, puis adressé, sous
l'identifiant du fichier — en minuscules, comme en v1.

La même règle — un seul `casefold()`, un seul sens de comparaison — gouverne désormais le
rapprochement des noms de groupes (voir « Groupes ») : une seule fonction pour les deux
rapprochements de ce produit, comptes et groupes, plutôt que deux règles à retenir et à tester
séparément.

### Tableau de rapprochement

| Situation | Action |
|---|---|
| Compte du fichier, absent du boîtier | Créé, puis mot de passe, puis ses adhésions ajoutées |
| Compte du fichier, présent (casse quelconque) | Conservé tel quel ; ses adhésions alignées ; ses attributs divergents signalés |
| Compte du boîtier, absent du fichier (orphelin) | Conservé, **jamais touché**, compté dans le rapport |

Aucune suppression de compte, aucune désactivation, aucune correction d'attribut.

## Attributs

`nom` et `prenom` du fichier sont comparés à ceux que le boîtier rend pour le compte. Toute
divergence est **signalée, jamais corrigée** : l'outil n'envoie aucun `USER UPDATE`.

La comparaison est exacte, sur les champs déjà débarrassés de leurs espaces de tête et de fin
par la lecture du CSV. Une comparaison trop stricte coûte une ligne de journal ; aucune
divergence ne déclenche d'écriture, donc le faux positif est sans conséquence.

Motif du refus de corriger : la syntaxe générale de `USER UPDATE` est connue
(`operation=(add|mod|del) attribute=<nom> value=<v>`), mais **seul l'attribut `mail` est
démontré par un exemple** ; rien ne confirme que `name` ou `gname` y soient accessibles.
Écrire à l'aveugle sur l'état civil d'un compte que quelqu'un a saisi à la main est exactement
le geste que le produit refuse.

Un compte dont les attributs n'ont pas pu être lus (voir « Points non vérifiés ») ne produit
aucune divergence : l'absence d'information n'est pas une information.

## Groupes

### Autorité conditionnée par la colonne

| Colonne `groupes` de la ligne | Adhésions du compte |
|---|---|
| **non vide** | autorité complète : les adhésions manquantes sont ajoutées, celles que le fichier ne donne pas sont **retirées** |
| **vide** | **aucune** adhésion touchée : ni ajout, ni retrait |

La colonne vide est le garde-fou contre le fichier dont toute la colonne serait vide — une
colonne perdue à l'export, un séparateur mal choisi —, qui retirerait sinon tout le monde de
tout. Elle ne signifie pas « aucun groupe » mais « je ne me prononce pas ».

**Le retrait ne concerne que les comptes du fichier.** Un compte absent du fichier, ou dont la
ligne a été rejetée, ne perd jamais aucune adhésion : le fichier ne le décrit pas.

Les noms de groupes sont comparés **insensibles à la casse**, exactement comme les identifiants
de comptes (voir « Casse ») : même `casefold()`, même sens de comparaison. Un groupe `Compta`
sur le boîtier est reconnu par une ligne portant `compta` : aucun groupe n'est créé, aucune
adhésion n'est de ce fait ajoutée ni retirée. **L'outil s'adresse au groupe sous l'orthographe
rendue par le boîtier**, jamais sous celle du fichier — même règle, même raison que pour les
comptes : c'est la seule graphie dont on sache qu'elle existe chez lui. Un groupe du fichier
absent sous toute casse est créé sous l'orthographe **du fichier**, la seule disponible.

Risque assumé : si un boîtier porte réellement `Compta` et `compta` comme deux groupes distincts
et vivants, l'outil les confond (voir « Points non vérifiés », point 7).

### Lecture des adhésions existantes

**Aucune commande SNS ne rend « les groupes d'un utilisateur ».** `USER GROUP LIST` rend des
groupes, pas leurs membres ; `USER SHOW` n'est pas prouvé les rendre. Le chemin est l'inverse :
**un `USER GROUP SHOW` par groupe du boîtier**.

Les groupes du fichier ne suffisent pas : on cherche précisément les appartenances que le
fichier ne mentionne pas. Le balayage porte donc sur **tous** les groupes rendus par
`USER GROUP LIST`.

Chaque groupe est interrogé avec l'identité que `USER GROUP LIST` a rendue, transmise verbatim.

### Membres non rattachés

`USER GROUP SHOW` rend ses membres sous forme de **DN**. Un membre dont le DN ne correspond à
aucun compte connu de l'outil est **signalé et jamais retiré**.

C'est l'asymétrie qui protège : un rapprochement raté ne doit jamais provoquer un retrait,
seulement un silence visible. Les membres non rattachés sont des sous-groupes, des comptes
d'un autre annuaire, ou des DN dont la forme n'est pas celle qu'on croit — dans les trois cas,
les retirer serait une destruction fondée sur une incompréhension.

## Lecture d'état : de 4 commandes à `4 + G + M`

La phase de lecture passe de quatre commandes fixes à :

| Lot de commandes | Nombre |
|---|---|
| `CONFIG LDAP LIST`, `CONFIG PASSWDPOLICY SHOW`, `USER LIST`, `USER GROUP LIST` | 4 |
| `USER GROUP SHOW` — un par groupe rendu par `USER GROUP LIST` | `G` |
| `USER SHOW` — un par compte du fichier **reconnu sur le boîtier** | `M` |

`M` porte sur les comptes reconnus, non sur toutes les lignes du fichier : un `USER SHOW` sur
un compte absent est un échec garanti, du bruit dans le journal, et n'apprendrait rien — le
plan de ce compte est déjà connu, c'est une création. Le majorant reste le nombre de lignes
valides du fichier, et c'est ce majorant qui donne l'ordre de grandeur ci-dessous.

Le nombre de lectures est donc connu **après la quatrième commande** : `USER LIST` donne `M`,
`USER GROUP LIST` donne `G`. La barre de progression compte ces lectures comme des opérations à
part entière (voir « Barre de progression »).

### Pourquoi un `USER SHOW` par compte

Il rend **deux choses d'un coup** :

1. **Le DN exact du compte.** Le rapprochement des membres devient une **comparaison de DN à
   DN, mot pour mot**, sans aucune hypothèse sur la forme du DN — les deux côtés viennent du
   boîtier lui-même. L'inconnue disparaît au lieu d'être contenue. Aucune reconstruction de DN
   à partir d'un `uid` et d'un suffixe supposé n'existe dans le produit.
2. **Ses attributs.** Sans cette commande, le signalement des divergences serait impossible :
   `USER LIST` ne rend que des identifiants.

### Le coût, en face

Une simulation de 200 comptes sur un boîtier de 20 groupes passe de **4 commandes à 224**, soit
quelques dizaines de secondes au lieu d'un instant. **La simulation cesse d'être gratuite.**
C'est le prix de la reprise d'un boîtier existant, et il est payé en lecture seule.

Conséquences concrètes :

- `NOMBRE_LECTURES = 4` cesse d'être une constante : le nombre de lectures se calcule.
- L'arrêt demandé est consulté **entre deux lectures d'inventaire** — entre deux
  `USER GROUP SHOW`, entre deux `USER SHOW` —, jamais au milieu d'une commande. Une lecture
  interrompue ne construit aucun plan et n'écrit rien ; son bilan est celui d'un arrêt demandé
  à zéro compte créé.
- Cela rend **vrai, rétroactivement, le motif d'armement du bouton *Arrêter* en simulation**,
  que la v1 avait dû corriger comme faux : la simulation est désormais réellement longue. Le
  motif d'interface retenu par la v1 — l'état des deux boutons ne doit pas dépendre du mode —
  reste valable et suffit à lui seul.

### Barre de progression

Elle couvre les lectures, en simulation comme en lot réel, et son total se fixe en deux temps :

1. **après la quatrième commande**, à `4 + G + M` — le nombre de lectures, seul connu à ce
   stade ; en simulation il ne bougera plus ;
2. **en lot réel, une fois le plan construit et l'écriture confirmée**, à
   `lectures accomplies + écritures planifiées`.

C'est la **seule** croissance admise du total, et elle amende l'invariant v1 « le total ne croît
jamais ». Elle est sans ambiguïté pour l'opérateur : elle survient juste après qu'il a lu, dans
la boîte de confirmation, le nombre d'opérations qu'il autorise. Le budget des écritures ne peut
pas être connu plus tôt — il dépend du plan, qui dépend de l'inventaire complet —, et laisser la
plus longue phase du produit avancer sans total serait pire.

Après une reconnexion, le total ne peut que **baisser**, comme en v1 : le plan reconstruit ne
compte plus que le reste.

## Ce que le plan produit

En plus de la v1 (comptes à créer, comptes déjà présents, groupes à créer, rejets) :

| Sortie | Contenu |
|---|---|
| Adhésions à ajouter | pour un compte à créer comme pour un compte déjà là |
| Adhésions à retirer | uniquement pour les comptes du fichier à colonne non vide dont la description a été lue |
| Divergences d'attributs | identifiant, attribut, valeur du fichier, valeur du boîtier |
| **Nombre** d'orphelins | un entier, pas une liste |
| Membres non rattachés | groupe et DN, pour signalement |

### Orphelins : un nombre, et plus aucune liste

Le plan porte un **entier** et rien d'autre : aucun nom d'orphelin ne survit à la construction
du plan, donc rien ne peut réimprimer la liste par inadvertance. Sur un boîtier de 500 comptes et un fichier de 20, la liste noyait le plan et les
rejets — ce sur quoi l'opérateur doit se prononcer avant d'écrire.

```
480 comptes du boîtier ne figurent pas dans le fichier : ils ne seront pas touchés.
```

### Groupes à créer

La liste se calcule désormais sur **toutes les adhésions à ajouter**, celles des comptes déjà
présents comprises — sans quoi leurs `USER GROUP ADDUSER` échoueraient sur un groupe inexistant.
Un groupe du fichier compte comme existant dès qu'il est reconnu sous quelque casse par
`USER GROUP LIST` (voir « Groupes ») ; c'est cette reconnaissance, jamais une égalité de chaîne,
qui l'écarte de cette liste. Le nombre de membres annoncé pour un groupe neuf est le nombre
d'adhésions à y ajouter.

Restent hors du calcul, comme en v1 : les groupes référencés seulement par des lignes rejetées,
et ceux référencés par un compte dont la colonne `groupes` est vide ou dont la description n'a
pas pu être lue — ces deux cas ne produisent aucune adhésion.

Le garde-fou v1 du groupe neuf à un seul membre est conservé tel quel.

### Le plan porte un travail par compte

Le plan expose, pour chaque compte concerné, **un seul objet** portant : le compte, s'il est à
créer ou déjà présent, ses adhésions à ajouter, ses adhésions à retirer. Il ne porte plus deux
listes parallèles de comptes ; « à créer » et « déjà présent » se lisent sur ces travaux, et
l'affichage du plan s'en déduit.

La boucle d'écriture est ainsi **une seule boucle sur les comptes**, ce qui garde le point
d'arrêt là où la v1 l'a posé — entre deux comptes — et rend impossible qu'un retrait d'un compte
parte avant les ajouts d'un autre.

## Ordre d'écriture

Groupes manquants d'abord, comme en v1. Puis, **par compte** :

1. `USER CREATE` si le compte est absent ;
2. `USER PASSWORD` si et seulement si la création vient de réussir ;
3. les **ajouts** d'adhésion ;
4. les **retraits** d'adhésion.

**Les retraits en dernier, délibérément.** Si le lot s'interrompt entre 3 et 4, le compte est
dans ses anciens groupes *et* dans les nouveaux : état trop permissif, visible dans le journal,
corrigé par un simple relancement. L'ordre inverse le laisserait dans aucun des deux — sans
accès, sans que personne ne s'en aperçoive avant que l'utilisateur ne se plaigne. Entre un
excès de droits pendant quelques minutes et une privation d'accès silencieuse, on choisit le
premier.

### Mot de passe : jamais sur un compte existant, et structurellement

Un compte déjà présent ne voit **jamais** son mot de passe touché.

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

La garantie v1 s'étend : quand l'opérateur clique *Arrêter*, **le compte en cours va jusqu'à
son terme — et son terme inclut désormais ses retraits**. Un compte laissé entre ses ajouts et
ses retraits serait précisément l'état trop permissif décrit plus haut ; le mener à son terme
coûte quelques commandes et l'évite.

L'arrêt est consulté à quatre endroits, et nulle part ailleurs : entre deux lectures
d'inventaire, après l'affichage du plan — avant la demande de confirmation, comme en v1, pour
ne pas demander l'autorisation d'écrire un lot déjà arrêté —, entre deux groupes à créer, et
entre deux comptes.

### Garde-fou : la confirmation

La boîte de confirmation qui précède déjà tout lot réel annonce, **à côté du nombre de comptes
à créer, le nombre de retraits d'adhésion prévus** — ainsi que le nombre d'ajouts et de groupes
neufs. Le retrait est la seule opération de ce produit qui enlève quelque chose à quelqu'un :
il ne doit pas se découvrir dans le journal après coup.

```
Ce lot va écrire sur le firewall 10.0.0.1.

12 comptes à créer, 1 groupe neuf.
31 adhésions à ajouter, 4 adhésions à retirer.

Rien n'a encore été écrit sur le firewall. Aucun compte ne sera supprimé
ni désactivé : cet outil ne retire que des appartenances de groupe.

Écrire maintenant ?
```

### Échec isolé

Un retrait refusé est **signalé, et le lot continue** — même traitement qu'un `ADDUSER` refusé
en v1, sans réessais dédiés : une adhésion de trop ne rend pas un compte inutilisable.

La documentation mentionne qu'on ne peut pas retirer le dernier membre d'un groupe. Ce cas ne
reçoit aucun traitement particulier : il se manifestera comme un refus nommé du boîtier, porté
tel quel au rapport. Anticiper un message qu'on n'a jamais lu produirait une branche morte.

Un refus est mémorisé au même titre que les refus de création de la v1 : le plan reconstruit
après une reconnexion ne le rejoue pas, sans quoi le rapport porterait deux fois le même échec.

## Idempotence

**Rejouer le même fichier sur le même boîtier ne doit produire aucune écriture** : ni création,
ni ajout, ni retrait. Zéro commande d'écriture émise, pas « des commandes sans effet ».

C'est la propriété la plus facile à perdre en passant d'un injecteur à un outil qui aligne :
il suffit qu'un DN se compare mal, qu'une casse se perde, qu'un membre ne se rattache pas, et
chaque exécution réémet les mêmes ajouts. Elle est donc une **exigence explicite**, éprouvée par
un test dédié : deuxième exécution sur l'état laissé par la première, journal d'appels du double
exempt de toute écriture.

L'état se lit sur le boîtier à chaque exécution, jamais dans un fichier d'état local.

## Reprise après coupure réseau

La relecture qui suit une reconnexion doit reconstruire **tout** l'inventaire des adhésions :
`USER LIST`, `USER GROUP LIST`, les membres de chaque groupe, puis les comptes du fichier
reconnus. L'annuaire et le plancher de politique restent ceux du premier état, comme en v1.

Réutiliser un inventaire d'adhésions antérieur à la coupure reviendrait à calculer des retraits
contre un état qu'on ne connaît plus. Le coût de cette relecture est celui décrit plus haut ; le
garde-fou v1 des tours de reconnexion sans progrès ferme toujours la boucle.

## Architecture : ce qui change

La décision reste dans `plan.py`, **pur** : tout le rapprochement — casse, DN, adhésions,
divergences, orphelins — se calcule hors ligne et se teste sans firewall.

### `boitier.py` — trois opérations de plus au `Protocol`

| Opération | Commande | Rend |
|---|---|---|
| `lister_membres(groupe)` | `USER GROUP SHOW group=<identité rendue par LIST>` | les DN des membres |
| `decrire_utilisateur(identifiant)` | `USER SHOW user=<orthographe du boîtier>` | DN, nom, prénom |
| `retirer_membre(groupe, identifiant)` | `USER GROUP DELUSER "<groupe>" <uid>` | — |

`boitier_sdk.py` reste le seul module à importer le SDK, et reste mince : la surface non prouvée
doit être la plus petite possible.

Le groupe est cité comme à l'ajout et à la création — citer d'un côté et pas de l'autre rendrait
un groupe nommé `compta bis` inadressable au retrait alors qu'il est adressable à l'ajout.

### `modele.py`

- `EtatBoitier` porte désormais : les comptes **et les groupes** du boîtier indexés par clé de
  casefold avec leur orthographe réelle, la description (DN, nom, prénom) des comptes du fichier
  reconnus, et les membres (DN) de chaque groupe.
- `Plan` porte : un travail par compte (à créer ou déjà présent, ajouts, retraits), les groupes
  à créer, les divergences d'attributs, le **nombre** d'orphelins, les membres non rattachés.
- `Plan.nombre_operations()` compte : les groupes à créer, puis par compte la création et le mot
  de passe s'il est à créer, plus ses ajouts, plus ses retraits.
- `comptes_a_creer` et `comptes_ignores` disparaissent au profit de ces travaux : un compte déjà
  présent n'est plus « ignoré », et le journal dit ce qui lui arrive plutôt que « ignoré ».
- `Rapport.comptes_prevus` reste figé à la construction du plan — il se compte désormais sur les
  travaux portant une création — et le bilan d'un arrêt demandé garde sa forme v1.
- `Rapport.echecs` accueille l'opération `USER GROUP DELUSER` comme les autres : aucune
  structure nouvelle pour un retrait refusé.

### `presentation.py`

Le journal affiche, par compte existant, ce que l'outil va lui faire — rien, des ajouts, des
retraits —, puis les divergences, puis les membres non rattachés, puis le nombre d'orphelins en
une ligne.

```
12 lignes lues, 0 rejet
Groupes à créer : compta_bis (1 membre)
dupont       : à créer, rattaché à compta, rh
Jean.Dupont  : présent — ajouté à rh, retiré de compta
legrand      : présent — attributs divergents : nom « Legrand » sur le fichier,
               « LEGRAND » sur le boîtier (non corrigé)
Groupe rh : 1 membre non rattaché à un compte connu (non retiré)
480 comptes du boîtier ne figurent pas dans le fichier : ils ne seront pas touchés.
```

### Compte dont la description n'a pas pu être lue

Un compte reconnu sur le boîtier dont le `USER SHOW` échoue est **signalé**, et ses adhésions ne
sont **pas touchées** — ni ajout, ni retrait — exactement comme si sa colonne `groupes` était
vide. Sans DN, on ne sait pas quelles adhésions il a déjà : ajouter rejouerait à chaque
exécution ce qui existe peut-être (idempotence perdue), retirer serait fondé sur rien. Ses
attributs ne sont pas comparés. Le lot continue.

## Tests

Tout ce qui suit tourne **sans firewall**.

### `plan.py`, pur

- un compte du boîtier orthographié `Jean.Dupont` est reconnu par une ligne `jean.dupont`, et
  toutes les opérations planifiées le visent sous `Jean.Dupont` ;
- colonne `groupes` non vide : ajouts et retraits calculés ; colonne vide : **aucun** des deux ;
- un compte absent du fichier ne perd aucune adhésion, même si un compte du fichier partage un
  de ses groupes ;
- un membre dont le DN ne correspond à aucun compte connu n'est jamais retiré et figure dans les
  membres non rattachés ;
- divergences d'attributs relevées, et aucune écriture planifiée pour elles ;
- orphelins comptés, jamais listés ;
- groupes à créer calculés sur toutes les adhésions à ajouter.

### `BoitierMemoire`, qui doit grandir

Il gagne : la lecture des membres d'un groupe, le retrait d'un membre, la description d'un
compte.

**Et il doit porter des cas que le code doit savoir traiter** — comptes dont la casse diffère,
attributs divergents, membres non rattachables. Un double qui ne peut pas mettre le code en
défaut ne prouve rien ; ce défaut a déjà coûté cher sur ce produit.

Deux exigences en découlent, sans lesquelles le double serait complaisant :

- **il rend des DN, jamais des identifiants** : ses membres de groupe sont stockés et rendus
  sous une forme `uid=<orthographe du boîtier>,ou=users,dc=…`, et sa description de compte rend
  le même DN. Un code qui comparerait un identifiant à un membre échouerait sur chaque test au
  lieu d'en passer quelques-uns ;
- **il se construit avec des comptes à casse arbitraire** (`Jean.Dupont`), des attributs
  qu'aucune ligne du fichier ne reproduit, et des membres dont le DN ne désigne aucun compte
  qu'il connaît.

### `execution.py` contre le double

- l'ordre par compte : création, mot de passe, ajouts, **puis** retraits ;
- arrêt demandé pendant un compte : ce compte va à son terme, **retraits compris**, le suivant
  n'est pas entamé ;
- arrêt demandé pendant l'inventaire : aucun plan, aucune écriture, bilan d'arrêt ;
- **idempotence** : deuxième exécution sur l'état laissé par la première, aucune écriture ;
- **aucun `definir_mot_de_passe`** quand tous les comptes du fichier existent déjà ;
- un retrait refusé est signalé et le lot continue ;
- reprise après coupure : l'inventaire des adhésions est relu, les refus ne sont pas rejoués.

Comme en v1 : on teste des comportements, pas des rouages. Les tests observent l'état final du
double et les événements émis.

**Analyse statique avant tout commit** : `ruff check .` puis `mypy`.

**Cahier de recette** : les cas ci-dessus y sont repris, plus ceux que seul un boîtier peut
trancher — la forme réelle des réponses de `USER SHOW` et de `USER GROUP SHOW`, la syntaxe
acceptée de `USER GROUP DELUSER`, le refus sur le dernier membre d'un groupe, et le temps réel
d'une simulation de 200 comptes.

## Ce qui est vérifié

Dans `cmd.complete` — le fichier de complétion livré par Stormshield avec le SDK, identique à
celui de leur dépôt officiel, qui liste les 1420 verbes acceptés par `serverd` :

- `USER GROUP DELUSER` **existe** ;
- `USER GROUP REMOVEFROM` **existe** ;
- `USER REMOVE` **existe** — et n'entrera pas dans l'outil ;
- **aucun verbe de désactivation de compte n'existe.** Il n'y avait donc pas de troisième voie
  entre « supprimer » et « conserver » : la recherche a été faite, et le choix de conserver
  n'est pas un repli faute d'avoir cherché.

## Points non vérifiés

Extraits de la documentation SNS, **non lus en source brute** — Cloudflare bloque l'accès
direct aux pages. Chacun est porté par un comportement qui échoue proprement, jamais par une
hypothèse cachée.

**1. La forme de la réponse de `USER SHOW`.** Syntaxe connue :
`USER SHOW user=<uid>|<DN> [attribute=<attr>]`. Les clés et sections de sa réponse ne le sont
pas. *Si l'hypothèse est fausse* : la description est illisible ou la commande est refusée →
le compte tombe dans le cas « description non lue » ci-dessus — signalé, adhésions non touchées,
attributs non comparés, lot poursuivi. Aucune écriture fausse n'en découle.

**2. La forme des membres rendus par `USER GROUP SHOW`.** La documentation donne une section
`[Group]` avec les membres en champs répétés `member=`, `member_2=`, …, **sous forme de DN**.
*Si l'hypothèse est fausse* : aucun membre n'est reconnu → **aucun retrait n'est émis** (le
silence est du bon côté), mais les ajouts sont recalculés identiques à chaque exécution et
**l'idempotence est perdue de façon visible** — les mêmes `ADDUSER` repartent, refusés ou non,
et le journal le montre au premier relancement. Défaut bruyant, jamais destructeur. Non tranché
également : ce que rend `USER GROUP SHOW` sur un groupe sans membre — section vide ou refus ;
les deux se traitent comme « aucun membre connu pour ce groupe ».

**3. Les arguments exacts de `USER GROUP DELUSER`.** Le verbe est **attesté** ; sa forme
positionnelle `USER GROUP DELUSER "<groupe>" <uid>` est **déduite par symétrie** avec `ADDUSER`,
déjà en service et cité de la même façon. *Si l'hypothèse est fausse* : le boîtier refuse la
commande, le retrait est signalé, le lot continue, **aucune adhésion n'est perdue par erreur**.
Le repli est documenté et tient en une ligne d'un seul module : la forme nommée
`USER GROUP REMOVEFROM group=<nom>|<DN> member=<uid>|<DN>`, qui accepte en outre un sous-groupe.
C'est précisément pour cela que la construction de la commande est une fonction isolée de
`boitier_sdk.py`.

**4. La sensibilité à la casse de l'`uid` côté SNS.** Non tranchée : signaux contradictoires, et
la page de l'annexe A du guide n'a pas pu être lue. **Rendue sans objet par construction** :
l'outil n'adresse un compte existant que sous l'orthographe que le boîtier lui a rendue.
Résidu : `USER SHOW user=<uid>` est appelé avec l'orthographe issue de `USER LIST` — même source,
donc même orthographe. *Si `USER LIST` rendait autre chose qu'un `uid` adressable* (un DN, par
exemple), `USER SHOW` échouerait et le compte tomberait dans le cas du point 1.

**5. La forme rendue par `USER GROUP LIST`** — nom de groupe ou DN. Héritée de la v1, mais elle
pèse davantage ici puisque cette identité sert aussi d'argument à `USER GROUP SHOW`. *Si ce sont
des DN* : les groupes du fichier ne s'y retrouvent pas, l'outil planifie leur création, le
boîtier la refuse (« existe déjà »), l'échec est signalé et le lot continue ; les adhésions sont
alors adressées par le nom du fichier, comme en v1. Rien n'est détruit.

**6. Le temps réel d'une lecture de 224 commandes.** L'ordre de grandeur annoncé — quelques
dizaines de secondes — vient du modèle « une commande, un aller-retour » ; aucune mesure n'existe.
*Si c'est plusieurs minutes* : rien ne casse, le bouton *Arrêter* est armé pendant toute la
lecture et la barre avance à chaque commande.

**7. La sensibilité à la casse des noms de groupe côté SNS.** Non tranchée, comme celle de
l'`uid` (point 4) : rien n'indique si `Compta` et `compta` peuvent coexister comme deux groupes
vivants et distincts. *Si l'hypothèse est fausse* — un boîtier réel porte un tel doublon —
`USER GROUP LIST` rend deux groupes que la clé de casefold confond. L'outil ne choisit pas au
hasard entre les deux : une collision de clé de casefold parmi les groupes rendus par
`USER GROUP LIST` est un **arrêt net, signalé, avant toute lecture de membres et toute
écriture** — aucun plan n'est construit sur un inventaire ambigu. Le doublon ne peut être levé
qu'à la main, sur le boîtier.

Les points non vérifiés de la v1 restent ouverts et inchangés.

## Hors périmètre v2

- **Suppression de comptes** (`USER REMOVE`). Existe, n'entrera pas dans l'outil.
- **Désactivation de comptes.** Aucun verbe n'existe ; il n'y a rien à mettre en œuvre.
- **Correction des attributs** (`USER UPDATE`). Divergences signalées, jamais corrigées.
- **Modification du mot de passe d'un compte existant.** Structurellement impossible, par
  exigence de cette spec.
- **Suppression de groupes**, y compris un groupe devenu vide après des retraits. L'outil ne
  crée et ne peuple des groupes que dans le sens où le fichier les décrit.
- **Boîtiers déclarant plusieurs annuaires LDAP.** Arrêt net, comme en v1.
- **Blacklists** — groupes d'objets réseau et d'URL. Suite prévue du dépôt.
- Tout le hors-périmètre v1 non repris ici demeure : signature du `.exe`, `cabundle`,
  mémorisation des identifiants, journal sur disque, écriture de la politique de mot de passe.
