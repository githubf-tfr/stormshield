"""Structures de données partagées. Aucune logique de décision, aucun accès réseau."""

from dataclasses import dataclass, field


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
    """`mot_de_passe` est vide quand USER PASSWORD a échoué malgré les réessais."""

    identifiant: str
    mot_de_passe: str


@dataclass(frozen=True)
class Echec:
    identifiant: str
    operation: str
    motif: str


@dataclass
class Rapport:
    comptes_crees: list[CompteCree] = field(default_factory=list)
    echecs: list[Echec] = field(default_factory=list)
    groupes_crees: list[str] = field(default_factory=list)
    interrompu: bool = False

    @property
    def sans_mot_de_passe(self) -> list[CompteCree]:
        """Comptes créés à reprendre à la main : un relancement ne les corrigera pas."""
        return [compte for compte in self.comptes_crees if not compte.mot_de_passe]
