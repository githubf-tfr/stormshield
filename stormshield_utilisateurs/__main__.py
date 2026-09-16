"""Point d'entrée : `python -m stormshield_utilisateurs`. Cible de PyInstaller.

Rien de ce module ne dépend de `tkinter` : la fenêtre n'est importée qu'à
l'intérieur du filet. Importer au niveau module ferait échouer le démarrage avant
qu'aucun code ne puisse le dire, et un exécutable construit en mode fenêtré — sans
console, donc sans `stderr` — ne ferait alors simplement rien.
"""

import sys

from stormshield_utilisateurs.presentation import texte_de_demarrage_impossible

TITRE_ERREUR = "Injection d'utilisateurs SNS"


def alerter_hors_interface(texte: str) -> None:
    """Rend un échec visible sans `tkinter` ni console.

    Sous Windows, la boîte de message du système : c'est le seul canal qui reste à un
    exécutable fenêtré. Ailleurs, `stderr` s'il existe.
    """
    if sys.platform == "win32":
        import ctypes

        # MB_ICONERROR ; le handle de fenêtre est nul, il n'y a aucune fenêtre.
        ctypes.windll.user32.MessageBoxW(0, texte, TITRE_ERREUR, 0x10)
        return
    if sys.stderr is not None:
        print(texte, file=sys.stderr)


def principal() -> int:
    """Rend un code de sortie. Aucune exception ne remonte plus haut."""
    try:
        from stormshield_utilisateurs.fenetre import lancer

        lancer()
    except Exception as erreur:
        alerter_hors_interface(texte_de_demarrage_impossible(erreur))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
