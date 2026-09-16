"""Le CSV est la seule entrée de l'outil : chaque règle de la spec a son test."""

from pathlib import Path

import pytest

from stormshield_utilisateurs.lecture import ColonnesManquantes, decoder, lire, lire_texte

EN_TETE = "identifiant;nom;prenom;groupes\n"


def test_colonne_manquante_fait_echouer_le_fichier_entier() -> None:
    """Pas de rejet ligne à ligne : on n'injecte rien et on nomme la colonne absente."""
    contenu = "identifiant;nom;groupes\ndupont;Dupont;compta\n"
    with pytest.raises(ColonnesManquantes) as erreur:
        lire_texte(contenu)
    assert erreur.value.colonnes == ("prenom",)
    assert "prenom" in str(erreur.value)


def test_espaces_parasites_autour_des_noms_de_colonnes_n_empechent_pas_la_lecture() -> None:
    """La vérification de structure strippe l'en-tête : l'extraction des champs doit
    voir les mêmes clés, sous peine de rejets silencieux pour "identifiant vide"."""
    contenu = " identifiant ; nom ;prenom; groupes \ndupont;Dupont;Marie;\n"
    utilisateurs, rejets = lire_texte(contenu)
    assert rejets == []
    assert utilisateurs[0].identifiant == "dupont"


def test_colonnes_dans_n_importe_quel_ordre_et_colonnes_en_trop_ignorees() -> None:
    contenu = "mail;groupes;prenom;nom;identifiant\nx@y.z;compta;Marie;Dupont;dupont\n"
    utilisateurs, rejets = lire_texte(contenu)
    assert rejets == []
    assert utilisateurs[0].identifiant == "dupont"
    assert utilisateurs[0].groupes == ("compta",)


def test_numeros_sont_des_numeros_d_enregistrement() -> None:
    """L'en-tête compte pour la ligne 1, le premier enregistrement pour la ligne 2."""
    contenu = EN_TETE + "dupont;Dupont;Marie;\n;Legrand;Paul;\n"
    utilisateurs, rejets = lire_texte(contenu)
    assert utilisateurs[0].ligne == 2
    assert rejets[0].ligne == 3


def test_champ_multiligne_ne_decale_pas_la_numerotation() -> None:
    contenu = EN_TETE + 'dupont;"Du\npont";Marie;\nlegrand;Legrand;Paul;\n'
    utilisateurs, _ = lire_texte(contenu)
    assert [utilisateur.ligne for utilisateur in utilisateurs] == [2, 3]


def test_decodage_bom_puis_utf8_puis_cp1252() -> None:
    assert decoder("é".encode("utf-8-sig")) == "é"
    assert decoder("é".encode()) == "é"
    assert decoder("é".encode("cp1252")) == "é"


def test_lire_ouvre_un_fichier_cp1252(tmp_path: Path) -> None:
    fichier = tmp_path / "users.csv"
    fichier.write_bytes((EN_TETE + "dupont;Dupont;Chloé;\n").encode("cp1252"))
    utilisateurs, _ = lire(fichier)
    assert utilisateurs[0].prenom == "Chloé"


def test_espaces_supprimes_avant_toute_validation() -> None:
    contenu = EN_TETE + "  dupont ; Dupont ; Marie ; compta | rh \n"
    utilisateurs, rejets = lire_texte(contenu)
    assert rejets == []
    assert utilisateurs[0].identifiant == "dupont"
    assert utilisateurs[0].nom == "Dupont"
    assert utilisateurs[0].groupes == ("compta", "rh")


def test_identifiant_bascule_en_minuscules_et_la_ligne_passe() -> None:
    utilisateurs, rejets = lire_texte(EN_TETE + "Jean.Dupont;Dupont;Jean;\n")
    assert rejets == []
    assert utilisateurs[0].identifiant == "jean.dupont"
    assert utilisateurs[0].identifiant_origine == "Jean.Dupont"
    assert utilisateurs[0].bascule_minuscules is True


@pytest.mark.parametrize(
    ("valeur", "extrait_du_motif"),
    [
        ("", "identifiant"),
        ("jean dupont", "caractère"),
        ("jéan", "caractère"),
        ("jean@dupont", "caractère"),
    ],
)
def test_identifiants_rejetes(valeur: str, extrait_du_motif: str) -> None:
    utilisateurs, rejets = lire_texte(EN_TETE + f"{valeur};Dupont;Jean;\n")
    assert utilisateurs == []
    assert extrait_du_motif in rejets[0].motif


def test_jeu_de_caracteres_accepte() -> None:
    utilisateurs, rejets = lire_texte(EN_TETE + "a-b_c.d9;Dupont;Jean;\n")
    assert rejets == []
    assert utilisateurs[0].identifiant == "a-b_c.d9"


@pytest.mark.parametrize("ligne", ["dupont;;Marie;", "dupont;Dupont;;"])
def test_nom_ou_prenom_vide_rejete(ligne: str) -> None:
    utilisateurs, rejets = lire_texte(EN_TETE + ligne + "\n")
    assert utilisateurs == []
    assert len(rejets) == 1


def test_doublon_rejette_les_deux_lignes() -> None:
    """L'outil ne tranche pas laquelle des deux est juste : il les refuse toutes les deux."""
    contenu = EN_TETE + "dupont;Dupont;Marie;\ndupont;Dupont;Paul;\n"
    utilisateurs, rejets = lire_texte(contenu)
    assert utilisateurs == []
    assert [rejet.ligne for rejet in rejets] == [2, 3]
    assert all("doublon" in rejet.motif for rejet in rejets)


def test_doublon_detecte_apres_bascule_en_minuscules() -> None:
    contenu = EN_TETE + "Jean.Dupont;Dupont;Jean;\njean.dupont;Dupont;Jean;\n"
    utilisateurs, rejets = lire_texte(contenu)
    assert utilisateurs == []
    assert [rejet.ligne for rejet in rejets] == [2, 3]


def test_rejets_portent_l_identifiant_apres_bascule() -> None:
    _, rejets = lire_texte(EN_TETE + "Jean.Dupont;;Jean;\n")
    assert rejets[0].identifiant == "jean.dupont"


def test_une_ligne_rejetee_ne_bloque_pas_les_autres() -> None:
    contenu = EN_TETE + ";Dupont;Marie;\nlegrand;Legrand;Paul;\n"
    utilisateurs, rejets = lire_texte(contenu)
    assert [utilisateur.identifiant for utilisateur in utilisateurs] == ["legrand"]
    assert len(rejets) == 1


def test_groupes_vides_dedupliques_et_segments_vides_ignores() -> None:
    contenu = EN_TETE + "dupont;Dupont;Marie;compta||rh|compta|\nlegrand;Legrand;Paul;\n"
    utilisateurs, rejets = lire_texte(contenu)
    assert rejets == []
    assert utilisateurs[0].groupes == ("compta", "rh")
    assert utilisateurs[1].groupes == ()


def test_aucune_contrainte_de_caracteres_sur_les_noms_de_groupes() -> None:
    utilisateurs, rejets = lire_texte(EN_TETE + 'dupont;Dupont;Marie;Groupe "A" & Cie\n')
    assert rejets == []
    assert utilisateurs[0].groupes == ('Groupe "A" & Cie',)
