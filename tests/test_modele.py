"""Comportements portés par le modèle : ils sont peu nombreux mais chacun est une règle."""

from conftest import utilisateur

from stormshield_utilisateurs.modele import (
    CompteCree,
    Echec,
    GroupeACreer,
    Plan,
    PolitiqueMotDePasse,
    Rapport,
)


def test_bascule_minuscules_signalee_quand_le_fichier_differe() -> None:
    assert utilisateur("jean.dupont", origine="Jean.Dupont").bascule_minuscules is True
    assert utilisateur("jean.dupont").bascule_minuscules is False


def test_nombre_de_classes_de_la_politique() -> None:
    politique = PolitiqueMotDePasse(
        longueur=16, minuscules=True, majuscules=True, chiffres=True, speciaux=False
    )
    assert politique.nombre_classes() == 3


def test_nombre_d_operations_du_plan() -> None:
    """1 groupe + (USER CREATE + USER PASSWORD + 2 ADDUSER) + (USER CREATE + USER PASSWORD)."""
    plan = Plan(
        comptes_a_creer=(utilisateur("dupont", "compta", "rh"), utilisateur("legrand")),
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
