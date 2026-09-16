"""Fenêtre unique tkinter. Ne décide rien : elle câble `presentation` sur des widgets.

Seul module du paquet à importer `tkinter`, et le seul qu'aucun test n'importe :
`tkinter` peut manquer sur la machine de test comme sur le runner d'intégration
continue. Tout ce qui se vérifie vit dans `presentation` ; ce qui reste ici — la
disposition, les boîtes de dialogue, l'activation des champs — relève du cahier de
recette.

Quatre règles tiennent ce fichier :

- le fil d'exécution ne touche jamais un widget. Il reçoit un objet figé, publie dans
  une `queue`, et `PompeEvenements` — replanifiée par `after()` — est seule à ramener
  ces messages dans le fil de l'interface. Rien de `self` ne lui est passé, cible comme
  arguments : un test de structure le vérifie sur ce source ;
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
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from types import TracebackType

from stormshield_utilisateurs import lecture, sortie
from stormshield_utilisateurs.execution import (
    CreationReussie,
    Echoue,
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
    Utilisateur,
)
from stormshield_utilisateurs.presentation import (
    FERMETURE_PENDANT_CREATION,
    POLITIQUE_INITIALE,
    AnnuaireCree,
    AnnuaireManquant,
    BoiteParLot,
    ComptesEnregistrables,
    Connexion,
    IncidentInterface,
    MessageFil,
    Parametres,
    ParametresAnnuaire,
    PompeEvenements,
    Publieur,
    avertissement_de_fermeture,
    avertissement_perte_de_secrets,
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
        exc: type[BaseException],  # noqa: ARG002 - signature imposée par Tk
        val: BaseException,
        tb: TracebackType | None,  # noqa: ARG002 - la trace est déjà dans `val`
    ) -> None:
        self._signaler(val)


class Fenetre:
    """Fenêtre principale. Tous ses widgets vivent dans le fil de l'interface."""

    def __init__(self) -> None:
        self.racine = _Racine(self._signaler_exception_tk)
        self.racine.title(TITRE)
        # Vrai entre le démarrage d'un fil de lot et son message terminal : c'est ce
        # que l'opérateur perdrait en fermant la fenêtre.
        self.lot_en_cours = False
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

        self.bouton_lancer = ttk.Button(cadre, text="Lancer", command=self._au_lancement)
        self.bouton_lancer.grid(row=10, column=0, sticky="w", padx=6, pady=3)

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
        chemin = filedialog.askopenfilename(
            parent=self.racine,
            title="Fichier des utilisateurs",
            filetypes=[("CSV", "*.csv"), ("Tous les fichiers", "*.*")],
        )
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
            messagebox.showerror(
                "Longueur invalide",
                "La longueur des mots de passe doit être un nombre entier.",
                parent=self.racine,
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
            messagebox.showerror("Lancement refusé", "\n".join(obstacles), parent=self.racine)
            return
        try:
            utilisateurs, rejets = lecture.lire(chemin)
        except lecture.ColonnesManquantes as erreur:
            messagebox.showerror("Fichier invalide", str(erreur), parent=self.racine)
            return
        except OSError as erreur:
            messagebox.showerror("Fichier illisible", str(erreur), parent=self.racine)
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
        self.bouton_lancer.configure(state=tk.DISABLED)
        self._demarrer(parametres, utilisateurs)

    def _confirmer_la_perte_des_secrets(self) -> bool:
        """Dernier rempart avant qu'un nouveau lot efface les mots de passe du précédent.

        Les comptes existent déjà sur le boîtier : un relancement les classera « déjà
        présent, ignoré » et ne leur redonnera jamais de mot de passe.
        """
        en_attente = self.enregistrables.secrets_en_attente
        if not en_attente:
            return True
        return messagebox.askyesno(
            "Mots de passe non enregistrés",
            avertissement_perte_de_secrets(en_attente),
            icon=messagebox.WARNING,
            default=messagebox.NO,
            parent=self.racine,
        )

    def _demarrer(self, parametres: Parametres, utilisateurs: list[Utilisateur]) -> None:
        # Le lot précédent est soldé : sa liste ne doit pas se mélanger à celle-ci, et
        # le bouton ne doit pas rester actif sur un contenu qui vient d'être vidé.
        self.enregistrables.reinitialiser()
        self.bouton_enregistrer.configure(state=tk.DISABLED)
        # Le lot qui commence a droit à sa boîte : le silence ne valait que pour le
        # précédent.
        self.boite_incident.reinitialiser()
        # Variable locale : rien de `self` ne doit voyager jusqu'au fil.
        file: queue.Queue[MessageFil] = queue.Queue()
        fil = threading.Thread(
            target=travailler,
            args=(parametres, utilisateurs, file.put),
            daemon=True,
        )
        self.lot_en_cours = True
        fil.start()
        self._pomper(file, self._appliquer)

    def _pomper(self, file: "queue.Queue[MessageFil]", appliquer: Publieur) -> None:
        PompeEvenements(file, appliquer, self._planifier, self._signaler_incident).tour()

    def _planifier(self, delai_ms: int, rappel: Callable[[], None]) -> None:
        # `after` conserve la référence du rappel : la pompe survit à la fin de ce tour.
        self.racine.after(delai_ms, rappel)

    def _reactiver_lancement(self) -> None:
        self.lot_en_cours = False
        self.bouton_lancer.configure(state=tk.NORMAL)

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
        messagebox.showerror("Anomalie interne", resume, parent=self.racine)

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
                messagebox.showerror(
                    "Politique refusée", "\n".join(lignes), parent=self.racine
                )
            case PlanPret(plan):
                self._ecrire_lignes(lignes_du_plan(plan))
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
                messagebox.showerror("Arrêt", texte, parent=self.racine)
            case AnnuaireManquant():
                self._reactiver_lancement()
                self._ouvrir_fenetre_annuaire()
            case _:
                # `AnnuaireCree` ne circule que sur la file du dialogue de création :
                # ici, un message non reconnu est une anomalie, pas un cas de figure.
                self._ecrire(ligne_de_message_inconnu(message))

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
            messagebox.showinfo(
                "Rien à enregistrer",
                "Aucun compte n'a été créé : il n'y a aucun mot de passe à écrire.",
                parent=self.racine,
            )
            return
        chemin = filedialog.asksaveasfilename(
            parent=self.racine,
            title="Enregistrer les mots de passe",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not chemin:
            return
        try:
            sortie.ecrire_mots_de_passe(Path(chemin), comptes)
        except OSError as erreur:
            messagebox.showerror("Écriture impossible", str(erreur), parent=self.racine)
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

        # Vrai entre le démarrage du fil de création et son message terminal. La pompe
        # est planifiée sur la fenêtre principale : elle survit au dialogue et
        # délivrerait ses messages à des widgets détruits.
        creation_en_cours = False

        def oublier_les_saisies() -> None:
            """Le secret de cn=StormshieldAdmin ne survit pas au dialogue : sans cela il
            resterait dans l'interpréteur Tcl tout le reste de la session."""
            for variable in (var_domainname, var_organisation, var_dc, var_secret):
                variable.set("")

        def fermer() -> None:
            if creation_en_cours:
                messagebox.showwarning(
                    "Création en cours", FERMETURE_PENDANT_CREATION, parent=dialogue
                )
                return
            oublier_les_saisies()
            dialogue.destroy()

        def appliquer(message: MessageFil) -> None:
            nonlocal creation_en_cours
            match message:
                case AnnuaireCree(domaine):
                    creation_en_cours = False
                    self._ecrire(f"annuaire {domaine} créé et activé")
                    oublier_les_saisies()
                    dialogue.destroy()
                    messagebox.showinfo(
                        "Annuaire créé",
                        f"L'annuaire {domaine} est créé et activé. Relancez le lot.",
                        parent=self.racine,
                    )
                case Journal(texte):
                    self._ecrire(texte)
                case Echoue(texte):
                    creation_en_cours = False
                    self._ecrire(texte)
                    # Le dialogue peut avoir disparu : le refus se dit alors sur la
                    # fenêtre principale, il ne doit pas se perdre.
                    if dialogue.winfo_exists():
                        bouton.configure(state=tk.NORMAL)
                        messagebox.showerror("Création refusée", texte, parent=dialogue)
                    else:
                        messagebox.showerror("Création refusée", texte, parent=self.racine)
                case _:
                    self._ecrire(ligne_de_message_inconnu(message))

        def creer() -> None:
            nonlocal creation_en_cours
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
                messagebox.showerror(
                    "Champ manquant",
                    "À renseigner : " + ", ".join(manquants),
                    parent=dialogue,
                )
                return
            bouton.configure(state=tk.DISABLED)
            # Champs lus ici, dans le fil de l'interface : rien de `self` ne voyage
            # jusqu'au fil, pas même le temps d'un appel.
            session = self._connexion_des_champs()
            file: queue.Queue[MessageFil] = queue.Queue()
            creation_en_cours = True
            threading.Thread(
                target=travailler_annuaire,
                args=(session, annuaire, file.put),
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
            secrets_en_attente=self.enregistrables.secrets_en_attente,
        )
        if avertissement is not None and not messagebox.askyesno(
            "Fermer la fenêtre",
            avertissement,
            icon=messagebox.WARNING,
            default=messagebox.NO,
            parent=self.racine,
        ):
            return
        self.racine.destroy()

    def lancer(self) -> None:
        self.racine.protocol("WM_DELETE_WINDOW", self._a_la_fermeture)
        self.racine.mainloop()


def lancer() -> None:
    """Construit et lance la fenêtre. Cible du point d'entrée et de PyInstaller."""
    Fenetre().lancer()
