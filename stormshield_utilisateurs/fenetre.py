"""Fenêtre unique tkinter. Ne décide rien : elle câble `presentation` sur des widgets.

Seul module du paquet à importer `tkinter`. `tests/test_fenetre.py` l'importe et
construit la fenêtre pour de vrai : il lui faut `tkinter` (paquet `python3-tk` sous
Debian) et un affichage — `xvfb-run -a pytest` en fournit un, et sans affichage ces
tests se sautent au lieu de rougir. Ce qui reste hors de leur portée : les boîtes
modales réelles, qui attendent un clic humain, et `lancer()`, qui entre dans
`mainloop` et n'en sort qu'à la fermeture. Ce qui relève encore du cahier de recette :
l'apparence, et tout ce qu'un humain seul peut juger.

Les boîtes modales sont pour cela injectables — `Dialogues`, défaut au vrai
comportement —, comme la fabrique de boîtier qui part dans le fil. Ces deux coutures
ne changent rien à ce que voit l'opérateur : elles rendent le reste de ce fichier
vérifiable sans qu'un humain clique.

Quatre règles tiennent ce fichier :

- le fil d'exécution ne touche jamais un widget. Il reçoit un objet figé, publie dans
  une `queue`, et `PompeEvenements` — replanifiée par `after()` — est seule à ramener
  ces messages dans le fil de l'interface. Aucun nom emprunté à `self` n'apparaît dans
  la construction du fil, cible comme arguments — seules la demande d'arrêt et la
  fabrique de boîtier la franchissent, recopiées dans des variables locales, et ni
  l'une ni l'autre ne porte le moindre widget —, et aucun fil ne naît autrement que
  d'un `threading.Thread` : un test de structure le vérifie sur ce source. Ce garde-fou
  attrape les contournements distraits, pas un contournement décidé — sa docstring dit
  ce qu'il ne voit pas ;
- aucun aiguillage sur une chaîne. `_appliquer` filtre sur le type du message, et les
  exceptions du métier ont été traduites en types par `message_de_fil` ;
- rien ne disparaît en silence. Ce que la pompe ou Tk attrape part au journal, et une
  fois par lot dans une boîte de dialogue : il n'y a ni fichier de journal, ni `stderr`
  dans un exécutable fenêtré. Aucune de ces boîtes ne s'ouvre depuis l'intérieur d'un
  tour de pompe — une modale Tk fait tourner une boucle imbriquée, qui rappellerait ce
  tour dans lui-même ;
- rien ne détruit un secret sans que l'opérateur l'ait dit. Les mots de passe générés
  n'existent que dans ce processus : un nouveau lot comme une fermeture de fenêtre
  demandent confirmation tant qu'ils n'ont pas été écrits.
"""

import queue
import sys
import threading
import tkinter as tk
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from types import TracebackType

from stormshield_utilisateurs import lecture, sortie
from stormshield_utilisateurs.boitier import Boitier
from stormshield_utilisateurs.execution import (
    CreationReussie,
    Journal,
    PlanPret,
    PolitiqueLue,
    PolitiqueRefusee,
    Progression,
    Termine,
)
from stormshield_utilisateurs.modele import (
    PlancherPolitique,
    PolitiqueMotDePasse,
    Rejet,
    Utilisateur,
)
from stormshield_utilisateurs.presentation import (
    ARRET_DEMANDE_AU_CLIC,
    FERMETURE_PENDANT_CREATION,
    POLITIQUE_INITIALE,
    AnnuaireCree,
    AnnuaireManquant,
    BoiteParLot,
    ComptesEnregistrables,
    Connexion,
    DemandeArret,
    DemandeConfirmation,
    Echoue,
    IncidentInterface,
    MessageFil,
    Parametres,
    ParametresAnnuaire,
    PompeEvenements,
    Publieur,
    avertissement_de_fermeture,
    avertissement_perte_de_secrets,
    boitier_de_la_connexion,
    etat_des_boutons,
    libelle_plancher,
    ligne_d_enregistrement,
    ligne_de_message_inconnu,
    ligne_de_nouveau_lot,
    lignes_de_l_incident,
    lignes_de_la_politique_refusee,
    lignes_du_fichier,
    lignes_du_plan,
    lignes_du_rapport,
    obstacles_au_lancement,
    politique_a_afficher,
    reglage_barre,
    resume_de_l_incident,
    travailler,
    travailler_annuaire,
)

TITRE = "Injection d'utilisateurs SNS"

# Le contournement de la vérification du certificat n'est jamais câblé en dur et jamais
# décoché par défaut : son libellé dit ce qu'il coûte, à l'endroit où on le décoche.
LIBELLE_CERTIFICAT = (
    "Vérifier le certificat du firewall (décoché : identifiants et mots de passe "
    "générés transitent dans une session interceptable)"
)

# Une boîte à trois arguments : son titre, son texte, et la fenêtre sous laquelle elle
# s'ouvre — le dialogue de création d'annuaire n'est pas la fenêtre principale, et une
# boîte posée sur la mauvaise passe derrière.
AfficherBoite = Callable[[str, str, tk.Misc], None]
# Vrai = l'opérateur a dit oui. Le défaut ci-dessous impose l'icône d'avertissement et
# le bouton *Non* par défaut : les trois questions du produit sont graves, et aucune ne
# doit se répondre « oui » par une frappe distraite.
PoserQuestionGrave = Callable[[str, str, tk.Misc], bool]
# Chaîne vide = l'opérateur a renoncé. Titre et filtres vivent dans le défaut : ils ne
# varient pas d'un appel à l'autre.
ChoisirFichier = Callable[[tk.Misc], str]


def _erreur_reelle(titre: str, message: str, parent: tk.Misc) -> None:
    messagebox.showerror(titre, message, parent=parent)


def _information_reelle(titre: str, message: str, parent: tk.Misc) -> None:
    messagebox.showinfo(titre, message, parent=parent)


def _avertissement_reel(titre: str, message: str, parent: tk.Misc) -> None:
    messagebox.showwarning(titre, message, parent=parent)


def _question_grave_reelle(titre: str, message: str, parent: tk.Misc) -> bool:
    return messagebox.askyesno(
        titre,
        message,
        icon=messagebox.WARNING,
        default=messagebox.NO,
        parent=parent,
    )


def _fichier_a_lire_reel(parent: tk.Misc) -> str:
    return filedialog.askopenfilename(
        parent=parent,
        title="Fichier des utilisateurs",
        filetypes=[("CSV", "*.csv"), ("Tous les fichiers", "*.*")],
    )


def _fichier_a_ecrire_reel(parent: tk.Misc) -> str:
    return filedialog.asksaveasfilename(
        parent=parent,
        title="Enregistrer les mots de passe",
        defaultextension=".csv",
        filetypes=[("CSV", "*.csv")],
    )


@dataclass(frozen=True)
class Dialogues:
    """Les boîtes modales de la fenêtre, injectables. Défaut : le vrai comportement.

    Une modale Tk fait tourner une boucle d'événements imbriquée et n'en sort qu'au
    clic d'un humain : rien d'automatique ne la traverse. Les six défauts ci-dessus
    sont donc les seules lignes de ce fichier qu'aucun test ne peut exécuter, et
    substituer ce groupe rend vérifiable tout ce qui les entoure — laquelle s'ouvre,
    avec quel texte, et ce que la fenêtre fait de la réponse.
    """

    erreur: AfficherBoite = _erreur_reelle
    information: AfficherBoite = _information_reelle
    avertissement: AfficherBoite = _avertissement_reel
    question_grave: PoserQuestionGrave = _question_grave_reelle
    fichier_a_lire: ChoisirFichier = _fichier_a_lire_reel
    fichier_a_ecrire: ChoisirFichier = _fichier_a_ecrire_reel


# Les boîtes de production : ce que voit l'opérateur, et le défaut de la fenêtre.
DIALOGUES_REELS = Dialogues()


class _Racine(tk.Tk):
    """`tk.Tk` dont le gestionnaire global d'exceptions passe par la fenêtre.

    Tk appelle `report_callback_exception` pour tout ce qui remonte d'un callback de
    widget — hors de la pompe, donc hors de son filet. Sa version d'origine écrit sur
    `stderr`, absent d'un exécutable construit en mode fenêtré : l'opérateur ne verrait
    rien. Surcharge plutôt qu'affectation d'attribut : une méthode ne se remplace pas
    en place sans mentir sur son type.
    """

    def __init__(self, signaler: Callable[[BaseException], None]) -> None:
        super().__init__()
        self._signaler = signaler

    def report_callback_exception(
        self,
        exc: type[BaseException],
        val: BaseException,
        tb: TracebackType | None,
    ) -> None:
        # Signature imposée par Tk : le type et la trace sont déjà portés par `val`.
        # `del` plutôt qu'une suppression d'avertissement en commentaire : ce dépôt
        # n'en accepte aucune, et celle-ci n'aurait pas été d'une autre famille.
        del exc, tb
        self._signaler(val)


class Fenetre:
    """Fenêtre principale. Tous ses widgets vivent dans le fil de l'interface."""

    def __init__(
        self,
        dialogues: Dialogues = DIALOGUES_REELS,
        fabriquer_boitier: Callable[[Connexion], Boitier] = boitier_de_la_connexion,
    ) -> None:
        # Les deux seules coutures de ce fichier, toutes deux au défaut de production :
        # les boîtes modales, qu'aucun test ne peut traverser, et la fabrique de
        # boîtier, qui ouvrirait une vraie session SSL sur un vrai firewall.
        self.dialogues = dialogues
        self.fabriquer_boitier = fabriquer_boitier
        self.racine = _Racine(self._signaler_exception_tk)
        self.racine.title(TITRE)
        # Vrai entre le démarrage d'un fil de lot et son message terminal : c'est ce
        # que l'opérateur perdrait en fermant la fenêtre.
        self.lot_en_cours = False
        # Ordre d'arrêt du lot en cours. Remplacé à chaque démarrage : une demande ne
        # se retire pas, et celle d'un lot fini n'a pas à arrêter le suivant. Celle-ci
        # ne sert jamais — *Arrêter* est grisé tant qu'aucun lot n'a démarré.
        self.arret = DemandeArret()
        # Vrai entre le démarrage du fil de création d'annuaire et son message terminal.
        # Attribut de la fenêtre et non fermeture du dialogue : le garde de fermeture de
        # la fenêtre principale doit le connaître, `CONFIG LDAP INITIALIZE` étant
        # l'opération la plus destructrice du produit.
        self.creation_annuaire_en_cours = False
        # None tant qu'aucune connexion n'a renseigné le plancher du boîtier : c'est
        # ce qui grise les champs de politique et interdit d'écrire.
        self.politique: PolitiqueMotDePasse | None = None
        self.plancher: PlancherPolitique | None = None
        self.enregistrables = ComptesEnregistrables()
        # Une boîte d'anomalie par lot ; les suivantes ne vont qu'au journal.
        self.boite_incident = BoiteParLot()
        self._construire_widgets()

    # --- construction ----------------------------------------------------

    def _construire_widgets(self) -> None:
        cadre = ttk.Frame(self.racine, padding=8)
        cadre.grid(row=0, column=0, sticky="nsew")
        self.racine.columnconfigure(0, weight=1)
        self.racine.rowconfigure(0, weight=1)
        cadre.columnconfigure(1, weight=1)

        self.var_hote = tk.StringVar()
        self.var_compte = tk.StringVar()
        self.var_mot_de_passe = tk.StringVar()
        self.var_fichier = tk.StringVar()
        ttk.Label(cadre, text="Hôte du firewall").grid(row=0, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(cadre, textvariable=self.var_hote).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=6, pady=3
        )
        ttk.Label(cadre, text="Compte d'administration").grid(
            row=1, column=0, sticky="w", padx=6, pady=3
        )
        ttk.Entry(cadre, textvariable=self.var_compte).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=6, pady=3
        )
        ttk.Label(cadre, text="Mot de passe").grid(row=2, column=0, sticky="w", padx=6, pady=3)
        # Aucun identifiant n'est mémorisé d'un lancement à l'autre : ces champs
        # naissent vides à chaque ouverture et ne sont écrits nulle part.
        ttk.Entry(cadre, textvariable=self.var_mot_de_passe, show="•").grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=6, pady=3
        )
        ttk.Label(cadre, text="Fichier CSV").grid(row=3, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(cadre, textvariable=self.var_fichier).grid(
            row=3, column=1, sticky="ew", padx=6, pady=3
        )
        ttk.Button(cadre, text="Parcourir…", command=self._parcourir).grid(
            row=3, column=2, sticky="ew", padx=6, pady=3
        )

        ttk.Separator(cadre, orient=tk.HORIZONTAL).grid(
            row=4, column=0, columnspan=3, sticky="ew", pady=8
        )

        # Politique de mot de passe : grisée tant que le plancher du boîtier est
        # inconnu. L'opérateur peut ensuite durcir, jamais descendre sous le plancher.
        self.var_longueur = tk.IntVar(value=POLITIQUE_INITIALE.longueur)
        self.var_minuscules = tk.BooleanVar(value=POLITIQUE_INITIALE.minuscules)
        self.var_majuscules = tk.BooleanVar(value=POLITIQUE_INITIALE.majuscules)
        self.var_chiffres = tk.BooleanVar(value=POLITIQUE_INITIALE.chiffres)
        self.var_speciaux = tk.BooleanVar(value=POLITIQUE_INITIALE.speciaux)
        ttk.Label(cadre, text="Longueur des mots de passe").grid(
            row=5, column=0, sticky="w", padx=6, pady=3
        )
        longueur = ttk.Spinbox(
            cadre, from_=1, to=128, textvariable=self.var_longueur, width=6
        )
        longueur.grid(row=5, column=1, sticky="w", padx=6, pady=3)
        classes = ttk.Frame(cadre)
        classes.grid(row=6, column=0, columnspan=3, sticky="w", padx=6, pady=3)
        cases = [
            ttk.Checkbutton(classes, text=libelle, variable=variable)
            for libelle, variable in (
                ("minuscules", self.var_minuscules),
                ("majuscules", self.var_majuscules),
                ("chiffres", self.var_chiffres),
                ("spéciaux", self.var_speciaux),
            )
        ]
        for colonne, case in enumerate(cases):
            case.grid(row=0, column=colonne, padx=6)
        self.champs_politique: list[ttk.Widget] = [longueur, *cases]
        for champ in self.champs_politique:
            # `widget["state"]` plutôt que `configure(state=...)` : l'option existe sur
            # chaque widget ttk, mais pas sur la signature commune de leur classe mère.
            champ["state"] = tk.DISABLED
        self.etiquette_plancher = ttk.Label(
            cadre, text="politique du boîtier : inconnue tant qu'aucune lecture n'a eu lieu"
        )
        self.etiquette_plancher.grid(row=7, column=0, columnspan=3, sticky="w", padx=6, pady=3)

        self.var_simulation = tk.BooleanVar(value=True)
        self.var_certificat = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            cadre,
            text="Simulation (lit le boîtier et affiche le plan, n'y écrit rien)",
            variable=self.var_simulation,
        ).grid(row=8, column=0, columnspan=3, sticky="w", padx=6, pady=3)
        # tk.Checkbutton plutôt que ttk : seul le premier sait replier un libellé long,
        # et ce libellé-là ne doit pas être raccourci.
        tk.Checkbutton(
            cadre,
            text=LIBELLE_CERTIFICAT,
            variable=self.var_certificat,
            wraplength=560,
            justify=tk.LEFT,
            anchor="w",
        ).grid(row=9, column=0, columnspan=3, sticky="w", padx=6, pady=3)

        # Sous-cadre, comme pour les cases de politique : posés dans les colonnes du
        # cadre principal, les deux boutons seraient séparés par la largeur de la colonne
        # des libellés — celle qui porte « Longueur des mots de passe ». Ici ils sont
        # réellement adjacents, et rien d'autre n'occupe cette ligne.
        boutons = ttk.Frame(cadre)
        boutons.grid(row=10, column=0, columnspan=3, sticky="w", padx=6, pady=3)
        self.bouton_lancer = ttk.Button(boutons, text="Lancer", command=self._au_lancement)
        self.bouton_lancer.grid(row=0, column=0, padx=(0, 6))
        # À côté de *Lancer*, jamais à sa place : l'opérateur doit voir d'un coup d'œil
        # dans quel état est l'outil, et lequel des deux gestes lui est offert.
        self.bouton_arreter = ttk.Button(boutons, text="Arrêter", command=self._a_l_arret)
        self.bouton_arreter.grid(row=0, column=1)
        self._appliquer_etat_des_boutons()

        journal = ttk.Frame(cadre)
        journal.grid(row=11, column=0, columnspan=3, sticky="nsew", padx=6, pady=3)
        cadre.rowconfigure(11, weight=1)
        journal.columnconfigure(0, weight=1)
        journal.rowconfigure(0, weight=1)
        # Aucun fichier de journal : il vit dans la fenêtre. Le Text reste désactivé
        # entre deux écritures, ce qui n'empêche ni la sélection ni Ctrl-C.
        self.journal = tk.Text(journal, height=18, width=90, wrap=tk.WORD, state=tk.DISABLED)
        self.journal.grid(row=0, column=0, sticky="nsew")
        ascenseur = ttk.Scrollbar(journal, orient=tk.VERTICAL, command=self.journal.yview)
        ascenseur.grid(row=0, column=1, sticky="ns")
        self.journal.configure(yscrollcommand=ascenseur.set)

        self.barre = ttk.Progressbar(cadre, orient=tk.HORIZONTAL, mode="determinate",
                                     maximum=1, value=0)
        self.barre.grid(row=12, column=0, columnspan=2, sticky="ew", padx=6, pady=3)
        self.etiquette_progression = ttk.Label(cadre, text="0 / 0")
        self.etiquette_progression.grid(row=12, column=2, sticky="w", padx=6, pady=3)

        # Aucune écriture automatique : ni à côté de l'exécutable, ni dans le dossier
        # du fichier d'entrée. L'opérateur désigne l'emplacement, ou rien n'est écrit.
        self.bouton_enregistrer = ttk.Button(
            cadre,
            text="Enregistrer les mots de passe…",
            command=self._enregistrer_mots_de_passe,
            state=tk.DISABLED,
        )
        self.bouton_enregistrer.grid(row=13, column=0, columnspan=2, sticky="w", padx=6, pady=3)

    # --- journal ---------------------------------------------------------

    def _ecrire(self, texte: str) -> None:
        self.journal.configure(state=tk.NORMAL)
        self.journal.insert(tk.END, texte + "\n")
        self.journal.see(tk.END)
        self.journal.configure(state=tk.DISABLED)

    def _ecrire_lignes(self, lignes: list[str]) -> None:
        for ligne in lignes:
            self._ecrire(ligne)

    # --- saisie ----------------------------------------------------------

    def _parcourir(self) -> None:
        chemin = self.dialogues.fichier_a_lire(self.racine)
        if chemin:
            self.var_fichier.set(chemin)

    def _connexion_des_champs(self) -> Connexion:
        return Connexion(
            hote=self.var_hote.get(),
            compte=self.var_compte.get(),
            mot_de_passe=self.var_mot_de_passe.get(),
            verifier_certificat=self.var_certificat.get(),
        )

    def _politique_des_champs(self) -> PolitiqueMotDePasse:
        """Lève `tk.TclError` si la longueur saisie n'est pas un entier."""
        return PolitiqueMotDePasse(
            longueur=self.var_longueur.get(),
            minuscules=self.var_minuscules.get(),
            majuscules=self.var_majuscules.get(),
            chiffres=self.var_chiffres.get(),
            speciaux=self.var_speciaux.get(),
        )

    # --- lancement -------------------------------------------------------

    def _au_lancement(self) -> None:
        """Le CSV est lu ici, hors ligne, avant la moindre connexion."""
        chemin = Path(self.var_fichier.get().strip())
        try:
            # Champs grisés tant qu'aucune lecture n'a eu lieu : c'est la politique de
            # repli qui part, et le métier la refusera contre le plancher qu'il lira.
            politique = (
                POLITIQUE_INITIALE if self.plancher is None else self._politique_des_champs()
            )
        except tk.TclError:
            self.dialogues.erreur(
                "Longueur invalide",
                "La longueur des mots de passe doit être un nombre entier.",
                self.racine,
            )
            return
        parametres = Parametres(
            connexion=self._connexion_des_champs(),
            fichier=chemin,
            simulation=self.var_simulation.get(),
            politique=politique,
        )
        obstacles = obstacles_au_lancement(parametres, self.plancher)
        if obstacles:
            self.dialogues.erreur("Lancement refusé", "\n".join(obstacles), self.racine)
            return
        try:
            utilisateurs, rejets = lecture.lire(chemin)
        except lecture.ColonnesManquantes as erreur:
            self.dialogues.erreur("Fichier invalide", str(erreur), self.racine)
            return
        except OSError as erreur:
            self.dialogues.erreur("Fichier illisible", str(erreur), self.racine)
            return
        if not self._confirmer_la_perte_des_secrets():
            return
        # Le choix de l'opérateur devient la politique courante : la lecture du boîtier
        # qui suivra ne réécrira pas ce qu'il a durci.
        if self.plancher is not None:
            self.politique = politique
        # Le journal n'est jamais vidé : il n'a aucun autre exemplaire, et l'effacer
        # emporterait la liste des comptes à reprendre du lot précédent. Cette ligne
        # dit où le nouveau lot commence.
        self._ecrire(ligne_de_nouveau_lot(simulation=parametres.simulation))
        self._ecrire_lignes(lignes_du_fichier(utilisateurs, rejets))
        self._demarrer(parametres, utilisateurs, rejets)

    def _confirmer_la_perte_des_secrets(self) -> bool:
        """Dernier rempart avant qu'un nouveau lot efface les mots de passe du précédent.

        Les comptes existent déjà sur le boîtier : un relancement les verra comme déjà
        présents, ne leur redonnera plus que leurs adhésions manquantes, et jamais de
        mot de passe.
        """
        en_attente = self.enregistrables.secrets_en_attente
        if not en_attente:
            return True
        return self.dialogues.question_grave(
            "Mots de passe non enregistrés",
            avertissement_perte_de_secrets(en_attente),
            self.racine,
        )

    def _demarrer(
        self,
        parametres: Parametres,
        utilisateurs: list[Utilisateur],
        rejets: list[Rejet],
    ) -> None:
        # Le lot précédent est soldé : sa liste ne doit pas se mélanger à celle-ci, et
        # le bouton ne doit pas rester actif sur un contenu qui vient d'être vidé.
        self.enregistrables.reinitialiser()
        self.bouton_enregistrer.configure(state=tk.DISABLED)
        # Le lot qui commence a droit à sa boîte : le silence ne valait que pour le
        # précédent.
        self.boite_incident.reinitialiser()
        # L'état des boutons ne se règle qu'ici : tout ce qui précède le démarrage
        # effectif du fil peut encore rendre la main sans qu'aucun lot ne parte.
        # Variables locales : rien de `self` ne doit voyager jusqu'au fil. `arret` est
        # un `threading.Event` enveloppé, sans le moindre widget : c'est le seul objet
        # que les deux fils partagent, et il ne circule que dans ce sens.
        file: queue.Queue[MessageFil] = queue.Queue()
        arret = DemandeArret()
        self.arret = arret
        # Même règle que pour `arret` : la fabrique est recopiée dans une variable locale
        # avant de partir. C'est une fonction du métier, sans le moindre widget, et rien
        # qui ressemble à `self` ne doit apparaître dans la construction du fil.
        fabriquer = self.fabriquer_boitier
        fil = threading.Thread(
            target=travailler,
            # `rejets` voyage jusqu'au fil : le plan en a besoin pour ne pas annoncer
            # orphelin un compte dont la ligne a seulement été rejetée.
            args=(parametres, utilisateurs, file.put, rejets, arret, fabriquer),
            daemon=True,
        )
        self.lot_en_cours = True
        self._appliquer_etat_des_boutons()
        fil.start()
        self._pomper(file, self._appliquer)

    def _a_l_arret(self) -> None:
        """Clic sur *Arrêter*, dans le fil de l'interface. Ne bloque rien, n'attend rien.

        Aucune confirmation : qui clique est déjà pressé, et relancer ne coûte rien
        puisque l'outil est idempotent. Le bouton reste actif jusqu'au bilan — un second
        clic pose une demande déjà posée, ce qui ne change rien. Le fil d'exécution
        répond quand l'opération en cours est allée à son terme — une lecture de
        l'inventaire ou un compte entamé —, et c'est le journal du métier qui le dit.

        La ligne de journal part d'ici et non du fil : elle accuse réception du geste,
        pendant que le fil achève ce qu'il avait commencé. Elle ne sait pas dans quelle
        phase le clic tombe, et ne promet donc aucun compte en cours. Un second clic la
        réécrit, ce qui est encore une réponse.
        """
        self._ecrire(ARRET_DEMANDE_AU_CLIC)
        self.arret.demander()

    def _appliquer_etat_des_boutons(self) -> None:
        """*Lancer* et *Arrêter* ne sont jamais actifs ensemble. La règle vit dans
        `presentation`, qui se teste ; ici il ne reste que la traduction en état Tk."""
        etat = etat_des_boutons(lot_en_cours=self.lot_en_cours)
        self.bouton_lancer.configure(state=tk.NORMAL if etat.lancer else tk.DISABLED)
        self.bouton_arreter.configure(state=tk.NORMAL if etat.arreter else tk.DISABLED)

    def _pomper(self, file: "queue.Queue[MessageFil]", appliquer: Publieur) -> None:
        PompeEvenements(file, appliquer, self._planifier, self._signaler_incident).tour()

    def _planifier(self, delai_ms: int, rappel: Callable[[], None]) -> None:
        # `after` conserve la référence du rappel : la pompe survit à la fin de ce tour.
        self.racine.after(delai_ms, rappel)

    def _reactiver_lancement(self) -> None:
        """Sur le message terminal du lot, et seulement là : *Lancer* redevient actif,
        *Arrêter* n'a plus rien à arrêter."""
        self.lot_en_cours = False
        self._appliquer_etat_des_boutons()

    # --- anomalies internes ----------------------------------------------

    def _signaler_incident(self, incident: IncidentInterface) -> None:
        """Rend visible ce qui, sans cela, ne s'afficherait nulle part.

        Tk écrit sa trace sur `stderr`, qui n'existe pas dans un exécutable construit
        en mode fenêtré, et le produit n'a par conception aucun fichier de journal.

        Ne rend jamais le bouton *Lancer* : l'anomalie n'arrête pas le fil, qui écrit
        toujours sur le firewall. Un second lot partirait sur le même boîtier et son
        démarrage viderait la liste des mots de passe pendant que la pompe du premier y
        déverse encore les siens. Seul le message terminal du lot réactive le bouton ;
        s'il n'arrive jamais, la fenêtre reste bloquée sur ce lot-là, et c'est la
        conduite voulue.

        Une seule boîte par lot, et jamais depuis l'intérieur du tour de pompe : elle
        est planifiée pour le tour de boucle suivant. Une boîte modale fait tourner une
        boucle d'événements imbriquée — ouverte ici, elle laisserait la pompe se
        rappeler elle-même, et une panne d'affichage persistante empilerait une boîte
        par message. Le journal, lui, reçoit tout.
        """
        self._ecrire_lignes(lignes_de_l_incident(incident))
        if self.boite_incident.doit_ouvrir():
            resume = resume_de_l_incident(incident)
            self._planifier(0, lambda: self._boite_d_anomalie(resume))

    def _boite_d_anomalie(self, resume: str) -> None:
        self.dialogues.erreur("Anomalie interne", resume, self.racine)

    def _signaler_exception_tk(self, erreur: BaseException) -> None:
        """Ce que Tk attrape hors de la pompe. Dernier recours : `stderr` s'il en reste."""
        try:
            self._signaler_incident(IncidentInterface(erreur))
        except Exception:  # plus rien au-dessus : ne jamais reboucler sur Tk
            if sys.stderr is not None:
                traceback.print_exception(erreur, file=sys.stderr)

    # --- réception -------------------------------------------------------

    def _appliquer(self, message: MessageFil) -> None:
        """Seul endroit qui touche les widgets sur ordre du fil d'exécution."""
        match message:
            case Journal(texte):
                # Texte d'affichage, jamais un aiguillage.
                self._ecrire(texte)
            case PolitiqueLue(plancher):
                self._accueillir_plancher(plancher)
            case PolitiqueRefusee() as refus:
                # Non terminal : le `Termine` qui suit réactivera le bouton *Lancer*.
                lignes = lignes_de_la_politique_refusee(refus)
                self._ecrire_lignes(lignes)
                self.dialogues.erreur("Politique refusée", "\n".join(lignes), self.racine)
            case PlanPret(plan):
                self._ecrire_lignes(lignes_du_plan(plan))
            case DemandeConfirmation() as demande:
                # Jamais depuis l'intérieur d'un tour de pompe : une modale Tk fait
                # tourner une boucle d'événements imbriquée, qui rappellerait ce tour
                # dans lui-même. Le fil attend sa réponse, il a tout le temps — et le
                # plan qu'il vient d'émettre est déjà à l'écran, sous la boîte.
                self._planifier(0, lambda: self._repondre_a_la_demande(demande))
            case Progression(accomplies, total):
                maximum, valeur = reglage_barre(message)
                self.barre.configure(maximum=maximum, value=valeur)
                self.etiquette_progression.configure(text=f"{accomplies} / {total}")
            case CreationReussie(compte):
                # Dès le premier compte, pas à la fin du lot.
                self.enregistrables.ajouter(compte)
                self.bouton_enregistrer.configure(state=tk.NORMAL)
            case Termine(rapport):
                # Le rapport fait foi sur ce que le CSV portera.
                self.enregistrables.fixer(rapport.comptes_crees)
                if rapport.comptes_crees:
                    self.bouton_enregistrer.configure(state=tk.NORMAL)
                self._ecrire_lignes(lignes_du_rapport(rapport))
                self._reactiver_lancement()
            case Echoue(texte):
                self._ecrire(texte)
                self._reactiver_lancement()
                self.dialogues.erreur("Arrêt", texte, self.racine)
            case AnnuaireManquant():
                self._reactiver_lancement()
                self._ouvrir_fenetre_annuaire()
            case _:
                # `AnnuaireCree` ne circule que sur la file du dialogue de création :
                # ici, un message non reconnu est une anomalie, pas un cas de figure.
                self._ecrire(ligne_de_message_inconnu(message))

    def _repondre_a_la_demande(self, demande: DemandeConfirmation) -> None:
        """Pose la question, puis débloque le fil — quoi qu'il arrive.

        Le fil d'exécution est arrêté sur `attendre()` : une exception qui partirait
        d'ici sans répondre le laisserait bloqué, bouton *Lancer* grisé, jusqu'à la
        fermeture de la fenêtre. Le `finally` répond « non » dans ce cas : rien n'a
        encore été écrit, et ne rien écrire est le côté sûr.
        """
        accorde = False
        try:
            accorde = self.dialogues.question_grave(
                "Écrire sur le firewall", demande.texte, self.racine
            )
        finally:
            demande.repondre(accorde)

    def _accueillir_plancher(self, plancher: PlancherPolitique) -> None:
        premiere_lecture = self.politique is None
        self.politique = politique_a_afficher(self.politique, plancher)
        self.plancher = plancher
        if premiere_lecture:
            # Pré-remplissage à la première lecture seulement : une relecture ne
            # réécrit jamais une valeur que l'opérateur a durcie entre-temps.
            self.var_longueur.set(self.politique.longueur)
            self.var_minuscules.set(self.politique.minuscules)
            self.var_majuscules.set(self.politique.majuscules)
            self.var_chiffres.set(self.politique.chiffres)
            self.var_speciaux.set(self.politique.speciaux)
        self.etiquette_plancher.configure(text=libelle_plancher(plancher))
        for champ in self.champs_politique:
            champ["state"] = tk.NORMAL

    # --- enregistrement --------------------------------------------------

    def _enregistrer_mots_de_passe(self) -> None:
        comptes = self.enregistrables.comptes
        if not comptes:
            self.dialogues.information(
                "Rien à enregistrer",
                "Aucun compte n'a été créé : il n'y a aucun mot de passe à écrire.",
                self.racine,
            )
            return
        chemin = self.dialogues.fichier_a_ecrire(self.racine)
        if not chemin:
            return
        try:
            sortie.ecrire_mots_de_passe(Path(chemin), comptes)
        except OSError as erreur:
            self.dialogues.erreur("Écriture impossible", str(erreur), self.racine)
            return
        # Marqué seulement ici, et seulement sur l'instantané réellement écrit : le
        # sélecteur de fichier a fait tourner la boucle d'événements, et les comptes
        # créés pendant ce temps ne sont dans aucun fichier.
        self.enregistrables.marquer_enregistres(comptes)
        self._ecrire(ligne_d_enregistrement(comptes, chemin))

    # --- création de l'annuaire ------------------------------------------

    def _ouvrir_fenetre_annuaire(self) -> None:
        """Fenêtre séparée, sa propre connexion : `executer` a déjà déconnecté le
        boîtier dans son `finally`."""
        dialogue = tk.Toplevel(self.racine)
        dialogue.title("Créer l'annuaire LDAP interne")
        cadre = ttk.Frame(dialogue, padding=8)
        cadre.grid(row=0, column=0, sticky="nsew")
        cadre.columnconfigure(1, weight=1)
        ttk.Label(
            cadre,
            text="Le boîtier ne déclare aucun annuaire LDAP interne.\n"
            "Cette opération ne se refait pas.",
            justify=tk.LEFT,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=3)

        var_domainname = tk.StringVar()
        var_organisation = tk.StringVar()
        var_dc = tk.StringVar()
        var_secret = tk.StringVar()
        for rang, (libelle, variable, masque) in enumerate(
            (
                ("domainname", var_domainname, ""),
                ("o", var_organisation, ""),
                ("dc", var_dc, ""),
                ("mot de passe de cn=StormshieldAdmin", var_secret, "•"),
            ),
            start=1,
        ):
            ttk.Label(cadre, text=libelle).grid(row=rang, column=0, sticky="w", padx=6, pady=3)
            ttk.Entry(cadre, textvariable=variable, show=masque).grid(
                row=rang, column=1, sticky="ew", padx=6, pady=3
            )
        ttk.Label(
            cadre,
            text="Ce mot de passe est saisi par vous : l'outil ne le génère pas et ne le\n"
            "conserve pas. Notez-le avant de valider.",
            justify=tk.LEFT,
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=6, pady=3)

        bouton = ttk.Button(cadre, text="Créer l'annuaire")
        bouton.grid(row=6, column=0, sticky="w", padx=6, pady=3)

        # `self.creation_annuaire_en_cours` porte l'état de ce fil : la pompe est
        # planifiée sur la fenêtre principale, elle survit au dialogue, et fermer la
        # fenêtre principale pendant la création doit aussi demander confirmation.

        def oublier_les_saisies() -> None:
            """Le secret de cn=StormshieldAdmin ne survit pas au dialogue : sans cela il
            resterait dans l'interpréteur Tcl tout le reste de la session."""
            for variable in (var_domainname, var_organisation, var_dc, var_secret):
                variable.set("")

        def fermer() -> None:
            if self.creation_annuaire_en_cours:
                self.dialogues.avertissement(
                    "Création en cours", FERMETURE_PENDANT_CREATION, dialogue
                )
                return
            oublier_les_saisies()
            dialogue.destroy()

        def appliquer(message: MessageFil) -> None:
            match message:
                case AnnuaireCree(domaine):
                    self.creation_annuaire_en_cours = False
                    self._ecrire(f"annuaire {domaine} créé et activé")
                    oublier_les_saisies()
                    dialogue.destroy()
                    self.dialogues.information(
                        "Annuaire créé",
                        f"L'annuaire {domaine} est créé et activé. Relancez le lot.",
                        self.racine,
                    )
                case Journal(texte):
                    self._ecrire(texte)
                case Echoue(texte):
                    self.creation_annuaire_en_cours = False
                    self._ecrire(texte)
                    # Le dialogue peut avoir disparu : le refus se dit alors sur la
                    # fenêtre principale, il ne doit pas se perdre.
                    if dialogue.winfo_exists():
                        bouton.configure(state=tk.NORMAL)
                        self.dialogues.erreur("Création refusée", texte, dialogue)
                    else:
                        self.dialogues.erreur("Création refusée", texte, self.racine)
                case _:
                    # Remis à faux ici aussi : un message terminal inconnu tomberait
                    # dans cette branche, la pompe s'arrêterait, et le dialogue comme
                    # la fenêtre principale resteraient verrouillés pour toujours.
                    self.creation_annuaire_en_cours = False
                    self._ecrire(ligne_de_message_inconnu(message))

        def creer() -> None:
            annuaire = ParametresAnnuaire(
                domainname=var_domainname.get().strip(),
                organisation=var_organisation.get().strip(),
                dc=var_dc.get().strip(),
                mot_de_passe=var_secret.get(),
            )
            manquants = [
                nom
                for nom, valeur in (
                    ("domainname", annuaire.domainname),
                    ("o", annuaire.organisation),
                    ("dc", annuaire.dc),
                    ("mot de passe de cn=StormshieldAdmin", annuaire.mot_de_passe),
                )
                if not valeur
            ]
            if manquants:
                self.dialogues.erreur(
                    "Champ manquant",
                    "À renseigner : " + ", ".join(manquants),
                    dialogue,
                )
                return
            bouton.configure(state=tk.DISABLED)
            # Champs lus ici, dans le fil de l'interface : rien de `self` ne voyage
            # jusqu'au fil, pas même le temps d'un appel.
            session = self._connexion_des_champs()
            fabriquer = self.fabriquer_boitier
            file: queue.Queue[MessageFil] = queue.Queue()
            self.creation_annuaire_en_cours = True
            threading.Thread(
                target=travailler_annuaire,
                args=(session, annuaire, file.put, fabriquer),
                daemon=True,
            ).start()
            # Le secret est parti avec `annuaire` : il n'a plus rien à faire dans Tcl.
            var_secret.set("")
            self._pomper(file, appliquer)

        bouton.configure(command=creer)
        # Sans cette interception, fermer le dialogue pendant la création laissait la
        # pompe délivrer ses messages à des widgets détruits.
        dialogue.protocol("WM_DELETE_WINDOW", fermer)
        dialogue.transient(self.racine)
        dialogue.grab_set()

    # --- fermeture -------------------------------------------------------

    def _a_la_fermeture(self) -> None:
        """Le fil est un démon : il meurt avec l'interpréteur, où qu'il en soit.

        Sans cette interception, la boucle rendait la main sans un mot et les mots de
        passe déjà générés partaient avec le processus.
        """
        avertissement = avertissement_de_fermeture(
            lot_en_cours=self.lot_en_cours,
            creation_annuaire_en_cours=self.creation_annuaire_en_cours,
            secrets_en_attente=self.enregistrables.secrets_en_attente,
        )
        if avertissement is not None and not self.dialogues.question_grave(
            "Fermer la fenêtre", avertissement, self.racine
        ):
            return
        self.racine.destroy()

    def lancer(self) -> None:
        self.racine.protocol("WM_DELETE_WINDOW", self._a_la_fermeture)
        self.racine.mainloop()


def lancer() -> None:
    """Construit et lance la fenêtre. Cible du point d'entrée et de PyInstaller."""
    Fenetre().lancer()
