"""Rapprochement des identités entre le fichier et le boîtier. Pur, aucun réseau.

Une seule clé de comparaison pour les comptes et pour les groupes, et une seule lecture
de DN : deux règles à retenir et à éprouver plutôt que quatre.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# Premier composant d'un DN, supposé de forme `uid=<valeur>`. C'est la seule hypothèse
# structurante de la v2 (spec, « Points non vérifiés », point 1) et tout le repli tient
# ici : le jour où la forme réelle rendue par USER GROUP SHOW sera connue, c'est cette
# expression et `uid_du_dn` qu'il faudra corriger, et rien d'autre.
_PREMIER_COMPOSANT_UID = re.compile(r"^\s*uid=([^,]+)", re.IGNORECASE)


def cle(valeur: str) -> str:
    """Clé de rapprochement, insensible à la casse. Comptes et groupes, même fonction."""
    return valeur.casefold()


def uid_du_dn(dn: str) -> str | None:
    """L'`uid` du premier composant d'un DN, ou None si le DN n'a pas cette forme.

    None n'est pas une erreur : c'est un membre que l'outil ne sait pas rattacher, donc
    à qui il n'a rien à faire. Il sera compté, jamais nommé.
    """
    trouve = _PREMIER_COMPOSANT_UID.match(dn)
    if trouve is None:
        return None
    return trouve.group(1).strip()


@dataclass(frozen=True)
class Reconnu:
    """Le boîtier porte ce nom : c'est sous cette orthographe qu'on l'adressera."""

    orthographe: str


@dataclass(frozen=True)
class Absent:
    """Aucune graphie côté boîtier. Un groupe absent sera créé sous l'orthographe du
    fichier, la seule disponible ; un compte absent sera créé sous la sienne."""


@dataclass(frozen=True)
class Ambigu:
    """Deux graphies vivantes que la clé confond, et aucune égale à celle du fichier.

    L'outil ne sait pas laquelle viser. Il le signale et poursuit : le doublon ne se
    lève qu'à la main, sur le boîtier. Les graphies sont triées à la construction :
    rien ne garantit l'ordre dans lequel le boîtier les rend, et ni l'égalité ni
    l'affichage ne doivent en dépendre.
    """

    graphies: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "graphies", tuple(sorted(self.graphies)))


Resolution = Reconnu | Absent | Ambigu


@dataclass(frozen=True)
class IndexBoitier:
    """Ce que le boîtier a rendu, rangé sous la clé de rapprochement.

    Toutes les graphies d'une même clé sont conservées : sans elles, une collision de
    casse serait tranchée au hasard de l'ordre de lecture. N'est jamais hachée.
    """

    par_cle: Mapping[str, tuple[str, ...]]
    graphies: tuple[str, ...]

    @classmethod
    def depuis(cls, noms: Iterable[str]) -> "IndexBoitier":
        """Une graphie rendue deux fois n'entre qu'une fois : c'est une seule identité.

        Que serverd puisse répéter une ligne n'est pas prouvé, mais l'aplatissement des
        sections d'une réponse le rend possible, et la conserver deux fois donnait une
        fausse ambiguïté — le compte ne recevait plus rien, sur un message annonçant
        deux graphies identiques — et un orphelin compté deux fois. Le dédoublonnage
        porte sur la graphie exacte, jamais sur la clé : deux casses distinctes restent
        deux identités du boîtier.
        """
        par_cle: dict[str, tuple[str, ...]] = {}
        rendues: list[str] = []
        for nom in noms:
            connues = par_cle.get(cle(nom), ())
            if nom in connues:
                continue
            par_cle[cle(nom)] = (*connues, nom)
            rendues.append(nom)
        return cls(par_cle=par_cle, graphies=tuple(rendues))

    @property
    def cles(self) -> frozenset[str]:
        return frozenset(self.par_cle)

    def resoudre(self, nom: str) -> Resolution:
        """Exacte d'abord, unique ensuite, ambiguë en dernier recours."""
        graphies = self.par_cle.get(cle(nom), ())
        if not graphies:
            return Absent()
        if nom in graphies:
            return Reconnu(nom)
        if len(graphies) == 1:
            return Reconnu(graphies[0])
        return Ambigu(graphies)
