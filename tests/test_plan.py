"""La décision, entièrement hors ligne : casse, adhésions, compteurs."""

from fabriques import utilisateur

from stormshield_utilisateurs.modele import (
    CompteAmbigu,
    EtatBoitier,
    GroupeACreer,
    GroupeAmbigu,
    PlancherPolitique,
    Rejet,
)
from stormshield_utilisateurs.plan import construire, groupes_a_interroger, groupes_cites
from stormshield_utilisateurs.rapprochement import IndexBoitier

PLANCHER = PlancherPolitique(longueur_min=12, nombre_classes_min=3, entropie_min=0)


def _etat(
    comptes: tuple[str, ...] = (),
    groupes: tuple[str, ...] = (),
    membres: dict[str, tuple[str, ...]] | None = None,
) -> EtatBoitier:
    return EtatBoitier(
        domaine="interne.local",
        plancher=PLANCHER,
        comptes=IndexBoitier.depuis(comptes),
        groupes=IndexBoitier.depuis(groupes),
        membres_par_groupe=membres or {},
    )


def _dn(identifiant: str) -> str:
    return f"uid={identifiant},ou=users,dc=interne,dc=local"


# --- casse des comptes -------------------------------------------------------------

def test_un_compte_du_boitier_est_reconnu_malgre_la_casse() -> None:
    plan = construire([utilisateur("jean.dupont")], _etat(comptes=("Jean.Dupont",)))
    (travail,) = plan.travaux
    assert travail.a_creer is False


def test_toutes_les_operations_visent_l_orthographe_du_boitier() -> None:
    """L'outil ne demande jamais au boîtier de retrouver un compte sous une graphie
    qu'il n'a pas lui-même rendue."""
    plan = construire(
        [utilisateur("jean.dupont", "compta")],
        _etat(comptes=("Jean.Dupont",), groupes=("compta",), membres={"compta": ()}),
    )
    (travail,) = plan.travaux
    assert travail.identifiant_cible == "Jean.Dupont"
    assert travail.adhesions == ("compta",)


def test_un_compte_absent_est_cree_sous_l_identifiant_du_fichier() -> None:
    plan = construire([utilisateur("dupont")], _etat())
    (travail,) = plan.travaux
    assert (travail.a_creer, travail.identifiant_cible) == (True, "dupont")


def test_un_compte_a_deux_graphies_est_signale_et_rien_ne_lui_est_fait() -> None:
    """L'ordre dans lequel le boîtier rend sa liste n'est garanti par rien : trancher sur
    la première graphie ferait écrire sur un compte différent d'une fois sur l'autre. Pas
    de travail, donc ni création, ni adhésion, ni mot de passe — et le lot continue."""
    plan = construire(
        [utilisateur("jean.dupont", "compta"), utilisateur("legrand", "compta", ligne=3)],
        _etat(
            comptes=("Jean.Dupont", "JEAN.DUPONT", "legrand"),
            groupes=("compta",),
            membres={"compta": ()},
        ),
    )
    # Graphies triées : `Ambigu` les range à la construction, pour que ni l'égalité ni
    # l'affichage ne dépendent de l'ordre dans lequel le boîtier a rendu sa liste.
    assert plan.comptes_ambigus == (
        CompteAmbigu("jean.dupont", ("JEAN.DUPONT", "Jean.Dupont")),
    )
    assert [travail.identifiant_cible for travail in plan.travaux] == ["legrand"]


def test_une_correspondance_exacte_l_emporte_sur_l_ambiguite_du_compte() -> None:
    """Même règle que pour les groupes : l'opérateur a écrit ce nom-là, il existe tel
    quel sur le boîtier."""
    plan = construire(
        [utilisateur("jean.dupont")], _etat(comptes=("Jean.Dupont", "jean.dupont"))
    )
    assert plan.comptes_ambigus == ()
    (travail,) = plan.travaux
    assert (travail.a_creer, travail.identifiant_cible) == (False, "jean.dupont")


def test_un_groupe_cite_par_le_seul_compte_ambigu_n_est_pas_cree() -> None:
    """Ce compte ne reçoit aucune adhésion : le groupe neuf n'aurait aucun membre."""
    plan = construire(
        [utilisateur("jean.dupont", "neuf")],
        _etat(comptes=("Jean.Dupont", "JEAN.DUPONT")),
    )
    assert plan.groupes_a_creer == ()


# --- adhésions ---------------------------------------------------------------------

def test_les_adhesions_manquantes_d_un_compte_present_sont_ajoutees() -> None:
    plan = construire(
        [utilisateur("legrand", "rh")],
        _etat(comptes=("legrand",), groupes=("rh",), membres={"rh": ()}),
    )
    assert plan.travaux[0].adhesions == ("rh",)


def test_une_adhesion_deja_portee_par_le_boitier_n_est_pas_replanifiee() -> None:
    """Le cœur de l'idempotence, dans la seule fonction pure qui la décide."""
    plan = construire(
        [utilisateur("legrand", "rh")],
        _etat(comptes=("legrand",), groupes=("rh",), membres={"rh": (_dn("legrand"),)}),
    )
    assert plan.travaux[0].adhesions == ()
    assert plan.nombre_operations() == 0


def test_l_adhesion_existante_est_reconnue_malgre_la_casse_du_dn() -> None:
    plan = construire(
        [utilisateur("jean.dupont", "rh")],
        _etat(
            comptes=("Jean.Dupont",),
            groupes=("rh",),
            membres={"rh": (_dn("Jean.Dupont"),)},
        ),
    )
    assert plan.travaux[0].adhesions == ()


def test_une_colonne_groupes_vide_n_ajoute_aucune_adhesion() -> None:
    """La colonne vide ne dit pas « aucun groupe » mais « je ne me prononce pas »."""
    plan = construire([utilisateur("legrand")], _etat(comptes=("legrand",)))
    assert plan.travaux[0].adhesions == ()
    assert plan.groupes_a_creer == ()


def test_un_compte_a_creer_recoit_aussi_ses_adhesions() -> None:
    plan = construire([utilisateur("dupont", "compta", "rh")], _etat(groupes=("compta",)))
    assert plan.travaux[0].adhesions == ("compta", "rh")


# --- casse et collisions de groupes ------------------------------------------------

def test_un_groupe_du_boitier_est_reconnu_malgre_la_casse_et_n_est_pas_recree() -> None:
    plan = construire(
        [utilisateur("dupont", "compta")], _etat(groupes=("Compta",), membres={"compta": ()})
    )
    assert plan.groupes_a_creer == ()
    assert plan.travaux[0].adhesions == ("Compta",)


def test_une_collision_de_casse_est_signalee_et_le_groupe_n_est_touche_pour_personne() -> None:
    """Un boîtier mal rangé ne doit pas priver les deux cents autres comptes du lot."""
    plan = construire(
        [utilisateur("dupont", "compta"), utilisateur("legrand", "rh", ligne=3)],
        _etat(groupes=("Compta", "COMPTA", "rh"), membres={"rh": ()}),
    )
    # Graphies triées, comme pour un compte ambigu, et pour la même raison.
    assert plan.groupes_ambigus == (GroupeAmbigu("compta", ("COMPTA", "Compta")),)
    assert plan.travaux[0].adhesions == ()
    assert plan.travaux[1].adhesions == ("rh",)
    assert plan.groupes_a_creer == ()


def test_une_correspondance_exacte_l_emporte_sur_la_collision() -> None:
    plan = construire(
        [utilisateur("dupont", "compta")],
        _etat(groupes=("Compta", "compta"), membres={"compta": ()}),
    )
    assert plan.groupes_ambigus == ()
    assert plan.travaux[0].adhesions == ("compta",)


# --- groupes à interroger ----------------------------------------------------------

def test_les_groupes_cites_se_calculent_avant_toute_connexion() -> None:
    assert groupes_cites(
        [utilisateur("dupont", "compta", "rh"), utilisateur("legrand", "Compta", ligne=3)]
    ) == ("compta", "rh")


def test_seuls_les_groupes_cites_et_presents_sont_interroges() -> None:
    """Un groupe qu'aucune ligne ne cite n'est pas lu ; un groupe cité mais absent n'a
    pas de membre ; un groupe ambigu ne sera touché pour personne.

    Aucune des deux graphies de `doublon` n'est celle du fichier : sans quoi la
    correspondance exacte l'emporterait et le groupe serait bel et bien interrogé, comme
    il serait bel et bien rattaché.
    """
    index = IndexBoitier.depuis(("Compta", "jamais.cite", "Doublon", "DOUBLON"))
    assert groupes_a_interroger(("compta", "neuf", "doublon"), index) == ("Compta",)


def test_un_groupe_ambigu_leve_par_une_correspondance_exacte_est_interroge() -> None:
    """La contrepartie du test précédent : `doublon` existe tel quel sur le boîtier, il
    n'y a rien à deviner, et lire ses membres évite un ADDUSER redondant."""
    index = IndexBoitier.depuis(("Doublon", "doublon"))
    assert groupes_a_interroger(("doublon",), index) == ("doublon",)


def test_une_ligne_a_colonne_vide_ne_cite_aucun_groupe() -> None:
    """Le majorant de la phase de lecture ne compte que ce que le fichier décrit ; les
    lignes rejetées, elles, n'arrivent pas jusqu'ici."""
    assert groupes_cites([utilisateur("legrand"), utilisateur("dupont", "rh", ligne=3)]) == (
        "rh",
    )


# --- membres non rattachés ---------------------------------------------------------

def test_un_membre_dont_le_dn_ne_se_lit_pas_est_compte_et_ne_provoque_rien() -> None:
    """Le canari de l'hypothèse sur la forme du DN : un entier, jamais une liste."""
    plan = construire(
        [utilisateur("dupont", "compta")],
        _etat(
            comptes=("dupont",),
            groupes=("compta",),
            membres={"compta": ("cn=sous-groupe,ou=groups,dc=local", _dn("dupont"))},
        ),
    )
    assert plan.nombre_membres_non_rattaches == 1
    assert plan.travaux[0].adhesions == ()


def test_un_membre_legitime_absent_du_fichier_n_est_pas_compte() -> None:
    """Un groupe peuplé contient forcément des gens que le CSV du jour ne cite pas : les
    compter noierait le signal dans le bruit qu'il doit détecter. Le point de comparaison
    est la liste des comptes du boîtier, jamais celle du fichier."""
    plan = construire(
        [utilisateur("dupont", "compta")],
        _etat(
            comptes=("dupont", "martin"),
            groupes=("compta",),
            membres={"compta": (_dn("martin"),)},
        ),
    )
    assert plan.nombre_membres_non_rattaches == 0


def test_un_dn_designant_un_compte_inconnu_du_boitier_est_compte() -> None:
    """Le boîtier a rendu un membre que sa propre liste de comptes ne porte pas : l'outil
    ne sait pas le relier, et c'est précisément ce que le compteur dit."""
    plan = construire(
        [utilisateur("dupont", "compta")],
        _etat(comptes=("dupont",), groupes=("compta",), membres={"compta": (_dn("martin"),)}),
    )
    assert plan.nombre_membres_non_rattaches == 1


def test_un_membre_non_rattache_ne_supprime_aucune_adhesion_planifiee() -> None:
    """Spec : un membre que l'outil ne sait relier à aucun compte **du boîtier** ne
    déclenche « aucune action ». Retirer du plan l'adhésion du compte homonyme que le
    fichier demande de créer en serait une, et la plus coûteuse : ce compte naîtrait sans
    le groupe que le CSV lui donne, sur la foi d'un DN qu'on n'a pas su lire."""
    plan = construire(
        [utilisateur("dupont", "compta")],
        _etat(groupes=("compta",), membres={"compta": (_dn("dupont"),)}),
    )
    assert plan.nombre_membres_non_rattaches == 1
    assert plan.travaux[0].a_creer is True
    assert plan.travaux[0].adhesions == ("compta",)


def test_aucun_membre_non_rattache_sur_un_boitier_sain() -> None:
    """Zéro, quel que soit le contenu du fichier : `legrand` n'y figure pas, mais le
    boîtier le connaît."""
    plan = construire(
        [utilisateur("dupont", "compta")],
        _etat(
            comptes=("dupont", "legrand"),
            groupes=("compta",),
            membres={"compta": (_dn("dupont"), _dn("legrand"))},
        ),
    )
    assert plan.nombre_membres_non_rattaches == 0


# --- orphelins ---------------------------------------------------------------------

def test_les_orphelins_sont_comptes_jamais_listes() -> None:
    plan = construire([utilisateur("dupont")], _etat(comptes=("dupont", "martin", "paul")))
    assert plan.nombre_orphelins == 2


def test_un_compte_dont_la_ligne_a_ete_rejetee_n_est_pas_orphelin() -> None:
    """Il est bel et bien dans le fichier : l'annoncer orphelin dirait à l'opérateur le
    contraire de ce qu'il doit corriger."""
    plan = construire(
        [],
        _etat(comptes=("Martin",)),
        rejets=[Rejet(ligne=2, identifiant="martin", motif="nom vide")],
    )
    assert plan.nombre_orphelins == 0


def test_un_orphelin_est_reconnu_malgre_la_casse() -> None:
    plan = construire([utilisateur("jean.dupont")], _etat(comptes=("Jean.Dupont",)))
    assert plan.nombre_orphelins == 0


# --- groupes à créer ---------------------------------------------------------------

def test_les_groupes_a_creer_se_calculent_sur_toutes_les_adhesions() -> None:
    """Y compris celles d'un compte déjà présent : sans quoi son ADDUSER échouerait sur
    un groupe inexistant."""
    plan = construire([utilisateur("legrand", "neuf")], _etat(comptes=("legrand",)))
    assert plan.groupes_a_creer == (GroupeACreer(nom="neuf", nombre_membres=1),)


def test_un_groupe_reference_par_une_seule_ligne_rejetee_n_est_pas_cree() -> None:
    plan = construire([], _etat(), rejets=[Rejet(ligne=2, identifiant="x", motif="nom vide")])
    assert plan.groupes_a_creer == ()


def test_les_groupes_a_creer_sont_tries_et_comptent_leurs_membres() -> None:
    plan = construire(
        [utilisateur("dupont", "rh", "compta"), utilisateur("legrand", "rh", ligne=3)],
        _etat(),
    )
    assert plan.groupes_a_creer == (
        GroupeACreer(nom="compta", nombre_membres=1),
        GroupeACreer(nom="rh", nombre_membres=2),
    )


def test_le_domaine_lu_sur_le_boitier_est_porte_par_le_plan() -> None:
    assert construire([], _etat()).domaine == "interne.local"


def test_construire_n_ecrit_rien_sur_l_etat_recu() -> None:
    etat = _etat(comptes=("dupont",), groupes=("compta",), membres={"compta": ()})
    construire([utilisateur("dupont", "compta")], etat)
    assert etat.comptes.graphies == ("dupont",)
    assert etat.membres_par_groupe == {"compta": ()}
