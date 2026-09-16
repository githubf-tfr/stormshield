"""Seul module du paquet à importer le SDK Stormshield. Écrit contre la documentation et
contre le SDK réellement installé (`stormshield-sns-sslclient` 1.1.2), prouvé par aucun test
tant qu'aucun boîtier n'est joignable.

Limite connue, hors de portée de cet adaptateur : le SDK journalise sur le *root logger*.
Une application qui passerait la racine en DEBUG ferait journaliser l'URL complète par
`urllib3`, secret encodé compris, sans que `_sans_secret` puisse s'interposer. L'application
ne doit pas mettre la racine en DEBUG (cahier de recette)."""

import contextlib
import re
from collections.abc import Callable, Mapping
from typing import Any
from xml.etree.ElementTree import ParseError

import requests
from stormshield.sns.sslclient import (
    AuthenticationError,
    MissingAuth,
    MissingCABundle,
    MissingHost,
    ServerError,
    SSLClient,
    TOTPNeededError,
)

from stormshield_utilisateurs.boitier import ErreurCommande, ErreurFatale, ErreurReseau
from stormshield_utilisateurs.modele import PlancherPolitique

# Rien de ce qui suit ne se répare en rouvrant une session : mot de passe refusé (y compris
# le verrouillage anti-bruteforce, que chaque nouvelle tentative prolongerait), second
# facteur exigé, hôte ou bundle de CA manquant. `send_command` lève aussi
# AuthenticationError sur le code serverd 205.
_ERREURS_FATALES: tuple[type[Exception], ...] = (
    AuthenticationError,
    TOTPNeededError,
    MissingAuth,
    MissingHost,
    MissingCABundle,
)

# Ce qui se retente : les erreurs de transport de `requests` (connexion refusée, délai
# dépassé, TLS), une réponse XML tronquée, et ServerError — qui couvre notamment la session
# invalide (203) et la session expirée (204), deux cas qu'une reconnexion résout.
_ERREURS_DE_LIAISON: tuple[type[Exception], ...] = (
    ServerError,
    requests.exceptions.RequestException,
    ParseError,
)

# Aucun `except Exception` : une AttributeError ou une TypeError venue de l'adaptateur
# lui-même doit remonter telle quelle. La déguiser en perte de liaison ferait reconnecter
# l'appelant sur un défaut de code, indéfiniment.
_ERREURS_ATTENDUES: tuple[type[Exception], ...] = _ERREURS_FATALES + _ERREURS_DE_LIAISON

# Délai de connexion et de lecture, en secondes. Le SDK laisse `timeout=None` par défaut,
# c'est-à-dire l'attente indéfinie : sur un lot de plusieurs centaines de comptes, un boîtier
# qui cesse de répondre figerait l'outil sans signal ni journal. Trente secondes laissent
# largement passer la commande SNS la plus lente tout en bornant l'attente.
DELAI_ATTENTE_PAR_DEFAUT = 30.0

# Le SDK construit l'URL de la commande avec quote(), qui encode le « = » en « %3D » et
# laisse le mot de passe en clair derrière. Quand la liaison tombe, `requests` recopie cette
# URL dans le message de son exception : chercher la seule forme littérale « password= »
# laissait donc passer « password%3DSECRET ». Les deux formes sont couvertes, sans
# distinction de casse (quote() majuscule les chiffres hexadécimaux, pas toutes les
# bibliothèques).
#
# Le masquage va jusqu'à la fin de la chaîne (`.*` avec DOTALL, pas `\S*`) : dans les
# commandes concernées, le mot de passe est le dernier argument, et rien n'y contraint
# l'espace — `USER PASSWORD` l'exclut de son générateur, mais `CONFIG LDAP INITIALIZE` reçoit
# celui de `cn=StormshieldAdmin`, saisi par l'opérateur. S'arrêter au premier blanc ne
# masquait alors qu'un fragment (« password=mot de passe » devenait « password=*** de
# passe »). Masquer trop est sans conséquence ; masquer trop peu est une fuite.
_MOTIF_MOT_DE_PASSE = re.compile(r"(password)(=|%3D).*", re.IGNORECASE | re.DOTALL)


def _sans_secret(texte: str) -> str:
    """Neutralise tout `password=...` — encodé ou non, jusqu'à la fin de la chaîne — avant
    qu'un texte ne figure dans une trace ou un message d'erreur. S'applique aussi bien à la
    commande émise (`USER PASSWORD`, `CONFIG LDAP INITIALIZE`) qu'au message de l'exception
    levée par le SDK, qui porte l'URL complète et donc le secret encodé.
    """
    return _MOTIF_MOT_DE_PASSE.sub(r"\1\2***", texte)


def _origine_masquee(erreur: Exception) -> str:
    """Type et message de l'exception du SDK, secret neutralisé. Le type est conservé parce
    que la chaîne `__cause__` est coupée là où un secret peut circuler."""
    return f"{type(erreur).__name__} : {_sans_secret(str(erreur))}"


def _entre_guillemets(valeur: str) -> str:
    """Tout ce que la validation amont n'exige que « non vide » — nom, prénom, nom de groupe
    — passe par ici. `De La Tour` nu produirait trois jetons pour le boîtier, qui découperait
    la commande autrement et en silence : c'est le cas dangereux, et un patronyme composé est
    le cas normal, pas un cas limite.

    Le guillemet double n'est pas échappé : SNS ne documente aucun échappement. Une commande
    refusée par le boîtier est un échec signalé, remonté dans le rapport — largement
    préférable à un découpage silencieux.
    """
    return f'"{valeur}"'


def commande_creer_utilisateur(identifiant: str, nom: str, prenom: str, domaine: str) -> str:
    """`uid` et `domainname` partent nus : l'identifiant est contraint en amont à
    `^[a-z0-9._-]+$`, et le domaine est relu du boîtier lui-même."""
    morceaux = [f"USER CREATE uid={identifiant}", f"name={_entre_guillemets(nom)}"]
    if prenom:
        morceaux.append(f"gname={_entre_guillemets(prenom)}")
    morceaux.append(f"domainname={domaine}")
    return " ".join(morceaux)


def commande_creer_groupe(nom: str) -> str:
    return f"USER GROUP CREATE {_entre_guillemets(nom)}"


def commande_ajouter_membre(groupe: str, identifiant: str) -> str:
    """Le groupe est cité comme à la création : citer d'un côté et pas de l'autre rendait un
    groupe créé sous « compta bis » définitivement inadressable."""
    return f"USER GROUP ADDUSER {_entre_guillemets(groupe)} {identifiant}"


# `CONFIG PASSWDPOLICY SHOW` ne rend pas un nombre de classes de caractères mais un
# mot-clé : la documentation SNS donne MinSetOfChars=<None|AlphaNum|AlphaSpecial>. La
# correspondance vers un nombre de classes est une hypothèse, à confirmer au premier
# boîtier joignable (cahier de recette).
CLASSES_PAR_JEU_DE_CARACTERES = {"none": 1, "alphanum": 2, "alphaspecial": 3}


def _entier(donnees: Mapping[str, Any], cle: str) -> int:
    """Clé absente : plancher nul, un boîtier sans politique déclarée n'impose rien. Clé
    présente mais illisible : on lève. Rendre zéro effacerait le garde-fou dans la direction
    exactement inverse de sa raison d'être."""
    brut = donnees.get(cle)
    if brut is None:
        return 0
    try:
        return int(str(brut).strip())
    except ValueError:
        raise ErreurFatale(
            f"{cle} vaut « {brut} », que l'outil ne sait pas lire comme un entier : "
            "il s'arrête plutôt que d'abaisser le plancher de politique à zéro."
        ) from None


def _nombre_de_classes(donnees: Mapping[str, Any], cle: str) -> int:
    """Traduit MinSetOfChars. Accepte aussi un entier, au cas où un boîtier en rende un."""
    brut = donnees.get(cle)
    if brut is None:
        return 0
    texte = str(brut).strip()
    connu = CLASSES_PAR_JEU_DE_CARACTERES.get(texte.casefold())
    if connu is not None:
        return connu
    try:
        return int(texte)
    except ValueError:
        connues = ", ".join(sorted(CLASSES_PAR_JEU_DE_CARACTERES))
        raise ErreurFatale(
            f"{cle} vaut « {brut} », valeur inconnue (attendu : {connues}, ou un entier) : "
            "l'outil s'arrête plutôt que de deviner un plancher de classes de caractères."
        ) from None


def lire_plancher(donnees: Mapping[str, Any]) -> PlancherPolitique:
    return PlancherPolitique(
        longueur_min=_entier(donnees, "MinLength"),
        nombre_classes_min=_nombre_de_classes(donnees, "MinSetOfChars"),
        entropie_min=_entier(donnees, "MinEntropy"),
    )


def _lignes(reponse: Any) -> list[dict[str, Any]]:
    """Aplati les lignes d'une réponse `format="section_line"` (une ligne par utilisateur,
    groupe ou annuaire), quel que soit le nom de la section. `.data` associe un nom de
    section à sa liste de lignes ; ce nom lui-même n'est pas exploité ici, seule sa forme
    (section -> liste de dictionnaires) l'est. Les clés de chaque ligne (`name`, `domain`,
    ...) restent à confirmer au premier boîtier joignable (cahier de recette).

    `.data` est une `CaseInsensitiveDict`, qui dérive de `MutableMapping` et **pas** de
    `dict` : un garde `isinstance(..., dict)` rendait systématiquement une liste vide, donc
    un boîtier vu comme vierge et tout recréé à chaque passage. Le test se fait sur
    `Mapping`.
    """
    donnees = getattr(reponse, "data", None)
    if not isinstance(donnees, Mapping):
        return []
    lignes: list[dict[str, Any]] = []
    for section in donnees.values():
        if isinstance(section, list):
            lignes.extend(dict(ligne) for ligne in section if isinstance(ligne, Mapping))
    return lignes


def _section_unique(reponse: Any) -> dict[str, Any]:
    """Fusionne les sections d'une réponse `format="section"` (ex. politique de mot de
    passe : un seul jeu de réglages par boîtier) en un seul dictionnaire de jetons.

    Deux couches à traverser, `Mapping` aux deux : `.data` est une `CaseInsensitiveDict`, et
    la valeur de chaque section en est une autre. Un `format="raw"` rend une chaîne, que le
    garde écarte."""
    donnees = getattr(reponse, "data", None)
    fusion: dict[str, Any] = {}
    if not isinstance(donnees, Mapping):
        return fusion
    for section in donnees.values():
        if isinstance(section, Mapping):
            fusion.update(section)
    return fusion


class BoitierSDK:
    """Adaptateur : une commande par aller-retour, jamais plus d'une session."""

    def __init__(
        self,
        hote: str,
        utilisateur: str,
        mot_de_passe: str,
        verifier_certificat: bool = True,
        delai_attente: float = DELAI_ATTENTE_PAR_DEFAUT,
        fabrique_client: Callable[..., Any] = SSLClient,
    ) -> None:
        self._hote = hote
        self._utilisateur = utilisateur
        self._mot_de_passe = mot_de_passe
        # Le contournement n'est jamais câblé en dur : il vient d'une case décochée
        # par l'opérateur, à chaque session. Par défaut la vérification reste active.
        self._verifier = verifier_certificat
        self._delai_attente = delai_attente
        # Seule couture d'injection de l'adaptateur : en production c'est SSLClient, et
        # l'ouverture de session a lieu dans son constructeur. Sans elle, la traduction des
        # exceptions du SDK ne serait prouvable que sur un boîtier joignable.
        self._fabrique_client = fabrique_client
        self._client: SSLClient | None = None

    def connecter(self) -> None:
        # Une session précédente n'est jamais abandonnée derrière soi : `ErreurReseau`
        # déclenche précisément des reconnexions, et chaque session laissée ouverte compte
        # dans la limite d'authentification du boîtier. `deconnecter()` ne lève pas, donc
        # une session déjà morte n'empêche pas d'en ouvrir une neuve.
        self.deconnecter()
        # autoconnect=True (le défaut du SDK) : le constructeur ouvre déjà la session.
        try:
            self._client = self._fabrique_client(
                user=self._utilisateur,
                password=self._mot_de_passe,
                host=self._hote,
                sslverifypeer=self._verifier,
                sslverifyhost=self._verifier,
                # Le SDK range ce délai dans conn_options : il couvre du même coup la
                # connexion, chaque commande et la déconnexion.
                timeout=self._delai_attente,
            )
        # Ici la chaîne des causes est conservée : le SDK authentifie par POST, mot de passe
        # dans le corps encodé en base64 et jamais dans l'URL, donc aucun message d'exception
        # de `requests` ne le porte — contrairement à `_envoyer`, où la commande voyage dans
        # l'URL. Le masquage reste appliqué par principe.
        except _ERREURS_FATALES as erreur:
            raise ErreurFatale(
                f"connexion à {self._hote} refusée : {_origine_masquee(erreur)}"
            ) from erreur
        except _ERREURS_DE_LIAISON as erreur:
            raise ErreurReseau(
                f"connexion impossible à {self._hote} : {_origine_masquee(erreur)}"
            ) from erreur

    def deconnecter(self) -> None:
        """N'absorbe que les familles attendues (`_ERREURS_ATTENDUES`) : une `AttributeError`,
        une `RuntimeError`, une `ValueError` nue ou un `KeyboardInterrupt` remontent tels
        quels — un bug de l'adaptateur ne doit pas se déguiser en simple échec de
        déconnexion. Une déconnexion s'appelle presque toujours depuis un `finally` : si une
        erreur attendue levait, son exception remplacerait celle en cours et la vraie cause de
        l'arrêt serait perdue. Un logout raté, parmi les erreurs attendues, est cosmétique —
        la session expirera d'elle-même côté boîtier ; décider qu'il interrompt le lot
        appartient à l'appelant, pas à l'adaptateur."""
        client, self._client = self._client, None
        if client is None:
            return
        with contextlib.suppress(*_ERREURS_ATTENDUES):
            client.disconnect()

    def _envoyer(self, commande: str) -> Any:
        if self._client is None:
            raise ErreurReseau("aucune session ouverte")
        try:
            reponse = self._client.send_command(commande)
        # `from None` et non `from erreur` : le message de l'exception d'origine porte l'URL
        # complète, donc le mot de passe encodé. La chaîner la ferait réapparaître en clair
        # dans toute trace d'appel affichée à l'opérateur, sous « direct cause of ». Rien
        # n'est perdu : le type et le texte masqués de l'origine sont repris ci-dessous.
        except _ERREURS_FATALES as erreur:
            # Code serverd 205 : la session n'est plus authentifiée et la rouvrir avec les
            # mêmes identifiants ne changerait rien.
            raise ErreurFatale(
                f"authentification refusée pendant « {_sans_secret(commande)} » : "
                f"{_origine_masquee(erreur)}"
            ) from None
        except _ERREURS_DE_LIAISON as erreur:
            raise ErreurReseau(
                f"liaison perdue pendant « {_sans_secret(commande)} » : "
                f"{_origine_masquee(erreur)}"
            ) from None
        # Response.__bool__ est vrai lorsque 100 <= ret < 200 : au-delà, le boîtier a
        # refusé la commande (échec isolé), la liaison elle-même reste valide.
        if not reponse:
            raise ErreurCommande(int(reponse.ret), str(reponse.msg))
        return reponse

    def lister_annuaires(self) -> list[str]:
        # À confirmer sur boîtier (cahier de recette) : `CONFIG LDAP LIST` liste aussi les
        # annuaires externes, qu'aucun filtre ne distingue ici alors que le Protocol parle
        # d'annuaires internes. La clé `domain` est elle-même une supposition.
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
