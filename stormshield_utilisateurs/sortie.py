"""CSV des mots de passe. Écrit uniquement à l'emplacement désigné par l'opérateur."""

import csv
from collections.abc import Sequence
from pathlib import Path

from stormshield_utilisateurs.modele import CompteCree


def ecrire_mots_de_passe(chemin: Path, comptes: Sequence[CompteCree]) -> None:
    """UTF-8 avec BOM et séparateur ';' : Excel en français l'ouvre sans manipulation.

    Les comptes créés dont USER PASSWORD a échoué y figurent avec un champ vide.
    """
    with chemin.open("w", encoding="utf-8-sig", newline="") as fichier:
        redacteur = csv.writer(fichier, delimiter=";", lineterminator="\r\n")
        redacteur.writerow(["identifiant", "mot_de_passe"])
        for compte in comptes:
            redacteur.writerow([compte.identifiant, compte.mot_de_passe])
