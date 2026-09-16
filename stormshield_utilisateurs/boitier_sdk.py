"""Seul module du paquet à importer le SDK Stormshield. Écrit contre la documentation et
contre le SDK réellement installé (`stormshield-sns-sslclient` 1.1.2), prouvé par aucun test
tant qu'aucun boîtier n'est joignable."""

import re
from typing import Any

from stormshield.sns.sslclient import SSLClient

from stormshield_utilisateurs.boitier import ErreurCommande, ErreurReseau
from stormshield_utilisateurs.modele import PlancherPolitique

_MOTIF_MOT_DE_PASSE = re.compile(r"password=\S*")


def _sans_secret(commande: str) -> str:
    """Neutralise tout `password=...` avant qu'une commande ne figure dans une trace ou un
    message d'erreur : ni `USER PASSWORD`, ni `CONFIG LDAP INITIALIZE` ne doivent y répéter
    leur mot de passe en clair."""
    return _MOTIF_MOT_DE_PASSE.sub("password=***", commande)


def commande_creer_utilisateur(identifiant: str, nom: str, prenom: str, domaine: str) -> str:
    morceaux = [f"USER CREATE uid={identifiant}", f"name={nom}"]
    if prenom:
        morceaux.append(f"gname={prenom}")
    morceaux.append(f"domainname={domaine}")
    return " ".join(morceaux)


def commande_creer_groupe(nom: str) -> str:
    """Nom transmis verbatim entre guillemets : un guillemet dans le nom ne passe pas."""
    return f'USER GROUP CREATE "{nom}"'


def commande_ajouter_membre(groupe: str, identifiant: str) -> str:
    return f"USER GROUP ADDUSER {groupe} {identifiant}"


def lire_plancher(donnees: dict[str, Any]) -> PlancherPolitique:
    def entier(cle: str) -> int:
        try:
            return int(donnees.get(cle, 0))
        except (TypeError, ValueError):
            return 0

    return PlancherPolitique(
        longueur_min=entier("MinLength"),
        nombre_classes_min=entier("MinSetOfChars"),
        entropie_min=entier("MinEntropy"),
    )


def _lignes(reponse: Any) -> list[dict[str, Any]]:
    """Aplati les lignes d'une réponse `format="section_line"` (une ligne par utilisateur,
    groupe ou annuaire), quel que soit le nom de la section. `.data` associe un nom de
    section à sa liste de lignes ; ce nom lui-même n'est pas exploité ici, seule sa forme
    (section -> liste de dictionnaires) l'est. Les clés de chaque ligne (`name`, `domain`,
    ...) restent à confirmer au premier boîtier joignable (cahier de recette)."""
    donnees = getattr(reponse, "data", None)
    if not isinstance(donnees, dict):
        return []
    lignes: list[dict[str, Any]] = []
    for section in donnees.values():
        if isinstance(section, list):
            lignes.extend(ligne for ligne in section if isinstance(ligne, dict))
    return lignes


def _section_unique(reponse: Any) -> dict[str, Any]:
    """Fusionne les sections d'une réponse `format="section"` (ex. politique de mot de
    passe : un seul jeu de réglages par boîtier) en un seul dictionnaire de jetons."""
    donnees = getattr(reponse, "data", None)
    fusion: dict[str, Any] = {}
    if not isinstance(donnees, dict):
        return fusion
    for section in donnees.values():
        if isinstance(section, dict):
            fusion.update(section)
    return fusion


class BoitierSDK:
    """Adaptateur : une commande par aller-retour, jamais plus d'une session."""

    def __init__(
        self, hote: str, utilisateur: str, mot_de_passe: str, verifier_certificat: bool = True
    ) -> None:
        self._hote = hote
        self._utilisateur = utilisateur
        self._mot_de_passe = mot_de_passe
        # Le contournement n'est jamais câblé en dur : il vient d'une case décochée
        # par l'opérateur, à chaque session. Par défaut la vérification reste active.
        self._verifier = verifier_certificat
        self._client: SSLClient | None = None

    def connecter(self) -> None:
        # autoconnect=True (le défaut du SDK) : le constructeur ouvre déjà la session.
        try:
            self._client = SSLClient(
                user=self._utilisateur,
                password=self._mot_de_passe,
                host=self._hote,
                sslverifypeer=self._verifier,
                sslverifyhost=self._verifier,
            )
        except Exception as erreur:
            raise ErreurReseau(f"connexion impossible à {self._hote} : {erreur}") from erreur

    def deconnecter(self) -> None:
        if self._client is None:
            return
        try:
            self._client.disconnect()
        except Exception as erreur:
            raise ErreurReseau(f"déconnexion de {self._hote} en échec : {erreur}") from erreur
        finally:
            self._client = None

    def _envoyer(self, commande: str) -> Any:
        if self._client is None:
            raise ErreurReseau("aucune session ouverte")
        try:
            reponse = self._client.send_command(commande)
        except Exception as erreur:
            raise ErreurReseau(
                f"liaison perdue pendant « {_sans_secret(commande)} » : {erreur}"
            ) from erreur
        # Response.__bool__ est vrai lorsque 100 <= ret < 200 : au-delà, le boîtier a
        # refusé la commande (échec isolé), la liaison elle-même reste valide.
        if not reponse:
            raise ErreurCommande(int(reponse.ret), str(reponse.msg))
        return reponse

    def lister_annuaires(self) -> list[str]:
        reponse = self._envoyer("CONFIG LDAP LIST")
        return [str(ligne["domain"]) for ligne in _lignes(reponse) if ligne.get("domain")]

    def initialiser_annuaire(
        self, domainname: str, organisation: str, dc: str, mot_de_passe: str
    ) -> None:
        self._envoyer(
            f"CONFIG LDAP INITIALIZE domainname={domainname} o={organisation} "
            f"dc={dc} password={mot_de_passe}"
        )

    def activer_annuaire(self) -> None:
        self._envoyer("CONFIG LDAP ACTIVATE")

    def lire_politique(self) -> PlancherPolitique:
        reponse = self._envoyer("CONFIG PASSWDPOLICY SHOW")
        return lire_plancher(_section_unique(reponse))

    def lister_utilisateurs(self) -> list[str]:
        reponse = self._envoyer("USER LIST")
        return [str(ligne["name"]) for ligne in _lignes(reponse) if ligne.get("name")]

    def lister_groupes(self) -> list[str]:
        reponse = self._envoyer("USER GROUP LIST")
        return [str(ligne["name"]) for ligne in _lignes(reponse) if ligne.get("name")]

    def creer_groupe(self, nom: str) -> None:
        self._envoyer(commande_creer_groupe(nom))

    def creer_utilisateur(self, identifiant: str, nom: str, prenom: str, domaine: str) -> None:
        self._envoyer(commande_creer_utilisateur(identifiant, nom, prenom, domaine))

    def definir_mot_de_passe(self, identifiant: str, mot_de_passe: str) -> None:
        # Le mot de passe ne doit figurer dans aucune trace : _sans_secret() le masque
        # avant toute inclusion dans un message d'erreur.
        self._envoyer(f"USER PASSWORD dn={identifiant} password={mot_de_passe}")

    def ajouter_membre(self, groupe: str, identifiant: str) -> None:
        self._envoyer(commande_ajouter_membre(groupe, identifiant))
