# Cahier de recette — injection d'utilisateurs LDAP v1

Recette fonctionnelle, **exécutée par un humain**, sur le `.exe` publié en release et sur un
firewall SNS de maquette.

## Pourquoi ce cahier n'est pas une formalité

Deux modules entiers du produit n'ont **jamais été exécutés** :

- `stormshield_utilisateurs/fenetre.py` — la machine de développement n'a pas `tkinter`.
  Aucun test ne l'importe, aucun ne l'importera. Ce cahier est sa **seule** couverture.
- `stormshield_utilisateurs/boitier_sdk.py` — écrit contre la documentation SNS et contre le
  SDK réellement installé, mais **il n'a jamais parlé à un vrai boîtier**. Plusieurs de ses
  choix sont des hypothèses, listées en section F ; elles se confirment ou se démentent ici.

Les tests unitaires (231, marqueur `firewall` exclu) prouvent que le code fait ce qui a été
écrit. Ce cahier prouve que le produit fait ce qu'on attend. Les cas déjà couverts en
unitaire y figurent donc **volontairement**.

Un cas dont on ne peut pas dire s'il a réussi est un cas inutile : chaque *Attendu*
ci-dessous est formulé pour se trancher sans interprétation.

## Comment s'en servir

- **Boîtier : non** — se joue sur un poste Windows seul. 21 cas.
- **Boîtier : oui** — exige un SNS de maquette joignable. 89 cas.
- **110 cas au total.**

Jouer d'abord les cas sans boîtier (sections B à D), puis les sections E et suivantes.
Consigner le verdict de chaque cas : **OK**, **KO** ou **NJ** (non joué, avec le motif).
Un KO se reporte en ticket ; un cas qui ne peut pas être provoqué se note **NJ**, jamais OK.

> **Rien de ce cahier ne contient d'adresse, de compte ni de mot de passe réels.** L'hôte de
> maquette est désigné par `sns-maquette.invalid` ; remplacer par l'adresse réelle au moment
> de jouer, sans jamais la réécrire ici.

## Matière d'essai à préparer

Fichiers CSV à créer avant de commencer. Tous en `identifiant;nom;prenom;groupes`, en-tête
comprise. Les groupes `compta-recette` et `lecture-recette` ne doivent **pas** exister sur le
boîtier au premier passage.

| Fichier | Contenu |
|---|---|
| `lot-nominal.csv` | 3 comptes (`jean.dupont`, `marie.martin`, `paul.durand`), les 2 groupes `compta-recette` et `lecture-recette`, un compte sans groupe |
| `lot-accents.csv` | `lot-nominal.csv` **réenregistré par Excel en français** (« CSV (séparateur : point-virgule) »), avec des noms accentués : `Désiré`, `Noël`, `Élodie` |
| `lot-sans-prenom.csv` | `lot-nominal.csv` amputé de la colonne `prenom` |
| `lot-colonnes-melees.csv` | mêmes données, colonnes dans l'ordre `groupes;prenom;nom;identifiant`, plus une colonne `service` en trop |
| `lot-casse.csv` | une ligne `Jean.Dupont;Dupont;Jean;` |
| `lot-doublon.csv` | deux lignes, `jean.dupont` et `JEAN.DUPONT`, noms différents |
| `lot-rejets.csv` | une ligne à identifiant vide, une à nom vide, une à identifiant `jean dupont` (espace), une à identifiant `rené` (accent) |
| `lot-groupes-sales.csv` | une ligne dont la colonne groupes vaut `compta-recette||compta-recette| |lecture-recette` |
| `lot-groupe-un-membre.csv` | un seul compte neuf, rattaché au seul groupe neuf `solo-recette` |
| `lot-groupe-sur-compte-present.csv` | un compte **déjà présent** sur le boîtier, rattaché au groupe neuf `fantome-recette` |
| `lot-uid-interdit.csv` | une ligne `admin;Admin;Admin;` plus deux lignes valides encadrantes |
| `lot-groupe-guillemet.csv` | deux comptes valides, groupe `compta"bis` |
| `lot-groupe-espace.csv` | deux comptes valides, groupe `compta bis recette` |
| `lot-groupe-retour-ligne.csv` | un compte valide, groupe contenant un saut de ligne (champ entre guillemets CSV, `compta\nbis`) |
| `lot-nom-compose.csv` | une ligne `p.delatour;De La Tour;Pierre;` |
| `lot-nom-guillemet.csv` | trois lignes valides, dont `d.oconnor;O"Connor;Diane;` — le guillemet double est dans le **nom**, pas dans un groupe |
| `lot-200.csv` | 200 comptes neufs, chacun rattaché à un groupe parmi trois |

---

# A. Préalables

Aucun cas numéroté : à vérifier avant de commencer.

- Le firewall de maquette est joignable depuis le poste, et **c'est une maquette** : la
  recette crée des comptes et des groupes qu'il faudra supprimer ensuite.
- Le compte d'administration utilisé a le privilège de créer utilisateurs et groupes.
- L'état de départ du boîtier est relevé : liste des comptes, liste des groupes, valeurs de
  `CONFIG PASSWDPOLICY SHOW`. Plusieurs cas s'y comparent.

---

# B. Empaquetage et premier lancement

**1 — La release porte un `.exe`** · boîtier : non
*Objectif* : le seul chemin de construction du binaire fonctionne de bout en bout.
*Départ* : dépôt à jour sur la branche d'intégration, aucun tag `v1.0.0`.
*Actions* : poser le tag `v1.0.0` et le pousser ; suivre le workflow `exe` dans l'onglet
Actions du dépôt.
*Attendu* : le job `construire` est vert sur `windows-latest`, et la release `v1.0.0` porte
un unique fichier joint `injection-utilisateurs-sns.exe`, de taille non nulle. Les notes de
la release mentionnent SmartScreen.
*Verdict* : OK / KO —

**2 — SmartScreen avertit, et l'outil s'ouvre quand même** · boîtier : non
*Objectif* : l'avertissement documenté dans le `README.md` est bien celui que l'opérateur
rencontre, et il est contournable.
*Départ* : poste Windows n'ayant jamais exécuté ce binaire.
*Actions* : télécharger le `.exe` depuis la release, double-cliquer.
*Attendu* : la boîte bleue « Windows a protégé votre ordinateur » apparaît. Après
« Informations complémentaires » puis « Exécuter quand même », la fenêtre de l'outil s'ouvre.
*Verdict* : OK / KO —

**3 — Aucune console noire** · boîtier : non
*Objectif* : `--windowed` fait son office.
*Départ* : cas 2 joué.
*Actions* : observer l'écran pendant et après l'ouverture de la fenêtre.
*Attendu* : **aucune fenêtre de console** n'apparaît, ni au lancement, ni derrière la
fenêtre de l'outil, ni à sa fermeture.
*Verdict* : OK / KO —

**4 — L'outil ne dépose rien sur le poste** · boîtier : non
*Objectif* : aucun fichier de journal, aucune configuration, aucun secret résiduel.
*Départ* : relever le contenu du dossier du `.exe`, du dossier du CSV d'entrée, de
`%TEMP%` et de `%APPDATA%` avant lancement.
*Actions* : ouvrir l'outil, le fermer, recomparer les quatre emplacements.
*Attendu* : aucun fichier nouveau porté par l'outil — en particulier aucun `.log`, aucun
`.ini`, aucun `.csv`. Les dossiers temporaires du dépaquetage PyInstaller (`_MEI…`)
disparaissent à la fermeture.
*Verdict* : OK / KO —

**5 — Démarrage impossible : l'outil le dit** · boîtier : non
*Objectif* : sur un poste sans bureau utilisable, l'exécutable fenêtré ne doit **jamais** se
terminer en silence.
*Départ* : une session Windows sans bureau interactif (Server Core, ou exécution sous un
compte de service sans session ouverte). **Noter NJ si aucun tel poste n'est disponible.**
*Actions* : lancer le `.exe`.
*Attendu* : une **boîte de message système** s'affiche (ou, à défaut de bureau, l'exécution
se solde par un code de sortie 1 avec le texte « L'interface n'a pas pu démarrer. » nommant
la cause). Le cas KO est : rien ne se passe du tout, sans message ni code d'erreur.
*Verdict* : OK / KO / NJ —

---

# C. Ouverture de la fenêtre et état initial

**6 — Titre de la fenêtre** · boîtier : non
*Objectif* : l'opérateur identifie l'outil dans sa barre des tâches.
*Départ* : outil ouvert.
*Actions* : lire la barre de titre.
*Attendu* : exactement « Injection d'utilisateurs SNS ».
*Verdict* : OK / KO —

**7 — Politique grisée tant que rien n'a été lu** · boîtier : non
*Objectif* : l'outil ne laisse pas régler une politique qu'il n'a encore confrontée à rien.
*Départ* : outil fraîchement ouvert, aucune connexion.
*Actions* : tenter de modifier la longueur, puis chacune des quatre cases de classes.
*Attendu* : le champ de longueur et les quatre cases **ne réagissent pas** et sont
visiblement grisés. L'étiquette au-dessous lit « politique du boîtier : inconnue tant
qu'aucune lecture n'a eu lieu ».
*Verdict* : OK / KO —

**8 — Réglages par défaut** · boîtier : non
*Objectif* : les deux garde-fous sont actifs et le bouton d'export est muet.
*Départ* : outil fraîchement ouvert.
*Actions* : lire l'état des deux cases et du bouton d'enregistrement.
*Attendu* : **Simulation cochée**, **Vérifier le certificat cochée**, bouton *Enregistrer les
mots de passe…* **grisé**.
*Verdict* : OK / KO —

**9 — Le libellé du certificat est lisible en entier** · boîtier : non
*Objectif* : le coût du contournement est écrit à l'endroit où on le décoche.
*Départ* : outil ouvert, fenêtre à sa taille d'ouverture.
*Actions* : lire le libellé de la case certificat ; réduire puis agrandir la fenêtre.
*Attendu* : le texte complet est visible, replié sur plusieurs lignes si nécessaire, jamais
tronqué par des points de suspension. Il mentionne que les identifiants et les mots de passe
générés transitent dans une **session interceptable**.
*Verdict* : OK / KO —

**10 — Aucun identifiant n'est mémorisé** · boîtier : non
*Objectif* : l'outil ne stocke rien, conformément à l'invariant du projet.
*Départ* : outil ouvert.
*Actions* : saisir hôte, compte et mot de passe ; fermer la fenêtre ; rouvrir l'outil.
*Attendu* : les trois champs sont **vides**. Aucun menu déroulant ne propose la saisie
précédente.
*Verdict* : OK / KO —

**11 — Le mot de passe est masqué à la saisie** · boîtier : non
*Objectif* : le caractère de masquage retenu (`•`) s'affiche correctement sous Windows.
*Départ* : outil ouvert.
*Actions* : saisir dix caractères dans le champ Mot de passe.
*Attendu* : dix symboles de masquage identiques et lisibles s'affichent. Le cas KO est un
carré vide, un point d'interrogation ou un caractère de remplacement — à signaler, le
masquage devra passer à `*`.
*Verdict* : OK / KO —

**12 — *Parcourir…* remplit le champ Fichier CSV** · boîtier : non
*Objectif* : l'opérateur n'a pas à taper un chemin.
*Départ* : outil ouvert, champ Fichier CSV vide.
*Actions* : cliquer *Parcourir…*, choisir `lot-nominal.csv`, valider ; recommencer et
**annuler** le sélecteur.
*Attendu* : après validation, le champ porte le chemin complet du fichier. Après annulation,
le champ **conserve** sa valeur précédente et n'est pas vidé.
*Verdict* : OK / KO —

---

# D. Refus avant tout envoi

Ces cas se jouent **sans boîtier joignable** : tout ce qui est vérifié ici l'est avant la
moindre connexion. Renseigner `sns-maquette.invalid` dans le champ Hôte suffit.

**13 — Un champ manquant est nommé** · boîtier : non
*Objectif* : un lot incomplet ne part pas, et l'opérateur sait quoi corriger.
*Départ* : outil ouvert, les quatre champs renseignés (hôte, compte, mot de passe, CSV).
*Actions* : vider **l'hôte**, cliquer *Lancer* ; le remettre, vider **le compte**, *Lancer* ;
puis **le mot de passe** ; puis **le fichier CSV**.
*Attendu* : à chaque fois une boîte « Lancement refusé » nommant le champ vide —
respectivement « l'hôte du firewall n'est pas renseigné », « le compte d'administration n'est
pas renseigné », « le mot de passe du compte d'administration n'est pas renseigné », « aucun
fichier CSV n'est désigné ». **Rien n'est écrit au journal** et aucune connexion n'est tentée.
*Verdict* : OK / KO —

**14 — Plusieurs champs vides sont tous nommés** · boîtier : non
*Objectif* : l'opérateur ne corrige pas les champs un par un, relance après relance.
*Départ* : outil ouvert, tous les champs vides.
*Actions* : cliquer *Lancer*.
*Attendu* : une seule boîte « Lancement refusé », listant **les quatre** obstacles, une
ligne chacun.
*Verdict* : OK / KO —

**15 — Un hôte vide ne provoque aucune tentative de connexion** · boîtier : non
*Objectif* : lever la réserve de la tâche 10, qui craignait trois reconnexions inutiles sur
un hôte vide.
*Départ* : outil ouvert, compte / mot de passe / CSV renseignés, hôte laissé **vide** (ou ne
contenant que des espaces).
*Actions* : cliquer *Lancer*, chronométrer.
*Attendu* : la boîte « Lancement refusé » apparaît **immédiatement** (moins d'une seconde).
Aucun délai de six secondes ni ligne « reconnexion n/3 échouée » : la réserve est levée.
*Verdict* : OK / KO —

**16 — Colonne manquante : le fichier entier est refusé** · boîtier : non
*Objectif* : une structure fausse ne laisse pas partir un lot partiel.
*Départ* : les quatre champs renseignés, CSV = `lot-sans-prenom.csv`.
*Actions* : cliquer *Lancer*.
*Attendu* : boîte « Fichier invalide » dont le texte **nomme `prenom`**. Le journal reste
vide, aucune connexion n'est tentée, aucune ligne du fichier n'est lue.
*Verdict* : OK / KO —

**17 — Fichier illisible** · boîtier : non
*Objectif* : un chemin erroné se distingue d'un fichier mal formé.
*Départ* : les quatre champs renseignés, champ CSV pointant un chemin **inexistant** saisi à
la main.
*Actions* : cliquer *Lancer*.
*Attendu* : boîte « **Fichier illisible** » — et non « Fichier invalide » — portant le
message du système. Rien ne part.
*Verdict* : OK / KO —

**18 — Ordre des colonnes libre, colonnes en trop ignorées** · boîtier : non
*Objectif* : un export métier réordonné ou enrichi reste exploitable.
*Départ* : les quatre champs renseignés, CSV = `lot-colonnes-melees.csv`, hôte
`sns-maquette.invalid` (la lecture du fichier précède la connexion).
*Actions* : cliquer *Lancer*, lire le journal avant l'échec de connexion.
*Attendu* : le journal porte « 3 lignes lues, 0 rejet » **avant** la boîte d'arrêt réseau :
l'ordre des colonnes et la colonne `service` n'ont gêné ni la structure ni les valeurs.
*Verdict* : OK / KO —

---

# E. Simulation sur boîtier

**19 — Simulation : le plan s'affiche, rien n'est écrit** · boîtier : oui
*Objectif* : le mode par défaut lit le boîtier sans y toucher.
*Départ* : boîtier de maquette ne portant **aucun** des 3 comptes ni des 2 groupes de
`lot-nominal.csv` ; état du boîtier relevé (section A).
*Actions* : renseigner les quatre champs, laisser **Simulation cochée**, cliquer *Lancer* ;
à la fin, relire sur le boîtier `USER LIST` et `USER GROUP LIST`.
*Attendu* : le journal affiche « Groupes à créer : compta-recette (n membres),
lecture-recette (n membres) », puis une ligne « <identifiant> : à créer, rattaché à … » par
compte. **Le boîtier est inchangé** : aucun des 3 comptes, aucun des 2 groupes n'y est
apparu.
*Verdict* : OK / KO —

**20 — Ordre et contenu du journal de simulation** · boîtier : oui
*Objectif* : la trace est lisible et complète, dans cet ordre.
*Départ* : CSV = `lot-rejets.csv` complété de 2 lignes valides.
*Actions* : lancer en simulation, lire le journal du haut vers le bas.
*Attendu* : dans l'ordre — (1) la ligne de séparation `───────── nouveau lancement
(simulation) ─────────`, (2) « 2 lignes lues, 4 rejets », (3) **une ligne par rejet** de la
forme « ligne N : <identifiant> — <motif> », (4) le plan.
*Verdict* : OK / KO —

**21 — Motifs de rejet** · boîtier : oui
*Objectif* : chaque rejet dit pourquoi, sans jargon.
*Départ* : cas 20 joué.
*Actions* : lire les quatre lignes de rejet.
*Attendu* : « identifiant vide », « nom vide », « identifiant : caractère interdit
(autorisés : a-z 0-9 . _ - ) » pour `jean dupont` **et** pour `rené`. Les numéros de ligne
correspondent au rang dans le fichier, l'en-tête comptant pour la ligne 1.
*Verdict* : OK / KO —

**22 — La politique s'active et se pré-remplit** · boîtier : oui
*Objectif* : le plancher du boîtier atteint l'interface.
*Départ* : outil fraîchement ouvert (champs de politique grisés), valeurs de
`CONFIG PASSWDPOLICY SHOW` relevées sur le boîtier.
*Actions* : lancer une simulation ; à la fin, lire l'étiquette et les champs de politique.
*Attendu* : le champ de longueur et les quatre cases sont **actifs**. L'étiquette lit
« politique du boîtier : MinLength=… , MinSet=… , MinEntropy=… » avec les valeurs relevées
sur le boîtier (voir cas 31 pour `MinSet`). Les quatre cases sont cochées et la longueur vaut
16, ou le `MinLength` du boîtier s'il dépasse 16.
*Verdict* : OK / KO —

**23 — La barre de simulation atteint son total** · boîtier : oui
*Objectif* : une simulation ne compte que ses quatre lectures.
*Départ* : CSV = `lot-nominal.csv`, Simulation cochée.
*Actions* : lancer, lire l'étiquette à droite de la barre à la fin.
*Attendu* : « **4 / 4** » et une barre pleine. Le nombre d'opérations à écrire n'entre pas
dans le total en simulation.
*Verdict* : OK / KO —

**24 — La fenêtre reste réactive pendant la lecture** · boîtier : oui
*Objectif* : le fil d'exécution ne bloque pas l'interface.
*Départ* : CSV = `lot-200.csv`, Simulation cochée.
*Actions* : pendant la lecture, déplacer la fenêtre, la redimensionner, faire défiler le
journal.
*Attendu* : la fenêtre suit la souris sans blanchir ni afficher « Ne répond pas ».
*Verdict* : OK / KO —

**25 — Groupe neuf à un seul membre : l'accord est au singulier** · boîtier : oui
*Objectif* : le décompte des membres est juste et lisible.
*Départ* : CSV = `lot-groupe-un-membre.csv`, groupe `solo-recette` absent du boîtier.
*Actions* : lancer en simulation.
*Attendu* : la ligne « Groupes à créer : solo-recette (**1 membre**) » — au singulier — et
elle apparaît **avant** toute ligne de création.
*Verdict* : OK / KO —

**26 — Un groupe réclamé par un compte déjà présent n'est pas créé** · boîtier : oui
*Objectif* : l'outil ne touche pas à ce qui existe, appartenances comprises.
*Départ* : le compte du CSV `lot-groupe-sur-compte-present.csv` **existe** sur le boîtier ;
le groupe `fantome-recette` n'existe pas.
*Actions* : lancer en simulation, puis décocher Simulation et relancer.
*Attendu* : aucune ligne « Groupes à créer » ne mentionne `fantome-recette` ; le compte est
listé « déjà présent, ignoré ». Après le lot réel, `fantome-recette` **n'existe toujours
pas** sur le boîtier et l'appartenance du compte existant est inchangée.
*Verdict* : OK / KO —

**27 — Les orphelins sont signalés, jamais touchés** · boîtier : oui
*Objectif* : l'outil ajoute et rien d'autre.
*Départ* : un compte `temoin.recette` existe sur le boîtier et **n'est dans aucun CSV**.
*Actions* : lancer un lot réel avec `lot-nominal.csv`, puis relire le boîtier.
*Attendu* : le journal porte « Orphelins sur le boîtier : … , temoin.recette, … ». Après le
lot, `temoin.recette` existe toujours, avec les mêmes attributs et les mêmes appartenances.
*Verdict* : OK / KO —

**28 — La bascule en minuscules est signalée** · boîtier : oui
*Objectif* : l'opérateur sait que l'identifiant créé diffère de celui qu'il a écrit.
*Départ* : CSV = `lot-casse.csv` (`Jean.Dupont`), compte absent du boîtier.
*Actions* : lancer en simulation, lire le journal ; puis lancer en réel et relire le boîtier.
*Attendu* : le journal porte « ligne 2 : identifiant **Jean.Dupont** basculé en minuscules ->
**jean.dupont** ». Le plan et le compte réellement créé portent `jean.dupont`.
*Verdict* : OK / KO —

**29 — Doublon : les deux lignes sont rejetées** · boîtier : oui
*Objectif* : l'outil ne choisit pas laquelle des deux lignes est la bonne.
*Départ* : CSV = `lot-doublon.csv`, `jean.dupont` absent du boîtier.
*Actions* : lancer en réel, puis relire le boîtier.
*Attendu* : le journal porte **deux** lignes de rejet portant « identifiant en doublon dans
le fichier », une par ligne du fichier. **Aucun** compte `jean.dupont` n'est créé.
*Verdict* : OK / KO —

**30 — Segments de groupes vides et doublons internes** · boîtier : oui
*Objectif* : un export métier bavard ne crée pas de groupe fantôme.
*Départ* : CSV = `lot-groupes-sales.csv` (`compta-recette||compta-recette| |lecture-recette`).
*Actions* : lancer en simulation.
*Attendu* : le compte est annoncé « rattaché à compta-recette, lecture-recette » —
exactement deux groupes, dans cet ordre. Aucun groupe au nom vide ni au nom composé d'une
espace n'apparaît.
*Verdict* : OK / KO —

---

# F. Hypothèses de l'adaptateur SDK à confirmer

**C'est la section la plus importante de ce cahier.** Chacun de ces points est une
supposition écrite contre la documentation, que rien n'a jamais confirmée. Un KO ici n'est
pas un détail : il invalide le plancher de politique affiché, ou fait voir le boîtier comme
vierge.

**31 — Traduction de `MinSetOfChars`** · boîtier : oui
*Objectif* : confirmer la table `None`→1, `AlphaNum`→2, `AlphaSpecial`→3, dont dépend tout le
plancher de politique affiché **et** le refus de politique.
*Départ* : accès à la configuration de politique de mot de passe du boîtier.
*Actions* : régler le boîtier successivement sur les trois valeurs (`None`, `AlphaNum`,
`AlphaSpecial`) ; après chaque réglage, relancer une simulation depuis l'outil et lire
l'étiquette de plancher.
*Attendu* : l'étiquette affiche respectivement `MinSet=1`, `MinSet=2`, `MinSet=3`. **Tout
autre résultat est un KO** : la table `CLASSES_PAR_JEU_DE_CARACTERES` de `boitier_sdk.py` est
fausse et doit être corrigée avant toute mise en service.
*Verdict* : OK / KO —

**32 — `MinLength` et `MinEntropy` sont lus fidèlement** · boîtier : oui
*Objectif* : le plancher affiché est celui du boîtier, pas un zéro de repli.
*Départ* : valeurs relevées sur le boîtier (section A).
*Actions* : lancer une simulation, comparer l'étiquette aux valeurs relevées.
*Attendu* : `MinLength=` et `MinEntropy=` portent **exactement** les valeurs du boîtier. Un
`0` affiché alors que le boîtier déclare autre chose est un KO.
*Verdict* : OK / KO —

**33 — Une valeur de politique illisible arrête l'outil** · boîtier : oui
*Objectif* : un plancher incompris ne doit pas être ramené à zéro en silence.
*Départ* : si le boîtier permet de laisser `MinLength` vide ou de lui donner une valeur non
numérique, l'y mettre. **Noter NJ s'il refuse.**
*Actions* : lancer une simulation.
*Attendu* : le lot s'arrête. Le journal porte « arrêt définitif : MinLength vaut « … », que
l'outil ne sait pas lire comme un entier : il s'arrête plutôt que d'abaisser le plancher de
politique à zéro. » Le rapport final commence par « **Lot interrompu** » et dit de corriger
avant de relancer. Les champs de politique restent **grisés** (le plancher n'a jamais été
émis). Aucune écriture.
*Verdict* : OK / KO / NJ —

**34 — Valeur inconnue de `MinSetOfChars`** · boîtier : oui
*Objectif* : même garde-fou, du côté des classes de caractères.
*Départ* : si le boîtier accepte une valeur hors `None|AlphaNum|AlphaSpecial`, l'y mettre.
**Noter NJ sinon.**
*Actions* : lancer une simulation.
*Attendu* : arrêt définitif, message nommant les valeurs attendues (« attendu : alphanum,
alphaspecial, none, ou un entier »), aucune écriture.
*Verdict* : OK / KO / NJ —

**35 — Clé `name` de `USER LIST`** · boîtier : oui
*Objectif* : confirmer que l'outil voit réellement les comptes existants. Si la clé est
fausse, `lister_utilisateurs()` rend une liste vide et **le boîtier passe pour vierge**.
*Départ* : le boîtier porte au moins 3 comptes connus, dont 2 sont dans `lot-nominal.csv`.
*Actions* : lancer une simulation avec `lot-nominal.csv`.
*Attendu* : les 2 comptes déjà présents sont annoncés « déjà présent, ignoré », **et** la
ligne « Orphelins sur le boîtier : … » liste les comptes du boîtier absents du CSV. Le KO
caractéristique : tous les comptes sont annoncés « à créer » et **aucun orphelin** n'est
listé — signe que la liste lue est vide.
*Verdict* : OK / KO —

**36 — Clé `name` de `USER GROUP LIST`** · boîtier : oui
*Objectif* : même vérification pour les groupes. Une clé fausse ferait recréer à chaque
passage des groupes qui existent.
*Départ* : `compta-recette` **existe** sur le boîtier ; `lecture-recette` n'existe pas.
*Actions* : lancer une simulation avec `lot-nominal.csv`.
*Attendu* : « Groupes à créer » mentionne **`lecture-recette` seulement**. Le KO
caractéristique : les deux groupes sont annoncés à créer.
*Verdict* : OK / KO —

**37 — Clé `domain` de `CONFIG LDAP LIST`** · boîtier : oui
*Objectif* : confirmer que l'outil voit l'annuaire. Une clé fausse rend une liste vide, donc
un boîtier vu comme « sans annuaire ».
*Départ* : boîtier portant **un** annuaire LDAP interne, dont on note le nom de domaine.
*Actions* : lancer une simulation.
*Attendu* : la simulation se déroule normalement. **La fenêtre de création d'annuaire ne
s'ouvre pas.** Si elle s'ouvre sur un boîtier qui porte bel et bien un annuaire, c'est un KO
grave : la clé `domain` est fausse, et accepter la création écraserait la base existante —
**fermer la fenêtre sans rien valider**.
*Verdict* : OK / KO —

**38 — Le domaine lu est bien celui passé à `USER CREATE`** · boîtier : oui
*Objectif* : les comptes atterrissent dans le bon annuaire.
*Départ* : nom de domaine de l'annuaire relevé au cas 37.
*Actions* : lancer un lot réel avec `lot-nominal.csv`, puis relire les comptes sur le
boîtier.
*Attendu* : les 3 comptes créés appartiennent à **cet** annuaire, et non à un autre ni à
aucun.
*Verdict* : OK / KO —

**39 — `CONFIG LDAP LIST` liste aussi les annuaires externes** · boîtier : oui
*Objectif* : mesurer une limite connue — l'outil ne distingue pas interne et externe.
*Départ* : déclarer sur la maquette un annuaire LDAP **externe**, en plus de l'annuaire
interne.
*Actions* : lancer une simulation.
*Attendu* : **le comportement observé est à consigner, quel qu'il soit.** Deux issues
possibles, toutes deux acceptables comme résultat de recette, mais qui appellent des suites
différentes :
(a) l'outil s'arrête sur « le boîtier déclare plusieurs annuaires LDAP internes : … » —
l'hypothèse est confirmée, la limite est réelle et doit être documentée pour l'exploitant ;
(b) l'outil ne voit que l'annuaire interne et poursuit — `CONFIG LDAP LIST` filtre de
lui-même, la limite n'existe pas et la mention peut être retirée du code.
Le KO est une troisième issue : l'outil poursuit **en visant le domaine externe**.
*Verdict* : (a) / (b) / KO —

**40 — Aucun mot de passe ne fuit dans un message d'erreur** · boîtier : oui
*Objectif* : le masquage `password=***` tient sur un vrai échec, URL encodée comprise.
*Départ* : lot réel en cours de création de comptes.
*Actions* : provoquer une coupure de liaison **pendant** la phase d'écriture (cas 80), puis
relire l'intégralité du journal, y compris les lignes de trace.
*Attendu* : le journal ne contient **aucun** mot de passe en clair. Toute occurrence de
`password` y apparaît sous la forme `password=***` ou `password%3D***`. Vérifier également
que le CSV des mots de passe est le **seul** endroit où un secret apparaît.
*Verdict* : OK / KO —

**41 — Une seule session à la fois** · boîtier : oui
*Objectif* : les reconnexions ne saturent pas la limite d'authentification du boîtier.
*Départ* : boîtier dont on sait consulter les sessions actives de l'API.
*Actions* : jouer le cas 80 (coupure et reconnexion) deux fois de suite, puis consulter les
sessions actives du boîtier.
*Attendu* : à la fin du lot, **aucune** session de l'outil ne reste ouverte. Pendant le lot,
jamais plus d'une. Aucun message de limite d'authentification atteinte.
*Verdict* : OK / KO —

---

# G. Politique de mot de passe

**42 — Un durcissement survit à une relecture du boîtier** · boîtier : oui
*Objectif* : ce que l'opérateur a durci ne doit jamais être effacé en silence.
*Départ* : une première simulation a eu lieu, champs de politique actifs et pré-remplis.
*Actions* : porter la longueur de 16 à 24, décocher « spéciaux » ; relancer une simulation ;
relire les champs.
*Attendu* : après la relecture du boîtier, la longueur affiche toujours **24** et
« spéciaux » est toujours **décoché**. L'étiquette de plancher, elle, est bien rafraîchie.
*Verdict* : OK / KO —

**43 — Politique sous le plancher : refus avant connexion** · boîtier : oui
*Objectif* : un lot qui ne peut pas aboutir ne part pas.
*Départ* : plancher du boîtier connu (`MinLength` relevé), champs actifs.
*Actions* : régler la longueur **en dessous** du `MinLength` du boîtier, cliquer *Lancer*.
*Attendu* : boîte « Lancement refusé » portant le texte « longueur N inférieure au minimum du
boîtier (M) », avec les deux vraies valeurs. **Aucune connexion n'est tentée** : rien n'est
écrit au journal, pas même la ligne de séparation.
*Verdict* : OK / KO —

**44 — Trop peu de classes de caractères** · boîtier : oui
*Objectif* : le second motif de refus est rendu lui aussi.
*Départ* : boîtier réglé sur `MinSetOfChars=AlphaSpecial` (soit 3 classes attendues).
*Actions* : ne laisser cochées que « minuscules » et « chiffres », cliquer *Lancer*.
*Attendu* : refus portant « 2 classes de caractères, le boîtier en exige 3 ».
*Verdict* : OK / KO —

**45 — Longueur invalide** · boîtier : oui
*Objectif* : une saisie non numérique ne fait pas partir de lot.
*Départ* : champs de politique **actifs** (donc après une première lecture — avant, ils sont
grisés et cette saisie est impossible).
*Actions* : effacer la longueur et taper `douze`, cliquer *Lancer*.
*Attendu* : boîte « Longueur invalide » disant que la longueur doit être un nombre entier.
Rien ne part, rien n'est écrit au journal.
*Verdict* : OK / KO —

**46 — Politique refusée par le boîtier, en cours de lot** · boîtier : oui
*Objectif* : le verdict qui fait foi est celui du boîtier réellement visé, et il tombe avant
la moindre écriture.
*Départ* : une première simulation a eu lieu, politique réglée juste au plancher. **Durcir
ensuite le `MinLength` du firewall** au-dessus de la valeur réglée dans l'outil.
*Actions* : décocher Simulation, cliquer *Lancer*.
*Attendu* : boîte « **Politique refusée** » ; les mêmes lignes au journal, dont « politique
refusée avant tout envoi : aucun compte n'a été touché. », le texte de la violation, le
libellé du plancher et « Durcissez la politique, puis relancez le lot. ». **Aucun compte,
aucun groupe n'a été créé** sur le boîtier. Le rapport final commence par « Lot interrompu »
et dit de **corriger avant de relancer**. Le bouton *Lancer* est réactivé.
*Verdict* : OK / KO —

**47 — Les mots de passe générés sont acceptés par le boîtier** · boîtier : oui
*Objectif* : la politique de l'outil et celle du boîtier s'accordent en pratique, pas
seulement sur le papier.
*Départ* : politique réglée au plancher du boîtier, `lot-nominal.csv`.
*Actions* : lancer un lot réel ; lire le rapport final ; se connecter au boîtier avec l'un
des comptes créés et le mot de passe restitué.
*Attendu* : le rapport annonce « 3 comptes créés, 2 groupes créés, **0 échec** » et
**aucune** section « Comptes créés sans mot de passe ». La connexion avec le mot de passe
restitué aboutit.
*Verdict* : OK / KO —

**48 — La politique réglée est celle réellement appliquée** · boîtier : oui
*Objectif* : le réglage de la fenêtre atteint bien le générateur.
*Départ* : politique portée à une longueur de 24, les quatre classes cochées.
*Actions* : lancer un lot réel, enregistrer les mots de passe, ouvrir le CSV.
*Attendu* : chaque mot de passe fait **exactement 24 caractères** et comporte au moins une
minuscule, une majuscule, un chiffre et un caractère parmi `!#$%*+-=?@_`. Aucun ne contient
d'espace ni de guillemet.
*Verdict* : OK / KO —

---

# H. Exécution réelle et idempotence

**49 — Lot réel nominal** · boîtier : oui
*Objectif* : le cœur du produit.
*Départ* : boîtier ne portant ni les 3 comptes ni les 2 groupes ; simulation du cas 19 déjà
jouée et relue.
*Actions* : décocher **Simulation**, cliquer *Lancer* ; à la fin, relire `USER LIST` et
`USER GROUP LIST` sur le boîtier.
*Attendu* : les **3 comptes** et les **2 groupes** existent sur le boîtier. La barre est
pleine et l'étiquette affiche un couple `N / N` identique. Le rapport final lit « Terminé :
3 comptes créés, 2 groupes créés, 0 échec. ».
*Verdict* : OK / KO —

**50 — Les rattachements aux groupes sont effectifs** · boîtier : oui
*Objectif* : `USER GROUP ADDUSER` n'est pas seulement compté, il agit.
*Départ* : cas 49 joué.
*Actions* : relire les membres de `compta-recette` et `lecture-recette` sur le boîtier.
*Attendu* : chaque compte figure dans **exactement** les groupes que le CSV lui donnait, et
dans aucun autre. Le compte sans groupe n'appartient à aucun des deux.
*Verdict* : OK / KO —

**51 — Idempotence : relancer ne réécrit rien** · boîtier : oui
*Objectif* : l'invariant du projet — l'état se lit sur le boîtier, jamais dans un fichier.
*Départ* : cas 49 joué, boîtier à jour, **aucun** fichier d'état sur le poste.
*Actions* : relancer le **même** CSV en lot réel ; relever l'heure de dernière modification
des comptes sur le boîtier avant et après.
*Attendu* : les 3 comptes tombent en « **déjà présent, ignoré** », aucune ligne « Groupes à
créer », le rapport lit « Terminé : 0 compte créé, 0 groupe créé, 0 échec. » et la barre
affiche « **4 / 4** ». Les comptes du boîtier sont **inchangés**, date de modification
comprise.
*Verdict* : OK / KO —

**52 — Idempotence après déplacement du poste** · boîtier : oui
*Objectif* : aucun état caché ne voyage avec l'exécutable.
*Départ* : cas 51 joué.
*Actions* : copier le `.exe` sur un **autre** poste, y rejouer le même CSV en lot réel.
*Attendu* : même résultat qu'au cas 51 — tout est « déjà présent, ignoré ». Le premier
lancement sur ce poste n'est pas traité comme un lot neuf.
*Verdict* : OK / KO —

**53 — Accents d'un CSV Excel français** · boîtier : oui
*Objectif* : l'encodage cp1252 est bien reconnu, jusque sur le boîtier.
*Départ* : `lot-accents.csv`, réellement enregistré par Excel en français ; comptes absents
du boîtier.
*Actions* : lancer un lot réel, puis relire les fiches des comptes créés sur le boîtier.
*Attendu* : les noms portent leurs accents **exacts** — `Désiré`, `Noël`, `Élodie` — sans
caractère de remplacement ni `Ã©`. Le journal les affiche également correctement.
*Verdict* : OK / KO —

**54 — Patronyme composé** · boîtier : oui
*Objectif* : un nom contenant une espace ne se fait pas découper en silence par le boîtier.
*Départ* : `lot-nom-compose.csv` (`De La Tour`).
*Actions* : lancer un lot réel, relire la fiche du compte `p.delatour`.
*Attendu* : le nom vaut exactement « **De La Tour** », en un seul champ. Ni « De » seul, ni
échec de commande.
*Verdict* : OK / KO —

**55 — Premier lot en réel, sans simulation préalable** · boîtier : oui
*Objectif* : l'outil n'impose pas de simulation préalable ; c'est le boîtier qui arbitre.
*Départ* : outil **fraîchement ouvert** (aucune lecture, champs de politique grisés) ;
`lot-nominal.csv` ; boîtier dont le `MinLength` est inférieur ou égal à 16.
*Actions* : décocher Simulation dès l'ouverture, cliquer *Lancer*.
*Attendu* : le lot **part** et aboutit. Aucune boîte ne réclame de simuler d'abord. La
politique de repli (longueur 16, quatre classes) a été confrontée au plancher réel et l'a
tenu. (Si le boîtier exige plus, voir le cas 46 : le refus est légitime.)
*Verdict* : OK / KO —

**56 — Progression d'un lot réel** · boîtier : oui
*Objectif* : la barre et l'étiquette disent la vérité.
*Départ* : `lot-nominal.csv`, 3 comptes dont 2 avec un groupe chacun, 2 groupes à créer.
*Actions* : lancer en réel, noter le premier et le dernier couple affichés.
*Attendu* : le total vaut **4 lectures + 2 créations de groupe + (2 + nombre de groupes) par
compte**. L'étiquette part de `0 / total` et finit sur `total / total`, la barre pleine ; les
valeurs intermédiaires ne reculent jamais.
*Verdict* : OK / KO —

**57 — Accords du rapport final** · boîtier : oui
*Objectif* : le bilan se lit sans buter sur un pluriel faux.
*Départ* : un lot créant exactement **1** compte et **1** groupe, sans échec.
*Actions* : lancer, lire le rapport.
*Attendu* : « Terminé : **1 compte créé, 1 groupe créé, 0 échec.** » — tout au singulier.
*Verdict* : OK / KO —

---

# I. Échecs isolés et noms hostiles

**58 — `uid` interdit : l'échec est isolé, le lot continue** · boîtier : oui
*Objectif* : un compte refusé n'arrête pas le lot.
*Départ* : `lot-uid-interdit.csv` (une ligne `admin` entre deux lignes valides).
*Actions* : lancer un lot réel.
*Attendu* : le journal porte « admin : échec de création (…) » puis les créations des deux
autres comptes. Le rapport final lit « 2 comptes créés, … , **1 échec** » et détaille
« admin — USER CREATE : … ». Les **deux** comptes valides existent sur le boîtier. La barre
atteint bien son total malgré le compte abandonné.
*Verdict* : OK / KO —

**59 — Nom de groupe contenant un guillemet double** · boîtier : oui
*Objectif* : mesurer le comportement assumé — le guillemet n'est pas échappé, la commande est
refusée, l'échec est signalé.
*Départ* : `lot-groupe-guillemet.csv` (groupe `compta"bis`), comptes absents du boîtier.
*Actions* : lancer un lot réel, relire le boîtier.
*Attendu* : le journal porte « compta"bis : échec de création (…) ». Les **deux comptes sont
créés** malgré cet échec. Le rattachement à ce groupe échoue également et figure au rapport
sous `USER GROUP ADDUSER`. Aucun groupe au nom tronqué n'apparaît sur le boîtier.
*Verdict* : OK / KO —

**60 — Nom de groupe contenant une espace** · boîtier : oui
*Objectif* : un nom composé doit passer entier, ce que l'ajout des guillemets garantit.
*Départ* : `lot-groupe-espace.csv` (groupe `compta bis recette`), groupe absent du boîtier.
*Actions* : lancer un lot réel, relire les groupes du boîtier.
*Attendu* : un groupe nommé exactement « **compta bis recette** » existe, et les comptes y
sont rattachés. Le KO caractéristique : trois groupes `compta`, `bis`, `recette`, ou un
groupe `compta` seul.
*Verdict* : OK / KO —

**61 — Nom de groupe contenant un saut de ligne** · boîtier : oui
*Objectif* : cas non couvert par le code ; **le comportement observé est à consigner**.
*Départ* : `lot-groupe-retour-ligne.csv`, champ groupes entre guillemets CSV contenant un
saut de ligne.
*Actions* : lancer d'abord en **simulation**, lire comment le groupe s'affiche dans le plan ;
puis en réel, relire le boîtier.
*Attendu* : la seule issue inacceptable est une écriture **silencieuse et fausse** — un
groupe créé sous un nom tronqué, ou plusieurs groupes créés là où le CSV en nommait un.
Toute issue visible est acceptable et se consigne : échec de commande signalé au rapport,
groupe créé avec son nom entier, ou rejet de la ligne. Noter précisément ce qui s'est passé.
*Verdict* : consigner —

**62 — Compte créé sans mot de passe utilisable** · boîtier : oui
*Objectif* : un `USER PASSWORD` durablement refusé donne un compte à reprendre à la main,
jamais un compte silencieusement incomplet.
*Départ* : provoquer le refus de `USER PASSWORD` — par exemple en durcissant la politique du
boîtier **pendant** le lot, entre le `USER CREATE` et le `USER PASSWORD`. **Noter NJ si le
refus ne peut pas être provoqué.**
*Actions* : lancer un lot réel, observer le journal, puis enregistrer les mots de passe.
*Attendu* : l'outil réessaie (un appel puis jusqu'à trois réessais, espacés de deux
secondes) avant d'abandonner. Le journal porte « <identifiant> : créé sans mot de passe — à
reprendre à la main (…) ». Le rapport final porte une section « **Comptes créés sans mot de
passe — à reprendre** » nommant ce compte. Le CSV exporté contient ce compte avec un **champ
mot de passe vide**.
*Verdict* : OK / KO / NJ —

---

# J. Mots de passe : enregistrement et perte

**63 — Le bouton s'active dès le premier compte créé** · boîtier : oui
*Objectif* : sur un lot de 200 comptes, l'export ne doit pas attendre la fin.
*Départ* : `lot-200.csv`, bouton *Enregistrer* grisé.
*Actions* : lancer un lot réel ; surveiller le bouton dès les premières lignes « … : créé ».
*Attendu* : le bouton devient **actif dès la première ligne « créé »**, sans attendre le
rapport final.
*Verdict* : OK / KO —

**64 — Le bouton redevient inactif au démarrage d'un lot** · boîtier : oui
*Objectif* : un export ne doit jamais mélanger deux lots.
*Départ* : un lot réel a créé des comptes, ils ont été enregistrés (cas 66).
*Actions* : relancer un lot ; observer le bouton juste après le démarrage.
*Attendu* : le bouton est **grisé** dès le démarrage et le reste jusqu'à la première création
du nouveau lot.
*Verdict* : OK / KO —

**65 — Annuler le sélecteur n'écrit rien** · boîtier : oui
*Objectif* : un clic malheureux ne produit pas de fichier.
*Départ* : un lot réel vient de créer des comptes, bouton actif.
*Actions* : cliquer *Enregistrer les mots de passe…*, **annuler** le sélecteur.
*Attendu* : aucun fichier n'est créé, aucune ligne de bilan au journal, le bouton reste actif
et les mots de passe restent en mémoire.
*Verdict* : OK / KO —

**66 — Le CSV restitué, et son ouverture dans Excel** · boîtier : oui
*Objectif* : la liste de reprise de l'opérateur est complète et exploitable sans manipulation.
*Départ* : un lot réel ayant créé au moins 3 comptes, dont si possible un sans mot de passe
(cas 62).
*Actions* : cliquer *Enregistrer les mots de passe…*, choisir un emplacement, valider ;
ouvrir le fichier par **double-clic** dans Excel en français.
*Attendu* : le fichier s'ouvre en **deux colonnes séparées**, `identifiant` et
`mot_de_passe`, sans passer par l'assistant d'importation. Il contient **exactement** les
comptes créés par ce lot — y compris ceux dont le mot de passe est vide — et aucun autre.
*Verdict* : OK / KO —

**67 — Aucun CSV n'apparaît tout seul** · boîtier : oui
*Objectif* : les secrets ne s'écrivent qu'où l'opérateur l'a dit.
*Départ* : contenu relevé du dossier du `.exe` et du dossier du CSV d'entrée.
*Actions* : jouer un lot réel complet **sans** cliquer *Enregistrer*, puis recomparer les
deux dossiers.
*Attendu* : **aucun** fichier CSV n'est apparu, ni à côté de l'exécutable, ni à côté du
fichier d'entrée, ni ailleurs.
*Verdict* : OK / KO —

**68 — Écriture impossible** · boîtier : oui
*Objectif* : un échec d'écriture est visible et ne fait pas croire les secrets sauvés.
*Départ* : un lot réel a créé des comptes ; disposer d'un chemin non inscriptible (dossier
protégé, ou clé USB en lecture seule).
*Actions* : cliquer *Enregistrer*, choisir ce chemin, valider ; puis relancer un lot.
*Attendu* : boîte « **Écriture impossible** » portant le message du système. Le bouton
*Enregistrer* **reste utilisable**. Au lancement suivant, l'avertissement de perte de secrets
**revient** : rien n'a été sauvé.
*Verdict* : OK / KO —

**69 — Bilan d'enregistrement : deux nombres** · boîtier : oui
*Objectif* : « N mots de passe enregistrés » ne doit pas faire croire à N secrets
récupérables.
*Départ* : un lot ayant créé 4 comptes dont 1 sans mot de passe.
*Actions* : enregistrer, lire la ligne de bilan au journal.
*Attendu* : « **4 comptes écrits dans <chemin>, 3 mots de passe enregistrés, 1 compte sans
mot de passe** ». Les trois nombres sont justes et les accords corrects.
*Verdict* : OK / KO —

**70 — Relancer sans avoir enregistré : l'avertissement** · boîtier : oui
*Objectif* : le scénario le plus coûteux du produit — des secrets détruits en silence.
*Départ* : un lot réel a créé 3 comptes avec mot de passe ; **ne pas** cliquer *Enregistrer*.
*Actions* : cliquer *Lancer*.
*Attendu* : une boîte d'avertissement annonce « **3 mots de passe n'ont pas été
enregistrés** dans un fichier », dit que les comptes resteront créés et seront classés « déjà
présent, ignoré », et demande « Lancer quand même ? ». **Le bouton présélectionné est
« Non »** : appuyer sur Entrée doit annuler, pas lancer.
*Verdict* : OK / KO —

**71 — Répondre Non** · boîtier : oui
*Objectif* : le refus préserve réellement les secrets.
*Départ* : cas 70 en cours, boîte ouverte.
*Actions* : répondre **Non** ; puis cliquer *Enregistrer les mots de passe…*.
*Attendu* : **rien ne part** — aucune ligne de séparation, aucune connexion. Le bouton
*Enregistrer* est toujours actif et le CSV écrit porte bien les 3 mots de passe du lot
précédent.
*Verdict* : OK / KO —

**72 — Répondre Oui** · boîtier : oui
*Objectif* : le consentement explicite fait ce qu'il annonce.
*Départ* : cas 70 rejoué, boîte ouverte.
*Actions* : répondre **Oui** ; laisser le lot aller à son terme ; enregistrer.
*Attendu* : le lot part, le bouton *Enregistrer* est **grisé** au démarrage, et le CSV
finalement écrit ne contient que les comptes du **nouveau** lot — aucun du précédent.
*Verdict* : OK / KO —

**73 — Enregistrer d'abord : aucun avertissement** · boîtier : oui
*Objectif* : l'avertissement ne harcèle pas l'opérateur diligent.
*Départ* : un lot réel a créé des comptes **et** ils ont été enregistrés avec succès.
*Actions* : cliquer *Lancer*.
*Attendu* : **aucune boîte** d'avertissement ; le lot démarre directement.
*Verdict* : OK / KO —

**74 — Enregistrer en cours de lot, puis relancer : le recompte est total** · boîtier : oui
*Objectif* : le bilan d'un lot remet à zéro ce qui est réputé déjà enregistré ; l'avertissement
qui suit recompte tout, par choix délibéré et conservateur.
*Départ* : `lot-200.csv`, lot réel en cours.
*Actions* : vers le milieu du lot, cliquer *Enregistrer* et écrire le fichier ; laisser le
lot aller à son terme ; cliquer *Lancer*.
*Attendu* : l'avertissement revient, et le nombre qu'il annonce compte **tous** les comptes à
mot de passe du rapport final — y compris ceux déjà écrits pendant le lot, et pas seulement
ceux créés après l'enregistrement. Comportement voulu : avertir deux fois coûte un clic, ne
pas avertir coûte des mots de passe qu'aucun relancement ne recrée.
*Verdict* : OK / KO —

**75 — Enregistrer pendant que le sélecteur reste ouvert : les comptes créés entre-temps ne sont pas soldés** · boîtier : oui
*Objectif* : le sélecteur de fichiers fait tourner la boucle d'événements de Tk ; ce qui est
créé pendant qu'il est ouvert ne doit jamais être compté comme enregistré.
*Départ* : `lot-200.csv`, lot réel en cours, au moins deux comptes déjà créés.
*Actions* : cliquer *Enregistrer les mots de passe…* ; **laisser le sélecteur ouvert** le
temps qu'au moins un compte de plus soit créé (l'observer apparaître au journal, derrière la
boîte) ; valider le sélecteur sur un chemin d'écriture ; laisser le lot aller à son terme ;
cliquer *Lancer*.
*Attendu* : le CSV écrit ne porte que les comptes créés **avant** l'ouverture du sélecteur.
Une fois le lot terminé, cliquer *Lancer* fait réapparaître l'avertissement de perte, et le
nombre qu'il annonce **inclut** les comptes créés pendant que le sélecteur était ouvert : ils
n'ont jamais été soldés.
*Verdict* : OK / KO —

**76 — Aucun secret à perdre : aucun avertissement** · boîtier : oui
*Objectif* : l'avertissement ne se déclenche pas sur des comptes déjà à reprendre à la main.
*Départ* : un lot dont **tous** les comptes ont été créés sans mot de passe (cas 62 forcé sur
tout le lot). **Noter NJ si impossible à provoquer.**
*Actions* : sans enregistrer, cliquer *Lancer*.
*Attendu* : **aucune boîte** d'avertissement : il n'y a aucun secret à perdre.
*Verdict* : OK / KO / NJ —

---

# K. Fermeture de la fenêtre

**77 — Fermer en plein lot** · boîtier : oui
*Objectif* : le fil est un démon ; le fermer peut laisser un compte créé sans mot de passe.
*Départ* : `lot-200.csv`, lot réel en cours.
*Actions* : cliquer la croix de la fenêtre ; répondre **Non** ; recliquer la croix ; répondre
**Oui**.
*Attendu* : une boîte avertit qu'un lot est en cours et que fermer couperait le travail « y
compris entre la création d'un compte et la pose de son mot de passe ». **Non** annule la
fermeture et le lot poursuit visiblement (la barre continue d'avancer). **Oui** ferme
l'outil.
*Verdict* : OK / KO —

**78 — Fermer avec des secrets non enregistrés** · boîtier : oui
*Objectif* : la fermeture est la seconde porte par laquelle les secrets disparaissent.
*Départ* : lot **terminé** ayant créé 3 comptes, non enregistrés.
*Actions* : cliquer la croix.
*Attendu* : une boîte annonce « 3 mots de passe n'ont pas été enregistrés … et disparaîtront
avec la fenêtre », précise que les comptes resteront créés, et propose « Fermer quand
même ? » avec **Non** par défaut.
*Verdict* : OK / KO —

**79 — Fermer quand il n'y a rien à perdre** · boîtier : non
*Objectif* : l'outil ne pose pas de question inutile.
*Départ* : outil ouvert, aucun lot lancé (ou lot terminé et secrets enregistrés).
*Actions* : cliquer la croix.
*Attendu* : **aucune question** ; la fenêtre se ferme immédiatement.
*Verdict* : OK / KO —

---

# L. Coupures, arrêts et reprise

**80 — Coupure brève : reconnexion et replanification** · boîtier : oui
*Objectif* : une liaison qui retombe ne fait ni perdre le lot, ni rejouer une écriture.
*Départ* : `lot-200.csv`, lot réel en cours de création de comptes.
*Actions* : débrancher le câble réseau du poste (ou couper le Wi-Fi) pendant 5 secondes, puis
rebrancher ; observer le journal et la barre.
*Attendu* : dans l'ordre — « liaison perdue, tentative de reconnexion », éventuellement
« reconnexion n/3 échouée », puis « **reconnecté à la tentative n** », puis **un nouveau plan
réaffiché en entier** à la suite du précédent. Le **total de la barre diminue** (les comptes
déjà créés en sortent) et la barre suit cette baisse sans anomalie visuelle ni recul de la
valeur affichée. Le lot reprend et va à son terme.
*Verdict* : OK / KO —

**81 — Aucun doublon après reconnexion** · boîtier : oui
*Objectif* : la commande interrompue n'est jamais rejouée ; l'outil relit et replanifie.
*Départ* : cas 80 joué.
*Actions* : relire `USER LIST` et `USER GROUP LIST` sur le boîtier, ainsi que le rapport
final.
*Attendu* : chaque compte et chaque groupe existe **une seule fois**. Aucun échec du type
« existe déjà » n'apparaît au rapport. Le nombre de comptes créés annoncé correspond au
nombre réellement apparu sur le boîtier.
*Verdict* : OK / KO —

**82 — Coupure prolongée : trois tentatives puis arrêt** · boîtier : oui
*Objectif* : l'outil ne tourne pas indéfiniment sur une liaison morte.
*Départ* : `lot-200.csv`, lot réel en cours.
*Actions* : débrancher le réseau et **ne pas** rebrancher ; observer le journal.
*Attendu* : trois lignes « reconnexion **1/3** », « **2/3** », « **3/3** » échouées, espacées
d'environ deux secondes, puis « arrêt : liaison irrécupérable. Ce qui est créé reste créé,
… ». La barre **gèle sous son total**. Le rapport final commence par « **Lot interrompu** »
et porte « La liaison est tombée : **relancer le lot suffit, rien à corriger.** ».
*Verdict* : OK / KO —

**83 — Reprise après l'arrêt** · boîtier : oui
*Objectif* : le lot reprend là où il en est, sans rien créer deux fois.
*Départ* : cas 82 joué, réseau rebranché ; relever ce que le boîtier porte réellement.
*Actions* : relancer le **même** CSV en lot réel ; comparer au relevé.
*Attendu* : les comptes déjà créés tombent en « déjà présent, ignoré », les autres sont
créés, et le boîtier finit avec **exactement** les 200 comptes, chacun une fois. Aucun échec
« existe déjà ».
*Verdict* : OK / KO —

**84 — Coupure entre la création et le mot de passe** · boîtier : oui
*Objectif* : un compte créé mais laissé sans mot de passe ne doit jamais sortir du lot sans
trace.
*Départ* : `lot-200.csv`, lot réel en cours. **Noter NJ si le moment ne peut pas être visé.**
*Actions* : couper la liaison juste après qu'une ligne « … : créé » soit apparue.
*Attendu* : le journal porte « <identifiant> : coupure réseau après la création : compte créé
sans mot de passe utilisable, à reprendre à la main ». Ce compte figure au rapport sous
« Comptes créés sans mot de passe — à reprendre », et dans le CSV exporté avec un champ vide.
Il existe bien sur le boîtier.
*Verdict* : OK / KO / NJ —

**85 — Arrêt définitif sur mot de passe d'administration erroné** · boîtier : oui
*Objectif* : ce qu'aucune reconnexion ne résout ne doit pas être retenté — le boîtier
verrouillerait le compte.
*Départ* : outil ouvert, mot de passe d'administration **volontairement faux**.
*Actions* : cliquer *Lancer* ; chronométrer ; consulter ensuite le compteur anti-bruteforce
du boîtier s'il est consultable.
*Attendu* : arrêt **immédiat** (pas de six secondes d'attente), **une seule** tentative
d'authentification côté boîtier, **aucune** ligne « reconnexion n/3 ». Le journal porte
« arrêt définitif : … Une reconnexion n'y changerait rien : corrigez les identifiants ou la
configuration avant de relancer le lot. ». Le rapport final commence par « Lot interrompu »
et dit de **corriger avant de relancer**.
*Verdict* : OK / KO —

**86 — Les deux arrêts se distinguent dans le rapport** · boîtier : oui
*Objectif* : la conduite à tenir est lisible sans fouiller des centaines de lignes de
journal.
*Départ* : cas 82 (réseau) et cas 85 (fatal) joués.
*Actions* : comparer la **première ligne** des deux rapports finaux.
*Attendu* : le rapport du cas 82 porte « La liaison est tombée : relancer le lot suffit, rien
à corriger. » ; celui du cas 85 porte « Une reconnexion n'y changerait rien : corrigez … avant
de relancer. ». Les deux commencent par « Lot interrompu » et finissent par « Ce qui est créé
reste créé. ».
*Verdict* : OK / KO —

**87 — Hôte malformé : arrêt immédiat, sans reconnexions** · boîtier : non
*Objectif* : requalifier la réserve de la tâche 10 — la connexion **initiale** n'est pas
retentée, seule une coupure en cours de lot l'est.
*Départ* : hôte = `???`, les autres champs renseignés, CSV valide.
*Actions* : cliquer *Lancer*, chronométrer.
*Attendu* : une boîte « **Arrêt** » apparaît **sans délai perceptible**. Le journal ne porte
**aucune** ligne « reconnexion n/3 échouée ». Le bouton *Lancer* redevient actif.
*Verdict* : OK / KO —

**88 — Après un arrêt, *Lancer* redevient actif** · boîtier : oui
*Objectif* : un arrêt ne laisse pas l'outil inutilisable.
*Départ* : l'un quelconque des cas 82, 85, 87 joué.
*Actions* : observer le bouton *Lancer* après l'arrêt, puis relancer.
*Attendu* : le bouton est **actif** et un nouveau lot peut partir sans redémarrer l'outil.
*Verdict* : OK / KO —

**89 — Le journal n'est pas vidé entre deux lancements** · boîtier : oui
*Objectif* : le journal est la **seule** trace des comptes à reprendre à la main ; l'effacer
la perdrait.
*Départ* : un premier lot a produit au moins une ligne d'échec.
*Actions* : relancer un second lot ; faire défiler le journal vers le haut.
*Attendu* : le contenu du premier lot est **toujours là**, et chaque lot est précédé de sa
ligne `───────── nouveau lancement (simulation) ─────────` ou `… (lot réel) …` selon le mode,
la mention correspondant bien à l'état de la case Simulation.
*Verdict* : OK / KO —

---

# M. Annuaire LDAP interne

**90 — Aucun annuaire : la fenêtre de création s'ouvre** · boîtier : oui
*Objectif* : le seul chemin par lequel `CONFIG LDAP INITIALIZE` est atteignable.
*Départ* : boîtier de maquette **sans aucun** annuaire LDAP interne. (Vérifier d'abord le cas
37 : une fenêtre qui s'ouvrirait sur un boîtier pourvu signalerait une clé de lecture fausse.)
*Actions* : lancer un lot (simulation ou réel).
*Attendu* : une **fenêtre séparée** s'ouvre, demandant `domainname`, `o`, `dc` et le mot de
passe de `cn=StormshieldAdmin`, portant les phrases « Le boîtier ne déclare aucun annuaire
LDAP interne. » et « **Cette opération ne se refait pas.** », avec un bouton *Créer
l'annuaire*. L'écran principal reste **nu** : aucun plan, aucune progression.
*Verdict* : OK / KO —

**91 — Champ manquant dans la fenêtre d'annuaire** · boîtier : oui
*Objectif* : une commande qui écrase une base ne part pas sur une saisie incomplète.
*Départ* : cas 90, fenêtre ouverte.
*Actions* : laisser `o` et le mot de passe vides, cliquer *Créer l'annuaire*.
*Attendu* : boîte « **Champ manquant** » listant « À renseigner : o, mot de passe de
cn=StormshieldAdmin ». **Rien n'est envoyé au boîtier**.
*Verdict* : OK / KO —

**92 — Création réussie** · boîtier : oui
*Objectif* : la séquence `INITIALIZE` → `ACTIVATE` → relecture aboutit.
*Départ* : cas 90, fenêtre ouverte, quatre champs renseignés.
*Actions* : cliquer *Créer l'annuaire* ; puis relancer le lot ; puis relire l'annuaire sur le
boîtier.
*Attendu* : le journal principal porte « création de l'annuaire <domaine> en cours » puis
« annuaire <domaine> créé et activé ». La fenêtre de création **se ferme**, et une boîte
« Annuaire créé » invite à relancer le lot. Le boîtier porte bien l'annuaire, **activé**. Le
lot relancé se déroule normalement.
*Verdict* : OK / KO —

**93 — Le mot de passe d'annuaire n'est ni généré ni conservé** · boîtier : oui
*Objectif* : l'outil ne fabrique jamais un secret à la place de l'opérateur, et ne le garde
pas.
*Départ* : cas 92 joué (ou cas 97, création refusée).
*Actions* : provoquer à nouveau l'ouverture de la fenêtre de création (sur un boîtier remis
sans annuaire), et lire les quatre champs.
*Attendu* : **les quatre champs sont vides**, mot de passe compris. Aucune valeur n'est
pré-remplie, aucune proposée.
*Verdict* : OK / KO —

**94 — Fermer le dialogue pendant la création** · boîtier : oui
*Objectif* : `CONFIG LDAP INITIALIZE` est déjà parti ; il ne s'annule pas.
*Départ* : cas 90, quatre champs renseignés.
*Actions* : cliquer *Créer l'annuaire*, puis **immédiatement** la croix du dialogue ; après le
verdict, recliquer la croix.
*Attendu* : la première fermeture est **refusée**, avec la boîte « Création en cours »
expliquant que la commande est déjà partie et qu'il faut attendre son verdict. Après le
verdict, la croix referme normalement le dialogue.
*Verdict* : OK / KO —

**95 — Fermer la fenêtre principale pendant `CONFIG LDAP INITIALIZE`** · boîtier : oui
*Objectif* : la commande la plus destructrice du produit ne doit jamais se refermer sur
elle-même sans un mot, même quand c'est la fenêtre principale que l'on ferme, pas le dialogue.
*Départ* : cas 90 (fenêtre de création d'annuaire ouverte), quatre champs renseignés.
*Actions* : cliquer *Créer l'annuaire* ; **immédiatement**, cliquer la croix de la **fenêtre
principale** (et non celle du dialogue) ; répondre **Non** ; attendre le verdict de la
création.
*Attendu* : une boîte de confirmation apparaît, nommant explicitement `CONFIG LDAP INITIALIZE`,
disant que la commande est déjà partie sur le boîtier, qu'elle ne s'annule pas et que son
verdict serait perdu en fermant maintenant. **Non** est présélectionné : appuyer sur Entrée
annule la fermeture. Après **Non**, la fenêtre principale **reste ouverte** et le dialogue de
création poursuit normalement jusqu'à son verdict.
*Verdict* : OK / KO —

**96 — Après le verdict de création, fermer la fenêtre principale ne pose plus de question sur l'annuaire** · boîtier : oui
*Objectif* : le drapeau qui protège la fermeture pendant `CONFIG LDAP INITIALIZE` doit
retomber une fois le verdict connu — succès ou refus — et ne doit fausser aucune fermeture
suivante.
*Départ* : cas 92 (création réussie) ou cas 97 (création refusée) joué.
*Actions* : après le verdict, cliquer la croix de la **fenêtre principale**.
*Attendu* : **aucune question ne mentionne l'annuaire ni `CONFIG LDAP INITIALIZE`** dans la
boîte de fermeture qui apparaîtrait le cas échéant (elle ne peut plus porter que sur un lot en
cours ou des mots de passe non enregistrés). Si rien de tout cela n'est en cours, la fenêtre
se ferme sans aucune question.
*Verdict* : OK / KO —

**97 — Création refusée par le boîtier** · boîtier : oui
*Objectif* : un refus laisse l'opérateur corriger, il ne fige pas le dialogue.
*Départ* : cas 90 ; saisir un `dc` volontairement invalide.
*Actions* : cliquer *Créer l'annuaire*.
*Attendu* : boîte « **Création refusée** » portant le message du boîtier, le dialogue **reste
ouvert** et le bouton *Créer l'annuaire* **redevient actif**. La ligne d'échec figure aussi
au journal principal.
*Verdict* : OK / KO —

**98 — Un refus de `CONFIG LDAP INITIALIZE` ne laisse pas voir le mot de passe** · boîtier : oui
*Objectif* : le masquage `password=***` s'applique aussi à la commande qui porte le mot de
passe de `cn=StormshieldAdmin`, la plus sensible du produit.
*Départ* : cas 97 rejoué (`dc` volontairement invalide).
*Actions* : cliquer *Créer l'annuaire* ; relire la boîte « Création refusée » **et** la ligne
correspondante du journal principal.
*Attendu* : **aucun mot de passe en clair** n'apparaît, ni dans la boîte, ni dans le journal.
Si le boîtier a renvoyé la commande dans son refus, elle porte `password=***` ou
`password%3D***`, jamais le mot de passe saisi en clair.
*Verdict* : OK / KO —

**99 — La fenêtre principale est inerte pendant le dialogue** · boîtier : oui
*Objectif* : mesurer l'effet réel de `grab_set()` — comportement non couvert par le code.
*Départ* : cas 90, dialogue ouvert.
*Actions* : cliquer *Lancer* sur la fenêtre principale, puis sa croix, puis un champ de
saisie.
*Attendu* : **aucune de ces actions n'aboutit** tant que le dialogue est ouvert : pas de
nouveau lot, pas de fermeture, pas de saisie. Si l'une aboutit, le consigner : la modalité
n'est pas celle attendue.
*Verdict* : OK / KO —

**100 — Un annuaire apparu entre-temps** · boîtier : oui
*Objectif* : la revérification interne protège contre l'écrasement d'une base existante, même
si l'appelant se trompe.
*Départ* : cas 90, dialogue ouvert ; **créer un annuaire depuis l'interface web du boîtier**
pendant que le dialogue est ouvert.
*Actions* : renseigner les quatre champs et cliquer *Créer l'annuaire*.
*Attendu* : boîte « Création refusée » disant que le boîtier déclare déjà un annuaire, que
l'initialisation écraserait sa base et qu'elle est refusée, avec la mention « **Un annuaire
est apparu entre-temps : il n'y a plus rien à créer.** ». Aucune commande d'initialisation
n'a été exécutée : la base créée depuis l'interface web est **intacte**.
*Verdict* : OK / KO —

**101 — Plusieurs annuaires : arrêt net** · boîtier : oui
*Objectif* : l'outil s'arrête plutôt que de choisir où partiraient les groupes.
*Départ* : maquette déclarant **deux** annuaires internes.
*Actions* : lancer un lot.
*Attendu* : boîte « Arrêt » portant « le boîtier déclare plusieurs annuaires LDAP internes :
<liste>. L'outil s'arrête plutôt que de choisir. », les annuaires étant **nommés**. **Aucune
fenêtre de création** ne s'ouvre, **aucune écriture** n'a lieu.
*Verdict* : OK / KO —

**102 — Message terminal inconnu dans le dialogue d'annuaire** · boîtier : oui
*Objectif* : un message que le dialogue de création ne reconnaît pas ne doit jamais le
verrouiller.
*Départ* : aucun moyen simple de provoquer ce cas sur le binaire livré — aucun message
terminal inconnu ne tombe aujourd'hui dans cette branche. **Noter NJ si aucune provocation
n'est possible** (build de recette instrumenté pour émettre depuis `travailler_annuaire` un
message que le dialogue ne reconnaît pas).
*Actions* : provoquer l'émission d'un tel message pendant une création d'annuaire en cours.
*Attendu* : le journal principal porte « message non affiché, type inconnu de la fenêtre :
… » ; le dialogue **reste fermable** ensuite par sa croix, sans boîte « Création en cours ».
*Verdict* : OK / KO / NJ —

---

# N. Certificat

**103 — La case pilote réellement la vérification** · boîtier : oui
*Objectif* : prouver que la case n'est pas décorative et que la valeur n'est pas câblée en
dur.
*Départ* : boîtier à certificat auto-signé, **sans** son autorité installée sur le poste.
*Actions* : lancer une fois la case **cochée**, puis une fois **décochée**.
*Attendu* : cochée, la connexion **échoue** avec un message nommant explicitement un problème
de certificat. Décochée, la connexion **aboutit** et la simulation se déroule. Les deux
issues doivent différer : deux échecs, ou deux succès, sont un KO.
*Verdict* : OK / KO —

**104 — La case revient cochée à chaque ouverture** · boîtier : non
*Objectif* : un contournement ne se mémorise pas.
*Départ* : décocher la case, lancer (peu importe l'issue), fermer l'outil.
*Actions* : rouvrir l'outil.
*Attendu* : la case **Vérifier le certificat** est de nouveau **cochée**.
*Verdict* : OK / KO —

---

# O. Volume et robustesse de l'interface

**105 — 200 comptes : la fenêtre reste utilisable** · boîtier : oui
*Objectif* : le lot réaliste ne fige pas l'outil.
*Départ* : `lot-200.csv`, boîtier vierge de ces comptes.
*Actions* : lancer un lot réel ; pendant toute son exécution, faire défiler le journal,
sélectionner du texte, redimensionner la fenêtre.
*Attendu* : la fenêtre répond en permanence, ne blanchit jamais, n'affiche jamais « Ne répond
pas ». La barre progresse régulièrement jusqu'à son total. Les 200 comptes existent à la fin.
*Verdict* : OK / KO —

**106 — Le journal est sélectionnable et copiable** · boîtier : oui
*Objectif* : l'opérateur doit pouvoir sortir la liste des comptes à reprendre, alors que la
zone est en lecture seule.
*Départ* : un lot terminé avec des échecs au journal.
*Actions* : sélectionner plusieurs lignes à la souris, faire `Ctrl-C`, coller dans le
Bloc-notes ; puis tenter de **taper** du texte dans le journal.
*Attendu* : le texte se sélectionne et se colle **intégralement**, accents et ligne de
séparation compris. La frappe au clavier **ne modifie pas** le journal.
*Verdict* : OK / KO —

**107 — Anomalie interne de l'interface** · boîtier : oui
*Objectif* : vérifier que la pompe d'événements survit à une exception d'affichage — sans
quoi barre et journal gèleraient pendant que l'écriture continue sur le firewall.
*Départ* : aucun moyen simple de provoquer l'anomalie sur le binaire livré. **Si aucune
provocation n'est possible, jouer la variante de contrôle ci-dessous et noter NJ pour le cas
principal.**
*Actions (principal)* : provoquer une exception dans l'affichage (build de recette instrumenté).
*Attendu (principal)* : le journal porte « anomalie interne de l'interface … » **suivi de la
trace complète** ; une boîte « Anomalie interne » s'ouvre, dont le texte dit que le bouton
« Lancer » reste grisé jusqu'au bilan du lot ; **la barre et le journal continuent de suivre
le lot** jusqu'à son terme ; le bouton *Lancer* **reste grisé** pendant tout ce temps et ne
redevient actif **qu'au message de bilan final** de ce lot (« Terminé : … » ou
« Lot interrompu … »), jamais avant.
*Actions (variante de contrôle)* : jouer les cas 49, 80 et 105 en lisant le journal en
entier.
*Attendu (variante)* : **aucune** ligne « anomalie interne de l'interface » et **aucune**
ligne « message non affiché, type inconnu de la fenêtre » n'apparaît en usage normal.
*Verdict* : OK / KO / NJ —

**108 — Une seule boîte d'anomalie par lot, les suivantes au journal seulement** · boîtier : oui
*Objectif* : une panne d'affichage qui se répète ne doit pas empiler une boîte modale par
message, ce qui rendrait la fenêtre inatteignable sur un lot de deux cents comptes.
*Départ* : cas 107 rejoué avec une anomalie qui se répète sur **plusieurs** messages du même
lot (build de recette instrumenté). **Noter NJ si l'anomalie ne peut être provoquée qu'une
seule fois.**
*Actions* : laisser le lot dérouler plusieurs messages provoquant chacun l'anomalie ; compter
les boîtes « Anomalie interne » qui s'ouvrent, et les lignes correspondantes au journal.
*Attendu* : **une seule** boîte « Anomalie interne » s'ouvre pour tout le lot. Le journal, lui,
porte **une ligne d'anomalie par message fautif** — aucune n'est perdue. Aucune boîte ne
s'empile ni ne se rouvre en cascade.
*Verdict* : OK / KO / NJ —

**109 — Un nouveau lot rouvre le droit à une boîte d'anomalie** · boîtier : oui
*Objectif* : le silence imposé par le cas 108 ne vaut que pour le lot qui a déjà parlé ; il
ne doit pas s'étendre aux lots suivants.
*Départ* : cas 108 joué (la boîte du lot précédent a déjà été consommée).
*Actions* : lancer un **nouveau** lot ; provoquer à nouveau l'anomalie (même build
instrumenté).
*Attendu* : une boîte « Anomalie interne » **s'ouvre à nouveau**, pour ce nouveau lot.
*Verdict* : OK / KO / NJ —

---

# P. Compléments de la revue finale

Cas ajoutés après la revue finale de branche. Numérotés à la suite pour ne pas décaler la
numérotation à laquelle la traçabilité renvoie.

**110 — Nom de personne contenant un guillemet double** · boîtier : oui
*Objectif* : le nom et le prénom sont cités exactement comme un nom de groupe, et le
guillemet n'y est pas davantage échappé. Le cas 59 ne mesure que les groupes ; rien ne
prouvait que le comportement était le même sur un patronyme, qui est pourtant le champ le
plus susceptible d'en porter un.
*Départ* : `lot-nom-guillemet.csv`, comptes absents du boîtier.
*Actions* : lancer un lot réel, relire les comptes du boîtier.
*Attendu* : la ligne **n'est pas rejetée à la lecture** (seul l'identifiant est contraint).
`USER CREATE` est refusé par le boîtier, le journal porte « d.oconnor : échec de création
(…) » et le rapport l'inscrit sous `USER CREATE`. Les deux comptes encadrants sont créés. La
seule issue inacceptable est un compte créé sous un **nom tronqué**, silencieusement.
*Verdict* : OK / KO —

---

# Récapitulatif

| Section | Cas | Boîtier requis |
|---|---|---|
| B — Empaquetage et premier lancement | 1 – 5 | non |
| C — Ouverture et état initial | 6 – 12 | non |
| D — Refus avant tout envoi | 13 – 18 | non |
| E — Simulation sur boîtier | 19 – 30 | **oui** |
| F — Hypothèses de l'adaptateur SDK | 31 – 41 | **oui** |
| G — Politique de mot de passe | 42 – 48 | **oui** |
| H — Exécution réelle et idempotence | 49 – 57 | **oui** |
| I — Échecs isolés et noms hostiles | 58 – 62 | **oui** |
| J — Mots de passe | 63 – 76 | **oui** |
| K — Fermeture de la fenêtre | 77 – 78 | **oui** |
| K — Fermeture de la fenêtre | 79 | non |
| L — Coupures, arrêts et reprise | 80 – 86, 88, 89 | **oui** |
| L — Coupures, arrêts et reprise | 87 | non |
| M — Annuaire LDAP interne | 90 – 102 | **oui** |
| N — Certificat | 103 | **oui** |
| N — Certificat | 104 | non |
| O — Volume et robustesse | 105 – 109 | **oui** |
| P — Compléments de la revue finale | 110 | **oui** |

**21 cas sans boîtier** : 1 à 18, 79, 87 et 104. Ils se jouent dès qu'un poste Windows et le
`.exe` sont disponibles, sans attendre la maquette.
**89 cas exigeant un boîtier** : tous les autres. **110 cas au total.**

## Traçabilité

Ce cahier reprend intégralement la liste de 55 points issue de la revue de la fenêtre, les 22
cas prévus par le plan, et les hypothèses non vérifiées de l'adaptateur SDK. Table de
correspondance, et **points devenus caducs**, qui ne sont donc pas repris tels quels.

**Les 55 points de la revue de la fenêtre** → cas de ce cahier :

| Points | Cas |
|---|---|
| 1 – 5 (ouverture) | 6, 7, 8, 9, 10 |
| 6 (démarrage impossible) | 5 |
| 7 – 11 (saisie et refus) | 12, 13, 16, 17 ; le point 10 devient le cas 45 |
| 12 – 16 (simulation) | 20, 22, 31, 19, 24 |
| 17 – 19 (durcissement, refus) | 42, 43, 46 |
| 20 – 26 (exécution réelle) | 56, 63, 64, 105, 106, 67, 89 |
| 27 – 32 (perte de secrets) | 70, 71, 72, 73, 74, 76 |
| 33 – 35 (fermeture) | 77, 78, 79 |
| 36 – 40 (enregistrement) | 65, 66, 67, 68, 69 |
| 41 – 44 (coupures et arrêts) | 80, 85, 86, 88 |
| 45 – 53 (annuaire) | 90, 91, 92, 93, 94, 99, 101, 39 |
| 54 (anomalie interne) | 107 |
| 55 (certificat) | 103 |

**Les 22 cas du plan** → cas de ce cahier : 1→19, 2→49, 3→51, 4→16, 5→53, 6→28, 7→29, 8→26,
9→25, 10→27, 11→42, 12→43, 13→63 et 66, 14→58, 15→59, 16→80 et 82, 17→83, 18→103, 19→90 et 92,
20→101, 21→105, 22→2 et 3.

**Les hypothèses de l'adaptateur SDK** → section F : table `MinSetOfChars` → cas 31 ; clés
`name` et `domain` → cas 35, 36, 37 ; annuaires externes non filtrés → cas 39 ; `MinLength`
vide → cas 33 ; journalisation du SDK et fuite de secret → cas 40 ; nom de groupe avec
guillemet, espace, saut de ligne → cas 59, 60, 61.

**Les points de la vague de correctifs R1 à R6** (voir
`.superpowers/sdd/2026-09-16-injection-utilisateurs-plan/task-11-report.md`) → cas de ce
cahier : recompte total des secrets après le bilan d'un lot (R6) → cas **74**, réécrit ;
enregistrement pendant qu'un sélecteur reste ouvert (R1) → cas **75** ; bouton *Lancer* resté
grisé après une anomalie interne (R2) → cas **107**, réécrit ; une seule boîte d'anomalie par
lot et son réarmement au lot suivant (R3) → cas **108**, **109** ; fermeture de la fenêtre
principale pendant `CONFIG LDAP INITIALIZE` (R4) → cas **95**, **96** ; masquage du mot de
passe dans un refus de création d'annuaire (R6) → cas **98** ; message terminal inconnu dans
le dialogue d'annuaire → cas **102**.

### Points devenus caducs

Trois points de la liste héritée ne décrivent plus le produit et **ne sont volontairement pas
repris** :

1. **« Lancer avec Simulation décochée avant toute connexion → refus demandant de simuler
   d'abord »** (point 8 de la première liste). L'obstacle a été retiré : un premier lot part
   directement en réel, et c'est le boîtier qui arbitre. Remplacé par les cas **55** (le lot
   part) et **46** (le boîtier refuse la politique).
2. **« Les deux arrêts ne se distinguent que dans le journal »** (point 29 de la première
   liste). `Rapport.motif_arret` porte désormais la distinction : le rapport lui-même dit
   quelle conduite tenir. Devenu le cas **86**.
3. **« Un hôte vide donne trois reconnexions inutiles »** (réserve 5 de la tâche 10).
   Requalifié, pour deux raisons vérifiées sur le code : un hôte vide est refusé par
   `obstacles_au_lancement` **avant toute connexion**, et la connexion **initiale** n'est de
   toute façon jamais retentée — les trois tentatives ne concernent qu'une coupure survenant
   en cours de lot. Deux cas le mesurent au lieu d'un : **15** (hôte vide, refus immédiat) et
   **87** (hôte malformé, arrêt immédiat sans reconnexion).

Un quatrième point a changé de nature : **« Longueur saisie non numérique »** (point 10) ne
peut plus être joué sans boîtier. Les champs de politique restent grisés tant qu'aucune
lecture n'a eu lieu, et l'outil n'utilise alors même pas leur valeur : le cas **45** exige
donc une lecture préalable, donc un boîtier.

## Nettoyage après recette

La recette laisse sur la maquette les comptes et groupes créés, ainsi que d'éventuels
annuaires. Les supprimer, et détruire les CSV de mots de passe produits en cours de recette :
ce sont des secrets en clair.

## Ce que ce cahier ne couvre pas

- La construction du `.exe` sur un autre système que `windows-latest` : il n'y en a pas
  d'autre, et c'est délibéré.
- La signature du binaire : hors périmètre v1, faute de certificat. Le cas 2 constate
  l'avertissement, il ne le fait pas disparaître.
- Les performances au-delà de 200 comptes.
- L'injection de blacklists, qui n'existe pas encore.
