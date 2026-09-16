"""L'adaptateur n'est prouvé par rien tant qu'aucun boîtier n'est joignable.
Seules les parties textuelles se testent hors ligne."""

import pytest

from stormshield_utilisateurs.boitier import Boitier
from stormshield_utilisateurs.boitier_sdk import (
    BoitierSDK,
    commande_ajouter_membre,
    commande_creer_groupe,
    commande_creer_utilisateur,
    lire_plancher,
)

# Ligne de type, jamais un test : c'est mypy, pas pytest, qui prouve ici que BoitierSDK
# satisfait structurellement le Protocol Boitier. Un `assert ... is not None` à l'exécution
# ne prouverait rien qu'une réussite systématique ; l'annotation ci-dessous, elle, échoue
# la vérification statique si une méthode du Protocol manque ou diverge.
_conforme_au_protocol: Boitier = BoitierSDK("10.0.0.1", "admin", "secret-factice")


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
