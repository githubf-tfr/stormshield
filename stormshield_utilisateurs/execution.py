"""Lecture de l'état du boîtier, puis application du plan. Émet des événements."""

import contextlib
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace

from stormshield_utilisateurs import motdepasse
from stormshield_utilisateurs import plan as construction_plan
from stormshield_utilisateurs.boitier import (
    Boitier,
    ErreurBoitier,
    ErreurCommande,
    ErreurFatale,
    ErreurReseau,
)
from stormshield_utilisateurs.modele import (
    CompteCree,
    Echec,
    EtatBoitier,
    Plan,
    PlancherPolitique,
    PolitiqueMotDePasse,
    Rapport,
    Utilisateur,
)

# CONFIG LDAP LIST, CONFIG PASSWDPOLICY SHOW, USER LIST, USER GROUP LIST.
NOMBRE_LECTURES = 4


class AnnuaireAbsent(Exception):
    """Aucun annuaire interne : c'est le seul cas où CONFIG LDAP INITIALIZE est atteignable."""


class AnnuaireDejaPresent(Exception):
    """Un annuaire répond déjà : CONFIG LDAP INITIALIZE écraserait sa base."""

    def __init__(self, annuaires: tuple[str, ...]) -> None:
        self.annuaires = annuaires
        super().__init__(
            "le boîtier déclare déjà un annuaire LDAP interne : "
            + ", ".join(annuaires)
            + ". L'initialisation écraserait sa base, elle est refusée."
        )


class AnnuairesMultiples(Exception):
    """Plusieurs annuaires : arrêt net, aucune écriture. USER GROUP CREATE ne sait
    pas viser un annuaire, les groupes partiraient on ne sait où."""

    def __init__(self, annuaires: tuple[str, ...]) -> None:
        self.annuaires = annuaires
        super().__init__(
            "le boîtier déclare plusieurs annuaires LDAP internes : "
            + ", ".join(annuaires)
            + ". L'outil s'arrête plutôt que de choisir."
        )


def lire_etat(boitier: Boitier) -> EtatBoitier:
    """Lecture seule. L'ordre est celui du flux d'exécution de la spec.

    Ouverture de session : les quatre lectures, avec le traitement des trois cas
    d'annuaire. En cas de reprise après coupure réseau en milieu de lot, utiliser
    plutôt `lire_comptes_et_groupes`, qui ne relit pas l'annuaire ni la politique.
    """
    annuaires = boitier.lister_annuaires()
    if not annuaires:
        raise AnnuaireAbsent("le boîtier ne déclare aucun annuaire LDAP interne")
    if len(annuaires) > 1:
        raise AnnuairesMultiples(tuple(annuaires))
    plancher = boitier.lire_politique()
    return EtatBoitier(
        domaine=annuaires[0],
        plancher=plancher,
        utilisateurs=frozenset(boitier.lister_utilisateurs()),
        groupes=frozenset(boitier.lister_groupes()),
    )


def lire_comptes_et_groupes(boitier: Boitier) -> tuple[frozenset[str], frozenset[str]]:
    """Reprise après reconnexion en milieu de lot : `USER LIST` et `USER GROUP LIST`
    seulement. Ni l'annuaire (lèverait `AnnuaireAbsent` sur un lot déjà entamé), ni
    la politique (ne change pas pendant un lot)."""
    return (
        frozenset(boitier.lister_utilisateurs()),
        frozenset(boitier.lister_groupes()),
    )


def creer_annuaire(
    boitier: Boitier, domainname: str, organisation: str, dc: str, mot_de_passe: str
) -> None:
    """Chemin conditionnel, atteignable seulement après AnnuaireAbsent. Ne se refait pas.

    `CONFIG LDAP INITIALIZE` écrase la base d'un annuaire existant : la fonction
    revérifie elle-même qu'aucun annuaire ne répond. Une protection qui repose sur
    la discipline de l'appelant n'en est pas une.
    """
    existants = boitier.lister_annuaires()
    if existants:
        raise AnnuaireDejaPresent(tuple(existants))
    boitier.initialiser_annuaire(domainname, organisation, dc, mot_de_passe)
    boitier.activer_annuaire()
    if domainname not in boitier.lister_annuaires():
        raise ErreurCommande(200, f"l'annuaire {domainname} n'apparaît pas après activation")


@dataclass(frozen=True)
class Patience:
    """Cadence des réessais. Injectable pour que les tests ne dorment pas.

    Les deux compteurs sont séparés parce qu'ils ne comptent pas la même chose :
    `tentatives_connexion` est un nombre de tentatives (aucune connexion en cours à
    conserver), `reessais_mot_de_passe` un nombre de réessais qui s'ajoutent à un
    premier appel déjà émis.
    """

    tentatives_connexion: int = 3
    reessais_mot_de_passe: int = 3
    delai: float = 2.0
    dormir: Callable[[float], None] = time.sleep


# Cadence de production : trois tentatives espacées de deux secondes, des deux côtés.
PATIENCE_PAR_DEFAUT = Patience()


@dataclass(frozen=True)
class Journal:
    """Ligne destinée au journal de la fenêtre. Texte d'affichage, jamais un aiguillage."""

    texte: str


@dataclass(frozen=True)
class PolitiqueLue:
    """Le plancher du boîtier est connu : les champs de politique peuvent s'activer."""

    plancher: PlancherPolitique


@dataclass(frozen=True)
class PlanPret:
    """Plan à afficher. Réémis après une reconnexion, avec le plan reconstruit."""

    plan: Plan


@dataclass(frozen=True)
class Progression:
    accomplies: int
    total: int


@dataclass(frozen=True)
class CreationReussie:
    """Un compte vient d'être créé, avec ou sans mot de passe.

    Émis compte par compte : sur un lot de 200 comptes, le bouton d'enregistrement
    des mots de passe s'active dès le premier, pas à la fin.
    """

    compte: CompteCree


@dataclass(frozen=True)
class Termine:
    rapport: Rapport


@dataclass(frozen=True)
class Echoue:
    """Arrêt avant toute écriture : annuaire absent ou multiple, connexion refusée."""

    message: str


Evenement = (
    Journal | PolitiqueLue | PlanPret | Progression | CreationReussie | Termine | Echoue
)
Emetteur = Callable[[Evenement], None]


@dataclass
class _Refuses:
    """Noms que le boîtier a explicitement refusés pendant le lot.

    Un refus n'est pas une perte de liaison : la commande a été reçue et rejetée,
    la rejouer donnerait le même verdict. Le plan reconstruit après une reconnexion
    les écarte, sans quoi le rapport porterait deux fois le même échec.
    """

    comptes: set[str] = field(default_factory=set)
    groupes: set[str] = field(default_factory=set)


class _Compteur:
    """Porte l'avancement de la barre de progression."""

    def __init__(self, emettre: Emetteur) -> None:
        self.accomplies = 0
        self.total = 0
        self._emettre = emettre

    def fixer_total(self, total: int) -> None:
        self.total = total
        self._emettre(Progression(self.accomplies, self.total))

    def avancer(self, pas: int = 1) -> None:
        """`pas` vaut le budget entier d'un compte quand ses opérations sont abandonnées :
        sans cela la barre n'atteindrait jamais son total."""
        self.accomplies += pas
        self._emettre(Progression(self.accomplies, self.total))


def executer(
    boitier: Boitier,
    utilisateurs: Sequence[Utilisateur],
    politique: PolitiqueMotDePasse,
    *,
    simulation: bool,
    emettre: Emetteur,
    patience: Patience = PATIENCE_PAR_DEFAUT,
    generer_mot_de_passe: Callable[[PolitiqueMotDePasse], str] = motdepasse.generer,
) -> Rapport:
    """Connexion, lecture, plan, puis écritures si Simulation est décochée.

    La connexion et la lecture ont lieu dans les deux modes : sans elles l'outil
    ne pourrait pas dire « déjà présent ».
    """
    rapport = Rapport()
    compteur = _Compteur(emettre)
    for utilisateur in utilisateurs:
        if utilisateur.bascule_minuscules:
            emettre(
                Journal(
                    f"ligne {utilisateur.ligne} : identifiant {utilisateur.identifiant_origine} "
                    f"basculé en minuscules -> {utilisateur.identifiant}"
                )
            )
    try:
        boitier.connecter()
        etat = lire_etat(boitier)
        emettre(PolitiqueLue(etat.plancher))
        plan_courant = construction_plan.construire(utilisateurs, etat)
        compteur.fixer_total(
            NOMBRE_LECTURES + (0 if simulation else plan_courant.nombre_operations())
        )
        for _ in range(NOMBRE_LECTURES):
            compteur.avancer()
        emettre(PlanPret(plan_courant))
        if not simulation:
            _appliquer(
                boitier,
                utilisateurs,
                etat,
                plan_courant,
                politique,
                rapport,
                compteur,
                emettre,
                patience,
                generer_mot_de_passe,
            )
    except ErreurFatale as erreur:
        # D'où qu'elle vienne — connexion initiale, lecture d'état, écriture en
        # cours de lot, tentative de reconnexion — une reconnexion ne la résoudra
        # jamais : aucun réessai, arrêt immédiat.
        _arreter_fatal(rapport, emettre, erreur)
    finally:
        # La déconnexion d'une liaison déjà perdue n'ajoute rien au rapport.
        with contextlib.suppress(ErreurBoitier):
            boitier.deconnecter()
    emettre(Termine(rapport))
    return rapport


def _appliquer(
    boitier: Boitier,
    utilisateurs: Sequence[Utilisateur],
    etat: EtatBoitier,
    plan_courant: Plan,
    politique: PolitiqueMotDePasse,
    rapport: Rapport,
    compteur: _Compteur,
    emettre: Emetteur,
    patience: Patience,
    generer_mot_de_passe: Callable[[PolitiqueMotDePasse], str],
) -> None:
    """Boucle d'écriture. Sur perte de liaison : reconnecte, reconstruit, reprend."""
    reste = plan_courant
    refuses = _Refuses()
    while True:
        try:
            _creer_groupes(boitier, reste, rapport, compteur, emettre, refuses)
            _creer_comptes(
                boitier, reste, politique, rapport, compteur, emettre,
                patience, generer_mot_de_passe, refuses,
            )
            return
        except ErreurReseau:
            emettre(Journal("liaison perdue, tentative de reconnexion"))
            if not _reconnecter(boitier, patience, emettre):
                _arreter(rapport, emettre, "liaison irrécupérable")
                return
            # On ne rejoue jamais la commande interrompue : on relit et on replanifie.
            operations_avant = reste.nombre_operations()
            try:
                reste = _replanifier(boitier, utilisateurs, etat, refuses)
            except ErreurFatale:
                # Classe fille d'ErreurBoitier : à intercepter avant elle, sinon
                # cette clause ne serait jamais atteinte.
                raise
            except ErreurBoitier as erreur:
                _arreter(rapport, emettre, f"relecture impossible ({erreur})")
                return
            # Seul un progrès autorise un tour de plus. Une écriture qui retombe
            # durablement laisse un plan identique : reboucler dessus ferait tourner
            # l'outil sans fin, à `delai` près, sans jamais rien créer de plus.
            if reste.nombre_operations() >= operations_avant:
                _arreter(
                    rapport, emettre,
                    "la reconnexion n'a fait progresser aucune écriture "
                    f"({reste.nombre_operations()} opérations restantes, "
                    f"{operations_avant} avant la coupure)",
                )
                return
            # Le plan a changé : le total aussi, sans quoi la barre viserait un total
            # qu'aucune opération restante ne peut plus atteindre.
            compteur.fixer_total(compteur.accomplies + reste.nombre_operations())
            emettre(PlanPret(reste))


def _arreter(rapport: Rapport, emettre: Emetteur, motif: str) -> None:
    rapport.interrompu = True
    emettre(
        Journal(
            f"arrêt : {motif}. Ce qui est créé reste créé, "
            "le CSV des mots de passe couvre les comptes réellement créés."
        )
    )


def _arreter_fatal(rapport: Rapport, emettre: Emetteur, erreur: ErreurFatale) -> None:
    """Arrêt immédiat, sans aucune reconnexion : contrairement à une liaison perdue,
    une ErreurFatale ne se résoudra pas en rejouant la même connexion — la répéter
    ne ferait qu'alimenter le verrouillage anti-bruteforce du boîtier."""
    rapport.interrompu = True
    emettre(
        Journal(
            f"arrêt définitif : {erreur}. Une reconnexion n'y changerait rien : "
            "corrigez les identifiants ou la configuration avant de relancer le lot. "
            "Ce qui est créé reste créé, le CSV des mots de passe couvre les comptes "
            "réellement créés."
        )
    )


def _replanifier(
    boitier: Boitier, utilisateurs: Sequence[Utilisateur], etat: EtatBoitier,
    refuses: _Refuses,
) -> Plan:
    """Reprise en milieu de lot : seuls les comptes et les groupes sont relus.

    L'annuaire et le plancher de politique du premier état sont conservés : ni l'un
    ni l'autre ne change pendant un lot, et les relire ferait lever `AnnuaireAbsent`
    sur un chemin que rien ne décrit.
    """
    comptes, groupes = lire_comptes_et_groupes(boitier)
    plan_reconstruit = construction_plan.construire(
        utilisateurs, replace(etat, utilisateurs=comptes, groupes=groupes)
    )
    # Ce que le boîtier a refusé ne repart pas : le refus est déjà au rapport, et le
    # rejouer le compterait une fois de plus sans rien créer.
    return replace(
        plan_reconstruit,
        comptes_a_creer=tuple(
            compte
            for compte in plan_reconstruit.comptes_a_creer
            if compte.identifiant not in refuses.comptes
        ),
        groupes_a_creer=tuple(
            groupe
            for groupe in plan_reconstruit.groupes_a_creer
            if groupe.nom not in refuses.groupes
        ),
    )


def _reconnecter(boitier: Boitier, patience: Patience, emettre: Emetteur) -> bool:
    for tentative in range(1, patience.tentatives_connexion + 1):
        patience.dormir(patience.delai)
        try:
            boitier.connecter()
        except ErreurFatale:
            # Classe fille d'ErreurBoitier : à intercepter avant elle. Réessayer une
            # authentification refusée n'aboutirait jamais et nourrirait le
            # verrouillage anti-bruteforce du boîtier — une seule tentative suffit
            # à le savoir.
            raise
        except ErreurBoitier:
            emettre(
                Journal(f"reconnexion {tentative}/{patience.tentatives_connexion} échouée")
            )
            continue
        emettre(Journal(f"reconnecté à la tentative {tentative}"))
        return True
    return False


def _creer_groupes(
    boitier: Boitier, plan_courant: Plan, rapport: Rapport,
    compteur: _Compteur, emettre: Emetteur, refuses: _Refuses,
) -> None:
    for groupe in plan_courant.groupes_a_creer:
        try:
            boitier.creer_groupe(groupe.nom)
        except ErreurCommande as erreur:
            refuses.groupes.add(groupe.nom)
            rapport.echecs.append(Echec(groupe.nom, "USER GROUP CREATE", str(erreur)))
            emettre(Journal(f"groupe {groupe.nom} : échec de création ({erreur})"))
        else:
            rapport.groupes_crees.append(groupe.nom)
            emettre(Journal(f"groupe {groupe.nom} : créé"))
        compteur.avancer()


def _creer_comptes(
    boitier: Boitier, plan_courant: Plan, politique: PolitiqueMotDePasse,
    rapport: Rapport, compteur: _Compteur, emettre: Emetteur,
    patience: Patience, generer_mot_de_passe: Callable[[PolitiqueMotDePasse], str],
    refuses: _Refuses,
) -> None:
    for utilisateur in plan_courant.comptes_a_creer:
        try:
            boitier.creer_utilisateur(
                utilisateur.identifiant, utilisateur.nom, utilisateur.prenom,
                plan_courant.domaine,
            )
        except ErreurCommande as erreur:
            refuses.comptes.add(utilisateur.identifiant)
            rapport.echecs.append(Echec(utilisateur.identifiant, "USER CREATE", str(erreur)))
            emettre(Journal(f"{utilisateur.identifiant} : échec de création ({erreur})"))
            # Aucun mot de passe n'a été généré : le secret n'est pas consommé.
            # Le budget entier du compte est consommé : ni USER PASSWORD ni les
            # USER GROUP ADDUSER n'auront lieu.
            compteur.avancer(2 + len(utilisateur.groupes))
            continue
        compteur.avancer()
        # Génération au moment de la création effective, jamais à la construction du plan.
        secret = generer_mot_de_passe(politique)
        # Le compte est inscrit au rapport dès sa création : le CSV de sortie est la
        # liste de reprise de l'opérateur, et une coupure survenue après USER CREATE
        # ne doit pas pouvoir effacer un compte qui existe bel et bien sur le boîtier.
        rang = len(rapport.comptes_crees)
        rapport.comptes_crees.append(CompteCree(utilisateur.identifiant, ""))
        try:
            retenu = _definir_mot_de_passe(
                boitier, utilisateur.identifiant, secret, rapport, emettre, patience
            )
        except ErreurReseau:
            _signaler_interruption(
                rapport, emettre, utilisateur.identifiant, "USER PASSWORD",
                "coupure réseau après la création : compte créé sans mot de passe "
                "utilisable, à reprendre à la main",
            )
            emettre(CreationReussie(rapport.comptes_crees[rang]))
            raise
        compteur.avancer()
        compte = CompteCree(utilisateur.identifiant, retenu)
        rapport.comptes_crees[rang] = compte
        emettre(Journal(f"{utilisateur.identifiant} : créé"))
        emettre(CreationReussie(compte))
        for rang_groupe, groupe in enumerate(utilisateur.groupes):
            try:
                boitier.ajouter_membre(groupe, utilisateur.identifiant)
            except ErreurCommande as erreur:
                rapport.echecs.append(
                    Echec(utilisateur.identifiant, "USER GROUP ADDUSER", str(erreur))
                )
                emettre(
                    Journal(f"{utilisateur.identifiant} : non rattaché à {groupe} ({erreur})")
                )
            except ErreurReseau:
                # Le plan reconstruit ne rattrapera pas ces rattachements : il ne
                # calcule d'ADDUSER que pour les comptes à créer, et celui-ci vient
                # de basculer dans les comptes déjà présents.
                restants = ", ".join(utilisateur.groupes[rang_groupe:])
                _signaler_interruption(
                    rapport, emettre, utilisateur.identifiant, "USER GROUP ADDUSER",
                    f"coupure réseau pendant le rattachement : groupes non rattachés "
                    f"({restants}), à reprendre à la main",
                )
                raise
            compteur.avancer()


def _signaler_interruption(
    rapport: Rapport, emettre: Emetteur, identifiant: str, operation: str, motif: str
) -> None:
    """Trace d'une coupure en plein travail sur un compte déjà créé.

    Sans elle, le compte sortirait du lot sans figurer ni aux échecs ni nulle part
    ailleurs : il existerait sur le boîtier et un relancement le classerait « déjà
    présent » à jamais, sans jamais le réparer.
    """
    rapport.echecs.append(Echec(identifiant, operation, motif))
    emettre(Journal(f"{identifiant} : {motif}"))


def _definir_mot_de_passe(
    boitier: Boitier, identifiant: str, secret: str, rapport: Rapport,
    emettre: Emetteur, patience: Patience,
) -> str:
    """Un appel puis jusqu'à `reessais_mot_de_passe` réessais. Rend le secret, ou ""."""
    for tentative in range(patience.reessais_mot_de_passe + 1):
        try:
            boitier.definir_mot_de_passe(identifiant, secret)
        except ErreurCommande as erreur:
            if tentative == patience.reessais_mot_de_passe:
                rapport.echecs.append(Echec(identifiant, "USER PASSWORD", str(erreur)))
                emettre(
                    Journal(
                        f"{identifiant} : créé sans mot de passe — à reprendre à la main "
                        f"({erreur})"
                    )
                )
                return ""
            patience.dormir(patience.delai)
        else:
            return secret
    return ""
