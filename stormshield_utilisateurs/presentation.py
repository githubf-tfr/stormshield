"""Tout ce que la fenêtre décide, calcule ou affiche, sans le moindre widget.

Ce module n'importe jamais `tkinter` : c'est ce qui rend la logique de l'interface
vérifiable par des tests, y compris là où `tkinter` n'est pas installé. `fenetre.py`
ne fait que câbler des widgets sur ce qui est défini ici.

Aucune chaîne de caractères ne pilote un branchement : les messages qui circulent
entre le fil d'exécution et la fenêtre sont des types, et les exceptions du métier
sont aiguillées sur leur classe.
"""

import contextlib
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
    Progression,
    Termine,
    creer_annuaire,
    executer,
)
from stormshield_utilisateurs.modele import (
    CompteCree,
    Plan,
    PlancherPolitique,
    PolitiqueMotDePasse,
    Rapport,
    Rejet,
    Utilisateur,
)

PERIODE_POMPE_MS = 100

# Politique de repli, valable le temps d'une seule simulation : tant que personne ne
# s'est connecté, le plancher du boîtier est inconnu. `obstacles_au_lancement` interdit
# d'écrire dans cet état, donc aucun mot de passe généré avec elle n'atteint un boîtier.
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


class PompeEvenements:
    """Vide la file de messages dans le fil de l'interface.

    Le fil d'exécution n'appelle jamais un widget : il dépose dans la file, et cette
    pompe — replanifiée par `after()` — est seule à en sortir les messages. La
    planification est injectée pour que la pompe se teste sans fenêtre.
    """

    def __init__(
        self,
        file: "Queue[MessageFil]",
        appliquer: Publieur,
        planifier: Callable[[int, Callable[[], None]], None],
        periode_ms: int = PERIODE_POMPE_MS,
    ) -> None:
        self._file = file
        self._appliquer = appliquer
        self._planifier = planifier
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
            self._appliquer(message)
            if est_terminal(message):
                self.active = False
        if self.active:
            self._planifier(self._periode_ms, self.tour)


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

    Un lot mal formé ne doit pas partir seul : tout est vérifié avant la moindre
    connexion, et la politique avant le moindre envoi.
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
    if plancher is None:
        if not parametres.simulation:
            # Sans plancher lu sur le boîtier, « ne jamais descendre sous le plancher »
            # n'est pas vérifiable : les mots de passe partiraient sur une politique que
            # rien n'a validée, et USER PASSWORD les refuserait un par un.
            obstacles.append(
                "le plancher de politique du boîtier n'est pas connu : lancez d'abord "
                "une simulation, puis relancez sans la simulation"
            )
        return obstacles
    obstacles.extend(motdepasse.violations(parametres.politique, plancher))
    return obstacles


class ComptesEnregistrables:
    """Ce que le bouton d'enregistrement écrira dans le CSV.

    Alimenté compte par compte, pour que le bouton s'active dès la première création
    et non à la fin d'un lot de deux cents comptes. Le rapport final le remplace : il
    fait foi sur ce qui a réellement été créé, mots de passe vides compris.
    """

    def __init__(self) -> None:
        self._comptes: list[CompteCree] = []

    @property
    def comptes(self) -> tuple[CompteCree, ...]:
        return tuple(self._comptes)

    def ajouter(self, compte: CompteCree) -> None:
        self._comptes.append(compte)

    def fixer(self, comptes: Sequence[CompteCree]) -> None:
        self._comptes = list(comptes)


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


def lignes_du_rapport(rapport: Rapport) -> list[str]:
    """Bilan final.

    `interrompu` distingue le lot mené à son terme de celui qui s'est arrêté ; le
    détail de l'arrêt — coupure réseau réessayée, ou arrêt définitif qu'aucune
    reconnexion ne résoudra — est déjà dans le journal, émis par le métier.
    """
    resume = (
        f"{_accord(len(rapport.comptes_crees), 'compte créé', 'comptes créés')}, "
        f"{_accord(len(rapport.groupes_crees), 'groupe créé', 'groupes créés')}, "
        f"{_accord(len(rapport.echecs), 'échec')}."
    )
    entete = (
        f"Lot interrompu : {resume} Le motif de l'arrêt est en clair dans le journal "
        "ci-dessus ; ce qui est créé reste créé."
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
