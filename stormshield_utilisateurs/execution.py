"""Lecture de l'état du boîtier, puis application du plan. Émet des événements."""

from stormshield_utilisateurs.boitier import Boitier, ErreurCommande
from stormshield_utilisateurs.modele import EtatBoitier

# CONFIG LDAP LIST, CONFIG PASSWDPOLICY SHOW, USER LIST, USER GROUP LIST.
NOMBRE_LECTURES = 4


class AnnuaireAbsent(Exception):
    """Aucun annuaire interne : c'est le seul cas où CONFIG LDAP INITIALIZE est atteignable."""


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
    """Chemin conditionnel, atteignable seulement après AnnuaireAbsent. Ne se refait pas."""
    boitier.initialiser_annuaire(domainname, organisation, dc, mot_de_passe)
    boitier.activer_annuaire()
    if domainname not in boitier.lister_annuaires():
        raise ErreurCommande(200, f"l'annuaire {domainname} n'apparaît pas après activation")
