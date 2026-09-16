"""Structures de données partagées. Aucune logique de décision, aucun accès réseau."""

from dataclasses import dataclass, field
from enum import Enum, auto


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
    """Ce que la phase de lecture rapporte du boîtier. Lecture seule."""

    domaine: str
    plancher: PlancherPolitique
    utilisateurs: frozenset[str]
    groupes: frozenset[str]


@dataclass(frozen=True)
class GroupeACreer:
    nom: str
    nombre_membres: int


@dataclass(frozen=True)
class Plan:
    comptes_a_creer: tuple[Utilisateur, ...]
    comptes_ignores: tuple[Utilisateur, ...]
    groupes_a_creer: tuple[GroupeACreer, ...]
    orphelins: tuple[str, ...]
    domaine: str

    def nombre_operations(self) -> int:
        """Écritures prévues : un USER GROUP CREATE par groupe, puis par compte
        un USER CREATE, un USER PASSWORD et un USER GROUP ADDUSER par groupe."""
        return len(self.groupes_a_creer) + sum(
            2 + len(compte.groupes) for compte in self.comptes_a_creer
        )


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
    """Pourquoi le lot s'est arrêté. Deux conduites à tenir, donc deux valeurs.

    Le journal porte le détail, mais sur un lot de deux cents comptes il fait des
    centaines de lignes : y chercher la ligne décisive n'est pas un aiguillage.
    """

    RESEAU = auto()  # la liaison est tombée : relancer le lot suffit
    FATAL = auto()  # l'opérateur doit corriger quelque chose avant de relancer


@dataclass
class Rapport:
    """`motif_arret` vaut None quand le lot est allé au bout ; il accompagne toujours
    `interrompu`, qui reste le fait brut « ce lot n'est pas allé au bout »."""

    comptes_crees: list[CompteCree] = field(default_factory=list)
    echecs: list[Echec] = field(default_factory=list)
    groupes_crees: list[str] = field(default_factory=list)
    interrompu: bool = False
    motif_arret: MotifArret | None = None

    @property
    def sans_mot_de_passe(self) -> list[CompteCree]:
        """Comptes créés à reprendre à la main : un relancement ne les corrigera pas."""
        return [compte for compte in self.comptes_crees if not compte.mot_de_passe]
