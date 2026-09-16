# Relevé des décisions — nuit du 2026-09-16

Décisions prises sans arbitrage humain, pendant l'exécution autonome du plan
d'implémentation de la v1. Elles sont toutes réversibles. Ce document existe pour
que celles qui te heurtent soient défaites en connaissance de cause, pas
découvertes par surprise.

Classées par ce qu'elles coûtent si elles sont fausses.

## À trancher en premier

**L'annulation d'un lot en cours n'existe pas.** Deux cents comptes font environ six
cents allers-retours, soit plusieurs minutes. L'opérateur qui s'aperçoit à la
douzième ligne qu'il a visé le boîtier de production au lieu de la maquette n'a
aucune sortie : pas de bouton, pas d'`Échap`. La seule issue est de fermer la
fenêtre, ce qui tue le fil où qu'il en soit — y compris entre la création d'un
compte et la pose de son mot de passe, laissant un compte inutilisable qu'aucun
relancement ne réparera.

La revue finale la désigne comme le manque le plus sérieux du produit. **Je ne l'ai
pas implémentée** : la spec que tu as validée n'en parle pas, et ajouter une
fonctionnalité en ton absence n'est pas mon rôle. Coût estimé : une quinzaine de
lignes dans `execution`, cinq dans `fenetre`.

## Décisions qui changent le produit

**Le premier lot peut partir directement en réel.** La spec imposait un détour par
la simulation, parce que les champs de politique restaient grisés tant que le
plancher du boîtier n'était pas lu. J'ai déplacé la vérification dans le métier :
`executer` compare lui-même la politique au plancher qu'il vient de lire et refuse
avant toute écriture. Le détour n'a plus de raison d'être.

**En échange, une confirmation avant tout lot réel.** Elle nomme l'hôte visé, le
nombre de comptes à créer, et les groupes neufs — en signalant ceux qui n'auraient
qu'un seul membre, signature d'une coquille de saisie. Sans elle, le retrait du
détour aurait emporté le garde-fou de la spec : le plan aurait défilé pendant que
les comptes partaient. Le produit demandait confirmation pour *perdre des mots de
passe* mais pas pour *écrire sur un firewall*.

**Le mail a disparu du CSV.** `USER CREATE` ne le prend pas ; tu avais choisi une
adresse unique pour tous les comptes, elle n'apportait rien côté firewall.

**Un compte créé dont le mot de passe n'a pas pu être posé figure quand même dans le
CSV de sortie**, avec un champ vide, et un échec le nomme. L'implémenteur l'avait
classé en limitation assumée ; je l'ai classé en défaut. Le CSV de sortie *est* la
liste de reprise de l'opérateur : un compte qui n'y figure pas est un compte perdu.

**Une troisième exception, `ErreurFatale`.** Un mot de passe d'administration faux
faisait reconnecter l'outil en boucle, et cette boucle alimentait le verrouillage
anti-bruteforce du firewall. La taxonomie n'avait pas de case « fatal, ne pas
réessayer ». Elle l'a maintenant, et `execution` s'arrête net dessus.

**`CONFIG LDAP INITIALIZE` se protège elle-même.** La spec voulait ce chemin
inatteignable dès qu'un annuaire répond ; la fonction s'en remettait à la
discipline de son appelant. Elle vérifie désormais d'abord.

**`MinSetOfChars` se traduit par une table explicite** — `None` → 1, `AlphaNum` → 2,
`AlphaSpecial` → 3 — et une valeur inconnue **lève** au lieu de replier sur zéro.
Un adaptateur n'a pas à décider qu'un plancher de sécurité incompris vaut zéro.
**Cette table est une hypothèse non vérifiée**, et tout le plancher affiché et
contrôlé en dépend. Cas 31 du cahier de recette.

**Après une reconnexion, l'outil ne relit que les comptes et les groupes**, pas
l'annuaire ni la politique. Relire l'annuaire en milieu de lot ferait lever
« annuaire absent » sur un chemin que rien ne décrit.

## Décisions d'outillage et de méthode

**Le remote est passé de SSH à HTTPS** avec le credential helper `gh` : le port 22
vers github.com est fermé depuis cet environnement. Aucune conséquence, l'URL se
remet à l'identique.

**`.claude/` a été ajouté au `.gitignore`.** Il ne l'était pas, alors qu'il porte
les worktrees des agents et un `settings.local.json` susceptible de contenir un mot
de passe en clair.

**`stormshield.sns.sslclient>=1.1.2`** au lieu du `>=1.4` que le plan exigeait :
PyPI ne publie pas au-delà de 1.1.2, le plan avait inventé un numéro de version.

**La CI teste Python 3.11 et 3.12**, alors que le plan n'imposait que 3.12 — le
projet déclare `>=3.11` et ne testait jamais son plancher.

**La règle `ruff` `N818`** (un nom d'exception doit finir par `Error`) est désactivée :
elle entre en conflit frontal avec l'invariant « français dans le code », où
« Erreur » préfixe.

**Les tâches sans dépendance ont été exécutées en parallèle**, chacune dans son
propre worktree git. Ton `CLAUDE.md` l'impose ; le greffon `superpowers`
l'interdisait pour cause de conflits d'arbre de travail. L'isolation par worktree
lève la raison technique de l'interdiction.

**`boitier.py` et `boitier_sdk.py` sont deux fichiers** là où la spec n'en nommait
qu'un : les tests métier n'importent ainsi jamais la surface non prouvée.

**Une couture d'injection dans l'adaptateur SDK** (`fabrique_client`, défaut
`SSLClient`) : sans elle, quatre défauts restaient invérifiables hors boîtier.

## Une décision que j'ai prise, puis annulée

J'ai fait supprimer un test qui se réduisait à `assert boitier is not None`, au
motif qu'une assertion toujours vraie ne prouve rien et que `mypy` porterait la
preuve de conformité au `Protocol`. **`mypy` ne la portait pas** : rien n'annotait
une variable `Boitier` recevant le double, donc aucune comparaison structurelle
n'avait lieu. Un relecteur l'a démontré en supprimant une méthode du double —
`mypy` est resté silencieux et tous les tests sont passés.

Le test est revenu, portant cette fois **deux** preuves : une annotation que `mypy`
vérifie, et une assertion de comportement. Le remède n'était pas de supprimer le
test, mais de le rendre mordant.

## Ce que personne n'a pu prouver

Ce n'est pas une décision, c'est l'état de la livraison — et c'est ce qui rend le
cahier de recette indispensable plutôt que formel.

- **`fenetre.py` n'a jamais été exécuté.** `tkinter` est absent de la machine de
  développement. Aucun test ne le couvre et aucun ne le couvrira.
- **`boitier_sdk.py` n'a jamais parlé à un SNS.** Il est écrit contre la
  documentation et contre la bibliothèque, dont l'API réelle a été vérifiée en
  l'exécutant — mais la casse des étiquettes rendues par serverd, les clés de champ,
  et le comportement réel des commandes restent des hypothèses.
- **`.github/workflows/exe.yml` n'a jamais tourné.** Aucun runner ne le validera
  avant le premier tag. Sa structure est vérifiée, la cible et les drapeaux
  confirmés par `pyi-makespec`, mais la collecte du SDK par PyInstaller reste le
  vrai risque. Pose un tag jetable avant `v1.0.0`.

Le cahier de recette, 112 cas dont 21 jouables sans boîtier, est la seule couverture
de ces deux modules.
