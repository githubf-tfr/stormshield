"""Génération : on teste la propriété garantie, jamais le tirage lui-même."""

import string

import pytest

from stormshield_utilisateurs.modele import PlancherPolitique, PolitiqueMotDePasse
from stormshield_utilisateurs.motdepasse import generer, proposer, violations

TOUTES_CLASSES = PolitiqueMotDePasse(
    longueur=16, minuscules=True, majuscules=True, chiffres=True, speciaux=True
)


def test_longueur_exacte_demandee() -> None:
    assert len(generer(TOUTES_CLASSES)) == 16


def test_au_moins_un_caractere_par_classe_demandee() -> None:
    """Répété : un tirage unique pourrait satisfaire la règle par chance."""
    for _ in range(200):
        genere = generer(TOUTES_CLASSES)
        assert any(caractere in string.ascii_lowercase for caractere in genere)
        assert any(caractere in string.ascii_uppercase for caractere in genere)
        assert any(caractere in string.digits for caractere in genere)
        assert any(not caractere.isalnum() for caractere in genere)


def test_classes_non_demandees_absentes() -> None:
    politique = PolitiqueMotDePasse(
        longueur=12, minuscules=True, majuscules=False, chiffres=True, speciaux=False
    )
    for _ in range(50):
        genere = generer(politique)
        assert all(caractere in string.ascii_lowercase + string.digits for caractere in genere)


def _classe(caractere: str) -> str:
    if caractere in string.ascii_lowercase:
        return "minuscule"
    if caractere in string.ascii_uppercase:
        return "majuscule"
    if caractere in string.digits:
        return "chiffre"
    return "special"


def _signature(genere: str) -> tuple[str, ...]:
    """Classes des quatre premiers caractères, dans l'ordre."""
    return tuple(_classe(caractere) for caractere in genere[:4])


def test_le_melange_casse_l_ordre_des_classes_imposees() -> None:
    """Le générateur pose d'abord un caractère de chaque classe demandée, dans l'ordre
    de la politique, puis complète et mélange. Rendre la chaîne avant le mélange donnerait
    des mots de passe dont les quatre premiers caractères sont, dans l'ordre, une
    minuscule, une majuscule, un chiffre et un spécial : un début entièrement prévisible,
    et autant d'entropie perdue.

    Quarante tirages : sous un générateur mélangé, la probabilité qu'ils partagent tous
    la même signature est de l'ordre de 10⁻¹⁷ — ce test n'est pas un test de hasard, il
    constate une constante là où il ne doit pas y en avoir."""
    signatures = {_signature(generer(TOUTES_CLASSES)) for _ in range(40)}
    assert signatures != {("minuscule", "majuscule", "chiffre", "special")}
    assert len(signatures) > 1


def test_chaque_position_peut_porter_chaque_classe() -> None:
    """Le mélange doit atteindre **toutes** les positions, la dernière comprise.

    Le test précédent n'inspectait que les quatre premiers caractères : borner la boucle
    de mélange à l'avant-dernier indice le laissait vert, alors que le dernier caractère
    n'était plus jamais déplacé — mesuré, il était un spécial 2000 fois sur 2000. Une
    permutation qui ne laisserait aucun caractère à sa place initiale passait tout
    autant : on exige donc que chaque position voie chacune des quatre classes.

    Quatre caractères, quatre classes : aucun remplissage, le mot de passe n'est que le
    mélange des classes imposées. Deux cents tirages, et 3/4 puissance 200 vaut 10⁻²⁵ —
    le test constate une couverture, il ne joue pas au hasard.
    """
    politique = PolitiqueMotDePasse(
        longueur=4, minuscules=True, majuscules=True, chiffres=True, speciaux=True
    )
    vues: list[set[str]] = [set(), set(), set(), set()]
    for _ in range(200):
        genere = generer(politique)
        for position, caractere in enumerate(genere):
            vues[position].add(_classe(caractere))
    for position, classes in enumerate(vues):
        assert classes == {"minuscule", "majuscule", "chiffre", "special"}, position


def test_une_longueur_egale_au_nombre_de_classes_est_acceptee() -> None:
    """La borne exacte du refus : quatre caractères pour quatre classes tient, il n'y a
    simplement aucun caractère de remplissage."""
    politique = PolitiqueMotDePasse(
        longueur=4, minuscules=True, majuscules=True, chiffres=True, speciaux=True
    )
    assert len(generer(politique)) == 4


def test_deux_appels_donnent_deux_mots_de_passe() -> None:
    assert generer(TOUTES_CLASSES) != generer(TOUTES_CLASSES)


def test_generation_refusee_si_aucune_classe() -> None:
    politique = PolitiqueMotDePasse(
        longueur=12, minuscules=False, majuscules=False, chiffres=False, speciaux=False
    )
    with pytest.raises(ValueError):
        generer(politique)


def test_generation_refusee_si_longueur_inferieure_au_nombre_de_classes() -> None:
    """Deux longueurs, dont celle qui borde le refus : à trois caractères pour quatre
    classes, relâcher la garde d'un cran rendrait un mot de passe de quatre caractères
    là où l'appelant en a demandé trois — plus long que demandé, donc silencieux."""
    for longueur in (2, 3):
        politique = PolitiqueMotDePasse(
            longueur=longueur, minuscules=True, majuscules=True, chiffres=True, speciaux=True
        )
        with pytest.raises(ValueError):
            generer(politique)


def test_politique_sous_le_plancher_refusee() -> None:
    plancher = PlancherPolitique(longueur_min=12, nombre_classes_min=3, entropie_min=0)
    trop_courte = PolitiqueMotDePasse(
        longueur=8, minuscules=True, majuscules=True, chiffres=True, speciaux=True
    )
    assert any("12" in message for message in violations(trop_courte, plancher))

    trop_peu_de_classes = PolitiqueMotDePasse(
        longueur=16, minuscules=True, majuscules=True, chiffres=False, speciaux=False
    )
    assert any("classes" in message for message in violations(trop_peu_de_classes, plancher))


def test_politique_au_dessus_du_plancher_acceptee() -> None:
    plancher = PlancherPolitique(longueur_min=12, nombre_classes_min=3, entropie_min=0)
    assert violations(TOUTES_CLASSES, plancher) == []


def test_proposition_respecte_le_plancher_et_reste_genereuse() -> None:
    plancher = PlancherPolitique(longueur_min=24, nombre_classes_min=2, entropie_min=0)
    propose = proposer(plancher)
    assert propose.longueur == 24
    assert violations(propose, plancher) == []
    assert proposer(PlancherPolitique(8, 2, 0)).longueur == 16


def test_la_proposition_active_les_quatre_classes() -> None:
    """C'est la politique de repli, celle qui part en lot réel quand l'opérateur ne
    touche à rien : en éteindre une seule réduisait l'alphabet sans que rien ne tombe."""
    propose = proposer(PlancherPolitique(longueur_min=8, nombre_classes_min=1, entropie_min=0))
    assert (
        propose.minuscules,
        propose.majuscules,
        propose.chiffres,
        propose.speciaux,
    ) == (True, True, True, True)
    assert propose.nombre_classes() == 4
