"""Frontière unique avec le firewall. Aucun import du SDK ici : voir boitier_sdk.py."""

from typing import Protocol

from stormshield_utilisateurs.modele import PlancherPolitique


class ErreurBoitier(Exception):  # noqa: N818 — français : « Erreur » préfixe, pas suffixe.
    """Racine des erreurs du dialogue avec le boîtier."""


class ErreurCommande(ErreurBoitier):
    """Le boîtier a répondu et a refusé : échec isolé, le lot continue."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"code {code} : {message}")


class ErreurReseau(ErreurBoitier):
    """La liaison est perdue : c'est le seul cas qui déclenche une reconnexion."""


class Boitier(Protocol):
    """Tout ce que l'outil sait demander à un firewall SNS, et rien de plus."""

    def connecter(self) -> None: ...

    def deconnecter(self) -> None: ...

    def lister_annuaires(self) -> list[str]:
        """CONFIG LDAP LIST : les noms de domaine des annuaires internes déclarés."""
        ...

    def initialiser_annuaire(
        self, domainname: str, organisation: str, dc: str, mot_de_passe: str
    ) -> None:
        """CONFIG LDAP INITIALIZE. Chemin conditionnel : voir execution.lire_etat."""
        ...

    def activer_annuaire(self) -> None: ...

    def lire_politique(self) -> PlancherPolitique:
        """CONFIG PASSWDPOLICY SHOW. Lecture seule : l'outil n'écrit jamais la politique."""
        ...

    def lister_utilisateurs(self) -> list[str]: ...

    def lister_groupes(self) -> list[str]: ...

    def creer_groupe(self, nom: str) -> None: ...

    def creer_utilisateur(
        self, identifiant: str, nom: str, prenom: str, domaine: str
    ) -> None: ...

    def definir_mot_de_passe(self, identifiant: str, mot_de_passe: str) -> None: ...

    def ajouter_membre(self, groupe: str, identifiant: str) -> None: ...
