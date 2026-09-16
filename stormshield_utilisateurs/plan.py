"""Décision : état lu + lignes valides -> Plan. Pur, n'écrit jamais sur le boîtier."""

from collections import Counter
from collections.abc import Sequence

from stormshield_utilisateurs.modele import EtatBoitier, GroupeACreer, Plan, Rejet, Utilisateur


def construire(
    utilisateurs: Sequence[Utilisateur],
    etat: EtatBoitier,
    rejets: Sequence[Rejet] = (),
) -> Plan:
    """L'outil ajoute et rien d'autre : il ne modifie ni ne supprime jamais l'existant.

    Les rejets comptent dans « ce qui est dans le fichier » : un compte présent sur le
    boîtier dont la ligne a été rejetée y est bel et bien, et l'annoncer « orphelin »
    dirait à l'opérateur le contraire de ce qu'il doit corriger. Ils ne comptent nulle
    part ailleurs — ni à créer, ni ignorés, ni dans le décompte des membres d'un groupe.
    """
    a_creer = tuple(
        utilisateur
        for utilisateur in utilisateurs
        if utilisateur.identifiant not in etat.utilisateurs
    )
    ignores = tuple(
        utilisateur
        for utilisateur in utilisateurs
        if utilisateur.identifiant in etat.utilisateurs
    )
    dans_le_fichier = {utilisateur.identifiant for utilisateur in utilisateurs}
    dans_le_fichier.update(rejet.identifiant for rejet in rejets)
    orphelins = tuple(sorted(etat.utilisateurs - dans_le_fichier))

    # Les groupes à créer ne se comptent que sur les comptes à créer : un groupe
    # référencé seulement par un rejet ou par un compte existant n'est pas créé.
    membres: Counter[str] = Counter()
    for utilisateur in a_creer:
        membres.update(utilisateur.groupes)
    groupes_a_creer = tuple(
        GroupeACreer(nom=nom, nombre_membres=membres[nom])
        for nom in sorted(membres)
        if nom not in etat.groupes
    )

    return Plan(
        comptes_a_creer=a_creer,
        comptes_ignores=ignores,
        groupes_a_creer=groupes_a_creer,
        orphelins=orphelins,
        domaine=etat.domaine,
    )
