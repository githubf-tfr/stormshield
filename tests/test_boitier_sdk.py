"""L'adaptateur n'est prouvé par rien tant qu'aucun boîtier n'est joignable.
Seules les parties textuelles se testent hors ligne."""

from typing import Any

import pytest
import requests
from stormshield.sns.sslclient import (
    AuthenticationError,
    ConfigParser,
    MissingCABundle,
    MissingHost,
    ServerError,
    TOTPNeededError,
)

from stormshield_utilisateurs.boitier import Boitier, ErreurCommande, ErreurFatale, ErreurReseau
from stormshield_utilisateurs.boitier_sdk import (
    DELAI_ATTENTE_PAR_DEFAUT,
    BoitierSDK,
    _lignes,
    _sans_secret,
    _section_unique,
    commande_ajouter_membre,
    commande_creer_groupe,
    commande_creer_utilisateur,
    lire_plancher,
)


def _conformite_au_protocol(adaptateur: BoitierSDK) -> Boitier:
    """Ligne de type, jamais un test : c'est mypy, pas pytest, qui prouve ici que BoitierSDK
    satisfait structurellement le Protocol Boitier — la vérification statique échoue si une
    méthode du Protocol manque ou diverge. Une fonction annotée le prouve autant qu'une
    instance, sans coder d'adresse ni d'identifiants dans le dépôt."""
    return adaptateur


class _ReponseFactice:
    """Réponse du SDK reconstituée : `ConfigParser` est celui du SDK installé, appliqué au
    texte `output` que produit `format_output`. Les types de `.data` sont donc les vrais
    (`CaseInsensitiveDict`), pas des `dict` de test qui masqueraient le défaut.

    `ret`, `msg` et `__bool__` sont fournis à part : `ConfigParser` les jette avec la ligne
    d'en-tête (il n'en tire que `format`), alors que c'est `ret` que `Response.__bool__` du
    vrai SDK teste pour décider d'un échec. Un double sans cette logique répondrait toujours
    vrai à `bool(...)`, et la branche `ErreurCommande` de l'adaptateur ne serait prouvée par
    aucun test hors ligne."""

    def __init__(self, sortie: str, ret: int = 100, msg: str = "Ok") -> None:
        analyseur = ConfigParser(sortie)
        self.data: Any = analyseur.data
        self.format: str = analyseur.format
        self.ret = ret
        self.msg = msg

    def __bool__(self) -> bool:
        return 100 <= self.ret < 200


def _reponse_section_line(
    titre: str, lignes: list[str], ret: int = 100, msg: str = "Ok"
) -> _ReponseFactice:
    corps = "".join(f"{ligne}\n" for ligne in lignes)
    return _ReponseFactice(
        f'{ret} code=00a01000 msg="{msg}" format="section_line"\n[{titre}]\n{corps}',
        ret=ret,
        msg=msg,
    )


def _reponse_section(titre: str, cles: list[str]) -> _ReponseFactice:
    corps = "".join(f"{cle}\n" for cle in cles)
    return _ReponseFactice(f'100 code=00a01000 msg="Ok" format="section"\n[{titre}]\n{corps}')


def test_commande_de_creation_d_utilisateur() -> None:
    assert commande_creer_utilisateur("dupont", "Dupont", "Marie", "interne.local") == (
        'USER CREATE uid=dupont name="Dupont" gname="Marie" domainname=interne.local'
    )


def test_prenom_vide_omet_gname() -> None:
    assert commande_creer_utilisateur("dupont", "Dupont", "", "interne.local") == (
        'USER CREATE uid=dupont name="Dupont" domainname=interne.local'
    )


def test_nom_compose_reste_un_seul_jeton() -> None:
    """Sans guillemets, `De La Tour` donnerait trois jetons au boîtier, qui découperait la
    commande autrement et sans rien signaler."""
    assert commande_creer_utilisateur("dupont", "De La Tour", "Jean Marie", "interne") == (
        'USER CREATE uid=dupont name="De La Tour" gname="Jean Marie" domainname=interne'
    )


def test_nom_de_groupe_transmis_verbatim_entre_guillemets() -> None:
    assert commande_creer_groupe("compta bis") == 'USER GROUP CREATE "compta bis"'


def test_appartenance_cite_le_groupe_comme_la_creation() -> None:
    """Citer à la création et pas au rattachement rendait « compta bis » inadressable."""
    assert commande_creer_groupe("compta bis").endswith('"compta bis"')
    assert commande_ajouter_membre("compta bis", "dupont") == (
        'USER GROUP ADDUSER "compta bis" dupont'
    )


def test_lecture_du_plancher_de_politique() -> None:
    """`MinSetOfChars` est un mot-clé, jamais un entier : c'est la forme que rend le boîtier."""
    donnees = {"MinLength": "12", "MinSetOfChars": "AlphaNum", "MinEntropy": "40"}
    plancher = lire_plancher(donnees)
    assert (plancher.longueur_min, plancher.nombre_classes_min, plancher.entropie_min) == (
        12,
        2,
        40,
    )


@pytest.mark.parametrize(
    ("brut", "attendu"), [("None", 1), ("AlphaNum", 2), ("AlphaSpecial", 3), ("alphanum", 2)]
)
def test_traduction_des_jeux_de_caracteres(brut: str, attendu: int) -> None:
    assert lire_plancher({"MinSetOfChars": brut}).nombre_classes_min == attendu


def test_un_entier_reste_accepte() -> None:
    """Au cas où un boîtier en rende un."""
    assert lire_plancher({"MinSetOfChars": "3"}).nombre_classes_min == 3


def test_jeu_de_caracteres_inconnu_leve_au_lieu_de_retomber_sur_zero() -> None:
    """Un plancher incompris n'est pas un plancher nul : l'adaptateur n'a pas à effacer le
    garde-fou dans la direction inverse de sa raison d'être."""
    with pytest.raises(ErreurFatale):
        lire_plancher({"MinSetOfChars": "AlphaNumSpecialInedit"})


def test_longueur_illisible_leve() -> None:
    with pytest.raises(ErreurFatale):
        lire_plancher({"MinLength": "illisible"})


def test_plancher_absent_retombe_sur_zero() -> None:
    """Un boîtier sans politique déclarée ne doit pas faire planter la lecture."""
    plancher = lire_plancher({})
    assert (plancher.longueur_min, plancher.nombre_classes_min) == (0, 0)


def test_les_lignes_d_une_vraie_reponse_sont_lues() -> None:
    """`.data` est une `CaseInsensitiveDict`, qui ne dérive pas de `dict` : un garde
    `isinstance(..., dict)` rendait une liste vide, donc un boîtier vu comme vierge et tout
    recréé à chaque passage — l'idempotence était rompue."""
    reponse = _reponse_section_line("Result", ["id=1 name=dupont", "id=2 name=martin"])
    assert not isinstance(reponse.data, dict)
    assert [ligne["name"] for ligne in _lignes(reponse)] == ["dupont", "martin"]


def test_la_section_d_une_vraie_reponse_est_lue() -> None:
    """Deux couches de `CaseInsensitiveDict` : `.data`, puis la valeur de la section."""
    reponse = _reponse_section(
        "PasswordPolicy", ["MinLength=12", "MinSetOfChars=AlphaNum", "MinEntropy=20"]
    )
    assert not isinstance(reponse.data["PasswordPolicy"], dict)
    plancher = lire_plancher(_section_unique(reponse))
    assert (plancher.longueur_min, plancher.nombre_classes_min, plancher.entropie_min) == (
        12,
        2,
        20,
    )


def test_une_ligne_etiquetee_dans_une_autre_casse_est_lue() -> None:
    """En `format="section_line"`, le SDK construit chaque ligne dans un `dict` nu : la casse
    des étiquettes de serverd n'est garantie par rien. Une ligne `Domain=` que l'adaptateur
    cherche sous `domain` rendrait un boîtier vu comme vierge — et les deux gardes de
    `CONFIG LDAP INITIALIZE`, la revérification de `creer_annuaire` comprise, sont la même
    mesure : elles tomberaient ensemble."""
    reponse = _reponse_section_line("Result", ["Domain=interne.local"])
    assert [ligne["domain"] for ligne in _lignes(reponse)] == ["interne.local"]
    boitier = _adaptateur(_ClientFactice(reponse=reponse))
    assert boitier.lister_annuaires() == ["interne.local"]


def test_les_comptes_et_les_groupes_se_lisent_quelle_que_soit_la_casse() -> None:
    """Même mécanisme sur `USER LIST` et `USER GROUP LIST` : une liste vide y signifie
    « rien sur le boîtier », donc tout à recréer à chaque passage."""
    reponse = _reponse_section_line("Result", ["NAME=dupont", "Name=martin"])
    boitier = _adaptateur(_ClientFactice(reponse=reponse))
    assert boitier.lister_utilisateurs() == ["dupont", "martin"]
    assert boitier.lister_groupes() == ["dupont", "martin"]


def test_le_plancher_se_lit_quelle_que_soit_la_casse() -> None:
    """Un jeton manqué vaut plancher nul, c'est-à-dire le garde-fou exactement à l'envers :
    toute politique passerait la vérification."""
    plancher = lire_plancher(
        {"minlength": "12", "MINSETOFCHARS": "AlphaNum", "minEntropy": "40"}
    )
    assert (plancher.longueur_min, plancher.nombre_classes_min, plancher.entropie_min) == (
        12,
        2,
        40,
    )


def test_la_section_fusionnee_reste_insensible_a_la_casse() -> None:
    """La fusion des sections ne doit pas retomber dans un `dict` nu : `.data` et la valeur
    de chaque section sont insensibles à la casse, la fusion doit l'être aussi."""
    reponse = _reponse_section("PasswordPolicy", ["minlength=12", "minsetofchars=AlphaSpecial"])
    fusion = _section_unique(reponse)
    assert fusion["MinLength"] == "12"
    plancher = lire_plancher(fusion)
    assert (plancher.longueur_min, plancher.nombre_classes_min) == (12, 3)


def test_une_reponse_brute_ne_fait_pas_planter_la_lecture() -> None:
    """`format="raw"` rend une chaîne, pas un Mapping."""
    reponse = _ReponseFactice('100 code=00a01000 msg="Ok" format="raw"\ntexte libre\n')
    assert _lignes(reponse) == []
    assert _section_unique(reponse) == {}


def test_le_mot_de_passe_encode_est_masque() -> None:
    """Le SDK encode `=` en `%3D` dans l'URL, et `requests` recopie cette URL dans le message
    de son exception : chercher la seule forme littérale laissait fuir le secret. Le masquage
    va jusqu'à la fin de la chaîne : ce qui suit (ici le « Caused by » ajouté par `requests`)
    est masqué avec lui, ce qui est sans conséquence, alors que s'arrêter plus tôt est une
    fuite."""
    url = "...&cmd=USER%20PASSWORD%20dn%3Ddupont%20password%3DSECRET-42 (Caused by ...)"
    masque = _sans_secret(url)
    assert "SECRET-42" not in masque
    assert "password%3D***" in masque
    assert "(Caused by ...)" not in masque


def test_le_mot_de_passe_en_clair_reste_masque() -> None:
    assert _sans_secret("USER PASSWORD dn=dupont password=SECRET-42") == (
        "USER PASSWORD dn=dupont password=***"
    )


def test_le_mot_de_passe_avec_espace_est_masque_jusqu_au_bout() -> None:
    """`USER PASSWORD` exclut l'espace de son jeu de caractères généré, mais
    `CONFIG LDAP INITIALIZE` reçoit le mot de passe de `cn=StormshieldAdmin`, saisi par
    l'opérateur et non contraint. S'arrêter au premier blanc (`\\S*`) ne masquait alors qu'un
    fragment : `password=mot de passe` devenait `password=*** de passe`."""
    assert _sans_secret(
        "CONFIG LDAP INITIALIZE domainname=interne.local o=Org dc=dc password=mot de passe"
    ) == "CONFIG LDAP INITIALIZE domainname=interne.local o=Org dc=dc password=***"
    assert _sans_secret("...password%3Dmot de passe (Caused by ...)") == "...password%3D***"


class _ClientFactice:
    """Tient la place de SSLClient. Aucun réseau : la fabrique est injectée."""

    def __init__(
        self,
        panne_a_l_envoi: Exception | None = None,
        reponse: _ReponseFactice | None = None,
    ) -> None:
        self.panne_a_l_envoi = panne_a_l_envoi
        self.reponse = reponse
        self.deconnexions = 0

    def send_command(self, commande: str) -> Any:
        del commande
        if self.panne_a_l_envoi is not None:
            raise self.panne_a_l_envoi
        if self.reponse is not None:
            return self.reponse
        return _reponse_section_line("Result", ["name=dupont"])

    def disconnect(self) -> None:
        self.deconnexions += 1


# Rien d'exploitable n'est codé ici : `.invalid` est un domaine de premier niveau réservé
# (RFC 2606), jamais résolvable, et la fabrique injectée n'atteint aucun réseau. Ni
# utilisateur ni mot de passe ne sont renseignés — la fabrique factice les ignore.
HOTE_INEXISTANT = "boitier.invalid"
SANS_IDENTITE = ""


class _FabriqueCapturante:
    """Fabrique injectée qui retient les mots-clés reçus par le constructeur du SDK.

    Une fabrique `lambda **_: client` les avalait tous sans en vérifier aucun : câbler
    `sslverifypeer=False, sslverifyhost=False` en dur dans l'adaptateur, ou supprimer le
    `timeout`, laissait toute la suite verte. Le seul contrôle de sécurité de bout en
    bout du produit n'avait alors aucune preuve automatisée.
    """

    def __init__(self, client: _ClientFactice | None = None) -> None:
        self.client = client if client is not None else _ClientFactice()
        self.mots_cles: dict[str, Any] = {}

    def __call__(self, **mots_cles: Any) -> Any:
        self.mots_cles = mots_cles
        return self.client


def _adaptateur(client: _ClientFactice) -> BoitierSDK:
    boitier = BoitierSDK(
        HOTE_INEXISTANT, SANS_IDENTITE, SANS_IDENTITE, fabrique_client=_FabriqueCapturante(client)
    )
    boitier.connecter()
    return boitier


@pytest.mark.parametrize("verifier", [True, False])
def test_la_case_de_verification_du_certificat_atteint_le_constructeur_du_sdk(
    verifier: bool,
) -> None:
    """Le contournement n'est jamais câblé en dur : il vient de la case décochée par
    l'opérateur, et les deux options du SDK doivent porter son choix — dans les deux
    états de la case, sans quoi un « toujours faux » passerait aussi bien qu'un
    « toujours vrai »."""
    fabrique = _FabriqueCapturante()
    boitier = BoitierSDK(
        HOTE_INEXISTANT,
        SANS_IDENTITE,
        SANS_IDENTITE,
        verifier_certificat=verifier,
        fabrique_client=fabrique,
    )
    boitier.connecter()
    assert fabrique.mots_cles["sslverifypeer"] is verifier
    assert fabrique.mots_cles["sslverifyhost"] is verifier
    assert fabrique.mots_cles["host"] == HOTE_INEXISTANT


def test_la_verification_du_certificat_est_active_sans_rien_demander() -> None:
    """Le défaut est la vérification : un oubli d'argument ne doit pas ouvrir la session
    à une interception."""
    fabrique = _FabriqueCapturante()
    BoitierSDK(
        HOTE_INEXISTANT, SANS_IDENTITE, SANS_IDENTITE, fabrique_client=fabrique
    ).connecter()
    assert fabrique.mots_cles["sslverifypeer"] is True
    assert fabrique.mots_cles["sslverifyhost"] is True


def test_le_delai_d_attente_atteint_le_constructeur_du_sdk() -> None:
    """Le SDK laisse `timeout=None` par défaut, c'est-à-dire l'attente indéfinie : un
    boîtier qui cesse de répondre figerait l'outil sans signal ni journal."""
    fabrique = _FabriqueCapturante()
    BoitierSDK(
        HOTE_INEXISTANT, SANS_IDENTITE, SANS_IDENTITE, fabrique_client=fabrique
    ).connecter()
    assert fabrique.mots_cles["timeout"] == DELAI_ATTENTE_PAR_DEFAUT
    choisi = _FabriqueCapturante()
    BoitierSDK(
        HOTE_INEXISTANT,
        SANS_IDENTITE,
        SANS_IDENTITE,
        delai_attente=7.5,
        fabrique_client=choisi,
    ).connecter()
    assert choisi.mots_cles["timeout"] == 7.5


@pytest.mark.parametrize(
    ("levee", "attendue"),
    [
        (AuthenticationError("mot de passe refusé"), ErreurFatale),
        (TOTPNeededError("TOTP is needed"), ErreurFatale),
        (MissingHost("Host parameter must be provided"), ErreurFatale),
        (MissingCABundle("bundle absent"), ErreurFatale),
        # Session invalide ou expirée : une reconnexion la résout, donc on réessaie.
        (ServerError("Expired session"), ErreurReseau),
        (requests.exceptions.ConnectionError("liaison coupée"), ErreurReseau),
    ],
)
def test_taxonomie_des_erreurs_de_connexion(levee: Exception, attendue: type) -> None:
    """Un mot de passe faux rangé en « on réessaie » faisait reconnecter l'outil en boucle,
    et cette boucle alimentait le verrouillage anti-bruteforce du boîtier."""

    def fabrique_en_panne(**_: Any) -> Any:
        raise levee

    boitier = BoitierSDK(
        HOTE_INEXISTANT, SANS_IDENTITE, SANS_IDENTITE, fabrique_client=fabrique_en_panne
    )
    with pytest.raises(attendue):
        boitier.connecter()


def test_authentification_refusee_en_cours_de_lot_est_fatale() -> None:
    """`send_command` lève AuthenticationError sur le code serverd 205."""
    boitier = _adaptateur(_ClientFactice(AuthenticationError("Authentication error")))
    with pytest.raises(ErreurFatale):
        boitier.lister_utilisateurs()


def test_un_defaut_de_code_ne_se_deguise_pas_en_perte_de_liaison() -> None:
    """Un `except Exception` nu faisait reconnecter l'appelant sur une AttributeError."""
    boitier = _adaptateur(_ClientFactice(AttributeError("défaut de l'adaptateur")))
    with pytest.raises(AttributeError):
        boitier.lister_utilisateurs()


def test_le_secret_ne_survit_pas_dans_la_chaine_des_causes() -> None:
    """Le message de `requests` porte l'URL, donc le mot de passe encodé : ni le message
    rendu ni `__cause__` ne doivent le laisser réapparaître dans une trace d'appel."""
    fuite = requests.exceptions.ConnectionError(
        "Max retries exceeded with url: /api/command?cmd=USER%20PASSWORD%20password%3DSECRET-42"
    )
    boitier = _adaptateur(_ClientFactice(fuite))
    with pytest.raises(ErreurReseau) as capture:
        boitier.definir_mot_de_passe("dupont", "SECRET-42")
    assert "SECRET-42" not in str(capture.value)
    assert capture.value.__cause__ is None
    # Le type de l'origine reste lisible : couper la chaîne ne coûte pas le diagnostic.
    assert "ConnectionError" in str(capture.value)


def test_le_boitier_refusant_une_commande_leve_erreur_commande() -> None:
    """`Response.__bool__` du vrai SDK est vrai seulement si `100 <= ret < 200` : au-delà, le
    boîtier a refusé la commande sans que la liaison tombe. Avec un double sans `ret`/`__bool__`
    fidèles, `bool(reponse)` valait toujours vrai et cette branche n'était atteinte par aucun
    test hors ligne."""
    reponse = _reponse_section_line("Result", [], ret=200, msg="Object not found")
    boitier = _adaptateur(_ClientFactice(reponse=reponse))
    with pytest.raises(ErreurCommande) as capture:
        boitier.lister_utilisateurs()
    assert (capture.value.code, capture.value.message) == (200, "Object not found")


def test_le_refus_du_boitier_ne_recopie_aucun_secret() -> None:
    """Le message du boîtier est repris tel quel dans `ErreurCommande`, et ce texte va
    désormais au journal de la fenêtre et dans une boîte de dialogue : un `CONFIG LDAP
    INITIALIZE` refusé peut y renvoyer la commande, mot de passe compris."""
    reponse = _reponse_section_line(
        "Result", [], ret=200, msg="Bad argument: password=SECRET-42"
    )
    boitier = _adaptateur(_ClientFactice(reponse=reponse))
    with pytest.raises(ErreurCommande) as capture:
        boitier.lister_utilisateurs()
    assert "SECRET-42" not in capture.value.message
    assert "password=***" in capture.value.message


def test_reconnecter_ferme_la_session_precedente() -> None:
    """Sans cela chaque reconnexion laissait une session ouverte sur le boîtier, jusqu'à
    la limite d'authentification."""
    client = _ClientFactice()
    boitier = _adaptateur(client)
    boitier.connecter()
    assert client.deconnexions == 1


def test_deconnecter_ne_leve_jamais() -> None:
    """Appelée depuis un `finally`, une déconnexion qui lève remplace l'erreur en cours."""

    class _LogoutEnPanne(_ClientFactice):
        def disconnect(self) -> None:
            raise requests.exceptions.ConnectionError("logout injoignable")

    boitier = _adaptateur(_LogoutEnPanne())
    boitier.deconnecter()


@pytest.mark.firewall
def test_connexion_a_un_boitier_reel() -> None:
    """Exclu par défaut. À exécuter avec `pytest -m firewall` et des identifiants fournis
    par variables d'environnement, jamais en dur.

    `SNS_VERIFIER_CERTIFICAT=0` contourne la vérification du certificat, pour un boîtier
    à certificat auto-signé. Le contournement était câblé en dur ici — le seul endroit
    du dépôt où il l'était, alors que le produit entier tient à ce qu'il ne le soit
    jamais. Il se lit comme les autres paramètres, et la vérification reste le défaut.
    """
    import os

    boitier = BoitierSDK(
        hote=os.environ["SNS_HOTE"],
        utilisateur=os.environ["SNS_UTILISATEUR"],
        mot_de_passe=os.environ["SNS_MOT_DE_PASSE"],
        verifier_certificat=os.environ.get("SNS_VERIFIER_CERTIFICAT", "1") != "0",
    )
    boitier.connecter()
    try:
        assert isinstance(boitier.lister_annuaires(), list)
    finally:
        boitier.deconnecter()
