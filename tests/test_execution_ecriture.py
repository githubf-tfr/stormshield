"""Exécution : on observe l'état final du double et les événements émis."""

from collections.abc import Callable

from stormshield_utilisateurs.boitier import ErreurCommande, ErreurReseau
from stormshield_utilisateurs.boitier_memoire import BoitierMemoire
from stormshield_utilisateurs.execution import (
    CreationReussie,
    Evenement,
    Journal,
    Patience,
    PlanPret,
    Progression,
    Termine,
    executer,
)
from stormshield_utilisateurs.modele import PolitiqueMotDePasse, Rapport, Utilisateur

POLITIQUE = PolitiqueMotDePasse(
    longueur=16, minuscules=True, majuscules=True, chiffres=True, speciaux=True
)
# Patience sans attente réelle : les tests ne dorment jamais.
PATIENCE = Patience(
    tentatives_connexion=3, reessais_mot_de_passe=3, delai=0.0, dormir=lambda _: None
)


def _utilisateur(identifiant: str, *groupes: str, ligne: int = 2) -> Utilisateur:
    return Utilisateur(
        ligne=ligne,
        identifiant=identifiant,
        identifiant_origine=identifiant,
        nom="Dupont",
        prenom="Marie",
        groupes=groupes,
    )


def _lancer(
    boitier: BoitierMemoire,
    utilisateurs: list[Utilisateur],
    *,
    simulation: bool = False,
    generer: Callable[[PolitiqueMotDePasse], str] = lambda _politique: "MotDePasse1!",
) -> tuple[Rapport, list[Evenement]]:
    evenements: list[Evenement] = []
    rapport = executer(
        boitier,
        utilisateurs,
        POLITIQUE,
        simulation=simulation,
        emettre=evenements.append,
        patience=PATIENCE,
        generer_mot_de_passe=generer,
    )
    return rapport, evenements


def _ecritures(boitier: BoitierMemoire) -> list[str]:
    return [
        operation
        for operation, _ in boitier.journal_appels
        if operation
        in {"creer_groupe", "creer_utilisateur", "definir_mot_de_passe", "ajouter_membre"}
    ]


def _progressions(evenements: list[Evenement]) -> list[Progression]:
    return [evenement for evenement in evenements if isinstance(evenement, Progression)]


def _textes(evenements: list[Evenement]) -> list[str]:
    return [evenement.texte for evenement in evenements if isinstance(evenement, Journal)]


def test_creation_nominale_dans_l_ordre_attendu() -> None:
    boitier = BoitierMemoire()
    rapport, _ = _lancer(boitier, [_utilisateur("dupont", "compta")])
    assert _ecritures(boitier) == [
        "creer_groupe",
        "creer_utilisateur",
        "definir_mot_de_passe",
        "ajouter_membre",
    ]
    assert boitier.mots_de_passe == {"dupont": "MotDePasse1!"}
    assert rapport.comptes_crees[0].identifiant == "dupont"
    assert rapport.groupes_crees == ["compta"]


def test_simulation_lit_mais_n_ecrit_pas() -> None:
    boitier = BoitierMemoire(utilisateurs=["martin"])
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont", "compta")], simulation=True)
    operations = {operation for operation, _ in boitier.journal_appels}
    assert operations <= {
        "connecter",
        "deconnecter",
        "lister_annuaires",
        "lire_politique",
        "lister_utilisateurs",
        "lister_groupes",
    }
    assert rapport.comptes_crees == []
    plans = [evenement for evenement in evenements if isinstance(evenement, PlanPret)]
    assert [compte.identifiant for compte in plans[0].plan.comptes_a_creer] == ["dupont"]
    assert plans[0].plan.orphelins == ("martin",)


def test_aucun_mot_de_passe_genere_en_simulation() -> None:
    """Un compte planifié mais jamais créé ne consomme aucun secret."""
    appels: list[str] = []

    def generer(_politique: PolitiqueMotDePasse) -> str:
        appels.append("appel")
        return "MotDePasse1!"

    _lancer(BoitierMemoire(), [_utilisateur("dupont")], simulation=True, generer=generer)
    assert appels == []


def test_aucun_mot_de_passe_genere_quand_la_creation_echoue() -> None:
    """USER CREATE refusé : le secret n'est jamais tiré."""
    boitier = BoitierMemoire()
    appels: list[str] = []

    def generer(_politique: PolitiqueMotDePasse) -> str:
        appels.append("appel")
        return "MotDePasse1!"

    def refuser(operation: str, _cible: str) -> None:
        if operation == "creer_utilisateur":
            raise ErreurCommande(200, "uid interdit")

    boitier.declencheur = refuser
    rapport, _ = _lancer(boitier, [_utilisateur("admin")], generer=generer)
    assert appels == []
    assert rapport.comptes_crees == []
    assert rapport.echecs[0].operation == "USER CREATE"


def test_echec_isole_n_arrete_pas_le_lot() -> None:
    boitier = BoitierMemoire()

    def refuser_dupont(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "dupont":
            raise ErreurCommande(200, "uid interdit")

    boitier.declencheur = refuser_dupont
    rapport, _ = _lancer(boitier, [_utilisateur("dupont"), _utilisateur("legrand", ligne=3)])
    assert [compte.identifiant for compte in rapport.comptes_crees] == ["legrand"]
    assert len(rapport.echecs) == 1


def test_trois_reessais_de_mot_de_passe_puis_champ_vide() -> None:
    boitier = BoitierMemoire()
    tentatives = 0

    def toujours_refuser(operation: str, _cible: str) -> None:
        nonlocal tentatives
        if operation == "definir_mot_de_passe":
            tentatives += 1
            raise ErreurCommande(200, "politique refusée")

    boitier.declencheur = toujours_refuser
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont")])
    assert tentatives == 4  # un appel initial puis trois réessais
    assert [compte.identifiant for compte in rapport.comptes_crees] == ["dupont"]
    assert rapport.comptes_crees[0].mot_de_passe == ""
    assert [compte.identifiant for compte in rapport.sans_mot_de_passe] == ["dupont"]
    assert any("sans mot de passe" in texte for texte in _textes(evenements))


def test_mot_de_passe_reussi_au_deuxieme_essai() -> None:
    boitier = BoitierMemoire()
    tentatives = 0

    def refuser_une_fois(operation: str, _cible: str) -> None:
        nonlocal tentatives
        if operation == "definir_mot_de_passe":
            tentatives += 1
            if tentatives == 1:
                raise ErreurCommande(200, "transitoire")

    boitier.declencheur = refuser_une_fois
    rapport, _ = _lancer(boitier, [_utilisateur("dupont")])
    assert rapport.comptes_crees[0].mot_de_passe == "MotDePasse1!"
    assert rapport.sans_mot_de_passe == []


def test_echec_d_appartenance_signale_sans_reessai() -> None:
    boitier = BoitierMemoire(groupes=["compta"])

    def refuser(operation: str, _cible: str) -> None:
        if operation == "ajouter_membre":
            raise ErreurCommande(200, "refusé")

    boitier.declencheur = refuser
    rapport, _ = _lancer(boitier, [_utilisateur("dupont", "compta")])
    assert rapport.comptes_crees[0].mot_de_passe == "MotDePasse1!"
    assert rapport.echecs[0].operation == "USER GROUP ADDUSER"
    assert [operation for operation, _ in boitier.journal_appels].count("ajouter_membre") == 1


def test_echec_de_creation_de_groupe_signale_et_lot_poursuivi() -> None:
    boitier = BoitierMemoire()

    def refuser(operation: str, _cible: str) -> None:
        if operation == "creer_groupe":
            raise ErreurCommande(200, "guillemet double interdit")

    boitier.declencheur = refuser
    rapport, _ = _lancer(boitier, [_utilisateur("dupont", 'Groupe "A"')])
    assert [compte.identifiant for compte in rapport.comptes_crees] == ["dupont"]
    assert any(echec.operation == "USER GROUP CREATE" for echec in rapport.echecs)


def test_un_evenement_type_signale_chaque_compte_cree() -> None:
    """Le bouton d'enregistrement s'active dès la première création, pas à la fin du lot."""
    rapport, evenements = _lancer(
        BoitierMemoire(), [_utilisateur("dupont"), _utilisateur("legrand", ligne=3)]
    )
    creations = [evenement for evenement in evenements if isinstance(evenement, CreationReussie)]
    assert [evenement.compte for evenement in creations] == rapport.comptes_crees
    premier = evenements.index(creations[0])
    second = evenements.index(creations[1])
    # Le premier événement de création tombe pendant le lot, pas après.
    assert premier < second
    assert any(isinstance(evenement, Progression) for evenement in evenements[premier:second])
    assert premier < evenements.index(
        next(evenement for evenement in evenements if isinstance(evenement, Termine))
    )


def test_compte_sans_mot_de_passe_signale_par_un_evenement_type() -> None:
    boitier = BoitierMemoire()

    def refuser(operation: str, _cible: str) -> None:
        if operation == "definir_mot_de_passe":
            raise ErreurCommande(200, "politique refusée")

    boitier.declencheur = refuser
    _, evenements = _lancer(boitier, [_utilisateur("dupont")])
    creations = [evenement for evenement in evenements if isinstance(evenement, CreationReussie)]
    assert creations[0].compte.identifiant == "dupont"
    assert creations[0].compte.mot_de_passe == ""


def test_reconnexion_reconstruit_le_plan_au_lieu_de_rejouer() -> None:
    """Après coupure, l'outil relit l'état : le compte déjà créé tombe en « déjà présent »."""
    boitier = BoitierMemoire()
    coupures = 0

    def couper_apres_le_premier(operation: str, cible: str) -> None:
        nonlocal coupures
        if operation == "creer_utilisateur" and cible == "legrand" and coupures == 0:
            coupures += 1
            boitier.utilisateurs.append("legrand")  # le boîtier a exécuté avant la coupure
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_apres_le_premier
    rapport, evenements = _lancer(
        boitier, [_utilisateur("dupont"), _utilisateur("legrand", ligne=3)]
    )
    assert boitier.utilisateurs.count("legrand") == 1
    assert boitier.connexions == 2
    assert rapport.interrompu is False
    # Le plan reconstruit range legrand en « déjà présent ».
    plans = [evenement for evenement in evenements if isinstance(evenement, PlanPret)]
    assert [compte.identifiant for compte in plans[-1].plan.comptes_ignores] == [
        "dupont",
        "legrand",
    ]
    # La barre reste cohérente : le total suit le plan reconstruit.
    derniere = _progressions(evenements)[-1]
    assert derniere.accomplies == derniere.total


def test_coupure_entre_la_creation_et_le_mot_de_passe_laisse_une_trace() -> None:
    """Le compte existe sur le boîtier : il doit figurer au rapport, sans mot de passe,
    et un échec doit le nommer. Sans cela l'opérateur perd un compte sans le savoir."""
    boitier = BoitierMemoire()

    def couper_le_mot_de_passe_de_dupont(operation: str, cible: str) -> None:
        if operation == "definir_mot_de_passe" and cible == "dupont":
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_le_mot_de_passe_de_dupont
    rapport, evenements = _lancer(
        boitier, [_utilisateur("dupont"), _utilisateur("legrand", ligne=3)]
    )
    assert "dupont" in boitier.utilisateurs
    assert "dupont" not in boitier.mots_de_passe
    assert [compte.identifiant for compte in rapport.comptes_crees] == ["dupont", "legrand"]
    assert [compte.identifiant for compte in rapport.sans_mot_de_passe] == ["dupont"]
    assert any(
        echec.identifiant == "dupont" and echec.operation == "USER PASSWORD"
        for echec in rapport.echecs
    )
    creations = [
        evenement for evenement in evenements if isinstance(evenement, CreationReussie)
    ]
    assert [evenement.compte for evenement in creations] == rapport.comptes_crees


def test_coupure_pendant_le_rattachement_laisse_une_trace() -> None:
    """Le plan reconstruit ne rattrape pas un compte devenu « déjà présent » :
    l'interruption doit laisser un échec exploitable."""
    boitier = BoitierMemoire(groupes=["compta"])

    def couper_le_rattachement(operation: str, cible: str) -> None:
        if operation == "ajouter_membre" and cible == "compta/dupont":
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_le_rattachement
    rapport, _ = _lancer(boitier, [_utilisateur("dupont", "compta")])
    assert boitier.membres == {}
    assert [compte.identifiant for compte in rapport.comptes_crees] == ["dupont"]
    assert any(
        echec.identifiant == "dupont" and echec.operation == "USER GROUP ADDUSER"
        for echec in rapport.echecs
    )


def test_la_reprise_ne_relit_que_les_comptes_et_les_groupes() -> None:
    """Ni l'annuaire ni la politique : ils ne changent pas au milieu d'un lot."""
    boitier = BoitierMemoire()

    def couper_une_fois(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "dupont" and boitier.connexions == 1:
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_une_fois
    _lancer(boitier, [_utilisateur("dupont")])
    operations = [operation for operation, _ in boitier.journal_appels]
    assert operations.count("lister_annuaires") == 1
    assert operations.count("lire_politique") == 1
    assert operations.count("lister_utilisateurs") == 2
    assert operations.count("lister_groupes") == 2


def test_trois_reconnexions_infructueuses_puis_arret_net() -> None:
    boitier = BoitierMemoire()

    def couper_toujours(operation: str, _cible: str) -> None:
        if operation in {"creer_utilisateur", "connecter"} and boitier.connexions >= 1:
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_toujours
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont")])
    assert rapport.interrompu is True
    # Connexion initiale réussie, puis trois tentatives de reconnexion toutes refusées.
    assert [operation for operation, _ in boitier.journal_appels].count("connecter") == 4
    assert boitier.connexions == 1
    assert any(isinstance(evenement, Termine) for evenement in evenements)


def test_relecture_impossible_apres_reconnexion_arrete_le_lot() -> None:
    """La liaison retombe pendant la relecture : arrêt net, jamais d'exception nue."""
    boitier = BoitierMemoire()

    def couper(operation: str, _cible: str) -> None:
        if operation == "creer_utilisateur":
            raise ErreurReseau("liaison perdue")
        if operation == "lister_utilisateurs" and boitier.connexions >= 2:
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont")])
    assert rapport.interrompu is True
    assert boitier.connecte is False
    assert any(isinstance(evenement, Termine) for evenement in evenements)


def test_reprise_les_comptes_deja_crees_sont_ignores() -> None:
    boitier = BoitierMemoire(utilisateurs=["dupont"])
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont"), _utilisateur("legrand")])
    assert [compte.identifiant for compte in rapport.comptes_crees] == ["legrand"]
    plans = [evenement for evenement in evenements if isinstance(evenement, PlanPret)]
    assert [compte.identifiant for compte in plans[0].plan.comptes_ignores] == ["dupont"]


def test_progression_en_simulation_couvre_les_seules_lectures() -> None:
    _, evenements = _lancer(BoitierMemoire(), [_utilisateur("dupont", "compta")], simulation=True)
    assert _progressions(evenements)[-1] == Progression(accomplies=4, total=4)


def test_progression_en_reel_couvre_lectures_et_ecritures() -> None:
    _, evenements = _lancer(BoitierMemoire(), [_utilisateur("dupont", "compta")])
    # 4 lectures + 1 groupe + USER CREATE + USER PASSWORD + 1 ADDUSER
    assert _progressions(evenements)[-1] == Progression(accomplies=8, total=8)


def test_progression_atteint_le_total_quand_une_creation_echoue() -> None:
    """USER CREATE refusé : les opérations restantes du compte n'auront pas lieu,
    leur budget est consommé d'un coup pour que la barre atteigne son total."""
    boitier = BoitierMemoire(groupes=["compta", "rh"])

    def refuser_dupont(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "dupont":
            raise ErreurCommande(200, "uid interdit")

    boitier.declencheur = refuser_dupont
    _, evenements = _lancer(
        boitier,
        [_utilisateur("dupont", "compta", "rh"), _utilisateur("legrand", ligne=3)],
    )
    # 4 lectures + (USER CREATE + USER PASSWORD + 2 ADDUSER) + (USER CREATE + USER PASSWORD)
    assert _progressions(evenements)[-1] == Progression(accomplies=10, total=10)


def test_bascule_en_minuscules_signalee_au_journal() -> None:
    utilisateur = Utilisateur(
        ligne=2,
        identifiant="jean.dupont",
        identifiant_origine="Jean.Dupont",
        nom="Dupont",
        prenom="Jean",
        groupes=(),
    )
    _, evenements = _lancer(BoitierMemoire(), [utilisateur])
    assert any(
        "Jean.Dupont" in texte and "jean.dupont" in texte for texte in _textes(evenements)
    )


def test_deconnexion_meme_en_cas_d_arret() -> None:
    boitier = BoitierMemoire()

    def couper_toujours(operation: str, _cible: str) -> None:
        if operation in {"creer_utilisateur", "connecter"} and boitier.connexions >= 1:
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_toujours
    _lancer(boitier, [_utilisateur("dupont")])
    assert boitier.connecte is False


def test_deconnexion_apres_un_lot_nominal() -> None:
    boitier = BoitierMemoire()
    _lancer(boitier, [_utilisateur("dupont")])
    assert boitier.connecte is False
