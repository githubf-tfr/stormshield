"""Fabrique de test partagée par les suites de tests."""

from stormshield_utilisateurs.modele import Utilisateur


def utilisateur(identifiant: str, *groupes: str, origine: str | None = None) -> Utilisateur:
    """Fabrique minimale d'utilisateur pour les tests.

    Args:
        identifiant: identifiant après normalisation (minuscules)
        *groupes: groupes d'appartenance
        origine: identifiant original du fichier (optionnel, défaut = identifiant)

    Returns:
        Instance d'Utilisateur avec remplissage minimal et cohérent.
    """
    return Utilisateur(
        ligne=2,
        identifiant=identifiant,
        identifiant_origine=origine if origine is not None else identifiant,
        nom="Dupont",
        prenom="Marie",
        groupes=groupes,
    )
