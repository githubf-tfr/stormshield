"""Phase de lecture : identique en simulation et en réel."""

import pytest

from stormshield_utilisateurs.boitier import ErreurCommande
from stormshield_utilisateurs.boitier_memoire import BoitierMemoire
from stormshield_utilisateurs.execution import (
    AnnuaireAbsent,
    AnnuaireDejaPresent,
    AnnuairesMultiples,
    creer_annuaire,
    lire_comptes_et_groupes,
    lire_etat,
)


def test_un_annuaire_est_le_cas_nominal() -> None:
    boitier = BoitierMemoire(utilisateurs=["martin"], groupes=["rh"])
    etat = lire_etat(boitier)
    assert etat.domaine == "interne.local"
    # Les graphies rendues par le boîtier, pas des clés : c'est sous elles que l'outil
    # s'adressera à lui.
    assert etat.comptes.graphies == ("martin",)
    assert etat.groupes.graphies == ("rh",)
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
    # La première lecture est la garde de la fonction : elle refuse d'écraser un
    # annuaire existant. La dernière est la confirmation.
    assert operations == [
        "lister_annuaires",
        "initialiser_annuaire",
        "activer_annuaire",
        "lister_annuaires",
    ]
    assert lire_etat(boitier).domaine == "neuf.local"


def test_initialisation_non_confirmee_est_une_erreur() -> None:
    """Le lot ne reprend la main qu'après confirmation par relecture."""
    boitier = BoitierMemoire(annuaires=[])

    def ne_rien_enregistrer(operation: str, _cible: str) -> None:
        if operation == "activer_annuaire":
            boitier._annuaire_en_attente = None
            raise ErreurCommande(200, "activation refusée")

    boitier.declencheur = ne_rien_enregistrer
    with pytest.raises(ErreurCommande):
        creer_annuaire(boitier, "neuf.local", "Societe", "dc=neuf,dc=local", "secret-factice")


def test_activation_silencieuse_sans_annuaire_est_une_erreur() -> None:
    """Le point central de la fonction : l'activation ne lève rien, mais l'annuaire
    n'apparaît pas à la relecture. Sans cette vérification le lot repartirait sur
    une base qui n'existe pas."""
    boitier = BoitierMemoire(annuaires=[])
    relectures = 0

    def oublier_l_annuaire(operation: str, _cible: str) -> None:
        nonlocal relectures
        if operation == "lister_annuaires":
            relectures += 1
            if relectures == 2:  # la relecture de confirmation ne voit rien
                boitier.annuaires.clear()

    boitier.declencheur = oublier_l_annuaire
    with pytest.raises(ErreurCommande) as erreur:
        creer_annuaire(boitier, "neuf.local", "Societe", "dc=neuf,dc=local", "secret-factice")
    assert "neuf.local" in str(erreur.value)


def test_creer_annuaire_refuse_si_un_annuaire_repond_deja() -> None:
    """CONFIG LDAP INITIALIZE écrase une base existante : la fonction se garde
    elle-même, elle ne s'en remet pas à la discipline de son appelant."""
    boitier = BoitierMemoire(annuaires=["deja.local"])
    with pytest.raises(AnnuaireDejaPresent) as erreur:
        creer_annuaire(boitier, "neuf.local", "Societe", "dc=neuf,dc=local", "secret-factice")
    assert erreur.value.annuaires == ("deja.local",)
    operations = [operation for operation, _ in boitier.journal_appels]
    assert "initialiser_annuaire" not in operations
    assert boitier.annuaires == ["deja.local"]


def test_reprise_ne_relit_que_les_comptes_et_les_groupes() -> None:
    """Après une reconnexion en milieu de lot : ni l'annuaire, ni la politique."""
    boitier = BoitierMemoire(utilisateurs=["martin"], groupes=["rh"])
    utilisateurs, groupes = lire_comptes_et_groupes(boitier)
    assert utilisateurs == frozenset({"martin"})
    assert groupes == frozenset({"rh"})
    operations = {operation for operation, _ in boitier.journal_appels}
    assert operations == {"lister_utilisateurs", "lister_groupes"}
