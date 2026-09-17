"""Décision : état lu + lignes valides -> Plan. Pur, n'écrit jamais sur le boîtier."""

from collections import Counter
from collections.abc import Sequence

from stormshield_utilisateurs.modele import (
    CompteAmbigu,
    EtatBoitier,
    GroupeACreer,
    GroupeAmbigu,
    Plan,
    Rejet,
    TravailCompte,
    Utilisateur,
)
from stormshield_utilisateurs.rapprochement import (
    Absent,
    Ambigu,
    IndexBoitier,
    Reconnu,
    cle,
    uid_du_dn,
)


def groupes_cites(utilisateurs: Sequence[Utilisateur]) -> tuple[str, ...]:
    """Les groupes que le fichier nomme, une graphie par clé, triés.

    Calculée hors ligne, avant toute connexion : c'est elle qui donne le majorant de la
    phase de lecture. Seules les lignes valides à colonne non vide comptent — une ligne
    rejetée ne produit aucune adhésion, une colonne vide ne se prononce pas.
    """
    retenus: dict[str, str] = {}
    for utilisateur in utilisateurs:
        for groupe in utilisateur.groupes:
            retenus.setdefault(cle(groupe), groupe)
    return tuple(retenus[clef] for clef in sorted(retenus))


def groupes_a_interroger(cites: Sequence[str], groupes: IndexBoitier) -> tuple[str, ...]:
    """Les identités à passer à `lister_membres`, telles que `USER GROUP LIST` les a
    rendues, verbatim.

    Un groupe cité mais absent du boîtier n'est pas lu : il est à créer, il n'a pas de
    membre. Un groupe ambigu ne l'est pas non plus : il ne sera touché pour aucun
    compte, le lire n'apprendrait rien.
    """
    identites: list[str] = []
    for nom in cites:
        match groupes.resoudre(nom):
            case Reconnu(orthographe):
                identites.append(orthographe)
            case Absent() | Ambigu():
                continue
    return tuple(identites)


def _adhesions_existantes(etat: EtatBoitier) -> tuple[dict[str, frozenset[str]], int]:
    """Par clé de groupe, les clés de comptes déjà membres ; et le nombre de membres que
    l'outil n'a su relier à **aucun compte du boîtier**.

    Le point de comparaison est la liste que `USER LIST` a rendue, jamais le fichier : un
    groupe peuplé contient forcément des gens légitimes qu'un CSV du jour ne cite pas, et
    les compter noierait le signal dans le bruit qu'il doit détecter. Sur un boîtier sain
    ce nombre vaut donc zéro, quel que soit le contenu du fichier, et une forme de DN
    inattendue le fait bondir d'un coup.

    Il n'intervient jamais : ni arrêt, ni refus, ni écriture en moins.
    """
    par_groupe: dict[str, frozenset[str]] = {}
    non_rattaches = 0
    for cle_groupe, membres in etat.membres_par_groupe.items():
        deja: set[str] = set()
        for dn in membres:
            uid = uid_du_dn(dn)
            if uid is None or cle(uid) not in etat.comptes.cles:
                non_rattaches += 1
            if uid is not None:
                deja.add(cle(uid))
        par_groupe[cle_groupe] = frozenset(deja)
    return par_groupe, non_rattaches


def construire(
    utilisateurs: Sequence[Utilisateur],
    etat: EtatBoitier,
    rejets: Sequence[Rejet] = (),
) -> Plan:
    """L'outil crée des comptes, crée des groupes, ajoute des adhésions — et n'enlève
    jamais rien.

    Les rejets comptent dans « ce qui est dans le fichier » : un compte présent sur le
    boîtier dont la ligne a été rejetée y est bel et bien, et le compter orphelin dirait
    à l'opérateur le contraire de ce qu'il doit corriger. Ils ne comptent nulle part
    ailleurs — ni travail, ni adhésion, ni membre d'un groupe à créer. Un compte signalé
    ambigu est dans le même cas : pas de travail, mais pas orphelin non plus.
    """
    cibles: dict[str, str] = {}
    cles_a_creer: set[str] = set()
    ambigus: list[GroupeAmbigu] = []
    for nom in groupes_cites(utilisateurs):
        match etat.groupes.resoudre(nom):
            case Reconnu(orthographe):
                cibles[cle(nom)] = orthographe
            case Absent():
                # Aucune graphie côté boîtier : celle du fichier est la seule dont on
                # dispose, et c'est sous elle que le groupe sera créé puis adressé.
                cibles[cle(nom)] = nom
                cles_a_creer.add(cle(nom))
            case Ambigu(graphies):
                ambigus.append(GroupeAmbigu(nom, graphies))

    cles_du_fichier = frozenset(cle(u.identifiant) for u in utilisateurs)
    deja_membres, non_rattaches = _adhesions_existantes(etat)

    travaux: list[TravailCompte] = []
    comptes_ambigus: list[CompteAmbigu] = []
    for utilisateur in utilisateurs:
        match etat.comptes.resoudre(utilisateur.identifiant):
            case Reconnu(orthographe):
                cible, a_creer = orthographe, False
            case Absent():
                cible, a_creer = utilisateur.identifiant, True
            case Ambigu(graphies):
                # Deux comptes que la clé confond, et aucun égal à la graphie du
                # fichier : l'ordre de la liste rendue par le boîtier n'est garanti par
                # rien, et trancher sur la première ferait écrire sur un compte différent
                # d'une exécution à l'autre. Aucun travail : rien ne l'atteindra.
                comptes_ambigus.append(CompteAmbigu(utilisateur.identifiant, graphies))
                continue
        travaux.append(
            TravailCompte(
                utilisateur=utilisateur,
                identifiant_cible=cible,
                a_creer=a_creer,
                adhesions=_adhesions(utilisateur, cibles, deja_membres),
            )
        )

    compte_des_membres: Counter[str] = Counter()
    for travail in travaux:
        compte_des_membres.update(travail.adhesions)
    groupes_a_creer = tuple(
        GroupeACreer(nom=nom, nombre_membres=compte_des_membres[nom])
        for nom in sorted(compte_des_membres)
        if cle(nom) in cles_a_creer
    )

    dans_le_fichier = set(cles_du_fichier)
    dans_le_fichier.update(cle(rejet.identifiant) for rejet in rejets)
    nombre_orphelins = sum(
        1 for nom in etat.comptes.graphies if cle(nom) not in dans_le_fichier
    )

    return Plan(
        travaux=tuple(travaux),
        groupes_a_creer=groupes_a_creer,
        nombre_orphelins=nombre_orphelins,
        nombre_membres_non_rattaches=non_rattaches,
        groupes_ambigus=tuple(ambigus),
        comptes_ambigus=tuple(comptes_ambigus),
        domaine=etat.domaine,
    )


def _adhesions(
    utilisateur: Utilisateur,
    cibles: dict[str, str],
    deja_membres: dict[str, frozenset[str]],
) -> tuple[str, ...]:
    """Les groupes que la ligne nomme, moins ceux que le boîtier porte déjà.

    Colonne vide : la boucle ne tourne pas, aucune adhésion. Groupe ambigu : absent de
    `cibles`, donc ignoré pour ce compte comme pour tous les autres.
    """
    retenues: list[str] = []
    for groupe in utilisateur.groupes:
        cible = cibles.get(cle(groupe))
        if cible is None or cible in retenues:
            continue
        if cle(utilisateur.identifiant) in deja_membres.get(cle(groupe), frozenset()):
            continue
        retenues.append(cible)
    return tuple(retenues)
