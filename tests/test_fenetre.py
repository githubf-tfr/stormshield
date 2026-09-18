"""Fenêtre tkinter, éprouvée sur de vrais widgets.

Ce fichier exige `tkinter` (paquet `python3-tk` sous Debian) et un affichage :
`xvfb-run -a pytest` en fournit un. Sans l'un ou sans l'autre, tout ce fichier se
saute avec sa raison — la suite reste verte sur une machine qui n'a ni l'un ni l'autre,
et l'intégration continue, elle, fournit les deux.

Deux choses ne sont jamais les vraies. Les boîtes modales : elles feraient tourner une
boucle d'événements imbriquée et n'en sortiraient qu'au clic d'un humain — la fenêtre
les reçoit en paramètre, et `_Boites` ci-dessous note ce qui s'ouvre et répond ce que
le test a décidé. La fabrique de boîtier : `BoitierMemoire`, jamais une session SSL.
Tout le reste est réel — les widgets, la grille, les fils, la file, `after`.

Ce qui reste hors de portée et vit dans le cahier de recette : l'apparence, les six
défauts de `Dialogues` qui appellent vraiment `messagebox`/`filedialog`, et la fonction
`lancer()` du module, qui construit la fenêtre de production puis entre dans
`mainloop`.
"""

import contextlib
import queue
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fabriques import utilisateur

from stormshield_utilisateurs.boitier import Boitier
from stormshield_utilisateurs.boitier_memoire import BoitierMemoire
from stormshield_utilisateurs.execution import (
    AnnuaireAbsent,
    CreationReussie,
    Journal,
    PlanPret,
    PolitiqueLue,
    PolitiqueRefusee,
    Progression,
    Termine,
)
from stormshield_utilisateurs.modele import (
    CompteCree,
    Plan,
    PlancherPolitique,
    PolitiqueMotDePasse,
    Rapport,
    TravailCompte,
)
from stormshield_utilisateurs.presentation import (
    ARRET_DEMANDE_AU_CLIC,
    FERMETURE_PENDANT_CREATION,
    POLITIQUE_INITIALE,
    AnnuaireCree,
    AnnuaireManquant,
    Connexion,
    DemandeConfirmation,
    Echoue,
    MessageFil,
    boitier_de_la_connexion,
)

try:
    import tkinter as tk
    from tkinter import ttk

    from stormshield_utilisateurs.fenetre import (
        DIALOGUES_REELS,
        LIBELLE_CERTIFICAT,
        TITRE,
        Dialogues,
        Fenetre,
    )
except ImportError as erreur:  # `python3-tk` absent : rien de ce fichier n'est jouable.
    pytest.skip(f"tkinter absent : {erreur}", allow_module_level=True)


def _raison_sans_affichage() -> str | None:
    """Pourquoi ce fichier ne peut pas s'exécuter ici. None = il peut.

    La réponse vient de Tk lui-même, jamais d'une supposition sur la plateforme : sous
    Windows il n'y a pas de `DISPLAY` et une fenêtre s'ouvre quand même.
    """
    try:
        sonde = tk.Tk()
    except tk.TclError as erreur:
        return f"aucun affichage pour tkinter ({erreur}) — relancer sous `xvfb-run -a`"
    sonde.destroy()
    return None


_SANS_AFFICHAGE = _raison_sans_affichage()
pytestmark = pytest.mark.skipif(_SANS_AFFICHAGE is not None, reason=_SANS_AFFICHAGE or "")

PLANCHER = PlancherPolitique(longueur_min=12, nombre_classes_min=3, entropie_min=0)
EN_TETE = "identifiant;nom;prenom;groupes\n"


class _Boites:
    """Les boîtes modales de la fenêtre, remplacées par un carnet.

    Note tout ce qui s'ouvre — titre, texte, et la fenêtre sous laquelle la boîte se
    pose, qui n'est pas la même selon qu'on parle à la fenêtre principale ou au
    dialogue de création d'annuaire — et répond ce que le test a décidé.
    """

    def __init__(
        self,
        *,
        reponse_aux_questions: bool = True,
        chemin_a_lire: str = "",
        chemin_a_ecrire: str = "",
    ) -> None:
        self.erreurs: list[tuple[str, str, tk.Misc]] = []
        self.informations: list[tuple[str, str, tk.Misc]] = []
        self.avertissements: list[tuple[str, str, tk.Misc]] = []
        self.questions: list[tuple[str, str, tk.Misc]] = []
        self.reponse_aux_questions = reponse_aux_questions
        self.chemin_a_lire = chemin_a_lire
        self.chemin_a_ecrire = chemin_a_ecrire
        self.selections_a_lire = 0
        self.selections_a_ecrire = 0

    def erreur(self, titre: str, message: str, parent: tk.Misc) -> None:
        self.erreurs.append((titre, message, parent))

    def information(self, titre: str, message: str, parent: tk.Misc) -> None:
        self.informations.append((titre, message, parent))

    def avertissement(self, titre: str, message: str, parent: tk.Misc) -> None:
        self.avertissements.append((titre, message, parent))

    def question_grave(self, titre: str, message: str, parent: tk.Misc) -> bool:
        self.questions.append((titre, message, parent))
        return self.reponse_aux_questions

    def fichier_a_lire(self, parent: tk.Misc) -> str:
        del parent
        self.selections_a_lire += 1
        return self.chemin_a_lire

    def fichier_a_ecrire(self, parent: tk.Misc) -> str:
        del parent
        self.selections_a_ecrire += 1
        return self.chemin_a_ecrire

    def dialogues(self) -> Dialogues:
        return Dialogues(
            erreur=self.erreur,
            information=self.information,
            avertissement=self.avertissement,
            question_grave=self.question_grave,
            fichier_a_lire=self.fichier_a_lire,
            fichier_a_ecrire=self.fichier_a_ecrire,
        )

    @property
    def titres_des_erreurs(self) -> list[str]:
        return [titre for titre, _, _ in self.erreurs]

    @property
    def titres_des_questions(self) -> list[str]:
        return [titre for titre, _, _ in self.questions]


def _fabrique(boitier: Boitier) -> Callable[[Connexion], Boitier]:
    """Toujours le même double, quelle que soit la connexion demandée."""

    def fabriquer(connexion: Connexion) -> Boitier:
        del connexion
        return boitier

    return fabriquer


@contextlib.contextmanager
def _fenetre_ouverte(
    boites: _Boites | None = None, boitier: Boitier | None = None
) -> Iterator[tuple[Fenetre, _Boites]]:
    """Ouvre une fenêtre, la détruit quoi qu'il arrive.

    Sans la destruction, l'interpréteur Tcl d'un test survivrait au suivant et la
    variable par défaut du suivant irait se poser sur la fenêtre du précédent.
    """
    carnet = _Boites() if boites is None else boites
    fenetre = Fenetre(
        dialogues=carnet.dialogues(),
        fabriquer_boitier=_fabrique(BoitierMemoire() if boitier is None else boitier),
    )
    try:
        yield fenetre, carnet
    finally:
        # Déjà détruite par le test lui-même dans tout ce qui éprouve la fermeture.
        with contextlib.suppress(tk.TclError):
            fenetre.racine.destroy()


def _retenir(boitier: BoitierMemoire, operation_retenue: str) -> threading.Event:
    """Retient le fil sur une opération du boîtier, jusqu'à ce que le test le libère.

    Le double est si rapide qu'un lot entier peut s'achever avant le premier tour de
    pompe : sans ce frein, tout ce qui ne se voit que *pendant* un lot — l'état des
    deux boutons, le bouton *Arrêter* qui doit être cliquable — serait inobservable, et
    l'affirmer sans frein rendrait le test faussement vert une fois sur deux.
    """
    feu_vert = threading.Event()

    def retenir(operation: str, cible: str) -> None:
        del cible
        if operation == operation_retenue:
            assert feu_vert.wait(20.0), "le test n'a jamais libéré le fil"

    boitier.declencheur = retenir
    return feu_vert


def _journal(fenetre: Fenetre) -> str:
    return str(fenetre.journal.get("1.0", tk.END))


def _etat(widget: tk.Misc) -> str:
    return str(widget["state"])


def _tourner(
    fenetre: Fenetre, condition: Callable[[], bool], limite_s: float = 20.0
) -> bool:
    """Fait tourner la boucle d'événements jusqu'à ce que `condition` tienne.

    Le fil d'un lot publie dans une file et rien ne la vide hors de la pompe, que
    `after` replanifie : sans boucle d'événements qui tourne, aucun message n'arrive
    jamais. L'attente est bornée pour qu'un test qui ne verra jamais sa condition
    échoue au lieu de pendre.
    """
    limite = time.monotonic() + limite_s
    while True:
        fenetre.racine.update()
        if condition():
            return True
        if time.monotonic() >= limite:
            return False
        time.sleep(0.005)


def _remplir(fenetre: Fenetre, fichier: Path, *, simulation: bool = True) -> None:
    """Ce que l'opérateur saisit avant de cliquer sur *Lancer*."""
    fenetre.var_hote.set("firewall.local")
    fenetre.var_compte.set("admin")
    fenetre.var_mot_de_passe.set("secret")
    fenetre.var_fichier.set(str(fichier))
    fenetre.var_simulation.set(simulation)


def _csv(dossier: Path, lignes: str = "marie;Dupont;Marie;profs\n") -> Path:
    chemin = dossier / "entree.csv"
    chemin.write_text(EN_TETE + lignes, encoding="utf-8")
    return chemin


def _plan(*travaux: TravailCompte) -> Plan:
    return Plan(
        travaux=travaux,
        groupes_a_creer=(),
        nombre_orphelins=0,
        nombre_membres_non_rattaches=0,
        groupes_ambigus=(),
        comptes_ambigus=(),
        domaine="interne.local",
    )


def _dialogue_annuaire(fenetre: Fenetre) -> tk.Toplevel:
    """Le dialogue de création d'annuaire : la seule autre fenêtre du processus."""
    ouverts = [
        enfant for enfant in fenetre.racine.winfo_children() if isinstance(enfant, tk.Toplevel)
    ]
    assert len(ouverts) == 1, f"un seul dialogue attendu, {len(ouverts)} ouvert(s)"
    return ouverts[0]


def _saisies(dialogue: tk.Toplevel) -> list[ttk.Entry]:
    """Les champs du dialogue, dans l'ordre : domainname, o, dc, puis le secret."""
    cadre = dialogue.winfo_children()[0]
    return [enfant for enfant in cadre.winfo_children() if isinstance(enfant, ttk.Entry)]


def _bouton_du_dialogue(dialogue: tk.Toplevel) -> ttk.Button:
    cadre = dialogue.winfo_children()[0]
    boutons = [enfant for enfant in cadre.winfo_children() if isinstance(enfant, ttk.Button)]
    assert len(boutons) == 1, f"un seul bouton attendu, {len(boutons)} trouvé(s)"
    return boutons[0]


def _saisir_l_annuaire(dialogue: tk.Toplevel) -> None:
    """Les quatre champs du dialogue, remplis comme l'opérateur le ferait."""
    for champ, valeur in zip(
        _saisies(dialogue),
        ("interne.local", "Ecole", "dc=interne,dc=local", "Secret-Admin-1234"),
        strict=True,
    ):
        champ.insert(0, valeur)


def _fermer_comme_le_gestionnaire(fenetre_tk: tk.Tk | tk.Toplevel) -> None:
    """Déclenche `WM_DELETE_WINDOW` comme le ferait la croix du gestionnaire.

    Aucun gestionnaire de fenêtres ne tourne sous `xvfb` : le test appelle lui-même la
    commande Tcl que Tk a enregistrée, ce qui prouve du même coup qu'elle l'est.
    """
    rappel = fenetre_tk.protocol("WM_DELETE_WINDOW")
    assert rappel, "aucune interception de la fermeture n'est posée"
    fenetre_tk.tk.call(rappel)


# --- construction, grille, état initial -----------------------------------


def test_la_fenetre_porte_son_titre() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        assert fenetre.racine.title() == TITRE


def test_les_coutures_sont_au_defaut_de_production() -> None:
    """Le défaut doit être le vrai comportement : une couture qui simule par défaut
    livrerait un exécutable qui n'ouvre aucune boîte et ne se connecte à rien."""
    fenetre = Fenetre()
    try:
        assert fenetre.dialogues is DIALOGUES_REELS
        assert fenetre.fabriquer_boitier is boitier_de_la_connexion
    finally:
        fenetre.racine.destroy()


def test_les_identifiants_naissent_vides() -> None:
    """Aucun identifiant n'est mémorisé d'un lancement à l'autre."""
    with _fenetre_ouverte() as (fenetre, _):
        assert (
            fenetre.var_hote.get(),
            fenetre.var_compte.get(),
            fenetre.var_mot_de_passe.get(),
            fenetre.var_fichier.get(),
        ) == ("", "", "", "")


def test_la_simulation_et_la_verification_du_certificat_naissent_cochees() -> None:
    """Les deux cases dont le décochage coûte quelque chose : jamais décochées d'office."""
    with _fenetre_ouverte() as (fenetre, _):
        assert fenetre.var_simulation.get() is True
        assert fenetre.var_certificat.get() is True


def test_le_libelle_du_certificat_dit_ce_que_le_decochage_coute() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        cases = [
            enfant
            for cadre in fenetre.racine.winfo_children()
            for enfant in cadre.winfo_children()
            if isinstance(enfant, tk.Checkbutton)
        ]
        assert [str(case["text"]) for case in cases] == [LIBELLE_CERTIFICAT]


def test_les_champs_de_politique_naissent_grises() -> None:
    """Tant que le plancher du boîtier est inconnu, il n'y a rien à durcir."""
    with _fenetre_ouverte() as (fenetre, _):
        assert [_etat(champ) for champ in fenetre.champs_politique] == ["disabled"] * 5
        assert "inconnue" in str(fenetre.etiquette_plancher["text"])


def test_la_politique_de_repli_pre_remplit_les_champs() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        assert fenetre.var_longueur.get() == POLITIQUE_INITIALE.longueur
        assert fenetre.var_speciaux.get() == POLITIQUE_INITIALE.speciaux


def test_lancer_est_actif_et_arreter_grise_avant_tout_lot() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        assert _etat(fenetre.bouton_lancer) == "normal"
        assert _etat(fenetre.bouton_arreter) == "disabled"


def test_le_bouton_d_enregistrement_nait_grise() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        assert _etat(fenetre.bouton_enregistrer) == "disabled"


def test_arreter_est_pose_a_cote_de_lancer_et_non_a_sa_place() -> None:
    """Les deux boutons doivent être visibles ensemble, dans le même sous-cadre et
    adjacents : l'opérateur doit voir d'un coup d'œil lequel des deux gestes lui est
    offert."""
    with _fenetre_ouverte() as (fenetre, _):
        assert fenetre.bouton_lancer.winfo_parent() == fenetre.bouton_arreter.winfo_parent()
        assert fenetre.bouton_lancer.grid_info()["row"] == fenetre.bouton_arreter.grid_info()["row"]
        assert int(fenetre.bouton_lancer.grid_info()["column"]) == 0
        assert int(fenetre.bouton_arreter.grid_info()["column"]) == 1


def test_le_journal_est_la_seule_ligne_qui_s_etire_en_hauteur() -> None:
    """Sans ce poids, agrandir la fenêtre n'agrandit pas le journal."""
    with _fenetre_ouverte() as (fenetre, _):
        cadre_du_journal = fenetre.journal.master
        assert isinstance(cadre_du_journal, ttk.Frame)
        cadre = cadre_du_journal.master
        assert isinstance(cadre, ttk.Frame)
        rang_du_journal = int(cadre_du_journal.grid_info()["row"])
        assert int(cadre.grid_rowconfigure(rang_du_journal)["weight"]) == 1


def test_la_barre_et_son_compteur_partagent_leur_ligne() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        assert fenetre.barre.grid_info()["row"] == fenetre.etiquette_progression.grid_info()["row"]
        assert str(fenetre.etiquette_progression["text"]) == "0 / 0"


# --- journal ---------------------------------------------------------------


def test_le_journal_reste_desactive_entre_deux_ecritures() -> None:
    """Désactivé pour qu'on n'y tape pas, ce qui n'empêche ni la sélection ni Ctrl-C."""
    with _fenetre_ouverte() as (fenetre, _):
        fenetre._appliquer(Journal("première ligne"))
        fenetre._appliquer(Journal("seconde ligne"))
        assert _journal(fenetre) == "première ligne\nseconde ligne\n\n"
        assert _etat(fenetre.journal) == "disabled"


# --- sélection de fichier --------------------------------------------------


def test_parcourir_renseigne_le_champ_du_fichier() -> None:
    with _fenetre_ouverte(_Boites(chemin_a_lire="/tmp/liste.csv")) as (fenetre, boites):
        fenetre._parcourir()
        assert fenetre.var_fichier.get() == "/tmp/liste.csv"
        assert boites.selections_a_lire == 1


def test_parcourir_annule_laisse_le_champ_intact() -> None:
    """Le sélecteur rend une chaîne vide quand l'opérateur renonce : ne pas effacer
    ce qu'il avait déjà tapé."""
    with _fenetre_ouverte(_Boites(chemin_a_lire="")) as (fenetre, _):
        fenetre.var_fichier.set("deja_saisi.csv")
        fenetre._parcourir()
        assert fenetre.var_fichier.get() == "deja_saisi.csv"


# --- lecture des champs ----------------------------------------------------


def test_la_connexion_reprend_les_champs_et_la_case_du_certificat() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        fenetre.var_hote.set("sns.local")
        fenetre.var_compte.set("admin")
        fenetre.var_mot_de_passe.set("secret")
        fenetre.var_certificat.set(False)
        assert fenetre._connexion_des_champs() == Connexion(
            hote="sns.local", compte="admin", mot_de_passe="secret", verifier_certificat=False
        )


def test_la_politique_reprend_les_cases_de_classes() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        fenetre.var_longueur.set(24)
        fenetre.var_speciaux.set(False)
        assert fenetre._politique_des_champs() == PolitiqueMotDePasse(
            longueur=24, minuscules=True, majuscules=True, chiffres=True, speciaux=False
        )


# --- refus de lancement ----------------------------------------------------


def test_un_lot_sans_hote_ne_part_pas_et_le_dit(tmp_path: Path) -> None:
    with _fenetre_ouverte() as (fenetre, boites):
        fenetre.var_fichier.set(str(_csv(tmp_path)))
        fenetre.bouton_lancer.invoke()
        assert boites.titres_des_erreurs == ["Lancement refusé"]
        assert "l'hôte du firewall n'est pas renseigné" in boites.erreurs[0][1]
        assert fenetre.lot_en_cours is False
        assert _journal(fenetre).strip() == ""


def test_une_longueur_non_numerique_ouvre_sa_propre_boite(tmp_path: Path) -> None:
    """L'opérateur peut taper des lettres dans le champ de longueur : `IntVar.get()`
    lève alors, et la boîte doit nommer la cause plutôt que d'exposer une trace."""
    with _fenetre_ouverte() as (fenetre, boites):
        fenetre._appliquer(PolitiqueLue(PLANCHER))
        spinbox = fenetre.champs_politique[0]
        assert isinstance(spinbox, ttk.Spinbox)
        spinbox.delete(0, tk.END)
        spinbox.insert(0, "douze")
        _remplir(fenetre, _csv(tmp_path))
        fenetre.bouton_lancer.invoke()
        assert boites.titres_des_erreurs == ["Longueur invalide"]
        assert fenetre.lot_en_cours is False


def test_un_fichier_sans_les_bonnes_colonnes_ouvre_fichier_invalide(tmp_path: Path) -> None:
    mauvais = tmp_path / "mauvais.csv"
    mauvais.write_text("login;nom\nmarie;Dupont\n", encoding="utf-8")
    with _fenetre_ouverte() as (fenetre, boites):
        _remplir(fenetre, mauvais)
        fenetre.bouton_lancer.invoke()
        assert boites.titres_des_erreurs == ["Fichier invalide"]
        assert "identifiant" in boites.erreurs[0][1]
        assert fenetre.lot_en_cours is False


def test_un_fichier_illisible_ouvre_fichier_illisible(tmp_path: Path) -> None:
    """Un dossier désigné à la place d'un fichier : `OSError`, pas un défaut de colonnes."""
    with _fenetre_ouverte() as (fenetre, boites):
        _remplir(fenetre, tmp_path)
        fenetre.bouton_lancer.invoke()
        assert boites.titres_des_erreurs == ["Fichier illisible"]
        assert fenetre.lot_en_cours is False


def test_le_refus_de_perdre_les_secrets_annule_le_lot(tmp_path: Path) -> None:
    """Dernier rempart : l'opérateur dit non, et rien ne part — les mots de passe du
    lot précédent sont toujours là."""
    with _fenetre_ouverte(_Boites(reponse_aux_questions=False)) as (fenetre, boites):
        fenetre._appliquer(CreationReussie(CompteCree("marie", "Secret-1234")))
        _remplir(fenetre, _csv(tmp_path))
        fenetre.bouton_lancer.invoke()
        assert boites.titres_des_questions == ["Mots de passe non enregistrés"]
        assert fenetre.lot_en_cours is False
        assert _journal(fenetre).strip() == ""
        assert fenetre.enregistrables.secrets_en_attente == 1


def test_l_accord_de_perdre_les_secrets_laisse_partir_le_lot(tmp_path: Path) -> None:
    boitier = BoitierMemoire(groupes=["profs"])
    feu_vert = _retenir(boitier, "lister_utilisateurs")
    with _fenetre_ouverte(_Boites(reponse_aux_questions=True), boitier) as (fenetre, boites):
        fenetre._appliquer(CreationReussie(CompteCree("marie", "Secret-1234")))
        _remplir(fenetre, _csv(tmp_path))
        fenetre.bouton_lancer.invoke()
        assert boites.titres_des_questions == ["Mots de passe non enregistrés"]
        assert fenetre.lot_en_cours is True
        # La liste du lot précédent est vidée au démarrage effectif, pas avant.
        assert fenetre.enregistrables.secrets_en_attente == 0
        assert _etat(fenetre.bouton_enregistrer) == "disabled"
        feu_vert.set()
        assert _tourner(fenetre, lambda: not fenetre.lot_en_cours)


def test_le_durcissement_choisi_survit_a_la_relecture_du_boitier(tmp_path: Path) -> None:
    """Le réglage durci au moment du clic devient la politique courante : la lecture du
    boîtier qui suit dans le lot ne doit pas la rabaisser à ce qu'il propose."""
    boitier = BoitierMemoire(groupes=["profs"], plancher=PLANCHER)
    with _fenetre_ouverte(boitier=boitier) as (fenetre, _):
        fenetre._appliquer(PolitiqueLue(PLANCHER))
        fenetre.var_longueur.set(40)
        _remplir(fenetre, _csv(tmp_path))
        fenetre.bouton_lancer.invoke()
        assert fenetre.politique == PolitiqueMotDePasse(longueur=40)
        assert _tourner(fenetre, lambda: not fenetre.lot_en_cours)
        assert fenetre.var_longueur.get() == 40
        assert fenetre.politique == PolitiqueMotDePasse(longueur=40)


# --- un lot, du clic au bilan ---------------------------------------------


def test_un_lot_en_simulation_va_du_clic_au_bilan_sans_rien_ecrire(tmp_path: Path) -> None:
    """Le chemin complet : clic, lecture hors ligne, fil, file, pompe, widgets."""
    boitier = BoitierMemoire(groupes=["profs"])
    with _fenetre_ouverte(boitier=boitier) as (fenetre, boites):
        _remplir(fenetre, _csv(tmp_path))
        fenetre.bouton_lancer.invoke()
        assert _tourner(fenetre, lambda: not fenetre.lot_en_cours)
        journal = _journal(fenetre)
        assert "simulation" in journal
        assert "anomalie interne" not in journal
        assert boitier.utilisateurs == []
        assert _etat(fenetre.bouton_lancer) == "normal"
        assert _etat(fenetre.bouton_arreter) == "disabled"
        assert boites.erreurs == []


def test_pendant_le_lot_lancer_est_grise_et_arreter_seul_actif(tmp_path: Path) -> None:
    """Les deux boutons ne sont jamais actifs ensemble : un second lot lancé sur le
    premier viderait la liste des mots de passe pendant que la pompe y déverse encore
    les siens. Le fil est retenu sur l'inventaire pour que l'état se voie."""
    boitier = BoitierMemoire(groupes=["profs"])
    feu_vert = _retenir(boitier, "lister_utilisateurs")
    with _fenetre_ouverte(boitier=boitier) as (fenetre, _):
        _remplir(fenetre, _csv(tmp_path))
        fenetre.bouton_lancer.invoke()
        assert _etat(fenetre.bouton_lancer) == "disabled"
        assert _etat(fenetre.bouton_arreter) == "normal"
        feu_vert.set()
        assert _tourner(fenetre, lambda: not fenetre.lot_en_cours)
        assert _etat(fenetre.bouton_lancer) == "normal"
        assert _etat(fenetre.bouton_arreter) == "disabled"


def test_un_lot_reel_demande_l_accord_puis_cree_le_compte_et_son_mot_de_passe(
    tmp_path: Path,
) -> None:
    """Le lot réel dans son entier : la confirmation passe par une boîte planifiée hors
    du tour de pompe, le fil attend la réponse, et le CSV des mots de passe s'écrit."""
    boitier = BoitierMemoire(groupes=["profs"])
    sortie = tmp_path / "mots_de_passe.csv"
    boites = _Boites(reponse_aux_questions=True, chemin_a_ecrire=str(sortie))
    with _fenetre_ouverte(boites, boitier) as (fenetre, _):
        _remplir(fenetre, _csv(tmp_path), simulation=False)
        fenetre.bouton_lancer.invoke()
        assert _tourner(fenetre, lambda: not fenetre.lot_en_cours)
        assert boites.titres_des_questions == ["Écrire sur le firewall"]
        assert boitier.utilisateurs == ["marie"]
        assert boitier.mots_de_passe["marie"]
        assert _etat(fenetre.bouton_enregistrer) == "normal"
        fenetre.bouton_enregistrer.invoke()
        assert sortie.read_text(encoding="utf-8-sig").splitlines()[0] == "identifiant;mot_de_passe"
        assert boitier.mots_de_passe["marie"] in sortie.read_text(encoding="utf-8-sig")
        assert fenetre.enregistrables.secrets_en_attente == 0
        assert "mot de passe enregistré" in _journal(fenetre)


def test_un_lot_reel_refuse_a_la_confirmation_n_ecrit_rien(tmp_path: Path) -> None:
    boitier = BoitierMemoire(groupes=["profs"])
    with _fenetre_ouverte(_Boites(reponse_aux_questions=False), boitier) as (fenetre, boites):
        _remplir(fenetre, _csv(tmp_path), simulation=False)
        fenetre.bouton_lancer.invoke()
        assert _tourner(fenetre, lambda: not fenetre.lot_en_cours)
        assert boites.titres_des_questions == ["Écrire sur le firewall"]
        assert boitier.utilisateurs == []
        assert _etat(fenetre.bouton_enregistrer) == "disabled"


def test_arreter_accuse_reception_du_geste_et_pose_la_demande(tmp_path: Path) -> None:
    """Le clic répond tout de suite dans le journal, sans rien attendre du fil."""
    boitier = BoitierMemoire(groupes=["profs"])
    feu_vert = _retenir(boitier, "lister_utilisateurs")
    with _fenetre_ouverte(boitier=boitier) as (fenetre, _):
        _remplir(fenetre, _csv(tmp_path))
        fenetre.bouton_lancer.invoke()
        fenetre.bouton_arreter.invoke()
        assert ARRET_DEMANDE_AU_CLIC in _journal(fenetre)
        assert fenetre.arret() is True
        # Le bouton reste actif jusqu'au bilan : un second clic repose une demande déjà
        # posée, ce qui ne change rien.
        assert _etat(fenetre.bouton_arreter) == "normal"
        feu_vert.set()
        assert _tourner(fenetre, lambda: not fenetre.lot_en_cours)
        assert "arrêt demandé" in _journal(fenetre).lower()


# --- la pompe --------------------------------------------------------------


def test_la_pompe_ramene_dans_la_fenetre_ce_que_le_fil_a_publie() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        file: queue.Queue[MessageFil] = queue.Queue()
        file.put(Journal("venu du fil"))
        fenetre._pomper(file, fenetre._appliquer)
        assert "venu du fil" in _journal(fenetre)


def test_la_pompe_se_replanifie_et_delivre_ce_qui_arrive_apres_son_tour() -> None:
    """Sans la replanification par `after`, un message publié après un tour à vide ne
    serait jamais délivré : barre et journal gelés pendant que le fil écrit."""
    with _fenetre_ouverte() as (fenetre, _):
        file: queue.Queue[MessageFil] = queue.Queue()
        fenetre._pomper(file, fenetre._appliquer)
        assert _journal(fenetre).strip() == ""
        file.put(Journal("arrivé plus tard"))
        assert _tourner(fenetre, lambda: "arrivé plus tard" in _journal(fenetre))


def test_la_pompe_survit_a_une_application_qui_leve_et_n_ouvre_qu_une_boite() -> None:
    """Une exception dans l'application d'un message ne doit ni arrêter la pompe, ni
    disparaître, ni empiler une boîte par message : le journal reçoit tout, la boîte
    ne s'ouvre qu'une fois par lot, et le message suivant s'applique quand même."""
    with _fenetre_ouverte() as (fenetre, boites):
        fenetre.barre.destroy()
        file: queue.Queue[MessageFil] = queue.Queue()
        file.put(Progression(1, 3))
        file.put(Progression(2, 3))
        file.put(Journal("le suivant passe quand même"))
        fenetre._pomper(file, fenetre._appliquer)
        journal = _journal(fenetre)
        assert journal.count("anomalie interne de l'interface en traitant Progression") == 2
        assert "TclError" in journal
        assert "le suivant passe quand même" in journal
        # La boîte n'est jamais ouverte depuis l'intérieur du tour de pompe.
        assert boites.erreurs == []
        fenetre.racine.update()
        assert boites.titres_des_erreurs == ["Anomalie interne"]
        assert "TclError" in boites.erreurs[0][1]


def test_une_anomalie_ne_rend_jamais_le_bouton_lancer(tmp_path: Path) -> None:
    """L'anomalie n'arrête pas le fil, qui écrit toujours : un second lot partirait sur
    le même boîtier et viderait la liste des mots de passe du premier."""
    boitier = BoitierMemoire(groupes=["profs"])
    feu_vert = _retenir(boitier, "lister_utilisateurs")
    with _fenetre_ouverte(boitier=boitier) as (fenetre, _):
        _remplir(fenetre, _csv(tmp_path))
        fenetre.bouton_lancer.invoke()
        fenetre.barre.destroy()
        file: queue.Queue[MessageFil] = queue.Queue()
        file.put(Progression(1, 3))
        fenetre._pomper(file, fenetre._appliquer)
        assert "anomalie interne" in _journal(fenetre)
        assert fenetre.lot_en_cours is True
        assert _etat(fenetre.bouton_lancer) == "disabled"
        feu_vert.set()
        assert _tourner(fenetre, lambda: not fenetre.lot_en_cours)


def test_ce_que_tk_attrape_hors_de_la_pompe_part_au_journal() -> None:
    """Un rappel de widget qui lève passe par `report_callback_exception`, hors du
    filet de la pompe. Sa version d'origine écrit sur un `stderr` qu'un exécutable
    fenêtré n'a pas : l'opérateur ne verrait rien."""

    def rappel_qui_leve() -> None:
        raise ValueError("un rappel a lâché")

    with _fenetre_ouverte() as (fenetre, boites):
        ttk.Button(fenetre.racine, command=rappel_qui_leve).invoke()
        journal = _journal(fenetre)
        assert "anomalie interne de l'interface : ValueError : un rappel a lâché" in journal
        # Aucun « en traitant » : l'exception ne vient d'aucun message de la file.
        assert "en traitant" not in journal
        fenetre.racine.update()
        assert boites.titres_des_erreurs == ["Anomalie interne"]


def test_une_exception_tk_apres_la_destruction_de_la_fenetre_part_sur_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dernier recours : plus aucun widget n'existe pour afficher quoi que ce soit."""
    with _fenetre_ouverte() as (fenetre, _):
        fenetre.racine.destroy()
        fenetre._signaler_exception_tk(ValueError("après la fermeture"))
        assert "après la fermeture" in capsys.readouterr().err


# --- application des messages du fil --------------------------------------


def test_la_premiere_lecture_du_plancher_active_et_pre_remplit_la_politique() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        fenetre._appliquer(PolitiqueLue(PlancherPolitique(16, 4, 0)))
        assert [_etat(champ) for champ in fenetre.champs_politique] == ["normal"] * 5
        assert fenetre.var_longueur.get() == 16
        assert fenetre.var_speciaux.get() is True
        assert "16" in str(fenetre.etiquette_plancher["text"])
        assert fenetre.plancher == PlancherPolitique(16, 4, 0)


def test_une_relecture_ne_reecrit_pas_une_longueur_durcie_par_l_operateur() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        fenetre._appliquer(PolitiqueLue(PlancherPolitique(16, 4, 0)))
        fenetre.var_longueur.set(40)
        fenetre.politique = fenetre._politique_des_champs()
        fenetre._appliquer(PolitiqueLue(PlancherPolitique(16, 4, 0)))
        assert fenetre.var_longueur.get() == 40


def test_une_politique_refusee_se_dit_deux_fois_sans_reactiver_le_lancement(
    tmp_path: Path,
) -> None:
    """Non terminal : le `Termine` qui suit réactivera *Lancer*, pas ce refus."""
    boitier = BoitierMemoire(groupes=["profs"])
    feu_vert = _retenir(boitier, "lister_utilisateurs")
    with _fenetre_ouverte(boitier=boitier) as (fenetre, boites):
        _remplir(fenetre, _csv(tmp_path))
        fenetre.bouton_lancer.invoke()
        fenetre._appliquer(PolitiqueRefusee(("longueur trop courte",), PLANCHER))
        assert "longueur trop courte" in _journal(fenetre)
        assert boites.titres_des_erreurs == ["Politique refusée"]
        assert "longueur trop courte" in boites.erreurs[0][1]
        assert _etat(fenetre.bouton_lancer) == "disabled"
        feu_vert.set()
        assert _tourner(fenetre, lambda: not fenetre.lot_en_cours)


def test_le_plan_s_ecrit_dans_le_journal() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        travail = TravailCompte(utilisateur("marie", "profs"), "marie", True, ("profs",))
        fenetre._appliquer(PlanPret(_plan(travail)))
        assert "marie" in _journal(fenetre)


def test_la_demande_de_confirmation_n_ouvre_rien_dans_le_tour_de_pompe() -> None:
    """Une modale ouverte depuis l'intérieur d'un tour de pompe ferait tourner une
    boucle imbriquée, qui rappellerait ce tour dans lui-même."""
    with _fenetre_ouverte(_Boites(reponse_aux_questions=True)) as (fenetre, boites):
        demande = DemandeConfirmation(_plan(), "firewall.local")
        fenetre._appliquer(demande)
        assert boites.questions == []
        fenetre.racine.update()
        assert boites.titres_des_questions == ["Écrire sur le firewall"]
        assert demande.attendre() is True


def test_une_confirmation_refusee_repond_non_au_fil() -> None:
    with _fenetre_ouverte(_Boites(reponse_aux_questions=False)) as (fenetre, _):
        demande = DemandeConfirmation(_plan(), "firewall.local")
        fenetre._repondre_a_la_demande(demande)
        assert demande.attendre() is False


def test_une_boite_de_confirmation_qui_leve_debloque_quand_meme_le_fil() -> None:
    """Le fil est arrêté sur `attendre()` : une exception qui partirait d'ici sans
    répondre le laisserait bloqué, bouton *Lancer* grisé, jusqu'à la fermeture."""

    def question_qui_casse(titre: str, message: str, parent: tk.Misc) -> bool:
        del titre, message, parent
        raise RuntimeError("la boîte a lâché")

    fenetre = Fenetre(dialogues=Dialogues(question_grave=question_qui_casse))
    try:
        demande = DemandeConfirmation(_plan(), "firewall.local")
        with pytest.raises(RuntimeError):
            fenetre._repondre_a_la_demande(demande)
        assert demande.attendre() is False
    finally:
        fenetre.racine.destroy()


def test_la_progression_regle_la_barre_et_son_compteur() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        fenetre._appliquer(Progression(2, 5))
        assert float(fenetre.barre["maximum"]) == 5.0
        assert float(fenetre.barre["value"]) == 2.0
        assert str(fenetre.etiquette_progression["text"]) == "2 / 5"


def test_un_total_nul_ne_met_pas_la_barre_a_zero_maximum() -> None:
    """Un maximum nul ferait une barre pleine ou une division par zéro selon Tk."""
    with _fenetre_ouverte() as (fenetre, _):
        fenetre._appliquer(Progression(0, 0))
        assert float(fenetre.barre["maximum"]) == 1.0
        assert str(fenetre.etiquette_progression["text"]) == "0 / 0"


def test_le_premier_compte_cree_active_le_bouton_d_enregistrement() -> None:
    """Dès le premier compte, pas à la fin du lot : un lot de deux cents comptes
    interrompu au dixième laisserait sinon dix mots de passe inatteignables."""
    with _fenetre_ouverte() as (fenetre, _):
        fenetre._appliquer(CreationReussie(CompteCree("marie", "Secret-1234")))
        assert _etat(fenetre.bouton_enregistrer) == "normal"
        assert fenetre.enregistrables.comptes == (CompteCree("marie", "Secret-1234"),)


def test_le_bilan_fixe_la_liste_et_reactive_le_lancement() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        fenetre.lot_en_cours = True
        fenetre._appliquer(CreationReussie(CompteCree("marie", "Secret-1234")))
        rapport = Rapport(comptes_crees=[CompteCree("marie", "Secret-5678")], comptes_prevus=1)
        fenetre._appliquer(Termine(rapport))
        # Le rapport fait foi sur ce que le CSV portera.
        assert fenetre.enregistrables.comptes == (CompteCree("marie", "Secret-5678"),)
        assert _etat(fenetre.bouton_enregistrer) == "normal"
        assert fenetre.lot_en_cours is False
        assert _etat(fenetre.bouton_lancer) == "normal"
        assert _etat(fenetre.bouton_arreter) == "disabled"


def test_un_bilan_sans_creation_laisse_le_bouton_d_enregistrement_grise() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        fenetre._appliquer(Termine(Rapport()))
        assert _etat(fenetre.bouton_enregistrer) == "disabled"


def test_un_echec_se_dit_dans_le_journal_et_dans_une_boite() -> None:
    with _fenetre_ouverte() as (fenetre, boites):
        fenetre.lot_en_cours = True
        fenetre._appliquer(Echoue("la liaison est tombée"))
        assert "la liaison est tombée" in _journal(fenetre)
        assert boites.titres_des_erreurs == ["Arrêt"]
        assert fenetre.lot_en_cours is False


def test_un_message_inconnu_laisse_une_trace_au_lieu_de_disparaitre() -> None:
    """`AnnuaireCree` ne circule que sur la file du dialogue de création : sur celle du
    lot, c'est une anomalie."""
    with _fenetre_ouverte() as (fenetre, _):
        fenetre._appliquer(AnnuaireCree("interne.local"))
        assert "AnnuaireCree" in _journal(fenetre)


# --- enregistrement des mots de passe -------------------------------------


def test_sans_aucun_compte_le_bouton_le_dit_et_n_ouvre_pas_de_selecteur() -> None:
    with _fenetre_ouverte() as (fenetre, boites):
        fenetre._enregistrer_mots_de_passe()
        assert [titre for titre, _, _ in boites.informations] == ["Rien à enregistrer"]
        assert boites.selections_a_ecrire == 0


def test_renoncer_au_selecteur_n_ecrit_rien_et_ne_solde_rien() -> None:
    with _fenetre_ouverte(_Boites(chemin_a_ecrire="")) as (fenetre, boites):
        fenetre._appliquer(CreationReussie(CompteCree("marie", "Secret-1234")))
        fenetre._enregistrer_mots_de_passe()
        assert boites.selections_a_ecrire == 1
        assert fenetre.enregistrables.secrets_en_attente == 1
        assert _journal(fenetre).strip() == ""


def test_une_ecriture_impossible_se_dit_et_ne_solde_rien(tmp_path: Path) -> None:
    """Le chemin désigne un dossier qui n'existe pas : les secrets restent en attente,
    sans quoi ils seraient réputés sauvés alors que rien n'a été écrit."""
    inaccessible = tmp_path / "absent" / "mdp.csv"
    with _fenetre_ouverte(_Boites(chemin_a_ecrire=str(inaccessible))) as (fenetre, boites):
        fenetre._appliquer(CreationReussie(CompteCree("marie", "Secret-1234")))
        fenetre._enregistrer_mots_de_passe()
        assert boites.titres_des_erreurs == ["Écriture impossible"]
        assert fenetre.enregistrables.secrets_en_attente == 1


def test_un_compte_cree_apres_l_ouverture_du_selecteur_reste_en_attente(
    tmp_path: Path,
) -> None:
    """Le sélecteur fait tourner la boucle d'événements : les comptes créés pendant ce
    temps ne sont dans aucun fichier. Ici le compte arrive pendant le choix du chemin,
    comme il le ferait en vrai."""
    chemin = tmp_path / "mdp.csv"

    with _fenetre_ouverte() as (fenetre, _):

        def selecteur_qui_laisse_passer_un_compte(parent: tk.Misc) -> str:
            del parent
            fenetre._appliquer(CreationReussie(CompteCree("paul", "Secret-9999")))
            return str(chemin)

        fenetre.dialogues = Dialogues(fichier_a_ecrire=selecteur_qui_laisse_passer_un_compte)
        fenetre._appliquer(CreationReussie(CompteCree("marie", "Secret-1234")))
        fenetre._enregistrer_mots_de_passe()
        assert "marie" in chemin.read_text(encoding="utf-8-sig")
        assert "paul" not in chemin.read_text(encoding="utf-8-sig")
        assert fenetre.enregistrables.secrets_en_attente == 1


# --- dialogue de création d'annuaire --------------------------------------


def test_l_annuaire_manquant_ouvre_son_dialogue_et_rend_le_bouton_lancer() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        fenetre.lot_en_cours = True
        fenetre._appliquer(AnnuaireManquant())
        assert fenetre.lot_en_cours is False
        dialogue = _dialogue_annuaire(fenetre)
        assert dialogue.title() == "Créer l'annuaire LDAP interne"
        assert len(_saisies(dialogue)) == 4
        assert str(_bouton_du_dialogue(dialogue)["text"]) == "Créer l'annuaire"


def test_le_secret_du_dialogue_est_masque_a_la_saisie() -> None:
    with _fenetre_ouverte() as (fenetre, _):
        fenetre._appliquer(AnnuaireManquant())
        masques = [str(champ["show"]) for champ in _saisies(_dialogue_annuaire(fenetre))]
        assert masques == ["", "", "", "•"]


def test_un_champ_manquant_du_dialogue_les_nomme_tous_sans_rien_envoyer() -> None:
    boitier = BoitierMemoire(annuaires=())
    with _fenetre_ouverte(boitier=boitier) as (fenetre, boites):
        fenetre._appliquer(AnnuaireManquant())
        dialogue = _dialogue_annuaire(fenetre)
        _saisies(dialogue)[0].insert(0, "interne.local")
        _bouton_du_dialogue(dialogue).invoke()
        assert boites.titres_des_erreurs == ["Champ manquant"]
        assert boites.erreurs[0][1] == "À renseigner : o, dc, mot de passe de cn=StormshieldAdmin"
        # La boîte se pose sur le dialogue, pas derrière lui.
        assert boites.erreurs[0][2] is dialogue
        assert boitier.journal_appels == []
        assert fenetre.creation_annuaire_en_cours is False


def test_la_creation_de_l_annuaire_part_dans_un_fil_et_oublie_le_secret_aussitot() -> None:
    """Le secret est parti avec les paramètres du fil : il n'a plus rien à faire dans
    l'interpréteur Tcl, où il resterait tout le reste de la session."""
    boitier = BoitierMemoire(annuaires=())
    feu_vert = _retenir(boitier, "initialiser_annuaire")
    with _fenetre_ouverte(boitier=boitier) as (fenetre, boites):
        fenetre._appliquer(AnnuaireManquant())
        dialogue = _dialogue_annuaire(fenetre)
        _saisir_l_annuaire(dialogue)
        _bouton_du_dialogue(dialogue).invoke()
        restant = [champ.get() for champ in _saisies(dialogue)]
        assert restant == ["interne.local", "Ecole", "dc=interne,dc=local", ""]
        assert fenetre.creation_annuaire_en_cours is True
        assert _etat(_bouton_du_dialogue(dialogue)) == "disabled"
        feu_vert.set()
        assert _tourner(fenetre, lambda: not fenetre.creation_annuaire_en_cours)
        assert boitier.annuaires == ["interne.local"]
        assert "annuaire interne.local créé et activé" in _journal(fenetre)
        assert "création de l'annuaire interne.local en cours" in _journal(fenetre)
        assert [titre for titre, _, _ in boites.informations] == ["Annuaire créé"]
        assert not dialogue.winfo_exists()


def test_un_refus_de_creation_reactive_le_bouton_et_se_dit_sur_le_dialogue() -> None:
    """Un annuaire apparu entre-temps : `creer_annuaire` revérifie lui-même, et le
    dialogue doit redevenir utilisable."""
    boitier = BoitierMemoire(annuaires=("deja.local",))
    with _fenetre_ouverte(boitier=boitier) as (fenetre, boites):
        fenetre._appliquer(AnnuaireManquant())
        dialogue = _dialogue_annuaire(fenetre)
        _saisir_l_annuaire(dialogue)
        _bouton_du_dialogue(dialogue).invoke()
        assert _tourner(fenetre, lambda: not fenetre.creation_annuaire_en_cours)
        assert boites.titres_des_erreurs == ["Création refusée"]
        assert boites.erreurs[0][2] is dialogue
        assert _etat(_bouton_du_dialogue(dialogue)) == "normal"
        assert dialogue.winfo_exists()
        assert boitier.annuaires == ["deja.local"]


def test_un_refus_arrive_apres_la_disparition_du_dialogue_se_dit_sur_la_fenetre() -> None:
    """Le refus ne doit pas se perdre avec le dialogue : la pompe est planifiée sur la
    fenêtre principale et lui survit.

    Le fil est retenu sur la relecture des annuaires — celle par laquelle
    `creer_annuaire` se protège lui-même — le temps que le dialogue disparaisse : sans
    ce frein, le refus serait délivré avant, et c'est l'autre branche qui serait éprouvée.
    """
    boitier = BoitierMemoire(annuaires=("deja.local",))
    feu_vert = _retenir(boitier, "lister_annuaires")
    with _fenetre_ouverte(boitier=boitier) as (fenetre, boites):
        fenetre._appliquer(AnnuaireManquant())
        dialogue = _dialogue_annuaire(fenetre)
        _saisir_l_annuaire(dialogue)
        _bouton_du_dialogue(dialogue).invoke()
        dialogue.destroy()
        feu_vert.set()
        assert _tourner(fenetre, lambda: not fenetre.creation_annuaire_en_cours)
        assert boites.titres_des_erreurs == ["Création refusée"]
        assert boites.erreurs[0][2] is fenetre.racine


def test_un_message_terminal_inconnu_deverrouille_quand_meme_le_dialogue() -> None:
    """Sans cela la pompe s'arrêterait sur ce message, et le dialogue comme la fenêtre
    resteraient verrouillés pour toujours."""
    boitier = BoitierMemoire(annuaires=())

    def annuaire_absent(operation: str, cible: str) -> None:
        del cible
        if operation == "connecter":
            raise AnnuaireAbsent("aucun annuaire")

    boitier.declencheur = annuaire_absent
    with _fenetre_ouverte(boitier=boitier) as (fenetre, _):
        fenetre._appliquer(AnnuaireManquant())
        dialogue = _dialogue_annuaire(fenetre)
        _saisir_l_annuaire(dialogue)
        _bouton_du_dialogue(dialogue).invoke()
        assert _tourner(fenetre, lambda: not fenetre.creation_annuaire_en_cours)
        assert "AnnuaireManquant" in _journal(fenetre)


def test_fermer_le_dialogue_pendant_la_creation_est_refuse() -> None:
    """`CONFIG LDAP INITIALIZE` est déjà parti sur le boîtier et ne s'annule pas."""
    with _fenetre_ouverte() as (fenetre, boites):
        fenetre._appliquer(AnnuaireManquant())
        dialogue = _dialogue_annuaire(fenetre)
        fenetre.creation_annuaire_en_cours = True
        _fermer_comme_le_gestionnaire(dialogue)
        assert [titre for titre, _, _ in boites.avertissements] == ["Création en cours"]
        assert boites.avertissements[0][1] == FERMETURE_PENDANT_CREATION
        assert dialogue.winfo_exists()


def test_fermer_le_dialogue_hors_creation_l_efface_avec_ses_saisies() -> None:
    with _fenetre_ouverte() as (fenetre, boites):
        fenetre._appliquer(AnnuaireManquant())
        dialogue = _dialogue_annuaire(fenetre)
        _saisies(dialogue)[3].insert(0, "Secret-Admin-1234")
        _fermer_comme_le_gestionnaire(dialogue)
        assert boites.avertissements == []
        assert not dialogue.winfo_exists()


# --- fermeture de la fenêtre ----------------------------------------------


def test_fermer_sans_rien_a_perdre_ne_demande_rien() -> None:
    with _fenetre_ouverte() as (fenetre, boites):
        fenetre._a_la_fermeture()
        assert boites.questions == []
        with pytest.raises(tk.TclError):
            fenetre.racine.winfo_exists()


def test_fermer_pendant_une_creation_d_annuaire_demande_confirmation() -> None:
    with _fenetre_ouverte(_Boites(reponse_aux_questions=True)) as (fenetre, boites):
        fenetre.creation_annuaire_en_cours = True
        fenetre._a_la_fermeture()
        assert boites.titres_des_questions == ["Fermer la fenêtre"]
        assert "CONFIG LDAP INITIALIZE" in boites.questions[0][1]


def test_lancer_intercepte_la_fermeture_et_un_refus_garde_la_fenetre() -> None:
    """La fenêtre entre dans `mainloop` pour de vrai ; sans cette interception la
    boucle rendait la main sans un mot et les mots de passe déjà générés partaient
    avec le processus.

    Le geste est celui du gestionnaire de fenêtres : la commande Tcl enregistrée pour
    `WM_DELETE_WINDOW`, appelée depuis un `after` — rien d'autre ne peut agir pendant
    que `mainloop` tourne.
    """
    boites = _Boites(reponse_aux_questions=False)
    fenetre = Fenetre(dialogues=boites.dialogues())
    fenetre._appliquer(CreationReussie(CompteCree("marie", "Secret-1234")))
    survivances: list[bool] = []

    def cliquer_sur_la_croix() -> None:
        _fermer_comme_le_gestionnaire(fenetre.racine)
        survivances.append(bool(fenetre.racine.winfo_exists()))
        boites.reponse_aux_questions = True
        _fermer_comme_le_gestionnaire(fenetre.racine)

    fenetre.racine.after(0, cliquer_sur_la_croix)
    fenetre.lancer()
    assert survivances == [True]
    assert boites.titres_des_questions == ["Fermer la fenêtre", "Fermer la fenêtre"]
    assert "1 mot de passe" in boites.questions[0][1]
