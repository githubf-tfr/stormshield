# Alignement sur un boîtier déjà peuplé (v2) — plan d'implémentation

> **Pour les agents qui exécutent :** SOUS-GREFFON REQUIS — `superpowers:subagent-driven-development`
> (recommandé) ou `superpowers:executing-plans`, tâche par tâche. Les étapes sont des cases à
> cocher (`- [ ]`).

**But :** faire reconnaître à l'outil les comptes et les groupes qu'un boîtier porte déjà,
quelle que soit leur casse, et ajouter aux comptes — nouveaux comme existants — les seules
adhésions de groupe que le fichier décrit et que le boîtier n'a pas.

**Architecture :** la décision reste pure et hors ligne. Un module neuf porte la seule clé de
rapprochement du produit (`casefold`) et l'extraction de l'`uid` d'un DN ; `plan.py` rend un
travail par compte au lieu de deux listes parallèles ; `execution.py` lit `4 + g` commandes
au lieu de quatre et n'a plus qu'une boucle d'écriture, sur les comptes ; `presentation.py`
dit ce qui arrive à chaque compte et compte les orphelins au lieu de les nommer.

**Pile :** Python 3.11, `pytest`, `ruff`, `mypy --strict`, aucune dépendance nouvelle.

**Spec :** `docs/superpowers/specs/2026-09-17-boitier-peuple-design.md`, qui amende
`docs/superpowers/specs/2026-09-16-injection-utilisateurs-design.md` (v1), laquelle fait
autorité sur tout ce que la v2 ne change pas. Les deux voyagent avec ce plan.

## Contraintes globales

Elles s'appliquent à **toutes** les tâches, sans être répétées dans chacune.

- **Le produit existe, il marche, il est testé.** 299 tests collectés par défaut (301 avec le
  marqueur `firewall`), `ruff` et `mypy --strict` verts, aucun `# type: ignore`. Chaque tâche
  modifie du code vivant : elle dit ce qu'elle change, pas seulement ce qu'elle ajoute.
- **Aucun firewall n'est joignable.** Tout se prouve contre `BoitierMemoire`. Ce qui exige un
  boîtier porte `@pytest.mark.firewall`, exclu par `addopts`.
- **`tkinter` est absent de la machine.** `fenetre.py` n'est **jamais importé**, même
  transitivement, par un test. Deux gardes de structure le vérifient, par analyse `ast` et
  sans rien importer : `tests/test_presentation.py:1461` (sur `fenetre.py` lui-même) et
  `tests/test_amorcage.py` (sur `__main__.py`). Ne les contourner ni les affaiblir sous aucun
  prétexte.
- **Français dans le code** — noms, docstrings, commentaires, messages — et **apostrophes
  droites** (`'`).
- **Avant tout commit** : `.venv/bin/ruff check . --exclude .claude` puis `.venv/bin/mypy`.
  Aucun `# type: ignore`, aucun `# noqa` de confort. `line-length = 100`.
- **Les imports sont triés** (règle `I` de `ruff`) : tout import ajouté se range à sa place
  alphabétique dans son bloc, sinon `ruff` échoue. Les extraits de ce plan montrent le nom à
  importer, pas la ligne où l'écrire.
- **Aucune tâche ne se clôt en cassant la suivante** : chaque tâche laisse
  `.venv/bin/python -m pytest`, `ruff` et `mypy` verts. Quand une tâche rend faux un test de
  la v1, c'est elle qui le corrige, dans le même commit — la liste exhaustive de ces tests est
  écrite dans la tâche qui les casse, avec ce qu'ils deviennent et pourquoi.
- **Aucune chaîne de caractères ne pilote un branchement.** Les événements, les résolutions
  d'identité et les exceptions portent des types ; les branchements se font sur la classe
  (`match` / `isinstance`), jamais sur un texte.
- **On teste des comportements, pas des rouages.** Aucun test ne vérifie qu'une fonction
  interne a été appelée ; les tests d'exécution observent l'état final du double et les
  événements émis. Exception unique et assumée : le journal d'appels du double, qui est
  l'observable du protocole SNS lui-même (« aucune écriture n'est partie »).
- **L'outil n'enlève jamais rien** : ni `USER REMOVE`, ni `USER GROUP DELUSER`, ni
  `USER GROUP REMOVEFROM`, ni `USER UPDATE`, ni `CONFIG PASSWDPOLICY SET`. Aucun de ces verbes
  n'entre dans le produit, à aucune tâche.
- **Critère de fin d'une tâche** : les étapes sont cochées, `.venv/bin/python -m pytest` passe
  **en entier** (pas seulement les tests de la tâche), `ruff` et `mypy` sont verts. **Aucun
  nombre de tests n'est un critère** : les décomptes annoncés dans le plan de la v1 se sont
  tous révélés faux.
- **Commandes** : `.venv/bin/python -m pytest`, `.venv/bin/ruff`, `.venv/bin/mypy` depuis
  `/home/vtramier/claude/stormshield`.

## Ce que la v2 change dans l'existant, en un coup d'œil

| Fichier | Nature du changement |
|---|---|
| `stormshield_utilisateurs/rapprochement.py` | **créé** — clé `casefold`, index des graphies du boîtier, extraction de l'`uid` d'un DN |
| `stormshield_utilisateurs/modele.py` | `EtatBoitier` réécrit, `Plan` réécrit, `TravailCompte`, `GroupeAmbigu` et `CompteAmbigu` ajoutés (**T4**) ; `Rapport` gagne `plan_construit` (**T5**) |
| `stormshield_utilisateurs/plan.py` | `construire` réécrit, `groupes_cites` et `groupes_a_interroger` ajoutés |
| `stormshield_utilisateurs/boitier.py` | une opération de plus au `Protocol` : `lister_membres` (**T3**, en même temps que l'implémentation SDK — voir « Ordre et parallélisme ») ; le renvoi à `execution.lire_etat` de la ligne 44 corrigé en T5 |
| `stormshield_utilisateurs/boitier_memoire.py` | rend des **DN**, accepte des membres non rattachables, `lister_membres` |
| `stormshield_utilisateurs/boitier_sdk.py` | `USER GROUP SHOW`, lecture des champs `member=`, `member_2=`, … ; le renvoi à `lire_etat` de la ligne 199 corrigé en T5 |
| `stormshield_utilisateurs/execution.py` | lecture `4 + g`, arrêt entre deux lectures, **une seule** boucle d'écriture, mot de passe structurellement inatteignable pour un compte existant, refus d'adhésion mémorisés, journal de l'arrêt dédoublé (un arrêt avant le plan n'a interrompu aucun compte) |
| `stormshield_utilisateurs/presentation.py` | rendu du plan par compte, orphelins comptés, membres non rattachés annoncés, ambiguïtés de casse — groupes et comptes — signalées, confirmation enrichie, « déjà présent, ignoré » purgé, docstring de `reglage_barre` (l. 422) corrigée, bilan d'un arrêt tombé avant le plan |
| `stormshield_utilisateurs/fenetre.py` | **une seule docstring** à corriger (celle de `_confirmer_la_perte_des_secrets`, l. 387-391, la formule courant sur 389-390) — aucun changement de câblage : la fenêtre ne touche le plan que par `lignes_du_plan` |
| `README.md`, `docs/recette/2026-09-16-cahier-recette-v1.md`, `KANBAN.md` | mis à jour (tâches 8 à 10) |

Tests existants qui **doivent** changer, et pourquoi :

| Fichier | Ce qui change, et le motif |
|---|---|
| `tests/test_plan.py` | réécrit : `EtatBoitier` et `Plan` changent de forme, et toute la décision change de contenu |
| `tests/test_modele.py` | `test_nombre_d_operations_du_plan` : le plan ne porte plus `comptes_a_creer`/`comptes_ignores` |
| `tests/test_boitier_memoire.py` | `boitier.membres["compta"]` contient désormais des DN, pas des identifiants |
| `tests/test_execution_ecriture.py` | 3 familles : les assertions sur `boitier.membres` (ligne 798 ; la 435 reste vraie), les totaux de `Progression` (la lecture ne vaut plus 4 mais `4 + g`, et le total croît une fois), et l'accès aux champs du plan émis par `PlanPret` ; plus une docstring devenue fausse sans que le test tombe (l. 878-880, jumelle de `reglage_barre`) |
| `tests/test_execution_lecture.py` | **en T4** : `etat.utilisateurs`/`etat.groupes` deviennent des `IndexBoitier` ; **en T5** : `lire_etat` se scinde, `lire_comptes_et_groupes` disparaît au profit de `relire_inventaire`, le nombre d'opérations de lecture n'est plus fixe |
| `tests/test_presentation.py` | `lignes_du_plan`, `texte_de_confirmation_du_lot`, le helper `_plan` et ses six appelants, `plan.orphelins` (l. 866), les textes qui disent « déjà présent, ignoré », et les cinq `Rapport` de la section « arrêt demandé » qui gagnent `plan_construit=True` |
| `tests/test_boitier_sdk.py` | la commande `USER GROUP SHOW` et sa lecture, plus une trace des commandes envoyées sur `_ClientFactice` (T3, étape 1) |
| `tests/fabriques.py` | reçoit `_Interrupteur`, déplacé depuis `tests/test_execution_ecriture.py` pour être partagé avec `tests/test_execution_lecture.py` (T5) |
| `tests/test_lecture.py`, `tests/test_motdepasse.py`, `tests/test_sortie.py` | **inchangés** : la v2 ne touche ni le contrat du CSV, ni la génération des secrets, ni le CSV de sortie |

## Ordre et parallélisme

```
T1 rapprochement ──┐
T2 double (DN)  ───┴─> T4 modèle + décision ─┬─> T5 lecture 4+g ─> T7 garde ─┬─> T8 README
        └─> T3 Protocol + adaptateur SDK ────┘                               ├─> T9 recette
                                             └─> T6 présentation ────────────┴─> T10 KANBAN
```

- **T1 et T2 sont indépendantes** : à dispatcher ensemble.
- **Le `Protocol` et l'adaptateur SDK voyagent ensemble, en T3.** Ajouter `lister_membres` au
  `Protocol` sans l'implémenter sur `BoitierSDK` fait **échouer `mypy`** — `presentation.py:805`
  rend un `BoitierSDK` là où un `Boitier` est annoncé, et `tests/test_boitier_sdk.py:31`
  (`_conformite_au_protocol`) le prouve une seconde fois. Or aucune tâche ne se clôt sans
  `mypy` vert. T2 ne touche donc **que** le double : une méthode de plus sur une classe
  concrète ne gêne aucun `Protocol`, et la suite reste verte.
- **T3 doit être close avant T5** : c'est T5 qui appelle `boitier.lister_membres` sur un
  paramètre annoté `Boitier`, donc qui a besoin de la méthode au `Protocol`. T3 reste
  parallélisable avec T4, qui ne l'appelle pas.
- **T4 doit suivre T1 et T2** : elle change `tests/test_execution_ecriture.py`, que T2 touche
  déjà ; les dispatcher ensemble provoquerait un conflit sur ce fichier.
- **T5 et T6 n'ont aucune dépendance de données** une fois T4 close : leurs fichiers sont
  disjoints (`execution.py` + tests d'exécution d'un côté, `presentation.py`, `fenetre.py` et
  `tests/test_presentation.py` de l'autre), et `reglage_barre` ne dépend pas du total réel —
  la dépendance annoncée « T5 change les totaux que T6 observe » n'existe pas. Les
  paralléliser exige deux arbres de travail séparés : les deux tâches lancent la suite
  **entière**, et un `execution.py` à demi réécrit la ferait échouer chez le voisin. Dans un
  arbre unique, les enchaîner — T5 puis T6.
- **T7 suit T5** : elle éprouve la structure de `execution.py`, et son étape 2 modifie
  temporairement ce fichier — la dispatcher pendant T5 provoquerait un conflit.
- **T8, T9 et T10 sont indépendantes entre elles** : à dispatcher ensemble une fois T6 **et**
  T7 closes (T9 cite les textes de T6 et les lectures `4 + g` de T5).

---

## Vocabulaire du plan

Trois mots se ressemblent et ne désignent pas la même chose. Ils sont qualifiés partout :

- **utilisateur** : une ligne valide du CSV (`modele.Utilisateur`).
- **compte** : une identité que le boîtier a rendue (`USER LIST`).
- **travail** : ce que l'outil va faire à un compte (`modele.TravailCompte`) — c'est le seul
  objet que la boucle d'écriture parcourt.

---

### Tâche 1 : le rapprochement, seul et pur

**Fichiers :**
- Créer : `stormshield_utilisateurs/rapprochement.py`
- Créer : `tests/test_rapprochement.py`

**Interfaces :**
- Consomme : rien.
- Produit : `cle(valeur: str) -> str` ; `uid_du_dn(dn: str) -> str | None` ; les dataclasses
  `Reconnu(orthographe: str)`, `Absent()`, `Ambigu(graphies: tuple[str, ...])` et l'alias
  `Resolution = Reconnu | Absent | Ambigu` ; `IndexBoitier` avec
  `IndexBoitier.depuis(noms: Iterable[str]) -> IndexBoitier`,
  `.resoudre(nom: str) -> Resolution`, `.graphies: tuple[str, ...]`, `.cles: frozenset[str]`.

Ce module existe pour deux raisons que la spec nomme : « une seule fonction, un seul sens de
comparaison » pour les comptes **et** les groupes, et « le repli tient dans une fonction
isolée : l'extraction de l'`uid` depuis un DN est le seul endroit à corriger quand la forme
réelle sera connue ». Il n'importe rien du paquet : ni `modele`, ni `boitier`.

- [ ] **Étape 1 : écrire les tests de la clé et de l'extraction d'uid**

```python
"""Rapprochement des identités : une seule clé, une seule lecture de DN."""

from stormshield_utilisateurs.rapprochement import (
    Absent,
    Ambigu,
    IndexBoitier,
    Reconnu,
    cle,
    uid_du_dn,
)


def test_la_cle_ignore_la_casse() -> None:
    assert cle("Jean.Dupont") == cle("jean.dupont")


def test_la_cle_laisse_inchange_un_identifiant_deja_en_minuscules() -> None:
    """Les identifiants du fichier sont basculés en minuscules par `lecture` : la clé
    ne doit rien leur faire de plus."""
    assert cle("jean.dupont") == "jean.dupont"


def test_l_uid_est_le_premier_composant_du_dn() -> None:
    assert uid_du_dn("uid=Jean.Dupont,ou=users,dc=interne,dc=local") == "Jean.Dupont"


def test_l_uid_se_lit_quelle_que_soit_la_casse_de_l_etiquette() -> None:
    assert uid_du_dn("UID=martin,ou=users,dc=interne,dc=local") == "martin"


def test_un_dn_qui_ne_commence_pas_par_uid_ne_rend_rien() -> None:
    """Sous-groupe, compte d'un autre annuaire, forme inattendue : aucune action, et
    surtout aucune erreur — ce membre sera compté, pas traité."""
    assert uid_du_dn("cn=sous-groupe,ou=groups,dc=interne,dc=local") is None


def test_une_chaine_vide_ne_rend_rien() -> None:
    assert uid_du_dn("") is None
```

- [ ] **Étape 2 : lancer, constater l'échec**

Run : `.venv/bin/python -m pytest tests/test_rapprochement.py -v`
Attendu : ÉCHEC — `ModuleNotFoundError: No module named 'stormshield_utilisateurs.rapprochement'`.

- [ ] **Étape 3 : écrire `cle` et `uid_du_dn`**

```python
"""Rapprochement des identités entre le fichier et le boîtier. Pur, aucun réseau.

Une seule clé de comparaison pour les comptes et pour les groupes, et une seule lecture
de DN : deux règles à retenir et à éprouver plutôt que quatre.
"""

import re

# Premier composant d'un DN, supposé de forme `uid=<valeur>`. C'est la seule hypothèse
# structurante de la v2 (spec, « Points non vérifiés », point 1) et tout le repli tient
# ici : le jour où la forme réelle rendue par USER GROUP SHOW sera connue, c'est cette
# expression et `uid_du_dn` qu'il faudra corriger, et rien d'autre.
_PREMIER_COMPOSANT_UID = re.compile(r"^\s*uid=([^,]+)", re.IGNORECASE)


def cle(valeur: str) -> str:
    """Clé de rapprochement, insensible à la casse. Comptes et groupes, même fonction."""
    return valeur.casefold()


def uid_du_dn(dn: str) -> str | None:
    """L'`uid` du premier composant d'un DN, ou None si le DN n'a pas cette forme.

    None n'est pas une erreur : c'est un membre que l'outil ne sait pas rattacher, donc
    à qui il n'a rien à faire. Il sera compté, jamais nommé.
    """
    trouve = _PREMIER_COMPOSANT_UID.match(dn)
    if trouve is None:
        return None
    return trouve.group(1).strip()
```

- [ ] **Étape 4 : lancer, constater le succès**

Run : `.venv/bin/python -m pytest tests/test_rapprochement.py -v`
Attendu : SUCCÈS.

- [ ] **Étape 5 : écrire les tests de l'index et de la résolution**

À ajouter à `tests/test_rapprochement.py` :

```python
def test_un_nom_absent_de_l_index_est_a_creer() -> None:
    assert IndexBoitier.depuis(("compta",)).resoudre("rh") == Absent()


def test_un_nom_present_est_rendu_sous_l_orthographe_du_boitier() -> None:
    """C'est la seule graphie dont on sache qu'elle existe chez lui."""
    assert IndexBoitier.depuis(("Jean.Dupont",)).resoudre("jean.dupont") == Reconnu(
        "Jean.Dupont"
    )


def test_deux_graphies_vivantes_sans_correspondance_exacte_sont_ambigues() -> None:
    """Un boîtier mal rangé ne doit pas priver les deux cents autres comptes du lot :
    la résolution le dit, elle ne lève pas."""
    resolution = IndexBoitier.depuis(("Compta", "COMPTA")).resoudre("compta")
    assert resolution == Ambigu(("Compta", "COMPTA"))


def test_la_correspondance_exacte_l_emporte_sur_l_ambiguite() -> None:
    """L'opérateur a écrit ce nom-là, il existe tel quel sur le boîtier."""
    assert IndexBoitier.depuis(("Compta", "compta")).resoudre("compta") == Reconnu("compta")


def test_l_index_conserve_toutes_les_graphies_rendues() -> None:
    """Les orphelins se comptent sur les graphies, pas sur les clés : deux comptes que
    la clé confond restent deux comptes du boîtier."""
    index = IndexBoitier.depuis(("Jean.Dupont", "jean.dupont", "martin"))
    assert index.graphies == ("Jean.Dupont", "jean.dupont", "martin")
    assert index.cles == frozenset({"jean.dupont", "martin"})


def test_un_index_vide_ne_reconnait_rien() -> None:
    assert IndexBoitier.depuis(()).resoudre("compta") == Absent()
```

- [ ] **Étape 6 : lancer, constater l'échec**

Run : `.venv/bin/python -m pytest tests/test_rapprochement.py -v`
Attendu : ÉCHEC — `ImportError: cannot import name 'IndexBoitier'`.

- [ ] **Étape 7 : écrire l'index et les résolutions**

À ajouter à `stormshield_utilisateurs/rapprochement.py`, avec les imports que ces
définitions réclament — `from collections.abc import Iterable, Mapping` et
`from dataclasses import dataclass`, à poser seulement maintenant : `ruff` refuse un import
inutilisé, et ils ne servent qu'ici.

```python
@dataclass(frozen=True)
class Reconnu:
    """Le boîtier porte ce nom : c'est sous cette orthographe qu'on l'adressera."""

    orthographe: str


@dataclass(frozen=True)
class Absent:
    """Aucune graphie côté boîtier. Un groupe absent sera créé sous l'orthographe du
    fichier, la seule disponible ; un compte absent sera créé sous la sienne."""


@dataclass(frozen=True)
class Ambigu:
    """Deux graphies vivantes que la clé confond, et aucune égale à celle du fichier.

    L'outil ne sait pas laquelle viser. Il le signale et poursuit : le doublon ne se
    lève qu'à la main, sur le boîtier.
    """

    graphies: tuple[str, ...]


Resolution = Reconnu | Absent | Ambigu


@dataclass(frozen=True)
class IndexBoitier:
    """Ce que le boîtier a rendu, rangé sous la clé de rapprochement.

    Toutes les graphies d'une même clé sont conservées : sans elles, une collision de
    casse serait tranchée au hasard de l'ordre de lecture. N'est jamais hachée.
    """

    par_cle: Mapping[str, tuple[str, ...]]
    graphies: tuple[str, ...]

    @classmethod
    def depuis(cls, noms: Iterable[str]) -> "IndexBoitier":
        rendues = tuple(noms)
        par_cle: dict[str, tuple[str, ...]] = {}
        for nom in rendues:
            par_cle[cle(nom)] = (*par_cle.get(cle(nom), ()), nom)
        return cls(par_cle=par_cle, graphies=rendues)

    @property
    def cles(self) -> frozenset[str]:
        return frozenset(self.par_cle)

    def resoudre(self, nom: str) -> Resolution:
        """Exacte d'abord, unique ensuite, ambiguë en dernier recours."""
        graphies = self.par_cle.get(cle(nom), ())
        if not graphies:
            return Absent()
        if nom in graphies:
            return Reconnu(nom)
        if len(graphies) == 1:
            return Reconnu(graphies[0])
        return Ambigu(graphies)
```

- [ ] **Étape 8 : lancer la suite entière**

Run : `.venv/bin/python -m pytest`
Attendu : SUCCÈS, aucun test existant touché.

- [ ] **Étape 9 : analyse statique puis commit**

```bash
.venv/bin/ruff check . --exclude .claude && .venv/bin/mypy
git add stormshield_utilisateurs/rapprochement.py tests/test_rapprochement.py
git commit -m "feat: clé de rapprochement unique, index des graphies du boîtier, lecture de DN"
```

---

### Tâche 2 : le double rend des membres, sous forme de DN

**Fichiers :**
- Modifier : `stormshield_utilisateurs/boitier_memoire.py:18-35` (constructeur), `:105-109`
  (`ajouter_membre`), et ajout de `SUFFIXE_DN`, `dn_de` et `lister_membres`
- Modifier : `tests/test_boitier_memoire.py:18`
- Modifier : `tests/test_execution_ecriture.py:798` (assertion sur `boitier.membres`, dont la
  valeur devient un DN)

**Interfaces :**
- Consomme : rien (indépendante de T1).
- Produit : `boitier_memoire.SUFFIXE_DN` ; `boitier_memoire.dn_de(identifiant: str) -> str` ;
  `BoitierMemoire.lister_membres(groupe: str) -> list[str]` ;
  `BoitierMemoire(..., membres: Mapping[str, Iterable[str]] | None = None)` où les valeurs
  sont des **DN**.

**Cette tâche ne touche pas `boitier.py`.** L'ajout de `lister_membres` au `Protocol` est en
T3, avec l'implémentation de `BoitierSDK` : le faire ici laisserait `BoitierSDK` sans cette
méthode et **`mypy` échouerait** (`presentation.py:805` et `tests/test_boitier_sdk.py:31`),
alors qu'aucune tâche ne se clôt sans `mypy` vert. Une méthode de plus sur le double, elle, ne
gêne aucun `Protocol` : la conformité est structurelle et ne demande pas l'égalité.

Le double doit pouvoir mettre le code en défaut, sans quoi il ne prouve rien : il rend des DN
et jamais des identifiants, et il se construit avec des comptes à casse arbitraire — **deux
graphies d'un même compte comprises**, `Jean.Dupont` et `jean.dupont` — et des membres qui ne
désignent aucun compte qu'il connaît.

Le double reste **strict sur la casse** : `creer_utilisateur("jean.dupont")` réussit même si
`Jean.Dupont` existe, et `ajouter_membre` sur un groupe dont la graphie exacte est inconnue
lève `ErreurCommande`. C'est délibéré : la sensibilité à la casse du boîtier réel n'est pas
tranchée (spec, points 3 et 4), et un double indulgent masquerait exactement les fautes que
la v2 doit éviter.

- [ ] **Étape 1 : écrire les tests du double**

À ajouter à `tests/test_boitier_memoire.py` :

```python
def test_les_membres_sont_rendus_sous_forme_de_dn() -> None:
    """Un code qui comparerait un identifiant à un membre échouerait sur chaque test au
    lieu d'en passer quelques-uns."""
    boitier = BoitierMemoire(utilisateurs=["dupont"], groupes=["compta"])
    boitier.ajouter_membre("compta", "dupont")
    assert boitier.lister_membres("compta") == [dn_de("dupont")]


def test_le_double_se_construit_avec_des_membres_deja_en_place() -> None:
    boitier = BoitierMemoire(
        utilisateurs=["Jean.Dupont"],
        groupes=["Compta"],
        membres={"Compta": [dn_de("Jean.Dupont"), "cn=sous-groupe,ou=groups,dc=local"]},
    )
    assert boitier.lister_membres("Compta") == [
        "uid=Jean.Dupont,ou=users,dc=interne,dc=local",
        "cn=sous-groupe,ou=groups,dc=local",
    ]


def test_le_double_porte_deux_comptes_que_seule_la_casse_distingue() -> None:
    """Exigence de la spec (« `BoitierMemoire`, qui doit grandir ») : un double qui ne
    peut pas mettre le code en défaut ne prouve rien. C'est ce montage-là qui rend le cas
    « compte ambigu » éprouvable de bout en bout (T4, étape 9)."""
    boitier = BoitierMemoire(utilisateurs=["Jean.Dupont", "jean.dupont"])
    assert boitier.lister_utilisateurs() == ["Jean.Dupont", "jean.dupont"]


def test_lister_les_membres_d_un_groupe_inconnu_est_refuse() -> None:
    """Le double est strict sur la graphie : la casse réelle du boîtier n'est pas
    tranchée, et un double indulgent masquerait la faute qu'on cherche."""
    boitier = BoitierMemoire(groupes=["Compta"])
    with pytest.raises(ErreurCommande):
        boitier.lister_membres("compta")


def test_un_groupe_sans_membre_rend_une_liste_vide() -> None:
    assert BoitierMemoire(groupes=["compta"]).lister_membres("compta") == []


def test_lister_les_membres_est_au_journal_des_appels() -> None:
    boitier = BoitierMemoire(groupes=["compta"])
    boitier.lister_membres("compta")
    assert ("lister_membres", "compta") in boitier.journal_appels
```

`import pytest` et `ErreurCommande` sont **déjà** dans les imports du fichier (lignes 3 et
5) : seul `dn_de` est à ajouter, sur la ligne d'import de `BoitierMemoire`. Corriger au
passage `tests/test_boitier_memoire.py:18` :
`assert boitier.membres["compta"] == [dn_de("dupont")]` — le double range désormais des DN,
le test observe le même comportement sous la forme que le boîtier réel rend.

- [ ] **Étape 2 : lancer, constater l'échec**

Run : `.venv/bin/python -m pytest tests/test_boitier_memoire.py -v`
Attendu : ÉCHEC — `ImportError: cannot import name 'dn_de'`.

- [ ] **Étape 3 : faire grandir le double**

Dans `stormshield_utilisateurs/boitier_memoire.py` :

```python
# Forme supposée du DN rendu par USER GROUP SHOW (spec v2, « Points non vérifiés »,
# point 1). Le double la reproduit telle quelle : c'est elle que le rapprochement doit
# savoir lire, et c'est elle qu'un boîtier réel démentira ou confirmera.
SUFFIXE_DN = "ou=users,dc=interne,dc=local"


def dn_de(identifiant: str) -> str:
    """Le DN sous lequel le double rend un compte qu'il connaît."""
    return f"uid={identifiant},{SUFFIXE_DN}"
```

Constructeur : ajouter le paramètre `membres: Mapping[str, Iterable[str]] | None = None`
après `groupes`, **et `Mapping` à la ligne d'import de `collections.abc`** (le module
n'importe aujourd'hui que `Callable, Iterable`), puis remplacer
`self.membres: dict[str, list[str]] = {}` par :

```python
        # Les valeurs sont des DN, jamais des identifiants : le double doit pouvoir
        # mettre en défaut un code qui confondrait les deux.
        self.membres: dict[str, list[str]] = {
            groupe: list(dns) for groupe, dns in (membres or {}).items()
        }
```

`ajouter_membre` : la dernière ligne devient
`self.membres.setdefault(groupe, []).append(dn_de(identifiant))`.

Nouvelle méthode :

```python
    def lister_membres(self, groupe: str) -> list[str]:
        """USER GROUP SHOW : les DN des membres. Graphie exacte exigée."""
        self._appel("lister_membres", groupe)
        if groupe not in self.groupes:
            raise ErreurCommande(200, f"groupe {groupe} inconnu")
        return list(self.membres.get(groupe, []))
```

Rien d'autre : `boitier.py` n'est **pas** touché par cette tâche (voir l'encadré en tête).

- [ ] **Étape 4 : lancer, constater le succès puis la casse ailleurs**

Run : `.venv/bin/python -m pytest`
Attendu : `tests/test_boitier_memoire.py` passe ; `tests/test_execution_ecriture.py` échoue
sur **une seule** assertion, `boitier.membres == {"compta": ["dupont"]}` (ligne 798).
`boitier.membres == {}` (ligne 435) **reste vraie** : ce montage n'ajoute aucun membre.

- [ ] **Étape 5 : corriger l'assertion rendue fausse**

`tests/test_execution_ecriture.py:798` :
`assert boitier.membres == {"compta": [dn_de("dupont")]}` — ajouter `dn_de` à la ligne
d'import de `BoitierMemoire`.
Ne rien changer d'autre : ce test observe un comportement qui n'a pas bougé — l'arrêt demandé
laisse le compte en cours aller jusqu'au bout, rattachements compris —, seule la forme sous
laquelle le double range ses membres a changé. Ce n'est donc pas un affaiblissement :
l'assertion reste aussi précise, sur la forme que le boîtier réel rend.

- [ ] **Étape 6 : lancer la suite entière**

Run : `.venv/bin/python -m pytest`
Attendu : SUCCÈS.

- [ ] **Étape 7 : analyse statique puis commit**

```bash
.venv/bin/ruff check . --exclude .claude && .venv/bin/mypy
git add stormshield_utilisateurs/boitier_memoire.py tests/
git commit -m "feat: le double range et rend ses membres de groupe sous forme de DN"
```

---

### Tâche 3 : le `Protocol` et l'adaptateur SDK savent demander les membres

**Fichiers :**
- Modifier : `stormshield_utilisateurs/boitier.py:65` (après `ajouter_membre`)
- Modifier : `stormshield_utilisateurs/boitier_sdk.py` (fonctions pures de commande et de
  lecture, puis `BoitierSDK.lister_membres`)
- Modifier : `tests/test_boitier_sdk.py` (ajouts, plus une trace des commandes envoyées sur
  `_ClientFactice`)

**Interfaces :**
- Consomme : `BoitierMemoire.lister_membres` (T2) — le `Protocol` n'a de sens que si ses deux
  implémentations le satisfont, et celle du double existe déjà.
- Produit : `Boitier.lister_membres(groupe: str) -> list[str]` (au `Protocol`) ;
  `commande_lister_membres(groupe: str) -> str` ;
  `lire_membres(jetons: Mapping[str, Any]) -> list[str]` ;
  `BoitierSDK.lister_membres(groupe: str) -> list[str]`.

**Le `Protocol` et l'implémentation SDK sont dans la même tâche, et c'est structurel** : dès
que `Boitier` porte `lister_membres`, `mypy` exige la méthode sur `BoitierSDK`
(`presentation.py:805`, `tests/test_boitier_sdk.py:31`). Les séparer laisserait une tâche
incapable de se clore. T3 est en revanche **indépendante de T4** (qui n'appelle pas cette
opération) et peut tourner en parallèle, dans un arbre de travail séparé ; **T5 la consomme**
et doit donc la suivre.

L'adaptateur est écrit contre la documentation et n'est prouvé par rien : il reste le plus
mince possible, et tout ce qui peut en sortir en sort — d'où deux fonctions pures testées
hors SDK.

- [ ] **Étape 1 : écrire les tests**

`_ClientFactice` ne garde aujourd'hui aucune trace de ce qu'on lui envoie (`send_command`
fait `del commande`) : sans cette trace, rien ne prouve que la commande partie est celle que
la fonction pure a composée. Lui ajouter la trace, seule modification d'un helper existant :

```python
        self.deconnexions = 0
        # Ce que l'adaptateur a réellement envoyé : sans cette trace, rien ne relie la
        # commande composée par la fonction pure à celle qui part sur le fil.
        self.commandes: list[str] = []

    def send_command(self, commande: str) -> Any:
        self.commandes.append(commande)
        if self.panne_a_l_envoi is not None:
```

(le `del commande` disparaît, la valeur étant désormais utilisée.)

Puis, à ajouter à `tests/test_boitier_sdk.py` — `_reponse_section(titre, cles)` prend une
**liste de chaînes `"cle=valeur"`**, et `_ClientFactice` reçoit sa réponse par le mot-clé
`reponse=`, son premier paramètre positionnel étant `panne_a_l_envoi` :

```python
def test_la_commande_de_lecture_des_membres_cite_le_groupe() -> None:
    """Même citation qu'à la création et qu'au rattachement : un groupe créé sous
    « compta bis » resterait sinon inadressable."""
    assert commande_lister_membres("compta bis") == 'USER GROUP SHOW group="compta bis"'


def test_les_membres_se_lisent_dans_les_champs_repetes() -> None:
    """La documentation donne une section [Group] et des champs member=, member_2=, …"""
    jetons = {
        "name": "compta",
        "member": "uid=dupont,ou=users,dc=interne,dc=local",
        "member_2": "uid=legrand,ou=users,dc=interne,dc=local",
    }
    assert lire_membres(jetons) == [
        "uid=dupont,ou=users,dc=interne,dc=local",
        "uid=legrand,ou=users,dc=interne,dc=local",
    ]


def test_les_membres_sont_rendus_dans_l_ordre_des_indices() -> None:
    """member_10 vient après member_2, et non entre member_1 et member_3."""
    jetons = {"member": "uid=a,dc=l", "member_10": "uid=j,dc=l", "member_2": "uid=b,dc=l"}
    assert lire_membres(jetons) == ["uid=a,dc=l", "uid=b,dc=l", "uid=j,dc=l"]


def test_une_section_sans_membre_rend_une_liste_vide() -> None:
    """Section vide ou refus : les deux se traitent comme « aucun membre connu ».

    Nommée « section » et non « groupe » : `tests/test_boitier_memoire.py` porte déjà un
    `test_un_groupe_sans_membre_rend_une_liste_vide`, et deux tests homonymes dans deux
    fichiers rendent un rapport `-v` illisible.
    """
    assert lire_membres({"name": "compta"}) == []


def test_les_champs_membres_se_lisent_quelle_que_soit_leur_casse() -> None:
    """Rien ne garantit que serverd étiquette dans la casse de la documentation."""
    assert lire_membres({"Member": "uid=dupont,dc=l"}) == ["uid=dupont,dc=l"]


def test_un_champ_qui_ressemble_a_member_sans_l_etre_est_ignore() -> None:
    assert lire_membres({"membership": "uid=dupont,dc=l", "member_x": "uid=x,dc=l"}) == []


def test_l_adaptateur_lit_les_membres_d_un_groupe() -> None:
    """Bout en bout, sans réseau : la commande composée part, et la réponse du SDK —
    analysée par le vrai `ConfigParser` — est relue en DN."""
    client = _ClientFactice(
        reponse=_reponse_section(
            "Group",
            ["name=compta", "member=uid=dupont,ou=users,dc=interne,dc=local"],
        )
    )
    assert _adaptateur(client).lister_membres("compta") == [
        "uid=dupont,ou=users,dc=interne,dc=local"
    ]
    assert client.commandes == ['USER GROUP SHOW group="compta"']
```

Ce dernier test a été exécuté tel quel contre les helpers du fichier : `ConfigParser` coupe
la ligne `member=uid=dupont,…` au **premier** `=`, la valeur reste le DN entier, et
`_adaptateur` n'envoie aucune commande à la connexion — `client.commandes` ne porte donc que
celle-ci.

Ajouter `commande_lister_membres` et `lire_membres` à la liste d'imports de `boitier_sdk`
en tête du fichier de test.

- [ ] **Étape 2 : lancer, constater l'échec**

Run : `.venv/bin/python -m pytest tests/test_boitier_sdk.py -v`
Attendu : ÉCHEC — `ImportError: cannot import name 'commande_lister_membres'`.

- [ ] **Étape 3 : écrire la commande, la lecture et la méthode**

```python
# Champs répétés d'une section [Group] : `member`, `member_2`, `member_3`, … La forme
# exacte n'est pas prouvée (spec v2, « Points non vérifiés », point 1) ; un champ qui ne
# répond pas à ce motif n'est pas un membre et n'est pas lu.
_MOTIF_MEMBRE = re.compile(r"^member(?:_(\d+))?$", re.IGNORECASE)


def commande_lister_membres(groupe: str) -> str:
    """Le groupe est cité comme partout ailleurs, et l'identité transmise est celle que
    `USER GROUP LIST` a rendue, verbatim."""
    return f"USER GROUP SHOW group={_entre_guillemets(groupe)}"


def lire_membres(jetons: Mapping[str, Any]) -> list[str]:
    """Les DN des membres, dans l'ordre des indices. Section sans membre : liste vide."""
    trouves: list[tuple[int, str]] = []
    for nom, valeur in jetons.items():
        correspondance = _MOTIF_MEMBRE.match(str(nom))
        if correspondance is None or not str(valeur).strip():
            continue
        indice = int(correspondance.group(1) or 1)
        trouves.append((indice, str(valeur).strip()))
    return [dn for _, dn in sorted(trouves)]
```

Et sur `BoitierSDK` :

```python
    def lister_membres(self, groupe: str) -> list[str]:
        reponse = self._envoyer(commande_lister_membres(groupe))
        return lire_membres(_section_unique(reponse))
```

`ErreurCommande` n'est **pas** absorbée ici : un refus est signalé et traité par l'appelant
(voir T5), qui le journalise et poursuit. L'absorber dans l'adaptateur rendrait un refus réel
indiscernable d'un groupe vide.

Puis, **une fois la méthode écrite et pas avant**, ajouter l'opération au `Protocol`, dans
`stormshield_utilisateurs/boitier.py`, après `ajouter_membre` :

```python
    def lister_membres(self, groupe: str) -> list[str]:
        """USER GROUP SHOW group=<identité rendue par USER GROUP LIST> : les DN des
        membres. Lecture seule, et la seule commande que la v2 ajoute au dialogue."""
        ...
```

L'ordre compte : entre les deux gestes, `mypy` est rouge (`BoitierSDK` ne satisferait plus
`Boitier`). Les enchaîner dans la même étape est ce qui rend la tâche closable.

- [ ] **Étape 4 : lancer, constater le succès**

Run : `.venv/bin/python -m pytest tests/test_boitier_sdk.py -v`
Attendu : SUCCÈS.

- [ ] **Étape 5 : suite entière, analyse statique, commit**

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check . --exclude .claude && .venv/bin/mypy
git add stormshield_utilisateurs/boitier.py stormshield_utilisateurs/boitier_sdk.py tests/test_boitier_sdk.py
git commit -m "feat: USER GROUP SHOW au Protocol et dans l'adaptateur SDK, membres lus en champs répétés"
```

---

### Tâche 4 : le modèle et la décision

**Fichiers :**
- Modifier : `stormshield_utilisateurs/modele.py:54-83` (`EtatBoitier`, `Plan`, ajouts)
- Réécrire : `stormshield_utilisateurs/plan.py` (entier)
- Modifier : `stormshield_utilisateurs/execution.py` (`lire_etat`, `lire_comptes_et_groupes`,
  `executer`, `_Refuses`, `_replanifier`, `_creer_comptes` → boucle unique sur les travaux)
- Modifier : `stormshield_utilisateurs/presentation.py:569-584` et `:591-630` (rendu par
  compte et orphelins comptés, dans leur forme définitive ; T6 ajoute les lignes restantes)
- Réécrire : `tests/test_plan.py`
- Modifier : `tests/test_modele.py`, `tests/test_execution_ecriture.py`,
  `tests/test_execution_lecture.py`, `tests/test_presentation.py` (adaptation aux nouveaux
  champs — l'inventaire complet des tests rendus faux est à l'étape 8)

**Interfaces :**
- Consomme : `rapprochement.cle`, `IndexBoitier`, `Reconnu`, `Absent`, `Ambigu`,
  `uid_du_dn` (T1). **Rien de T3** : aucune lecture de membres ici, donc T4 et T3 peuvent
  tourner en parallèle.
- Produit : `modele.EtatBoitier(domaine, plancher, comptes: IndexBoitier,
  groupes: IndexBoitier, membres_par_groupe: Mapping[str, tuple[str, ...]])` ;
  `modele.TravailCompte(utilisateur, identifiant_cible, a_creer, adhesions)` ;
  `modele.GroupeAmbigu(nom_fichier, graphies)` ; `modele.CompteAmbigu(identifiant_fichier,
  graphies)` ; `modele.Plan(travaux, groupes_a_creer, nombre_orphelins,
  nombre_membres_non_rattaches, groupes_ambigus, comptes_ambigus, domaine)` avec
  `.creations`, `.nombre_adhesions`, `.nombre_operations()` ;
  `plan.groupes_cites(utilisateurs) -> tuple[str, ...]` ;
  `plan.groupes_a_interroger(cites, groupes: IndexBoitier) -> tuple[str, ...]` ;
  `plan.construire(utilisateurs, etat, rejets=()) -> Plan`.

**État intermédiaire assumé** : à la fin de cette tâche, `execution.lire_etat` ne lit encore
aucun membre (`membres_par_groupe` vide) et l'outil réémet donc les `USER GROUP ADDUSER` des
adhésions déjà en place. L'idempotence stricte arrive en T5, qui branche la lecture. Toute la
décision, elle, est **entièrement** éprouvée ici, sur des `EtatBoitier` construits à la main.

- [ ] **Étape 1 : écrire les tests de la décision**

`tests/test_plan.py`, réécrit intégralement :

```python
"""La décision, entièrement hors ligne : casse, adhésions, compteurs."""

from fabriques import utilisateur

from stormshield_utilisateurs.modele import (
    CompteAmbigu,
    EtatBoitier,
    GroupeACreer,
    GroupeAmbigu,
    PlancherPolitique,
    Rejet,
)
from stormshield_utilisateurs.plan import construire, groupes_a_interroger, groupes_cites
from stormshield_utilisateurs.rapprochement import IndexBoitier

PLANCHER = PlancherPolitique(longueur_min=12, nombre_classes_min=3, entropie_min=0)


def _etat(
    comptes: tuple[str, ...] = (),
    groupes: tuple[str, ...] = (),
    membres: dict[str, tuple[str, ...]] | None = None,
) -> EtatBoitier:
    return EtatBoitier(
        domaine="interne.local",
        plancher=PLANCHER,
        comptes=IndexBoitier.depuis(comptes),
        groupes=IndexBoitier.depuis(groupes),
        membres_par_groupe=membres or {},
    )


def _dn(identifiant: str) -> str:
    return f"uid={identifiant},ou=users,dc=interne,dc=local"


# --- casse des comptes -------------------------------------------------------------

def test_un_compte_du_boitier_est_reconnu_malgre_la_casse() -> None:
    plan = construire([utilisateur("jean.dupont")], _etat(comptes=("Jean.Dupont",)))
    (travail,) = plan.travaux
    assert travail.a_creer is False


def test_toutes_les_operations_visent_l_orthographe_du_boitier() -> None:
    """L'outil ne demande jamais au boîtier de retrouver un compte sous une graphie
    qu'il n'a pas lui-même rendue."""
    plan = construire(
        [utilisateur("jean.dupont", "compta")],
        _etat(comptes=("Jean.Dupont",), groupes=("compta",), membres={"compta": ()}),
    )
    (travail,) = plan.travaux
    assert travail.identifiant_cible == "Jean.Dupont"
    assert travail.adhesions == ("compta",)


def test_un_compte_absent_est_cree_sous_l_identifiant_du_fichier() -> None:
    plan = construire([utilisateur("dupont")], _etat())
    (travail,) = plan.travaux
    assert (travail.a_creer, travail.identifiant_cible) == (True, "dupont")


def test_un_compte_a_deux_graphies_est_signale_et_rien_ne_lui_est_fait() -> None:
    """L'ordre dans lequel le boîtier rend sa liste n'est garanti par rien : trancher sur
    la première graphie ferait écrire sur un compte différent d'une fois sur l'autre. Pas
    de travail, donc ni création, ni adhésion, ni mot de passe — et le lot continue."""
    plan = construire(
        [utilisateur("jean.dupont", "compta"), utilisateur("legrand", "compta", ligne=3)],
        _etat(
            comptes=("Jean.Dupont", "JEAN.DUPONT", "legrand"),
            groupes=("compta",),
            membres={"compta": ()},
        ),
    )
    assert plan.comptes_ambigus == (
        CompteAmbigu("jean.dupont", ("Jean.Dupont", "JEAN.DUPONT")),
    )
    assert [travail.identifiant_cible for travail in plan.travaux] == ["legrand"]


def test_une_correspondance_exacte_l_emporte_sur_l_ambiguite_du_compte() -> None:
    """Même règle que pour les groupes : l'opérateur a écrit ce nom-là, il existe tel
    quel sur le boîtier."""
    plan = construire(
        [utilisateur("jean.dupont")], _etat(comptes=("Jean.Dupont", "jean.dupont"))
    )
    assert plan.comptes_ambigus == ()
    (travail,) = plan.travaux
    assert (travail.a_creer, travail.identifiant_cible) == (False, "jean.dupont")


def test_un_groupe_cite_par_le_seul_compte_ambigu_n_est_pas_cree() -> None:
    """Ce compte ne reçoit aucune adhésion : le groupe neuf n'aurait aucun membre."""
    plan = construire(
        [utilisateur("jean.dupont", "neuf")],
        _etat(comptes=("Jean.Dupont", "JEAN.DUPONT")),
    )
    assert plan.groupes_a_creer == ()


# --- adhésions ---------------------------------------------------------------------

def test_les_adhesions_manquantes_d_un_compte_present_sont_ajoutees() -> None:
    plan = construire(
        [utilisateur("legrand", "rh")],
        _etat(comptes=("legrand",), groupes=("rh",), membres={"rh": ()}),
    )
    assert plan.travaux[0].adhesions == ("rh",)


def test_une_adhesion_deja_portee_par_le_boitier_n_est_pas_replanifiee() -> None:
    """Le cœur de l'idempotence, dans la seule fonction pure qui la décide."""
    plan = construire(
        [utilisateur("legrand", "rh")],
        _etat(comptes=("legrand",), groupes=("rh",), membres={"rh": (_dn("legrand"),)}),
    )
    assert plan.travaux[0].adhesions == ()
    assert plan.nombre_operations() == 0


def test_l_adhesion_existante_est_reconnue_malgre_la_casse_du_dn() -> None:
    plan = construire(
        [utilisateur("jean.dupont", "rh")],
        _etat(
            comptes=("Jean.Dupont",),
            groupes=("rh",),
            membres={"rh": (_dn("Jean.Dupont"),)},
        ),
    )
    assert plan.travaux[0].adhesions == ()


def test_une_colonne_groupes_vide_n_ajoute_aucune_adhesion() -> None:
    """La colonne vide ne dit pas « aucun groupe » mais « je ne me prononce pas »."""
    plan = construire([utilisateur("legrand")], _etat(comptes=("legrand",)))
    assert plan.travaux[0].adhesions == ()
    assert plan.groupes_a_creer == ()


def test_un_compte_a_creer_recoit_aussi_ses_adhesions() -> None:
    plan = construire([utilisateur("dupont", "compta", "rh")], _etat(groupes=("compta",)))
    assert plan.travaux[0].adhesions == ("compta", "rh")


# --- casse et collisions de groupes ------------------------------------------------

def test_un_groupe_du_boitier_est_reconnu_malgre_la_casse_et_n_est_pas_recree() -> None:
    plan = construire(
        [utilisateur("dupont", "compta")], _etat(groupes=("Compta",), membres={"compta": ()})
    )
    assert plan.groupes_a_creer == ()
    assert plan.travaux[0].adhesions == ("Compta",)


def test_une_collision_de_casse_est_signalee_et_le_groupe_n_est_touche_pour_personne() -> None:
    """Un boîtier mal rangé ne doit pas priver les deux cents autres comptes du lot."""
    plan = construire(
        [utilisateur("dupont", "compta"), utilisateur("legrand", "rh", ligne=3)],
        _etat(groupes=("Compta", "COMPTA", "rh"), membres={"rh": ()}),
    )
    assert plan.groupes_ambigus == (GroupeAmbigu("compta", ("Compta", "COMPTA")),)
    assert plan.travaux[0].adhesions == ()
    assert plan.travaux[1].adhesions == ("rh",)
    assert plan.groupes_a_creer == ()


def test_une_correspondance_exacte_l_emporte_sur_la_collision() -> None:
    plan = construire(
        [utilisateur("dupont", "compta")],
        _etat(groupes=("Compta", "compta"), membres={"compta": ()}),
    )
    assert plan.groupes_ambigus == ()
    assert plan.travaux[0].adhesions == ("compta",)


# --- groupes à interroger ----------------------------------------------------------

def test_les_groupes_cites_se_calculent_avant_toute_connexion() -> None:
    assert groupes_cites(
        [utilisateur("dupont", "compta", "rh"), utilisateur("legrand", "Compta", ligne=3)]
    ) == ("compta", "rh")


def test_seuls_les_groupes_cites_et_presents_sont_interroges() -> None:
    """Un groupe qu'aucune ligne ne cite n'est pas lu ; un groupe cité mais absent n'a
    pas de membre ; un groupe ambigu ne sera touché pour personne.

    Les deux graphies du doublon sont `Doublon` et `DOUBLON` : aucune n'égale la graphie
    du fichier, sans quoi la correspondance exacte lèverait l'ambiguïté et ce groupe
    **serait** interrogé (cas éprouvé par le test suivant).
    """
    index = IndexBoitier.depuis(("Compta", "jamais.cite", "Doublon", "DOUBLON"))
    assert groupes_a_interroger(("compta", "neuf", "doublon"), index) == ("Compta",)


def test_un_groupe_ambigu_leve_par_une_correspondance_exacte_est_interroge() -> None:
    """La contrepartie du test précédent : `doublon` existe tel quel sur le boîtier, il
    n'y a rien à deviner, et lire ses membres évite un ADDUSER redondant."""
    index = IndexBoitier.depuis(("Doublon", "doublon"))
    assert groupes_a_interroger(("doublon",), index) == ("doublon",)


def test_une_ligne_a_colonne_vide_ne_cite_aucun_groupe() -> None:
    """Le majorant de la phase de lecture ne compte que ce que le fichier décrit ; les
    lignes rejetées, elles, n'arrivent pas jusqu'ici."""
    assert groupes_cites([utilisateur("legrand"), utilisateur("dupont", "rh", ligne=3)]) == (
        "rh",
    )


# --- membres non rattachés ---------------------------------------------------------

def test_un_membre_dont_le_dn_ne_se_lit_pas_est_compte_et_ne_provoque_rien() -> None:
    """Le canari de l'hypothèse sur la forme du DN : un entier, jamais une liste."""
    plan = construire(
        [utilisateur("dupont", "compta")],
        _etat(
            comptes=("dupont",),
            groupes=("compta",),
            membres={"compta": ("cn=sous-groupe,ou=groups,dc=local", _dn("dupont"))},
        ),
    )
    assert plan.nombre_membres_non_rattaches == 1
    assert plan.travaux[0].adhesions == ()


def test_un_membre_legitime_absent_du_fichier_n_est_pas_compte() -> None:
    """Un groupe peuplé contient forcément des gens que le CSV du jour ne cite pas : les
    compter noierait le signal dans le bruit qu'il doit détecter. Le point de comparaison
    est la liste des comptes du boîtier, jamais celle du fichier."""
    plan = construire(
        [utilisateur("dupont", "compta")],
        _etat(
            comptes=("dupont", "martin"),
            groupes=("compta",),
            membres={"compta": (_dn("martin"),)},
        ),
    )
    assert plan.nombre_membres_non_rattaches == 0


def test_un_dn_designant_un_compte_inconnu_du_boitier_est_compte() -> None:
    """Le boîtier a rendu un membre que sa propre liste de comptes ne porte pas : l'outil
    ne sait pas le relier, et c'est précisément ce que le compteur dit."""
    plan = construire(
        [utilisateur("dupont", "compta")],
        _etat(comptes=("dupont",), groupes=("compta",), membres={"compta": (_dn("martin"),)}),
    )
    assert plan.nombre_membres_non_rattaches == 1


def test_un_membre_non_rattache_ne_supprime_aucune_adhesion_planifiee() -> None:
    """Spec : un membre que l'outil ne sait relier à aucun compte **du boîtier** ne
    déclenche « aucune action ». Retirer du plan l'adhésion du compte homonyme que le
    fichier demande de créer en serait une, et la plus coûteuse : ce compte naîtrait sans
    le groupe que le CSV lui donne, sur la foi d'un DN qu'on n'a pas su lire."""
    plan = construire(
        [utilisateur("dupont", "compta")],
        _etat(groupes=("compta",), membres={"compta": (_dn("dupont"),)}),
    )
    assert plan.nombre_membres_non_rattaches == 1
    assert plan.travaux[0].a_creer is True
    assert plan.travaux[0].adhesions == ("compta",)


def test_aucun_membre_non_rattache_sur_un_boitier_sain() -> None:
    """Zéro, quel que soit le contenu du fichier : `legrand` n'y figure pas, mais le
    boîtier le connaît."""
    plan = construire(
        [utilisateur("dupont", "compta")],
        _etat(
            comptes=("dupont", "legrand"),
            groupes=("compta",),
            membres={"compta": (_dn("dupont"), _dn("legrand"))},
        ),
    )
    assert plan.nombre_membres_non_rattaches == 0


# --- orphelins ---------------------------------------------------------------------

def test_les_orphelins_sont_comptes_jamais_listes() -> None:
    plan = construire([utilisateur("dupont")], _etat(comptes=("dupont", "martin", "paul")))
    assert plan.nombre_orphelins == 2


def test_un_compte_dont_la_ligne_a_ete_rejetee_n_est_pas_orphelin() -> None:
    """Il est bel et bien dans le fichier : l'annoncer orphelin dirait à l'opérateur le
    contraire de ce qu'il doit corriger."""
    plan = construire(
        [],
        _etat(comptes=("Martin",)),
        rejets=[Rejet(ligne=2, identifiant="martin", motif="nom vide")],
    )
    assert plan.nombre_orphelins == 0


def test_un_orphelin_est_reconnu_malgre_la_casse() -> None:
    plan = construire([utilisateur("jean.dupont")], _etat(comptes=("Jean.Dupont",)))
    assert plan.nombre_orphelins == 0


# --- groupes à créer ---------------------------------------------------------------

def test_les_groupes_a_creer_se_calculent_sur_toutes_les_adhesions() -> None:
    """Y compris celles d'un compte déjà présent : sans quoi son ADDUSER échouerait sur
    un groupe inexistant."""
    plan = construire([utilisateur("legrand", "neuf")], _etat(comptes=("legrand",)))
    assert plan.groupes_a_creer == (GroupeACreer(nom="neuf", nombre_membres=1),)


def test_un_groupe_reference_par_une_seule_ligne_rejetee_n_est_pas_cree() -> None:
    plan = construire([], _etat(), rejets=[Rejet(ligne=2, identifiant="x", motif="nom vide")])
    assert plan.groupes_a_creer == ()


def test_les_groupes_a_creer_sont_tries_et_comptent_leurs_membres() -> None:
    plan = construire(
        [utilisateur("dupont", "rh", "compta"), utilisateur("legrand", "rh", ligne=3)],
        _etat(),
    )
    assert plan.groupes_a_creer == (
        GroupeACreer(nom="compta", nombre_membres=1),
        GroupeACreer(nom="rh", nombre_membres=2),
    )


def test_le_domaine_lu_sur_le_boitier_est_porte_par_le_plan() -> None:
    assert construire([], _etat()).domaine == "interne.local"


def test_construire_n_ecrit_rien_sur_l_etat_recu() -> None:
    etat = _etat(comptes=("dupont",), groupes=("compta",), membres={"compta": ()})
    construire([utilisateur("dupont", "compta")], etat)
    assert etat.comptes.graphies == ("dupont",)
    assert etat.membres_par_groupe == {"compta": ()}
```

- [ ] **Étape 2 : lancer, constater l'échec**

Run : `.venv/bin/python -m pytest tests/test_plan.py -v`
Attendu : ÉCHEC — `ImportError: cannot import name 'groupes_cites'`.

- [ ] **Étape 3 : réécrire le modèle**

Dans `stormshield_utilisateurs/modele.py`, remplacer `EtatBoitier` et `Plan`, ajouter
`TravailCompte`, `GroupeAmbigu` et `CompteAmbigu` (et importer `Mapping` de
`collections.abc` ainsi que `IndexBoitier` de `rapprochement` — `modele` n'importait
jusqu'ici que `dataclass, field` et `Enum, auto`, et `rapprochement` n'importe rien du
paquet, donc aucun cycle).

`EtatBoitier` reste `frozen=True` pour l'immuabilité, mais **cesse d'être hachable** : elle
porte désormais une `Mapping` et un `IndexBoitier` qui en porte une. Aucun site ne la hache
aujourd'hui ; ne pas en faire une clé de dictionnaire ni un membre d'ensemble.

```python
@dataclass(frozen=True)
class EtatBoitier:
    """Ce que la phase de lecture rapporte du boîtier. Lecture seule.

    `comptes` et `groupes` portent les graphies rendues par le boîtier, rangées sous la
    clé de rapprochement : c'est sous ces graphies-là que l'outil s'adressera à lui.

    `membres_par_groupe` ne couvre que les groupes **cités par le fichier et reconnus**
    sur le boîtier, rangés sous leur clé. Un groupe absent de cette table n'a pas été
    lu : aucune adhésion n'y est réputée exister.
    """

    domaine: str
    plancher: PlancherPolitique
    comptes: IndexBoitier
    groupes: IndexBoitier
    membres_par_groupe: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class GroupeAmbigu:
    """Un groupe du fichier que deux graphies vivantes du boîtier revendiquent.

    Signalé, jamais tranché : l'outil ne sait pas auquel des deux ajouter, il n'en crée
    aucun — ils existent — et ne touche ce groupe pour aucun compte. Le lot continue.
    """

    nom_fichier: str
    graphies: tuple[str, ...]


@dataclass(frozen=True)
class CompteAmbigu:
    """Un compte du fichier que deux graphies vivantes du boîtier revendiquent.

    Même règle que pour un groupe, et pour la même raison : l'ordre dans lequel le
    boîtier rend sa liste n'est garanti par rien, et trancher sur la première graphie
    ferait écrire sur un compte différent d'une exécution à l'autre. Signalé, jamais
    tranché : aucun travail n'est produit pour lui — ni création, ni adhésion, ni mot de
    passe — et le lot continue.
    """

    identifiant_fichier: str
    graphies: tuple[str, ...]


@dataclass(frozen=True)
class TravailCompte:
    """Tout ce que l'outil va faire à un compte, en un seul objet.

    Un seul objet et non deux listes parallèles : la boucle d'écriture reste unique, et
    le point d'arrêt reste où la v1 l'a posé, entre deux comptes.

    `identifiant_cible` est la graphie sous laquelle le boîtier sera adressé : celle
    qu'il a rendue pour un compte déjà présent, celle du fichier pour un compte à créer
    — la seule disponible alors.
    """

    utilisateur: Utilisateur
    identifiant_cible: str
    a_creer: bool
    adhesions: tuple[str, ...]


@dataclass(frozen=True)
class Plan:
    """Orphelins et membres non rattachés sont des **nombres** : aucun nom ne survit à
    la construction du plan, donc rien ne peut réimprimer une liste de 500 comptes
    au-dessus de ce sur quoi l'opérateur doit se prononcer."""

    travaux: tuple[TravailCompte, ...]
    groupes_a_creer: tuple[GroupeACreer, ...]
    nombre_orphelins: int
    nombre_membres_non_rattaches: int
    groupes_ambigus: tuple[GroupeAmbigu, ...]
    comptes_ambigus: tuple[CompteAmbigu, ...]
    domaine: str

    @property
    def creations(self) -> tuple[TravailCompte, ...]:
        return tuple(travail for travail in self.travaux if travail.a_creer)

    @property
    def nombre_adhesions(self) -> int:
        return sum(len(travail.adhesions) for travail in self.travaux)

    def nombre_operations(self) -> int:
        """Un USER GROUP CREATE par groupe neuf ; pour un compte à créer un USER CREATE
        et un USER PASSWORD ; un USER GROUP ADDUSER par adhésion."""
        return len(self.groupes_a_creer) + 2 * len(self.creations) + self.nombre_adhesions
```

- [ ] **Étape 4 : réécrire la décision**

`stormshield_utilisateurs/plan.py`, entier :

```python
"""Décision : état lu + lignes valides -> Plan. Pur, n'écrit jamais sur le boîtier."""

from collections import Counter
from collections.abc import Sequence

from stormshield_utilisateurs.modele import (
    CompteAmbigu,
    EtatBoitier,
    GroupeACreer,
    GroupeAmbigu,
    Plan,
    Rejet,
    TravailCompte,
    Utilisateur,
)
from stormshield_utilisateurs.rapprochement import (
    Absent,
    Ambigu,
    IndexBoitier,
    Reconnu,
    cle,
    uid_du_dn,
)


def groupes_cites(utilisateurs: Sequence[Utilisateur]) -> tuple[str, ...]:
    """Les groupes que le fichier nomme, une graphie par clé, triés.

    Calculée hors ligne, avant toute connexion : c'est elle qui donne le majorant de la
    phase de lecture. Seules les lignes valides à colonne non vide comptent — une ligne
    rejetée ne produit aucune adhésion, une colonne vide ne se prononce pas.
    """
    retenus: dict[str, str] = {}
    for utilisateur in utilisateurs:
        for groupe in utilisateur.groupes:
            retenus.setdefault(cle(groupe), groupe)
    return tuple(retenus[clef] for clef in sorted(retenus))


def groupes_a_interroger(cites: Sequence[str], groupes: IndexBoitier) -> tuple[str, ...]:
    """Les identités à passer à `lister_membres`, telles que `USER GROUP LIST` les a
    rendues, verbatim.

    Un groupe cité mais absent du boîtier n'est pas lu : il est à créer, il n'a pas de
    membre. Un groupe ambigu ne l'est pas non plus : il ne sera touché pour aucun
    compte, le lire n'apprendrait rien.
    """
    identites: list[str] = []
    for nom in cites:
        match groupes.resoudre(nom):
            case Reconnu(orthographe):
                identites.append(orthographe)
            case Absent() | Ambigu():
                continue
    return tuple(identites)


def _adhesions_existantes(etat: EtatBoitier) -> tuple[dict[str, frozenset[str]], int]:
    """Par clé de groupe, les clés de comptes déjà membres ; et le nombre de membres que
    l'outil n'a su relier à **aucun compte du boîtier**.

    Le point de comparaison est la liste que `USER LIST` a rendue, jamais le fichier : un
    groupe peuplé contient forcément des gens légitimes qu'un CSV du jour ne cite pas, et
    les compter noierait le signal dans le bruit qu'il doit détecter. Sur un boîtier sain
    ce nombre vaut donc zéro, quel que soit le contenu du fichier, et une forme de DN
    inattendue le fait bondir d'un coup.

    Il n'intervient jamais : ni arrêt, ni refus, ni écriture en moins.
    """
    par_groupe: dict[str, frozenset[str]] = {}
    non_rattaches = 0
    for cle_groupe, membres in etat.membres_par_groupe.items():
        deja: set[str] = set()
        for dn in membres:
            uid = uid_du_dn(dn)
            if uid is None or cle(uid) not in etat.comptes.cles:
                # Aucun compte du boîtier derrière ce membre : « aucune action », dit la
                # spec — et retenir son uid en serait une, la plus coûteuse : elle
                # supprimerait du plan l'adhésion d'un compte homonyme à créer. Compté,
                # rien de plus.
                non_rattaches += 1
                continue
            deja.add(cle(uid))
        par_groupe[cle_groupe] = frozenset(deja)
    return par_groupe, non_rattaches


def construire(
    utilisateurs: Sequence[Utilisateur],
    etat: EtatBoitier,
    rejets: Sequence[Rejet] = (),
) -> Plan:
    """L'outil crée des comptes, crée des groupes, ajoute des adhésions — et n'enlève
    jamais rien.

    Les rejets comptent dans « ce qui est dans le fichier » : un compte présent sur le
    boîtier dont la ligne a été rejetée y est bel et bien, et le compter orphelin dirait
    à l'opérateur le contraire de ce qu'il doit corriger. Ils ne comptent nulle part
    ailleurs — ni travail, ni adhésion, ni membre d'un groupe à créer. Un compte signalé
    ambigu est dans le même cas : pas de travail, mais pas orphelin non plus.
    """
    cibles: dict[str, str] = {}
    cles_a_creer: set[str] = set()
    ambigus: list[GroupeAmbigu] = []
    for nom in groupes_cites(utilisateurs):
        match etat.groupes.resoudre(nom):
            case Reconnu(orthographe):
                cibles[cle(nom)] = orthographe
            case Absent():
                # Aucune graphie côté boîtier : celle du fichier est la seule dont on
                # dispose, et c'est sous elle que le groupe sera créé puis adressé.
                cibles[cle(nom)] = nom
                cles_a_creer.add(cle(nom))
            case Ambigu(graphies):
                ambigus.append(GroupeAmbigu(nom, graphies))

    cles_du_fichier = frozenset(cle(u.identifiant) for u in utilisateurs)
    deja_membres, non_rattaches = _adhesions_existantes(etat)

    travaux: list[TravailCompte] = []
    comptes_ambigus: list[CompteAmbigu] = []
    for utilisateur in utilisateurs:
        match etat.comptes.resoudre(utilisateur.identifiant):
            case Reconnu(orthographe):
                cible, a_creer = orthographe, False
            case Absent():
                cible, a_creer = utilisateur.identifiant, True
            case Ambigu(graphies):
                # Deux comptes que la clé confond, et aucun égal à la graphie du
                # fichier : l'ordre de la liste rendue par le boîtier n'est garanti par
                # rien, et trancher sur la première ferait écrire sur un compte différent
                # d'une exécution à l'autre. Aucun travail : rien ne l'atteindra.
                comptes_ambigus.append(CompteAmbigu(utilisateur.identifiant, graphies))
                continue
        travaux.append(
            TravailCompte(
                utilisateur=utilisateur,
                identifiant_cible=cible,
                a_creer=a_creer,
                adhesions=_adhesions(utilisateur, cibles, deja_membres),
            )
        )

    compte_des_membres: Counter[str] = Counter()
    for travail in travaux:
        compte_des_membres.update(travail.adhesions)
    groupes_a_creer = tuple(
        GroupeACreer(nom=nom, nombre_membres=compte_des_membres[nom])
        for nom in sorted(compte_des_membres)
        if cle(nom) in cles_a_creer
    )

    dans_le_fichier = set(cles_du_fichier)
    dans_le_fichier.update(cle(rejet.identifiant) for rejet in rejets)
    nombre_orphelins = sum(
        1 for nom in etat.comptes.graphies if cle(nom) not in dans_le_fichier
    )

    return Plan(
        travaux=tuple(travaux),
        groupes_a_creer=groupes_a_creer,
        nombre_orphelins=nombre_orphelins,
        nombre_membres_non_rattaches=non_rattaches,
        groupes_ambigus=tuple(ambigus),
        comptes_ambigus=tuple(comptes_ambigus),
        domaine=etat.domaine,
    )


def _adhesions(
    utilisateur: Utilisateur,
    cibles: dict[str, str],
    deja_membres: dict[str, frozenset[str]],
) -> tuple[str, ...]:
    """Les groupes que la ligne nomme, moins ceux que le boîtier porte déjà.

    Colonne vide : la boucle ne tourne pas, aucune adhésion. Groupe ambigu : absent de
    `cibles`, donc ignoré pour ce compte comme pour tous les autres.
    """
    retenues: list[str] = []
    for groupe in utilisateur.groupes:
        cible = cibles.get(cle(groupe))
        if cible is None or cible in retenues:
            continue
        if cle(utilisateur.identifiant) in deja_membres.get(cle(groupe), frozenset()):
            continue
        retenues.append(cible)
    return tuple(retenues)
```

- [ ] **Étape 5 : lancer les tests de décision**

Run : `.venv/bin/python -m pytest tests/test_plan.py tests/test_rapprochement.py -v`
Attendu : SUCCÈS.

- [ ] **Étape 6 : adapter `execution.py` à la nouvelle forme**

Quatre changements, sans toucher encore à la lecture des membres. `execution.py` importe
désormais `IndexBoitier` de `rapprochement` et `TravailCompte` de `modele`.

1. `lire_etat` construit des index et un inventaire d'adhésions vide :

```python
    return EtatBoitier(
        domaine=annuaires[0],
        plancher=plancher,
        comptes=IndexBoitier.depuis(boitier.lister_utilisateurs()),
        groupes=IndexBoitier.depuis(boitier.lister_groupes()),
    )
```

2. `lire_comptes_et_groupes` rend deux `IndexBoitier` et non plus deux `frozenset` — sans quoi
   `_replanifier` ne saurait plus reconstruire l'état, et un `frozenset` détruirait l'ordre des
   graphies dont dépend la résolution d'une collision de casse :

```python
def lire_comptes_et_groupes(boitier: Boitier) -> tuple[IndexBoitier, IndexBoitier]:
    return (
        IndexBoitier.depuis(boitier.lister_utilisateurs()),
        IndexBoitier.depuis(boitier.lister_groupes()),
    )
```

   (cette fonction disparaît en T5 au profit de `relire_inventaire` ; elle doit rester juste
   en attendant, et son test avec elle — voir étape 8.)

3. `rapport.comptes_prevus = len(plan_courant.creations)` remplace
   `len(plan_courant.comptes_a_creer)`.

4. `_creer_comptes` devient `_traiter_comptes` : **une seule boucle**, sur les travaux, et le
   mot de passe n'est atteignable que depuis la branche de création. Son unique site d'appel,
   dans `_appliquer` (l. 389), suit le renommage — les arguments ne changent pas.

```python
def _traiter_comptes(
    boitier: Boitier, plan_courant: Plan, politique: PolitiqueMotDePasse,
    rapport: Rapport, compteur: _Compteur, emettre: Emetteur,
    patience: Patience, generer_mot_de_passe: Callable[[PolitiqueMotDePasse], str],
    refuses: _Refuses, arret_demande: ArretDemande,
) -> None:
    """Une seule boucle sur les comptes : le point d'arrêt reste entre deux d'entre eux,
    et le compte entamé va jusqu'à son terme, ses adhésions comprises."""
    for travail in plan_courant.travaux:
        _verifier_arret(arret_demande)
        if travail.a_creer and not _creer_le_compte(
            boitier, travail, plan_courant.domaine, politique, rapport, compteur,
            emettre, patience, generer_mot_de_passe, refuses,
        ):
            continue
        _ajouter_les_adhesions(boitier, travail, rapport, compteur, emettre, refuses)


def _creer_le_compte(
    boitier: Boitier, travail: TravailCompte, domaine: str,
    politique: PolitiqueMotDePasse, rapport: Rapport, compteur: _Compteur,
    emettre: Emetteur, patience: Patience,
    generer_mot_de_passe: Callable[[PolitiqueMotDePasse], str], refuses: _Refuses,
) -> bool:
    """Crée le compte puis pose son mot de passe. Rend faux si la création a échoué.

    **Seul chemin d'appel de `_definir_mot_de_passe` du module.** Un compte déjà présent
    ne traverse jamais cette fonction : c'est ainsi, et non par une règle qu'on se
    rappelle, que son mot de passe reste hors d'atteinte. Le secret n'est généré qu'ici,
    après une création réussie : un compte qui n'est pas créé n'en consomme aucun.
    """
    try:
        boitier.creer_utilisateur(
            travail.identifiant_cible, travail.utilisateur.nom,
            travail.utilisateur.prenom, domaine,
        )
    except ErreurCommande as erreur:
        refuses.comptes.add(travail.identifiant_cible)
        rapport.echecs.append(Echec(travail.identifiant_cible, "USER CREATE", str(erreur)))
        emettre(Journal(f"{travail.identifiant_cible} : échec de création ({erreur})"))
        # Budget entier du compte : ni USER PASSWORD ni les ADDUSER n'auront lieu.
        compteur.avancer(2 + len(travail.adhesions))
        return False
    compteur.avancer()
    secret = generer_mot_de_passe(politique)
    # Inscrit dès la création : le CSV de sortie est la liste de reprise de l'opérateur,
    # et une coupure survenue après USER CREATE ne doit pas effacer un compte qui existe.
    rang = len(rapport.comptes_crees)
    rapport.comptes_crees.append(CompteCree(travail.identifiant_cible, ""))
    try:
        retenu = _definir_mot_de_passe(
            boitier, travail.identifiant_cible, secret, rapport, emettre, patience
        )
    except ErreurReseau:
        _signaler_interruption(
            rapport, emettre, travail.identifiant_cible, "USER PASSWORD",
            "coupure réseau après la création : compte créé sans mot de passe "
            "utilisable, à reprendre à la main",
        )
        emettre(CreationReussie(rapport.comptes_crees[rang]))
        raise
    compteur.avancer()
    compte = CompteCree(travail.identifiant_cible, retenu)
    rapport.comptes_crees[rang] = compte
    emettre(Journal(f"{travail.identifiant_cible} : créé"))
    emettre(CreationReussie(compte))
    return True


def _ajouter_les_adhesions(
    boitier: Boitier, travail: TravailCompte, rapport: Rapport,
    compteur: _Compteur, emettre: Emetteur, refuses: _Refuses,
) -> None:
    """Un ADDUSER refusé est signalé et le lot continue : une adhésion manquante ne rend
    pas un compte inutilisable, et aucun réessai dédié n'est prévu."""
    for rang, groupe in enumerate(travail.adhesions):
        try:
            boitier.ajouter_membre(groupe, travail.identifiant_cible)
        except ErreurCommande as erreur:
            # Mémorisé comme un refus de création : le plan reconstruit après une
            # reconnexion ne le rejoue pas, sans quoi le rapport porterait deux fois le
            # même échec.
            refuses.adhesions.add((travail.identifiant_cible, groupe))
            rapport.echecs.append(
                Echec(travail.identifiant_cible, "USER GROUP ADDUSER", str(erreur))
            )
            emettre(
                Journal(f"{travail.identifiant_cible} : non rattaché à {groupe} ({erreur})")
            )
        except ErreurReseau:
            # Contrairement à la v1, la relecture qui suit la reconnexion replanifiera
            # ces adhésions : elle relit les membres de chaque groupe cité.
            restants = ", ".join(travail.adhesions[rang:])
            _signaler_interruption(
                rapport, emettre, travail.identifiant_cible, "USER GROUP ADDUSER",
                f"coupure réseau pendant le rattachement : groupes non rattachés "
                f"({restants}), ils seront replanifiés après reconnexion",
            )
            raise
        compteur.avancer()
```

`_Refuses` gagne son troisième ensemble :

```python
    # (identifiant visé, groupe visé) : un refus d'adhésion ne se rejoue pas plus qu'un
    # refus de création.
    adhesions: set[tuple[str, str]] = field(default_factory=set)
```

`_replanifier` garde sa signature v1 — `(boitier, utilisateurs, etat, rejets, refuses)`, T5 y
ajoutera `cites` et `emettre` — reconstruit l'état avec les deux index, puis filtre les
travaux au lieu des deux listes disparues :

```python
    comptes, groupes = lire_comptes_et_groupes(boitier)
    plan_reconstruit = construction_plan.construire(
        utilisateurs, replace(etat, comptes=comptes, groupes=groupes), rejets
    )
    return replace(
        plan_reconstruit,
        travaux=tuple(
            replace(
                travail,
                adhesions=tuple(
                    groupe
                    for groupe in travail.adhesions
                    if (travail.identifiant_cible, groupe) not in refuses.adhesions
                ),
            )
            for travail in plan_reconstruit.travaux
            if travail.identifiant_cible not in refuses.comptes
        ),
        groupes_a_creer=tuple(
            groupe
            for groupe in plan_reconstruit.groupes_a_creer
            if groupe.nom not in refuses.groupes
        ),
    )
```

- [ ] **Étape 7 : adapter `presentation.py`**

Les deux lignes que le nouveau plan rend nécessaires sont écrites **dans leur forme
définitive**, pas dans une forme provisoire : leur texte est connu (spec, « `presentation.py` »)
et un journal qui ment, même le temps d'une tâche, est un journal qu'il faudrait re-prouver.
T6 ne les réécrira pas ; il ajoutera les lignes d'ambiguïté et celle des membres non
rattachés, et enrichira la confirmation.

```python
def _ligne_du_travail(travail: TravailCompte) -> str:
    """Ce que l'outil va faire à ce compte : rien, ou des ajouts. Jamais « ignoré » —
    un compte déjà présent n'est plus ignoré, et le journal dit ce qui lui arrive."""
    adhesions = ", ".join(travail.adhesions)
    if travail.a_creer:
        return f"{travail.identifiant_cible} : à créer" + (
            f", rattaché à {adhesions}" if travail.adhesions else ""
        )
    if travail.adhesions:
        return f"{travail.identifiant_cible} : présent — ajouté à {adhesions}"
    return f"{travail.identifiant_cible} : présent — rien à faire"


def _ligne_des_orphelins(nombre: int) -> str:
    """Un nombre, jamais une liste : sur un boîtier de 500 comptes et un fichier de 20,
    la liste noyait le plan et les rejets — ce sur quoi l'opérateur doit se prononcer."""
    if nombre == 1:
        return "1 compte du boîtier ne figure pas dans le fichier : il ne sera pas touché."
    return (
        f"{nombre} comptes du boîtier ne figurent pas dans le fichier : "
        "ils ne seront pas touchés."
    )
```

- `lignes_du_plan` : les groupes à créer (inchangé), puis une ligne par travail
  (`_ligne_du_travail`), puis `_ligne_des_orphelins(plan.nombre_orphelins)` **si le nombre
  n'est pas nul**. Les deux lignes disparues — « déjà présent, ignoré » et « Orphelins sur le
  boîtier : … » — ne survivent nulle part.
- `texte_de_confirmation_du_lot` : `len(plan.comptes_a_creer)` devient
  `len(plan.creations)`.
- Importer `TravailCompte` dans `presentation.py`.

- [ ] **Étape 8 : adapter les tests existants rendus faux — inventaire exhaustif**

Cette liste a été établie en exécutant la suite v1 contre le code de la v2 : c'est
**exactement** ce qui tombe, rien de plus, rien de moins. Aucun de ces tests n'est supprimé
parce qu'il gêne : chacun devient faux parce que la règle qu'il énonçait a changé, ou parce
que la donnée qu'il lit a changé de nom — et il est réécrit sur la règle neuve, sans rien
perdre de sa précision.

| Test | Pourquoi il tombe | Ce qu'il devient |
|---|---|---|
| `test_plan.py` — les 13 tests | `EtatBoitier` et `Plan` changent de forme, et la décision change de contenu | fichier réécrit (étape 1) ; chaque règle v1 encore vraie y a son test, augmenté de la casse, des adhésions et des compteurs |
| `test_modele.py::test_nombre_d_operations_du_plan` | `Plan(comptes_a_creer=…)` n'existe plus | reconstruit avec `travaux=(TravailCompte(…),)`, même arithmétique (`1 + 4 + 2`). **Ajouter** un cas : un compte déjà présent à deux adhésions vaut **deux** opérations, pas quatre — ni création, ni mot de passe. Une fabrique locale `_plan(travaux, groupes_a_creer)` évite de répéter les sept champs |
| `test_presentation.py::test_le_plan_annonce_groupes_comptes_ignores_et_orphelins` | construit un `Plan` v1 et attend « déjà présent, ignoré » et la liste des orphelins | remplacé par `test_le_plan_dit_par_compte_ce_qui_lui_arrive` (T6, étape 1). En attendant, l'adapter au rendu de l'étape 7 : « à créer, rattaché à … », « présent — rien à faire », et la ligne comptée des orphelins. La formule v1 ne disparaît pas par confort : la spec la déclare mensongère, un compte présent recevant désormais des adhésions |
| `test_presentation.py::test_l_accord_de_membre_suit_le_nombre_de_membres` | construit un `Plan` v1 | même test, sur un plan sans travaux : il n'éprouve que l'accord de « membre », qui ne bouge pas |
| `test_presentation.py::test_un_plan_sans_groupe_ni_orphelin_n_annonce_ni_l_un_ni_l_autre` | idem | même test, avec un unique travail à créer sans adhésion : le rendu attendu reste `["dupont : à créer"]` |
| `test_presentation.py::_plan` et ses 6 appelants (l. 765, 778, 788, 796, 803, 810) | le helper construit un `Plan` v1 | seul le helper change : il rend des `TravailCompte(..., a_creer=True, adhesions=())`. Les six tests de confirmation gardent leurs assertions mot pour mot — `len(plan.creations)` vaut ce que `len(plan.comptes_a_creer)` valait |
| `test_presentation.py::test_travailler_transmet_les_rejets_a_executer` (l. 866) | lit `plan.orphelins` | `assert plans[0].plan.nombre_orphelins == 0`. Le test prouve le câblage des rejets jusqu'à `executer` ; il le prouve autant sur un compteur que sur un tuple vide |
| `test_execution_ecriture.py::test_un_lot_reel_demande_confirmation_sur_le_plan_avant_toute_ecriture` (l. 137) | lit `vus[0].comptes_a_creer` | `[travail.identifiant_cible for travail in vus[0].creations] == ["dupont"]` |
| `test_execution_ecriture.py::test_simulation_lit_mais_n_ecrit_pas` (l. 182 **et** 183) | lit `comptes_a_creer` **et** `plan.orphelins == ("martin",)` | `plan.creations` pour la première, `plan.nombre_orphelins == 1` pour la seconde. Le nom de l'orphelin disparaît du plan par exigence de la spec — c'est le comportement testé qui change, pas la couverture |
| `test_execution_ecriture.py::test_reconnexion_reconstruit_le_plan_au_lieu_de_rejouer` (l. 346) | lit `comptes_ignores` | `[travail.identifiant_cible for travail in plans[-1].plan.travaux if not travail.a_creer]` : la même preuve — après reconnexion, les deux comptes sont vus comme présents |
| `test_execution_ecriture.py::test_executer_transmet_les_rejets_a_la_construction_du_plan` (l. 367) | lit `plan.orphelins` | `plans[0].plan.nombre_orphelins == 0` |
| `test_execution_ecriture.py::test_la_reconstruction_du_plan_apres_reconnexion_transmet_aussi_les_rejets` (l. 391) | lit `plan.orphelins` | `plans[-1].plan.nombre_orphelins == 0` |
| `test_execution_ecriture.py::test_reprise_les_comptes_deja_crees_sont_ignores` (l. 586) | lit `comptes_ignores` | la même compréhension que ci-dessus, comparée à `["dupont"]` — **à replier sur quatre lignes**, voir l'extrait sous le tableau : transcrite d'un trait elle fait 112 caractères et `ruff` la refuse (`line-length = 100`) |
| `test_execution_lecture.py::test_un_annuaire_est_le_cas_nominal` (l. 21-22) | `etat.utilisateurs` / `etat.groupes` ne sont plus des `frozenset` | `etat.comptes.graphies == ("martin",)` et `etat.groupes.graphies == ("rh",)` — l'index conserve l'ordre rendu, l'assertion y gagne en précision |
| `test_execution_lecture.py::test_reprise_ne_relit_que_les_comptes_et_les_groupes` (l. 116-118) | `lire_comptes_et_groupes` rend deux index | `utilisateurs.graphies == ("martin",)`, `groupes.graphies == ("rh",)` ; l'assertion sur les deux seules opérations lues ne bouge pas (le test disparaît en T5, remplacé par celui de `relire_inventaire`) |

Deux détails que le tableau ne peut pas porter, et que le cadre du tableau rend faciles à
manquer — l'un coûte un `ruff` rouge, l'autre un `NameError` :

```python
# test_reprise_les_comptes_deja_crees_sont_ignores : repliée, 100 caractères au plus.
    assert [
        travail.identifiant_cible
        for travail in plans[0].plan.travaux
        if not travail.a_creer
    ] == ["dupont"]
```

- **Importer `TravailCompte` dans `tests/test_modele.py` et dans `tests/test_presentation.py`**
  (depuis `stormshield_utilisateurs.modele`), en plus de `presentation.py` : les tests réécrits
  ci-dessus le construisent des deux côtés, et il n'y est aujourd'hui dans ni l'un ni l'autre.
  Sans ces imports, `NameError` à l'exécution.

Pour les trois tests de `lignes_du_plan` et le helper `_plan`, le rendu attendu en fin de T4
— il n'y a rien à deviner, et T6 le remplacera par un rendu plus complet :

```python
# test_le_plan_annonce_groupes_comptes_ignores_et_orphelins, sur un plan portant
# un travail à créer avec un groupe, un travail déjà présent sans adhésion, un groupe
# à créer et un orphelin :
    assert lignes_du_plan(plan) == [
        "Groupes à créer : compta_bis (1 membre)",
        "dupont : à créer, rattaché à compta_bis",
        "legrand : présent — rien à faire",
        "1 compte du boîtier ne figure pas dans le fichier : il ne sera pas touché.",
    ]


# test_un_plan_sans_groupe_ni_orphelin_n_annonce_ni_l_un_ni_l_autre :
    assert lignes_du_plan(plan) == ["dupont : à créer"]


# le helper de confirmation, sans import nouveau : les sept champs sont écrits une fois,
# et T6 y ajoutera ses propres fabriques.
def _plan(
    comptes: tuple[str, ...] = ("dupont",),
    groupes: tuple[GroupeACreer, ...] = (),
) -> Plan:
    return Plan(
        travaux=tuple(
            TravailCompte(utilisateur(identifiant), identifiant, True, ())
            for identifiant in comptes
        ),
        groupes_a_creer=groupes,
        nombre_orphelins=0,
        nombre_membres_non_rattaches=0,
        groupes_ambigus=(),
        comptes_ambigus=(),
        domaine="interne.local",
    )
```

Un test **ne tombe pas** mais change de sens, et il faut le dire :

- `test_execution_ecriture.py::test_coupure_pendant_le_rattachement_laisse_une_trace`
  (l. 424) continue de passer, alors que le comportement s'inverse. En v1 le plan reconstruit
  ne replanifiait pas l'adhésion d'un compte devenu « déjà présent », et le lot se terminait
  proprement ; en v2 elle est replanifiée, la coupure se reproduit, et le lot s'achève sur un
  arrêt réseau après deux tours sans progrès (vérifié : `rapport.interrompu is True`,
  `motif_arret is MotifArret.RESEAU`, 4 connexions, 3 échecs `USER GROUP ADDUSER`). Sa
  docstring devient fausse : la réécrire — « l'adhésion est replanifiée après reconnexion ;
  si la coupure se répète, le garde-fou des tours sans progrès ferme la boucle » — et
  **ajouter** `assert rapport.motif_arret is MotifArret.RESEAU`, sans quoi ce renversement
  n'est prouvé nulle part.

- [ ] **Étape 9 : ajouter le test comportemental du mot de passe**

Dans `tests/test_execution_ecriture.py` :

```python
def test_aucun_mot_de_passe_n_est_pose_sur_un_compte_deja_present() -> None:
    """La garantie que le nouveau périmètre met le plus à l'épreuve : l'outil écrit
    désormais sur des comptes existants."""
    boitier = BoitierMemoire(utilisateurs=["Jean.Dupont", "legrand"], groupes=["rh"])
    _lancer(
        boitier,
        [_utilisateur("jean.dupont", "rh"), _utilisateur("legrand", ligne=3)],
        simulation=False,
    )
    assert "definir_mot_de_passe" not in [operation for operation, _ in boitier.journal_appels]
    assert boitier.mots_de_passe == {}


def test_un_compte_ambigu_ne_recoit_rien_et_le_lot_continue() -> None:
    """Ni création, ni adhésion, ni mot de passe — et les autres comptes du lot passent :
    un boîtier mal rangé ne prive pas les deux cents autres."""
    boitier = BoitierMemoire(
        utilisateurs=["Jean.Dupont", "JEAN.DUPONT"], groupes=["rh"]
    )
    _lancer(
        boitier,
        [_utilisateur("jean.dupont", "rh"), _utilisateur("legrand", ligne=3)],
        simulation=False,
    )
    assert boitier.membres.get("rh", []) == []
    assert boitier.mots_de_passe.keys() == {"legrand"}
    assert sorted(boitier.utilisateurs) == ["JEAN.DUPONT", "Jean.Dupont", "legrand"]
```

Le montage suppose que `BoitierMemoire` accepte deux graphies d'un même compte : c'est
exactement le cas que la spec lui demande de savoir provoquer (« `BoitierMemoire`, qui doit
grandir »), et T2 le prouve désormais par un test dédié. Le double expose bien ses comptes
sous `utilisateurs` (`boitier_memoire.py:25`) et ses mots de passe sous `mots_de_passe` : les
deux montages ci-dessus ont été exécutés tels quels.

- [ ] **Étape 10 : lancer la suite entière**

Run : `.venv/bin/python -m pytest`
Attendu : SUCCÈS.

- [ ] **Étape 11 : analyse statique puis commit**

```bash
.venv/bin/ruff check . --exclude .claude && .venv/bin/mypy
git add stormshield_utilisateurs tests
git commit -m "feat: un travail par compte, reconnaissance insensible à la casse, adhésions ajoutées"
```

---

### Tâche 5 : la lecture d'état passe à `4 + g`

**Fichiers :**
- Modifier : `stormshield_utilisateurs/execution.py:30-31` (la constante), `:70-98`
  (`lire_etat` et `lire_comptes_et_groupes` **supprimées**), `:298-363` (`executer`),
  `:366-432` (`_appliquer`), `:480-489` (`_arreter_par_l_operateur`), `:514-542`
  (`_replanifier`), et ajout de `Socle`, `lire_socle`, `lire_adhesions`,
  `relire_inventaire`
- Modifier : `stormshield_utilisateurs/modele.py:120-132` (`Rapport`) — **un champ de
  plus**, `plan_construit`, exigé par le point d'arrêt neuf (étape 4)
- Modifier : `stormshield_utilisateurs/boitier.py:44` et
  `stormshield_utilisateurs/boitier_sdk.py:199` — deux docstrings renvoient à
  `execution.lire_etat`, qui disparaît ici ; écrire `execution.lire_socle`
- Modifier : `tests/fabriques.py` (accueille `_Interrupteur`)
- Modifier : `tests/test_execution_lecture.py`, `tests/test_execution_ecriture.py` (totaux de
  progression, idempotence, reprise)

**Interfaces :**
- Consomme : `Boitier.lister_membres` (**T3** : c'est le `Protocol` qui est appelé ici, pas le
  double), `plan.groupes_cites`, `plan.groupes_a_interroger`,
  `EtatBoitier.membres_par_groupe` (T4).
- Produit : `LECTURES_DE_BASE: int = 4` ; `Socle(domaine, plancher, comptes, groupes)` ;
  `lire_socle(boitier) -> Socle` ;
  `lire_adhesions(boitier, identites, *, emettre, arret_demande=jamais_arrete,
  apres_chaque=_rien) -> dict[str, tuple[str, ...]]` ;
  `relire_inventaire(boitier, cites, emettre) -> tuple[IndexBoitier, IndexBoitier,
  dict[str, tuple[str, ...]]]`. `lire_comptes_et_groupes` **disparaît**.
- Produit aussi : `Rapport.plan_construit: bool = False`, lu par `presentation.py` en T6.

C'est cette tâche qui rend l'outil idempotent : jusqu'ici l'inventaire des adhésions était
vide et les `ADDUSER` repartaient à chaque exécution.

**Lecture de la spec assumée** : « `NOMBRE_LECTURES = 4` cesse d'être une constante » se
réalise ici en gardant une constante pour la **part fixe** (`LECTURES_DE_BASE`) et en
calculant le **total** (`LECTURES_DE_BASE + g`). L'intention — le nombre de lectures n'est plus
connu d'avance — est respectée, et nommer les quatre commandes fixes vaut mieux que semer un
`4` littéral dans `executer`.

- [ ] **Étape 1 : écrire les tests de la phase de lecture**

`lire_etat` disparaît, et **cinq** tests de `tests/test_execution_lecture.py` l'appellent —
pas deux. Aucun ne perd sa preuve : `lire_socle` fait exactement ce que `lire_etat` faisait,
moins l'inventaire des adhésions, et ces cinq tests portent sur l'annuaire, pas sur les
membres.

| Test | Ligne | Ce qu'il devient |
|---|---|---|
| `test_un_annuaire_est_le_cas_nominal` | 19 | `socle = lire_socle(boitier)` ; assertions sur `socle.domaine`, `socle.comptes.graphies`, `socle.groupes.graphies`, `socle.plancher` (déjà adapté en T4 pour les index, ici pour le nom de la fonction) |
| `test_la_lecture_n_ecrit_rien` | 28 | `lire_socle(boitier)` ; le jeu des quatre opérations lues ne bouge pas |
| `test_aucun_annuaire_demande_l_initialisation` | 40 | `lire_socle(BoitierMemoire(annuaires=[]))` — `AnnuaireAbsent` est toujours levée par le socle |
| `test_plusieurs_annuaires_arretent_tout` | 47 | `lire_socle(boitier)` — `AnnuairesMultiples` inchangée, y compris la garde « aucun `lister_utilisateurs` » |
| `test_initialisation_puis_activation_puis_relecture_de_confirmation` | 64 | `lire_socle(boitier).domaine == "neuf.local"` |
| `test_reprise_ne_relit_que_les_comptes_et_les_groupes` | 113 | **remplacé** par `test_la_relecture_apres_reconnexion_reconstruit_tout_l_inventaire` ci-dessous : la fonction qu'il éprouvait n'existe plus, et la relecture qui la remplace relit davantage — la preuve est plus forte, pas plus faible |

Puis ajouter les tests de la phase de lecture neuve :

```python
def test_la_lecture_vaut_quatre_commandes_plus_un_par_groupe_cite_et_present() -> None:
    boitier = BoitierMemoire(utilisateurs=["dupont"], groupes=["compta", "jamais.cite"])
    socle = lire_socle(boitier)
    identites = groupes_a_interroger(("compta", "neuf"), socle.groupes)
    lire_adhesions(boitier, identites, emettre=lambda _: None)
    assert [operation for operation, _ in boitier.journal_appels] == [
        "lister_annuaires",
        "lire_politique",
        "lister_utilisateurs",
        "lister_groupes",
        "lister_membres",
    ]


def test_l_arret_est_consulte_avant_chaque_lecture_d_inventaire() -> None:
    """Sans quoi le bouton *Arrêter* serait inerte pendant la phase devenue longue.

    `_ArretParLOperateur` est privé et le reste : ce test est le seul à l'importer,
    parce qu'il éprouve l'unité de lecture isolément. La preuve de bout en bout est
    `test_l_arret_pendant_l_inventaire_ne_construit_aucun_plan`, qui ne connaît que
    l'interface publique.
    """
    boitier = BoitierMemoire(groupes=["compta", "rh"])
    with pytest.raises(_ArretParLOperateur):
        lire_adhesions(
            boitier, ("compta", "rh"), emettre=lambda _: None,
            arret_demande=_Interrupteur(demande=True),
        )
    assert ("lister_membres", "compta") not in boitier.journal_appels


def test_un_groupe_dont_les_membres_sont_illisibles_ne_stoppe_pas_la_lecture() -> None:
    """Section vide ou refus : les deux valent « aucun membre connu »."""
    boitier = BoitierMemoire(groupes=["compta", "rh"])

    def refuser(operation: str, cible: str) -> None:
        if operation == "lister_membres" and cible == "compta":
            raise ErreurCommande(200, "groupe illisible")

    boitier.declencheur = refuser
    membres = lire_adhesions(boitier, ("compta", "rh"), emettre=lambda _: None)
    assert membres == {"compta": (), "rh": ()}


def test_la_relecture_apres_reconnexion_reconstruit_tout_l_inventaire() -> None:
    """Réutiliser un inventaire antérieur à la coupure ferait rejouer des ajouts déjà
    passés, ou manquer ceux qu'un autre chemin aurait posés entre-temps."""
    boitier = BoitierMemoire(utilisateurs=["dupont"], groupes=["compta"])
    boitier.ajouter_membre("compta", "dupont")
    comptes, groupes, membres = relire_inventaire(boitier, ("compta",), lambda _: None)
    assert comptes.graphies == ("dupont",)
    assert groupes.graphies == ("compta",)
    assert membres == {"compta": ("uid=dupont,ou=users,dc=interne,dc=local",)}
    assert "lister_annuaires" not in [operation for operation, _ in boitier.journal_appels]
```

`_Interrupteur` est déjà écrit dans `tests/test_execution_ecriture.py:50-64` (callable,
construit avec `demande=` et basculé par `demander()`) : le déplacer dans `tests/fabriques.py`
plutôt que de le dupliquer, et l'importer des deux côtés (`from fabriques import
_Interrupteur`, comme `utilisateur` l'est déjà ailleurs). Imports à ajouter dans
`tests/test_execution_lecture.py` : `_ArretParLOperateur`, `lire_adhesions`, `lire_socle`,
`relire_inventaire` depuis `execution`, et `groupes_a_interroger` depuis
`stormshield_utilisateurs.plan` ; `pytest` et `ErreurCommande` y sont déjà.

- [ ] **Étape 2 : lancer, constater l'échec**

Run : `.venv/bin/python -m pytest tests/test_execution_lecture.py -v`
Attendu : ÉCHEC — `ImportError: cannot import name 'lire_socle'`.

- [ ] **Étape 3 : écrire la nouvelle phase de lecture**

**Où poser ce bloc :** `Socle`, `lire_socle`, `lire_adhesions` et `relire_inventaire` ne
peuvent **pas** prendre la place de `lire_etat` (ligne 70). Leurs annotations et leurs valeurs
par défaut citent `Emetteur` (l. 205), `ArretDemande` (l. 214) et `jamais_arrete` (l. 217),
définis bien plus bas : évaluées à la définition de la fonction, elles lèveraient un
`NameError` **à l'import du module**. Les poser juste **après `jamais_arrete`**, avant
`class _ArretParLOperateur`. Les corps, eux, peuvent citer `_verifier_arret` défini plus loin :
un corps ne se résout qu'à l'appel. `LECTURES_DE_BASE` et `_rien`, qui ne dépendent de rien,
restent en tête, à la place de `NOMBRE_LECTURES`.

```python
# CONFIG LDAP LIST, CONFIG PASSWDPOLICY SHOW, USER LIST, USER GROUP LIST. La part fixe
# de la lecture : le total vaut `LECTURES_DE_BASE + g`, où `g` est le nombre de groupes
# cités par le fichier et reconnus sur le boîtier — connu seulement après la quatrième.
LECTURES_DE_BASE = 4


def _rien() -> None:
    """Défaut neutre : la lecture d'inventaire se teste sans compteur ni barre."""


@dataclass(frozen=True)
class Socle:
    """Les quatre lectures fixes. C'est `groupes` qui dit combien d'autres suivront."""

    domaine: str
    plancher: PlancherPolitique
    comptes: IndexBoitier
    groupes: IndexBoitier


def lire_socle(boitier: Boitier) -> Socle:
    """Lecture seule, dans l'ordre du flux d'exécution de la spec, avec le traitement
    des trois cas d'annuaire. Les adhésions se lisent ensuite, avec `lire_adhesions`."""
    annuaires = boitier.lister_annuaires()
    if not annuaires:
        raise AnnuaireAbsent("le boîtier ne déclare aucun annuaire LDAP interne")
    if len(annuaires) > 1:
        raise AnnuairesMultiples(tuple(annuaires))
    plancher = boitier.lire_politique()
    return Socle(
        domaine=annuaires[0],
        plancher=plancher,
        comptes=IndexBoitier.depuis(boitier.lister_utilisateurs()),
        groupes=IndexBoitier.depuis(boitier.lister_groupes()),
    )


def lire_adhesions(
    boitier: Boitier,
    identites: Sequence[str],
    *,
    emettre: Emetteur,
    arret_demande: ArretDemande = jamais_arrete,
    apres_chaque: Callable[[], None] = _rien,
) -> dict[str, tuple[str, ...]]:
    """Un `USER GROUP SHOW` par groupe cité et reconnu, dans l'ordre reçu.

    L'arrêt est consulté **entre deux lectures**, jamais au milieu de l'une d'elles : la
    phase n'est plus l'affaire de quatre commandes, et un bouton *Arrêter* inerte
    pendant qu'elle dure serait un bouton qui ment. Une lecture interrompue ne construit
    aucun plan et n'écrit rien.
    """
    membres: dict[str, tuple[str, ...]] = {}
    for identite in identites:
        _verifier_arret(arret_demande)
        try:
            membres[cle(identite)] = tuple(boitier.lister_membres(identite))
        except ErreurCommande as erreur:
            # Un groupe sans membre peut rendre une section vide ou un refus : les deux
            # se traitent comme « aucun membre connu ». Au pire des ADDUSER redondants
            # partiront, que le boîtier absorbera ou refusera.
            membres[cle(identite)] = ()
            emettre(
                Journal(
                    f"groupe {identite} : membres illisibles ({erreur}) — ses adhésions "
                    "seront toutes considérées comme manquantes"
                )
            )
        apres_chaque()
    return membres


def relire_inventaire(
    boitier: Boitier, cites: Sequence[str], emettre: Emetteur
) -> tuple[IndexBoitier, IndexBoitier, dict[str, tuple[str, ...]]]:
    """Reprise après reconnexion : comptes, groupes et **tout** l'inventaire des
    adhésions. Ni l'annuaire (lèverait `AnnuaireAbsent` sur un lot déjà entamé), ni la
    politique (ne change pas pendant un lot)."""
    comptes = IndexBoitier.depuis(boitier.lister_utilisateurs())
    groupes = IndexBoitier.depuis(boitier.lister_groupes())
    membres = lire_adhesions(
        boitier, construction_plan.groupes_a_interroger(cites, groupes), emettre=emettre
    )
    return comptes, groupes, membres
```

Supprimer `lire_etat` et `lire_comptes_et_groupes`. `execution.py` importe désormais `cle` en
plus d'`IndexBoitier` (posé en T4), et `Socle` s'ajoute aux dataclasses du module — ce n'est
pas un événement, il ne rejoint pas l'union `Evenement`.

Corriger au passage les deux docstrings qui renvoient à la fonction supprimée :
`boitier.py:44` (« voir `execution.lire_etat` ») et `boitier_sdk.py:199`
(« `lire_etat` lève `AnnuaireAbsent` ») — écrire `lire_socle`, qui porte désormais cette
garde. Une référence orpheline dans un commentaire coûte, plus tard, une lecture de code pour
rien.

- [ ] **Étape 4 : câbler `executer`, et rendre vrai le journal de l'arrêt**

Dans le corps de `executer`, remplacer le bloc de lecture et de total :

```python
        cites = construction_plan.groupes_cites(utilisateurs)
        boitier.connecter()
        socle = lire_socle(boitier)
        emettre(PolitiqueLue(socle.plancher))
        manquements = tuple(motdepasse.violations(politique, socle.plancher))
        if manquements:
            _arreter_politique(rapport, emettre, manquements, socle.plancher)
        else:
            identites = construction_plan.groupes_a_interroger(cites, socle.groupes)
            # Le nombre exact de lectures n'est connu qu'ici : USER GROUP LIST vient de
            # dire lesquels des groupes cités existent déjà.
            compteur.fixer_total(LECTURES_DE_BASE + len(identites))
            for _ in range(LECTURES_DE_BASE):
                compteur.avancer()
            etat = EtatBoitier(
                domaine=socle.domaine,
                plancher=socle.plancher,
                comptes=socle.comptes,
                groupes=socle.groupes,
                membres_par_groupe=lire_adhesions(
                    boitier, identites, emettre=emettre,
                    arret_demande=arret_demande, apres_chaque=compteur.avancer,
                ),
            )
            plan_courant = construction_plan.construire(utilisateurs, etat, rejets)
            rapport.comptes_prevus = len(plan_courant.creations)
            # Deux faits distincts : combien de comptes étaient prévus, et qu'il y ait
            # eu un plan du tout. Un arrêt tombé plus haut n'a ni l'un ni l'autre.
            rapport.plan_construit = True
            emettre(PlanPret(plan_courant))
            _verifier_arret(arret_demande)
            if not simulation and not confirmer(plan_courant):
                emettre(Journal(ABANDON_A_LA_CONFIRMATION))
            elif not simulation:
                # Seule croissance admise du total, et elle suit immédiatement l'accord
                # donné sur le nombre d'opérations lu dans la boîte de confirmation.
                compteur.fixer_total(compteur.accomplies + plan_courant.nombre_operations())
                _appliquer(
                    boitier, utilisateurs, etat, plan_courant, rejets, cites, politique,
                    rapport, compteur, emettre, patience, generer_mot_de_passe,
                    arret_demande,
                )
```

`_appliquer` prend `cites` — **sixième paramètre, juste après `rejets`**, comme l'appel
positionnel ci-dessus l'exige — et le passe à `_replanifier`, qui remplace son appel à
`lire_comptes_et_groupes` par `relire_inventaire`. Les deux signatures en entier, pour qu'il
n'y ait rien à deviner :

```python
def _appliquer(
    boitier: Boitier,
    utilisateurs: Sequence[Utilisateur],
    etat: EtatBoitier,
    plan_courant: Plan,
    rejets: Sequence[Rejet],
    cites: Sequence[str],
    politique: PolitiqueMotDePasse,
    rapport: Rapport,
    compteur: _Compteur,
    emettre: Emetteur,
    patience: Patience,
    generer_mot_de_passe: Callable[[PolitiqueMotDePasse], str],
    arret_demande: ArretDemande,
) -> None:
```

```python
def _replanifier(
    boitier: Boitier,
    utilisateurs: Sequence[Utilisateur],
    etat: EtatBoitier,
    rejets: Sequence[Rejet],
    cites: Sequence[str],
    refuses: _Refuses,
    emettre: Emetteur,
) -> Plan:
    """Reprise en milieu de lot : comptes, groupes et **tout** l'inventaire des adhésions.

    L'annuaire et le plancher de politique du premier état sont conservés : ni l'un ni
    l'autre ne change pendant un lot, et les relire ferait lever `AnnuaireAbsent` sur un
    chemin que rien ne décrit.
    """
    comptes, groupes, membres = relire_inventaire(boitier, cites, emettre)
    plan_reconstruit = construction_plan.construire(
        utilisateurs,
        replace(etat, comptes=comptes, groupes=groupes, membres_par_groupe=membres),
        rejets,
    )
    return replace(
        plan_reconstruit,
        travaux=…,          # filtre posé en T4, inchangé
        groupes_a_creer=…,  # idem
    )
```

Et son unique site d'appel, dans `_appliquer` :

```python
                reste = _replanifier(
                    boitier, utilisateurs, etat, rejets, cites, refuses, emettre
                )
```

**Le journal de l'arrêt, rendu vrai sur le chemin neuf.** Jusqu'ici l'arrêt demandé ne pouvait
tomber qu'après la construction du plan : le journal pouvait donc affirmer sans risque qu'un
compte était allé à son terme. Le point d'arrêt posé dans `lire_adhesions` ouvre un second
chemin, où **aucun compte n'était en cours** et où **rien n'a été planifié** — la phrase
devient un mensonge mesurable, et l'opérateur chercherait dans le journal un compte qui
n'existe pas. Le rapport doit donc porter le fait qui distingue les deux chemins. Dans
`modele.py`, sous `comptes_prevus` :

```python
    # Faux tant que la phase de lecture n'a pas abouti à un plan. `comptes_prevus` vaut
    # alors zéro faute d'avoir été compté, et non parce que rien n'était à créer : sans
    # cette distinction, un arrêt tombé pendant la lecture se raconterait comme un lot
    # dont le plan ne prévoyait aucune création.
    plan_construit: bool = False
```

Puis `_arreter_par_l_operateur` (`execution.py:480`) gagne une branche, et rien d'autre : le
texte de la v1 reste mot pour mot sur le chemin de la v1 :

```python
def _arreter_par_l_operateur(rapport: Rapport, emettre: Emetteur) -> None:
    """Arrêt sur ordre : ni panne à attendre, ni erreur à corriger avant de relancer.

    Deux textes, parce que l'arrêt a désormais deux moments possibles. Avant le plan,
    aucun compte n'était en cours : dire qu'il est allé à son terme serait faux, et
    l'opérateur chercherait dans le journal un compte qui n'existe pas.
    """
    _marquer_arret(rapport, MotifArret.OPERATEUR)
    if not rapport.plan_construit:
        emettre(
            Journal(
                "arrêt demandé pendant la lecture de l'état du firewall : aucun plan "
                "n'a été construit, aucun compte n'a été entamé, rien n'a été écrit. "
                "Relancer est sans danger : le lot repartira de la première lecture."
            )
        )
        return
    emettre(
        Journal(
            "arrêt demandé : le compte en cours est allé à son terme, les suivants n'ont "
            "pas été entamés. Relancer est sans danger : les comptes créés seront vus "
            "comme déjà présents."
        )
    )
```

Les deux textes commencent par « arrêt demandé » : `test_l_arret_demande_laisse_une_ligne_de_journal`
(l. 900) n'en cherche pas davantage et reste vert sans retouche, quel que soit le chemin pris.
Le **bilan** rendu par `presentation.py` porte le même mensonge sur ce chemin (« Aucun compte
ne restait à créer. » alors que le CSV en portait) : il se corrige en **T6, étape 3**, avec le
reste de la présentation. Vérifié en exécutant : la branche de `_arreter_par_l_operateur` seule
ne casse aucun test existant ; c'est celle de `presentation.py` qui en casse quatre, et T6 les
reprend.

- [ ] **Étape 5 : écrire les tests d'idempotence et de reprise**

Dans `tests/test_execution_ecriture.py` :

```python
def test_rejouer_le_meme_fichier_n_emet_aucune_ecriture() -> None:
    """Zéro commande d'écriture, pas « des commandes sans effet »."""
    boitier = BoitierMemoire()
    utilisateurs = [_utilisateur("dupont", "compta"), _utilisateur("legrand", ligne=3)]
    _lancer(boitier, utilisateurs, simulation=False)
    boitier.journal_appels.clear()
    rapport, _ = _lancer(boitier, utilisateurs, simulation=False)
    assert _ecritures(boitier) == []
    assert rapport.comptes_crees == []


def test_l_idempotence_survit_a_une_difference_de_casse() -> None:
    boitier = BoitierMemoire(utilisateurs=["Jean.Dupont"], groupes=["Compta"])
    boitier.ajouter_membre("Compta", "Jean.Dupont")
    boitier.journal_appels.clear()
    _lancer(boitier, [_utilisateur("jean.dupont", "compta")], simulation=False)
    assert _ecritures(boitier) == []


def test_un_rattachement_illisible_fait_repartir_les_memes_adhesions() -> None:
    """Dégradation honnête : l'outil ne promet pas une idempotence que l'hypothèse sur
    le DN ne garantit pas — il promet qu'un rattachement raté coûte des commandes
    redondantes et jamais un dommage."""
    boitier = BoitierMemoire(
        utilisateurs=["dupont"],
        groupes=["compta"],
        membres={"compta": ("cn=forme-inattendue,dc=local",)},
    )
    _, evenements = _lancer(boitier, [_utilisateur("dupont", "compta")], simulation=False)
    assert ("ajouter_membre", "compta/dupont") in boitier.journal_appels
    (plan,) = [message.plan for message in evenements if isinstance(message, PlanPret)]
    assert plan.nombre_membres_non_rattaches == 1


def test_une_adhesion_refusee_ne_se_rejoue_pas_apres_reconnexion() -> None:
    """Le rapport porterait sinon deux fois le même refus.

    Le compte existe déjà : `compta` est refusé par le boîtier, puis la coupure survient
    sur `rh`. Le plan reconstruit après reconnexion replanifie `rh` — l'inventaire relu
    dit que l'adhésion manque — mais pas `compta`, que le boîtier a explicitement refusé.
    """
    boitier = BoitierMemoire(utilisateurs=["legrand"], groupes=["rh"])
    coupures: list[str] = []

    def saboter(operation: str, cible: str) -> None:
        if operation == "ajouter_membre" and cible == "compta/legrand":
            raise ErreurCommande(200, "groupe compta inconnu")
        if operation == "ajouter_membre" and cible == "rh/legrand" and not coupures:
            coupures.append(cible)
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = saboter
    rapport, _ = _lancer(
        boitier, [_utilisateur("legrand", "compta", "rh")], simulation=False
    )
    # Une seule tentative sur compta : c'est là qu'est la preuve du non-rejeu.
    assert boitier.journal_appels.count(("ajouter_membre", "compta/legrand")) == 1
    refus = [echec for echec in rapport.echecs if "groupe compta inconnu" in echec.motif]
    assert len(refus) == 1
    assert refus[0].operation == "USER GROUP ADDUSER"
    assert boitier.membres["rh"] == [dn_de("legrand")]
```

**Ne pas écrire `count("USER GROUP ADDUSER") == 1`** : le rapport en porte **deux**, et c'est
correct. Exécuté, ce montage donne exactement
`[('legrand', 'USER GROUP ADDUSER', 'code 200 : groupe compta inconnu'),
('legrand', 'USER GROUP ADDUSER', 'coupure réseau pendant le rattachement : …')]` — le refus,
puis la trace que `_signaler_interruption` inscrit sur la coupure réseau. Ce sont deux faits
distincts, tous deux dus à l'opérateur ; ce que la spec interdit, c'est que le **même** refus
revienne deux fois, et c'est cela que les deux premières assertions prouvent.

Le groupe `compta` est bien planifié : absent du boîtier, il est créé par `_creer_groupes`
(le `declencheur` ne refuse que `ajouter_membre`), puis l'adhésion est tentée et refusée.
`dn_de` est déjà importé par le fichier depuis T2.

Ajouter enfin, pour l'arrêt pendant la lecture — de bout en bout, sans rien de privé :

```python
def test_l_arret_pendant_l_inventaire_ne_construit_aucun_plan() -> None:
    """Une lecture interrompue ne construit aucun plan et n'écrit rien ; son bilan est
    celui d'un arrêt demandé à zéro compte créé, et son journal ne parle d'aucun compte
    mené à son terme — il n'y en avait pas."""
    boitier = BoitierMemoire(groupes=["compta", "rh"])
    interrupteur = _Interrupteur()

    def arreter_apres_la_premiere_lecture(operation: str, cible: str) -> None:
        if operation == "lister_membres" and cible == "compta":
            interrupteur.demander()

    boitier.declencheur = arreter_apres_la_premiere_lecture
    rapport, evenements = _lancer(
        boitier,
        [_utilisateur("dupont", "compta", "rh")],
        simulation=False,
        arret=interrupteur,
    )
    assert ("lister_membres", "rh") not in boitier.journal_appels
    assert not [message for message in evenements if isinstance(message, PlanPret)]
    assert rapport.motif_arret is MotifArret.OPERATEUR
    assert rapport.comptes_crees == []
    assert _ecritures(boitier) == []
    (ligne,) = [texte for texte in _textes(evenements) if texte.startswith("arrêt demandé")]
    assert "aucun plan n'a été construit" in ligne
    assert "le compte en cours" not in ligne
```

**Ne pas écrire `assert rapport.comptes_prevus == 0`** : c'est vrai, mais c'est vrai *faute
d'avoir compté*, et une assertion qui fige cette valeur verrouille le bilan mensonger qu'elle
produisait avant la correction. Ce que ce test doit verrouiller, c'est le texte : il n'y a pas
eu de compte en cours, et le journal ne doit pas en inventer un. `_textes` est déjà défini dans
le fichier (l. 106) ; la décomposition `(ligne,) = …` vaut assertion d'unicité — deux lignes
« arrêt demandé » ou aucune font échouer le test.

- [ ] **Étape 6 : corriger les totaux de progression rendus faux**

Quatre tests figent un total qui incluait « 4 lectures ». Vérification faite en exécutant,
**un seul change** : dans les trois autres montages, aucun groupe cité n'existe sur le double,
donc `g = 0` et le total ne bouge pas. Ne pas les toucher — un test recalculé sans nécessité
est un test qu'on croit avoir relu.

| Test | Ligne | Verdict |
|---|---|---|
| `test_progression_en_simulation_couvre_les_seules_lectures` | 591 | `g = 0`, `Progression(4, 4)` **reste vrai** |
| `test_progression_en_reel_couvre_lectures_et_ecritures` | 597 | `g = 0`, total `4 + 4 = 8` **reste vrai** |
| `test_arret_definitif_gele_la_barre_sous_son_total` | 635 | aucun groupe cité, `Progression(5, 8)` **reste vrai** |
| `test_progression_atteint_le_total_quand_une_creation_echoue` | 615 | `compta` et `rh` sont cités **et** présents : `g = 2`. Le total passe de 10 à **12**, les accomplies aussi — `Progression(accomplies=12, total=12)`, commentaire à corriger en « 4 + 2 lectures + … » |

Un cinquième test tombe, et il n'est pas dans cette famille :
`test_le_total_ne_croit_jamais_apres_un_recalcul` (l. 638-652) assère
`totaux == sorted(totaux, reverse=True)` **et** `totaux[-1] < totaux[0]`. La v2 fait croître
le total une fois, après confirmation : la séquence devient `[4, 4, 4, 4, 4, 8, 8, 8, 6]` et
les deux assertions tombent. Ce test n'est ni supprimé ni affaibli : **la moitié de son
invariant survit** — après la confirmation, un recalcul ne peut que faire baisser le total —
et c'est elle qu'il éprouve désormais, sur le même montage. Il est **renommé** (son ancien nom
affirmerait le contraire de ce que la v2 fait) et **remplace** l'ancien, qui ne reste pas à
côté :

```python
def test_un_recalcul_apres_reconnexion_ne_peut_que_faire_baisser_le_total() -> None:
    """Moitié de l'invariant v1 qui survit. Le total croît une fois, à la confirmation
    (`test_le_total_ne_croit_qu_une_fois_l_ecriture_confirmee`) ; passé cet instant, un
    plan reconstruit ne compte plus que le reste et la barre suit à la baisse, plutôt que
    de viser un total qu'aucune opération restante ne peut plus atteindre."""
    boitier = BoitierMemoire()

    def couper_apres_le_premier(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "legrand" and boitier.connexions == 1:
            boitier.utilisateurs.append("legrand")  # le boîtier a exécuté avant la coupure
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_apres_le_premier
    _, evenements = _lancer(boitier, [_utilisateur("dupont"), _utilisateur("legrand", ligne=3)])
    totaux = [progression.total for progression in _progressions(evenements)]
    budget = max(totaux)
    apres_la_confirmation = totaux[totaux.index(budget) :]
    assert apres_la_confirmation == sorted(apres_la_confirmation, reverse=True)
    assert totaux[-1] < budget
```

Et **ajouter** le test du seul instant où le total croît :

```python
def test_le_total_ne_croit_qu_une_fois_l_ecriture_confirmee() -> None:
    """L'amendement de l'invariant v1 « le total ne croît jamais » survit, réduit à ce
    seul moment : juste après que l'opérateur a lu le nombre d'opérations qu'il autorise."""
    boitier = BoitierMemoire(groupes=["compta"])
    _, evenements = _lancer(boitier, [_utilisateur("dupont", "compta")], simulation=False)
    totaux = [progression.total for progression in _progressions(evenements)]
    (plan,) = [message.plan for message in evenements if isinstance(message, PlanPret)]
    assert totaux[0] == LECTURES_DE_BASE + 1  # le seul groupe cité existe déjà
    assert totaux[-1] == totaux[0] + plan.nombre_operations()
    assert totaux == sorted(totaux)
```

Les deux bornes sont exprimées en `LECTURES_DE_BASE` et en `plan.nombre_operations()`, jamais
en nombres nus : un changement de la part fixe de la lecture doit faire bouger ce test, pas le
laisser vert par accident. Exécuté, il donne `[5, 5, 5, 5, 5, 5, 8, 8, 8, 8]`. Importer
`LECTURES_DE_BASE` depuis `execution`.

Un sixième test **ne tombe pas**, mais sa docstring devient fausse — et c'est le jumeau exact
de celle de `reglage_barre` que T6 corrige (`presentation.py:422`) : ne pas corriger l'une
après avoir corrigé l'autre laisserait dans la suite la phrase que le produit vient de
démentir. `test_la_barre_gele_sous_son_total_sur_un_arret_demande` (l. 878-880) affirme
« son total ne **croît jamais** ». Ses assertions restent exactes et ne bougent pas ; seule la
docstring change :

```python
    """Contrat de progression : la barre ne ment pas en s'achevant. Son total ne croît
    qu'une fois, à la confirmation de l'écriture — jamais après, et jamais sur un arrêt.
    C'est `rapport.interrompu` qui dit si le lot est allé au bout."""
```

Un dernier test à retoucher, qui passe mais pour une mauvaise raison :
`test_simulation_lit_mais_n_ecrit_pas` (l. 172) compare le journal à un sur-ensemble
(`operations <= {…}`) qui ne contient pas `lister_membres` ; il ne survit que parce que ce
montage n'a aucun groupe sur le double. Ajouter `"lister_membres"` à ce jeu : la simulation
lit désormais les adhésions, et le test doit dire ce qu'il autorise, pas ce qu'il n'a pas
rencontré.

- [ ] **Étape 7 : lancer la suite entière**

Run : `.venv/bin/python -m pytest`
Attendu : SUCCÈS.

- [ ] **Étape 8 : analyse statique puis commit**

```bash
.venv/bin/ruff check . --exclude .claude && .venv/bin/mypy
git add stormshield_utilisateurs tests
git commit -m "feat: lecture d'état à 4 + g commandes, adhésions relues, idempotence stricte"
```

---

### Tâche 6 : ce que l'opérateur lit

**Fichiers :**
- Modifier : `stormshield_utilisateurs/presentation.py:422` (docstring de `reglage_barre`),
  `:471-482` (docstring), `:541-554` (`avertissement_perte_de_secrets`), `:569-584`
  (`lignes_du_plan`), `:591-630` (`texte_de_confirmation_du_lot`), `:668-699`
  (`_lignes_d_un_arret_demande`)
- Modifier : `stormshield_utilisateurs/fenetre.py:387-391` (docstring seulement)
- Modifier : `tests/test_presentation.py`

**Interfaces :**
- Consomme : `Plan` v2, `TravailCompte`, `GroupeAmbigu`, `CompteAmbigu` (T4),
  `Rapport.plan_construit` (T5).
- Produit : rien de nouveau pour les autres modules ; `lignes_du_plan` et
  `texte_de_confirmation_du_lot` changent de contenu, pas de signature.

**Ce que T4 a déjà posé** : `_ligne_du_travail` et `_ligne_des_orphelins`, dans leur forme
définitive, et l'enchaînement « groupes à créer, travaux, orphelins ». T6 ne les réécrit pas :
il ajoute les trois lignes manquantes — membres non rattachés, groupe ambigu, compte ambigu —,
enrichit la confirmation et purge « déjà présent, ignoré ». Les trois tests de `lignes_du_plan`
adaptés en T4 sont ici **remplacés** par les tests ci-dessous, qui couvrent le rendu complet.

- [ ] **Étape 1 : écrire les tests d'affichage**

Dans `tests/test_presentation.py`, remplacer les trois tests de `lignes_du_plan` et
compléter ceux de la confirmation. `from dataclasses import replace` n'est **pas** dans les
imports du fichier : l'ajouter, ainsi que `GroupeAmbigu` et `CompteAmbigu` (`TravailCompte`
l'a été en T4).

```python
def test_le_plan_dit_par_compte_ce_qui_lui_arrive() -> None:
    plan = Plan(
        travaux=(
            TravailCompte(utilisateur("dupont", "compta", "rh"), "dupont", True,
                          ("compta", "rh")),
            TravailCompte(utilisateur("jean.dupont"), "Jean.Dupont", False, ("rh",)),
            TravailCompte(utilisateur("legrand"), "legrand", False, ()),
        ),
        groupes_a_creer=(GroupeACreer("compta_bis", 1),),
        nombre_orphelins=480,
        nombre_membres_non_rattaches=0,
        groupes_ambigus=(),
        comptes_ambigus=(),
        domaine="interne.local",
    )
    assert lignes_du_plan(plan) == [
        "Groupes à créer : compta_bis (1 membre)",
        "dupont : à créer, rattaché à compta, rh",
        "Jean.Dupont : présent — ajouté à rh",
        "legrand : présent — rien à faire",
        "480 comptes du boîtier ne figurent pas dans le fichier : "
        "ils ne seront pas touchés.",
    ]


def test_un_seul_orphelin_s_annonce_au_singulier() -> None:
    assert lignes_du_plan(replace(_plan_vide(), nombre_orphelins=1)) == [
        "1 compte du boîtier ne figure pas dans le fichier : il ne sera pas touché."
    ]


def test_aucun_orphelin_n_annonce_rien() -> None:
    assert lignes_du_plan(_plan_vide()) == []


def test_les_membres_non_rattaches_ont_leur_ligne_quand_ils_existent() -> None:
    """Sans elle, un lot qui réémet les mêmes ADDUSER a toutes les apparences d'un lot
    qui réussit."""
    plan = replace(_plan_vide(), nombre_membres_non_rattaches=7)
    assert lignes_du_plan(plan) == [
        "7 membres de groupes n'ont pas pu être reconnus : les adhésions "
        "correspondantes seront renvoyées à chaque exécution."
    ]


def test_aucun_membre_non_rattache_n_annonce_rien() -> None:
    """Zéro sur un boîtier sain : la ligne du canari ne doit pas s'afficher pour rien,
    sans quoi elle perdrait tout pouvoir d'alerte. Le plan porte ici des orphelins, pour
    que ce test échoue si la ligne des non-rattachés s'ajoutait à un rendu non vide —
    ce qu'un plan entièrement vide ne prouverait pas."""
    assert lignes_du_plan(replace(_plan_vide(), nombre_orphelins=3)) == [
        "3 comptes du boîtier ne figurent pas dans le fichier : ils ne seront pas touchés."
    ]


def test_une_collision_de_casse_est_dite_en_clair() -> None:
    plan = replace(
        _plan_vide(), groupes_ambigus=(GroupeAmbigu("compta", ("Compta", "COMPTA")),)
    )
    assert lignes_du_plan(plan) == [
        "groupe compta : le boîtier en porte 2 graphies (Compta, COMPTA) — aucun "
        "compte n'y sera rattaché, le doublon se lève à la main sur le boîtier."
    ]


def test_une_collision_de_casse_entre_comptes_est_dite_en_clair() -> None:
    """Même signalement que pour un groupe : ni destructeur, ni bloquant."""
    plan = replace(
        _plan_vide(),
        comptes_ambigus=(CompteAmbigu("jean.dupont", ("Jean.Dupont", "JEAN.DUPONT")),),
    )
    assert lignes_du_plan(plan) == [
        "compte jean.dupont : le boîtier en porte 2 graphies (Jean.Dupont, "
        "JEAN.DUPONT) — rien ne lui sera fait, le doublon se lève à la main sur le "
        "boîtier."
    ]


def test_la_confirmation_annonce_les_adhesions_a_ajouter() -> None:
    """Le seul endroit où l'opérateur voit, avant qu'elle ne parte, l'ampleur de ce que
    l'outil va poser sur des comptes qu'il n'a pas créés."""
    texte = texte_de_confirmation_du_lot("10.0.0.1", _plan_de_confirmation())
    assert "12 comptes à créer, 1 groupe neuf." in texte
    assert "31 adhésions à ajouter." in texte


def test_la_confirmation_promet_qu_aucun_retrait_n_aura_lieu() -> None:
    texte = texte_de_confirmation_du_lot("10.0.0.1", _plan_de_confirmation())
    assert (
        "Cet outil n'enlève rien : aucun compte supprimé ni désactivé, aucune "
        "appartenance de groupe retirée." in texte
    )


def test_une_seule_adhesion_s_annonce_au_singulier() -> None:
    plan = replace(
        _plan_vide(),
        travaux=(TravailCompte(utilisateur("legrand"), "legrand", False, ("rh",)),),
    )
    assert "1 adhésion à ajouter." in texte_de_confirmation_du_lot("10.0.0.1", plan)


def test_l_avertissement_de_perte_ne_parle_plus_de_compte_ignore() -> None:
    """Un compte déjà présent n'est plus « ignoré » : il peut recevoir des adhésions."""
    assert "ignoré" not in avertissement_perte_de_secrets(2)


def test_le_bilan_d_un_arret_pendant_la_lecture_ne_dit_rien_du_reste_a_creer() -> None:
    """Le plan n'était pas construit : rien n'avait été compté, donc rien ne peut être
    dit de ce qui restait à créer. « Aucun compte ne restait à créer » se lirait comme
    « le fichier n'apportait rien », et le CSV en portait."""
    rapport = Rapport(interrompu=True, motif_arret=MotifArret.OPERATEUR)
    assert lignes_du_rapport(rapport)[:4] == [
        "Arrêt demandé.",
        "Le lot s'est arrêté pendant la lecture de l'état du firewall : aucun plan "
        "n'a été construit.",
        "Rien n'a été écrit sur le firewall.",
        "Relancez quand vous voulez : le lot repartira de la première lecture.",
    ]
```

Ce dernier test est le pendant, côté bilan, de
`test_l_arret_pendant_l_inventaire_ne_construit_aucun_plan` (T5) : le point d'arrêt neuf de la
lecture d'inventaire rend un `Rapport` sans plan, que la v1 ne pouvait pas produire. Les
**cinq** `Rapport(…)` de la section « arrêt demandé par l'opérateur » du fichier — celles que
rend `grep -n "motif_arret=MotifArret.OPERATEUR," tests/test_presentation.py` : l. 915, 931,
947, 963 et 976 avant T4 — décrivent, eux, des lots arrêtés **après** la construction du
plan : leur ajouter `plan_construit=True`, sans quoi quatre d'entre eux tombent sur le nouveau
rendu. Mesuré : ce sont exactement ces quatre-là — `…compte_les_crees_et_les_non_touches`,
`…s_accorde_au_singulier`, `…ne_promet_rien_quand_aucun_compte_n_est_ne`,
`…ne_parle_pas_de_zero_restant` —, le cinquième (`…detaille_quand_meme_les_echecs`) passe dans
les deux cas mais décrit le même lot et reçoit le même champ.

Les deux fabriques locales à ajouter au fichier de test, pour ne pas répéter la construction
d'un `Plan` à sept champs. Le helper `_plan(comptes, groupes)` adapté en T4 **reste** : les
six tests de confirmation de la v1 s'appuient dessus et n'ont pas à changer une deuxième fois.

```python
def _plan_vide() -> Plan:
    return Plan(
        travaux=(),
        groupes_a_creer=(),
        nombre_orphelins=0,
        nombre_membres_non_rattaches=0,
        groupes_ambigus=(),
        comptes_ambigus=(),
        domaine="interne.local",
    )


def _plan_de_confirmation() -> Plan:
    """12 comptes à créer, 1 groupe neuf, 31 adhésions — l'exemple de la spec.

    Sept comptes à trois groupes et cinq à deux : 7 × 3 + 5 × 2 = 31.
    """
    groupes = [("compta", "rh", "compta_bis")] * 7 + [("compta", "rh")] * 5
    travaux = tuple(
        TravailCompte(
            utilisateur(f"compte{rang}", *noms), f"compte{rang}", True, noms
        )
        for rang, noms in enumerate(groupes)
    )
    return replace(
        _plan_vide(),
        travaux=travaux,
        groupes_a_creer=(GroupeACreer("compta_bis", 7),),
    )
```

- [ ] **Étape 2 : lancer, constater l'échec**

Run : `.venv/bin/python -m pytest tests/test_presentation.py -v`
Attendu : ÉCHEC sur les textes attendus.

- [ ] **Étape 3 : écrire le rendu**

`_ligne_du_travail` et `_ligne_des_orphelins` existent depuis T4, dans leur forme définitive :
ne pas y toucher. Les trois lignes qui manquent — elles annotent `GroupeAmbigu` et
`CompteAmbigu`, **à ajouter aux imports de `presentation.py`** depuis
`stormshield_utilisateurs.modele`, à côté de `TravailCompte` posé en T4 (sans quoi `ruff` et
`mypy` sont rouges dès l'écriture de ce bloc) :

```python
def _ligne_des_non_rattaches(nombre: int) -> str:
    """Le canari de l'hypothèse sur la forme du DN. N'arrête rien, ne refuse rien, ne
    retire aucune écriture : il informe, il n'intervient pas."""
    if nombre == 1:
        return (
            "1 membre de groupe n'a pas pu être reconnu : l'adhésion correspondante "
            "sera renvoyée à chaque exécution."
        )
    return (
        f"{nombre} membres de groupes n'ont pas pu être reconnus : les adhésions "
        "correspondantes seront renvoyées à chaque exécution."
    )


def _ligne_du_groupe_ambigu(ambigu: GroupeAmbigu) -> str:
    graphies = ", ".join(ambigu.graphies)
    return (
        f"groupe {ambigu.nom_fichier} : le boîtier en porte "
        f"{_accord(len(ambigu.graphies), 'graphie')} ({graphies}) — aucun compte n'y "
        "sera rattaché, le doublon se lève à la main sur le boîtier."
    )


def _ligne_du_compte_ambigu(ambigu: CompteAmbigu) -> str:
    """Même signalement que pour un groupe, et même conséquence : l'outil ne tranche pas
    ce que le boîtier n'a pas tranché, et le lot continue sans ce compte."""
    graphies = ", ".join(ambigu.graphies)
    return (
        f"compte {ambigu.identifiant_fichier} : le boîtier en porte "
        f"{_accord(len(ambigu.graphies), 'graphie')} ({graphies}) — rien ne lui sera "
        "fait, le doublon se lève à la main sur le boîtier."
    )
```

`lignes_du_plan` enchaîne : groupes à créer (inchangé), une ligne par travail, une ligne par
groupe ambigu, une ligne par compte ambigu, la ligne des orphelins si le nombre n'est pas nul,
celle des membres non rattachés si le nombre n'est pas nul.

**Arbitrage écrit, à ne pas re-trancher** : la spec (« puis le nombre d'orphelins en une
ligne, puis, s'il n'est pas nul, le nombre de membres non rattachés ») peut se lire comme
n'exigeant la condition que sur le second compteur. Les deux la portent ici, pour deux
raisons : « 0 compte du boîtier ne figure pas dans le fichier » sur un boîtier vierge est du
bruit au-dessus de ce sur quoi l'opérateur doit se prononcer, et la v1 n'affichait déjà rien
dans ce cas. Le plan ne perd aucune information : un journal sans cette ligne dit zéro.

`texte_de_confirmation_du_lot` : `len(plan.creations)` pour les comptes (posé en T4), une
partie de plus **juste après celle des comptes et des groupes neufs**, dans la liste
`parties` :
`f"{_accord(plan.nombre_adhesions, 'adhésion à ajouter', 'adhésions à ajouter')}."`, et le
dernier paragraphe devient :

```python
    parties.append(
        "Rien n'a encore été écrit sur le firewall. Cet outil n'enlève rien : aucun "
        "compte supprimé ni désactivé, aucune appartenance de groupe retirée."
        "\n\nÉcrire maintenant ?"
    )
```

**Le bilan d'un arrêt tombé avant le plan.** `_lignes_d_un_arret_demande` (l. 668) se dit
contre `comptes_prevus`, qui n'a de sens qu'une fois le plan construit. Sur le chemin ouvert
par T5 — arrêt pendant la lecture d'inventaire — il vaut zéro faute d'avoir été compté, et le
bilan affirme alors « Aucun compte ne restait à créer. » quand le CSV en portait. Mesuré tel
quel avant correction, avec un CSV d'un compte à créer. Poser la branche **en tête de la
fonction**, avant tout calcul :

```python
    if not rapport.plan_construit:
        # Arrêt tombé pendant la lecture d'inventaire : rien n'a été compté, donc rien
        # ne peut être dit de ce qui restait à créer. « Aucun compte ne restait à
        # créer » se lirait comme « le fichier n'apportait rien », ce qui est faux.
        return [
            "Arrêt demandé.",
            "Le lot s'est arrêté pendant la lecture de l'état du firewall : aucun plan "
            "n'a été construit.",
            "Rien n'a été écrit sur le firewall.",
            "Relancez quand vous voulez : le lot repartira de la première lecture.",
        ]
```

La forme v1 est conservée — quatre lignes, « Arrêt demandé. » en tête, « Relancez quand vous
voulez : … » en queue — et la suite de la fonction ne bouge pas d'une ligne : le chemin
historique rend exactement ce qu'il rendait. `lignes_du_rapport` non plus ne change pas, elle
continue d'aiguiller sur `MotifArret.OPERATEUR`.

- [ ] **Étape 4 : purger « déjà présent, ignoré »**

Trois textes visibles et trois docstrings mentent désormais :

- `presentation.py:553` (`avertissement_perte_de_secrets`, texte rendu à l'opérateur —
  la ligne 552 porte « …ne leur redonnera de mot de passe, », la formule est sur la
  suivante) : remplacer « ils seront classés « déjà présent, ignoré » » par « ils seront vus
  comme déjà présents et ne recevront plus que leurs adhésions manquantes ».
- `presentation.py:480` et `:545` (docstrings) : même correction de vocabulaire.
- `presentation.py:422` (docstring de `reglage_barre`) : « Le total ne croît jamais : un plan
  reconstruit après reconnexion ne peut que le réduire » devient faux depuis T5. Écrire que le
  total croît **une seule fois**, à la confirmation de l'écriture, et qu'un recalcul après
  reconnexion ne peut ensuite que le réduire. La fonction elle-même ne change pas : elle
  n'a jamais lu que la progression qu'on lui donne.
- `fenetre.py:389-390` (docstring de `_confirmer_la_perte_des_secrets`, la formule court sur
  deux lignes) : idem. **Aucune autre ligne de `fenetre.py` ne change** — vérifié : la fenêtre
  ne touche le plan que par `lignes_du_plan` (l. 526-527).
- `execution.py::_arreter_par_l_operateur` : sa formule « seront vus comme déjà présents »
  reste vraie et ne change pas ici. **T5 y a déjà posé sa branche** — le texte du chemin
  « arrêt avant le plan » —, et T6 ne touche pas ce fichier : rien à faire dans cette étape,
  la moitié `presentation.py` du même défaut est traitée à l'étape 3.

- [ ] **Étape 5 : lancer la suite entière**

Run : `.venv/bin/python -m pytest`
Attendu : SUCCÈS.

- [ ] **Étape 6 : analyse statique puis commit**

```bash
.venv/bin/ruff check . --exclude .claude && .venv/bin/mypy
git add stormshield_utilisateurs tests
git commit -m "feat: le journal dit ce qui arrive à chaque compte, orphelins comptés"
```

---

### Tâche 7 : la garde structurelle du mot de passe

**Fichiers :**
- Modifier : `tests/test_amorcage.py` (ajout d'une garde de structure)

**Interfaces :**
- Consomme : la structure de `execution.py` posée en T4 et T5.
- Produit : rien pour le code.

La spec exige que le mot de passe d'un compte existant reste hors d'atteinte
**structurellement**, et pas seulement non appelé. Le test comportemental (T4, étape 9) prouve
le « non appelé » ; celui-ci prouve le « structurellement », sans importer autre chose que
`ast` — même technique que les gardes déjà en place, et pour la même raison : ce qu'un test
comportemental ne voit pas, c'est la branche que quelqu'un ajoutera demain.

- [ ] **Étape 1 : écrire la garde**

```python
def test_le_mot_de_passe_n_est_atteignable_que_depuis_la_creation_d_un_compte() -> None:
    """Un compte déjà présent ne doit jamais voir son mot de passe touché, et c'est la
    structure du module qui doit l'interdire : `_definir_mot_de_passe` n'a qu'un seul
    appelant, `_creer_le_compte`, qui n'est lui-même atteint qu'après avoir constaté
    qu'un compte est à créer.
    """
    source = Path(stormshield_utilisateurs.__file__).with_name("execution.py")
    arbre = ast.parse(source.read_text(encoding="utf-8"))
    appelants = {
        fonction.name
        for fonction in ast.walk(arbre)
        if isinstance(fonction, ast.FunctionDef)
        for appel in ast.walk(fonction)
        if isinstance(appel, ast.Call)
        and isinstance(appel.func, ast.Name)
        and appel.func.id == "_definir_mot_de_passe"
    }
    assert appelants == {"_creer_le_compte"}
```

- [ ] **Étape 2 : lancer et vérifier que la garde mord**

Run : `.venv/bin/python -m pytest tests/test_amorcage.py -v`
Attendu : SUCCÈS. Puis, pour prouver qu'elle n'est pas décorative : ajouter temporairement un
appel à `_definir_mot_de_passe` dans `_traiter_comptes`, relancer, constater l'ÉCHEC,
**retirer la modification temporaire**.

- [ ] **Étape 3 : suite entière, analyse statique, commit**

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check . --exclude .claude && .venv/bin/mypy
git add tests/test_amorcage.py
git commit -m "test: garde de structure — le mot de passe n'est atteignable qu'après création"
```

---

### Tâche 8 : `README.md`

**Fichiers :** Modifier `README.md` (sections « État », « Ce que l'outil fait, et ce qu'il ne
fait pas », « Simulation », « Arrêter un lot en cours » et « Mots de passe »).

Indépendante de T9 et T10.

**Critère de fin, à la lettre** — deux `grep`, et deux seulement :

```bash
grep -n "déjà présent, ignoré" README.md   # doit rendre zéro ligne (aujourd'hui : 73, 107, 120)
grep -n "comptes ignorés" README.md        # doit rendre zéro ligne (aujourd'hui : 88)
```

Ce sont les quatre phrases qui décrivent un compte déjà présent comme entièrement ignoré,
comportement que la v2 abandonne. Les lignes 107 et 120 sont hors des sections que le plan
visait, d'où l'étape 4.

**Ne pas viser `grep -n "ignoré" README.md`** : la **l. 50** — « toute colonne en trop est
ignorée » — parle des colonnes du CSV, elle est exacte, la v2 n'y change rien et elle doit
rester. Un critère qui exigerait zéro occurrence du mot pousserait à abîmer une phrase juste
pour satisfaire un `grep`.

- [ ] **Étape 1 : réécrire le paragraphe de rapprochement**

Le texte actuel est faux sur trois points : « un compte déjà présent est classé « déjà
présent, ignoré » […] ses appartenances de groupe comprises », « Un groupe réclamé uniquement
par un compte déjà présent n'est donc pas créé », et « un compte présent sur le boîtier et
absent du CSV est **listé** comme orphelin ». Le remplacer par :

> il crée les comptes du CSV absents du boîtier et les groupes que les adhésions décrites
> réclament ; un compte déjà présent — reconnu quelle que soit sa casse, `Jean.Dupont` pour
> une ligne `jean.dupont` — n'est **ni modifié, ni supprimé**, et reçoit seulement les
> adhésions de groupe que le CSV lui donne et que le boîtier n'a pas. La colonne `groupes`
> vide ne veut pas dire « aucun groupe » mais « je ne me prononce pas » : aucune adhésion
> n'est ajoutée. Si le boîtier porte deux graphies d'un même nom que seule la casse distingue
> — deux comptes ou deux groupes —, l'outil ne choisit pas à votre place : il le signale, ne
> touche à rien pour ce nom-là, et poursuit le lot. Les comptes du boîtier absents du CSV sont
> **comptés** en une ligne, jamais nommés, et jamais touchés. L'outil **n'enlève rien** : aucun
> compte supprimé ni désactivé, aucune appartenance de groupe retirée, aucun attribut corrigé.

- [ ] **Étape 2 : mettre à jour « Simulation »**

« affiche le plan complet — comptes à créer, groupes à créer, comptes ignorés, orphelins »
devient « affiche le plan complet — ce qui arrive à chaque compte du fichier, les groupes à
créer, le nombre de comptes du boîtier absents du fichier ». La phrase sur la boîte de
confirmation gagne « le nombre d'adhésions à ajouter » à côté des comptes et des groupes neufs.

- [ ] **Étape 3 : ajouter le paragraphe du canari**

Sous « Ce que l'outil fait », une phrase qui dit à l'opérateur quoi faire de ce nombre :

> Si le journal annonce que des membres de groupes n'ont pas pu être reconnus, rien n'est
> cassé : l'outil renverra simplement les mêmes rattachements à chaque exécution, que le
> firewall absorbera ou refusera. Signalez ce nombre — c'est le seul signal qui dise que la
> forme des membres rendus par le firewall n'est pas celle que l'outil attend.

- [ ] **Étape 4 : les deux occurrences hors périmètre, et la section « État »**

Trois phrases restent fausses en dehors des sections ci-dessus :

- **l. 106-107**, « Arrêter un lot en cours » : « Relancer le même CSV est sans danger : les
  comptes créés seront classés « déjà présent, ignoré ». » → « …seront vus comme déjà
  présents : ils ne seront ni modifiés ni recréés, et ne recevront que les adhésions de
  groupe que le CSV leur donne et que le firewall n'a pas. »
- **l. 118-120**, « Mots de passe » : « le compte existe sur le boîtier, il n'a pas de mot de
  passe utilisable, et aucun relancement ne le réparera — il sera classé « déjà présent,
  ignoré ». » → remplacer la fin par « — il sera vu comme déjà présent, et son mot de passe
  ne sera jamais retouché. » C'est le point le plus important à ne pas affaiblir : la v2
  écrit sur des comptes existants, et cette phrase est ce qui dit à l'opérateur que le mot de
  passe, lui, reste hors d'atteinte.
- **l. 11**, « État » : « La v1 couvre l'injection d'utilisateurs… » — ajouter une phrase
  disant que la v2 y ajoute la reconnaissance des comptes et groupes déjà présents, quelle
  que soit leur casse, et l'ajout des adhésions manquantes.

- [ ] **Étape 5 : commit**

```bash
git add README.md && git commit -m "docs: README aligné sur le rapprochement de la v2"
```

---

### Tâche 9 : le cahier de recette

**Fichiers :** Modifier `docs/recette/2026-09-16-cahier-recette-v1.md`.

**Tranché : on étend le cahier existant, on n'en ouvre pas un second.** Motif : la v2 ne
s'ajoute pas à la v1, elle **rend faux douze** cas déjà numérotés (23, 26, 27, 35, 50, 51, 52,
56, 70, 83, 118, 119). Un cahier v2 séparé laisserait un cahier v1 mensonger à côté de lui, et
un humain en recette jouerait les deux. Le fichier n'est pas renommé — la numérotation et les tables de
traçabilité y renvoient — mais son titre devient
`# Cahier de recette — injection d'utilisateurs LDAP (v1 et v2)`, avec une ligne de chapeau
disant que les cas marqués *(v2)* remplacent l'attendu d'origine.

Indépendante de T8 et T10.

- [ ] **Étape 1 : corriger en place les douze cas rendus faux**

Chacun garde son numéro et son intitulé ; seul l'*Attendu* change, suivi de la mention
*(v2)*. `grep -n "déjà présent, ignoré" docs/recette/2026-09-16-cahier-recette-v1.md` doit
rendre **zéro ligne** à la fin de l'étape — six cas portent la formule, les autres une
promesse que la v2 contredit :

| Cas | Ce qui devient faux | Nouvel attendu |
|---|---|---|
| 23 | « 4 / 4 », « une simulation ne compte que ses quatre lectures » | `4 + g / 4 + g`, où `g` est le nombre de groupes du CSV déjà présents sur le boîtier ; pour `lot-nominal.csv` sur un boîtier vierge, `g = 0` |
| 26 | « le compte est listé « déjà présent, ignoré » », « `fantome-recette` n'existe toujours pas » | le groupe **est** créé et le compte existant **y est rattaché** : la liste des groupes à créer se calcule sur toutes les adhésions. Le compte reste inchangé par ailleurs |
| 27 | « le journal porte « Orphelins sur le boîtier : … , temoin.recette, … » » | le journal porte « N comptes du boîtier ne figurent pas dans le fichier : ils ne seront pas touchés. » et **aucun nom d'orphelin** |
| 35 | « les 2 comptes déjà présents sont annoncés « déjà présent, ignoré » », « la ligne « Orphelins sur le boîtier : … » liste » | « présent — rien à faire » ou « présent — ajouté à … », et le **nombre** d'orphelins non nul. KO caractéristique inchangé : tout « à créer » et zéro orphelin |
| 50 | « chaque compte figure dans **exactement** les groupes que le CSV lui donnait, et dans aucun autre » | « figure dans **au moins** les groupes que le CSV lui donnait » : l'outil n'enlève rien, une adhésion préexistante hors CSV subsiste |
| 51 | « les 3 comptes tombent en « déjà présent, ignoré » », « la barre affiche « 4 / 4 » » | « présent — rien à faire » pour les trois, **zéro commande d'écriture**, barre `4 + g / 4 + g` |
| 52 | « tout est « déjà présent, ignoré » » | « tout est « présent — rien à faire » » |
| 56 | « le total vaut **4 lectures** + … » | « le total vaut **4 + g lectures** + 1 par groupe neuf + 2 par compte à créer + 1 par adhésion », et il **croît une fois**, juste après la confirmation |
| 70 (l. 776) | la boîte d'avertissement « dit que les comptes resteront créés et seront classés « déjà présent, ignoré » » | « …resteront créés et seront vus comme déjà présents, sans que leur mot de passe soit retouché ». Le reste du cas — 3 mots de passe annoncés, bouton « Non » présélectionné — est inchangé |
| 83 (l. 909) | « les comptes déjà créés tombent en « déjà présent, ignoré » » | « les comptes déjà créés sont vus comme présents — « présent — rien à faire », ou « présent — ajouté à … » si le CSV leur donne un groupe qu'ils n'ont pas ». Le reste — 200 comptes, chacun une fois, aucun échec « existe déjà » — est inchangé |
| 118 (l. 1320) | « les N comptes du premier lot tombent en « **déjà présent, ignoré** » » | même correction qu'au cas 83 ; la promesse du bilan (« relancer est sans danger ») reste ce que le cas vérifie |
| 119 | « Cette fenêtre vaut quatre commandes » | « Cette fenêtre vaut `4 + g` commandes » ; ajouter que le clic pendant la lecture des adhésions est un point d'arrêt à part entière |

- [ ] **Étape 2 : écrire la section R, cas 122 à 139**

Nouvelle section `# R. Boîtier déjà peuplé (v2)`, cas 122 à 139, insérée **après** la section Q
et **avant** le récapitulatif, numérotée à la suite pour ne décaler aucun renvoi existant. Format
identique aux cas existants (`**N — Titre** · boîtier : oui`, puis *Objectif*, *Départ*,
*Actions*, *Attendu*, *Verdict*).

| Cas | Titre | Ce qu'il prouve |
|---|---|---|
| 122 | Le compteur des membres non rattachés | **à jouer en premier au premier boîtier joignable**, avant même de juger l'idempotence : n'importe quel CSV citant un groupe peuplé ; attendu `0`, quel que soit le contenu du CSV — les membres se comparent aux comptes du boîtier, pas au fichier. Non nul = l'hypothèse sur le DN est fausse en tout ou partie |
| 123 | Forme réelle de la réponse de `USER GROUP SHOW` | relever la réponse brute sur un groupe à deux membres ; confirmer la section `[Group]` et les champs `member=`, `member_2=` porteurs de DN |
| 124 | `USER GROUP SHOW` sur un groupe sans membre | section vide ou refus : les deux doivent donner « aucun membre » et le lot doit continuer |
| 125 | Un compte créé à la main sous `Jean.Dupont` | la ligne `jean.dupont` ne le recrée pas ; toutes les commandes le visent sous `Jean.Dupont` |
| 126 | Une adhésion ajoutée à un compte déjà présent | le compte existant entre dans le groupe du CSV ; ses autres appartenances sont intactes |
| 127 | Colonne `groupes` vide sur un compte présent | aucune adhésion ajoutée, aucune retirée, aucune écriture pour ce compte |
| 128 | Un groupe `Compta` reconnu par une ligne `compta` | aucun groupe créé en double ; l'`ADDUSER` vise `Compta` |
| 129 | Collision de casse entre deux groupes | `Compta` et `compta` sur le boîtier, CSV portant `COMPTA` : le journal signale, aucun compte n'y est rattaché, **le lot continue** pour les autres |
| 130 | Collision levée par une correspondance exacte | CSV portant `compta` : c'est `compta` qui est visé, sans signalement |
| 131 | Lecture à `4 + g` commandes | CSV citant 5 groupes dont 3 présents : 7 commandes de lecture, pas 9, pas 4 |
| 132 | Arrêt pendant la lecture des adhésions | sur un boîtier à nombreux groupes cités, cliquer *Arrêter* pendant la lecture : bilan d'arrêt, **aucun plan affiché**, aucune écriture |
| 133 | Idempotence : seconde exécution sans aucune écriture | relancer le même CSV sur le boîtier laissé par le cas 49 : « rien à faire » partout, zéro écriture, dates de modification inchangées |
| 134 | Le mot de passe d'un compte existant n'est jamais touché | se connecter avec un compte existant avant et après le lot : le mot de passe d'origine fonctionne toujours |
| 135 | La confirmation annonce les adhésions | la boîte nomme l'hôte, les comptes à créer, les groupes neufs **et** le nombre d'adhésions, et promet qu'aucun retrait n'aura lieu |
| 136 | `USER GROUP ADDUSER` refusé | provoquer un refus sur une adhésion : signalé au rapport, lot poursuivi, comptes suivants créés |
| 137 | Reprise après coupure pendant les rattachements | couper la liaison entre deux `ADDUSER` : après reconnexion, l'inventaire des adhésions est relu et les rattachements restants sont replanifiés, sans doublon au rapport |
| 138 | Collision de casse entre deux comptes | `Jean.Dupont` et `JEAN.DUPONT` sur le boîtier, CSV portant `jean.dupont` : le journal signale, **rien n'est fait à ce compte** — ni création, ni adhésion, ni mot de passe —, les deux graphies sont intactes et le lot continue pour les autres |
| 139 | Collision de comptes levée par une correspondance exacte | `Jean.Dupont` et `jean.dupont` sur le boîtier, CSV portant `jean.dupont` — l'identifiant du fichier est toujours en minuscules : c'est `jean.dupont` qui est visé, sans signalement |

- [ ] **Étape 3 : mettre à jour le récapitulatif et la traçabilité**

- Ajouter au tableau : `| R — Boîtier déjà peuplé (v2) | 122 – 139 | **oui** |`.
- Les deux lignes de synthèse de fin de fichier (l. 1388-1390) deviennent : **22 cas sans
  boîtier** (inchangé), **117 cas exigeant un boîtier**, **139 cas au total**.
- **Les mêmes compteurs vivent en tête du fichier**, § « Comment s'en servir »
  (l. 26-28) : « 99 cas » devient **117 cas**, « **121 cas au total.** » devient
  **139 cas au total.** Les laisser en l'état donnerait un cahier qui se contredit à deux
  pages d'intervalle, et c'est la tête que l'humain en recette lit en premier. Vérification :
  `grep -n "121 cas\|99 cas" docs/recette/2026-09-16-cahier-recette-v1.md` doit rendre zéro
  ligne à la fin de l'étape.
- Sous « Traçabilité », ajouter une correspondance en prose **spec v2 → cas**, sur le modèle
  des correspondances existantes : casse des comptes → 125 ; casse des groupes → 128 ;
  collision de groupes → 129, 130 ; collision de comptes → 138, 139 ; colonne vide → 127 ;
  membres non rattachés → 122 ; `4 + g` → 131 ; arrêt entre deux lectures → 132 ;
  idempotence → 133 ; mot de passe structurel → 134 ; confirmation → 135 ; échec isolé → 136 ;
  reprise → 137 ; hypothèses SDK → 123, 124.
- Sous « Points devenus caducs », ajouter les douze attendus v1 corrigés à l'étape 1, avec
  leur numéro et le motif en une ligne.

- [ ] **Étape 4 : commit**

```bash
git add docs/recette/2026-09-16-cahier-recette-v1.md
git commit -m "docs: cahier de recette étendu à la v2, douze attendus v1 corrigés"
```

---

### Tâche 10 : `KANBAN.md`

**Fichiers :** Modifier `KANBAN.md`.

Indépendante de T8 et T9.

- [ ] **Étape 1 : écrire l'entrée datée**

En tête de la section `## Terminé`, avant « Arrêt d'un lot en cours (2026-09-17) » :

```markdown
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
```

- [ ] **Étape 2 : redresser l'invariant de `## Décisions actées`**

`KANBAN.md:22-23` porte encore l'invariant v1 : « Ajout seul : jamais de suppression, jamais
de modification d'un compte existant. Les orphelins sont signalés, pas touchés. » La v2 en
abandonne la moitié — elle ajoute des adhésions à un compte existant. C'est la seule section
du fichier qu'un lecteur consulte pour connaître les invariants **courants** ; l'entrée datée
de l'étape 1 ne la corrige pas, un journal ne se relit pas pour cela. Remplacer ces deux
lignes par :

```markdown
- Ajout seul : jamais de suppression, jamais de retrait d'appartenance. Un compte
  existant n'est ni supprimé, ni désactivé, ni modifié dans ses attributs, et son mot
  de passe reste hors d'atteinte ; depuis la v2 il reçoit les adhésions de groupe que
  le fichier lui donne et que le boîtier n'a pas. Les orphelins sont signalés, pas
  touchés.
```

**Rien d'autre dans le journal ne se réécrit** : les entrées datées de `## Terminé` — dont
`KANBAN.md:85`, « quatre commandes quel que soit le CSV » — disent ce qui était vrai à leur
date et restent telles quelles.

- [ ] **Étape 3 : compléter « Points à lever dès qu'un boîtier est joignable »**

Trois entrées, dans cet ordre de priorité :

```markdown
- **La forme des membres rendus par `USER GROUP SHOW`** — seul point structurant de la
  v2. Le nombre de membres non rattachés affiché au plan la confirme ou l'infirme dès la
  première lecture : il vaut **zéro sur un boîtier sain**, les membres se comparant aux
  comptes du boîtier et non au fichier (cahier de recette, cas 122, à jouer en premier).
  Faux : l'outil réémet des `ADDUSER` redondants, sans dommage, et le repli tient dans
  `uid_du_dn`.
- **La forme rendue par `USER GROUP LIST`** — nom de groupe ou DN. Elle sert désormais
  d'argument à `USER GROUP SHOW`.
- **La coexistence de deux groupes — ou de deux comptes — que la casse seule distingue.**
  Si elle est possible, la collision est signalée sans correspondance exacte, et ni le
  groupe ni le compte en cause n'est touché (cas 129 et 138).
```

- [ ] **Étape 4 : ajouter les pièges rencontrés**

Si l'exécution du plan en a rencontré, les consigner en fin de fichier au format
`- (2026-09-17) **Titre** : description`. Sinon, ne rien ajouter — un journal qui invente
des pièges ne sert plus à rien.

- [ ] **Étape 5 : commit**

```bash
git add KANBAN.md && git commit -m "docs: KANBAN — entrée v2, points à lever au premier boîtier"
```

---

## Ce que le plan ne fait pas, et pourquoi

- **Aucun retrait**, sous aucune forme : `USER REMOVE`, `USER GROUP DELUSER`,
  `USER GROUP REMOVEFROM`, `USER UPDATE`, `CONFIG PASSWDPOLICY SET` n'entrent pas dans
  l'outil. Le coût de lecture d'un retrait sûr n'est pas payé.
- **Aucun signalement de divergence d'attributs** : il exigeait un `USER SHOW` par compte,
  que le périmètre resserré supprime. `USER LIST` ne rend que des identifiants.
- **Aucun changement au contrat du CSV**, aux motifs de rejet, à la génération et à la
  restitution des mots de passe, à l'annuaire LDAP, au certificat, à l'empaquetage : la v1
  fait autorité sur tout cela et rien n'y touche.
- **Aucun changement de câblage dans `fenetre.py`** : une seule docstring y est corrigée.
- **Aucune blacklist** : groupes d'objets réseau et d'URL restent la suite prévue du dépôt.

## Points d'attention pour qui relit le résultat

1. **Le compteur des membres non rattachés se compare aux comptes du boîtier, jamais à ceux du
   fichier.** Un membre légitime qu'un CSV du jour ne cite pas n'y compte donc pas : le
   compteur vaut **zéro sur un boîtier sain**, quel que soit le contenu du fichier, et ne porte
   aucun bruit. C'est ce qui le rend lisible — une forme de DN inattendue le fait bondir d'un
   coup. Un compteur comparé au fichier afficherait un nombre élevé en fonctionnement
   parfaitement normal, et le signal se noierait dans le bruit qu'il doit détecter.
2. **Un groupe ambigu n'est pas interrogé**, donc il ne compte pas dans `g`. Il ne sera touché
   pour aucun compte : lire ses membres n'apprendrait rien.
3. **Un compte ambigu** (deux graphies sur le boîtier que la clé confond) suit exactement la
   règle des groupes : correspondance exacte avec l'identifiant du fichier, c'est ce compte-là ;
   sinon il est **signalé et rien ne lui est fait** — ni création, ni adhésion, ni mot de passe
   —, et le lot continue. Trancher sur la première graphie rendue serait arbitraire : l'ordre
   de la liste rendue par le boîtier n'est garanti par rien, et deux exécutions pourraient
   écrire sur deux comptes différents. Une seule règle pour les deux rapprochements, et aucun
   concept nouveau dans le produit : c'est le signalement non destructeur et non bloquant déjà
   en place pour les échecs isolés.
4. **La relecture qui suit une reconnexion ne consulte pas l'arrêt demandé** : la spec fixe
   quatre points d'arrêt et quatre seulement. Conséquence assumée : pendant une relecture de
   `g` commandes, le bouton *Arrêter* ne mord pas — la fenêtre est courte, et ajouter un
   cinquième point d'arrêt serait ajouter une règle que la spec n'a pas écrite.
5. **Un membre non rattaché ne retire jamais une adhésion planifiée.** Il est compté, et rien
   d'autre : son `uid` n'entre pas dans l'ensemble des adhésions réputées existantes. Sans
   cette précaution, un DN illisible désignant en réalité un compte du fichier ferait naître
   ce compte **sans** le groupe que le CSV lui donne — une action, là où la spec en interdit
   une. C'est `test_un_membre_non_rattache_ne_supprime_aucune_adhesion_planifiee` (T4) qui
   verrouille ce point.
6. **Le rapport porte deux échecs `USER GROUP ADDUSER` quand un refus précède une coupure**,
   et c'est correct : le refus du boîtier et la trace de l'interruption sont deux faits
   distincts. Ce que la spec interdit, c'est qu'un **même** refus reparte au tour suivant — ce
   que prouve le compte des appels sur le groupe refusé, pas le compte des échecs.
7. **La ligne des orphelins ne s'affiche pas quand le nombre est nul** (voir l'arbitrage écrit
   en T6, étape 3). Un journal sans cette ligne dit zéro ; une ligne « 0 compte » au-dessus du
   plan est du bruit.
8. **L'arrêt demandé a désormais deux récits, parce qu'il a deux moments.** Avant le plan, le
   journal (T5) et le bilan (T6) ne parlent ni d'un compte mené à son terme, ni de ce qui
   restait à créer : rien n'avait été entamé, rien n'avait été compté. `Rapport.plan_construit`
   porte cette distinction — `comptes_prevus == 0` ne la porte pas, il vaut zéro dans les deux
   cas. Le chemin historique, lui, rend exactement les textes de la v1.
