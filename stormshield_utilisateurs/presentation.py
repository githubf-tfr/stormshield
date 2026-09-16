"""Tout ce que la fenêtre décide, calcule ou affiche, sans le moindre widget.

Ce module n'importe jamais `tkinter` : c'est ce qui rend la logique de l'interface
vérifiable par des tests, y compris là où `tkinter` n'est pas installé. `fenetre.py`
ne fait que câbler des widgets sur ce qui est défini ici.

Aucune chaîne de caractères ne pilote un branchement : les messages qui circulent
entre le fil d'exécution et la fenêtre sont des types, et les exceptions du métier
sont aiguillées sur leur classe.
"""

import contextlib
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue

from stormshield_utilisateurs import motdepasse
from stormshield_utilisateurs.boitier import Boitier, ErreurBoitier
from stormshield_utilisateurs.boitier_sdk import BoitierSDK
from stormshield_utilisateurs.execution import (
    AnnuaireAbsent,
    AnnuaireDejaPresent,
    Echoue,
    Evenement,
    Journal,
    PolitiqueRefusee,
    Progression,
    Termine,
    creer_annuaire,
    executer,
)
from stormshield_utilisateurs.modele import (
    CompteCree,
    MotifArret,
    Plan,
    PlancherPolitique,
    PolitiqueMotDePasse,
    Rapport,
    Rejet,
    Utilisateur,
)

PERIODE_POMPE_MS = 100

# Politique de repli, le temps qu'une première lecture fasse connaître le plancher du
# boîtier. Elle peut partir en lot réel : le métier la confronte au plancher qu'il vient
# de lire et émet `PolitiqueRefusee` avant le moindre envoi si elle ne le tient pas.
POLITIQUE_INITIALE = motdepasse.proposer(PlancherPolitique(0, 0, 0))


@dataclass(frozen=True)
class AnnuaireManquant:
    """Le boîtier n'a aucun annuaire interne : la fenêtre propose d'en créer un.

    Message distinct d'`Echoue` parce que la fenêtre en fait autre chose qu'un
    affichage — c'est le seul cas qui ouvre la fenêtre de création.
    """


@dataclass(frozen=True)
class AnnuaireCree:
    """L'annuaire vient d'être initialisé puis activé. Ne se refait pas."""

    domaine: str


# Ce qui circule du fil d'exécution vers la fenêtre : les événements du métier, plus
# les deux verdicts que seule la fenêtre sait traiter.
MessageFil = Evenement | AnnuaireManquant | AnnuaireCree
Publieur = Callable[[MessageFil], None]

# Rien ne suit un message terminal : la pompe s'arrête, le bouton Lancer se réactive.
_TERMINAUX: tuple[type, ...] = (Termine, Echoue, AnnuaireManquant, AnnuaireCree)


@dataclass(frozen=True)
class Connexion:
    """De quoi ouvrir une session sur le boîtier, et rien de plus.

    Séparé des paramètres du lot parce que la création d'un annuaire ouvre sa propre
    session sans rien avoir à savoir d'un CSV ni d'une politique de mot de passe.

    Aucun identifiant n'est mémorisé d'un lancement à l'autre : cet objet naît au clic
    sur *Lancer* et disparaît avec le fil qui l'a reçu.
    """

    hote: str
    compte: str
    mot_de_passe: str
    verifier_certificat: bool


@dataclass(frozen=True)
class Parametres:
    """Tout ce dont le fil d'exécution a besoin, lu dans le fil de l'interface.

    Le fil ne touche aucun widget : il ne lit que cet objet, figé avant son démarrage.
    """

    connexion: Connexion
    fichier: Path
    simulation: bool
    politique: PolitiqueMotDePasse


@dataclass(frozen=True)
class ParametresAnnuaire:
    """Saisie de la fenêtre de création d'annuaire.

    `mot_de_passe` est celui de `cn=StormshieldAdmin`, saisi par l'opérateur : l'outil
    ne le génère pas et ne le conserve nulle part après l'envoi de la commande.
    """

    domainname: str
    organisation: str
    dc: str
    mot_de_passe: str


def est_terminal(message: MessageFil) -> bool:
    """Vrai si plus rien ne suivra ce message. Aiguillage sur le type, jamais sur un texte."""
    return isinstance(message, _TERMINAUX)


def message_de_fil(erreur: BaseException) -> MessageFil:
    """Traduit une exception qui a traversé le métier en message pour la fenêtre.

    Le fil d'exécution n'a pas d'appelant : une exception qu'il laisserait passer
    disparaîtrait sans rien afficher à l'opérateur.
    """
    match erreur:
        case AnnuaireAbsent():
            return AnnuaireManquant()
        case AnnuaireDejaPresent():
            return Echoue(
                f"{erreur} Un annuaire est apparu entre-temps : il n'y a plus rien à créer."
            )
        case _:
            return Echoue(str(erreur))


@dataclass(frozen=True)
class IncidentInterface:
    """Une exception a traversé le fil de l'interface.

    `message` est celui dont l'application a levé, ou None quand l'exception vient du
    gestionnaire global de Tk — elle remonte alors d'un callback de widget, hors de
    toute file.
    """

    erreur: BaseException
    message: MessageFil | None = None


Signaleur = Callable[[IncidentInterface], None]


def lignes_de_l_incident(incident: IncidentInterface) -> list[str]:
    """Trace complète, destinée au journal de la fenêtre.

    Le produit n'a par conception aucun fichier de journal, et un exécutable construit
    en mode fenêtré n'a pas de `stderr` : ce que Tk y écrirait n'existerait nulle part.
    """
    en_traitant = (
        "" if incident.message is None else f" en traitant {type(incident.message).__name__}"
    )
    lignes = [
        f"anomalie interne de l'interface{en_traitant} : "
        f"{type(incident.erreur).__name__} : {incident.erreur}"
    ]
    trace = "".join(traceback.format_exception(incident.erreur)).splitlines()
    lignes.extend(trace)
    return lignes


class BoiteParLot:
    """Autorise une seule boîte de dialogue d'anomalie par lot.

    Une boîte modale Tk fait tourner une boucle d'événements imbriquée : ouverte depuis
    l'intérieur d'un tour de pompe, elle laisse ce tour se rappeler lui-même. Une panne
    d'affichage persistante ouvrirait alors une boîte par message — des centaines sur un
    lot de deux cents comptes, empilées et imbriquées, jusqu'à ce que l'opérateur ne
    puisse plus rien atteindre. La première anomalie du lot se dit donc à l'écran, les
    suivantes n'existent que dans le journal de la fenêtre.
    """

    def __init__(self) -> None:
        self._deja_ouverte = False

    def doit_ouvrir(self) -> bool:
        """Vrai une seule fois par lot. Consomme le droit d'ouvrir."""
        deja, self._deja_ouverte = self._deja_ouverte, True
        return not deja

    def reinitialiser(self) -> None:
        """Au démarrage d'un lot : le silence ne vaut que pour le lot qui a déjà parlé."""
        self._deja_ouverte = False


def resume_de_l_incident(incident: IncidentInterface) -> str:
    """Une phrase pour la boîte de dialogue ; le détail reste dans le journal."""
    return (
        f"{type(incident.erreur).__name__} : {incident.erreur}\n\n"
        "L'affichage a peut-être manqué des étapes ; la trace complète est dans le "
        "journal de la fenêtre. Le travail déjà lancé sur le firewall, lui, se poursuit : "
        "le bouton « Lancer » reste donc grisé jusqu'au bilan de ce lot.\n\n"
        "Les anomalies suivantes de ce lot n'iront plus qu'au journal de la fenêtre."
    )


def texte_de_demarrage_impossible(erreur: BaseException) -> str:
    """Ce qui s'affiche quand la fenêtre n'a même pas pu naître.

    `tkinter` absent ou aucun affichage utilisable : l'exception partirait sur `stderr`,
    et un exécutable construit en mode fenêtré n'en a pas — il ne ferait rien du tout.
    """
    return (
        f"L'interface n'a pas pu démarrer.\n\n{type(erreur).__name__} : {erreur}\n\n"
        "Causes les plus fréquentes : le paquet tkinter n'est pas installé avec ce "
        "Python, ou aucun affichage n'est utilisable depuis cette session."
    )


def ligne_de_message_inconnu(message: MessageFil) -> str:
    """Un message qu'aucune branche ne reconnaît ne doit pas disparaître en silence."""
    return (
        f"message non affiché, type inconnu de la fenêtre : {type(message).__name__}. "
        "Le lot se poursuit ; signalez cette ligne."
    )


class PompeEvenements:
    """Vide la file de messages dans le fil de l'interface.

    Le fil d'exécution n'appelle jamais un widget : il dépose dans la file, et cette
    pompe — replanifiée par `after()` — est seule à en sortir les messages. La
    planification est injectée pour que la pompe se teste sans fenêtre.

    Rien de ce qu'applique la pompe ne peut l'empêcher de se replanifier : une
    exception qui remonterait jusqu'ici emporterait la replanification avec elle, et
    la file cesserait d'être vidée — barre et journal gelés, bouton *Lancer* grisé,
    pendant que le fil continue d'écrire sur le firewall.
    """

    def __init__(
        self,
        file: "Queue[MessageFil]",
        appliquer: Publieur,
        planifier: Callable[[int, Callable[[], None]], None],
        signaler: Signaleur,
        periode_ms: int = PERIODE_POMPE_MS,
    ) -> None:
        self._file = file
        self._appliquer = appliquer
        self._planifier = planifier
        self._signaler = signaler
        self._periode_ms = periode_ms
        self.active = True

    def tour(self) -> None:
        while True:
            try:
                message = self._file.get_nowait()
            except Empty:
                break
            # Le message terminal n'interrompt pas la boucle : ce qui le précède dans
            # la file est déjà écrit et doit s'afficher.
            try:
                self._appliquer(message)
            except Exception as erreur:
                self._rendre_visible(IncidentInterface(erreur, message))
            # Évalué même si l'application a levé : sans cela la pompe tournerait sans
            # fin sur une file que plus rien n'alimente.
            if est_terminal(message):
                self.active = False
        if self.active:
            self._planifier(self._periode_ms, self.tour)

    def _rendre_visible(self, incident: IncidentInterface) -> None:
        # Le signalement touche lui-même des widgets : s'il lâche à son tour, il n'y a
        # plus rien au-dessus, et la pompe doit quand même se replanifier.
        with contextlib.suppress(Exception):
            self._signaler(incident)


def politique_a_afficher(
    politique_courante: PolitiqueMotDePasse | None, plancher: PlancherPolitique
) -> PolitiqueMotDePasse:
    """Pré-remplissage à la première lecture seulement.

    Une relecture du boîtier ne réécrit jamais un réglage que l'opérateur a durci :
    un durcissement effacé en silence serait pire que pas de rafraîchissement du tout.
    """
    if politique_courante is not None:
        return politique_courante
    return motdepasse.proposer(plancher)


def libelle_plancher(plancher: PlancherPolitique) -> str:
    """Reprend les noms des jetons SNS : l'opérateur les retrouve tels quels sur le boîtier."""
    return (
        f"politique du boîtier : MinLength={plancher.longueur_min}, "
        f"MinSet={plancher.nombre_classes_min}, MinEntropy={plancher.entropie_min}"
    )


def reglage_barre(progression: Progression) -> tuple[int, int]:
    """Rend le couple (maximum, valeur) de la barre.

    Le total ne croît jamais : un plan reconstruit après reconnexion ne peut que le
    réduire, et la barre doit suivre à la baisse plutôt que viser un total qu'aucune
    opération restante ne peut plus atteindre. Elle gèle sous son total sur un arrêt :
    c'est `rapport.interrompu`, jamais la barre, qui dit si le lot est allé au bout.
    """
    maximum = max(progression.total, 1)
    return maximum, min(progression.accomplies, maximum)


def obstacles_au_lancement(
    parametres: Parametres, plancher: PlancherPolitique | None
) -> list[str]:
    """Ce qui empêche de lancer. Liste vide = le lot peut partir.

    Un lot mal formé ne doit pas partir seul : tout ce qui se vérifie hors ligne l'est
    ici, avant la moindre connexion. La politique n'est confrontée au plancher que s'il
    est déjà connu d'une lecture antérieure — le verdict qui fait foi est celui du
    métier, contre le plancher du boîtier réellement visé (`PolitiqueRefusee`), et il
    tombe avant la moindre écriture. Un premier lot peut donc partir directement en réel.
    """
    obstacles: list[str] = []
    if not parametres.connexion.hote.strip():
        obstacles.append("l'hôte du firewall n'est pas renseigné")
    if not parametres.connexion.compte.strip():
        obstacles.append("le compte d'administration n'est pas renseigné")
    if not parametres.connexion.mot_de_passe:
        obstacles.append("le mot de passe du compte d'administration n'est pas renseigné")
    if not str(parametres.fichier).strip() or parametres.fichier == Path():
        obstacles.append("aucun fichier CSV n'est désigné")
    if plancher is not None:
        obstacles.extend(motdepasse.violations(parametres.politique, plancher))
    return obstacles


def lignes_de_la_politique_refusee(refus: PolitiqueRefusee) -> list[str]:
    """Rendu du refus émis par le métier, avant toute écriture.

    Les violations sont recopiées telles quelles : elles viennent de
    `motdepasse.violations`, et les reformuler ici ferait diverger deux textes qui
    doivent dire la même chose.
    """
    return [
        "politique refusée avant tout envoi : aucun compte n'a été touché.",
        *refus.violations,
        libelle_plancher(refus.plancher),
        "Durcissez la politique, puis relancez le lot.",
    ]


class ComptesEnregistrables:
    """Ce que le bouton d'enregistrement écrira dans le CSV.

    Alimenté compte par compte, pour que le bouton s'active dès la première création
    et non à la fin d'un lot de deux cents comptes. Le rapport final le remplace : il
    fait foi sur ce qui a réellement été créé, mots de passe vides compris.

    Porte aussi le seul fait qui distingue un secret perdu d'un secret sauvé : ces mots
    de passe n'existent que dans la mémoire du processus. Les comptes, eux, existent sur
    le boîtier et un relancement les classera « déjà présent, ignoré » à jamais.
    """

    def __init__(self) -> None:
        self._comptes: list[CompteCree] = []
        # Nombre de comptes de tête déjà écrits dans un fichier. La liste ne fait que
        # croître entre deux `fixer`, donc ce rang suffit à dire ce qui reste en mémoire.
        self._deja_ecrits = 0

    @property
    def comptes(self) -> tuple[CompteCree, ...]:
        return tuple(self._comptes)

    @property
    def secrets_en_attente(self) -> int:
        """Combien de mots de passe seraient perdus maintenant. Zéro = rien à perdre.

        Un compte créé sans mot de passe utilisable n'a aucun secret à perdre : il est
        déjà à reprendre à la main, et le rapport le dit dans sa propre section.
        """
        return sum(1 for compte in self._comptes[self._deja_ecrits :] if compte.mot_de_passe)

    def ajouter(self, compte: CompteCree) -> None:
        self._comptes.append(compte)

    def fixer(self, comptes: Sequence[CompteCree]) -> None:
        # Le rapport peut porter un mot de passe là où l'écriture en cours de lot avait
        # vu un compte encore muet : rien de cette liste-ci n'est réputé écrit. Choix
        # conservateur assumé — après la fin d'un lot, l'avertissement recompte les
        # secrets déjà exportés en cours de route. Avertir deux fois coûte un clic ;
        # ne pas avertir coûte des mots de passe qu'aucun relancement ne recrée.
        self._comptes = list(comptes)
        self._deja_ecrits = 0

    def marquer_enregistres(self, comptes: Sequence[CompteCree]) -> None:
        """À n'appeler qu'après une écriture réussie, avec exactement ce qui a été écrit.

        Tk fait tourner sa boucle d'événements pendant qu'un sélecteur de fichier est
        ouvert : entre l'instantané confié à l'écriture et ce marquage, le fil a pu
        créer d'autres comptes, le rapport final a pu remplacer la liste et un nouveau
        lot a pu la vider. Seule une liste écrite qui est encore la tête de la liste en
        mémoire solde quoi que ce soit ; tout le reste demeure en attente.
        """
        ecrits = list(comptes)
        if self._comptes[: len(ecrits)] != ecrits:
            return
        self._deja_ecrits = len(ecrits)

    def reinitialiser(self) -> None:
        """Au démarrage effectif d'un lot : sans cela, un export mélangerait deux lots."""
        self._comptes = []
        self._deja_ecrits = 0


def _secrets_en_souffrance(nombre: int) -> str:
    """« N mots de passe n'ont pas été enregistrés », accordé au nombre."""
    sujet = _accord(nombre, "mot de passe", "mots de passe")
    verbe = "n'a pas été enregistré" if nombre <= 1 else "n'ont pas été enregistrés"
    return f"{sujet} {verbe}"


def avertissement_perte_de_secrets(nombre: int) -> str:
    """Ce que l'opérateur doit lire avant qu'un nouveau lot efface des secrets.

    Aucun relancement ne les reconstitue : les comptes existent déjà sur le boîtier, le
    plan suivant les classera « déjà présent, ignoré » et ils resteront sans mot de
    passe connu.
    """
    return (
        f"{_secrets_en_souffrance(nombre)} dans un fichier.\n\n"
        "Lancer un nouveau lot les efface définitivement. Les comptes, eux, restent "
        "créés sur le firewall : aucun relancement ne leur redonnera de mot de passe, "
        "ils seront classés « déjà présent, ignoré ».\n\n"
        "Lancer quand même ?"
    )


def _accord(nombre: int, singulier: str, pluriel: str | None = None) -> str:
    return f"{nombre} {singulier if nombre <= 1 else (pluriel or singulier + 's')}"


def lignes_du_fichier(utilisateurs: Sequence[Utilisateur], rejets: Sequence[Rejet]) -> list[str]:
    """Bilan de la lecture du CSV, écrit une fois au lancement. Hors ligne."""
    lignes = [f"{_accord(len(utilisateurs), 'ligne lue', 'lignes lues')}, "
              f"{_accord(len(rejets), 'rejet')}"]
    lignes.extend(f"ligne {rejet.ligne} : {rejet.identifiant} — {rejet.motif}" for rejet in rejets)
    return lignes


def lignes_du_plan(plan: Plan) -> list[str]:
    """Plan de rapprochement. Réécrit tel quel après une reconnexion, sur le plan reconstruit."""
    lignes: list[str] = []
    if plan.groupes_a_creer:
        details = ", ".join(
            f"{groupe.nom} ({_accord(groupe.nombre_membres, 'membre')})"
            for groupe in plan.groupes_a_creer
        )
        lignes.append(f"Groupes à créer : {details}")
    for compte in plan.comptes_a_creer:
        rattachement = f", rattaché à {', '.join(compte.groupes)}" if compte.groupes else ""
        lignes.append(f"{compte.identifiant} : à créer{rattachement}")
    lignes.extend(f"{compte.identifiant} : déjà présent, ignoré" for compte in plan.comptes_ignores)
    if plan.orphelins:
        lignes.append(f"Orphelins sur le boîtier : {', '.join(plan.orphelins)}")
    return lignes


def ligne_de_nouveau_lot(*, simulation: bool) -> str:
    """Sépare deux lancements dans un journal qui n'est jamais vidé.

    Le journal n'a aucun autre exemplaire — pas de fichier, pas de console : l'effacer
    au lancement suivant emporterait la liste des comptes à reprendre à la main du lot
    précédent. Il est donc conservé, et c'est cette ligne qui dit où le lot commence.
    """
    mode = "simulation" if simulation else "lot réel"
    return f"───────── nouveau lancement ({mode}) ─────────"


def _conduite_apres_arret(motif: MotifArret | None) -> str:
    """Ce que l'opérateur doit faire, et non le détail de ce qui s'est passé.

    Le journal porte ce détail, mais sur un lot de deux cents comptes il fait des
    centaines de lignes : y chercher la ligne décisive n'est pas une conduite à tenir.
    """
    match motif:
        case MotifArret.RESEAU:
            return "La liaison est tombée : relancer le lot suffit, rien à corriger."
        case MotifArret.FATAL:
            return (
                "Une reconnexion n'y changerait rien : corrigez ce que le journal "
                "ci-dessus indique — identifiants, configuration ou politique de mot "
                "de passe — avant de relancer."
            )
        case None:
            return "Le motif de l'arrêt est en clair dans le journal ci-dessus."


def lignes_du_rapport(rapport: Rapport) -> list[str]:
    """Bilan final.

    `interrompu` distingue le lot mené à son terme de celui qui s'est arrêté, et
    `motif_arret` dit laquelle des deux conduites à tenir s'impose.
    """
    resume = (
        f"{_accord(len(rapport.comptes_crees), 'compte créé', 'comptes créés')}, "
        f"{_accord(len(rapport.groupes_crees), 'groupe créé', 'groupes créés')}, "
        f"{_accord(len(rapport.echecs), 'échec')}."
    )
    entete = (
        f"Lot interrompu : {resume} {_conduite_apres_arret(rapport.motif_arret)} "
        "Ce qui est créé reste créé."
        if rapport.interrompu
        else f"Terminé : {resume}"
    )
    lignes = [entete]
    lignes.extend(f"{echec.identifiant} — {echec.operation} : {echec.motif}"
                  for echec in rapport.echecs)
    sans_secret = rapport.sans_mot_de_passe
    if sans_secret:
        # Section distincte des rejets, des échecs et des orphelins : ces comptes
        # existent sur le boîtier et aucun relancement ne les réparera.
        lignes.append("Comptes créés sans mot de passe — à reprendre")
        lignes.extend(compte.identifiant for compte in sans_secret)
    return lignes


FERMETURE_PENDANT_CREATION = (
    "La création de l'annuaire est en cours et ne peut pas être annulée : "
    "CONFIG LDAP INITIALIZE est déjà parti sur le boîtier. Attendez son verdict."
)


def avertissement_de_fermeture(*, lot_en_cours: bool, secrets_en_attente: int) -> str | None:
    """Ce que fermer la fenêtre ferait perdre. None = il n'y a rien à perdre.

    Le fil est un démon : il meurt avec l'interpréteur, où qu'il en soit — y compris
    entre la création d'un compte et la pose de son mot de passe.
    """
    if not lot_en_cours and not secrets_en_attente:
        return None
    parties: list[str] = []
    if lot_en_cours:
        parties.append(
            "Un lot est en cours sur le firewall. Fermer maintenant coupe le travail "
            "où qu'il en soit, y compris entre la création d'un compte et la pose de "
            "son mot de passe : ce compte resterait créé, sans mot de passe utilisable."
        )
    if secrets_en_attente:
        disparition = "disparaîtra" if secrets_en_attente <= 1 else "disparaîtront"
        parties.append(
            f"{_secrets_en_souffrance(secrets_en_attente)} dans un fichier et "
            f"{disparition} avec la fenêtre. Les comptes, eux, resteront créés sur "
            "le firewall."
        )
    parties.append("Fermer quand même ?")
    return "\n\n".join(parties)


def ligne_d_enregistrement(comptes: Sequence[CompteCree], chemin: str) -> str:
    """Bilan de l'écriture du CSV. Deux nombres, jamais un seul.

    Le CSV porte une ligne par compte créé, mot de passe vide compris : annoncer
    « N mots de passe enregistrés » ferait croire à N secrets récupérables.
    """
    avec_secret = sum(1 for compte in comptes if compte.mot_de_passe)
    sans_secret = len(comptes) - avec_secret
    ligne = (
        f"{_accord(len(comptes), 'compte écrit', 'comptes écrits')} dans {chemin}, "
        f"{_accord(avec_secret, 'mot de passe enregistré', 'mots de passe enregistrés')}"
    )
    if sans_secret:
        ligne += (
            f", {_accord(sans_secret, 'compte sans mot de passe', 'comptes sans mot de passe')}"
        )
    return ligne


def boitier_de_la_connexion(connexion: Connexion) -> Boitier:
    """Fabrique de production. Injectée dans les tests pour rester hors réseau."""
    return BoitierSDK(
        hote=connexion.hote,
        utilisateur=connexion.compte,
        mot_de_passe=connexion.mot_de_passe,
        # Jamais câblé en dur : la valeur vient d'une case que l'opérateur décoche,
        # cochée à chaque ouverture de la fenêtre.
        verifier_certificat=connexion.verifier_certificat,
    )


def travailler(
    parametres: Parametres,
    utilisateurs: Sequence[Utilisateur],
    publier: Publieur,
    fabriquer_boitier: Callable[[Connexion], Boitier] = boitier_de_la_connexion,
) -> None:
    """Corps du fil d'exécution : ne touche aucun widget, ne fait que publier.

    Toute exception est convertie en message : le fil n'a pas d'appelant, ce qu'il
    laisserait passer ne s'afficherait nulle part.
    """
    boitier = fabriquer_boitier(parametres.connexion)
    try:
        executer(
            boitier,
            utilisateurs,
            parametres.politique,
            simulation=parametres.simulation,
            emettre=publier,
        )
    except Exception as erreur:
        publier(message_de_fil(erreur))


def travailler_annuaire(
    connexion: Connexion,
    annuaire: ParametresAnnuaire,
    publier: Publieur,
    fabriquer_boitier: Callable[[Connexion], Boitier] = boitier_de_la_connexion,
) -> None:
    """Création de l'annuaire, dans son propre fil et sa propre connexion.

    `executer` a déjà déconnecté le boîtier dans son `finally` : il n'y a plus de
    session à reprendre au moment où l'opérateur valide cette fenêtre.
    """
    boitier = fabriquer_boitier(connexion)
    try:
        boitier.connecter()
        publier(Journal(f"création de l'annuaire {annuaire.domainname} en cours"))
        creer_annuaire(
            boitier,
            annuaire.domainname,
            annuaire.organisation,
            annuaire.dc,
            annuaire.mot_de_passe,
        )
    except Exception as erreur:
        publier(message_de_fil(erreur))
    else:
        publier(AnnuaireCree(annuaire.domainname))
    finally:
        # La déconnexion d'une liaison déjà perdue n'apprend rien de plus à l'opérateur.
        with contextlib.suppress(ErreurBoitier):
            boitier.deconnecter()
