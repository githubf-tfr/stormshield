<!-- Généré par githubf-tfr/claude (propagation). Ne pas éditer : écrasé au prochain passage. -->
> Règles héritées des chapeaux, dans l'ordre. Sources : githubf-tfr/claude@1e6a7b4. En cas de contradiction, l'`AGENTS.md` de ce repo gagne.

# AGENTS.md — claude (chapeau des projets `~/Git`)

**Chapeau.** Règles communes aux projets de `~/Git`. Chaque projet reste autonome — son
`AGENTS.md` **gagne** sur un point qui lui est propre ; signale la contradiction, ne la
tranche pas seul.

## Chapeau ou feuille

Un repo est un chapeau si son `AGENTS.md` commence par `**Chapeau.**` (`claude`, `rpi-fleet`,
`warhammer`) ; sinon c'est une feuille. Chapeau : lis son `README.md` ; un chapeau autre que
`claude` lit aussi `claude:README.md` s'il est accessible. Feuille : aucun `README.md` au
démarrage.

## Entretien des `AGENTS.md`

**Réduis tout `AGENTS.md` que tu touches.** Coupe ce qu'un greffon porte déjà, les lignes sans
effet et les justifications évidentes. **Ajouter sans compresser est un défaut.** Ce qu'une
feuille n'a pas à savoir va dans le `README.md` de son chapeau (`claude:README.md` pour l'atelier).
`.claude/rules/heritage.md` ne s'édite jamais : il se régénère (`claude:propagation/`).
Un `AGENTS.md` de chapeau est lu hors de son repo : citer tout autre fichier en `repo:chemin`.

## Méthode : superpowers

**Obligatoire pour tout dev au sens large** — code, Ansible, Docker/Compose, scripts, IaC ;
aucune consigne utilisateur requise. Autres tâches complexes : à proposer. Hors greffon, une
seule règle : **jamais « terminé » sans avoir exécuté les commandes et lu leur sortie.**

**Routage.** Greffons de production (`brainstorming`, `writing-plans`,
`test-driven-development`, `executing-plans`) : en sous-agent, jamais en session principale —
un dispatch = un rôle = un greffon. La principale cadre, conteste le livrable, arbitre ; ne
produit pas. Exception : `subagent-driven-development` et `dispatching-parallel-agents` *sont*
le pilotage. `<SUBAGENT-STOP>` : le prompt de dispatch nomme le greffon, le sous-agent n'invoque rien seul.

| Artefact | Emplacement | Versionné |
|---|---|---|
| Spec, plan, cahier de recette | `docs/superpowers/{specs,plans}/` | oui |
| Ledger | `.superpowers/sdd/` | **non** |

Un plan achevé se fond dans la doc pérenne, puis se supprime.

## Consigne temporaire — abonnement max

Hors méthode, ne se combine avec rien d'autre. À supprimer quand l'abonnement retombe.
**Parallélise au maximum** : dispatchs sans dépendance émis dans la même réponse (appels
simultanés), jamais l'un après l'autre.

## Délégation

Sous-agent natif de l'agent choisi, aucun outil tiers. **Chaque dispatch fixe `model`** :
le moins cher qui tient le rôle (barème § *Model Selection* de `subagent-driven-development`),
sans hériter du modèle de session.

## Documentation : trois rôles

| Fichier | Rôle |
|---|---|
| `README.md` | Le *comment*, générique et intemporel. Aucune date, aucun avancement. |
| `KANBAN.md` | Le journal daté. Seule source pour « où on en est ». |
| `AGENTS.md` | Conventions et invariants pour qui *modifie*. Ni catalogue, ni journal. |

Un seul fichier générique par projet, pas de `README` par sous-dossier. Le **pourquoi** est
co-localisé : commentaire à côté de la valeur, section « Écartés » pour les refus de fond.

Créer ou refondre un `KANBAN.md` : partir du gabarit, qui porte ses consignes :
`claude:gabarits/KANBAN.md` ; sinon `raw.githubusercontent.com/githubf-tfr/claude/main/gabarits/KANBAN.md`.

## Tests : trois niveaux, aucun ne dispense d'un autre

**1. Unitaires.** On teste des comportements, jamais des rouages : le test survit à une
réécriture interne. Vérifier qu'une fonction interne a été appelée est interdit. **Aucun test
ne requiert root ni matériel** — tout appel système ou chemin cible passe par un paramètre
injectable à défaut de production. Ce qui exige un privilège est isolé derrière un marqueur
(`-m network`, `-m volumes`) ou renvoyé au niveau 3.

**2. Analyse statique.** Chaque repo déclare sa commande et elle passe **avant tout commit** :
`ruff` + `mypy`, `ansible-lint`, l'équivalent ailleurs.
Repo `claude` : `uv tool run ruff check propagation && uv tool run ruff format --check propagation && uv tool run mypy --strict propagation`.

**3. Cahier de recette.** Fonctionnel. **Couvre tous les cas d'usage, y compris ceux déjà
couverts en unitaire** : l'un prouve que le code fait ce qu'on a écrit, l'autre que le produit
fait ce qu'on attend. Exécution : **P1 automatisée** ; P2, ce qui ne s'automatise pas, par
l'IA ou l'humain selon le cas. Le mettre à jour fait partie de la demande.

## Idempotence

**Tout ce qui s'installe ou se rejoue doit l'être deux fois sans effet de bord.** L'état se
détecte sur le système réel, jamais dans un fichier d'état maison.

## Une limitation assumée n'est pas un défaut à corriger

Mode d'échec le plus coûteux : ce qui paraît cassé ou faible est « réparé », et un choix
délibéré disparaît — hook volontairement non bloquant, `git-crypt` qui fait échouer git
(l'échec *est* la protection), absence de filet assumée.

Avant de renforcer ou contourner un garde-fou, **cherche pourquoi il est ainsi** (`KANBAN.md`,
« Écartés », commentaire). La raison prime ; introuvable, demande.

## Vocabulaire

Quand un mot désigne deux choses, le repo tient une section « Vocabulaire » et le mot est
**systématiquement qualifié**. Ne renomme pas pour lever l'ambiguïté : qualifie.

## Secrets

1. **Ne jamais générer ni remplacer un secret à la place de l'utilisateur** — même « un mot de
   passe fort » proposé de bonne foi. Attends sa valeur exacte.
2. **Aucun secret en clair, aucun `.env` commité** : que des `*.example`. Les secrets suivis
   sont chiffrés (`git-crypt` sous `rpi/deploiement/`), clé jamais demandée ni acceptée.
3. ⚠️ `.claude/settings.local.json` contient un mot de passe en clair. Gitignoré, à garder
   ainsi : ne le recopie pas, ne le colle pas dans un rapport.

## Git

- Remotes sous `github.com/githubf-tfr/`. **Vérifie la branche avant de pousser**, `main`
  n'est pas universel.
- **Ticket de demande** : entre repos sans lien hiérarchique, du consommateur vers l'outil.
  Un chapeau (`**Chapeau.**`) n'en émet jamais — il agit.
- **Ticket d'ordre** : d'un chapeau vers un repo qu'il domine, seulement s'il ne peut pas agir
  (secret chiffré, remote injoignable). Titre en `[ordre]`, commande exacte dans le corps.
- **Toute session lit les tickets ouverts du repo** ; un `[ordre]` non résolu passe avant.
- **Ne touche à aucun repo autre que celui visé par la tâche** — accès en écriture ≠ autorisation. Vérifie le chemin absolu avant d'écrire.

## Style de travail

- **Français**, réponses **concises** : une action = un résultat ; ni préambule, ni
  récapitulatif, ni raisonnement exposé sauf demande.
- Français **dans le code** sur les projets qui l'ont adopté — ne l'impose pas ailleurs.
- **L'utilisateur tranche.** En cadrage : 1-2 questions maximum, tranche le reste.
- **Proposer avant de faire** : au-delà de 5 lignes, montrer le diff.
- **Strict minimum de code**, **rien qui n'ait été demandé**.
- **Ne re-tranche pas une décision prise**, ne généralise pas une décision ponctuelle.
- **Caveman `full` obligatoire** : coupe articles, remplissage, politesses et hésitations ;
  fragments permis, mots courts, termes techniques exacts. Préserve toute substance technique.
  Forme : fait, action, raison, prochaine étape. Code inchangé.
- Niveaux : `/caveman lite|full|ultra|wenyan`. Ne change de niveau ou ne désactive que sur
  consigne explicite de l'utilisateur (`stop caveman` ou `normal mode`).
- Reviens au style clair pour les avertissements de sécurité, les actions irréversibles ou
  si l'utilisateur ne comprend pas ; reprends ensuite Caveman.
- Code, commits et PRs : style normal.
