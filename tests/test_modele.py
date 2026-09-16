"""Comportements portés par le modèle : ils sont peu nombreux mais chacun est une règle."""

from fabriques import utilisateur

from stormshield_utilisateurs.modele import (
    CompteCree,
    Echec,
    GroupeACreer,
    MotifArret,
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


def test_un_lot_mene_a_son_terme_n_a_aucun_motif_d_arret() -> None:
    """`motif_arret` à None est la seule marque d'un lot allé au bout."""
    rapport = Rapport()
    assert rapport.interrompu is False
    assert rapport.motif_arret is None


def test_un_rapport_porte_le_motif_d_arret_qu_on_lui_donne() -> None:
    """Relancer suffit après une coupure réseau ; un arrêt fatal demande une correction.
    Le rapport transporte ce verdict jusqu'à la fenêtre, qui aiguille dessus sans lire
    un texte — les deux conduites tenues sont vérifiées par `lignes_du_rapport`."""
    assert Rapport(interrompu=True, motif_arret=MotifArret.RESEAU).motif_arret is (
        MotifArret.RESEAU
    )
    assert Rapport(interrompu=True, motif_arret=MotifArret.FATAL).motif_arret is MotifArret.FATAL
