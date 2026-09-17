"""Vérifie que le paquet est importable et que le marqueur firewall est bien exclu."""

import ast
import sys
from pathlib import Path
from typing import Any, cast

import pytest

import stormshield_utilisateurs
from stormshield_utilisateurs.__main__ import texte_d_echec
from stormshield_utilisateurs.presentation import texte_de_demarrage_impossible

PRESENTATION = "stormshield_utilisateurs.presentation"


def test_le_paquet_a_une_docstring() -> None:
    assert stormshield_utilisateurs.__doc__ is not None


def test_le_marqueur_firewall_est_exclu_par_defaut() -> None:
    """Ce test échoue si un jour le marqueur cesse d'être exclu par addopts."""
    import subprocess

    resultat = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "test_exige_un_boitier" not in resultat.stdout


def test_le_texte_d_echec_reprend_celui_de_presentation() -> None:
    """Le repli ne doit pas remplacer le texte soigné quand celui-ci est atteignable."""
    erreur = ModuleNotFoundError("No module named 'tkinter'")
    assert texte_d_echec(erreur) == texte_de_demarrage_impossible(erreur)


def test_le_filet_tient_meme_si_presentation_ne_s_importe_pas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mode d'échec le plus probable d'une construction PyInstaller : le paquet n'est
    pas collecté. L'import tombait alors avant que le filet n'existe, la trace partait
    sur un `stderr` qu'un exécutable fenêtré n'a pas, et rien ne s'affichait.

    `None` dans `sys.modules` fait lever l'import : c'est la façon la plus directe de
    simuler un module absent du paquet gelé.
    """
    monkeypatch.setitem(cast(dict[str, Any], sys.modules), PRESENTATION, None)
    texte = texte_d_echec(ModuleNotFoundError("No module named 'stormshield_utilisateurs'"))
    assert "n'a pas pu démarrer" in texte
    assert "ModuleNotFoundError" in texte
    assert "No module named 'stormshield_utilisateurs'" in texte


def test_le_point_d_entree_n_importe_rien_du_paquet_au_niveau_module() -> None:
    """Le filet ne doit dépendre d'aucun import que son propre mode d'échec casse."""
    source = Path(stormshield_utilisateurs.__file__).with_name("__main__.py")
    arbre = ast.parse(source.read_text(encoding="utf-8"))
    importes: list[str] = []
    for noeud in arbre.body:
        if isinstance(noeud, ast.Import):
            importes.extend(alias.name for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom):
            importes.append(noeud.module or "")
    assert not [nom for nom in importes if nom.startswith("stormshield_utilisateurs")]


def _appelants_du_mot_de_passe(source: str) -> dict[str, set[str]]:
    """Pour chacune des deux façons d'atteindre l'écriture du mot de passe — le wrapper
    du module (`_definir_mot_de_passe(...)`) et l'opération protocolaire elle-même
    (`<objet>.definir_mot_de_passe(...)`, quel que soit l'objet qui la porte) — l'ensemble
    des noms de fonctions de ce source dont le corps contient un tel appel.

    Se fier au seul nom `_definir_mot_de_passe` laissait passer un appel direct à
    `boitier.definir_mot_de_passe(...)` : la même opération, sans passer par le wrapper.
    """
    arbre = ast.parse(source)
    appelants: dict[str, set[str]] = {"wrapper": set(), "protocole": set()}
    for fonction in ast.walk(arbre):
        if not isinstance(fonction, ast.FunctionDef):
            continue
        for appel in ast.walk(fonction):
            if not isinstance(appel, ast.Call):
                continue
            cible = appel.func
            if isinstance(cible, ast.Name) and cible.id == "_definir_mot_de_passe":
                appelants["wrapper"].add(fonction.name)
            elif isinstance(cible, ast.Attribute) and cible.attr == "definir_mot_de_passe":
                appelants["protocole"].add(fonction.name)
    return appelants


def test_le_mot_de_passe_n_est_atteignable_que_depuis_la_creation_d_un_compte() -> None:
    """Un compte déjà présent ne doit jamais voir son mot de passe touché, et c'est la
    structure du module qui doit l'interdire, sur les deux façons de l'atteindre :
    `_definir_mot_de_passe`, le wrapper du module, n'a qu'un seul appelant,
    `_creer_le_compte` — lui-même atteint qu'après avoir constaté qu'un compte est à
    créer — et l'opération protocolaire elle-même, `<boîtier>.definir_mot_de_passe(...)`,
    n'est appelée que depuis ce wrapper.

    Ce que cette garde ne voit toujours pas : un appel par alias
    (`f = boitier.definir_mot_de_passe; f(...)`), par `getattr`, ou toute expression dont
    le nom n'apparaît pas littéralement en position d'appel. Le test comportemental de T4
    reste la seule preuve que le chemin ne s'exécute jamais sur un compte existant ;
    celui-ci ne prouve que la structure.
    """
    source = Path(stormshield_utilisateurs.__file__).with_name("execution.py").read_text(
        encoding="utf-8"
    )
    appelants = _appelants_du_mot_de_passe(source)
    assert appelants["wrapper"] == {"_creer_le_compte"}
    assert appelants["protocole"] == {"_definir_mot_de_passe"}


# Sources factices : jamais importées, seulement analysées — elles prouvent que la garde
# mord, au lieu de le supposer. Forme minimale du module réel : un wrapper, son seul
# appelant légitime, et la boucle qui traite tous les travaux, créés ou non.
_MODULE_SAIN = """
def _definir_mot_de_passe(boitier, identifiant, secret):
    boitier.definir_mot_de_passe(identifiant, secret)
    return secret


def _creer_le_compte(boitier, travail):
    boitier.creer_utilisateur(travail.identifiant)
    return _definir_mot_de_passe(boitier, travail.identifiant, "secret")


def _traiter_comptes(boitier, plan):
    for travail in plan.travaux:
        if travail.a_creer:
            _creer_le_compte(boitier, travail)
        _ajouter_les_adhesions(boitier, travail)


def _ajouter_les_adhesions(boitier, travail):
    for groupe in travail.adhesions:
        boitier.ajouter_membre(groupe, travail.identifiant)
"""

_MODULE_SABOTE_PAR_L_OPERATION_PROTOCOLAIRE = """
def _definir_mot_de_passe(boitier, identifiant, secret):
    boitier.definir_mot_de_passe(identifiant, secret)
    return secret


def _creer_le_compte(boitier, travail):
    boitier.creer_utilisateur(travail.identifiant)
    return _definir_mot_de_passe(boitier, travail.identifiant, "secret")


def _traiter_comptes(boitier, plan):
    for travail in plan.travaux:
        if travail.a_creer:
            _creer_le_compte(boitier, travail)
        _ajouter_les_adhesions(boitier, travail)


def _ajouter_les_adhesions(boitier, travail):
    boitier.definir_mot_de_passe(travail.identifiant, "sabotage")
    for groupe in travail.adhesions:
        boitier.ajouter_membre(groupe, travail.identifiant)
"""

_MODULE_SABOTE_PAR_UN_SECOND_APPELANT_DU_WRAPPER = """
def _definir_mot_de_passe(boitier, identifiant, secret):
    boitier.definir_mot_de_passe(identifiant, secret)
    return secret


def _creer_le_compte(boitier, travail):
    boitier.creer_utilisateur(travail.identifiant)
    return _definir_mot_de_passe(boitier, travail.identifiant, "secret")


def _traiter_comptes(boitier, plan):
    for travail in plan.travaux:
        _definir_mot_de_passe(boitier, travail.identifiant, "sabotage")
        if travail.a_creer:
            _creer_le_compte(boitier, travail)
        _ajouter_les_adhesions(boitier, travail)


def _ajouter_les_adhesions(boitier, travail):
    for groupe in travail.adhesions:
        boitier.ajouter_membre(groupe, travail.identifiant)
"""


def test_la_garde_laisse_passer_un_module_sain() -> None:
    appelants = _appelants_du_mot_de_passe(_MODULE_SAIN)
    assert appelants["wrapper"] == {"_creer_le_compte"}
    assert appelants["protocole"] == {"_definir_mot_de_passe"}


def test_la_garde_refuse_l_appel_direct_a_l_operation_protocolaire() -> None:
    """Le contournement démontré en revue : poser le mot de passe via l'attribut du
    boîtier depuis la boucle des adhésions, qui traite tous les travaux — comptes déjà
    présents compris — sans jamais passer par le wrapper du module."""
    appelants = _appelants_du_mot_de_passe(_MODULE_SABOTE_PAR_L_OPERATION_PROTOCOLAIRE)
    assert appelants["protocole"] == {"_definir_mot_de_passe", "_ajouter_les_adhesions"}


def test_la_garde_refuse_un_second_appelant_du_wrapper() -> None:
    appelants = _appelants_du_mot_de_passe(_MODULE_SABOTE_PAR_UN_SECOND_APPELANT_DU_WRAPPER)
    assert appelants["wrapper"] == {"_creer_le_compte", "_traiter_comptes"}


@pytest.mark.firewall
def test_exige_un_boitier() -> None:
    """Sentinelle : collectée seulement avec `pytest -m firewall`."""
    raise AssertionError("ce test ne doit jamais tourner sans boîtier")
