"""Fabriques de test partagées par les suites de tests."""

from stormshield_utilisateurs.modele import Utilisateur


class _Interrupteur:
    """Le bouton *Arrêter* de la fenêtre, réduit à ce que le métier en voit.

    En production c'est un `threading.Event` posé depuis le fil de l'interface ; ici le
    test le bascule lui-même, au moment exact qu'il veut éprouver.
    """

    def __init__(self, *, demande: bool = False) -> None:
        self.demande = demande

    def demander(self) -> None:
        self.demande = True

    def __call__(self) -> bool:
        return self.demande


def utilisateur(
    identifiant: str,
    *groupes: str,
    ligne: int = 2,
    origine: str | None = None,
) -> Utilisateur:
    """Fabrique minimale d'utilisateur pour les tests.

    Args:
        identifiant: identifiant après normalisation (minuscules)
        *groupes: groupes d'appartenance
        ligne: numéro d'enregistrement (en-tête = 1, défaut = 2)
        origine: identifiant original du fichier (optionnel, défaut = identifiant)

    Returns:
        Instance d'Utilisateur avec remplissage minimal et cohérent.
    """
    return Utilisateur(
        ligne=ligne,
        identifiant=identifiant,
        identifiant_origine=origine if origine is not None else identifiant,
        nom="Dupont",
        prenom="Marie",
        groupes=groupes,
    )
