"""Génération de mots de passe. Module pur, `secrets` de la bibliothèque standard."""

import secrets
import string

from stormshield_utilisateurs.modele import PlancherPolitique, PolitiqueMotDePasse

LONGUEUR_PROPOSEE = 16
# Jeu de spéciaux volontairement étroit : pas de guillemet ni d'espace, qui compliqueraient
# la construction de la commande USER PASSWORD sans rien apporter à l'entropie.
SPECIAUX = "!#$%*+-=?@_"


def _alphabets(politique: PolitiqueMotDePasse) -> list[str]:
    alphabets = []
    if politique.minuscules:
        alphabets.append(string.ascii_lowercase)
    if politique.majuscules:
        alphabets.append(string.ascii_uppercase)
    if politique.chiffres:
        alphabets.append(string.digits)
    if politique.speciaux:
        alphabets.append(SPECIAUX)
    return alphabets


def generer(politique: PolitiqueMotDePasse) -> str:
    """Longueur exacte et au moins un caractère de chaque classe demandée."""
    alphabets = _alphabets(politique)
    if not alphabets:
        raise ValueError("au moins une classe de caractères est nécessaire")
    if politique.longueur < len(alphabets):
        raise ValueError(
            f"longueur {politique.longueur} insuffisante pour {len(alphabets)} classes"
        )
    caracteres = [secrets.choice(alphabet) for alphabet in alphabets]
    complet = "".join(alphabets)
    caracteres += [secrets.choice(complet) for _ in range(politique.longueur - len(caracteres))]
    # Mélange : sans lui, les premiers caractères trahiraient l'ordre des classes.
    melange = list(caracteres)
    for indice in range(len(melange) - 1, 0, -1):
        autre = secrets.randbelow(indice + 1)
        melange[indice], melange[autre] = melange[autre], melange[indice]
    return "".join(melange)


def violations(politique: PolitiqueMotDePasse, plancher: PlancherPolitique) -> list[str]:
    """Messages à afficher ; liste vide = la politique tient le plancher du boîtier."""
    messages: list[str] = []
    if politique.longueur < plancher.longueur_min:
        messages.append(
            f"longueur {politique.longueur} inférieure au minimum du boîtier "
            f"({plancher.longueur_min})"
        )
    if politique.nombre_classes() < plancher.nombre_classes_min:
        messages.append(
            f"{politique.nombre_classes()} classes de caractères, le boîtier en exige "
            f"{plancher.nombre_classes_min}"
        )
    return messages


def proposer(plancher: PlancherPolitique) -> PolitiqueMotDePasse:
    """Pré-remplissage initial uniquement : jamais appelé sur une relecture du boîtier."""
    return PolitiqueMotDePasse(
        longueur=max(LONGUEUR_PROPOSEE, plancher.longueur_min),
        minuscules=True,
        majuscules=True,
        chiffres=True,
        speciaux=True,
    )
