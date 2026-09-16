"""Point d'entrée : `python -m stormshield_utilisateurs`. Cible de PyInstaller.

Ce module n'importe rien du paquet au niveau module — ni `tkinter`, ni
`presentation`. Un import qui échoue ici tombe avant que le filet n'existe, la
trace part sur un `stderr` qu'un exécutable construit en mode fenêtré n'a pas, et
l'exécutable ne fait alors simplement rien. C'est exactement le mode d'échec le
plus probable d'une construction PyInstaller — un paquet non collecté —, et
c'était le seul que ce filet ne rattrapait pas.
"""

import sys

TITRE_ERREUR = "Injection d'utilisateurs SNS"

# Repli local, sans aucune dépendance : si `presentation` ne s'importe pas, c'est ce
# texte qui s'affiche. Moins soigné que celui de `presentation`, mais il tient tant que
# ce fichier-ci tourne, et un exécutable muet est la seule issue vraiment inacceptable.
TEXTE_DE_REPLI = (
    "L'interface n'a pas pu démarrer.\n\n{type} : {erreur}\n\n"
    "Causes les plus fréquentes : le paquet tkinter n'est pas installé avec ce "
    "Python, aucun affichage n'est utilisable depuis cette session, ou l'exécutable "
    "est incomplet."
)


def texte_d_echec(erreur: BaseException) -> str:
    """Le texte de `presentation` si ce module s'importe, le repli local sinon.

    L'import est tenté ici et non au niveau module : c'est sa panne même que ce filet
    doit rattraper. Le `except Exception` couvre aussi l'appel — rien de ce chemin ne
    doit pouvoir lever, il n'y a plus personne au-dessus pour le dire.
    """
    try:
        from stormshield_utilisateurs.presentation import texte_de_demarrage_impossible

        return texte_de_demarrage_impossible(erreur)
    except Exception:
        return TEXTE_DE_REPLI.format(type=type(erreur).__name__, erreur=erreur)


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
        alerter_hors_interface(texte_d_echec(erreur))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
