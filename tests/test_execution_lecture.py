"""Phase de lecture : identique en simulation et en réel."""

import pytest
from fabriques import _Interrupteur

from stormshield_utilisateurs.boitier import ErreurCommande
from stormshield_utilisateurs.boitier_memoire import BoitierMemoire
from stormshield_utilisateurs.execution import (
    AnnuaireAbsent,
    AnnuaireDejaPresent,
    AnnuairesMultiples,
    _ArretParLOperateur,
    creer_annuaire,
    lire_adhesions,
    lire_socle,
    relire_inventaire,
)
from stormshield_utilisateurs.plan import groupes_a_interroger


def test_un_annuaire_est_le_cas_nominal() -> None:
    boitier = BoitierMemoire(utilisateurs=["martin"], groupes=["rh"])
    socle = lire_socle(boitier)
    assert socle.domaine == "interne.local"
    # Les graphies rendues par le boîtier, pas des clés : c'est sous elles que l'outil
    # s'adressera à lui.
    assert socle.comptes.graphies == ("martin",)
    assert socle.groupes.graphies == ("rh",)
    assert socle.plancher.longueur_min == 12


def test_la_lecture_n_ecrit_rien() -> None:
    boitier = BoitierMemoire()
    lire_socle(boitier)
    operations = {operation for operation, _ in boitier.journal_appels}
    assert operations == {
        "lister_annuaires",
        "lire_politique",
        "lister_utilisateurs",
        "lister_groupes",
    }


def test_aucun_annuaire_demande_l_initialisation() -> None:
    with pytest.raises(AnnuaireAbsent):
        lire_socle(BoitierMemoire(annuaires=[]))


def test_plusieurs_annuaires_arretent_tout() -> None:
    """Les comptes iraient au bon endroit et les groupes on ne sait où : on refuse."""
    boitier = BoitierMemoire(annuaires=["a.local", "b.local"])
    with pytest.raises(AnnuairesMultiples) as erreur:
        lire_socle(boitier)
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
    assert lire_socle(boitier).domaine == "neuf.local"


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
