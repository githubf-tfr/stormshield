# Injection d'utilisateurs LDAP (v1) — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** livrer un `.exe` Windows à fenêtre unique qui crée en lot, à partir d'un CSV, les comptes et groupes absents de la base LDAP interne d'un firewall Stormshield SNS, sans jamais modifier l'existant.

**Architecture :** tout le métier est pur et se teste hors ligne ; la seule frontière réseau est le `Protocol` `Boitier`, doublé en test par `BoitierMemoire`. La décision (`plan.py`) ne sait pas écrire, l'écriture (`execution.py`) ne décide rien, et la fenêtre ne fait que câbler : elle lance l'exécution dans un thread qui ne touche aucun widget et publie ses événements dans une `queue`, vidée par `after()`.

**Tech Stack :** Python ≥ 3.11, bibliothèque standard (`csv`, `secrets`, `tkinter`, `queue`, `threading`), SDK `stormshield.sns.sslclient`, pytest / ruff / mypy, PyInstaller via GitHub Actions.

**Spec :** `docs/superpowers/specs/2026-09-16-injection-utilisateurs-design.md` — elle fait autorité, ce plan ne fait que l'ordonner. En cas de divergence, la spec gagne et le plan est corrigé.

## Contraintes globales

Elles s'appliquent à **toutes** les tâches, sans être répétées dans chacune.

- **Français dans le code** : noms de modules, de fonctions, de variables, docstrings, commentaires, messages destinés à l'opérateur. Apostrophes droites (`'`) dans les chaînes et docstrings, jamais `’`.
- **TDD strict** : le test est écrit et **exécuté en échec** avant l'implémentation. Un test qui passe du premier coup est un test à revoir.
- **Aucun firewall joignable.** Aucun test hors marqueur `firewall` n'ouvre une socket. Tout ce qui parle au boîtier passe par le `Protocol` `Boitier`.
- **Analyse statique avant tout commit** : `ruff check .` puis `mypy`, tous deux configurés dans `pyproject.toml` (tâche 1) et en service dès la tâche 1. Un commit dont l'un des deux échoue n'est pas fait.
- **Ajout seul** : aucune suppression, aucune modification d'un compte ou d'un groupe existant, jamais, dans aucun module.
- **Aucun secret dans le repo** : ni identifiant, ni mot de passe, ni `.env`, ni CSV de mots de passe. Les fixtures de test utilisent des valeurs manifestement factices.
- **Aucune écriture sur disque** hors du CSV de mots de passe à un emplacement désigné par l'opérateur. Pas de fichier de journal, pas de fichier d'état local.
- Commandes SNS autorisées, et aucune autre : `USER LIST`, `USER GROUP LIST`, `USER CREATE`, `USER PASSWORD`, `USER GROUP CREATE`, `USER GROUP ADDUSER`, `CONFIG PASSWDPOLICY SHOW`, `CONFIG LDAP LIST`, `CONFIG LDAP INITIALIZE`, `CONFIG LDAP ACTIVATE`.
- Messages de commit : Conventional Commits, type en anglais, corps en français (`feat: lecture du CSV d'entrée`).

## Disposition des fichiers

| Fichier | Responsabilité |
|---|---|
| `pyproject.toml` | métadonnées, dépendances, configuration `ruff` / `mypy` / `pytest` |
| `stormshield_utilisateurs/__init__.py` | paquet, vide |
| `stormshield_utilisateurs/modele.py` | dataclasses partagées, aucune logique |
| `stormshield_utilisateurs/lecture.py` | CSV → (utilisateurs valides, rejets). Pur |
| `stormshield_utilisateurs/motdepasse.py` | génération et validation contre le plancher. Pur |
| `stormshield_utilisateurs/boitier.py` | `Protocol` `Boitier` + exceptions du dialogue |
| `stormshield_utilisateurs/boitier_memoire.py` | implémentation en mémoire du `Protocol`, support de tous les tests |
| `stormshield_utilisateurs/boitier_sdk.py` | adaptateur `stormshield.sns.sslclient`, **seul** module à l'importer |
| `stormshield_utilisateurs/plan.py` | état boîtier + lignes valides → `Plan`. Pur, n'écrit rien |
| `stormshield_utilisateurs/execution.py` | lecture d'état, application du `Plan`, réessais, événements |
| `stormshield_utilisateurs/sortie.py` | CSV des mots de passe des comptes créés |
| `stormshield_utilisateurs/fenetre.py` | tkinter, une fenêtre, câblage |
| `stormshield_utilisateurs/__main__.py` | point d'entrée, cible PyInstaller |
| `tests/test_*.py` | un fichier par module métier |
| `.github/workflows/qualite.yml` | ruff + mypy + pytest à chaque poussée |
| `.github/workflows/exe.yml` | PyInstaller sur tag `v*`, release GitHub |
| `docs/recette/2026-09-16-cahier-recette-v1.md` | cahier de recette fonctionnel |

**Écart de forme assumé par rapport au tableau des modules de la spec :** la spec loge le `Protocol` et l'implémentation SDK dans `boitier.py`. Le plan les sépare en `boitier.py` (Protocol, exceptions) et `boitier_sdk.py` (adaptateur), pour que la totalité des tests métier importe la frontière sans tirer la surface non prouvée. Les rôles décrits par la spec sont inchangés ; `boitier_sdk.py` reste le seul module à importer `stormshield.sns.sslclient`.

## Ordre des tâches et dépendances

```
1 amorçage
├─ 2 modele
│  ├─ 3 lecture          (pur)
│  ├─ 4 motdepasse       (pur)
│  ├─ 5 boitier + BoitierMemoire
│  │  ├─ 6 plan          (pur, consomme 2 et l'état lu)
│  │  ├─ 7 execution — lecture d'état et annuaire
│  │  ├─ 8 execution — écritures, réessais, reconnexion  (dépend de 4, 6, 7)
│  │  └─ 10 boitier_sdk  (marqueur firewall, prouvé par rien)
│  └─ 9 sortie           (pur)
└─ 11 fenetre + __main__ (câble 3, 4, 7, 8, 9)
   └─ 12 empaquetage, README, cahier de recette
```

Les tâches 3, 4, 5 et 9 sont indépendantes entre elles et peuvent être dispatchées en parallèle une fois la 2 close. La 10 peut se faire à tout moment après la 5.

---

## Task 1: Amorçage du projet et garde-fous de qualité

**Files:**
- Create: `pyproject.toml`
- Create: `stormshield_utilisateurs/__init__.py`
- Create: `tests/test_amorcage.py`
- Create: `.github/workflows/qualite.yml`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: rien.
- Produces: les commandes `ruff check .`, `mypy`, `pytest` ; le marqueur pytest `firewall` exclu par défaut ; le paquet importable `stormshield_utilisateurs`.

- [ ] **Step 1: Créer le squelette du paquet et des tests**

```bash
mkdir -p stormshield_utilisateurs tests .github/workflows
touch stormshield_utilisateurs/__init__.py
```

`stormshield_utilisateurs/__init__.py` contient une seule ligne :

```python
"""Injection en lot d'utilisateurs dans la base LDAP interne d'un firewall Stormshield SNS."""
```

- [ ] **Step 2: Écrire `pyproject.toml`**

```toml
[project]
name = "stormshield-utilisateurs"
version = "1.0.0"
description = "Injection en lot d'utilisateurs LDAP sur firewall Stormshield SNS"
requires-python = ">=3.11"
dependencies = ["stormshield.sns.sslclient>=1.4"]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6", "mypy>=1.11", "pyinstaller>=6.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools]
packages = ["stormshield_utilisateurs"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "N", "SIM", "ARG", "PTH", "RUF"]
# RUF001-003 signalent les caractères Unicode ambigus : le code est en français et
# les accents ne doivent pas être traités comme des anomalies.
ignore = ["RUF001", "RUF002", "RUF003"]

[tool.mypy]
python_version = "3.11"
files = ["stormshield_utilisateurs", "tests"]
strict = true

# Le SDK Stormshield ne publie pas de stubs.
[[tool.mypy.overrides]]
module = ["stormshield.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
# Le marqueur firewall exige un boîtier joignable : exclu par défaut, `pytest -m firewall`
# le rappelle explicitement (le -m de la ligne de commande écrase celui-ci).
addopts = "-m 'not firewall'"
markers = ["firewall: exige un boîtier SNS joignable, exclu par défaut"]
```

- [ ] **Step 3: Compléter `.gitignore`**

Ajouter à la fin du fichier existant :

```
build/
dist/
*.spec
.mypy_cache/
.pytest_cache/
.ruff_cache/
# CSV de mots de passe : ne doit jamais entrer dans le repo, même par mégarde.
mots_de_passe*.csv
```

- [ ] **Step 4: Écrire le test d'amorçage (il doit échouer)**

`tests/test_amorcage.py` :

```python
"""Vérifie que le paquet est importable et que le marqueur firewall est bien exclu."""

import pytest

import stormshield_utilisateurs


def test_le_paquet_est_importable() -> None:
    assert stormshield_utilisateurs.__doc__ is not None


def test_le_marqueur_firewall_est_exclu_par_defaut() -> None:
    """Ce test échoue si un jour le marqueur cesse d'être exclu par addopts."""
    import subprocess
    import sys

    resultat = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "test_exige_un_boitier" not in resultat.stdout


@pytest.mark.firewall
def test_exige_un_boitier() -> None:
    """Sentinelle : collectée seulement avec `pytest -m firewall`."""
    raise AssertionError("ce test ne doit jamais tourner sans boîtier")
```

- [ ] **Step 5: Installer et faire échouer**

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
```
Attendu : échec — le paquet n'est pas encore installé / le fichier `__init__.py` est vide de docstring si l'étape 1 a été sautée. Corriger jusqu'à ce que l'échec soit **uniquement** celui attendu.

- [ ] **Step 6: Faire passer et vérifier les trois commandes**

```bash
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/pytest -q
```
Attendu : trois succès, 2 tests passés, 1 dé-sélectionné.

- [ ] **Step 7: Écrire `.github/workflows/qualite.yml`**

```yaml
name: qualite

on:
  push:
  pull_request:

jobs:
  qualite:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e '.[dev]'
      - run: ruff check .
      - run: mypy
      # Le marqueur firewall est déjà exclu par addopts ; répété ici pour que le
      # workflow dise lui-même ce qu'il ne prouve pas.
      - run: pytest -m "not firewall" -q
```

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore stormshield_utilisateurs tests .github
git commit -m "chore: amorcer le paquet, ruff, mypy, pytest et le workflow qualite"
```

**Fini quand :** `ruff check .`, `mypy` et `pytest -q` passent en local, le workflow `qualite.yml` est committé, et `pytest -m firewall --collect-only` collecte la sentinelle que la passe par défaut ignore.

---

## Task 2: Modèle de données

**Files:**
- Create: `stormshield_utilisateurs/modele.py`
- Test: `tests/test_modele.py`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `Utilisateur(ligne: int, identifiant: str, identifiant_origine: str, nom: str, prenom: str, groupes: tuple[str, ...])`, propriété `bascule_minuscules -> bool`
  - `Rejet(ligne: int, identifiant: str, motif: str)`
  - `PlancherPolitique(longueur_min: int, nombre_classes_min: int, entropie_min: int)`
  - `PolitiqueMotDePasse(longueur: int, minuscules: bool, majuscules: bool, chiffres: bool, speciaux: bool)`, méthode `nombre_classes() -> int`
  - `EtatBoitier(domaine: str, plancher: PlancherPolitique, utilisateurs: frozenset[str], groupes: frozenset[str])`
  - `GroupeACreer(nom: str, nombre_membres: int)`
  - `Plan(comptes_a_creer, comptes_ignores, groupes_a_creer, orphelins, domaine)`, méthodes `nombre_operations() -> int`
  - `CompteCree(identifiant: str, mot_de_passe: str)`
  - `Echec(identifiant: str, operation: str, motif: str)`
  - `Rapport(comptes_crees: list[CompteCree], echecs: list[Echec], groupes_crees: list[str], interrompu: bool)`, propriété `sans_mot_de_passe -> list[CompteCree]`

- [ ] **Step 1: Écrire les tests de comportement du modèle**

`tests/test_modele.py` :

```python
"""Comportements portés par le modèle : ils sont peu nombreux mais chacun est une règle."""

from stormshield_utilisateurs.modele import (
    GroupeACreer,
    CompteCree,
    Echec,
    Plan,
    PolitiqueMotDePasse,
    Rapport,
    Utilisateur,
)


def _utilisateur(identifiant: str, *groupes: str, origine: str | None = None) -> Utilisateur:
    return Utilisateur(
        ligne=2,
        identifiant=identifiant,
        identifiant_origine=origine if origine is not None else identifiant,
        nom="Dupont",
        prenom="Marie",
        groupes=groupes,
    )


def test_bascule_minuscules_signalee_quand_le_fichier_differe() -> None:
    assert _utilisateur("jean.dupont", origine="Jean.Dupont").bascule_minuscules is True
    assert _utilisateur("jean.dupont").bascule_minuscules is False


def test_nombre_de_classes_de_la_politique() -> None:
    politique = PolitiqueMotDePasse(
        longueur=16, minuscules=True, majuscules=True, chiffres=True, speciaux=False
    )
    assert politique.nombre_classes() == 3


def test_nombre_d_operations_du_plan() -> None:
    """1 groupe + (USER CREATE + USER PASSWORD + 2 ADDUSER) + (USER CREATE + USER PASSWORD)."""
    plan = Plan(
        comptes_a_creer=(_utilisateur("dupont", "compta", "rh"), _utilisateur("legrand")),
        comptes_ignores=(),
        groupes_a_creer=(GroupeACreer(nom="compta", nombre_membres=1),),
        orphelins=(),
        domaine="interne.local",
    )
    assert plan.nombre_operations() == 1 + 4 + 2


def test_comptes_sans_mot_de_passe_isoles_dans_le_rapport() -> None:
    rapport = Rapport(
        comptes_crees=[CompteCree("dupont", "Abc123!x"), CompteCree("legrand", "")],
        echecs=[Echec("legrand", "USER PASSWORD", "code 200")],
        groupes_crees=["compta"],
        interrompu=False,
    )
    assert [compte.identifiant for compte in rapport.sans_mot_de_passe] == ["legrand"]
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_modele.py -q`
Attendu : `ModuleNotFoundError: No module named 'stormshield_utilisateurs.modele'`.

- [ ] **Step 3: Écrire `modele.py`**

```python
"""Structures de données partagées. Aucune logique de décision, aucun accès réseau."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Utilisateur:
    """Une ligne de CSV validée. `ligne` est un numéro d'enregistrement (en-tête = 1)."""

    ligne: int
    identifiant: str
    identifiant_origine: str
    nom: str
    prenom: str
    groupes: tuple[str, ...]

    @property
    def bascule_minuscules(self) -> bool:
        """Vrai si l'identifiant créé diffère de celui écrit dans le fichier."""
        return self.identifiant != self.identifiant_origine


@dataclass(frozen=True)
class Rejet:
    ligne: int
    identifiant: str
    motif: str


@dataclass(frozen=True)
class PlancherPolitique:
    """Politique lue sur le boîtier. L'opérateur peut durcir, jamais descendre en dessous."""

    longueur_min: int
    nombre_classes_min: int
    entropie_min: int


@dataclass(frozen=True)
class PolitiqueMotDePasse:
    """Réglage de génération choisi par l'opérateur."""

    longueur: int
    minuscules: bool = True
    majuscules: bool = True
    chiffres: bool = True
    speciaux: bool = True

    def nombre_classes(self) -> int:
        return sum([self.minuscules, self.majuscules, self.chiffres, self.speciaux])


@dataclass(frozen=True)
class EtatBoitier:
    """Ce que la phase de lecture rapporte du boîtier. Lecture seule."""

    domaine: str
    plancher: PlancherPolitique
    utilisateurs: frozenset[str]
    groupes: frozenset[str]


@dataclass(frozen=True)
class GroupeACreer:
    nom: str
    nombre_membres: int


@dataclass(frozen=True)
class Plan:
    comptes_a_creer: tuple[Utilisateur, ...]
    comptes_ignores: tuple[Utilisateur, ...]
    groupes_a_creer: tuple[GroupeACreer, ...]
    orphelins: tuple[str, ...]
    domaine: str

    def nombre_operations(self) -> int:
        """Écritures prévues : un USER GROUP CREATE par groupe, puis par compte
        un USER CREATE, un USER PASSWORD et un USER GROUP ADDUSER par groupe."""
        return len(self.groupes_a_creer) + sum(
            2 + len(compte.groupes) for compte in self.comptes_a_creer
        )


@dataclass(frozen=True)
class CompteCree:
    """`mot_de_passe` est vide quand USER PASSWORD a échoué malgré les réessais."""

    identifiant: str
    mot_de_passe: str


@dataclass(frozen=True)
class Echec:
    identifiant: str
    operation: str
    motif: str


@dataclass
class Rapport:
    comptes_crees: list[CompteCree] = field(default_factory=list)
    echecs: list[Echec] = field(default_factory=list)
    groupes_crees: list[str] = field(default_factory=list)
    interrompu: bool = False

    @property
    def sans_mot_de_passe(self) -> list[CompteCree]:
        """Comptes créés à reprendre à la main : un relancement ne les corrigera pas."""
        return [compte for compte in self.comptes_crees if not compte.mot_de_passe]
```

- [ ] **Step 4: Vérifier que tout passe**

```bash
.venv/bin/pytest tests/test_modele.py -q && .venv/bin/ruff check . && .venv/bin/mypy
```
Attendu : 4 tests passés, ruff et mypy silencieux.

- [ ] **Step 5: Commit**

```bash
git add stormshield_utilisateurs/modele.py tests/test_modele.py
git commit -m "feat: modele de donnees partage"
```

**Fini quand :** les quatre tests passent et `mypy --strict` accepte le module.

---

## Task 3: Lecture et validation du CSV

**Files:**
- Create: `stormshield_utilisateurs/lecture.py`
- Test: `tests/test_lecture.py`

**Interfaces:**
- Consumes: `modele.Utilisateur`, `modele.Rejet`.
- Produces:
  - `COLONNES_ATTENDUES: tuple[str, ...] = ("identifiant", "nom", "prenom", "groupes")`
  - `class ColonnesManquantes(Exception)` avec attribut `colonnes: tuple[str, ...]` ; son `str()` nomme les colonnes.
  - `def lire(chemin: Path) -> tuple[list[Utilisateur], list[Rejet]]`
  - `def lire_texte(contenu: str) -> tuple[list[Utilisateur], list[Rejet]]` — le cœur, testé directement ; `lire` décode puis délègue.
  - `def decoder(octets: bytes) -> str`

**Comportements subtils à ne pas aplatir** — chacun a son test nommé ci-dessous : bascule en minuscules signalée, doublon détecté **après** bascule et rejetant **les deux** lignes, colonne manquante faisant échouer le **fichier entier**, numéros d'enregistrement (en-tête = 1), cascade d'encodages.

- [ ] **Step 1: Écrire les tests de structure et d'encodage**

`tests/test_lecture.py` (début) :

```python
"""Le CSV est la seule entrée de l'outil : chaque règle de la spec a son test."""

from pathlib import Path

import pytest

from stormshield_utilisateurs.lecture import ColonnesManquantes, decoder, lire, lire_texte

EN_TETE = "identifiant;nom;prenom;groupes\n"


def test_colonne_manquante_fait_echouer_le_fichier_entier() -> None:
    """Pas de rejet ligne à ligne : on n'injecte rien et on nomme la colonne absente."""
    contenu = "identifiant;nom;groupes\ndupont;Dupont;compta\n"
    with pytest.raises(ColonnesManquantes) as erreur:
        lire_texte(contenu)
    assert erreur.value.colonnes == ("prenom",)
    assert "prenom" in str(erreur.value)


def test_colonnes_dans_n_importe_quel_ordre_et_colonnes_en_trop_ignorees() -> None:
    contenu = "mail;groupes;prenom;nom;identifiant\nx@y.z;compta;Marie;Dupont;dupont\n"
    utilisateurs, rejets = lire_texte(contenu)
    assert rejets == []
    assert utilisateurs[0].identifiant == "dupont"
    assert utilisateurs[0].groupes == ("compta",)


def test_numeros_sont_des_numeros_d_enregistrement() -> None:
    """L'en-tête compte pour la ligne 1, le premier enregistrement pour la ligne 2."""
    contenu = EN_TETE + "dupont;Dupont;Marie;\n;Legrand;Paul;\n"
    utilisateurs, rejets = lire_texte(contenu)
    assert utilisateurs[0].ligne == 2
    assert rejets[0].ligne == 3


def test_champ_multiligne_ne_decale_pas_la_numerotation() -> None:
    contenu = EN_TETE + 'dupont;"Du\npont";Marie;\nlegrand;Legrand;Paul;\n'
    utilisateurs, _ = lire_texte(contenu)
    assert [utilisateur.ligne for utilisateur in utilisateurs] == [2, 3]


def test_decodage_bom_puis_utf8_puis_cp1252() -> None:
    assert decoder("é".encode("utf-8-sig")) == "é"
    assert decoder("é".encode()) == "é"
    assert decoder("é".encode("cp1252")) == "é"


def test_lire_ouvre_un_fichier_cp1252(tmp_path: Path) -> None:
    fichier = tmp_path / "users.csv"
    fichier.write_bytes((EN_TETE + "dupont;Dupont;Chloé;\n").encode("cp1252"))
    utilisateurs, _ = lire(fichier)
    assert utilisateurs[0].prenom == "Chloé"
```

- [ ] **Step 2: Écrire les tests de validation, bascule et doublons**

Suite de `tests/test_lecture.py` :

```python
def test_espaces_supprimes_avant_toute_validation() -> None:
    contenu = EN_TETE + "  dupont ; Dupont ; Marie ; compta | rh \n"
    utilisateurs, rejets = lire_texte(contenu)
    assert rejets == []
    assert utilisateurs[0].identifiant == "dupont"
    assert utilisateurs[0].nom == "Dupont"
    assert utilisateurs[0].groupes == ("compta", "rh")


def test_identifiant_bascule_en_minuscules_et_la_ligne_passe() -> None:
    utilisateurs, rejets = lire_texte(EN_TETE + "Jean.Dupont;Dupont;Jean;\n")
    assert rejets == []
    assert utilisateurs[0].identifiant == "jean.dupont"
    assert utilisateurs[0].identifiant_origine == "Jean.Dupont"
    assert utilisateurs[0].bascule_minuscules is True


@pytest.mark.parametrize(
    ("valeur", "extrait_du_motif"),
    [
        ("", "identifiant"),
        ("jean dupont", "caractère"),
        ("jéan", "caractère"),
        ("jean@dupont", "caractère"),
    ],
)
def test_identifiants_rejetes(valeur: str, extrait_du_motif: str) -> None:
    utilisateurs, rejets = lire_texte(EN_TETE + f"{valeur};Dupont;Jean;\n")
    assert utilisateurs == []
    assert extrait_du_motif in rejets[0].motif


def test_jeu_de_caracteres_accepte() -> None:
    utilisateurs, rejets = lire_texte(EN_TETE + "a-b_c.d9;Dupont;Jean;\n")
    assert rejets == []
    assert utilisateurs[0].identifiant == "a-b_c.d9"


@pytest.mark.parametrize("ligne", ["dupont;;Marie;", "dupont;Dupont;;"])
def test_nom_ou_prenom_vide_rejete(ligne: str) -> None:
    utilisateurs, rejets = lire_texte(EN_TETE + ligne + "\n")
    assert utilisateurs == []
    assert len(rejets) == 1


def test_doublon_rejette_les_deux_lignes() -> None:
    """L'outil ne tranche pas laquelle des deux est juste : il les refuse toutes les deux."""
    contenu = EN_TETE + "dupont;Dupont;Marie;\ndupont;Dupont;Paul;\n"
    utilisateurs, rejets = lire_texte(contenu)
    assert utilisateurs == []
    assert [rejet.ligne for rejet in rejets] == [2, 3]
    assert all("doublon" in rejet.motif for rejet in rejets)


def test_doublon_detecte_apres_bascule_en_minuscules() -> None:
    contenu = EN_TETE + "Jean.Dupont;Dupont;Jean;\njean.dupont;Dupont;Jean;\n"
    utilisateurs, rejets = lire_texte(contenu)
    assert utilisateurs == []
    assert [rejet.ligne for rejet in rejets] == [2, 3]


def test_rejets_portent_l_identifiant_apres_bascule() -> None:
    _, rejets = lire_texte(EN_TETE + "Jean.Dupont;;Jean;\n")
    assert rejets[0].identifiant == "jean.dupont"


def test_une_ligne_rejetee_ne_bloque_pas_les_autres() -> None:
    contenu = EN_TETE + ";Dupont;Marie;\nlegrand;Legrand;Paul;\n"
    utilisateurs, rejets = lire_texte(contenu)
    assert [utilisateur.identifiant for utilisateur in utilisateurs] == ["legrand"]
    assert len(rejets) == 1


def test_groupes_vides_dedupliques_et_segments_vides_ignores() -> None:
    contenu = EN_TETE + "dupont;Dupont;Marie;compta||rh|compta|\nlegrand;Legrand;Paul;\n"
    utilisateurs, rejets = lire_texte(contenu)
    assert rejets == []
    assert utilisateurs[0].groupes == ("compta", "rh")
    assert utilisateurs[1].groupes == ()


def test_aucune_contrainte_de_caracteres_sur_les_noms_de_groupes() -> None:
    utilisateurs, rejets = lire_texte(EN_TETE + 'dupont;Dupont;Marie;Groupe "A" & Cie\n')
    assert rejets == []
    assert utilisateurs[0].groupes == ('Groupe "A" & Cie',)
```

- [ ] **Step 3: Lancer, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_lecture.py -q`
Attendu : `ModuleNotFoundError: No module named 'stormshield_utilisateurs.lecture'`.

- [ ] **Step 4: Écrire `lecture.py`**

```python
"""CSV -> (utilisateurs valides, rejets). Module pur : aucun réseau, aucune écriture."""

import csv
import io
import re
from collections import Counter
from pathlib import Path

from stormshield_utilisateurs.modele import Rejet, Utilisateur

COLONNES_ATTENDUES: tuple[str, ...] = ("identifiant", "nom", "prenom", "groupes")
SEPARATEUR = ";"
SEPARATEUR_GROUPES = "|"
# Jeu volontairement restrictif : la liste exacte admise par le boîtier n'a pas pu
# être vérifiée (voir « Points non vérifiés » de la spec).
IDENTIFIANT_VALIDE = re.compile(r"^[a-z0-9._-]+$")


class ColonnesManquantes(Exception):
    """Erreur de structure : le fichier entier est refusé, aucune ligne n'est lue."""

    def __init__(self, colonnes: tuple[str, ...]) -> None:
        self.colonnes = colonnes
        super().__init__(
            "colonne(s) absente(s) du fichier : " + ", ".join(colonnes)
        )


def decoder(octets: bytes) -> str:
    """BOM d'abord, puis UTF-8, puis repli cp1252 (Excel français)."""
    for bom, encodage in (
        (b"\xef\xbb\xbf", "utf-8-sig"),
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
    ):
        if octets.startswith(bom):
            return octets.decode(encodage)
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError:
        return octets.decode("cp1252")


def lire(chemin: Path) -> tuple[list[Utilisateur], list[Rejet]]:
    return lire_texte(decoder(chemin.read_bytes()))


def _decouper_groupes(brut: str) -> tuple[str, ...]:
    """Segments vides ignorés, doublons internes supprimés, ordre conservé."""
    groupes: list[str] = []
    for segment in brut.split(SEPARATEUR_GROUPES):
        nom = segment.strip()
        if nom and nom not in groupes:
            groupes.append(nom)
    return tuple(groupes)


def _motifs(identifiant: str, nom: str, prenom: str) -> list[str]:
    motifs: list[str] = []
    if not identifiant:
        motifs.append("identifiant vide")
    elif not IDENTIFIANT_VALIDE.match(identifiant):
        motifs.append("identifiant : caractère interdit (autorisés : a-z 0-9 . _ -)")
    if not nom:
        motifs.append("nom vide")
    if not prenom:
        motifs.append("prenom vide")
    return motifs


def lire_texte(contenu: str) -> tuple[list[Utilisateur], list[Rejet]]:
    lecteur = csv.DictReader(io.StringIO(contenu, newline=""), delimiter=SEPARATEUR)
    presentes = {(colonne or "").strip() for colonne in (lecteur.fieldnames or [])}
    manquantes = tuple(
        colonne for colonne in COLONNES_ATTENDUES if colonne not in presentes
    )
    if manquantes:
        raise ColonnesManquantes(manquantes)

    # Numéro d'enregistrement : l'en-tête est la ligne 1, le premier enregistrement la 2.
    candidats: list[tuple[int, Utilisateur, list[str]]] = []
    for numero, enregistrement in enumerate(lecteur, start=2):
        champs = {
            colonne: (enregistrement.get(colonne) or "").strip()
            for colonne in COLONNES_ATTENDUES
        }
        identifiant = champs["identifiant"].lower()
        utilisateur = Utilisateur(
            ligne=numero,
            identifiant=identifiant,
            identifiant_origine=champs["identifiant"],
            nom=champs["nom"],
            prenom=champs["prenom"],
            groupes=_decouper_groupes(champs["groupes"]),
        )
        candidats.append(
            (numero, utilisateur, _motifs(identifiant, champs["nom"], champs["prenom"]))
        )

    # Les doublons se comptent sur les identifiants par ailleurs valides, après bascule ;
    # les deux lignes d'un doublon sont rejetées, jamais une seule.
    occurrences = Counter(
        utilisateur.identifiant for _, utilisateur, motifs in candidats if not motifs
    )

    utilisateurs: list[Utilisateur] = []
    rejets: list[Rejet] = []
    for numero, utilisateur, motifs in candidats:
        if occurrences[utilisateur.identifiant] > 1:
            motifs = [*motifs, "identifiant en doublon dans le fichier"]
        if motifs:
            rejets.append(
                Rejet(ligne=numero, identifiant=utilisateur.identifiant, motif=" ; ".join(motifs))
            )
        else:
            utilisateurs.append(utilisateur)
    return utilisateurs, rejets
```

- [ ] **Step 5: Faire passer, contrôler la sortie**

```bash
.venv/bin/pytest tests/test_lecture.py -q && .venv/bin/ruff check . && .venv/bin/mypy
```
Attendu : tous les tests passent. Si `test_champ_multiligne_ne_decale_pas_la_numerotation` échoue, la cause est le `newline` de `io.StringIO` : vérifier `io.StringIO(contenu, newline="")`.

- [ ] **Step 6: Commit**

```bash
git add stormshield_utilisateurs/lecture.py tests/test_lecture.py
git commit -m "feat: lecture et validation du CSV d'entree"
```

**Fini quand :** les 18 tests de `test_lecture.py` passent, dont nommément `test_colonne_manquante_fait_echouer_le_fichier_entier`, `test_identifiant_bascule_en_minuscules_et_la_ligne_passe`, `test_doublon_rejette_les_deux_lignes` et `test_doublon_detecte_apres_bascule_en_minuscules`.

---

## Task 4: Génération des mots de passe et plancher de politique

**Files:**
- Create: `stormshield_utilisateurs/motdepasse.py`
- Test: `tests/test_motdepasse.py`

**Interfaces:**
- Consumes: `modele.PolitiqueMotDePasse`, `modele.PlancherPolitique`.
- Produces:
  - `def generer(politique: PolitiqueMotDePasse) -> str`
  - `def violations(politique: PolitiqueMotDePasse, plancher: PlancherPolitique) -> list[str]` — liste vide = accepté ; messages destinés à l'opérateur.
  - `def proposer(plancher: PlancherPolitique) -> PolitiqueMotDePasse` — pré-remplissage initial uniquement.
  - `LONGUEUR_PROPOSEE: int = 16`

- [ ] **Step 1: Écrire les tests**

`tests/test_motdepasse.py` :

```python
"""Génération : on teste la propriété garantie, jamais le tirage lui-même."""

import string

import pytest

from stormshield_utilisateurs.modele import PlancherPolitique, PolitiqueMotDePasse
from stormshield_utilisateurs.motdepasse import generer, proposer, violations

TOUTES_CLASSES = PolitiqueMotDePasse(
    longueur=16, minuscules=True, majuscules=True, chiffres=True, speciaux=True
)


def test_longueur_exacte_demandee() -> None:
    assert len(generer(TOUTES_CLASSES)) == 16


def test_au_moins_un_caractere_par_classe_demandee() -> None:
    """Répété : un tirage unique pourrait satisfaire la règle par chance."""
    for _ in range(200):
        genere = generer(TOUTES_CLASSES)
        assert any(caractere in string.ascii_lowercase for caractere in genere)
        assert any(caractere in string.ascii_uppercase for caractere in genere)
        assert any(caractere in string.digits for caractere in genere)
        assert any(not caractere.isalnum() for caractere in genere)


def test_classes_non_demandees_absentes() -> None:
    politique = PolitiqueMotDePasse(
        longueur=12, minuscules=True, majuscules=False, chiffres=True, speciaux=False
    )
    for _ in range(50):
        genere = generer(politique)
        assert all(caractere in string.ascii_lowercase + string.digits for caractere in genere)


def test_deux_appels_donnent_deux_mots_de_passe() -> None:
    assert generer(TOUTES_CLASSES) != generer(TOUTES_CLASSES)


def test_generation_refusee_si_aucune_classe() -> None:
    politique = PolitiqueMotDePasse(
        longueur=12, minuscules=False, majuscules=False, chiffres=False, speciaux=False
    )
    with pytest.raises(ValueError):
        generer(politique)


def test_generation_refusee_si_longueur_inferieure_au_nombre_de_classes() -> None:
    politique = PolitiqueMotDePasse(
        longueur=2, minuscules=True, majuscules=True, chiffres=True, speciaux=True
    )
    with pytest.raises(ValueError):
        generer(politique)


def test_politique_sous_le_plancher_refusee() -> None:
    plancher = PlancherPolitique(longueur_min=12, nombre_classes_min=3, entropie_min=0)
    trop_courte = PolitiqueMotDePasse(
        longueur=8, minuscules=True, majuscules=True, chiffres=True, speciaux=True
    )
    assert any("12" in message for message in violations(trop_courte, plancher))

    trop_peu_de_classes = PolitiqueMotDePasse(
        longueur=16, minuscules=True, majuscules=True, chiffres=False, speciaux=False
    )
    assert any("classes" in message for message in violations(trop_peu_de_classes, plancher))


def test_politique_au_dessus_du_plancher_acceptee() -> None:
    plancher = PlancherPolitique(longueur_min=12, nombre_classes_min=3, entropie_min=0)
    assert violations(TOUTES_CLASSES, plancher) == []


def test_proposition_respecte_le_plancher_et_reste_genereuse() -> None:
    plancher = PlancherPolitique(longueur_min=24, nombre_classes_min=2, entropie_min=0)
    propose = proposer(plancher)
    assert propose.longueur == 24
    assert violations(propose, plancher) == []
    assert proposer(PlancherPolitique(8, 2, 0)).longueur == 16
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_motdepasse.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Écrire `motdepasse.py`**

```python
"""Génération de mots de passe. Module pur, `secrets` de la bibliothèque standard."""

import secrets
import string

from stormshield_utilisateurs.modele import PlancherPolitique, PolitiqueMotDePasse

LONGUEUR_PROPOSEE = 16
# Jeu de spéciaux volontairement étroit : pas de guillemet ni d'espace, qui compliqueraient
# la construction de la commande USER PASSWORD sans rien apporter à l'entropie.
SPECIAUX = "!#$%*+-=?@_"


def _alphabets(politique: PolitiqueMotDePasse) -> list[str]:
    alphabets = []
    if politique.minuscules:
        alphabets.append(string.ascii_lowercase)
    if politique.majuscules:
        alphabets.append(string.ascii_uppercase)
    if politique.chiffres:
        alphabets.append(string.digits)
    if politique.speciaux:
        alphabets.append(SPECIAUX)
    return alphabets


def generer(politique: PolitiqueMotDePasse) -> str:
    """Longueur exacte et au moins un caractère de chaque classe demandée."""
    alphabets = _alphabets(politique)
    if not alphabets:
        raise ValueError("au moins une classe de caractères est nécessaire")
    if politique.longueur < len(alphabets):
        raise ValueError(
            f"longueur {politique.longueur} insuffisante pour {len(alphabets)} classes"
        )
    caracteres = [secrets.choice(alphabet) for alphabet in alphabets]
    complet = "".join(alphabets)
    caracteres += [
        secrets.choice(complet) for _ in range(politique.longueur - len(caracteres))
    ]
    # Mélange : sans lui, les premiers caractères trahiraient l'ordre des classes.
    melange = list(caracteres)
    for indice in range(len(melange) - 1, 0, -1):
        autre = secrets.randbelow(indice + 1)
        melange[indice], melange[autre] = melange[autre], melange[indice]
    return "".join(melange)


def violations(politique: PolitiqueMotDePasse, plancher: PlancherPolitique) -> list[str]:
    """Messages à afficher ; liste vide = la politique tient le plancher du boîtier."""
    messages: list[str] = []
    if politique.longueur < plancher.longueur_min:
        messages.append(
            f"longueur {politique.longueur} inférieure au minimum du boîtier "
            f"({plancher.longueur_min})"
        )
    if politique.nombre_classes() < plancher.nombre_classes_min:
        messages.append(
            f"{politique.nombre_classes()} classes de caractères, le boîtier en exige "
            f"{plancher.nombre_classes_min}"
        )
    return messages


def proposer(plancher: PlancherPolitique) -> PolitiqueMotDePasse:
    """Pré-remplissage initial uniquement : jamais appelé sur une relecture du boîtier."""
    return PolitiqueMotDePasse(
        longueur=max(LONGUEUR_PROPOSEE, plancher.longueur_min),
        minuscules=True,
        majuscules=True,
        chiffres=True,
        speciaux=True,
    )
```

- [ ] **Step 4: Faire passer**

```bash
.venv/bin/pytest tests/test_motdepasse.py -q && .venv/bin/ruff check . && .venv/bin/mypy
```

- [ ] **Step 5: Commit**

```bash
git add stormshield_utilisateurs/motdepasse.py tests/test_motdepasse.py
git commit -m "feat: generation des mots de passe et plancher de politique"
```

**Fini quand :** les 10 tests passent, `MinEntropy` n'est contraint nulle part (il est porté par `PlancherPolitique.entropie_min` et seulement affiché), et aucun appel à `CONFIG PASSWDPOLICY SET` n'existe dans le code.

---

## Task 5: Frontière `Boitier` et double en mémoire

**Files:**
- Create: `stormshield_utilisateurs/boitier.py`
- Create: `stormshield_utilisateurs/boitier_memoire.py`
- Test: `tests/test_boitier_memoire.py`

**Interfaces:**
- Consumes: `modele.PlancherPolitique`.
- Produces:
  - `class ErreurBoitier(Exception)` — racine.
  - `class ErreurCommande(ErreurBoitier)` : `__init__(self, code: int, message: str)`, attributs `code`, `message`. Le boîtier a répondu et a refusé : échec isolé, pas de reconnexion.
  - `class ErreurReseau(ErreurBoitier)` — transport perdu : déclenche la reconnexion.
  - `class Boitier(Protocol)` avec `connecter`, `deconnecter`, `lister_annuaires`, `initialiser_annuaire`, `activer_annuaire`, `lire_politique`, `lister_utilisateurs`, `lister_groupes`, `creer_groupe`, `creer_utilisateur`, `definir_mot_de_passe`, `ajouter_membre` (signatures exactes ci-dessous).
  - `class BoitierMemoire` implémentant le Protocol, avec `journal_appels: list[tuple[str, str]]` et le point d'injection `declencheur: Callable[[str, str], None]`.

- [ ] **Step 1: Écrire les tests du double**

`tests/test_boitier_memoire.py` :

```python
"""Le double est l'instrument de tous les autres tests : il a les siens."""

import pytest

from stormshield_utilisateurs.boitier import Boitier, ErreurCommande, ErreurReseau
from stormshield_utilisateurs.boitier_memoire import BoitierMemoire


def test_le_double_satisfait_le_protocol() -> None:
    boitier: Boitier = BoitierMemoire()
    assert boitier is not None


def test_creation_d_un_utilisateur_et_d_un_groupe() -> None:
    boitier = BoitierMemoire(utilisateurs=["martin"], groupes=["rh"])
    boitier.connecter()
    boitier.creer_utilisateur("dupont", "Dupont", "Marie", "interne.local")
    boitier.creer_groupe("compta")
    boitier.ajouter_membre("compta", "dupont")
    boitier.definir_mot_de_passe("dupont", "Abc123!x")
    assert sorted(boitier.lister_utilisateurs()) == ["dupont", "martin"]
    assert sorted(boitier.lister_groupes()) == ["compta", "rh"]
    assert boitier.membres["compta"] == ["dupont"]
    assert boitier.mots_de_passe["dupont"] == "Abc123!x"


def test_creer_deux_fois_le_meme_utilisateur_est_refuse() -> None:
    """Le boîtier réel refuse ; le double doit refuser aussi, sinon l'idempotence
    de l'outil serait prouvée contre un double plus permissif que la réalité."""
    boitier = BoitierMemoire(utilisateurs=["dupont"])
    with pytest.raises(ErreurCommande):
        boitier.creer_utilisateur("dupont", "Dupont", "Marie", "interne.local")


def test_journal_des_appels_conserve_l_ordre() -> None:
    boitier = BoitierMemoire()
    boitier.lister_utilisateurs()
    boitier.creer_utilisateur("dupont", "Dupont", "Marie", "interne.local")
    assert boitier.journal_appels == [
        ("lister_utilisateurs", ""),
        ("creer_utilisateur", "dupont"),
    ]


def test_le_declencheur_permet_d_injecter_une_panne() -> None:
    boitier = BoitierMemoire()

    def couper(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur":
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper
    with pytest.raises(ErreurReseau):
        boitier.creer_utilisateur("dupont", "Dupont", "Marie", "interne.local")
    assert boitier.lister_utilisateurs() == []


def test_annuaires_et_politique_par_defaut() -> None:
    boitier = BoitierMemoire()
    assert boitier.lister_annuaires() == ["interne.local"]
    assert boitier.lire_politique().longueur_min == 12


def test_initialisation_puis_activation_d_un_annuaire() -> None:
    boitier = BoitierMemoire(annuaires=[])
    assert boitier.lister_annuaires() == []
    boitier.initialiser_annuaire("neuf.local", "Societe", "dc=neuf,dc=local", "secret-factice")
    boitier.activer_annuaire()
    assert boitier.lister_annuaires() == ["neuf.local"]
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_boitier_memoire.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Écrire `boitier.py`**

```python
"""Frontière unique avec le firewall. Aucun import du SDK ici : voir boitier_sdk.py."""

from typing import Protocol

from stormshield_utilisateurs.modele import PlancherPolitique


class ErreurBoitier(Exception):
    """Racine des erreurs du dialogue avec le boîtier."""


class ErreurCommande(ErreurBoitier):
    """Le boîtier a répondu et a refusé : échec isolé, le lot continue."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"code {code} : {message}")


class ErreurReseau(ErreurBoitier):
    """La liaison est perdue : c'est le seul cas qui déclenche une reconnexion."""


class Boitier(Protocol):
    """Tout ce que l'outil sait demander à un firewall SNS, et rien de plus."""

    def connecter(self) -> None: ...

    def deconnecter(self) -> None: ...

    def lister_annuaires(self) -> list[str]:
        """CONFIG LDAP LIST : les noms de domaine des annuaires internes déclarés."""
        ...

    def initialiser_annuaire(
        self, domainname: str, organisation: str, dc: str, mot_de_passe: str
    ) -> None:
        """CONFIG LDAP INITIALIZE. Chemin conditionnel : voir execution.lire_etat."""
        ...

    def activer_annuaire(self) -> None: ...

    def lire_politique(self) -> PlancherPolitique:
        """CONFIG PASSWDPOLICY SHOW. Lecture seule : l'outil n'écrit jamais la politique."""
        ...

    def lister_utilisateurs(self) -> list[str]: ...

    def lister_groupes(self) -> list[str]: ...

    def creer_groupe(self, nom: str) -> None: ...

    def creer_utilisateur(
        self, identifiant: str, nom: str, prenom: str, domaine: str
    ) -> None: ...

    def definir_mot_de_passe(self, identifiant: str, mot_de_passe: str) -> None: ...

    def ajouter_membre(self, groupe: str, identifiant: str) -> None: ...
```

- [ ] **Step 4: Écrire `boitier_memoire.py`**

```python
"""Boîtier en mémoire : support de la totalité des tests métier, aucun réseau."""

from collections.abc import Callable, Iterable

from stormshield_utilisateurs.boitier import ErreurCommande
from stormshield_utilisateurs.modele import PlancherPolitique

PLANCHER_PAR_DEFAUT = PlancherPolitique(longueur_min=12, nombre_classes_min=3, entropie_min=0)


def _sans_panne(operation: str, cible: str) -> None:
    """Déclencheur neutre ; les tests le remplacent pour injecter une panne."""


class BoitierMemoire:
    """Implémente le Protocol Boitier contre un état en mémoire."""

    def __init__(
        self,
        utilisateurs: Iterable[str] = (),
        groupes: Iterable[str] = (),
        annuaires: Iterable[str] = ("interne.local",),
        plancher: PlancherPolitique = PLANCHER_PAR_DEFAUT,
    ) -> None:
        self.utilisateurs: list[str] = list(utilisateurs)
        self.groupes: list[str] = list(groupes)
        self.annuaires: list[str] = list(annuaires)
        self.plancher = plancher
        self.membres: dict[str, list[str]] = {}
        self.mots_de_passe: dict[str, str] = {}
        self.connecte = False
        self.connexions = 0
        self.journal_appels: list[tuple[str, str]] = []
        self.declencheur: Callable[[str, str], None] = _sans_panne
        self._annuaire_en_attente: str | None = None

    def _appel(self, operation: str, cible: str = "") -> None:
        self.journal_appels.append((operation, cible))
        self.declencheur(operation, cible)

    def connecter(self) -> None:
        self._appel("connecter")
        self.connecte = True
        self.connexions += 1

    def deconnecter(self) -> None:
        self._appel("deconnecter")
        self.connecte = False

    def lister_annuaires(self) -> list[str]:
        self._appel("lister_annuaires")
        return list(self.annuaires)

    def initialiser_annuaire(
        self, domainname: str, organisation: str, dc: str, mot_de_passe: str
    ) -> None:
        self._appel("initialiser_annuaire", domainname)
        if self.annuaires:
            raise ErreurCommande(200, "un annuaire existe déjà")
        self._annuaire_en_attente = domainname

    def activer_annuaire(self) -> None:
        self._appel("activer_annuaire")
        if self._annuaire_en_attente is None:
            raise ErreurCommande(200, "aucun annuaire à activer")
        self.annuaires.append(self._annuaire_en_attente)
        self._annuaire_en_attente = None

    def lire_politique(self) -> PlancherPolitique:
        self._appel("lire_politique")
        return self.plancher

    def lister_utilisateurs(self) -> list[str]:
        self._appel("lister_utilisateurs")
        return list(self.utilisateurs)

    def lister_groupes(self) -> list[str]:
        self._appel("lister_groupes")
        return list(self.groupes)

    def creer_groupe(self, nom: str) -> None:
        self._appel("creer_groupe", nom)
        if nom in self.groupes:
            raise ErreurCommande(200, f"le groupe {nom} existe déjà")
        if '"' in nom:
            # Le nom est transmis verbatim entre guillemets doubles : un guillemet
            # dans le nom ne peut pas passer. Échec de création, pas rejet de ligne.
            raise ErreurCommande(200, "guillemet double interdit dans un nom de groupe")
        self.groupes.append(nom)

    def creer_utilisateur(self, identifiant: str, nom: str, prenom: str, domaine: str) -> None:
        self._appel("creer_utilisateur", identifiant)
        if identifiant in self.utilisateurs:
            raise ErreurCommande(200, f"l'utilisateur {identifiant} existe déjà")
        self.utilisateurs.append(identifiant)

    def definir_mot_de_passe(self, identifiant: str, mot_de_passe: str) -> None:
        self._appel("definir_mot_de_passe", identifiant)
        if identifiant not in self.utilisateurs:
            raise ErreurCommande(200, f"utilisateur {identifiant} inconnu")
        self.mots_de_passe[identifiant] = mot_de_passe

    def ajouter_membre(self, groupe: str, identifiant: str) -> None:
        self._appel("ajouter_membre", f"{groupe}/{identifiant}")
        if groupe not in self.groupes:
            raise ErreurCommande(200, f"groupe {groupe} inconnu")
        self.membres.setdefault(groupe, []).append(identifiant)
```

- [ ] **Step 5: Faire passer**

```bash
.venv/bin/pytest tests/test_boitier_memoire.py -q && .venv/bin/ruff check . && .venv/bin/mypy
```
Attendu : 7 tests passés. Si mypy signale `ARG002` sur les paramètres inutilisés de `creer_utilisateur`, préfixer le corps d'un commentaire est insuffisant : ajouter `del organisation, dc, mot_de_passe` ou nommer les paramètres tels quels et laisser `ruff` les accepter (ils font partie de la signature du Protocol). Régler proprement, pas par `# noqa` global.

- [ ] **Step 6: Commit**

```bash
git add stormshield_utilisateurs/boitier.py stormshield_utilisateurs/boitier_memoire.py \
        tests/test_boitier_memoire.py
git commit -m "feat: protocol Boitier et double en memoire"
```

**Fini quand :** `boitier.py` ne contient aucun `import stormshield`, `BoitierMemoire` est accepté par mypy comme un `Boitier`, et les 7 tests passent.

---

## Task 6: Construction du plan (pure)

**Files:**
- Create: `stormshield_utilisateurs/plan.py`
- Test: `tests/test_plan.py`

**Interfaces:**
- Consumes: `modele.Utilisateur`, `modele.EtatBoitier`, `modele.Plan`, `modele.GroupeACreer`.
- Produces: `def construire(utilisateurs: Sequence[Utilisateur], etat: EtatBoitier) -> Plan`

**Comportement subtil :** les groupes à créer se calculent sur **les seuls comptes à créer**, avec leur nombre de membres.

- [ ] **Step 1: Écrire les tests**

`tests/test_plan.py` :

```python
"""Toute la décision de l'outil tient dans ce module : il se teste sans réseau."""

from stormshield_utilisateurs.modele import EtatBoitier, PlancherPolitique, Utilisateur
from stormshield_utilisateurs.plan import construire

PLANCHER = PlancherPolitique(longueur_min=12, nombre_classes_min=3, entropie_min=0)


def _etat(utilisateurs: set[str] = frozenset(), groupes: set[str] = frozenset()) -> EtatBoitier:
    return EtatBoitier(
        domaine="interne.local",
        plancher=PLANCHER,
        utilisateurs=frozenset(utilisateurs),
        groupes=frozenset(groupes),
    )


def _utilisateur(identifiant: str, *groupes: str, ligne: int = 2) -> Utilisateur:
    return Utilisateur(
        ligne=ligne,
        identifiant=identifiant,
        identifiant_origine=identifiant,
        nom="Dupont",
        prenom="Marie",
        groupes=groupes,
    )


def test_compte_absent_du_boitier_est_a_creer() -> None:
    plan = construire([_utilisateur("dupont")], _etat())
    assert [compte.identifiant for compte in plan.comptes_a_creer] == ["dupont"]
    assert plan.comptes_ignores == ()


def test_compte_present_sur_le_boitier_est_ignore_entierement() -> None:
    """Appartenances de groupes comprises : rien n'est rattaché à un compte existant."""
    plan = construire([_utilisateur("dupont", "compta")], _etat(utilisateurs={"dupont"}))
    assert plan.comptes_a_creer == ()
    assert [compte.identifiant for compte in plan.comptes_ignores] == ["dupont"]
    assert plan.groupes_a_creer == ()


def test_compte_du_boitier_absent_du_fichier_est_orphelin() -> None:
    plan = construire([_utilisateur("dupont")], _etat(utilisateurs={"martin", "dupont"}))
    assert plan.orphelins == ("martin",)


def test_orphelins_tries_pour_un_affichage_stable() -> None:
    plan = construire([], _etat(utilisateurs={"zoe", "alice", "martin"}))
    assert plan.orphelins == ("alice", "martin", "zoe")


def test_groupe_absent_du_boitier_et_reference_par_un_compte_a_creer_est_cree() -> None:
    plan = construire([_utilisateur("dupont", "compta", "rh")], _etat(groupes={"rh"}))
    assert [groupe.nom for groupe in plan.groupes_a_creer] == ["compta"]


def test_groupe_reference_seulement_par_un_compte_deja_present_n_est_pas_cree() -> None:
    plan = construire(
        [_utilisateur("dupont", "compta_bis")], _etat(utilisateurs={"dupont"})
    )
    assert plan.groupes_a_creer == ()


def test_nombre_de_membres_compte_les_seuls_comptes_a_creer() -> None:
    """compta_bis à un seul membre est la signature d'une coquille : le nombre doit le dire."""
    utilisateurs = [
        _utilisateur("dupont", "compta", ligne=2),
        _utilisateur("legrand", "compta", "compta_bis", ligne=3),
        _utilisateur("martin", "compta", ligne=4),
    ]
    plan = construire(utilisateurs, _etat(utilisateurs={"martin"}))
    membres = {groupe.nom: groupe.nombre_membres for groupe in plan.groupes_a_creer}
    assert membres == {"compta": 2, "compta_bis": 1}


def test_groupes_a_creer_tries_par_nom() -> None:
    plan = construire([_utilisateur("dupont", "zoe", "alice")], _etat())
    assert [groupe.nom for groupe in plan.groupes_a_creer] == ["alice", "zoe"]


def test_le_domaine_lu_sur_le_boitier_est_porte_par_le_plan() -> None:
    assert construire([], _etat()).domaine == "interne.local"


def test_construire_n_ecrit_rien_sur_l_etat_recu() -> None:
    etat = _etat(utilisateurs={"martin"}, groupes={"rh"})
    construire([_utilisateur("dupont", "compta")], etat)
    assert etat.utilisateurs == frozenset({"martin"})
    assert etat.groupes == frozenset({"rh"})
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_plan.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Écrire `plan.py`**

```python
"""Décision : état lu + lignes valides -> Plan. Pur, n'écrit jamais sur le boîtier."""

from collections import Counter
from collections.abc import Sequence

from stormshield_utilisateurs.modele import EtatBoitier, GroupeACreer, Plan, Utilisateur


def construire(utilisateurs: Sequence[Utilisateur], etat: EtatBoitier) -> Plan:
    """L'outil ajoute et rien d'autre : il ne modifie ni ne supprime jamais l'existant."""
    a_creer = tuple(
        utilisateur
        for utilisateur in utilisateurs
        if utilisateur.identifiant not in etat.utilisateurs
    )
    ignores = tuple(
        utilisateur
        for utilisateur in utilisateurs
        if utilisateur.identifiant in etat.utilisateurs
    )
    dans_le_fichier = {utilisateur.identifiant for utilisateur in utilisateurs}
    orphelins = tuple(sorted(etat.utilisateurs - dans_le_fichier))

    # Les groupes à créer ne se comptent que sur les comptes à créer : un groupe
    # référencé seulement par un rejet ou par un compte existant n'est pas créé.
    membres: Counter[str] = Counter()
    for utilisateur in a_creer:
        membres.update(utilisateur.groupes)
    groupes_a_creer = tuple(
        GroupeACreer(nom=nom, nombre_membres=membres[nom])
        for nom in sorted(membres)
        if nom not in etat.groupes
    )

    return Plan(
        comptes_a_creer=a_creer,
        comptes_ignores=ignores,
        groupes_a_creer=groupes_a_creer,
        orphelins=orphelins,
        domaine=etat.domaine,
    )
```

- [ ] **Step 4: Faire passer**

```bash
.venv/bin/pytest tests/test_plan.py -q && .venv/bin/ruff check . && .venv/bin/mypy
```

- [ ] **Step 5: Commit**

```bash
git add stormshield_utilisateurs/plan.py tests/test_plan.py
git commit -m "feat: construction du plan de rapprochement"
```

**Fini quand :** les 10 tests passent et `plan.py` n'importe ni `boitier`, ni `execution`, ni `secrets`.

---

## Task 7: Lecture de l'état du boîtier et cas de l'annuaire

**Files:**
- Create: `stormshield_utilisateurs/execution.py`
- Test: `tests/test_execution_lecture.py`

**Interfaces:**
- Consumes: `boitier.Boitier`, `boitier.ErreurCommande`, `modele.EtatBoitier`.
- Produces:
  - `class AnnuaireAbsent(Exception)` — aucun annuaire : la fenêtre doit proposer l'initialisation.
  - `class AnnuairesMultiples(Exception)` avec attribut `annuaires: tuple[str, ...]` — arrêt net, aucune écriture.
  - `def lire_etat(boitier: Boitier) -> EtatBoitier` — enchaîne `CONFIG LDAP LIST`, `CONFIG PASSWDPOLICY SHOW`, `USER LIST`, `USER GROUP LIST`.
  - `def creer_annuaire(boitier, domainname, organisation, dc, mot_de_passe) -> None` — initialise, active, **relit** `CONFIG LDAP LIST` pour confirmer, lève `ErreurCommande` sinon.
  - `NOMBRE_LECTURES: int = 4` — total de la barre de progression en simulation.

- [ ] **Step 1: Écrire les tests des trois cas d'annuaire**

`tests/test_execution_lecture.py` :

```python
"""Phase de lecture : identique en simulation et en réel."""

import pytest

from stormshield_utilisateurs.boitier import ErreurCommande
from stormshield_utilisateurs.boitier_memoire import BoitierMemoire
from stormshield_utilisateurs.execution import (
    AnnuaireAbsent,
    AnnuairesMultiples,
    creer_annuaire,
    lire_etat,
)


def test_un_annuaire_est_le_cas_nominal() -> None:
    boitier = BoitierMemoire(utilisateurs=["martin"], groupes=["rh"])
    etat = lire_etat(boitier)
    assert etat.domaine == "interne.local"
    assert etat.utilisateurs == frozenset({"martin"})
    assert etat.groupes == frozenset({"rh"})
    assert etat.plancher.longueur_min == 12


def test_la_lecture_n_ecrit_rien() -> None:
    boitier = BoitierMemoire()
    lire_etat(boitier)
    operations = {operation for operation, _ in boitier.journal_appels}
    assert operations == {
        "lister_annuaires",
        "lire_politique",
        "lister_utilisateurs",
        "lister_groupes",
    }


def test_aucun_annuaire_demande_l_initialisation() -> None:
    with pytest.raises(AnnuaireAbsent):
        lire_etat(BoitierMemoire(annuaires=[]))


def test_plusieurs_annuaires_arretent_tout() -> None:
    """Les comptes iraient au bon endroit et les groupes on ne sait où : on refuse."""
    boitier = BoitierMemoire(annuaires=["a.local", "b.local"])
    with pytest.raises(AnnuairesMultiples) as erreur:
        lire_etat(boitier)
    assert erreur.value.annuaires == ("a.local", "b.local")
    assert ("lister_utilisateurs", "") not in boitier.journal_appels


def test_initialisation_puis_activation_puis_relecture_de_confirmation() -> None:
    boitier = BoitierMemoire(annuaires=[])
    creer_annuaire(boitier, "neuf.local", "Societe", "dc=neuf,dc=local", "secret-factice")
    operations = [operation for operation, _ in boitier.journal_appels]
    assert operations == ["initialiser_annuaire", "activer_annuaire", "lister_annuaires"]
    assert lire_etat(boitier).domaine == "neuf.local"


def test_initialisation_non_confirmee_est_une_erreur() -> None:
    """Le lot ne reprend la main qu'après confirmation par relecture."""
    boitier = BoitierMemoire(annuaires=[])

    def ne_rien_enregistrer(operation: str, cible: str) -> None:
        if operation == "activer_annuaire":
            boitier._annuaire_en_attente = None
            raise ErreurCommande(200, "activation refusée")

    boitier.declencheur = ne_rien_enregistrer
    with pytest.raises(ErreurCommande):
        creer_annuaire(boitier, "neuf.local", "Societe", "dc=neuf,dc=local", "secret-factice")
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_execution_lecture.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Écrire la partie lecture de `execution.py`**

```python
"""Lecture de l'état du boîtier, puis application du plan. Émet des événements."""

from stormshield_utilisateurs.boitier import Boitier, ErreurCommande
from stormshield_utilisateurs.modele import EtatBoitier

# CONFIG LDAP LIST, CONFIG PASSWDPOLICY SHOW, USER LIST, USER GROUP LIST.
NOMBRE_LECTURES = 4


class AnnuaireAbsent(Exception):
    """Aucun annuaire interne : c'est le seul cas où CONFIG LDAP INITIALIZE est atteignable."""


class AnnuairesMultiples(Exception):
    """Plusieurs annuaires : arrêt net, aucune écriture. USER GROUP CREATE ne sait
    pas viser un annuaire, les groupes partiraient on ne sait où."""

    def __init__(self, annuaires: tuple[str, ...]) -> None:
        self.annuaires = annuaires
        super().__init__(
            "le boîtier déclare plusieurs annuaires LDAP internes : "
            + ", ".join(annuaires)
            + ". L'outil s'arrête plutôt que de choisir."
        )


def lire_etat(boitier: Boitier) -> EtatBoitier:
    """Lecture seule. L'ordre est celui du flux d'exécution de la spec."""
    annuaires = boitier.lister_annuaires()
    if not annuaires:
        raise AnnuaireAbsent("le boîtier ne déclare aucun annuaire LDAP interne")
    if len(annuaires) > 1:
        raise AnnuairesMultiples(tuple(annuaires))
    plancher = boitier.lire_politique()
    return EtatBoitier(
        domaine=annuaires[0],
        plancher=plancher,
        utilisateurs=frozenset(boitier.lister_utilisateurs()),
        groupes=frozenset(boitier.lister_groupes()),
    )


def creer_annuaire(
    boitier: Boitier, domainname: str, organisation: str, dc: str, mot_de_passe: str
) -> None:
    """Chemin conditionnel, atteignable seulement après AnnuaireAbsent. Ne se refait pas."""
    boitier.initialiser_annuaire(domainname, organisation, dc, mot_de_passe)
    boitier.activer_annuaire()
    if domainname not in boitier.lister_annuaires():
        raise ErreurCommande(200, f"l'annuaire {domainname} n'apparaît pas après activation")
```

- [ ] **Step 4: Faire passer**

```bash
.venv/bin/pytest tests/test_execution_lecture.py -q && .venv/bin/ruff check . && .venv/bin/mypy
```

- [ ] **Step 5: Commit**

```bash
git add stormshield_utilisateurs/execution.py tests/test_execution_lecture.py
git commit -m "feat: lecture de l'etat du boitier et cas de l'annuaire LDAP"
```

**Fini quand :** les 6 tests passent, et `test_plusieurs_annuaires_arretent_tout` prouve qu'aucune lecture de comptes n'a lieu après l'arrêt.

---

## Task 8: Application du plan, réessais, reconnexion

**Files:**
- Modify: `stormshield_utilisateurs/execution.py`
- Test: `tests/test_execution_ecriture.py`

**Interfaces:**
- Consumes: tâches 2, 4, 5, 6, 7.
- Produces (tous exportés par `execution`) :
  - `@dataclass(frozen=True) class Patience: reessais: int = 3; delai: float = 2.0; dormir: Callable[[float], None] = time.sleep`
  - Événements, tous `@dataclass(frozen=True)` : `Journal(texte: str)`, `PlanPret(plan: Plan)`, `PolitiqueLue(plancher: PlancherPolitique)`, `Progression(accomplies: int, total: int)`, `Termine(rapport: Rapport)`, `Echoue(message: str)`
  - `Evenement = Journal | PlanPret | PolitiqueLue | Progression | Termine | Echoue`
  - `def executer(boitier, utilisateurs, politique, simulation, emettre, patience=Patience(), generer_mot_de_passe=motdepasse.generer) -> Rapport`

**Comportements subtils :** mot de passe généré **au moment de la création**, jamais avant ; trois réessais de `USER PASSWORD` puis `mot_de_passe` vide ; simulation qui lit quand même ; reconnexion qui **reconstruit** le plan au lieu de rejouer.

- [ ] **Step 1: Écrire les tests d'exécution**

`tests/test_execution_ecriture.py` :

```python
"""Exécution : on observe l'état final du double et les événements émis."""

from collections.abc import Callable

from stormshield_utilisateurs.boitier import ErreurCommande, ErreurReseau
from stormshield_utilisateurs.boitier_memoire import BoitierMemoire
from stormshield_utilisateurs.execution import (
    Evenement,
    Journal,
    Patience,
    PlanPret,
    Progression,
    Termine,
    executer,
)
from stormshield_utilisateurs.modele import PolitiqueMotDePasse, Rapport, Utilisateur

POLITIQUE = PolitiqueMotDePasse(
    longueur=16, minuscules=True, majuscules=True, chiffres=True, speciaux=True
)
# Patience sans attente réelle : les tests ne dorment jamais.
PATIENCE = Patience(reessais=3, delai=0.0, dormir=lambda _: None)


def _utilisateur(identifiant: str, *groupes: str, ligne: int = 2) -> Utilisateur:
    return Utilisateur(
        ligne=ligne,
        identifiant=identifiant,
        identifiant_origine=identifiant,
        nom="Dupont",
        prenom="Marie",
        groupes=groupes,
    )


def _lancer(
    boitier: BoitierMemoire,
    utilisateurs: list[Utilisateur],
    *,
    simulation: bool = False,
    generer: Callable[[PolitiqueMotDePasse], str] = lambda _: "MotDePasse1!",
) -> tuple[Rapport, list[Evenement]]:
    evenements: list[Evenement] = []
    rapport = executer(
        boitier,
        utilisateurs,
        POLITIQUE,
        simulation=simulation,
        emettre=evenements.append,
        patience=PATIENCE,
        generer_mot_de_passe=generer,
    )
    return rapport, evenements


def test_creation_nominale_dans_l_ordre_attendu() -> None:
    boitier = BoitierMemoire()
    rapport, _ = _lancer(boitier, [_utilisateur("dupont", "compta")])
    ecritures = [
        operation
        for operation, _ in boitier.journal_appels
        if operation
        in {"creer_groupe", "creer_utilisateur", "definir_mot_de_passe", "ajouter_membre"}
    ]
    assert ecritures == [
        "creer_groupe",
        "creer_utilisateur",
        "definir_mot_de_passe",
        "ajouter_membre",
    ]
    assert boitier.mots_de_passe == {"dupont": "MotDePasse1!"}
    assert rapport.comptes_crees[0].identifiant == "dupont"
    assert rapport.groupes_crees == ["compta"]


def test_simulation_lit_mais_n_ecrit_pas() -> None:
    boitier = BoitierMemoire(utilisateurs=["martin"])
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont", "compta")], simulation=True)
    operations = {operation for operation, _ in boitier.journal_appels}
    assert operations <= {
        "connecter",
        "deconnecter",
        "lister_annuaires",
        "lire_politique",
        "lister_utilisateurs",
        "lister_groupes",
    }
    assert rapport.comptes_crees == []
    plans = [evenement for evenement in evenements if isinstance(evenement, PlanPret)]
    assert [compte.identifiant for compte in plans[0].plan.comptes_a_creer] == ["dupont"]
    assert plans[0].plan.orphelins == ("martin",)


def test_aucun_mot_de_passe_genere_en_simulation() -> None:
    """Un compte planifié mais jamais créé ne consomme aucun secret."""
    appels: list[str] = []

    def generer(politique: PolitiqueMotDePasse) -> str:
        appels.append("appel")
        return "MotDePasse1!"

    _lancer(BoitierMemoire(), [_utilisateur("dupont")], simulation=True, generer=generer)
    assert appels == []


def test_aucun_mot_de_passe_genere_quand_USER_CREATE_echoue() -> None:
    boitier = BoitierMemoire()
    appels: list[str] = []

    def generer(politique: PolitiqueMotDePasse) -> str:
        appels.append("appel")
        return "MotDePasse1!"

    def refuser(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur":
            raise ErreurCommande(200, "uid interdit")

    boitier.declencheur = refuser
    rapport, _ = _lancer(boitier, [_utilisateur("admin")], generer=generer)
    assert appels == []
    assert rapport.comptes_crees == []
    assert rapport.echecs[0].operation == "USER CREATE"


def test_echec_isole_n_arrete_pas_le_lot() -> None:
    boitier = BoitierMemoire()

    def refuser_dupont(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "dupont":
            raise ErreurCommande(200, "uid interdit")

    boitier.declencheur = refuser_dupont
    rapport, _ = _lancer(boitier, [_utilisateur("dupont"), _utilisateur("legrand", ligne=3)])
    assert [compte.identifiant for compte in rapport.comptes_crees] == ["legrand"]
    assert len(rapport.echecs) == 1


def test_trois_reessais_de_mot_de_passe_puis_champ_vide() -> None:
    boitier = BoitierMemoire()
    tentatives = 0

    def toujours_refuser(operation: str, cible: str) -> None:
        nonlocal tentatives
        if operation == "definir_mot_de_passe":
            tentatives += 1
            raise ErreurCommande(200, "politique refusée")

    boitier.declencheur = toujours_refuser
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont")])
    assert tentatives == 4  # un appel initial puis trois réessais
    assert [compte.identifiant for compte in rapport.comptes_crees] == ["dupont"]
    assert rapport.comptes_crees[0].mot_de_passe == ""
    assert [compte.identifiant for compte in rapport.sans_mot_de_passe] == ["dupont"]
    textes = [evenement.texte for evenement in evenements if isinstance(evenement, Journal)]
    assert any("sans mot de passe" in texte for texte in textes)


def test_mot_de_passe_reussi_au_deuxieme_essai() -> None:
    boitier = BoitierMemoire()
    tentatives = 0

    def refuser_une_fois(operation: str, cible: str) -> None:
        nonlocal tentatives
        if operation == "definir_mot_de_passe":
            tentatives += 1
            if tentatives == 1:
                raise ErreurCommande(200, "transitoire")

    boitier.declencheur = refuser_une_fois
    rapport, _ = _lancer(boitier, [_utilisateur("dupont")])
    assert rapport.comptes_crees[0].mot_de_passe == "MotDePasse1!"
    assert rapport.sans_mot_de_passe == []


def test_echec_d_appartenance_signale_sans_reessai() -> None:
    boitier = BoitierMemoire(groupes=["compta"])

    def refuser(operation: str, cible: str) -> None:
        if operation == "ajouter_membre":
            raise ErreurCommande(200, "refusé")

    boitier.declencheur = refuser
    rapport, _ = _lancer(boitier, [_utilisateur("dupont", "compta")])
    assert rapport.comptes_crees[0].mot_de_passe == "MotDePasse1!"
    assert rapport.echecs[0].operation == "USER GROUP ADDUSER"
    assert [operation for operation, _ in boitier.journal_appels].count("ajouter_membre") == 1


def test_echec_de_creation_de_groupe_signale_et_lot_poursuivi() -> None:
    boitier = BoitierMemoire()

    def refuser(operation: str, cible: str) -> None:
        if operation == "creer_groupe":
            raise ErreurCommande(200, "guillemet double interdit")

    boitier.declencheur = refuser
    rapport, _ = _lancer(boitier, [_utilisateur("dupont", 'Groupe "A"')])
    assert [compte.identifiant for compte in rapport.comptes_crees] == ["dupont"]
    assert any(echec.operation == "USER GROUP CREATE" for echec in rapport.echecs)


def test_reconnexion_reconstruit_le_plan_au_lieu_de_rejouer() -> None:
    """Après coupure, l'outil relit l'état : le compte déjà créé tombe en « déjà présent »."""
    boitier = BoitierMemoire()
    coupures = 0

    def couper_apres_le_premier(operation: str, cible: str) -> None:
        nonlocal coupures
        if operation == "creer_utilisateur" and cible == "legrand" and coupures == 0:
            coupures += 1
            boitier.utilisateurs.append("legrand")  # le boîtier a exécuté avant la coupure
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_apres_le_premier
    rapport, _ = _lancer(
        boitier, [_utilisateur("dupont"), _utilisateur("legrand", ligne=3)]
    )
    assert boitier.utilisateurs.count("legrand") == 1
    assert boitier.connexions == 2
    assert rapport.interrompu is False


def test_trois_reconnexions_infructueuses_puis_arret_net() -> None:
    boitier = BoitierMemoire()

    def couper_toujours(operation: str, cible: str) -> None:
        if operation in {"creer_utilisateur", "connecter"} and boitier.connexions >= 1:
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_toujours
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont")])
    assert rapport.interrompu is True
    # Connexion initiale réussie, puis trois tentatives de reconnexion toutes refusées.
    assert [operation for operation, _ in boitier.journal_appels].count("connecter") == 4
    assert boitier.connexions == 1
    assert any(isinstance(evenement, Termine) for evenement in evenements)


def test_reprise_les_comptes_deja_crees_sont_ignores() -> None:
    boitier = BoitierMemoire(utilisateurs=["dupont"])
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont"), _utilisateur("legrand")])
    assert [compte.identifiant for compte in rapport.comptes_crees] == ["legrand"]
    plans = [evenement for evenement in evenements if isinstance(evenement, PlanPret)]
    assert [compte.identifiant for compte in plans[0].plan.comptes_ignores] == ["dupont"]


def test_progression_en_simulation_couvre_les_seules_lectures() -> None:
    _, evenements = _lancer(BoitierMemoire(), [_utilisateur("dupont", "compta")], simulation=True)
    progressions = [
        evenement for evenement in evenements if isinstance(evenement, Progression)
    ]
    assert progressions[-1] == Progression(accomplies=4, total=4)


def test_progression_en_reel_couvre_lectures_et_ecritures() -> None:
    _, evenements = _lancer(BoitierMemoire(), [_utilisateur("dupont", "compta")])
    progressions = [
        evenement for evenement in evenements if isinstance(evenement, Progression)
    ]
    # 4 lectures + 1 groupe + USER CREATE + USER PASSWORD + 1 ADDUSER
    assert progressions[-1] == Progression(accomplies=8, total=8)


def test_bascule_en_minuscules_signalee_au_journal() -> None:
    utilisateur = Utilisateur(
        ligne=2,
        identifiant="jean.dupont",
        identifiant_origine="Jean.Dupont",
        nom="Dupont",
        prenom="Jean",
        groupes=(),
    )
    _, evenements = _lancer(BoitierMemoire(), [utilisateur])
    textes = [evenement.texte for evenement in evenements if isinstance(evenement, Journal)]
    assert any("Jean.Dupont" in texte and "jean.dupont" in texte for texte in textes)


def test_deconnexion_meme_en_cas_d_arret() -> None:
    boitier = BoitierMemoire()
    _lancer(boitier, [_utilisateur("dupont")])
    assert boitier.connecte is False
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_execution_ecriture.py -q`
Attendu : `ImportError: cannot import name 'Patience'`.

- [ ] **Step 3: Compléter `execution.py`**

Ajouter aux imports et à la suite du module :

```python
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from stormshield_utilisateurs import motdepasse, plan as construction_plan
from stormshield_utilisateurs.boitier import Boitier, ErreurCommande, ErreurReseau
from stormshield_utilisateurs.modele import (
    CompteCree,
    Echec,
    EtatBoitier,
    PlancherPolitique,
    Plan,
    PolitiqueMotDePasse,
    Rapport,
    Utilisateur,
)


@dataclass(frozen=True)
class Patience:
    """Cadence des réessais. Injectable pour que les tests ne dorment pas."""

    reessais: int = 3
    delai: float = 2.0
    dormir: Callable[[float], None] = time.sleep


@dataclass(frozen=True)
class Journal:
    texte: str


@dataclass(frozen=True)
class PolitiqueLue:
    plancher: PlancherPolitique


@dataclass(frozen=True)
class PlanPret:
    plan: Plan


@dataclass(frozen=True)
class Progression:
    accomplies: int
    total: int


@dataclass(frozen=True)
class Termine:
    rapport: Rapport


@dataclass(frozen=True)
class Echoue:
    message: str


Evenement = Journal | PolitiqueLue | PlanPret | Progression | Termine | Echoue
Emetteur = Callable[[Evenement], None]


class _Compteur:
    """Porte l'avancement de la barre de progression."""

    def __init__(self, emettre: Emetteur) -> None:
        self.accomplies = 0
        self.total = 0
        self._emettre = emettre

    def avancer(self) -> None:
        self.accomplies += 1
        self._emettre(Progression(self.accomplies, self.total))


def executer(
    boitier: Boitier,
    utilisateurs: Sequence[Utilisateur],
    politique: PolitiqueMotDePasse,
    *,
    simulation: bool,
    emettre: Emetteur,
    patience: Patience = Patience(),
    generer_mot_de_passe: Callable[[PolitiqueMotDePasse], str] = motdepasse.generer,
) -> Rapport:
    """Connexion, lecture, plan, puis écritures si Simulation est décochée.

    La connexion et la lecture ont lieu dans les deux modes : sans elles l'outil
    ne pourrait pas dire « déjà présent ».
    """
    rapport = Rapport()
    compteur = _Compteur(emettre)
    for utilisateur in utilisateurs:
        if utilisateur.bascule_minuscules:
            emettre(
                Journal(
                    f"ligne {utilisateur.ligne} : identifiant {utilisateur.identifiant_origine} "
                    f"basculé en minuscules -> {utilisateur.identifiant}"
                )
            )
    boitier.connecter()
    try:
        etat = lire_etat(boitier)
        emettre(PolitiqueLue(etat.plancher))
        plan_courant = construction_plan.construire(utilisateurs, etat)
        compteur.total = NOMBRE_LECTURES + (
            0 if simulation else plan_courant.nombre_operations()
        )
        for _ in range(NOMBRE_LECTURES):
            compteur.avancer()
        emettre(PlanPret(plan_courant))
        if not simulation:
            _appliquer(
                boitier,
                utilisateurs,
                plan_courant,
                politique,
                rapport,
                compteur,
                emettre,
                patience,
                generer_mot_de_passe,
            )
    finally:
        try:
            boitier.deconnecter()
        except ErreurBoitier:
            # La déconnexion d'une liaison déjà perdue n'ajoute rien au rapport.
            pass
    emettre(Termine(rapport))
    return rapport


def _appliquer(
    boitier: Boitier,
    utilisateurs: Sequence[Utilisateur],
    plan_courant: Plan,
    politique: PolitiqueMotDePasse,
    rapport: Rapport,
    compteur: _Compteur,
    emettre: Emetteur,
    patience: Patience,
    generer_mot_de_passe: Callable[[PolitiqueMotDePasse], str],
) -> None:
    """Boucle d'écriture. Sur perte de liaison : reconnecte, reconstruit, reprend."""
    reste = plan_courant
    while True:
        try:
            _creer_groupes(boitier, reste, rapport, compteur, emettre)
            _creer_comptes(
                boitier, reste, politique, rapport, compteur, emettre,
                patience, generer_mot_de_passe,
            )
            return
        except ErreurReseau:
            emettre(Journal("liaison perdue, tentative de reconnexion"))
            if not _reconnecter(boitier, patience, emettre):
                rapport.interrompu = True
                emettre(
                    Journal(
                        "arrêt : liaison irrécupérable. Ce qui est créé reste créé, "
                        "le CSV des mots de passe couvre les comptes réellement créés."
                    )
                )
                return
            # On ne rejoue jamais la commande interrompue : on relit et on replanifie.
            reste = construction_plan.construire(utilisateurs, lire_etat(boitier))
            emettre(PlanPret(reste))


def _reconnecter(boitier: Boitier, patience: Patience, emettre: Emetteur) -> bool:
    for tentative in range(1, patience.reessais + 1):
        patience.dormir(patience.delai)
        try:
            boitier.connecter()
        except ErreurBoitier:
            emettre(Journal(f"reconnexion {tentative}/{patience.reessais} échouée"))
            continue
        emettre(Journal(f"reconnecté à la tentative {tentative}"))
        return True
    return False


def _creer_groupes(
    boitier: Boitier, plan_courant: Plan, rapport: Rapport,
    compteur: _Compteur, emettre: Emetteur,
) -> None:
    for groupe in plan_courant.groupes_a_creer:
        if groupe.nom in rapport.groupes_crees:
            continue
        try:
            boitier.creer_groupe(groupe.nom)
        except ErreurCommande as erreur:
            rapport.echecs.append(Echec(groupe.nom, "USER GROUP CREATE", str(erreur)))
            emettre(Journal(f"groupe {groupe.nom} : échec de création ({erreur})"))
        else:
            rapport.groupes_crees.append(groupe.nom)
            emettre(Journal(f"groupe {groupe.nom} : créé"))
        compteur.avancer()


def _creer_comptes(
    boitier: Boitier, plan_courant: Plan, politique: PolitiqueMotDePasse,
    rapport: Rapport, compteur: _Compteur, emettre: Emetteur,
    patience: Patience, generer_mot_de_passe: Callable[[PolitiqueMotDePasse], str],
) -> None:
    deja_traites = {compte.identifiant for compte in rapport.comptes_crees}
    for utilisateur in plan_courant.comptes_a_creer:
        if utilisateur.identifiant in deja_traites:
            continue
        try:
            boitier.creer_utilisateur(
                utilisateur.identifiant, utilisateur.nom, utilisateur.prenom,
                plan_courant.domaine,
            )
        except ErreurCommande as erreur:
            rapport.echecs.append(Echec(utilisateur.identifiant, "USER CREATE", str(erreur)))
            emettre(Journal(f"{utilisateur.identifiant} : échec de création ({erreur})"))
            # Aucun mot de passe n'a été généré : le secret n'est pas consommé.
            compteur.avancer()
            continue
        compteur.avancer()
        # Génération au moment de la création effective, jamais à la construction du plan.
        secret = generer_mot_de_passe(politique)
        retenu = _definir_mot_de_passe(
            boitier, utilisateur.identifiant, secret, rapport, emettre, patience
        )
        compteur.avancer()
        rapport.comptes_crees.append(CompteCree(utilisateur.identifiant, retenu))
        emettre(Journal(f"{utilisateur.identifiant} : créé"))
        for groupe in utilisateur.groupes:
            try:
                boitier.ajouter_membre(groupe, utilisateur.identifiant)
            except ErreurCommande as erreur:
                rapport.echecs.append(
                    Echec(utilisateur.identifiant, "USER GROUP ADDUSER", str(erreur))
                )
                emettre(
                    Journal(f"{utilisateur.identifiant} : non rattaché à {groupe} ({erreur})")
                )
            compteur.avancer()


def _definir_mot_de_passe(
    boitier: Boitier, identifiant: str, secret: str, rapport: Rapport,
    emettre: Emetteur, patience: Patience,
) -> str:
    """Un appel puis jusqu'à `reessais` réessais. Rend le secret, ou "" en cas d'abandon."""
    for tentative in range(patience.reessais + 1):
        try:
            boitier.definir_mot_de_passe(identifiant, secret)
        except ErreurCommande as erreur:
            if tentative == patience.reessais:
                rapport.echecs.append(Echec(identifiant, "USER PASSWORD", str(erreur)))
                emettre(
                    Journal(
                        f"{identifiant} : créé sans mot de passe — à reprendre à la main "
                        f"({erreur})"
                    )
                )
                return ""
            patience.dormir(patience.delai)
        else:
            return secret
    return ""
```

Importer aussi `ErreurBoitier` depuis `boitier`.

- [ ] **Step 4: Faire passer, un test à la fois**

```bash
.venv/bin/pytest tests/test_execution_ecriture.py -q
```
Attendu : les 16 tests passent. Points de vigilance connus :
- `test_progression_en_reel_couvre_lectures_et_ecritures` fixe le contrat de la barre : si le compte n'y est pas, c'est `nombre_operations()` ou un `compteur.avancer()` manquant, pas le test.
- `test_trois_reconnexions_infructueuses_puis_arret_net` exige que l'échec de `connecter` lève bien `ErreurReseau` depuis le déclencheur.

- [ ] **Step 5: Vérifier l'ensemble de la suite**

```bash
.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy
```

- [ ] **Step 6: Commit**

```bash
git add stormshield_utilisateurs/execution.py tests/test_execution_ecriture.py
git commit -m "feat: application du plan, reessais et reconnexion"
```

**Fini quand :** les 16 tests passent, dont nommément `test_aucun_mot_de_passe_genere_en_simulation`, `test_trois_reessais_de_mot_de_passe_puis_champ_vide`, `test_reconnexion_reconstruit_le_plan_au_lieu_de_rejouer` et `test_simulation_lit_mais_n_ecrit_pas`.

---

## Task 9: CSV de restitution des mots de passe

**Files:**
- Create: `stormshield_utilisateurs/sortie.py`
- Test: `tests/test_sortie.py`

**Interfaces:**
- Consumes: `modele.CompteCree`.
- Produces: `def ecrire_mots_de_passe(chemin: Path, comptes: Sequence[CompteCree]) -> None`

- [ ] **Step 1: Écrire les tests**

`tests/test_sortie.py` :

```python
"""Le CSV de restitution est la seule écriture disque de l'outil."""

from pathlib import Path

from stormshield_utilisateurs.modele import CompteCree
from stormshield_utilisateurs.sortie import ecrire_mots_de_passe


def test_entete_separateur_et_bom_pour_excel_francais(tmp_path: Path) -> None:
    fichier = tmp_path / "mdp.csv"
    ecrire_mots_de_passe(fichier, [CompteCree("dupont", "MotDePasse1!")])
    octets = fichier.read_bytes()
    assert octets.startswith(b"\xef\xbb\xbf")
    assert octets.decode("utf-8-sig").splitlines() == [
        "identifiant;mot_de_passe",
        "dupont;MotDePasse1!",
    ]


def test_compte_cree_sans_mot_de_passe_figure_avec_un_champ_vide(tmp_path: Path) -> None:
    """C'est de ce fichier que l'opérateur repart : l'en omettre serait le perdre."""
    fichier = tmp_path / "mdp.csv"
    ecrire_mots_de_passe(fichier, [CompteCree("dupont", ""), CompteCree("legrand", "Abc123!x")])
    assert fichier.read_text(encoding="utf-8-sig").splitlines()[1] == "dupont;"


def test_fichier_ecrit_meme_sans_aucun_compte(tmp_path: Path) -> None:
    fichier = tmp_path / "mdp.csv"
    ecrire_mots_de_passe(fichier, [])
    assert fichier.read_text(encoding="utf-8-sig").strip() == "identifiant;mot_de_passe"


def test_aucune_ecriture_ailleurs_que_le_chemin_donne(tmp_path: Path) -> None:
    fichier = tmp_path / "sous" / "mdp.csv"
    fichier.parent.mkdir()
    ecrire_mots_de_passe(fichier, [CompteCree("dupont", "Abc123!x")])
    assert [chemin.name for chemin in tmp_path.rglob("*.csv")] == ["mdp.csv"]
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_sortie.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Écrire `sortie.py`**

```python
"""CSV des mots de passe. Écrit uniquement à l'emplacement désigné par l'opérateur."""

import csv
from collections.abc import Sequence
from pathlib import Path

from stormshield_utilisateurs.modele import CompteCree


def ecrire_mots_de_passe(chemin: Path, comptes: Sequence[CompteCree]) -> None:
    """UTF-8 avec BOM et séparateur ';' : Excel en français l'ouvre sans manipulation.

    Les comptes créés dont USER PASSWORD a échoué y figurent avec un champ vide.
    """
    with chemin.open("w", encoding="utf-8-sig", newline="") as fichier:
        redacteur = csv.writer(fichier, delimiter=";", lineterminator="\r\n")
        redacteur.writerow(["identifiant", "mot_de_passe"])
        for compte in comptes:
            redacteur.writerow([compte.identifiant, compte.mot_de_passe])
```

- [ ] **Step 4: Faire passer**

```bash
.venv/bin/pytest tests/test_sortie.py -q && .venv/bin/ruff check . && .venv/bin/mypy
```

- [ ] **Step 5: Commit**

```bash
git add stormshield_utilisateurs/sortie.py tests/test_sortie.py
git commit -m "feat: CSV de restitution des mots de passe"
```

**Fini quand :** les 4 tests passent et la restriction aux comptes réellement créés est portée par l'appelant (la fonction reçoit `rapport.comptes_crees`, jamais le plan).

---

## Task 10: Adaptateur SDK (marqueur `firewall`, prouvé par rien)

**Files:**
- Create: `stormshield_utilisateurs/boitier_sdk.py`
- Test: `tests/test_boitier_sdk.py`

**Interfaces:**
- Consumes: `boitier.Boitier`, `boitier.ErreurCommande`, `boitier.ErreurReseau`, `modele.PlancherPolitique`.
- Produces: `class BoitierSDK` — `__init__(self, hote: str, utilisateur: str, mot_de_passe: str, verifier_certificat: bool = True)`.

Ce module est **mince par construction** : traduction d'appels en chaînes de commande et lecture de `Response`. Toute logique qui pourrait en sortir doit en sortir. Ses tests hors marqueur ne portent que sur la **construction des chaînes de commande** et la **traduction des codes de retour**, qui sont du texte pur ; tout ce qui ouvre une session porte `@pytest.mark.firewall`.

- [ ] **Step 1: Écrire les tests sans boîtier (construction de chaînes) et la sentinelle marquée**

`tests/test_boitier_sdk.py` :

```python
"""L'adaptateur n'est prouvé par rien tant qu'aucun boîtier n'est joignable.
Seules les parties textuelles se testent hors ligne."""

import pytest

from stormshield_utilisateurs.boitier_sdk import (
    BoitierSDK,
    commande_ajouter_membre,
    commande_creer_groupe,
    commande_creer_utilisateur,
    lire_plancher,
)


def test_commande_de_creation_d_utilisateur() -> None:
    assert commande_creer_utilisateur("dupont", "Dupont", "Marie", "interne.local") == (
        "USER CREATE uid=dupont name=Dupont gname=Marie domainname=interne.local"
    )


def test_prenom_vide_omet_gname() -> None:
    assert commande_creer_utilisateur("dupont", "Dupont", "", "interne.local") == (
        "USER CREATE uid=dupont name=Dupont domainname=interne.local"
    )


def test_nom_de_groupe_transmis_verbatim_entre_guillemets() -> None:
    assert commande_creer_groupe("compta bis") == 'USER GROUP CREATE "compta bis"'


def test_commande_d_appartenance() -> None:
    assert commande_ajouter_membre("compta", "dupont") == "USER GROUP ADDUSER compta dupont"


def test_lecture_du_plancher_de_politique() -> None:
    donnees = {"MinLength": "12", "MinSetOfChars": "3", "MinEntropy": "40"}
    plancher = lire_plancher(donnees)
    assert (plancher.longueur_min, plancher.nombre_classes_min, plancher.entropie_min) == (
        12,
        3,
        40,
    )


def test_plancher_absent_retombe_sur_zero() -> None:
    """Un boîtier sans politique déclarée ne doit pas faire planter la lecture."""
    plancher = lire_plancher({})
    assert (plancher.longueur_min, plancher.nombre_classes_min) == (0, 0)


@pytest.mark.firewall
def test_connexion_a_un_boitier_reel() -> None:
    """Exclu par défaut. À exécuter avec `pytest -m firewall` et des identifiants fournis
    par variables d'environnement, jamais en dur."""
    import os

    boitier = BoitierSDK(
        hote=os.environ["SNS_HOTE"],
        utilisateur=os.environ["SNS_UTILISATEUR"],
        mot_de_passe=os.environ["SNS_MOT_DE_PASSE"],
        verifier_certificat=False,
    )
    boitier.connecter()
    try:
        assert isinstance(boitier.lister_annuaires(), list)
    finally:
        boitier.deconnecter()
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_boitier_sdk.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Écrire `boitier_sdk.py`**

```python
"""Seul module du paquet à importer le SDK Stormshield. Écrit contre la documentation,
prouvé par aucun test tant qu'aucun boîtier n'est joignable."""

from typing import Any

from stormshield.sns.sslclient import SSLClient

from stormshield_utilisateurs.boitier import ErreurCommande, ErreurReseau
from stormshield_utilisateurs.modele import PlancherPolitique


def commande_creer_utilisateur(identifiant: str, nom: str, prenom: str, domaine: str) -> str:
    morceaux = [f"USER CREATE uid={identifiant}", f"name={nom}"]
    if prenom:
        morceaux.append(f"gname={prenom}")
    morceaux.append(f"domainname={domaine}")
    return " ".join(morceaux)


def commande_creer_groupe(nom: str) -> str:
    """Nom transmis verbatim entre guillemets : un guillemet dans le nom ne passe pas."""
    return f'USER GROUP CREATE "{nom}"'


def commande_ajouter_membre(groupe: str, identifiant: str) -> str:
    return f"USER GROUP ADDUSER {groupe} {identifiant}"


def lire_plancher(donnees: dict[str, Any]) -> PlancherPolitique:
    def entier(cle: str) -> int:
        try:
            return int(donnees.get(cle, 0))
        except (TypeError, ValueError):
            return 0

    return PlancherPolitique(
        longueur_min=entier("MinLength"),
        nombre_classes_min=entier("MinSetOfChars"),
        entropie_min=entier("MinEntropy"),
    )


class BoitierSDK:
    """Adaptateur : une commande par aller-retour, jamais plus d'une session."""

    def __init__(
        self, hote: str, utilisateur: str, mot_de_passe: str, verifier_certificat: bool = True
    ) -> None:
        self._hote = hote
        self._utilisateur = utilisateur
        self._mot_de_passe = mot_de_passe
        # Le contournement n'est jamais câblé en dur : il vient d'une case décochée
        # par l'opérateur, à chaque session.
        self._verifier = verifier_certificat
        self._client: SSLClient | None = None

    def connecter(self) -> None:
        try:
            self._client = SSLClient(
                user=self._utilisateur,
                password=self._mot_de_passe,
                host=self._hote,
                sslverifypeer=self._verifier,
                sslverifyhost=self._verifier,
            )
        except Exception as erreur:  # noqa: BLE001 - le SDK ne documente pas ses exceptions
            raise ErreurReseau(f"connexion impossible à {self._hote} : {erreur}") from erreur

    def deconnecter(self) -> None:
        if self._client is not None:
            self._client.disconnect()
            self._client = None

    def _envoyer(self, commande: str) -> Any:
        if self._client is None:
            raise ErreurReseau("aucune session ouverte")
        try:
            reponse = self._client.send_command(commande)
        except Exception as erreur:  # noqa: BLE001 - idem
            raise ErreurReseau(f"liaison perdue pendant « {commande} » : {erreur}") from erreur
        # Response.__bool__ est vrai lorsque 100 <= ret < 200.
        if not reponse:
            raise ErreurCommande(int(reponse.ret), str(reponse.msg))
        return reponse

    def lister_annuaires(self) -> list[str]:
        reponse = self._envoyer("CONFIG LDAP LIST")
        return [
            str(entree["domain"])
            for entree in _sections(reponse)
            if entree.get("domain")
        ]

    def initialiser_annuaire(
        self, domainname: str, organisation: str, dc: str, mot_de_passe: str
    ) -> None:
        # realbind n'est pas transmis : la v1 s'en remet au défaut du boîtier.
        self._envoyer(
            f"CONFIG LDAP INITIALIZE domainname={domainname} o={organisation} "
            f"dc={dc} password={mot_de_passe}"
        )

    def activer_annuaire(self) -> None:
        self._envoyer("CONFIG LDAP ACTIVATE")

    def lire_politique(self) -> PlancherPolitique:
        reponse = self._envoyer("CONFIG PASSWDPOLICY SHOW")
        fusion: dict[str, Any] = {}
        for section in _sections(reponse):
            fusion.update(section)
        return lire_plancher(fusion)

    def lister_utilisateurs(self) -> list[str]:
        reponse = self._envoyer("USER LIST")
        return [str(entree["name"]) for entree in _sections(reponse) if entree.get("name")]

    def lister_groupes(self) -> list[str]:
        reponse = self._envoyer("USER GROUP LIST")
        return [str(entree["name"]) for entree in _sections(reponse) if entree.get("name")]

    def creer_groupe(self, nom: str) -> None:
        self._envoyer(commande_creer_groupe(nom))

    def creer_utilisateur(self, identifiant: str, nom: str, prenom: str, domaine: str) -> None:
        self._envoyer(commande_creer_utilisateur(identifiant, nom, prenom, domaine))

    def definir_mot_de_passe(self, identifiant: str, mot_de_passe: str) -> None:
        # Le boîtier ne journalise pas les arguments de cette commande.
        self._envoyer(f"USER PASSWORD dn={identifiant} password={mot_de_passe}")

    def ajouter_membre(self, groupe: str, identifiant: str) -> None:
        self._envoyer(commande_ajouter_membre(groupe, identifiant))


def _sections(reponse: Any) -> list[dict[str, Any]]:
    """Aplati le `data` du SDK en une liste de dictionnaires. La forme exacte du `data`
    n'est pas prouvée : elle est à confirmer au premier boîtier joignable (cahier de recette)."""
    donnees = getattr(reponse, "data", None) or []
    lignes: list[dict[str, Any]] = []
    for section in donnees:
        contenu = section.get("section", section) if isinstance(section, dict) else section
        if isinstance(contenu, dict):
            lignes.append(contenu)
        elif isinstance(contenu, list):
            lignes.extend(entree for entree in contenu if isinstance(entree, dict))
    return lignes
```

- [ ] **Step 4: Vérifier la conformité au Protocol par mypy**

Ajouter à la fin de `tests/test_boitier_sdk.py` :

```python
def test_l_adaptateur_satisfait_le_protocol() -> None:
    from stormshield_utilisateurs.boitier import Boitier

    def accepter(boitier: Boitier) -> None:
        assert boitier is not None

    accepter(BoitierSDK("10.0.0.1", "admin", "secret-factice"))
```

Run: `.venv/bin/pytest tests/test_boitier_sdk.py -q && .venv/bin/mypy`
Attendu : 7 tests passés, 1 dé-sélectionné (le marqué `firewall`), mypy silencieux — c'est mypy, pas le test, qui prouve la conformité au Protocol.

- [ ] **Step 5: Commit**

```bash
git add stormshield_utilisateurs/boitier_sdk.py tests/test_boitier_sdk.py
git commit -m "feat: adaptateur SDK stormshield.sns.sslclient"
```

**Fini quand :** `grep -rl "stormshield.sns" stormshield_utilisateurs/` ne rend que `boitier_sdk.py`, `pytest -q` ne collecte pas le test marqué, et `pytest -m firewall --collect-only` le collecte.

---

## Task 11: Fenêtre tkinter et point d'entrée

**Files:**
- Create: `stormshield_utilisateurs/fenetre.py`
- Create: `stormshield_utilisateurs/__main__.py`
- Test: `tests/test_fenetre.py`

**Interfaces:**
- Consumes: tâches 3, 4, 7, 8, 9, 10.
- Produces:
  - `def politique_a_afficher(politique_courante: PolitiqueMotDePasse | None, plancher: PlancherPolitique) -> PolitiqueMotDePasse` — pré-remplit à la première lecture, **ne réécrit jamais** un réglage durci.
  - `class PompeEvenements` : `__init__(self, file: queue.Queue[Evenement], appliquer: Callable[[Evenement], None], planifier: Callable[[int, Callable[[], None]], None], periode_ms: int = 100)`, méthode `tour() -> None`, attribut `active: bool`.
  - `class Fenetre` : `__init__(self)`, `lancer(self) -> None`.
  - `def lancer() -> None` — construit et lance la fenêtre.

**Comportements subtils :** le thread ne touche aucun widget ; la file est vidée par `after()` ; la politique durcie survit à une relecture du boîtier.

**Note de test :** `import tkinter` fonctionne sans serveur graphique ; seul `tkinter.Tk()` échoue. Les tests de cette tâche portent donc sur `politique_a_afficher` et `PompeEvenements`, qui n'instancient aucun widget. Le reste de la fenêtre est couvert par le cahier de recette (tâche 12).

- [ ] **Step 1: Écrire les tests**

`tests/test_fenetre.py` :

```python
"""Seule la logique sans widget est testée ici ; l'IHM relève du cahier de recette."""

import queue
from collections.abc import Callable

from stormshield_utilisateurs.execution import Evenement, Journal, Progression, Termine
from stormshield_utilisateurs.fenetre import PompeEvenements, politique_a_afficher
from stormshield_utilisateurs.modele import PlancherPolitique, PolitiqueMotDePasse, Rapport

PLANCHER = PlancherPolitique(longueur_min=12, nombre_classes_min=3, entropie_min=0)


def test_premiere_lecture_pre_remplit_la_politique() -> None:
    politique = politique_a_afficher(None, PLANCHER)
    assert politique.longueur >= PLANCHER.longueur_min
    assert politique.nombre_classes() >= PLANCHER.nombre_classes_min


def test_relecture_ne_reecrit_jamais_un_reglage_durci() -> None:
    """Un réglage effacé par un rafraîchissement silencieux serait pire que pas de
    rafraîchissement du tout."""
    durcie = PolitiqueMotDePasse(
        longueur=32, minuscules=True, majuscules=True, chiffres=True, speciaux=True
    )
    assert politique_a_afficher(durcie, PLANCHER) is durcie
    assert politique_a_afficher(durcie, PlancherPolitique(20, 4, 0)) is durcie


def test_la_pompe_vide_la_file_et_se_replanifie() -> None:
    file: queue.Queue[Evenement] = queue.Queue()
    file.put(Journal("bonjour"))
    file.put(Progression(1, 4))
    recus: list[Evenement] = []
    replanifications: list[int] = []

    def planifier(delai_ms: int, rappel: Callable[[], None]) -> None:
        replanifications.append(delai_ms)

    pompe = PompeEvenements(file, recus.append, planifier, periode_ms=100)
    pompe.tour()
    assert recus == [Journal("bonjour"), Progression(1, 4)]
    assert replanifications == [100]
    assert pompe.active is True


def test_la_pompe_s_arrete_sur_Termine() -> None:
    file: queue.Queue[Evenement] = queue.Queue()
    file.put(Termine(Rapport()))
    recus: list[Evenement] = []
    replanifications: list[int] = []
    pompe = PompeEvenements(
        file, recus.append, lambda delai, rappel: replanifications.append(delai)
    )
    pompe.tour()
    assert isinstance(recus[0], Termine)
    assert pompe.active is False
    assert replanifications == []


def test_la_pompe_sur_file_vide_se_replanifie_sans_rien_appliquer() -> None:
    file: queue.Queue[Evenement] = queue.Queue()
    recus: list[Evenement] = []
    replanifications: list[int] = []
    pompe = PompeEvenements(
        file, recus.append, lambda delai, rappel: replanifications.append(delai)
    )
    pompe.tour()
    assert recus == []
    assert replanifications == [100]
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_fenetre.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Écrire la partie testable de `fenetre.py`**

```python
"""Fenêtre unique tkinter. Ne contient aucune décision : elle câble les autres modules."""

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from stormshield_utilisateurs import lecture, motdepasse, sortie
from stormshield_utilisateurs.boitier_sdk import BoitierSDK
from stormshield_utilisateurs.execution import (
    AnnuaireAbsent,
    AnnuairesMultiples,
    Echoue,
    Evenement,
    Journal,
    PlanPret,
    PolitiqueLue,
    Progression,
    Termine,
    creer_annuaire,
    executer,
)
from stormshield_utilisateurs.modele import PlancherPolitique, PolitiqueMotDePasse, Rapport

PERIODE_POMPE_MS = 100


def politique_a_afficher(
    politique_courante: PolitiqueMotDePasse | None, plancher: PlancherPolitique
) -> PolitiqueMotDePasse:
    """Pré-remplissage à la première lecture seulement ; les relectures ne touchent
    que le plancher affiché."""
    if politique_courante is not None:
        return politique_courante
    return motdepasse.proposer(plancher)


class PompeEvenements:
    """Vide la file d'événements dans le fil de l'interface. Le thread d'exécution
    n'appelle jamais un widget : il ne fait que déposer dans cette file."""

    def __init__(
        self,
        file: "queue.Queue[Evenement]",
        appliquer: Callable[[Evenement], None],
        planifier: Callable[[int, Callable[[], None]], None],
        periode_ms: int = PERIODE_POMPE_MS,
    ) -> None:
        self._file = file
        self._appliquer = appliquer
        self._planifier = planifier
        self._periode_ms = periode_ms
        self.active = True

    def tour(self) -> None:
        while True:
            try:
                evenement = self._file.get_nowait()
            except queue.Empty:
                break
            self._appliquer(evenement)
            if isinstance(evenement, Termine | Echoue):
                self.active = False
        if self.active:
            self._planifier(self._periode_ms, self.tour)
```

- [ ] **Step 4: Faire passer les tests de la pompe**

```bash
.venv/bin/pytest tests/test_fenetre.py -q
```
Attendu : 5 tests passés.

- [ ] **Step 5: Écrire la classe `Fenetre`**

À la suite de `fenetre.py`. Disposition conforme au croquis de la spec : hôte, compte, mot de passe, fichier + *Parcourir*, longueur et quatre cases de classes (grisées tant qu'aucune politique n'a été lue), libellé du plancher, case *Simulation* cochée, case *Vérifier le certificat du firewall* cochée, bouton *Lancer*, zone de journal `tk.Text` sélectionnable, `ttk.Progressbar`, bouton *Enregistrer les mots de passe…* désactivé.

```python
class Fenetre:
    def __init__(self) -> None:
        self.racine = tk.Tk()
        self.racine.title("Injection utilisateurs SNS")
        self.file: queue.Queue[Evenement] = queue.Queue()
        self.politique: PolitiqueMotDePasse | None = None
        self.plancher: PlancherPolitique | None = None
        self.rapport = Rapport()
        self._construire_widgets()

    # --- câblage ---------------------------------------------------------

    def _au_lancement(self) -> None:
        """Appelé par le bouton Lancer. Lit le CSV ici (hors ligne), puis démarre le thread."""
        try:
            utilisateurs, rejets = lecture.lire(Path(self.champ_fichier.get()))
        except lecture.ColonnesManquantes as erreur:
            messagebox.showerror("Fichier invalide", str(erreur))
            return
        except OSError as erreur:
            messagebox.showerror("Fichier illisible", str(erreur))
            return
        self._afficher_rejets(rejets)
        if self.politique is not None and self.plancher is not None:
            problemes = motdepasse.violations(self.politique, self.plancher)
            if problemes:
                messagebox.showerror("Politique refusée", "\n".join(problemes))
                return
        self.bouton_lancer.config(state=tk.DISABLED)
        fil = threading.Thread(
            target=self._travail, args=(utilisateurs,), daemon=True
        )
        fil.start()
        pompe = PompeEvenements(self.file, self._appliquer, self._planifier)
        pompe.tour()

    def _planifier(self, delai_ms: int, rappel: Callable[[], None]) -> None:
        self.racine.after(delai_ms, rappel)

    def _travail(self, utilisateurs: list) -> None:  # type: ignore[type-arg]
        """Tourne dans un thread : ne touche aucun widget, ne fait que déposer
        des événements dans la file."""
        boitier = BoitierSDK(
            hote=self.champ_hote.get(),
            utilisateur=self.champ_compte.get(),
            mot_de_passe=self.champ_mot_de_passe.get(),
            verifier_certificat=bool(self.var_certificat.get()),
        )
        politique = self.politique or motdepasse.proposer(PlancherPolitique(0, 0, 0))
        try:
            self.rapport = executer(
                boitier,
                utilisateurs,
                politique,
                simulation=bool(self.var_simulation.get()),
                emettre=self.file.put,
            )
        except AnnuaireAbsent:
            self.file.put(Echoue("ANNUAIRE_ABSENT"))
        except AnnuairesMultiples as erreur:
            self.file.put(Echoue(str(erreur)))
        except Exception as erreur:  # noqa: BLE001 - tout échec doit revenir à l'écran
            self.file.put(Echoue(str(erreur)))

    def _appliquer(self, evenement: Evenement) -> None:
        """Tourne dans le fil de l'interface : seul endroit qui touche les widgets."""
        match evenement:
            case Journal(texte):
                self._ecrire(texte)
            case PolitiqueLue(plancher):
                self.plancher = plancher
                self.politique = politique_a_afficher(self.politique, plancher)
                self._activer_champs_politique()
            case PlanPret(plan):
                self._afficher_plan(plan)
            case Progression(accomplies, total):
                self.barre.config(maximum=max(total, 1), value=accomplies)
                self.etiquette_progression.config(text=f"{accomplies} / {total}")
            case Termine(rapport):
                self.rapport = rapport
                self.bouton_lancer.config(state=tk.NORMAL)
                if rapport.comptes_crees:
                    self.bouton_enregistrer.config(state=tk.NORMAL)
                self._afficher_rapport(rapport)
            case Echoue(message):
                self.bouton_lancer.config(state=tk.NORMAL)
                if message == "ANNUAIRE_ABSENT":
                    self._ouvrir_fenetre_annuaire()
                else:
                    messagebox.showerror("Arrêt", message)

    def _enregistrer_mots_de_passe(self) -> None:
        chemin = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")]
        )
        if not chemin:
            return
        sortie.ecrire_mots_de_passe(Path(chemin), self.rapport.comptes_crees)
        self._ecrire(f"mots de passe enregistrés dans {chemin}")

    def lancer(self) -> None:
        self.racine.mainloop()


def lancer() -> None:
    Fenetre().lancer()
```

Détails à respecter dans `_construire_widgets`, `_afficher_plan`, `_afficher_rapport` et `_ouvrir_fenetre_annuaire` :

- *Simulation* cochée par défaut, *Vérifier le certificat* cochée par défaut ; le libellé de cette dernière est : `Vérifier le certificat du firewall (décoché : identifiants et mots de passe générés transitent dans une session interceptable)`.
- Champs de politique créés en `state=tk.DISABLED` ; `_activer_champs_politique` les passe en `NORMAL` et met à jour l'étiquette `politique du boîtier : MinLength=…, MinSet=…, MinEntropy=…`.
- `_afficher_plan` écrit dans l'ordre : `N lignes lues, M rejets`, une ligne par rejet (`ligne 4 : jean dupont — identifiant : caractère interdit`), `Groupes à créer : compta_bis (1 membre)` (accord « membre » / « membres »), puis une ligne par compte à créer, une par compte ignoré (`legrand : déjà présent, ignoré`), puis `Orphelins sur le boîtier : martin`.
- `_afficher_rapport` ajoute, si `rapport.sans_mot_de_passe` n'est pas vide, une section intitulée exactement `Comptes créés sans mot de passe — à reprendre`, distincte des rejets, des échecs et des orphelins.
- `tk.Text` en `state=tk.DISABLED` entre deux écritures mais sélectionnable et copiable (`Ctrl-C` fonctionne sur un `Text` désactivé).
- `_ouvrir_fenetre_annuaire` : `tk.Toplevel` demandant `domainname`, `o`, `dc` et le mot de passe de `cn=StormshieldAdmin` (saisi par l'opérateur, jamais généré ni conservé), bouton *Créer l'annuaire*, texte `Cette opération ne se refait pas.` ; sur validation, appelle `creer_annuaire` dans un thread et redemande à l'opérateur de relancer.
- Aucun champ de port : 443, valeur par défaut du SDK.

- [ ] **Step 6: Écrire `__main__.py`**

```python
"""Point d'entrée. Cible de PyInstaller."""

from stormshield_utilisateurs.fenetre import lancer

if __name__ == "__main__":
    lancer()
```

- [ ] **Step 7: Vérifier**

```bash
.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy
```
Puis, sur une machine avec affichage : `.venv/bin/python -m stormshield_utilisateurs` doit ouvrir la fenêtre, champs de politique grisés, *Simulation* et *Vérifier le certificat* cochées, *Enregistrer les mots de passe…* inactif.

- [ ] **Step 8: Commit**

```bash
git add stormshield_utilisateurs/fenetre.py stormshield_utilisateurs/__main__.py \
        tests/test_fenetre.py
git commit -m "feat: fenetre tkinter et point d'entree"
```

**Fini quand :** les 5 tests passent, `grep -n "tk\." stormshield_utilisateurs/fenetre.py` ne montre aucun appel de widget dans `_travail`, et la fenêtre s'ouvre avec les valeurs par défaut attendues.

---

## Task 12: Empaquetage, README et cahier de recette

**Files:**
- Create: `.github/workflows/exe.yml`
- Create: `docs/recette/2026-09-16-cahier-recette-v1.md`
- Modify: `README.md`
- Modify: `KANBAN.md`

**Interfaces:**
- Consumes: la totalité du paquet.
- Produces: un `.exe` publié en release GitHub sur tag `v*` ; le cahier de recette exécutable par un humain dès qu'un boîtier est joignable.

- [ ] **Step 1: Écrire `.github/workflows/exe.yml`**

```yaml
name: exe

on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  construire:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e '.[dev]'
      # --windowed empêche une console noire de s'ouvrir derrière la fenêtre tkinter.
      - run: >
          pyinstaller --onefile --windowed
          --name injection-utilisateurs-sns
          stormshield_utilisateurs/__main__.py
      - run: gh release create ${{ github.ref_name }} dist/injection-utilisateurs-sns.exe
          --title ${{ github.ref_name }}
          --notes "Executable non signe : SmartScreen avertit au premier lancement."
        env:
          GH_TOKEN: ${{ github.token }}
```

- [ ] **Step 2: Vérifier localement que PyInstaller trouve son point d'entrée**

```bash
.venv/bin/pyinstaller --onefile --name injection-utilisateurs-sns \
    stormshield_utilisateurs/__main__.py
ls dist/
```
Attendu : un binaire produit (sous Linux ici — il ne sert qu'à prouver que la cible et les imports sont corrects ; le `.exe` vient de `windows-latest`). Supprimer `build/`, `dist/` et le `.spec` ensuite, ils sont ignorés par git.

- [ ] **Step 3: Écrire le cahier de recette**

`docs/recette/2026-09-16-cahier-recette-v1.md`. Structure : un tableau `# | Cas | Préparation | Action | Résultat attendu | OK/KO`, avec au minimum ces cas — chacun couvre un comportement de la spec, y compris ceux déjà prouvés en unitaire :

| # | Cas |
|---|---|
| 1 | CSV valide, 3 comptes, 2 groupes, Simulation cochée : le plan s'affiche, rien n'est créé sur le boîtier |
| 2 | Même CSV, Simulation décochée : les 3 comptes et les 2 groupes existent, la barre atteint son total |
| 3 | Relancement à l'identique : les 3 comptes tombent en « déjà présent, ignoré », aucune écriture |
| 4 | CSV auquel manque la colonne `prenom` : message nommant `prenom`, aucune injection |
| 5 | CSV enregistré par Excel en français (cp1252, accents) : les accents des noms sont corrects sur le boîtier |
| 6 | CSV avec `Jean.Dupont` : le compte créé est `jean.dupont`, la bascule apparaît au journal |
| 7 | CSV contenant deux fois le même identifiant, l'un en majuscules : les deux lignes sont rejetées, aucun des deux comptes n'est créé |
| 8 | CSV où un compte déjà présent référence un groupe neuf : le groupe n'est pas créé |
| 9 | Groupe neuf à un seul membre : `Groupes à créer : X (1 membre)` s'affiche avant toute écriture |
| 10 | Compte présent sur le boîtier et absent du CSV : listé en orphelin, ni modifié ni supprimé |
| 11 | Politique : au premier *Lancer* les champs s'activent et affichent le plancher ; durcir la longueur, relancer, la valeur durcie est conservée |
| 12 | Politique réglée sous le plancher : le lancement est refusé avec un message nommant le minimum du boîtier |
| 13 | *Enregistrer les mots de passe…* : inactif avant toute création, actif après ; le CSV s'ouvre dans Excel sans manipulation, colonnes séparées |
| 14 | `uid` interdit (`admin`) dans le CSV : échec signalé sur ce compte, le lot continue |
| 15 | Nom de groupe contenant un guillemet double : échec de création de groupe signalé, les comptes sont créés |
| 16 | Câble réseau débranché en cours de lot : trois tentatives de reconnexion, arrêt net, journal cohérent avec l'état réel du boîtier |
| 17 | Reprise après l'arrêt du cas 16 : le lot reprend sur ce qui reste, rien n'est créé deux fois |
| 18 | Case *Vérifier le certificat* cochée sur un boîtier SNS 5.x sans CA installée : échec explicite ; décochée : la connexion passe |
| 19 | Boîtier sans annuaire LDAP : la fenêtre d'initialisation s'ouvre, l'écran principal reste nu ; après création, le lot reprend |
| 20 | Boîtier déclarant deux annuaires : arrêt net, message explicite, aucune écriture (à éprouver sur maquette) |
| 21 | 200 comptes : la fenêtre reste réactive pendant toute l'exécution, la barre progresse |
| 22 | `.exe` téléchargé depuis la release : SmartScreen avertit, l'outil s'ouvre après *Informations complémentaires → Exécuter quand même*, aucune console noire |

- [ ] **Step 4: Mettre à jour `README.md`**

Remplacer la section « État » — qui annonce aujourd'hui « repo amorcé, sans code » — et ajouter ce qu'un opérateur doit savoir. Le `README.md` reste générique et intemporel (aucune date, aucun avancement : cela vit dans `KANBAN.md`). Il doit contenir :

- **État** : v1 livrée, périmètre utilisateurs LDAP ; blacklists à venir.
- **Installation** : télécharger le `.exe` depuis les releases GitHub. Aucun Python à installer.
- **Avertissement SmartScreen**, en propre et sans ambiguïté : *« Le `.exe` n'est pas signé : la signature exige un certificat payant, hors périmètre v1. Au premier lancement, Windows SmartScreen affiche « Windows a protégé votre ordinateur ». Cliquer sur « Informations complémentaires » puis « Exécuter quand même ». Cet avertissement est attendu, il ne signale pas un défaut. »*
- **Format du CSV attendu** : `identifiant;nom;prenom;groupes`, séparateur `;`, en-tête obligatoire, colonnes dans n'importe quel ordre, `groupes` séparés par `|`, encodage Excel français accepté.
- **Ce que l'outil fait et ne fait pas** : il ajoute seulement ; aucune suppression, aucune modification d'un compte existant, appartenances comprises ; les orphelins sont signalés, jamais touchés.
- **Simulation** : cochée par défaut, elle lit le boîtier et n'écrit rien ; premier lancement en simulation, lecture du plan, puis décochage.
- **Mots de passe** : générés à la création, restitués uniquement par *Enregistrer les mots de passe…* à un emplacement choisi ; un champ vide signale un compte créé dont le mot de passe a échoué, à reprendre à la main.
- **Certificat** : case cochée par défaut ; décochée, la session est interceptable.
- **Pour qui développe** : `pip install -e '.[dev]'`, `ruff check .`, `mypy`, `pytest` (marqueur `firewall` exclu par défaut), renvoi vers `CLAUDE.md`, la spec et ce plan.

- [ ] **Step 5: Mettre à jour `KANBAN.md`**

- Déplacer « Plan d'implémentation de la v1 » de *À faire* vers *Terminé*, avec une entrée `### Injection d'utilisateurs v1 (date)` listant les modules livrés et les workflows.
- Conserver la section « Points à lever dès qu'un boîtier est joignable » et y ajouter : forme exacte du `data` rendu par `USER LIST`, `USER GROUP LIST`, `CONFIG LDAP LIST` et `CONFIG PASSWDPOLICY SHOW` — l'aplatissement de `boitier_sdk._sections` est une hypothèse.
- Ajouter le cahier de recette en *À faire* : « exécuter `docs/recette/2026-09-16-cahier-recette-v1.md` dès qu'un boîtier est joignable ».

- [ ] **Step 6: Vérification finale**

```bash
.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q
grep -rl "stormshield.sns" stormshield_utilisateurs/
git status --short
```
Attendu : trois succès, un seul fichier cité par `grep`, aucun fichier non suivi inattendu (pas de `dist/`, pas de CSV).

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/exe.yml docs/recette README.md KANBAN.md
git commit -m "docs: empaquetage exe, README operateur et cahier de recette v1"
```

**Fini quand :** `exe.yml` est committé, le cahier de recette couvre les 22 cas, le `README.md` porte l'avertissement SmartScreen et le format du CSV, et `KANBAN.md` dit où en est le projet.

---

## Revue du plan contre la spec

Passage section par section de la spec, avec la tâche qui la porte.

| Exigence de la spec | Tâche |
|---|---|
| Contrat du CSV, colonnes par nom, colonnes en trop ignorées | 3 |
| Colonne manquante = échec du fichier entier | 3 |
| Encodages BOM → UTF-8 → cp1252 | 3 |
| Espaces supprimés, bascule en minuscules signalée | 3 (bascule) et 8 (signalement au journal) |
| Numéros d'enregistrement | 3 |
| Motifs de rejet, liste close | 3 |
| Doublon : les deux lignes rejetées, après bascule | 3 |
| Segments de groupes vides et doublons internes | 3 |
| Rapprochement : créer / ignorer / orphelin | 6 |
| Groupes à créer sur les seuls comptes à créer, avec leur nombre de membres | 6 |
| Génération par `secrets`, à la création effective | 4 et 8 |
| Plancher lu sur le boîtier, durcissement préservé | 4, 7, 11 |
| `CONFIG PASSWDPOLICY SET` jamais envoyé | 5 (absent du Protocol), 10 |
| CSV de restitution, comptes créés seuls, champ vide si échec | 9 |
| Fenêtre unique, disposition, champs grisés, bouton inactif | 11 |
| Simulation cochée, se connecte et lit quand même | 8 et 11 |
| Certificat : case cochée, libellé explicite, jamais en dur | 10 et 11 |
| Aucun identifiant stocké | 10, 11 (saisie à chaque exécution) |
| `CONFIG LDAP LIST` : aucun / un / plusieurs | 7 |
| Séquence INITIALIZE → ACTIVATE → relecture | 7 et 11 |
| `domainname=` passé à `USER CREATE` | 8 et 10 |
| Modules et frontières, SDK isolé | 5, 10 et le tableau de disposition |
| Thread, file, `after()`, barre fonctionnelle | 8 (émission) et 11 (pompe) |
| Commandes utilisées, une par aller-retour | 10 |
| Panne réseau : 3 reconnexions, pas de rejeu, reconstruction | 8 |
| Échec isolé, lot poursuivi | 8 |
| 3 réessais de `USER PASSWORD`, section de journal dédiée | 8 et 11 |
| Échec d'`ADDUSER` signalé sans réessai | 8 |
| Idempotence par relecture, jamais par fichier d'état | 6 et 8 |
| Tests unitaires par module, `BoitierMemoire` | 3, 4, 5, 6, 7, 8, 9 |
| Marqueur `firewall` exclu par défaut | 1 et 10 |
| `ruff` puis `mypy` avant tout commit | 1, puis chaque tâche |
| Cahier de recette | 12 |
| `qualite.yml` | 1 |
| `exe.yml`, `--onefile --windowed`, release | 12 |
| Avertissement SmartScreen dans le `README.md` | 12 |

Aucune exigence de la spec n'est sans tâche. Les points laissés ouverts par la spec (« Points non vérifiés », « Hors périmètre v1 ») ne reçoivent délibérément aucune tâche ; ils sont reportés dans `KANBAN.md` à l'étape 12.

## Ce que ce plan a tranché lui-même

Points sur lesquels la spec ne se prononce pas et où une décision était nécessaire pour que les tâches soient exécutables. Ils sont réversibles ; si l'un heurte l'intention, c'est le plan qu'il faut corriger, pas la spec.

1. `boitier.py` (Protocol) et `boitier_sdk.py` (adaptateur) sont deux fichiers, là où la spec n'en nomme qu'un.
2. `PlancherPolitique` est distinct de `PolitiqueMotDePasse` : le plancher du boîtier compte des classes (`MinSetOfChars`), le réglage de l'opérateur les nomme.
3. « Trois réessais de `USER PASSWORD` » est lu comme un appel initial **plus** trois réessais (quatre appels), quand « trois tentatives de reconnexion » est lu comme trois tentatives au total.
4. Les doublons se comptent sur les identifiants par ailleurs valides ; une ligne cumulant plusieurs motifs porte un seul `Rejet` dont le motif les joint par ` ; `.
5. Les noms de colonnes de l'en-tête sont comparés après suppression des espaces, sensibles à la casse.
6. `ErreurCommande` (le boîtier refuse) et `ErreurReseau` (la liaison tombe) sont deux exceptions distinctes : c'est ce qui sépare un échec isolé d'une reconnexion.
7. Le jeu de caractères spéciaux générés exclut le guillemet double et l'espace.
