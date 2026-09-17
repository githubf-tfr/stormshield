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
    TravailCompte,
)


def _plan(*travaux: TravailCompte, groupes: tuple[GroupeACreer, ...] = ()) -> Plan:
    return Plan(
        travaux=travaux,
        groupes_a_creer=groupes,
        nombre_orphelins=0,
        nombre_membres_non_rattaches=0,
        groupes_ambigus=(),
        comptes_ambigus=(),
        domaine="interne.local",
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
    plan = _plan(
        TravailCompte(
            utilisateur=utilisateur("dupont", "compta", "rh"),
            identifiant_cible="dupont",
            a_creer=True,
            adhesions=("compta", "rh"),
        ),
        TravailCompte(
            utilisateur=utilisateur("legrand"),
            identifiant_cible="legrand",
            a_creer=True,
            adhesions=(),
        ),
        groupes=(GroupeACreer(nom="compta", nombre_membres=1),),
    )
    assert plan.nombre_operations() == 1 + 4 + 2


def test_un_compte_deja_present_ne_coute_que_ses_adhesions() -> None:
    """Deux opérations et non quatre : ni USER CREATE ni USER PASSWORD ne le visent.

    C'est la garantie que le nouveau périmètre met le plus à l'épreuve — l'outil écrit
    désormais sur des comptes existants — et la barre de progression viserait un total
    que rien ne peut plus atteindre si elle les comptait.
    """
    plan = _plan(
        TravailCompte(
            utilisateur=utilisateur("legrand", "compta", "rh"),
            identifiant_cible="legrand",
            a_creer=False,
            adhesions=("compta", "rh"),
        )
    )
    assert plan.creations == ()
    assert plan.nombre_operations() == 2


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


def test_un_arret_demande_par_l_operateur_est_un_motif_a_part() -> None:
    """Troisième fin possible, distincte des deux autres : rien n'est tombé et rien n'est
    à corriger, ce sont les comptes non entamés qui le sont restés."""
    rapport = Rapport(interrompu=True, motif_arret=MotifArret.OPERATEUR, comptes_prevus=200)
    assert rapport.motif_arret is MotifArret.OPERATEUR
    assert rapport.comptes_prevus == 200


def test_un_rapport_neuf_ne_prevoit_aucun_compte() -> None:
    """`comptes_prevus` n'a de sens qu'une fois le plan construit : avant, il n'y a rien
    à annoncer, pas même un total inconnu."""
    assert Rapport().comptes_prevus == 0


def test_le_mot_de_passe_d_un_compte_cree_ne_figure_pas_dans_son_repr() -> None:
    """Fuite latente : aucun chemin ne l'affiche aujourd'hui, mais une ligne de journal
    ajoutée un jour, une assertion de test qui échoue ou un formateur de trace suffirait.
    Le secret reste comparé et transporté comme avant, il ne s'imprime plus."""
    compte = CompteCree("dupont", "S3cret-Genere!")
    assert "S3cret-Genere!" not in repr(compte)
    assert "dupont" in repr(compte)
    assert compte.mot_de_passe == "S3cret-Genere!"
    assert compte == CompteCree("dupont", "S3cret-Genere!")
    assert compte != CompteCree("dupont", "autre")
