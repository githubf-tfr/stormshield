"""Toute la décision de l'outil tient dans ce module : il se teste sans réseau."""

from collections.abc import Iterable

from fabriques import utilisateur

from stormshield_utilisateurs.modele import EtatBoitier, PlancherPolitique
from stormshield_utilisateurs.plan import construire

PLANCHER = PlancherPolitique(longueur_min=12, nombre_classes_min=3, entropie_min=0)


def _etat(
    utilisateurs: Iterable[str] = frozenset(), groupes: Iterable[str] = frozenset()
) -> EtatBoitier:
    return EtatBoitier(
        domaine="interne.local",
        plancher=PLANCHER,
        utilisateurs=frozenset(utilisateurs),
        groupes=frozenset(groupes),
    )


def test_compte_absent_du_boitier_est_a_creer() -> None:
    plan = construire([utilisateur("dupont")], _etat())
    assert [compte.identifiant for compte in plan.comptes_a_creer] == ["dupont"]
    assert plan.comptes_ignores == ()


def test_compte_present_sur_le_boitier_est_ignore_entierement() -> None:
    """Appartenances de groupes comprises : rien n'est rattaché à un compte existant."""
    plan = construire([utilisateur("dupont", "compta")], _etat(utilisateurs={"dupont"}))
    assert plan.comptes_a_creer == ()
    assert [compte.identifiant for compte in plan.comptes_ignores] == ["dupont"]
    assert plan.groupes_a_creer == ()


def test_compte_du_boitier_absent_du_fichier_est_orphelin() -> None:
    plan = construire([utilisateur("dupont")], _etat(utilisateurs={"martin", "dupont"}))
    assert plan.orphelins == ("martin",)


def test_orphelins_tries_pour_un_affichage_stable() -> None:
    plan = construire([], _etat(utilisateurs={"zoe", "alice", "martin"}))
    assert plan.orphelins == ("alice", "martin", "zoe")


def test_groupe_absent_du_boitier_et_reference_par_un_compte_a_creer_est_cree() -> None:
    plan = construire([utilisateur("dupont", "compta", "rh")], _etat(groupes={"rh"}))
    assert [groupe.nom for groupe in plan.groupes_a_creer] == ["compta"]


def test_groupe_reference_seulement_par_un_compte_deja_present_n_est_pas_cree() -> None:
    plan = construire(
        [utilisateur("dupont", "compta_bis")], _etat(utilisateurs={"dupont"})
    )
    assert plan.groupes_a_creer == ()


def test_nombre_de_membres_compte_les_seuls_comptes_a_creer() -> None:
    """compta_bis à un seul membre est la signature d'une coquille : le nombre doit le dire."""
    utilisateurs = [
        utilisateur("dupont", "compta", ligne=2),
        utilisateur("legrand", "compta", "compta_bis", ligne=3),
        utilisateur("martin", "compta", ligne=4),
    ]
    plan = construire(utilisateurs, _etat(utilisateurs={"martin"}))
    membres = {groupe.nom: groupe.nombre_membres for groupe in plan.groupes_a_creer}
    assert membres == {"compta": 2, "compta_bis": 1}


def test_groupes_a_creer_tries_par_nom() -> None:
    plan = construire([utilisateur("dupont", "zoe", "alice")], _etat())
    assert [groupe.nom for groupe in plan.groupes_a_creer] == ["alice", "zoe"]


def test_le_domaine_lu_sur_le_boitier_est_porte_par_le_plan() -> None:
    assert construire([], _etat()).domaine == "interne.local"


def test_construire_n_ecrit_rien_sur_l_etat_recu() -> None:
    etat = _etat(utilisateurs={"martin"}, groupes={"rh"})
    construire([utilisateur("dupont", "compta")], etat)
    assert etat.utilisateurs == frozenset({"martin"})
    assert etat.groupes == frozenset({"rh"})
