# Relevé des décisions — nuit du 2026-09-17, v2

Décisions prises sans arbitrage humain pendant l'exécution autonome du plan de la
v2 — l'alignement sur un boîtier déjà peuplé. Elles sont toutes réversibles. Ce
document existe pour que celles qui te heurtent soient défaites en connaissance de
cause, pas découvertes par surprise.

Le relevé de la v1 est dans `docs/2026-09-16-releve-des-decisions.md`.

## Ma faute, et ce qu'elle a coûté

**J'ai découpé les dix cahiers des charges avant que le plan ne soit réparé.**

Le plan a été écrit, jugé inexécutable par un scan, réparé — il est passé de 2456 à
2917 lignes —, puis corrigé une fois encore. J'avais extrait les briefs au premier
état, et je ne les ai jamais réextraits. Les quatre premières tâches ont donc été
implémentées et revues sur des cahiers amputés de 7 % à 37 % :

| Tâche | Périmé | Correct | Perdu |
|---|---|---|---|
| T1 | 331 | 354 | 7 % |
| T2 | 254 | 289 | 12 % |
| T3 | 234 | 309 | 24 % |
| T4 | 977 | 1175 | 17 % |
| **T5** | **465** | **733** | **37 %** |
| T6 à T10 | — | — | 13 % à 28 % |

Le coût n'a pas été théorique. Le brief périmé de T4 avait perdu exactement les
quatre prescriptions que sa revue a trouvées manquantes, dont un défaut `Critique` :
un membre non rattaché supprimait une adhésion planifiée — l'inverse de ce que la
spec promet — et **aucun test ne tombait** si on le corrigeait. L'implémenteur en a
trouvé une cinquième en relisant la version corrigée : `presentation.py` devait
porter des textes définitifs là où le brief périmé demandait du provisoire, et
**T6 n'aurait pas rattrapé**, son propre brief lui disant « ne pas y toucher ».
Deux formules provisoires seraient parties en production sans qu'aucun test ne
tombe.

Sur T3, la troncature avait fait pire que retirer une consigne : elle avait laissé
à sa place une porte de sortie invitant à « suivre l'existant plutôt que ce qui est
écrit ici ». L'implémenteur s'y est engouffré et a retiré une assertion.

**Ce qui a sauvé la situation, c'est la revue par tâche.** Le plan versionné était
juste ; mes briefs ne l'étaient pas ; et les relecteurs ont comparé les deux d'eux-
mêmes au lieu de s'en tenir à ce qu'on leur donnait. Aucune tâche n'a eu à être
reprise.

Trois autres erreurs de ma part, plus petites : j'ai repris d'une version périmée
du plan une contrainte d'ordonnancement que sa réparation avait explicitement
levée ; j'ai répété pendant tout le cadrage que « la simulation n'est plus
instantanée », ce que la spec contredit — je traînais un chiffre du design
abandonné ; et j'ai laissé sans correction une ligne de compteur du `KANBAN.md`
qu'aucune tâche du plan ne couvrait.

## Décisions qui changent le produit

**Les retraits d'adhésion sont abandonnés.** C'était la décision de cadrage, prise
avec toi : leur coût de lecture faisait passer l'état de `4 + g` à `4 + G + M`
commandes. Ce que la v2 perd avec eux, et qu'il faut savoir : **le signalement des
divergences de nom**, qui était un sous-produit de la lecture par compte. La spec
te le promettait une heure avant d'y renoncer ; c'est écrit comme tel.

**Le registre des refus compare désormais à la clé, pas à la graphie.** Défaut
trouvé par la revue finale : le sort d'une écriture dépendait de la casse rendue
par le boîtier. Un compte refusé puis relu sous une autre graphie voyait ses
adhésions partir ; sous la même, non.

**Un `USER CREATE` refusé nomme au journal les adhésions qu'il n'a pas tentées.**
Elles n'apparaissaient nulle part. En v1 c'était juste — sans création, pas
d'adhésion — mais en v2 un refus « existe déjà » prouve que le compte existe.

**Je n'ai pas pris la décision de fond qui va avec** : tenter ces adhésions malgré
le refus. L'outil n'ajoute que, donc ce serait cohérent, mais c'est un choix de
conception qui t'appartient.

**Les comptes et groupes ambigus remontent jusqu'à la boîte de confirmation et au
bilan.** Ils n'atteignaient ni l'une ni l'autre : le rapport disait « 0 échec »
pendant qu'un compte du fichier ne recevait rien. Ils ne sont pas versés aux
échecs, et c'est délibéré — un échec porte une opération et un motif rendus par le
boîtier, or ici aucune commande n'est partie.

**Trois messages disaient « le compte en cours est allé à son terme » sur des
chemins où aucun compte n'était entamé.** Corrigés l'un après l'autre, à trois
tâches d'écart : le bilan, le texte du clic, puis le journal métier.

## Décisions de méthode

**J'ai suspendu l'exécution pour faire réparer le plan.** Un scan l'avait déclaré
inexécutable : trois tâches ne pouvaient pas se clore avec `mypy` vert, vingt-cinq
tests de la v1 cassaient dont neuf jamais mentionnés, deux corps de tests écrits
dans le plan étaient factuellement faux. Le réparateur a porté une copie hors dépôt
du code v1 jusqu'à la v2 complète, suite verte : les blocs du plan n'étaient plus
écrits de mémoire. C'est la garantie qui manquait au plan de la v1.

**J'ai fait passer un second scan sur le plan réparé**, à ta demande. Il a trouvé
quatre régressions introduites par la réparation elle-même, dont une de fond.

**Chaque tâche devait pouvoir se clore avec la suite verte et les deux outils
verts.** Trois n'y arrivaient pas : le `Protocol` et son implémentation SDK ont dû
voyager dans la même tâche, faute de quoi `mypy` échouait entre les deux.

## Ce que personne n'a pu prouver

- **`fenetre.py` n'a jamais été exécuté.** `tkinter` est absent de cette machine.
  Le diff de la v2 sur ce fichier n'est **que des docstrings** — vérifié.
- **`boitier_sdk.py` n'a jamais parlé à un SNS.** La forme des membres rendus par
  `USER GROUP SHOW` reste la dernière hypothèse structurante du produit.
- **Le compteur des membres non rattachés est aveugle à un mauvais *format* de
  réponse.** Il détecte une mauvaise *forme de DN*. Si le boîtier rend un format
  inattendu, ou répète `member=` sans suffixe, des membres sont perdus en silence
  et le compteur vaut zéro — c'est-à-dire « tout va bien ». Seul le texte brut de
  la réponse garde la vérité, et le cas 123 du cahier est écrit pour ça.
- **La troncature de `USER LIST` n'était évoquée nulle part.** Trouvée par la revue
  finale. Si serverd tronque ou pagine, les comptes au-delà sont vus absents, leur
  création est refusée « existe déjà », et leurs adhésions sont écartées — à chaque
  exécution, définitivement, puisque la troncature est persistante. C'est le seul
  scénario où les défauts du chemin de refus cessent d'être réparables par un
  relancement.
- **Le `.exe` n'a jamais été lancé.** La construction passe, ce qui prouve que
  PyInstaller collecte le paquet ; rien ne prouve que la fenêtre s'ouvre.
