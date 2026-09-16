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
    PolitiqueRefusee,
    Progression,
    Termine,
)
from stormshield_utilisateurs.modele import (
    CompteCree,
    Echec,
    GroupeACreer,
    MotifArret,
    Plan,
    PlancherPolitique,
    PolitiqueMotDePasse,
    Rapport,
    Rejet,
)
from stormshield_utilisateurs.presentation import (
    AnnuaireCree,
    AnnuaireManquant,
    BoiteParLot,
    ComptesEnregistrables,
    Connexion,
    DemandeConfirmation,
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
    message_de_fil,
    obstacles_au_lancement,
    politique_a_afficher,
    reglage_barre,
    resume_de_l_incident,
    texte_de_confirmation_du_lot,
    texte_de_demarrage_impossible,
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


class BancDEssai:
    """Une pompe et tout ce qu'elle a produit, sans le moindre widget."""

    def __init__(self, *messages: MessageFil, appliquer: Publieur | None = None) -> None:
        self.file: queue.Queue[MessageFil] = queue.Queue()
        for message in messages:
            self.file.put(message)
        self.recus: list[MessageFil] = []
        self.replanifications: list[int] = []
        self.incidents: list[IncidentInterface] = []
        self.pompe = PompeEvenements(
            self.file,
            appliquer if appliquer is not None else self.recus.append,
            lambda delai, _rappel: self.replanifications.append(delai),
            self.incidents.append,
        )


def test_la_pompe_vide_la_file_et_se_replanifie() -> None:
    banc = BancDEssai(Journal("bonjour"), Progression(1, 4))
    banc.pompe.tour()
    assert banc.recus == [Journal("bonjour"), Progression(1, 4)]
    assert banc.replanifications == [100]
    assert banc.pompe.active is True


def test_la_pompe_sur_file_vide_se_replanifie_sans_rien_appliquer() -> None:
    banc = BancDEssai()
    banc.pompe.tour()
    assert banc.recus == []
    assert banc.replanifications == [100]


def test_la_pompe_applique_le_reste_de_la_file_avant_de_s_arreter() -> None:
    """Un message terminal n'autorise pas à jeter ce qui le précède dans la file."""
    banc = BancDEssai(Journal("avant"), Echoue("arrêt"))
    banc.pompe.tour()
    assert banc.recus == [Journal("avant"), Echoue("arrêt")]
    assert banc.pompe.active is False


@pytest.mark.parametrize(
    "message",
    [Termine(Rapport()), Echoue("x"), AnnuaireManquant(), AnnuaireCree("interne.local")],
)
def test_la_pompe_s_arrete_sur_chaque_message_terminal(message: MessageFil) -> None:
    banc = BancDEssai(message)
    banc.pompe.tour()
    assert banc.recus == [message]
    assert banc.pompe.active is False
    assert banc.replanifications == []


@pytest.mark.parametrize(
    "message",
    [
        Journal("x"),
        PolitiqueLue(PLANCHER),
        PolitiqueRefusee(("trop court",), PLANCHER),
        Progression(1, 2),
        CreationReussie(CompteCree("a", "b")),
    ],
)
def test_la_pompe_continue_apres_chaque_message_courant(message: MessageFil) -> None:
    """`PolitiqueRefusee` en fait partie : un `Termine` suit toujours, et c'est lui qui
    réactive le bouton *Lancer*."""
    banc = BancDEssai(message)
    banc.pompe.tour()
    assert banc.pompe.active is True
    assert banc.replanifications == [100]


# --- la pompe survit à ce qui lève ----------------------------------------


def test_une_exception_dans_l_application_ne_tue_pas_la_pompe() -> None:
    """Sans replanification, la file n'est plus vidée : barre et journal gèlent, le
    bouton *Lancer* reste grisé, et le fil continue d'écrire sur le firewall."""
    recus: list[MessageFil] = []

    def appliquer(message: MessageFil) -> None:
        if isinstance(message, Progression):
            raise ValueError("widget détruit")
        recus.append(message)

    banc = BancDEssai(Progression(1, 4), Journal("après"), appliquer=appliquer)
    banc.pompe.tour()
    assert recus == [Journal("après")]
    assert banc.replanifications == [100]
    assert banc.pompe.active is True


def test_une_exception_dans_l_application_est_signalee_avec_son_message() -> None:
    def appliquer(_message: MessageFil) -> None:
        raise ValueError("widget détruit")

    banc = BancDEssai(Progression(1, 4), appliquer=appliquer)
    banc.pompe.tour()
    assert len(banc.incidents) == 1
    assert isinstance(banc.incidents[0].erreur, ValueError)
    assert banc.incidents[0].message == Progression(1, 4)


def test_un_message_terminal_qui_leve_arrete_quand_meme_la_pompe() -> None:
    """Sans cela la pompe tournerait sans fin sur une file que plus rien n'alimente."""

    def appliquer(_message: MessageFil) -> None:
        raise ValueError("widget détruit")

    banc = BancDEssai(Termine(Rapport()), appliquer=appliquer)
    banc.pompe.tour()
    assert banc.pompe.active is False
    assert len(banc.incidents) == 1


def test_un_signalement_qui_leve_ne_tue_pas_la_pompe_non_plus() -> None:
    """Dernier filet : s'il lâche, la pompe doit malgré tout se replanifier."""
    file: queue.Queue[MessageFil] = queue.Queue()
    file.put(Journal("x"))
    replanifications: list[int] = []

    def exploser(*_arguments: object) -> None:
        raise ValueError("journal détruit")

    pompe = PompeEvenements(
        file,
        exploser,
        lambda delai, _rappel: replanifications.append(delai),
        exploser,
    )
    pompe.tour()
    assert replanifications == [100]
    assert pompe.active is True


def test_les_lignes_de_l_incident_nomment_le_message_et_portent_la_trace() -> None:
    """Le produit n'a aucun fichier de journal, et un .exe fenêtré n'a pas de stderr :
    ce que Tk y écrirait n'existerait nulle part."""
    try:
        raise ValueError("widget détruit")
    except ValueError as erreur:
        incident = IncidentInterface(erreur, Progression(1, 4))
    lignes = lignes_de_l_incident(incident)
    assert "Progression" in lignes[0]
    assert "ValueError" in lignes[0]
    assert "widget détruit" in lignes[0]
    assert any("Traceback" in ligne for ligne in lignes[1:])


def test_un_incident_sans_message_ne_nomme_aucun_message() -> None:
    """Le gestionnaire global de Tk attrape ce qui remonte d'un callback de widget :
    il n'y a alors aucun message de la file en cause."""
    lignes = lignes_de_l_incident(IncidentInterface(ValueError("bing")))
    assert "en traitant" not in lignes[0]
    assert "ValueError" in lignes[0]


def test_le_resume_de_l_incident_dit_que_le_lot_continue() -> None:
    resume = resume_de_l_incident(IncidentInterface(ValueError("bing")))
    assert "bing" in resume
    assert "journal" in resume


def test_le_resume_de_l_incident_dit_que_lancer_reste_grise() -> None:
    """Le fil écrit toujours : rendre le bouton laisserait partir un second lot sur le
    même boîtier, et son démarrage viderait la liste des mots de passe du premier."""
    resume = resume_de_l_incident(IncidentInterface(ValueError("bing")))
    assert "Lancer" in resume


def test_le_resume_de_l_incident_dit_ou_iront_les_anomalies_suivantes() -> None:
    """Une seule boîte par lot : l'opérateur doit savoir que le reste est au journal."""
    assert "journal" in resume_de_l_incident(IncidentInterface(ValueError("bing"))).split(
        "suivantes"
    )[-1]


def test_la_premiere_anomalie_du_lot_ouvre_une_boite() -> None:
    boite = BoiteParLot()
    assert boite.doit_ouvrir() is True


def test_les_anomalies_suivantes_du_lot_ne_vont_qu_au_journal() -> None:
    """Une boîte modale Tk fait tourner une boucle imbriquée : une panne d'affichage
    persistante en ouvrirait une par message, des centaines sur un lot de deux cents
    comptes, empilées les unes dans les autres."""
    boite = BoiteParLot()
    boite.doit_ouvrir()
    assert [boite.doit_ouvrir() for _ in range(200)] == [False] * 200


def test_un_nouveau_lot_rouvre_le_droit_a_une_boite() -> None:
    """Le silence ne vaut que pour le lot qui a déjà parlé."""
    boite = BoiteParLot()
    boite.doit_ouvrir()
    boite.reinitialiser()
    assert boite.doit_ouvrir() is True


def test_un_message_inconnu_de_la_fenetre_laisse_une_trace() -> None:
    """Un message non reconnu disparaissait sans rien dire."""
    ligne = ligne_de_message_inconnu(Progression(1, 2))
    assert "Progression" in ligne


# --- barre de progression -------------------------------------------------


def test_la_barre_prend_son_maximum_et_sa_valeur_de_la_progression() -> None:
    """La décroissance du total, elle, est une garantie du métier : le plan reconstruit
    après reconnexion ne peut que le réduire, et rien ici n'a d'état pour le vérifier."""
    assert reglage_barre(Progression(4, 40)) == (40, 4)


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


def test_un_premier_lot_reel_part_sans_simulation_prealable() -> None:
    """Le métier refuse lui-même la politique contre le plancher du boîtier visé.

    Il émet `PolitiqueRefusee` après `PolitiqueLue` et avant la moindre écriture :
    exiger une simulation préalable ici n'apporterait plus rien et imposerait deux
    lancements pour tout premier lot.
    """
    assert obstacles_au_lancement(parametres(simulation=False), plancher=None) == []


def test_une_simulation_avant_toute_lecture_du_plancher_est_permise() -> None:
    """C'est précisément la simulation qui fait connaître le plancher."""
    assert obstacles_au_lancement(parametres(simulation=True), plancher=None) == []


# --- politique refusée par le boîtier -------------------------------------


def test_la_politique_refusee_porte_les_violations_mot_pour_mot() -> None:
    """Le métier a déjà rendu ces textes : la fenêtre ne les reconstruit pas."""
    refus = PolitiqueRefusee(("longueur 8 inférieure au minimum du boîtier (12)",), PLANCHER)
    lignes = lignes_de_la_politique_refusee(refus)
    assert "longueur 8 inférieure au minimum du boîtier (12)" in lignes
    assert any("MinLength=12" in ligne for ligne in lignes)
    assert any("aucun compte" in ligne for ligne in lignes)


# --- comptes enregistrables -----------------------------------------------


def test_un_compte_ajoute_est_aussitot_enregistrable() -> None:
    """Compte par compte : sur un lot de deux cents, le premier suffit à avoir de quoi
    écrire. L'activation du bouton, elle, est dans la fenêtre — non couverte ici."""
    enregistrables = ComptesEnregistrables()
    assert not enregistrables.comptes
    enregistrables.ajouter(CompteCree("dupont", "s3cr3t"))
    assert enregistrables.comptes == (CompteCree("dupont", "s3cr3t"),)


def test_un_mot_de_passe_jamais_ecrit_reste_en_attente() -> None:
    """Ces secrets n'existent que dans la mémoire du processus : rien ne les recrée."""
    enregistrables = ComptesEnregistrables()
    assert enregistrables.secrets_en_attente == 0
    enregistrables.ajouter(CompteCree("dupont", "s3cr3t"))
    enregistrables.ajouter(CompteCree("martin", "aut3r"))
    assert enregistrables.secrets_en_attente == 2


def test_un_compte_sans_mot_de_passe_n_a_aucun_secret_a_perdre() -> None:
    enregistrables = ComptesEnregistrables()
    enregistrables.ajouter(CompteCree("dupont", ""))
    assert enregistrables.secrets_en_attente == 0


def test_l_ecriture_du_csv_solde_l_attente() -> None:
    enregistrables = ComptesEnregistrables()
    enregistrables.ajouter(CompteCree("dupont", "s3cr3t"))
    enregistrables.marquer_enregistres(enregistrables.comptes)
    assert enregistrables.secrets_en_attente == 0


def test_un_compte_cree_apres_l_ecriture_du_csv_rouvre_l_attente() -> None:
    """Le lot continue après un enregistrement en cours de route : ce qui suit n'est
    dans aucun fichier."""
    enregistrables = ComptesEnregistrables()
    enregistrables.ajouter(CompteCree("dupont", "s3cr3t"))
    enregistrables.marquer_enregistres(enregistrables.comptes)
    enregistrables.ajouter(CompteCree("martin", "aut3r"))
    assert enregistrables.secrets_en_attente == 1


def test_un_compte_arrive_pendant_le_selecteur_de_fichier_n_est_pas_dit_ecrit() -> None:
    """Tk fait tourner sa boucle d'événements pendant qu'un sélecteur de fichier est
    ouvert : c'est ainsi qu'il attend. Les comptes créés pendant ce temps ne figurent
    dans aucun fichier, et les compter comme écrits les ferait détruire sans question
    au lancement suivant.
    """
    enregistrables = ComptesEnregistrables()
    enregistrables.ajouter(CompteCree("a", "s3cr3t"))
    ecrits = enregistrables.comptes
    # Le fil continue pendant que la boîte est ouverte.
    enregistrables.ajouter(CompteCree("b", "aut3r"))
    enregistrables.marquer_enregistres(ecrits)
    assert enregistrables.secrets_en_attente == 1


def test_un_lot_relance_pendant_le_selecteur_de_fichier_ne_solde_rien() -> None:
    """La liste écrite n'est plus celle qui est en mémoire : rien de ce lot-ci n'a été
    écrit, et le marquage ne doit porter sur aucun de ses comptes."""
    enregistrables = ComptesEnregistrables()
    enregistrables.ajouter(CompteCree("a", "s3cr3t"))
    ecrits = enregistrables.comptes
    enregistrables.reinitialiser()
    enregistrables.ajouter(CompteCree("b", "aut3r"))
    enregistrables.marquer_enregistres(ecrits)
    assert enregistrables.secrets_en_attente == 1


def test_le_rapport_final_rouvre_l_attente() -> None:
    """`fixer` remplace la liste : ce qu'elle porte n'a pas été écrit sous cette forme."""
    enregistrables = ComptesEnregistrables()
    enregistrables.ajouter(CompteCree("dupont", "s3cr3t"))
    enregistrables.marquer_enregistres(enregistrables.comptes)
    enregistrables.fixer([CompteCree("dupont", "s3cr3t")])
    assert enregistrables.secrets_en_attente == 1


def test_la_reinitialisation_vide_la_liste_et_l_attente() -> None:
    """Au démarrage d'un lot : sans cela, l'export mélangerait deux lots."""
    enregistrables = ComptesEnregistrables()
    enregistrables.ajouter(CompteCree("dupont", "s3cr3t"))
    enregistrables.reinitialiser()
    assert enregistrables.comptes == ()
    assert enregistrables.secrets_en_attente == 0


def test_l_avertissement_de_perte_dit_le_nombre_et_l_irreversible() -> None:
    texte = avertissement_perte_de_secrets(200)
    assert "200 mots de passe" in texte
    assert "créés" in texte  # les comptes, eux, restent sur le firewall
    assert texte.endswith("Lancer quand même ?")


def test_l_avertissement_de_perte_s_accorde_au_singulier() -> None:
    assert "1 mot de passe n'a pas" in avertissement_perte_de_secrets(1)


def test_rien_a_perdre_ne_pose_aucune_question_a_la_fermeture() -> None:
    """None = la fenêtre se ferme sans rien demander."""
    assert (
        avertissement_de_fermeture(
            lot_en_cours=False, creation_annuaire_en_cours=False, secrets_en_attente=0
        )
        is None
    )


def test_fermer_en_plein_lot_dit_ce_que_le_fil_perd() -> None:
    """Le fil est tué où qu'il en soit, y compris entre un USER CREATE et son
    USER PASSWORD."""
    texte = avertissement_de_fermeture(
        lot_en_cours=True, creation_annuaire_en_cours=False, secrets_en_attente=0
    )
    assert texte is not None
    assert "en cours" in texte
    assert "mot de passe" in texte
    assert texte.endswith("Fermer quand même ?")


def test_fermer_pendant_une_creation_d_annuaire_nomme_la_commande_partie() -> None:
    """L'opération la plus destructrice du produit : elle ne se refait pas, ne s'annule
    pas, et son fil est un démon qui meurt avec l'interpréteur."""
    texte = avertissement_de_fermeture(
        lot_en_cours=False, creation_annuaire_en_cours=True, secrets_en_attente=0
    )
    assert texte is not None
    assert "CONFIG LDAP INITIALIZE" in texte
    assert texte.endswith("Fermer quand même ?")


def test_fermer_sur_des_secrets_non_enregistres_dit_leur_nombre() -> None:
    texte = avertissement_de_fermeture(
        lot_en_cours=False, creation_annuaire_en_cours=False, secrets_en_attente=200
    )
    assert texte is not None
    assert "200 mots de passe" in texte
    assert "en cours" not in texte


def test_fermer_en_plein_lot_avec_des_secrets_dit_les_deux() -> None:
    texte = avertissement_de_fermeture(
        lot_en_cours=True, creation_annuaire_en_cours=False, secrets_en_attente=3
    )
    assert texte is not None
    assert "en cours" in texte
    assert "3 mots de passe" in texte


def test_l_enregistrement_compte_a_part_les_comptes_sans_mot_de_passe() -> None:
    """« N mots de passe enregistrés » mentait dès qu'un USER PASSWORD avait échoué."""
    ligne = ligne_d_enregistrement(
        (CompteCree("dupont", "s3cr3t"), CompteCree("martin", "")), "C:/lot.csv"
    )
    assert "2 comptes écrits" in ligne
    assert "1 mot de passe enregistré" in ligne
    assert "1 compte sans mot de passe" in ligne
    assert "C:/lot.csv" in ligne


def test_l_enregistrement_sans_compte_muet_ne_parle_que_des_mots_de_passe() -> None:
    ligne = ligne_d_enregistrement((CompteCree("dupont", "s3cr3t"),), "lot.csv")
    assert "sans mot de passe" not in ligne
    assert "1 mot de passe enregistré" in ligne


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


# --- secrets hors du repr -------------------------------------------------


def test_le_mot_de_passe_d_administration_ne_figure_pas_dans_le_repr() -> None:
    """Fuite latente, et elle traverserait précisément la frontière que `boitier_sdk`
    blinde à grands frais : `Connexion` voyage jusqu'au fil d'exécution, et son `repr`
    apparaîtrait dans une trace, une assertion qui échoue ou une ligne de journal."""
    session = connexion(mot_de_passe="MotDePasseAdmin!")
    assert "MotDePasseAdmin!" not in repr(session)
    assert "firewall.local" in repr(session)
    assert session.mot_de_passe == "MotDePasseAdmin!"
    # Les paramètres du lot portent la connexion : la fuite passerait aussi par eux.
    assert "MotDePasseAdmin!" not in repr(
        Parametres(
            connexion=session,
            fichier=Path("entree.csv"),
            simulation=False,
            politique=DURCIE,
        )
    )


def test_le_secret_de_l_annuaire_ne_figure_pas_dans_le_repr() -> None:
    """Celui de `cn=StormshieldAdmin` : le secret de la commande la plus destructrice."""
    annuaire = ParametresAnnuaire(
        domainname="interne.local",
        organisation="Org",
        dc="dc",
        mot_de_passe="SecretAnnuaire!",
    )
    assert "SecretAnnuaire!" not in repr(annuaire)
    assert "interne.local" in repr(annuaire)
    assert annuaire.mot_de_passe == "SecretAnnuaire!"


# --- confirmation avant écriture ------------------------------------------


def _plan(
    comptes: tuple[str, ...] = ("dupont",),
    groupes: tuple[GroupeACreer, ...] = (),
) -> Plan:
    return Plan(
        comptes_a_creer=tuple(utilisateur(identifiant) for identifiant in comptes),
        comptes_ignores=(),
        groupes_a_creer=groupes,
        orphelins=(),
        domaine="interne.local",
    )


def test_la_confirmation_nomme_l_hote_les_comptes_et_les_groupes_neufs() -> None:
    """Le produit demandait confirmation pour perdre des mots de passe et pas pour écrire
    sur un firewall : c'est cette asymétrie que ce texte corrige."""
    texte = texte_de_confirmation_du_lot(
        "firewall.local", _plan(("dupont", "martin"), (GroupeACreer("rh", 2),))
    )
    assert "firewall.local" in texte
    assert "2 comptes à créer" in texte
    assert "1 groupe neuf" in texte
    assert "Groupes à créer : rh (2 membres)" in texte
    assert "Écrire maintenant ?" in texte


def test_la_confirmation_signale_un_groupe_neuf_a_un_seul_membre() -> None:
    """Un groupe neuf à un membre est la signature d'une coquille de saisie, et un groupe
    fantôme créé sur le boîtier ne s'annule pas depuis cet outil."""
    texte = texte_de_confirmation_du_lot(
        "firewall.local", _plan(("dupont",), (GroupeACreer("compta_bis", 1),))
    )
    assert "Un groupe neuf n'aurait qu'un seul membre (compta_bis)" in texte
    assert "coquille de saisie" in texte


def test_la_confirmation_accorde_le_signalement_a_plusieurs_groupes_solitaires() -> None:
    texte = texte_de_confirmation_du_lot(
        "firewall.local",
        _plan(("dupont", "martin"), (GroupeACreer("compta_bis", 1), GroupeACreer("rh", 1))),
    )
    assert "2 groupes neufs n'auraient qu'un seul membre (compta_bis, rh)" in texte


def test_la_confirmation_sans_groupe_neuf_ne_parle_pas_de_groupes() -> None:
    texte = texte_de_confirmation_du_lot("firewall.local", _plan(("dupont",)))
    assert "1 compte à créer, 0 groupe neuf." in texte
    assert "Groupes à créer" not in texte
    assert "seul membre" not in texte


def test_la_demande_porte_son_texte_et_debloque_le_fil_sur_la_reponse() -> None:
    """Seul message à circuler dans les deux sens : le fil ne peut pas ouvrir de boîte de
    dialogue, la fenêtre ne peut pas décider à la place de l'opérateur."""
    demande = DemandeConfirmation(_plan(("dupont",)), "firewall.local")
    assert demande.texte == texte_de_confirmation_du_lot("firewall.local", demande.plan)
    demande.repondre(True)
    assert demande.attendre() is True
    refus = DemandeConfirmation(_plan(("dupont",)), "firewall.local")
    refus.repondre(False)
    assert refus.attendre() is False


def test_le_fil_demande_l_autorisation_avant_d_ecrire_et_respecte_le_refus() -> None:
    """Le fil publie la demande, bloque, et n'écrit rien si la réponse est non."""
    boitier = BoitierMemoire()
    messages: list[MessageFil] = []

    def publier(message: MessageFil) -> None:
        messages.append(message)
        if isinstance(message, DemandeConfirmation):
            assert boitier.utilisateurs == []
            message.repondre(False)

    travailler(
        parametres(simulation=False),
        [utilisateur("dupont")],
        publier,
        fabriquer_boitier=lambda _: boitier,
    )
    demandes = [message for message in messages if isinstance(message, DemandeConfirmation)]
    assert len(demandes) == 1
    assert demandes[0].hote == "firewall.local"
    assert boitier.utilisateurs == []


def test_le_fil_n_ecrit_qu_une_fois_l_autorisation_donnee() -> None:
    boitier = BoitierMemoire()
    messages, publier = collecter()
    travailler(
        parametres(simulation=False),
        [utilisateur("dupont")],
        publier,
        fabriquer_boitier=lambda _: boitier,
    )
    assert any(isinstance(message, DemandeConfirmation) for message in messages)
    assert boitier.utilisateurs == ["dupont"]


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


def test_un_arret_reseau_dit_que_relancer_suffit() -> None:
    """Deux conduites à tenir, donc deux textes : chercher la ligne décisive dans un
    journal de plusieurs centaines de lignes n'est pas une conduite."""
    rapport = Rapport(interrompu=True, motif_arret=MotifArret.RESEAU)
    assert "relancer le lot" in lignes_du_rapport(rapport)[0]


def test_un_arret_fatal_dit_de_corriger_avant_de_relancer() -> None:
    rapport = Rapport(interrompu=True, motif_arret=MotifArret.FATAL)
    entete = lignes_du_rapport(rapport)[0]
    assert "corrig" in entete
    assert "relancer le lot" not in entete


def test_un_lot_mene_a_son_terme_ne_parle_d_aucun_arret() -> None:
    assert lignes_du_rapport(Rapport())[0].startswith("Terminé")


# --- séparation de deux lots ----------------------------------------------


def test_un_nouveau_lot_ouvre_le_journal_par_une_ligne_qui_dit_son_mode() -> None:
    """Après une simulation puis un lot réel, deux plans se suivaient dans la même zone
    sans rien qui dise où l'un finit."""
    assert "simulation" in ligne_de_nouveau_lot(simulation=True)
    assert "réel" in ligne_de_nouveau_lot(simulation=False)


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


def collecter(*, accorder: bool = True) -> tuple[list[MessageFil], Callable[[MessageFil], None]]:
    """Publieur de test. Il répond aux demandes de confirmation, faute de quoi le fil
    resterait bloqué sur `attendre()` — c'est le rôle que tient la fenêtre en production."""
    messages: list[MessageFil] = []

    def publier(message: MessageFil) -> None:
        messages.append(message)
        if isinstance(message, DemandeConfirmation):
            message.repondre(accorder)

    return messages, publier


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


# --- garde-fous de structure ----------------------------------------------
#
# Ces tests lisent des fichiers source sans les importer : `fenetre.py` importe
# `tkinter`, qui peut être absent de la machine. Ils vérifient des propriétés que
# l'exécution ne montrerait qu'en recette, sur un boîtier, un jour de coupure réseau —
# et les derniers sabotent des sources factices pour prouver qu'ils mordent.


def _arbre(module_source: str) -> ast.Module:
    return ast.parse(Path(module_source).read_text(encoding="utf-8"))


def _modules_importes(arbre: ast.Module) -> list[str]:
    importes: list[str] = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            importes.extend(alias.name for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module is not None:
            importes.append(noeud.module)
    return importes


def test_le_module_de_presentation_n_importe_pas_tkinter() -> None:
    """Garde-fou : la logique testable doit rester importable là où `tkinter` est absent.

    Le jour où un raccourci ferait remonter un widget ici, toute la suite deviendrait
    incollectable sur le runner d'intégration continue — ce test le dit avant.
    """
    importes = _modules_importes(_arbre(presentation.__file__))
    assert [nom for nom in importes if nom.partition(".")[0] == "tkinter"] == []


def _venus_de_presentation(arbre: ast.Module) -> set[str]:
    return {
        alias.asname or alias.name
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.ImportFrom)
        and noeud.module == "stormshield_utilisateurs.presentation"
        for alias in noeud.names
    }


def _noms_de_thread(arbre: ast.Module) -> set[str]:
    """Toutes les façons dont `threading.Thread` peut être nommé dans ce source.

    Se fier au seul `threading.Thread` laissait passer un `from threading import Thread`
    suivi d'un `Thread(...)` : la règle ne doit pas dépendre du style d'import.
    """
    noms: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            noms.update(
                f"{alias.asname or alias.name}.Thread"
                for alias in noeud.names
                if alias.name == "threading"
            )
        elif isinstance(noeud, ast.ImportFrom) and noeud.module == "threading":
            noms.update(
                alias.asname or alias.name for alias in noeud.names if alias.name == "Thread"
            )
    return noms


def _mentionne_self(expression: ast.expr) -> bool:
    return any(
        isinstance(noeud, ast.Name) and noeud.id == "self" for noeud in ast.walk(expression)
    )


def _noms_mentionnes(expression: ast.expr) -> set[str]:
    return {noeud.id for noeud in ast.walk(expression) if isinstance(noeud, ast.Name)}


def _fonctions_qui_atteignent_self(arbre: ast.Module) -> set[str]:
    """Noms des fonctions de ce source dont le corps mentionne `self`, méthodes comprises.

    C'est le contournement réaliste : `def publier(m): self._appliquer(m)` passée en
    argument ne montre aucun jeton `self` au point d'appel, et le fil appelle pourtant
    une méthode de la fenêtre en boucle.
    """
    return {
        noeud.name
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.FunctionDef | ast.AsyncFunctionDef)
        and any(
            isinstance(interne, ast.Name) and interne.id == "self"
            for interne in ast.walk(noeud)
        )
    }


# Toute autre façon de lancer un fil que `threading.Thread(target=...)` est refusée en
# bloc : la fenêtre n'en a aucun besoin, et refuser le constructeur coûte moins cher que
# d'analyser ce qu'on lui passe. Comparaison sur le dernier segment du nom appelé, pour
# ne pas dépendre du style d'import.
_LANCEURS_INTERDITS = frozenset(
    {
        "Timer",
        "submit",
        "run_in_executor",
        "start_new_thread",
        "ThreadPoolExecutor",
        "ProcessPoolExecutor",
        "Process",
    }
)


def _lanceurs_interdits(arbre: ast.Module) -> list[str]:
    return [
        f"lanceur de fil interdit : {ast.unparse(noeud.func)}"
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.Call)
        and ast.unparse(noeud.func).rpartition(".")[2] in _LANCEURS_INTERDITS
    ]


def _sous_classes_de_thread(arbre: ast.Module) -> list[str]:
    """Une sous-classe de `Thread` porte la fenêtre dans son état : aucun `target=` à lire."""
    return [
        f"classe dérivée de Thread : {noeud.name}"
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.ClassDef)
        and any(ast.unparse(base).rpartition(".")[2] == "Thread" for base in noeud.bases)
    ]


def _appels_de_fil(arbre: ast.Module, noms: set[str]) -> list[ast.Call]:
    return [
        noeud
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.Call)
        and (ast.unparse(noeud.func) in noms or ast.unparse(noeud.func).endswith(".Thread"))
    ]


def _fils_qui_pourraient_toucher_un_widget(source: str) -> list[str]:
    """Un motif d'infraction par fil douteux. Liste vide = aucune infraction *visible*.

    Ce que la règle vérifie : un fil ne peut naître que d'un `threading.Thread` doté
    d'un `target=` nommé, cette cible vient de `presentation` — module où `tkinter` est
    interdit par un autre test —, et ni la cible ni les arguments ne mentionnent `self`
    ni un nom de fonction de ce source qui, lui, atteint `self`. Les `args` comptent
    autant que la cible : ils portent le publieur, c'est-à-dire ce que le fil appelle en
    boucle, et ce publieur touche le journal, la barre, les boutons et les dialogues.
    Toute autre façon de lancer un fil — `Timer`, exécuteur, sous-classe de `Thread` —
    est refusée en bloc.

    Ce qu'elle **ne garantit pas**, et qu'aucune règle statique de cette forme ne
    garantira :

    - un widget rangé *dans* un objet passé au fil : la règle lit des noms, elle ne
      suit pas les valeurs. Un `Parametres` qui porterait un `tk.Entry` passerait ;
    - une capture indirecte : `def publier(m): aider(m)`, où seule `aider` atteint
      `self`, n'est pas vue — seule la mention directe de `self` dans le corps l'est ;
    - un widget atteint par une variable globale ou par un autre module, sans passer
      par `self` ;
    - un fil lancé depuis un module autre que `fenetre.py`, que ce test ne lit pas ;
    - ce que fait `presentation` de ce qu'on lui donne : la règle s'arrête au point
      d'appel.

    Autrement dit : elle attrape les contournements distraits, pas un contournement
    décidé. Ce qui passe ici se paiera en recette, un jour de coupure réseau.
    """
    arbre = ast.parse(source)
    venus = _venus_de_presentation(arbre)
    dangereuses = _fonctions_qui_atteignent_self(arbre)
    infractions = _lanceurs_interdits(arbre) + _sous_classes_de_thread(arbre)
    for appel in _appels_de_fil(arbre, _noms_de_thread(arbre)):
        if appel.args:
            infractions.append("fil construit avec des arguments positionnels")
        cible = next((mot for mot in appel.keywords if mot.arg == "target"), None)
        if cible is None:
            infractions.append("fil sans target= nommé")
        elif ast.unparse(cible.value) not in venus:
            infractions.append(f"cible hors de presentation : {ast.unparse(cible.value)}")
        for mot in appel.keywords:
            if _mentionne_self(mot.value):
                infractions.append(f"{mot.arg}= mentionne self : {ast.unparse(mot.value)}")
            infractions.extend(
                f"{mot.arg}= porte {nom}, qui atteint self"
                for nom in sorted(_noms_mentionnes(mot.value) & dangereuses)
            )
    return infractions


def test_aucun_fil_de_la_fenetre_ne_peut_toucher_un_widget() -> None:
    """La règle « le fil ne touche jamais un widget » est vérifiée par construction.

    Chaque fil vise une fonction de `presentation`, module où `tkinter` est interdit par
    le test ci-dessus, et ne reçoit rien qui vienne de `self`. Le fil n'a pas d'appelant,
    et Tk ne signale pas toujours un widget touché hors de son fil : ce qui passerait ici
    ne se verrait qu'en recette, un jour de coupure réseau.
    """
    source = Path(presentation.__file__).with_name("fenetre.py").read_text(encoding="utf-8")
    assert _fils_qui_pourraient_toucher_un_widget(source) == []
    assert _appels_de_fil(ast.parse(source), _noms_de_thread(ast.parse(source))), (
        "la fenêtre doit lancer son travail dans un fil"
    )


# Sources de sabotage : ce que le garde-fou doit refuser. Jamais importés, seulement
# analysés — ils prouvent que le garde-fou mord, au lieu de le supposer.
_FIL_SAIN = """
import threading
from stormshield_utilisateurs.presentation import travailler

class Fenetre:
    def _demarrer(self, parametres, utilisateurs):
        file = queue.Queue()
        threading.Thread(
            target=travailler, args=(parametres, utilisateurs, file.put), daemon=True
        ).start()
"""


def test_le_point_d_entree_n_importe_pas_la_fenetre_au_niveau_module() -> None:
    """Sans quoi il n'y aurait aucun filet : l'import de `tkinter` lèverait avant que
    quoi que ce soit ne puisse l'afficher, et un .exe fenêtré ne ferait rien du tout."""
    point_d_entree = Path(presentation.__file__).with_name("__main__.py")
    arbre = ast.parse(point_d_entree.read_text(encoding="utf-8"))
    importes_au_niveau_module = [
        noeud.module
        for noeud in arbre.body
        if isinstance(noeud, ast.ImportFrom) and noeud.module is not None
    ]
    assert "stormshield_utilisateurs.fenetre" not in importes_au_niveau_module


def test_le_texte_de_demarrage_impossible_nomme_les_deux_causes() -> None:
    """Seul message que verra l'opérateur d'un exécutable sans console."""
    texte = texte_de_demarrage_impossible(ImportError("No module named 'tkinter'"))
    assert "tkinter" in texte
    assert "affichage" in texte
    assert "ImportError" in texte


def test_le_garde_fou_laisse_passer_un_fil_sain() -> None:
    assert _fils_qui_pourraient_toucher_un_widget(_FIL_SAIN) == []


def test_le_garde_fou_refuse_un_publieur_pris_sur_la_fenetre() -> None:
    """Cible inchangée, publieur de la fenêtre dans `args` : c'est le trou qui compte."""
    sabotage = _FIL_SAIN.replace("file.put", "self._appliquer")
    infractions = _fils_qui_pourraient_toucher_un_widget(sabotage)
    assert any("mentionne self" in infraction for infraction in infractions)


def test_le_garde_fou_refuse_un_thread_importe_directement() -> None:
    """La détection ne doit pas dépendre de la façon dont `Thread` a été importé."""
    sabotage = _FIL_SAIN.replace("import threading", "from threading import Thread").replace(
        "threading.Thread(", "Thread("
    ).replace("target=travailler", "target=self._appliquer")
    infractions = _fils_qui_pourraient_toucher_un_widget(sabotage)
    assert any("cible hors de presentation" in infraction for infraction in infractions)
    assert any("mentionne self" in infraction for infraction in infractions)


def test_le_garde_fou_refuse_un_fil_sans_target_nomme() -> None:
    sabotage = _FIL_SAIN.replace("target=travailler,", "travailler,")
    assert _fils_qui_pourraient_toucher_un_widget(sabotage) == [
        "fil construit avec des arguments positionnels",
        "fil sans target= nommé",
    ]


# Les cinq contournements relevés en re-revue. Les quatre premiers se couvrent ; le
# cinquième — un widget rangé dans un objet passé au fil — ne se couvre pas par une
# règle statique, et la docstring du garde-fou le dit.

_FIL_A_FERMETURE_LOCALE = """
import threading
from stormshield_utilisateurs.presentation import travailler

class Fenetre:
    def _demarrer(self, parametres, utilisateurs):
        def publier(message):
            self._appliquer(message)
        threading.Thread(
            target=travailler, args=(parametres, utilisateurs, publier), daemon=True
        ).start()
"""

_FIL_PAR_TIMER = """
import threading

class Fenetre:
    def _demarrer(self):
        threading.Timer(1.0, self._appliquer).start()
"""

_FIL_PAR_EXECUTOR = """
from concurrent.futures import ThreadPoolExecutor

class Fenetre:
    def _demarrer(self):
        ThreadPoolExecutor().submit(self._appliquer)
"""

_FIL_PAR_SOUS_CLASSE = """
import threading

class FilDuLot(threading.Thread):
    def __init__(self, fenetre):
        super().__init__(daemon=True)
        self._fenetre = fenetre

    def run(self):
        self._fenetre.journal.insert("fini")
"""


def test_le_garde_fou_refuse_une_fermeture_locale_qui_capture_self() -> None:
    """Le cas réaliste : au point d'appel, `publier` ne montre aucun jeton `self`, et
    pourtant le fil appelle en boucle une méthode de la fenêtre."""
    infractions = _fils_qui_pourraient_toucher_un_widget(_FIL_A_FERMETURE_LOCALE)
    assert any("publier" in infraction for infraction in infractions)


def test_le_garde_fou_refuse_un_fil_lance_par_un_timer() -> None:
    assert _fils_qui_pourraient_toucher_un_widget(_FIL_PAR_TIMER) != []


def test_le_garde_fou_refuse_un_fil_lance_par_un_executeur() -> None:
    assert _fils_qui_pourraient_toucher_un_widget(_FIL_PAR_EXECUTOR) != []


def test_le_garde_fou_refuse_une_sous_classe_de_thread() -> None:
    """Une sous-classe porte la fenêtre dans son état : aucun `target=` à inspecter."""
    assert _fils_qui_pourraient_toucher_un_widget(_FIL_PAR_SOUS_CLASSE) != []
