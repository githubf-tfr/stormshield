"""Le double est l'instrument de tous les autres tests : il a les siens."""

import pytest

from stormshield_utilisateurs.boitier import ErreurCommande, ErreurReseau
from stormshield_utilisateurs.boitier_memoire import BoitierMemoire


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

    def couper(operation: str, _cible: str) -> None:
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
