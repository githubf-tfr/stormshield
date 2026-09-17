"""Structures de données partagées. Aucune logique de décision, aucun accès réseau."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, auto

from stormshield_utilisateurs.rapprochement import IndexBoitier


@dataclass(frozen=True)
class Utilisateur:
    """Une ligne de CSV validée. `ligne` est un numéro d'enregistrement (en-tête = 1)."""

    ligne: int
    identifiant: str
    identifiant_origine: str
    nom: str
    prenom: str
    groupes: tuple[str, ...]

    @property
    def bascule_minuscules(self) -> bool:
        """Vrai si l'identifiant créé diffère de celui écrit dans le fichier."""
        return self.identifiant != self.identifiant_origine


@dataclass(frozen=True)
class Rejet:
    ligne: int
    identifiant: str
    motif: str


@dataclass(frozen=True)
class PlancherPolitique:
    """Politique lue sur le boîtier. L'opérateur peut durcir, jamais descendre en dessous."""

    longueur_min: int
    nombre_classes_min: int
    entropie_min: int


@dataclass(frozen=True)
class PolitiqueMotDePasse:
    """Réglage de génération choisi par l'opérateur."""

    longueur: int
    minuscules: bool = True
    majuscules: bool = True
    chiffres: bool = True
    speciaux: bool = True

    def nombre_classes(self) -> int:
        return sum([self.minuscules, self.majuscules, self.chiffres, self.speciaux])


@dataclass(frozen=True)
class EtatBoitier:
    """Ce que la phase de lecture rapporte du boîtier. Lecture seule.

    `comptes` et `groupes` portent les graphies rendues par le boîtier, rangées sous la
    clé de rapprochement : c'est sous ces graphies-là que l'outil s'adressera à lui.

    `membres_par_groupe` ne couvre que les groupes **cités par le fichier et reconnus**
    sur le boîtier, rangés sous leur clé. Un groupe absent de cette table n'a pas été
    lu : aucune adhésion n'y est réputée exister.
    """

    domaine: str
    plancher: PlancherPolitique
    comptes: IndexBoitier
    groupes: IndexBoitier
    membres_par_groupe: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class GroupeACreer:
    nom: str
    nombre_membres: int


@dataclass(frozen=True)
class GroupeAmbigu:
    """Un groupe du fichier que deux graphies vivantes du boîtier revendiquent.

    Signalé, jamais tranché : l'outil ne sait pas auquel des deux ajouter, il n'en crée
    aucun — ils existent — et ne touche ce groupe pour aucun compte. Le lot continue.
    """

    nom_fichier: str
    graphies: tuple[str, ...]


@dataclass(frozen=True)
class CompteAmbigu:
    """Un compte du fichier que deux graphies vivantes du boîtier revendiquent.

    Même règle que pour un groupe, et pour la même raison : l'ordre dans lequel le
    boîtier rend sa liste n'est garanti par rien, et trancher sur la première graphie
    ferait écrire sur un compte différent d'une exécution à l'autre. Signalé, jamais
    tranché : aucun travail n'est produit pour lui — ni création, ni adhésion, ni mot de
    passe — et le lot continue.
    """

    identifiant_fichier: str
    graphies: tuple[str, ...]


@dataclass(frozen=True)
class TravailCompte:
    """Tout ce que l'outil va faire à un compte, en un seul objet.

    Un seul objet et non deux listes parallèles : la boucle d'écriture reste unique, et
    le point d'arrêt reste où la v1 l'a posé, entre deux comptes.

    `identifiant_cible` est la graphie sous laquelle le boîtier sera adressé : celle
    qu'il a rendue pour un compte déjà présent, celle du fichier pour un compte à créer
    — la seule disponible alors.
    """

    utilisateur: Utilisateur
    identifiant_cible: str
    a_creer: bool
    adhesions: tuple[str, ...]


@dataclass(frozen=True)
class Plan:
    """Orphelins et membres non rattachés sont des **nombres** : aucun nom ne survit à
    la construction du plan, donc rien ne peut réimprimer une liste de 500 comptes
    au-dessus de ce sur quoi l'opérateur doit se prononcer."""

    travaux: tuple[TravailCompte, ...]
    groupes_a_creer: tuple[GroupeACreer, ...]
    nombre_orphelins: int
    nombre_membres_non_rattaches: int
    groupes_ambigus: tuple[GroupeAmbigu, ...]
    comptes_ambigus: tuple[CompteAmbigu, ...]
    domaine: str

    @property
    def creations(self) -> tuple[TravailCompte, ...]:
        return tuple(travail for travail in self.travaux if travail.a_creer)

    @property
    def nombre_adhesions(self) -> int:
        return sum(len(travail.adhesions) for travail in self.travaux)

    def nombre_operations(self) -> int:
        """Un USER GROUP CREATE par groupe neuf ; pour un compte à créer un USER CREATE
        et un USER PASSWORD ; un USER GROUP ADDUSER par adhésion."""
        return len(self.groupes_a_creer) + 2 * len(self.creations) + self.nombre_adhesions


@dataclass(frozen=True)
class CompteCree:
    """`mot_de_passe` est vide quand USER PASSWORD a échoué malgré les réessais.

    Le secret est hors du `repr` : il reste comparé et transporté comme avant, mais
    n'apparaît plus dans une ligne de journal, une assertion de test qui échoue ou un
    formateur de trace. Le mot de passe généré ne doit sortir que par le CSV que
    l'opérateur désigne.
    """

    identifiant: str
    mot_de_passe: str = field(repr=False)


@dataclass(frozen=True)
class Echec:
    identifiant: str
    operation: str
    motif: str


class MotifArret(Enum):
    """Pourquoi le lot s'est arrêté. Trois conduites à tenir, donc trois valeurs.

    Le journal porte le détail, mais sur un lot de deux cents comptes il fait des
    centaines de lignes : y chercher la ligne décisive n'est pas un aiguillage.
    """

    RESEAU = auto()  # la liaison est tombée : relancer le lot suffit
    FATAL = auto()  # l'opérateur doit corriger quelque chose avant de relancer
    OPERATEUR = auto()  # l'opérateur a cliqué sur Arrêter : rien à corriger, rien à attendre


@dataclass
class Rapport:
    """`motif_arret` vaut None quand le lot est allé au bout ; il accompagne toujours
    `interrompu`, qui reste le fait brut « ce lot n'est pas allé au bout »."""

    comptes_crees: list[CompteCree] = field(default_factory=list)
    echecs: list[Echec] = field(default_factory=list)
    groupes_crees: list[str] = field(default_factory=list)
    interrompu: bool = False
    motif_arret: MotifArret | None = None
    # Comptes que le plan prévoyait de créer, figé à sa construction. Un arrêt demandé
    # se juge à ce qu'il laisse derrière lui : sans ce total, le bilan pourrait dire
    # combien de comptes sont nés, jamais combien n'ont pas été touchés.
    comptes_prevus: int = 0
    # Comptes et groupes du fichier que deux graphies vivantes du boîtier revendiquent,
    # figés à la construction du plan comme `comptes_prevus`. Des nombres, jamais des
    # noms : le journal les nomme un par un, le bilan dit seulement combien de comptes
    # n'ont rien reçu du tout — sans quoi ils ne seraient comptés nulle part, ni aux
    # échecs, ni ailleurs.
    nombre_comptes_ambigus: int = 0
    nombre_groupes_ambigus: int = 0
    # Faux tant que la phase de lecture n'a pas abouti à un plan. `comptes_prevus` vaut
    # alors zéro faute d'avoir été compté, et non parce que rien n'était à créer : sans
    # cette distinction, un arrêt tombé pendant la lecture se raconterait comme un lot
    # dont le plan ne prévoyait aucune création.
    plan_construit: bool = False

    @property
    def sans_mot_de_passe(self) -> list[CompteCree]:
        """Comptes créés à reprendre à la main : un relancement ne les corrigera pas."""
        return [compte for compte in self.comptes_crees if not compte.mot_de_passe]
