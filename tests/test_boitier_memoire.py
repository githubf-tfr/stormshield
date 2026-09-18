"""Le double est l'instrument de tous les autres tests : il a les siens."""

import pytest

from stormshield_utilisateurs.boitier import Boitier, ErreurCommande, ErreurReseau
from stormshield_utilisateurs.boitier_memoire import BoitierMemoire, dn_de


def test_creation_d_un_utilisateur_et_d_un_groupe() -> None:
    boitier = BoitierMemoire(utilisateurs=["martin"], groupes=["rh"])
    boitier.connecter()
    boitier.creer_utilisateur("dupont", "Dupont", "Marie", "interne.local")
    boitier.creer_groupe("compta")
    boitier.ajouter_membre("compta", "dupont")
    boitier.definir_mot_de_passe("dupont", "Abc123!x")
    assert sorted(boitier.lister_utilisateurs()) == ["dupont", "martin"]
    assert sorted(boitier.lister_groupes()) == ["compta", "rh"]
    assert boitier.membres["compta"] == [dn_de("dupont")]
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


def test_initialiser_un_annuaire_alors_qu_un_existe_deja_est_refuse() -> None:
    """Le boîtier réel n'admet qu'un seul annuaire actif ; le double doit le refuser
    aussi, sinon un test vert n'exercerait jamais ce chemin.

    Le motif est asséré, pas seulement le type : sans lui, le double pourrait se mettre à
    refuser pour une tout autre raison — un argument vide, un nom déjà pris — sans qu'un
    seul test ne le dise, et le chemin qu'on croit exercer ne serait plus exercé.
    """
    boitier = BoitierMemoire()
    with pytest.raises(ErreurCommande, match="un annuaire existe déjà"):
        boitier.initialiser_annuaire("neuf.local", "Societe", "dc=neuf,dc=local", "secret-factice")


def test_activer_un_annuaire_sans_initialisation_prealable_est_refuse() -> None:
    boitier = BoitierMemoire(annuaires=[])
    with pytest.raises(ErreurCommande, match="aucun annuaire à activer"):
        boitier.activer_annuaire()


def test_creer_deux_fois_le_meme_groupe_est_refuse() -> None:
    boitier = BoitierMemoire(groupes=["compta"])
    with pytest.raises(ErreurCommande, match="le groupe compta existe déjà"):
        boitier.creer_groupe("compta")


def test_creer_un_groupe_avec_un_guillemet_double_dans_le_nom_est_refuse() -> None:
    """Le nom est transmis verbatim entre guillemets doubles : un guillemet dans le
    nom casserait la commande, donc le double refuse la création."""
    boitier = BoitierMemoire()
    with pytest.raises(ErreurCommande, match="guillemet double interdit"):
        boitier.creer_groupe('compta"rh')


def test_definir_le_mot_de_passe_d_un_utilisateur_inconnu_est_refuse() -> None:
    boitier = BoitierMemoire()
    with pytest.raises(ErreurCommande, match="utilisateur dupont inconnu"):
        boitier.definir_mot_de_passe("dupont", "Abc123!x")


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


def test_boitier_memoire_respecte_le_protocole_boitier_et_produit_un_effet_reel() -> None:
    """Preuve statique : l'annotation `Boitier` force mypy à comparer structurellement
    `BoitierMemoire` au Protocol - une méthode manquante ou de signature modifiée fait
    échouer la vérification de types. Preuve comportementale : les appels passés à
    travers cette variable typée `Boitier` produisent un effet observable réel."""
    boitier: Boitier = BoitierMemoire()
    boitier.connecter()
    boitier.creer_groupe("compta")
    boitier.creer_utilisateur("dupont", "Dupont", "Marie", "interne.local")
    boitier.ajouter_membre("compta", "dupont")
    boitier.deconnecter()
    assert boitier.lister_utilisateurs() == ["dupont"]
    assert boitier.lister_groupes() == ["compta"]
