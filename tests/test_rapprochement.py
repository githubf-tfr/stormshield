"""Rapprochement des identités : une seule clé, une seule lecture de DN."""

from stormshield_utilisateurs.rapprochement import (
    Absent,
    Ambigu,
    IndexBoitier,
    Reconnu,
    cle,
    uid_du_dn,
)


def test_la_cle_ignore_la_casse() -> None:
    assert cle("Jean.Dupont") == cle("jean.dupont")


def test_la_cle_laisse_inchange_un_identifiant_deja_en_minuscules() -> None:
    """Les identifiants du fichier sont basculés en minuscules par `lecture` : la clé
    ne doit rien leur faire de plus."""
    assert cle("jean.dupont") == "jean.dupont"


def test_l_uid_est_le_premier_composant_du_dn() -> None:
    assert uid_du_dn("uid=Jean.Dupont,ou=users,dc=interne,dc=local") == "Jean.Dupont"


def test_l_uid_se_lit_quelle_que_soit_la_casse_de_l_etiquette() -> None:
    assert uid_du_dn("UID=martin,ou=users,dc=interne,dc=local") == "martin"


def test_un_dn_qui_ne_commence_pas_par_uid_ne_rend_rien() -> None:
    """Sous-groupe, compte d'un autre annuaire, forme inattendue : aucune action, et
    surtout aucune erreur — ce membre sera compté, pas traité."""
    assert uid_du_dn("cn=sous-groupe,ou=groups,dc=interne,dc=local") is None


def test_une_chaine_vide_ne_rend_rien() -> None:
    assert uid_du_dn("") is None


def test_un_nom_absent_de_l_index_est_a_creer() -> None:
    assert IndexBoitier.depuis(("compta",)).resoudre("rh") == Absent()


def test_un_nom_present_est_rendu_sous_l_orthographe_du_boitier() -> None:
    """C'est la seule graphie dont on sache qu'elle existe chez lui."""
    assert IndexBoitier.depuis(("Jean.Dupont",)).resoudre("jean.dupont") == Reconnu(
        "Jean.Dupont"
    )


def test_deux_graphies_vivantes_sans_correspondance_exacte_sont_ambigues() -> None:
    """Un boîtier mal rangé ne doit pas priver les deux cents autres comptes du lot :
    la résolution le dit, elle ne lève pas."""
    resolution = IndexBoitier.depuis(("Compta", "COMPTA")).resoudre("compta")
    assert resolution == Ambigu(("Compta", "COMPTA"))


def test_la_correspondance_exacte_l_emporte_sur_l_ambiguite() -> None:
    """L'opérateur a écrit ce nom-là, il existe tel quel sur le boîtier."""
    assert IndexBoitier.depuis(("Compta", "compta")).resoudre("compta") == Reconnu("compta")


def test_l_index_conserve_toutes_les_graphies_rendues() -> None:
    """Les orphelins se comptent sur les graphies, pas sur les clés : deux comptes que
    la clé confond restent deux comptes du boîtier."""
    index = IndexBoitier.depuis(("Jean.Dupont", "jean.dupont", "martin"))
    assert index.graphies == ("Jean.Dupont", "jean.dupont", "martin")
    assert index.cles == frozenset({"jean.dupont", "martin"})


def test_un_index_vide_ne_reconnait_rien() -> None:
    assert IndexBoitier.depuis(()).resoudre("compta") == Absent()
