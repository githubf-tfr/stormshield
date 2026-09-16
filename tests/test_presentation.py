"""Logique de présentation, testée sans widget.

`tkinter` peut être absent de la machine de test comme du runner d'intégration
continue : aucun test n'importe `stormshield_utilisateurs.fenetre`, qui est le seul
module du paquet à importer `tkinter`. Tout ce qui est vérifiable l'est ici ; la
fenêtre elle-même relève du cahier de recette.
"""

import ast
import queue
from collections.abc import Callable
from pathlib import Path

import pytest
from fabriques import utilisateur

from stormshield_utilisateurs import presentation
from stormshield_utilisateurs.boitier import ErreurCommande, ErreurFatale, ErreurReseau
from stormshield_utilisateurs.boitier_memoire import BoitierMemoire
from stormshield_utilisateurs.execution import (
    AnnuaireAbsent,
    AnnuaireDejaPresent,
    AnnuairesMultiples,
    CreationReussie,
    Echoue,
    Journal,
    PlanPret,
    PolitiqueLue,
    Progression,
    Termine,
)
from stormshield_utilisateurs.modele import (
    CompteCree,
    Echec,
    GroupeACreer,
    Plan,
    PlancherPolitique,
    PolitiqueMotDePasse,
    Rapport,
    Rejet,
)
from stormshield_utilisateurs.presentation import (
    AnnuaireCree,
    AnnuaireManquant,
    ComptesEnregistrables,
    Connexion,
    MessageFil,
    Parametres,
    ParametresAnnuaire,
    PompeEvenements,
    est_terminal,
    libelle_plancher,
    lignes_du_fichier,
    lignes_du_plan,
    lignes_du_rapport,
    message_de_fil,
    obstacles_au_lancement,
    politique_a_afficher,
    reglage_barre,
    travailler,
    travailler_annuaire,
)

PLANCHER = PlancherPolitique(longueur_min=12, nombre_classes_min=3, entropie_min=0)
DURCIE = PolitiqueMotDePasse(
    longueur=32, minuscules=True, majuscules=True, chiffres=True, speciaux=True
)


def connexion(
    hote: str = "firewall.local",
    compte: str = "admin",
    mot_de_passe: str = "secret",
    verifier_certificat: bool = True,
) -> Connexion:
    return Connexion(
        hote=hote,
        compte=compte,
        mot_de_passe=mot_de_passe,
        verifier_certificat=verifier_certificat,
    )


def parametres(
    hote: str = "firewall.local",
    compte: str = "admin",
    mot_de_passe: str = "secret",
    fichier: Path = Path("entree.csv"),
    simulation: bool = True,
    politique: PolitiqueMotDePasse = DURCIE,
) -> Parametres:
    """Paramètres complets et valides ; chaque test n'altère que ce qui l'intéresse."""
    return Parametres(
        connexion=connexion(hote=hote, compte=compte, mot_de_passe=mot_de_passe),
        fichier=fichier,
        simulation=simulation,
        politique=politique,
    )


# --- politique affichée ---------------------------------------------------


def test_premiere_lecture_pre_remplit_la_politique() -> None:
    politique = politique_a_afficher(None, PLANCHER)
    assert politique.longueur >= PLANCHER.longueur_min
    assert politique.nombre_classes() >= PLANCHER.nombre_classes_min


def test_relecture_ne_reecrit_jamais_un_reglage_durci() -> None:
    """Un réglage effacé par un rafraîchissement silencieux serait pire que pas de
    rafraîchissement du tout."""
    assert politique_a_afficher(DURCIE, PLANCHER) is DURCIE
    assert politique_a_afficher(DURCIE, PlancherPolitique(20, 4, 0)) is DURCIE


def test_le_libelle_du_plancher_nomme_les_trois_reglages_du_boitier() -> None:
    assert libelle_plancher(PlancherPolitique(12, 3, 100)) == (
        "politique du boîtier : MinLength=12, MinSet=3, MinEntropy=100"
    )


# --- pompe d'événements ---------------------------------------------------


def test_la_pompe_vide_la_file_et_se_replanifie() -> None:
    file: queue.Queue[MessageFil] = queue.Queue()
    file.put(Journal("bonjour"))
    file.put(Progression(1, 4))
    recus: list[MessageFil] = []
    replanifications: list[int] = []

    def planifier(delai_ms: int, _rappel: Callable[[], None]) -> None:
        replanifications.append(delai_ms)

    pompe = PompeEvenements(file, recus.append, planifier, periode_ms=100)
    pompe.tour()
    assert recus == [Journal("bonjour"), Progression(1, 4)]
    assert replanifications == [100]
    assert pompe.active is True


def test_la_pompe_s_arrete_sur_un_message_terminal() -> None:
    file: queue.Queue[MessageFil] = queue.Queue()
    file.put(Termine(Rapport()))
    recus: list[MessageFil] = []
    replanifications: list[int] = []
    pompe = PompeEvenements(
        file, recus.append, lambda delai, _rappel: replanifications.append(delai)
    )
    pompe.tour()
    assert isinstance(recus[0], Termine)
    assert pompe.active is False
    assert replanifications == []


def test_la_pompe_sur_file_vide_se_replanifie_sans_rien_appliquer() -> None:
    file: queue.Queue[MessageFil] = queue.Queue()
    recus: list[MessageFil] = []
    replanifications: list[int] = []
    pompe = PompeEvenements(
        file, recus.append, lambda delai, _rappel: replanifications.append(delai)
    )
    pompe.tour()
    assert recus == []
    assert replanifications == [100]


def test_la_pompe_applique_le_reste_de_la_file_avant_de_s_arreter() -> None:
    """Un message terminal n'autorise pas à jeter ce qui le précède dans la file."""
    file: queue.Queue[MessageFil] = queue.Queue()
    file.put(Journal("avant"))
    file.put(Echoue("arrêt"))
    recus: list[MessageFil] = []
    pompe = PompeEvenements(file, recus.append, lambda _delai, _rappel: None)
    pompe.tour()
    assert recus == [Journal("avant"), Echoue("arrêt")]
    assert pompe.active is False


@pytest.mark.parametrize(
    "message",
    [Termine(Rapport()), Echoue("x"), AnnuaireManquant(), AnnuaireCree("interne.local")],
)
def test_les_messages_terminaux_arretent_la_pompe(message: MessageFil) -> None:
    assert est_terminal(message) is True


@pytest.mark.parametrize(
    "message",
    [
        Journal("x"),
        PolitiqueLue(PLANCHER),
        Progression(1, 2),
        CreationReussie(CompteCree("a", "b")),
    ],
)
def test_les_messages_courants_laissent_la_pompe_tourner(message: MessageFil) -> None:
    assert est_terminal(message) is False


# --- barre de progression -------------------------------------------------


def test_la_barre_suit_un_total_qui_decroit() -> None:
    """Un plan reconstruit après reconnexion ne peut que réduire le total : la barre
    doit le suivre vers le bas, jamais retenir l'ancien maximum."""
    assert reglage_barre(Progression(4, 40)) == (40, 4)
    assert reglage_barre(Progression(10, 22)) == (22, 10)


def test_la_barre_ne_depasse_jamais_son_maximum() -> None:
    assert reglage_barre(Progression(9, 4)) == (4, 4)


def test_la_barre_reste_utilisable_sur_un_total_nul() -> None:
    """`ttk.Progressbar` n'accepte pas un maximum de zéro."""
    maximum, valeur = reglage_barre(Progression(0, 0))
    assert maximum >= 1
    assert valeur == 0


# --- obstacles au lancement -----------------------------------------------


def test_aucun_obstacle_quand_tout_est_renseigne() -> None:
    assert obstacles_au_lancement(parametres(), plancher=PLANCHER) == []


@pytest.mark.parametrize(
    "vides",
    [
        parametres(hote="   "),
        parametres(compte=""),
        parametres(mot_de_passe=""),
        parametres(fichier=Path()),
    ],
)
def test_un_champ_vide_bloque_le_lancement(vides: Parametres) -> None:
    assert len(obstacles_au_lancement(vides, plancher=PLANCHER)) == 1


def test_une_politique_sous_le_plancher_est_refusee_avant_tout_envoi() -> None:
    """Le message affiché est celui que `violations()` rend, mot pour mot."""
    faible = PolitiqueMotDePasse(longueur=8, speciaux=False)
    assert obstacles_au_lancement(parametres(politique=faible), plancher=PLANCHER) == [
        "longueur 8 inférieure au minimum du boîtier (12)"
    ]


def test_une_ecriture_avant_toute_lecture_du_plancher_est_refusee() -> None:
    """Sans plancher connu, « ne jamais descendre sous le plancher » n'est pas
    vérifiable : l'écriture partirait sur une politique que rien n'a validée."""
    obstacles = obstacles_au_lancement(parametres(simulation=False), plancher=None)
    assert len(obstacles) == 1
    assert "simulation" in obstacles[0]


def test_une_simulation_avant_toute_lecture_du_plancher_est_permise() -> None:
    """C'est précisément la simulation qui fait connaître le plancher."""
    assert obstacles_au_lancement(parametres(simulation=True), plancher=None) == []


# --- comptes enregistrables -----------------------------------------------


def test_le_bouton_s_active_des_la_premiere_creation() -> None:
    enregistrables = ComptesEnregistrables()
    assert not enregistrables.comptes
    enregistrables.ajouter(CompteCree("dupont", "s3cr3t"))
    assert enregistrables.comptes == (CompteCree("dupont", "s3cr3t"),)


def test_le_rapport_final_fait_foi_sur_ce_qui_sera_ecrit() -> None:
    """Le CSV ne porte que `rapport.comptes_crees`, mots de passe vides compris."""
    enregistrables = ComptesEnregistrables()
    enregistrables.ajouter(CompteCree("dupont", ""))
    enregistrables.fixer([CompteCree("dupont", "s3cr3t"), CompteCree("martin", "")])
    assert enregistrables.comptes == (
        CompteCree("dupont", "s3cr3t"),
        CompteCree("martin", ""),
    )


# --- aiguillage typé ------------------------------------------------------


def test_un_annuaire_absent_devient_une_proposition_de_creation() -> None:
    assert message_de_fil(AnnuaireAbsent("rien")) == AnnuaireManquant()


def test_des_annuaires_multiples_deviennent_un_arret_qui_les_nomme() -> None:
    message = message_de_fil(AnnuairesMultiples(("a.local", "b.local")))
    assert isinstance(message, Echoue)
    assert "a.local" in message.message
    assert "b.local" in message.message


def test_un_annuaire_apparu_entre_temps_est_dit_tel_quel() -> None:
    message = message_de_fil(AnnuaireDejaPresent(("interne.local",)))
    assert isinstance(message, Echoue)
    assert "entre-temps" in message.message


def test_toute_autre_erreur_devient_un_arret_portant_son_texte() -> None:
    message = message_de_fil(ErreurReseau("liaison coupée"))
    assert message == Echoue("liaison coupée")


# --- rendu du fichier, du plan et du rapport ------------------------------


def test_les_lignes_du_fichier_comptent_les_lues_et_detaillent_les_rejets() -> None:
    lignes = lignes_du_fichier(
        [utilisateur("dupont"), utilisateur("martin")],
        [Rejet(4, "jean dupont", "identifiant : caractère interdit")],
    )
    assert lignes == [
        "2 lignes lues, 1 rejet",
        "ligne 4 : jean dupont — identifiant : caractère interdit",
    ]


def test_le_pluriel_des_rejets_suit_leur_nombre() -> None:
    assert lignes_du_fichier([], [])[0] == "0 ligne lue, 0 rejet"
    assert lignes_du_fichier([utilisateur("a")], [Rejet(2, "b", "x"), Rejet(3, "c", "y")])[
        0
    ] == "1 ligne lue, 2 rejets"


def test_le_plan_annonce_groupes_comptes_ignores_et_orphelins() -> None:
    plan = Plan(
        comptes_a_creer=(utilisateur("dupont", "compta_bis"),),
        comptes_ignores=(utilisateur("legrand"),),
        groupes_a_creer=(GroupeACreer("compta_bis", 1),),
        orphelins=("martin",),
        domaine="interne.local",
    )
    assert lignes_du_plan(plan) == [
        "Groupes à créer : compta_bis (1 membre)",
        "dupont : à créer, rattaché à compta_bis",
        "legrand : déjà présent, ignoré",
        "Orphelins sur le boîtier : martin",
    ]


def test_l_accord_de_membre_suit_le_nombre_de_membres() -> None:
    plan = Plan(
        comptes_a_creer=(),
        comptes_ignores=(),
        groupes_a_creer=(GroupeACreer("rh", 3), GroupeACreer("compta", 1)),
        orphelins=(),
        domaine="interne.local",
    )
    assert lignes_du_plan(plan) == ["Groupes à créer : rh (3 membres), compta (1 membre)"]


def test_un_plan_sans_groupe_ni_orphelin_n_annonce_ni_l_un_ni_l_autre() -> None:
    plan = Plan(
        comptes_a_creer=(utilisateur("dupont"),),
        comptes_ignores=(),
        groupes_a_creer=(),
        orphelins=(),
        domaine="interne.local",
    )
    assert lignes_du_plan(plan) == ["dupont : à créer"]


def test_le_rapport_resume_puis_detaille_les_echecs() -> None:
    rapport = Rapport(
        comptes_crees=[CompteCree("dupont", "s3cr3t")],
        echecs=[Echec("martin", "USER CREATE", "refusé")],
        groupes_crees=["compta"],
    )
    assert lignes_du_rapport(rapport) == [
        "Terminé : 1 compte créé, 1 groupe créé, 1 échec.",
        "martin — USER CREATE : refusé",
    ]


def test_un_lot_interrompu_le_dit_dans_son_rapport() -> None:
    """La barre gèle sous son total sans rien prouver : seul `interrompu` fait foi."""
    rapport = Rapport(interrompu=True)
    assert lignes_du_rapport(rapport)[0].startswith("Lot interrompu")
    assert "journal" in lignes_du_rapport(rapport)[0]


def test_les_comptes_sans_mot_de_passe_ont_leur_section_a_part() -> None:
    rapport = Rapport(
        comptes_crees=[CompteCree("dupont", "s3cr3t"), CompteCree("martin", "")],
        echecs=[Echec("martin", "USER PASSWORD", "refusé")],
    )
    lignes = lignes_du_rapport(rapport)
    assert "Comptes créés sans mot de passe — à reprendre" in lignes
    indice = lignes.index("Comptes créés sans mot de passe — à reprendre")
    assert lignes[indice + 1] == "martin"
    assert lignes.index("martin — USER PASSWORD : refusé") < indice


def test_un_rapport_sans_compte_sans_mot_de_passe_n_ouvre_pas_la_section() -> None:
    rapport = Rapport(comptes_crees=[CompteCree("dupont", "s3cr3t")])
    assert not any("sans mot de passe" in ligne for ligne in lignes_du_rapport(rapport))


# --- fil d'exécution ------------------------------------------------------


def collecter() -> tuple[list[MessageFil], Callable[[MessageFil], None]]:
    messages: list[MessageFil] = []
    return messages, messages.append


def test_une_simulation_lit_le_boitier_et_n_y_ecrit_rien() -> None:
    boitier = BoitierMemoire()
    messages, publier = collecter()
    travailler(
        parametres(), [utilisateur("dupont")], publier, fabriquer_boitier=lambda _: boitier
    )
    types = [type(message) for message in messages]
    assert PolitiqueLue in types
    assert PlanPret in types
    assert isinstance(messages[-1], Termine)
    assert boitier.utilisateurs == []


def test_une_execution_reelle_cree_les_comptes() -> None:
    boitier = BoitierMemoire()
    messages, publier = collecter()
    travailler(
        parametres(simulation=False),
        [utilisateur("dupont")],
        publier,
        fabriquer_boitier=lambda _: boitier,
    )
    assert boitier.utilisateurs == ["dupont"]
    assert any(isinstance(message, CreationReussie) for message in messages)


def test_un_annuaire_absent_remonte_au_fil_sans_bilan_final() -> None:
    boitier = BoitierMemoire(annuaires=())
    messages, publier = collecter()
    travailler(parametres(), [utilisateur("dupont")], publier, fabriquer_boitier=lambda _: boitier)
    assert messages[-1] == AnnuaireManquant()
    assert not any(isinstance(message, Termine) for message in messages)


def test_des_annuaires_multiples_arretent_le_fil() -> None:
    boitier = BoitierMemoire(annuaires=("a.local", "b.local"))
    messages, publier = collecter()
    travailler(parametres(), [utilisateur("dupont")], publier, fabriquer_boitier=lambda _: boitier)
    dernier = messages[-1]
    assert isinstance(dernier, Echoue)
    assert "a.local" in dernier.message


def test_une_connexion_qui_tombe_remonte_un_arret_et_non_une_exception() -> None:
    """Une exception qui traverserait le fil disparaîtrait sans laisser de trace à
    l'écran : le fil n'a pas d'appelant pour la rattraper."""
    boitier = BoitierMemoire()

    def couper(operation: str, _cible: str) -> None:
        if operation == "connecter":
            raise ErreurReseau("boîtier injoignable")

    boitier.declencheur = couper
    messages, publier = collecter()
    travailler(parametres(), [utilisateur("dupont")], publier, fabriquer_boitier=lambda _: boitier)
    assert messages[-1] == Echoue("boîtier injoignable")


def test_un_arret_fatal_rend_un_rapport_interrompu() -> None:
    """`executer` intercepte `ErreurFatale` : le fil reçoit un `Termine` normal, et
    c'est `interrompu` — jamais la barre — qui dit que le lot n'est pas allé au bout."""
    boitier = BoitierMemoire()

    def refuser(operation: str, _cible: str) -> None:
        if operation == "connecter":
            raise ErreurFatale("mot de passe administrateur refusé")

    boitier.declencheur = refuser
    messages, publier = collecter()
    travailler(parametres(), [utilisateur("dupont")], publier, fabriquer_boitier=lambda _: boitier)
    dernier = messages[-1]
    assert isinstance(dernier, Termine)
    assert dernier.rapport.interrompu is True


def test_le_fil_transmet_la_politique_choisie_par_l_operateur() -> None:
    boitier = BoitierMemoire()
    _messages, publier = collecter()
    travailler(
        parametres(simulation=False, politique=PolitiqueMotDePasse(longueur=24)),
        [utilisateur("dupont")],
        publier,
        fabriquer_boitier=lambda _: boitier,
    )
    assert len(boitier.mots_de_passe["dupont"]) == 24


# --- fil de création d'annuaire -------------------------------------------


def test_la_creation_d_annuaire_ouvre_sa_propre_connexion() -> None:
    """`executer` a déjà déconnecté le boîtier dans son `finally`."""
    boitier = BoitierMemoire(annuaires=())
    messages, publier = collecter()
    travailler_annuaire(
        connexion(),
        ParametresAnnuaire("interne.local", "Societe", "dc=interne,dc=local", "secret"),
        publier,
        fabriquer_boitier=lambda _: boitier,
    )
    assert messages[-1] == AnnuaireCree("interne.local")
    assert boitier.annuaires == ["interne.local"]
    assert boitier.connexions == 1
    assert boitier.connecte is False


def test_un_annuaire_apparu_entre_temps_annule_la_creation() -> None:
    boitier = BoitierMemoire(annuaires=("interne.local",))
    messages, publier = collecter()
    travailler_annuaire(
        connexion(),
        ParametresAnnuaire("autre.local", "Societe", "dc=autre,dc=local", "secret"),
        publier,
        fabriquer_boitier=lambda _: boitier,
    )
    dernier = messages[-1]
    assert isinstance(dernier, Echoue)
    assert "entre-temps" in dernier.message
    assert boitier.annuaires == ["interne.local"]


def test_une_creation_d_annuaire_refusee_remonte_le_refus() -> None:
    boitier = BoitierMemoire(annuaires=())

    def refuser(operation: str, _cible: str) -> None:
        if operation == "initialiser_annuaire":
            raise ErreurCommande(200, "paramètre invalide")

    boitier.declencheur = refuser
    messages, publier = collecter()
    travailler_annuaire(
        connexion(),
        ParametresAnnuaire("interne.local", "Societe", "dc=interne,dc=local", "secret"),
        publier,
        fabriquer_boitier=lambda _: boitier,
    )
    dernier = messages[-1]
    assert isinstance(dernier, Echoue)
    assert "paramètre invalide" in dernier.message
    assert boitier.connecte is False


# --- aucun secret ne s'échappe --------------------------------------------


def test_le_module_de_presentation_n_importe_pas_tkinter() -> None:
    """Garde-fou : la logique testable doit rester importable là où `tkinter` est absent.

    Le jour où un raccourci ferait remonter un widget ici, toute la suite deviendrait
    incollectable sur le runner d'intégration continue — ce test le dit avant.
    """
    arbre = ast.parse(Path(presentation.__file__).read_text(encoding="utf-8"))
    importes: list[str] = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            importes.extend(alias.name for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module is not None:
            importes.append(noeud.module)
    assert [nom for nom in importes if nom.partition(".")[0] == "tkinter"] == []
