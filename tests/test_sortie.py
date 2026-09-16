"""Le CSV de restitution est la seule écriture disque de l'outil."""

from pathlib import Path

from stormshield_utilisateurs.modele import CompteCree
from stormshield_utilisateurs.sortie import ecrire_mots_de_passe


def test_entete_separateur_et_bom_pour_excel_francais(tmp_path: Path) -> None:
    fichier = tmp_path / "mdp.csv"
    ecrire_mots_de_passe(fichier, [CompteCree("dupont", "MotDePasse1!")])
    octets = fichier.read_bytes()
    assert octets.startswith(b"\xef\xbb\xbf")
    assert octets.decode("utf-8-sig").splitlines() == [
        "identifiant;mot_de_passe",
        "dupont;MotDePasse1!",
    ]


def test_compte_cree_sans_mot_de_passe_figure_avec_un_champ_vide(tmp_path: Path) -> None:
    """C'est de ce fichier que l'opérateur repart : l'en omettre serait le perdre."""
    fichier = tmp_path / "mdp.csv"
    ecrire_mots_de_passe(fichier, [CompteCree("dupont", ""), CompteCree("legrand", "Abc123!x")])
    assert fichier.read_text(encoding="utf-8-sig").splitlines()[1] == "dupont;"


def test_fichier_ecrit_meme_sans_aucun_compte(tmp_path: Path) -> None:
    fichier = tmp_path / "mdp.csv"
    ecrire_mots_de_passe(fichier, [])
    assert fichier.read_text(encoding="utf-8-sig").strip() == "identifiant;mot_de_passe"


def test_aucune_ecriture_ailleurs_que_le_chemin_donne(tmp_path: Path) -> None:
    fichier = tmp_path / "sous" / "mdp.csv"
    fichier.parent.mkdir()
    ecrire_mots_de_passe(fichier, [CompteCree("dupont", "Abc123!x")])
    assert [chemin.name for chemin in tmp_path.rglob("*.csv")] == ["mdp.csv"]
