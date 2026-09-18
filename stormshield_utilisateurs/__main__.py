"""Point d'entrée : `python -m stormshield_utilisateurs`. Cible de PyInstaller.

Ce module n'importe rien du paquet au niveau module — ni `tkinter`, ni
`presentation`. Un import qui échoue ici tombe avant que le filet n'existe, la
trace part sur un `stderr` qu'un exécutable construit en mode fenêtré n'a pas, et
l'exécutable ne fait alors simplement rien. C'est exactement le mode d'échec le
plus probable d'une construction PyInstaller — un paquet non collecté —, et
c'était le seul que ce filet ne rattrapait pas.
"""

import sys
from collections.abc import Callable
from typing import Any, cast

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


def _ouvrir_la_boite_de_message(texte: str) -> None:
    """La vraie boîte de message Windows : le seul canal qui reste à un exécutable
    fenêtré sans console. Inatteignable pour de vrai ailleurs que sous Windows —
    `ctypes.windll` n'existe pas sur les autres plateformes.
    """
    import ctypes

    # `windll` n'existe que dans les stubs Windows de `ctypes` : ce `cast` fait taire
    # mypy, qui type-vérifie ce fichier depuis une machine qui ne l'est pas, plutôt que
    # de cacher la ligne derrière un `if sys.platform == "win32"` littéral qui la
    # rendrait inatteignable aux tests.
    # MB_ICONERROR ; le handle de fenêtre est nul, il n'y a aucune fenêtre.
    cast(Any, ctypes).windll.user32.MessageBoxW(0, texte, TITRE_ERREUR, 0x10)


def _ecrire_sur_stderr(texte: str) -> None:
    """Repli hors Windows : `stderr` s'il existe, rien sinon (exécutable fenêtré)."""
    if sys.stderr is not None:
        print(texte, file=sys.stderr)


def alerter_hors_interface(
    texte: str,
    *,
    plateforme: str = sys.platform,
    boite_de_message: Callable[[str], None] = _ouvrir_la_boite_de_message,
    afficheur_de_repli: Callable[[str], None] = _ecrire_sur_stderr,
) -> None:
    """Rend un échec visible sans `tkinter` ni console.

    Sous Windows, la boîte de message du système : c'est le seul canal qui reste à un
    exécutable fenêtré. Ailleurs, `stderr` s'il existe.

    `plateforme`, `boite_de_message` et `afficheur_de_repli` sont les coutures qui
    rendent ce choix vérifiable : la vraie boîte de message n'existe que sous Windows.
    """
    if plateforme == "win32":
        boite_de_message(texte)
        return
    afficheur_de_repli(texte)


def principal(*, lancer_l_interface: Callable[[], None] | None = None) -> int:
    """Rend un code de sortie. Aucune exception ne remonte plus haut.

    `lancer_l_interface` est la couture : la vraie interface importe `tkinter`, que
    les tests ne doivent pas charger. L'import réel n'est tenté que si rien n'est
    fourni.
    """
    try:
        lancer = lancer_l_interface
        if lancer is None:
            from stormshield_utilisateurs.fenetre import lancer as lancer_reel

            lancer = lancer_reel

        lancer()
    except Exception as erreur:
        alerter_hors_interface(texte_d_echec(erreur))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
