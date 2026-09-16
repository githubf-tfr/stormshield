"""CSV -> (utilisateurs valides, rejets). Module pur : aucun réseau, aucune écriture."""

import csv
import io
import re
from collections import Counter
from pathlib import Path

from stormshield_utilisateurs.modele import Rejet, Utilisateur

COLONNES_ATTENDUES: tuple[str, ...] = ("identifiant", "nom", "prenom", "groupes")
SEPARATEUR = ";"
SEPARATEUR_GROUPES = "|"
# Jeu volontairement restrictif : la liste exacte admise par le boîtier n'a pas pu
# être vérifiée (voir « Points non vérifiés » de la spec).
IDENTIFIANT_VALIDE = re.compile(r"^[a-z0-9._-]+$")


class ColonnesManquantes(Exception):  # noqa: N818 -- nom de contrat imposé par la spec
    """Erreur de structure : le fichier entier est refusé, aucune ligne n'est lue."""

    def __init__(self, colonnes: tuple[str, ...]) -> None:
        self.colonnes = colonnes
        super().__init__("colonne(s) absente(s) du fichier : " + ", ".join(colonnes))


def decoder(octets: bytes) -> str:
    """BOM UTF-8 d'abord, puis tentative UTF-8, puis repli cp1252 (Excel français)."""
    if octets.startswith(b"\xef\xbb\xbf"):
        return octets.decode("utf-8-sig")
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError:
        return octets.decode("cp1252")


def lire(chemin: Path) -> tuple[list[Utilisateur], list[Rejet]]:
    return lire_texte(decoder(chemin.read_bytes()))


def _decouper_groupes(brut: str) -> tuple[str, ...]:
    """Segments vides ignorés, doublons internes supprimés, ordre conservé."""
    groupes: list[str] = []
    for segment in brut.split(SEPARATEUR_GROUPES):
        nom = segment.strip()
        if nom and nom not in groupes:
            groupes.append(nom)
    return tuple(groupes)


def _motifs(identifiant: str, nom: str, prenom: str) -> list[str]:
    motifs: list[str] = []
    if not identifiant:
        motifs.append("identifiant vide")
    elif not IDENTIFIANT_VALIDE.match(identifiant):
        motifs.append("identifiant : caractère interdit (autorisés : a-z 0-9 . _ -)")
    if not nom:
        motifs.append("nom vide")
    if not prenom:
        motifs.append("prenom vide")
    return motifs


def lire_texte(contenu: str) -> tuple[list[Utilisateur], list[Rejet]]:
    lecteur = csv.DictReader(io.StringIO(contenu, newline=""), delimiter=SEPARATEUR)
    presentes = {(colonne or "").strip() for colonne in (lecteur.fieldnames or [])}
    manquantes = tuple(colonne for colonne in COLONNES_ATTENDUES if colonne not in presentes)
    if manquantes:
        raise ColonnesManquantes(manquantes)

    # Numéro d'enregistrement : l'en-tête est la ligne 1, le premier enregistrement la 2.
    candidats: list[tuple[int, Utilisateur, list[str]]] = []
    for numero, enregistrement in enumerate(lecteur, start=2):
        champs = {
            colonne: (enregistrement.get(colonne) or "").strip() for colonne in COLONNES_ATTENDUES
        }
        identifiant = champs["identifiant"].lower()
        utilisateur = Utilisateur(
            ligne=numero,
            identifiant=identifiant,
            identifiant_origine=champs["identifiant"],
            nom=champs["nom"],
            prenom=champs["prenom"],
            groupes=_decouper_groupes(champs["groupes"]),
        )
        candidats.append(
            (numero, utilisateur, _motifs(identifiant, champs["nom"], champs["prenom"]))
        )

    # Les doublons se comptent sur les identifiants par ailleurs valides, après bascule ;
    # les deux lignes d'un doublon sont rejetées, jamais une seule.
    occurrences = Counter(
        utilisateur.identifiant for _, utilisateur, motifs in candidats if not motifs
    )

    utilisateurs: list[Utilisateur] = []
    rejets: list[Rejet] = []
    for numero, utilisateur, motifs in candidats:
        if occurrences[utilisateur.identifiant] > 1:
            motifs = [*motifs, "identifiant en doublon dans le fichier"]
        if motifs:
            rejets.append(
                Rejet(ligne=numero, identifiant=utilisateur.identifiant, motif=" ; ".join(motifs))
            )
        else:
            utilisateurs.append(utilisateur)
    return utilisateurs, rejets
