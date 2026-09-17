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


@pytest.mark.firewall
def test_exige_un_boitier() -> None:
    """Sentinelle : collectée seulement avec `pytest -m firewall`."""
    raise AssertionError("ce test ne doit jamais tourner sans boîtier")
