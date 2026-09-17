"""Exécution : on observe l'état final du double et les événements émis."""

from collections.abc import Callable, Sequence

from fabriques import _Interrupteur

from stormshield_utilisateurs import motdepasse
from stormshield_utilisateurs.boitier import ErreurCommande, ErreurFatale, ErreurReseau
from stormshield_utilisateurs.boitier_memoire import BoitierMemoire, dn_de
from stormshield_utilisateurs.execution import (
    LECTURES_DE_BASE,
    CreationReussie,
    Evenement,
    Journal,
    Patience,
    PlanPret,
    PolitiqueLue,
    PolitiqueRefusee,
    Progression,
    Termine,
    executer,
)
from stormshield_utilisateurs.modele import (
    MotifArret,
    Plan,
    PlancherPolitique,
    PolitiqueMotDePasse,
    Rapport,
    Rejet,
    Utilisateur,
)

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
    rejets: Sequence[Rejet] = (),
    generer: Callable[[PolitiqueMotDePasse], str] = lambda _politique: "MotDePasse1!",
    confirmer: Callable[[Plan], bool] = lambda _plan: True,
    arret: Callable[[], bool] = lambda: False,
) -> tuple[Rapport, list[Evenement]]:
    evenements: list[Evenement] = []
    rapport = executer(
        boitier,
        utilisateurs,
        POLITIQUE,
        simulation=simulation,
        emettre=evenements.append,
        confirmer=confirmer,
        rejets=rejets,
        patience=PATIENCE,
        generer_mot_de_passe=generer,
        arret_demande=arret,
    )
    return rapport, evenements


def _ecritures(boitier: BoitierMemoire) -> list[str]:
    return [
        operation
        for operation, _ in boitier.journal_appels
        if operation
        in {"creer_groupe", "creer_utilisateur", "definir_mot_de_passe", "ajouter_membre"}
    ]


def _rattachements(boitier: BoitierMemoire) -> list[str]:
    return [cible for operation, cible in boitier.journal_appels if operation == "ajouter_membre"]


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


def test_un_lot_reel_demande_confirmation_sur_le_plan_avant_toute_ecriture() -> None:
    """La confirmation est posée sur le plan déjà construit — comptes à créer et groupes
    neufs compris — et avant la première commande d'écriture."""
    boitier = BoitierMemoire()
    vus: list[Plan] = []

    def accorder(plan: Plan) -> bool:
        # Aucune écriture ne doit avoir eu lieu quand la question se pose.
        assert _ecritures(boitier) == []
        vus.append(plan)
        return True

    _lancer(boitier, [_utilisateur("dupont", "compta_bis")], confirmer=accorder)
    assert [travail.identifiant_cible for travail in vus[0].creations] == ["dupont"]
    assert [(groupe.nom, groupe.nombre_membres) for groupe in vus[0].groupes_a_creer] == [
        ("compta_bis", 1)
    ]
    assert boitier.utilisateurs == ["dupont"]


def test_un_refus_de_confirmation_n_envoie_rien() -> None:
    """L'opérateur doit pouvoir renoncer : rien ne part, et le journal le dit."""
    boitier = BoitierMemoire()
    rapport, evenements = _lancer(
        boitier, [_utilisateur("dupont", "compta")], confirmer=lambda _plan: False
    )
    assert _ecritures(boitier) == []
    assert boitier.utilisateurs == []
    assert rapport.comptes_crees == []
    assert any("abandonné à la confirmation" in texte for texte in _textes(evenements))
    assert isinstance(evenements[-1], Termine)


def test_une_simulation_ne_demande_aucune_confirmation() -> None:
    """Rien n'est écrit : il n'y a rien à confirmer, et une question de plus serait une
    question à laquelle on répond sans lire."""
    boitier = BoitierMemoire()

    def interdite(_plan: Plan) -> bool:
        raise AssertionError("aucune confirmation ne doit être demandée en simulation")

    _lancer(boitier, [_utilisateur("dupont")], simulation=True, confirmer=interdite)


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
        "lister_membres",
    }
    assert rapport.comptes_crees == []
    plans = [evenement for evenement in evenements if isinstance(evenement, PlanPret)]
    assert [travail.identifiant_cible for travail in plans[0].plan.creations] == ["dupont"]
    assert plans[0].plan.nombre_orphelins == 1


def test_aucun_mot_de_passe_genere_en_simulation() -> None:
    """Un compte planifié mais jamais créé ne consomme aucun secret."""
    appels: list[str] = []

    def generer(_politique: PolitiqueMotDePasse) -> str:
        appels.append("appel")
        return "MotDePasse1!"

    _lancer(BoitierMemoire(), [_utilisateur("dupont")], simulation=True, generer=generer)
    assert appels == []


def test_aucun_mot_de_passe_n_est_pose_sur_un_compte_deja_present() -> None:
    """La garantie que le nouveau périmètre met le plus à l'épreuve : l'outil écrit
    désormais sur des comptes existants."""
    boitier = BoitierMemoire(utilisateurs=["Jean.Dupont", "legrand"], groupes=["rh"])
    _lancer(
        boitier,
        [_utilisateur("jean.dupont", "rh"), _utilisateur("legrand", ligne=3)],
        simulation=False,
    )
    assert "definir_mot_de_passe" not in [operation for operation, _ in boitier.journal_appels]
    assert boitier.mots_de_passe == {}


def test_un_compte_ambigu_ne_recoit_rien_et_le_lot_continue() -> None:
    """Ni création, ni adhésion, ni mot de passe — et les autres comptes du lot passent :
    un boîtier mal rangé ne prive pas les deux cents autres."""
    boitier = BoitierMemoire(
        utilisateurs=["Jean.Dupont", "JEAN.DUPONT"], groupes=["rh"]
    )
    _lancer(
        boitier,
        [_utilisateur("jean.dupont", "rh"), _utilisateur("legrand", ligne=3)],
        simulation=False,
    )
    assert boitier.membres.get("rh", []) == []
    assert boitier.mots_de_passe.keys() == {"legrand"}
    assert sorted(boitier.utilisateurs) == ["JEAN.DUPONT", "Jean.Dupont", "legrand"]


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


def test_un_refus_de_creation_nomme_au_journal_les_adhesions_non_tentees() -> None:
    """En v1 un refus emportait les adhésions en silence, et c'était juste : sans
    création, pas d'adhésion. En v2 un refus « existe déjà » prouve au contraire que le
    compte est là, donc que ses adhésions sont du travail légitime — et rien ne disait
    lesquelles n'avaient pas été tentées. Le rapport annonçait « 1 échec » et le journal
    ne parlait que de la création : les deux adhésions écartées n'apparaissaient nulle
    part, et l'opérateur n'avait pas de quoi les reprendre."""
    boitier = BoitierMemoire(groupes=["compta", "rh"], membres={"compta": [], "rh": []})

    def refuser_b(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "b":
            raise ErreurCommande(200, "l'utilisateur b existe déjà")

    boitier.declencheur = refuser_b
    _, evenements = _lancer(boitier, [_utilisateur("b", "compta", "rh")])
    assert (
        "b : adhésions non tentées, le compte n'ayant pas été créé — compta, rh"
        in _textes(evenements)
    )


def test_un_refus_de_creation_sans_adhesion_ne_parle_pas_d_adhesions() -> None:
    """La ligne ne doit pas s'écrire pour rien : le cas le plus fréquent d'un premier lot
    est le CSV sans colonne de groupes."""
    boitier = BoitierMemoire()

    def refuser(operation: str, _cible: str) -> None:
        if operation == "creer_utilisateur":
            raise ErreurCommande(200, "uid interdit")

    boitier.declencheur = refuser
    _, evenements = _lancer(boitier, [_utilisateur("admin")])
    assert not any("adhésions non tentées" in texte for texte in _textes(evenements))


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
    assert [
        travail.identifiant_cible
        for travail in plans[-1].plan.travaux
        if not travail.a_creer
    ] == ["dupont", "legrand"]
    # La barre reste cohérente : le total suit le plan reconstruit.
    derniere = _progressions(evenements)[-1]
    assert derniere.accomplies == derniere.total


def test_executer_transmet_les_rejets_a_la_construction_du_plan() -> None:
    """`test_un_compte_dont_la_ligne_a_ete_rejetee_n_est_pas_orphelin` (test_plan.py) ne
    prouve le câblage des rejets qu'en isolation, sur `plan.construire` directement.
    `executer` doit porter ce même paramètre à son premier appel, sans quoi un compte du
    boîtier dont la ligne a été rejetée serait annoncé orphelin à tort."""
    boitier = BoitierMemoire(utilisateurs=["martin"])
    _, evenements = _lancer(
        boitier,
        [_utilisateur("dupont")],
        rejets=[Rejet(ligne=3, identifiant="martin", motif="prenom vide")],
    )
    plans = [evenement for evenement in evenements if isinstance(evenement, PlanPret)]
    assert plans[0].plan.nombre_orphelins == 0


def test_la_reconstruction_du_plan_apres_reconnexion_transmet_aussi_les_rejets() -> None:
    """Même preuve que ci-dessus, mais sur le second appel à `construire` — celui de
    `_replanifier`, atteint après une reconnexion, jamais exercé par le test précédent."""
    boitier = BoitierMemoire(utilisateurs=["martin"])
    coupures = 0

    def couper_apres_le_premier(operation: str, cible: str) -> None:
        nonlocal coupures
        if operation == "creer_utilisateur" and cible == "legrand" and coupures == 0:
            coupures += 1
            boitier.utilisateurs.append("legrand")
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_apres_le_premier
    _, evenements = _lancer(
        boitier,
        [_utilisateur("dupont"), _utilisateur("legrand", ligne=3)],
        rejets=[Rejet(ligne=4, identifiant="martin", motif="prenom vide")],
    )
    plans = [evenement for evenement in evenements if isinstance(evenement, PlanPret)]
    assert len(plans) == 2  # le plan reconstruit après la coupure, pas le premier
    assert plans[-1].plan.nombre_orphelins == 0


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
    # Le lot ne peut pas se déclarer réussi : le rapport porte l'échec et le compte
    # à reprendre à la main.
    assert rapport.echecs != []
    creations = [
        evenement for evenement in evenements if isinstance(evenement, CreationReussie)
    ]
    assert [evenement.compte for evenement in creations] == rapport.comptes_crees


def test_coupure_pendant_le_rattachement_laisse_une_trace() -> None:
    """L'adhésion est replanifiée après reconnexion ; si la coupure se répète, le
    garde-fou des tours sans progrès ferme la boucle. L'interruption doit laisser un
    échec exploitable, et le lot s'achève sur un arrêt réseau."""
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
    # Sans cette ligne, l'inversion du comportement — la v1 finissait proprement, la v2
    # replanifie l'adhésion et bute deux fois sur la même coupure — ne serait prouvée
    # nulle part, et le test continuerait de passer en disant le contraire.
    assert rapport.motif_arret is MotifArret.RESEAU


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


def test_un_compte_refuse_n_est_pas_rejoue_apres_une_reconnexion() -> None:
    """Le compte refusé n'existe pas sur le boîtier : le plan reconstruit le remettrait
    à créer, il échouerait encore, et le rapport compterait deux fois le même échec."""
    boitier = BoitierMemoire()

    def refuser_admin_et_couper_sur_legrand(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "admin":
            raise ErreurCommande(200, "uid interdit")
        if operation == "creer_utilisateur" and cible == "legrand" and boitier.connexions == 1:
            boitier.utilisateurs.append("legrand")  # le boîtier a exécuté avant la coupure
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = refuser_admin_et_couper_sur_legrand
    rapport, _ = _lancer(boitier, [_utilisateur("admin"), _utilisateur("legrand", ligne=3)])
    appels = [cible for operation, cible in boitier.journal_appels
              if operation == "creer_utilisateur"]
    assert appels.count("admin") == 1
    assert [echec.identifiant for echec in rapport.echecs] == ["admin"]


def _lot_ou_un_compte_refuse_reapparait(graphie_relue: str) -> BoitierMemoire:
    """`USER CREATE` refusé sur `jean.dupont`, coupure, puis relecture où le boîtier rend
    ce compte sous `graphie_relue`.

    Un refus « existe déjà » est le cas le plus fréquent de la v2 : le compte est bel et
    bien là, et c'est le boîtier qui décide sous quelle casse il le rend.
    """
    boitier = BoitierMemoire(groupes=["compta"], membres={"compta": []})
    coupures: list[str] = []

    def refuser_jean_puis_couper(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "jean.dupont":
            raise ErreurCommande(200, "l'utilisateur jean.dupont existe déjà")
        if operation == "creer_utilisateur" and cible == "legrand" and not coupures:
            coupures.append(cible)
            boitier.utilisateurs.append(graphie_relue)
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = refuser_jean_puis_couper
    _lancer(boitier, [_utilisateur("jean.dupont", "compta"), _utilisateur("legrand", ligne=3)])
    return boitier


def test_le_sort_d_un_compte_refuse_ne_depend_pas_de_la_graphie_relue() -> None:
    """Un refus se retient sous la clé de rapprochement, jamais sous la graphie reçue.

    Sur la graphie identique, le plan reconstruit écarte le travail et ses adhésions ne
    partent jamais ; sur une graphie de casse différente, la comparaison de chaînes
    brutes échoue et les mêmes adhésions partent. Le sort d'une écriture dépendrait alors
    de la casse que le boîtier choisit de rendre — dans la branche dont tout le sujet est
    l'insensibilité à la casse.
    """
    rendu_tel_quel = _lot_ou_un_compte_refuse_reapparait("jean.dupont")
    rendu_sous_une_autre_casse = _lot_ou_un_compte_refuse_reapparait("Jean.Dupont")
    assert _rattachements(rendu_tel_quel) == _rattachements(rendu_sous_une_autre_casse) == []


def test_une_adhesion_refusee_ne_se_rejoue_pas_sous_une_autre_graphie() -> None:
    """Même règle pour un `USER GROUP ADDUSER` refusé : sa clé peut changer de casse
    entre deux plans, et le rapport porterait sinon deux fois le même échec — ce que la
    spec v1 interdit au paragraphe « Échec isolé »."""
    boitier = BoitierMemoire(
        utilisateurs=["jean.dupont"], groupes=["compta"], membres={"compta": []}
    )
    coupures: list[str] = []

    def refuser_compta_puis_couper(operation: str, cible: str) -> None:
        if operation == "ajouter_membre" and cible.startswith("compta/"):
            raise ErreurCommande(200, "groupe compta inconnu")
        if operation == "creer_utilisateur" and cible == "legrand" and not coupures:
            coupures.append(cible)
            # Même compte, autre graphie rendue par la relecture.
            boitier.utilisateurs[0] = "Jean.Dupont"
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = refuser_compta_puis_couper
    rapport, _ = _lancer(
        boitier, [_utilisateur("jean.dupont", "compta"), _utilisateur("legrand", ligne=3)]
    )
    refus = [echec for echec in rapport.echecs if echec.operation == "USER GROUP ADDUSER"]
    assert len(refus) == 1
    assert _rattachements(boitier) == ["compta/jean.dupont"]


def test_un_groupe_refuse_n_est_pas_rejoue_apres_une_reconnexion() -> None:
    """Même règle pour USER GROUP CREATE : un refus est signalé une fois."""
    boitier = BoitierMemoire()

    def refuser_le_groupe_et_couper_sur_alice(operation: str, cible: str) -> None:
        if operation == "creer_groupe":
            raise ErreurCommande(200, "guillemet double interdit")
        if operation == "definir_mot_de_passe" and cible == "alice":
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = refuser_le_groupe_et_couper_sur_alice
    rapport, _ = _lancer(
        boitier,
        [_utilisateur("alice", 'Groupe "A"'), _utilisateur("bob", 'Groupe "A"', ligne=3)],
    )
    assert [operation for operation, _ in boitier.journal_appels].count("creer_groupe") == 1
    creations_de_groupe = [
        echec for echec in rapport.echecs if echec.operation == "USER GROUP CREATE"
    ]
    assert len(creations_de_groupe) == 1


def test_une_coupure_sur_la_toute_premiere_ecriture_ne_fait_pas_avorter_le_lot() -> None:
    """Une coupure unique sur la première commande d'écriture, reconnectée du premier
    coup : aucune écriture n'a encore abouti, donc le plan reconstruit est forcément
    identique. Mesurer le progrès sur la taille du plan faisait lire là une pathologie
    et arrêtait le lot à zéro compte, en accusant le boîtier d'un défaut inexistant."""
    boitier = BoitierMemoire()
    coupures = 0

    def couper_la_premiere_ecriture(operation: str, _cible: str) -> None:
        nonlocal coupures
        if operation == "creer_groupe" and coupures == 0:
            coupures += 1
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_la_premiere_ecriture
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont", "compta")])
    assert coupures == 1
    assert boitier.connexions == 2
    assert rapport.interrompu is False
    assert [compte.identifiant for compte in rapport.comptes_crees] == ["dupont"]
    assert rapport.groupes_crees == ["compta"]
    assert not any("aucune écriture" in texte for texte in _textes(evenements))


def test_une_ecriture_qui_echoue_durablement_arrete_le_lot() -> None:
    """La reconnexion et les relectures passent, mais l'écriture retombe : le plan
    reconstruit est identique au précédent. Sans exigence de progrès, la boucle
    tourne indéfiniment, à `delai` près."""
    boitier = BoitierMemoire()
    tentatives = 0

    def couper_chaque_ecriture(operation: str, _cible: str) -> None:
        nonlocal tentatives
        if operation == "creer_utilisateur":
            tentatives += 1
            if tentatives > 5:
                raise RuntimeError("boucle sans fin : le lot ne s'arrête jamais")
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_chaque_ecriture
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont")])
    assert tentatives <= 2
    assert rapport.interrompu is True
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
    assert [
        travail.identifiant_cible for travail in plans[0].plan.travaux if not travail.a_creer
    ] == ["dupont"]


def test_une_adhesion_deja_posee_n_est_pas_reposee_apres_une_reconnexion() -> None:
    """L'inventaire relu après la coupure doit **servir** : le lire puis le jeter ferait
    reposer les adhésions déjà passées — membres dupliqués sur le boîtier — et ferait
    croître le total une seconde fois, après la confirmation.

    `test_la_relecture_apres_reconnexion_reconstruit_tout_l_inventaire` éprouve
    `relire_inventaire` en direct et ne reconnecte jamais : le câblage de son résultat
    dans le plan reconstruit n'est prouvé qu'ici.
    """
    boitier = BoitierMemoire(utilisateurs=["alpha"], groupes=["g1", "g2"])
    coupures: list[str] = []

    def couper_apres_le_premier_rattachement(operation: str, cible: str) -> None:
        if operation == "ajouter_membre" and cible == "g2/alpha" and not coupures:
            coupures.append(cible)
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_apres_le_premier_rattachement
    rapport, evenements = _lancer(boitier, [_utilisateur("alpha", "g1", "g2")])
    assert boitier.connexions == 2
    # g1 était posé avant la coupure : le plan reconstruit ne le replanifie pas.
    assert boitier.journal_appels.count(("ajouter_membre", "g1/alpha")) == 1
    assert boitier.membres["g1"] == [dn_de("alpha")]
    assert boitier.membres["g2"] == [dn_de("alpha")]
    assert rapport.interrompu is False
    totaux = [progression.total for progression in _progressions(evenements)]
    # Le total ne croît qu'à la confirmation ; une adhésion replanifiée à tort le ferait
    # monter une seconde fois, après elle.
    budget = max(totaux)
    assert totaux[totaux.index(budget) :] == sorted(totaux[totaux.index(budget) :], reverse=True)


def test_l_arret_est_honore_pendant_la_relecture_qui_suit_une_reconnexion() -> None:
    """La relecture de reprise est aussi longue que la première — un USER GROUP SHOW par
    groupe cité. Un bouton *Arrêter* qui ne répondrait que sur l'un des deux chemins
    serait un bouton qui ment."""
    boitier = BoitierMemoire(groupes=["g1", "g2", "g3"])
    interrupteur = _Interrupteur()

    def couper_puis_cliquer_pendant_la_relecture(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and boitier.connexions == 1:
            raise ErreurReseau("liaison perdue")
        if operation == "lister_membres" and cible == "g1" and boitier.connexions == 2:
            interrupteur.demander()

    boitier.declencheur = couper_puis_cliquer_pendant_la_relecture
    rapport, _ = _lancer(
        boitier, [_utilisateur("alpha", "g1", "g2", "g3")], arret=interrupteur
    )
    lectures = [
        cible for operation, cible in boitier.journal_appels if operation == "lister_membres"
    ]
    # Les trois du premier tour, puis la seule du second : g2 et g3 ne sont pas entamés.
    assert lectures == ["g1", "g2", "g3", "g1"]
    assert rapport.motif_arret is MotifArret.OPERATEUR


def test_rejouer_le_meme_fichier_n_emet_aucune_ecriture() -> None:
    """Zéro commande d'écriture, pas « des commandes sans effet »."""
    boitier = BoitierMemoire()
    utilisateurs = [_utilisateur("dupont", "compta"), _utilisateur("legrand", ligne=3)]
    _lancer(boitier, utilisateurs, simulation=False)
    boitier.journal_appels.clear()
    rapport, _ = _lancer(boitier, utilisateurs, simulation=False)
    assert _ecritures(boitier) == []
    assert rapport.comptes_crees == []


def test_l_idempotence_survit_a_une_difference_de_casse() -> None:
    boitier = BoitierMemoire(utilisateurs=["Jean.Dupont"], groupes=["Compta"])
    boitier.ajouter_membre("Compta", "Jean.Dupont")
    boitier.journal_appels.clear()
    _lancer(boitier, [_utilisateur("jean.dupont", "compta")], simulation=False)
    assert _ecritures(boitier) == []


def test_un_rattachement_illisible_fait_repartir_les_memes_adhesions() -> None:
    """Dégradation honnête : l'outil ne promet pas une idempotence que l'hypothèse sur
    le DN ne garantit pas — il promet qu'un rattachement raté coûte des commandes
    redondantes et jamais un dommage."""
    boitier = BoitierMemoire(
        utilisateurs=["dupont"],
        groupes=["compta"],
        membres={"compta": ("cn=forme-inattendue,dc=local",)},
    )
    _, evenements = _lancer(boitier, [_utilisateur("dupont", "compta")], simulation=False)
    assert ("ajouter_membre", "compta/dupont") in boitier.journal_appels
    (plan,) = [message.plan for message in evenements if isinstance(message, PlanPret)]
    assert plan.nombre_membres_non_rattaches == 1


def test_une_adhesion_refusee_ne_se_rejoue_pas_apres_reconnexion() -> None:
    """Le rapport porterait sinon deux fois le même refus.

    Le compte existe déjà : `compta` est refusé par le boîtier, puis la coupure survient
    sur `rh`. Le plan reconstruit après reconnexion replanifie `rh` — l'inventaire relu
    dit que l'adhésion manque — mais pas `compta`, que le boîtier a explicitement refusé.
    """
    boitier = BoitierMemoire(utilisateurs=["legrand"], groupes=["rh"])
    coupures: list[str] = []

    def saboter(operation: str, cible: str) -> None:
        if operation == "ajouter_membre" and cible == "compta/legrand":
            raise ErreurCommande(200, "groupe compta inconnu")
        if operation == "ajouter_membre" and cible == "rh/legrand" and not coupures:
            coupures.append(cible)
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = saboter
    rapport, _ = _lancer(
        boitier, [_utilisateur("legrand", "compta", "rh")], simulation=False
    )
    # Une seule tentative sur compta : c'est là qu'est la preuve du non-rejeu.
    assert boitier.journal_appels.count(("ajouter_membre", "compta/legrand")) == 1
    refus = [echec for echec in rapport.echecs if "groupe compta inconnu" in echec.motif]
    assert len(refus) == 1
    assert refus[0].operation == "USER GROUP ADDUSER"
    assert boitier.membres["rh"] == [dn_de("legrand")]


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
    # 4 + 2 lectures + (USER CREATE + USER PASSWORD + 2 ADDUSER)
    # + (USER CREATE + USER PASSWORD)
    assert _progressions(evenements)[-1] == Progression(accomplies=12, total=12)


def test_arret_definitif_gele_la_barre_sous_son_total() -> None:
    """Contrat de fin de lot : sur arrêt définitif la barre ne rejoint pas son total.
    Elle reste où le lot s'est arrêté, ce qui est le seul affichage honnête."""
    boitier = BoitierMemoire()

    def couper_le_mot_de_passe_puis_la_liaison(operation: str, _cible: str) -> None:
        if operation == "definir_mot_de_passe":
            raise ErreurReseau("liaison perdue")
        if operation == "connecter" and boitier.connexions >= 1:
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_le_mot_de_passe_puis_la_liaison
    rapport, evenements = _lancer(
        boitier, [_utilisateur("dupont"), _utilisateur("legrand", ligne=3)]
    )
    assert rapport.interrompu is True
    # 4 lectures + le seul USER CREATE parvenu à son terme, sur 4 lectures + 2 comptes.
    assert _progressions(evenements)[-1] == Progression(accomplies=5, total=8)


def test_un_recalcul_apres_reconnexion_ne_peut_que_faire_baisser_le_total() -> None:
    """Moitié de l'invariant v1 qui survit. Le total croît une fois, à la confirmation
    (`test_le_total_ne_croit_qu_une_fois_l_ecriture_confirmee`) ; passé cet instant, un
    plan reconstruit ne compte plus que le reste et la barre suit à la baisse, plutôt que
    de viser un total qu'aucune opération restante ne peut plus atteindre."""
    boitier = BoitierMemoire()

    def couper_apres_le_premier(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "legrand" and boitier.connexions == 1:
            boitier.utilisateurs.append("legrand")  # le boîtier a exécuté avant la coupure
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_apres_le_premier
    _, evenements = _lancer(boitier, [_utilisateur("dupont"), _utilisateur("legrand", ligne=3)])
    totaux = [progression.total for progression in _progressions(evenements)]
    budget = max(totaux)
    apres_la_confirmation = totaux[totaux.index(budget) :]
    assert apres_la_confirmation == sorted(apres_la_confirmation, reverse=True)
    assert totaux[-1] < budget


def test_le_total_ne_croit_qu_une_fois_l_ecriture_confirmee() -> None:
    """L'amendement de l'invariant v1 « le total ne croît jamais » survit, réduit à ce
    seul moment : juste après que l'opérateur a lu le nombre d'opérations qu'il autorise."""
    boitier = BoitierMemoire(groupes=["compta"])
    _, evenements = _lancer(boitier, [_utilisateur("dupont", "compta")], simulation=False)
    totaux = [progression.total for progression in _progressions(evenements)]
    (plan,) = [message.plan for message in evenements if isinstance(message, PlanPret)]
    assert totaux[0] == LECTURES_DE_BASE + 1  # le seul groupe cité existe déjà
    assert totaux[-1] == totaux[0] + plan.nombre_operations()
    assert totaux == sorted(totaux)


def test_une_politique_sous_le_plancher_arrete_avant_toute_ecriture() -> None:
    """Le plancher lu sur le boîtier visé fait foi : une politique plus faible ne peut
    pas partir. Sans cette garde, chaque USER PASSWORD serait refusé un par un, et le
    plancher mis en cache par un lancement antérieur suffirait à laisser passer le lot."""
    boitier = BoitierMemoire(
        plancher=PlancherPolitique(longueur_min=24, nombre_classes_min=4, entropie_min=0)
    )
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont", "compta")])
    assert _ecritures(boitier) == []
    assert rapport.comptes_crees == []
    assert rapport.interrompu is True
    refus = [
        evenement for evenement in evenements if isinstance(evenement, PolitiqueRefusee)
    ]
    # Les violations circulent telles que `violations()` les rend : la fenêtre les
    # affiche mot pour mot, elle n'a rien à reconstruire ni à interpréter.
    assert refus[0].violations == tuple(motdepasse.violations(POLITIQUE, boitier.plancher))
    assert refus[0].plancher == boitier.plancher


def test_le_plancher_est_emis_avant_le_refus_de_la_politique() -> None:
    """La fenêtre doit pouvoir montrer le plancher réellement lu à côté du refus."""
    boitier = BoitierMemoire(
        plancher=PlancherPolitique(longueur_min=24, nombre_classes_min=4, entropie_min=0)
    )
    _, evenements = _lancer(boitier, [_utilisateur("dupont")])
    types = [type(evenement) for evenement in evenements]
    assert types.index(PolitiqueLue) < types.index(PolitiqueRefusee)
    assert types[-1] is Termine


def test_la_simulation_refuse_aussi_une_politique_sous_le_plancher() -> None:
    """La lecture a lieu dans les deux modes : le refus aussi, sans quoi la simulation
    afficherait un plan que le lot réel ne pourrait jamais appliquer."""
    boitier = BoitierMemoire(
        plancher=PlancherPolitique(longueur_min=24, nombre_classes_min=4, entropie_min=0)
    )
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont")], simulation=True)
    assert any(isinstance(evenement, PolitiqueRefusee) for evenement in evenements)
    assert not any(isinstance(evenement, PlanPret) for evenement in evenements)
    assert rapport.interrompu is True


def test_une_politique_qui_tient_le_plancher_ne_refuse_rien() -> None:
    _, evenements = _lancer(BoitierMemoire(), [_utilisateur("dupont")])
    assert not any(isinstance(evenement, PolitiqueRefusee) for evenement in evenements)


def test_un_lot_mene_a_son_terme_ne_porte_aucun_motif_d_arret() -> None:
    rapport, _ = _lancer(BoitierMemoire(), [_utilisateur("dupont")])
    assert rapport.interrompu is False
    assert rapport.motif_arret is None


def test_une_coupure_reseau_irrecuperable_est_un_arret_reseau() -> None:
    """Relancer le lot suffit : le motif doit le dire sans qu'on lise le journal,
    qui fait des centaines de lignes sur un lot de deux cents comptes."""
    boitier = BoitierMemoire()

    def couper_toujours(operation: str, _cible: str) -> None:
        if operation in {"creer_utilisateur", "connecter"} and boitier.connexions >= 1:
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_toujours
    rapport, _ = _lancer(boitier, [_utilisateur("dupont")])
    assert rapport.interrompu is True
    assert rapport.motif_arret is MotifArret.RESEAU


def test_une_relecture_impossible_est_un_arret_reseau() -> None:
    boitier = BoitierMemoire()

    def couper(operation: str, _cible: str) -> None:
        if operation == "creer_utilisateur":
            raise ErreurReseau("liaison perdue")
        if operation == "lister_utilisateurs" and boitier.connexions >= 2:
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper
    rapport, _ = _lancer(boitier, [_utilisateur("dupont")])
    assert rapport.motif_arret is MotifArret.RESEAU


def test_une_erreur_fatale_est_un_arret_fatal() -> None:
    """L'opérateur doit corriger quelque chose : relancer tel quel ne donnerait rien."""
    boitier = BoitierMemoire()

    def refuser_l_authentification(operation: str, _cible: str) -> None:
        if operation == "connecter":
            raise ErreurFatale("authentification refusée")

    boitier.declencheur = refuser_l_authentification
    rapport, _ = _lancer(boitier, [_utilisateur("dupont")])
    assert rapport.interrompu is True
    assert rapport.motif_arret is MotifArret.FATAL


def test_une_politique_refusee_est_un_arret_fatal() -> None:
    """Il y a quelque chose à corriger avant de relancer : la politique."""
    boitier = BoitierMemoire(
        plancher=PlancherPolitique(longueur_min=24, nombre_classes_min=4, entropie_min=0)
    )
    rapport, _ = _lancer(boitier, [_utilisateur("dupont")])
    assert rapport.motif_arret is MotifArret.FATAL


def test_interrompu_et_motif_d_arret_restent_coherents() -> None:
    """Les deux champs disent la même chose : un motif posé implique un lot interrompu."""
    boitier = BoitierMemoire()

    def couper_toujours(operation: str, _cible: str) -> None:
        if operation in {"creer_utilisateur", "connecter"} and boitier.connexions >= 1:
            raise ErreurReseau("liaison perdue")

    boitier.declencheur = couper_toujours
    interrompu, _ = _lancer(boitier, [_utilisateur("dupont")])
    complet, _ = _lancer(BoitierMemoire(), [_utilisateur("dupont")])
    for rapport in (interrompu, complet):
        assert rapport.interrompu is (rapport.motif_arret is not None)


# --- arrêt demandé par l'opérateur ----------------------------------------


def test_le_compte_en_cours_va_jusqu_au_bout_et_le_suivant_n_est_pas_entame() -> None:
    """Tout l'intérêt de l'arrêt : il remplace la fermeture brutale de la fenêtre, qui
    coupait le fil n'importe où — y compris entre USER CREATE et USER PASSWORD, laissant
    un compte sans mot de passe utilisable qu'aucun relancement ne répare."""
    boitier = BoitierMemoire()
    interrupteur = _Interrupteur()

    def cliquer_pendant_la_creation(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "dupont":
            interrupteur.demander()

    boitier.declencheur = cliquer_pendant_la_creation
    rapport, _ = _lancer(
        boitier,
        [_utilisateur("dupont", "compta"), _utilisateur("martin")],
        arret=interrupteur,
    )
    assert boitier.utilisateurs == ["dupont"]
    assert boitier.mots_de_passe == {"dupont": "MotDePasse1!"}
    assert boitier.membres == {"compta": [dn_de("dupont")]}
    assert rapport.interrompu is True
    assert rapport.motif_arret is MotifArret.OPERATEUR


def test_le_rapport_d_un_arret_demande_dit_ce_que_le_plan_prevoyait() -> None:
    """Le bilan doit pouvoir dire combien de comptes n'ont pas été touchés, et non
    seulement combien sont nés."""
    boitier = BoitierMemoire()
    interrupteur = _Interrupteur()

    def cliquer_au_premier_compte(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "dupont":
            interrupteur.demander()

    boitier.declencheur = cliquer_au_premier_compte
    rapport, _ = _lancer(
        boitier,
        [_utilisateur("dupont"), _utilisateur("martin"), _utilisateur("legrand")],
        arret=interrupteur,
    )
    assert rapport.comptes_prevus == 3
    assert [compte.identifiant for compte in rapport.comptes_crees] == ["dupont"]


def test_un_arret_demande_n_entame_pas_le_groupe_suivant() -> None:
    boitier = BoitierMemoire()
    interrupteur = _Interrupteur()

    def cliquer_pendant_le_premier_groupe(operation: str, cible: str) -> None:
        if operation == "creer_groupe" and cible == "compta":
            interrupteur.demander()

    boitier.declencheur = cliquer_pendant_le_premier_groupe
    rapport, _ = _lancer(
        boitier,
        [_utilisateur("dupont", "compta"), _utilisateur("martin", "rh")],
        arret=interrupteur,
    )
    assert boitier.groupes == ["compta"]
    assert boitier.utilisateurs == []
    assert rapport.motif_arret is MotifArret.OPERATEUR


def test_l_arret_demande_pendant_une_simulation_est_pris_en_compte() -> None:
    """La simulation ne fait que lire, mais lire prend aussi du temps : un bouton qui ne
    réagirait pas dans un cas sur deux serait déroutant."""
    boitier = BoitierMemoire()
    rapport, _ = _lancer(
        boitier,
        [_utilisateur("dupont")],
        simulation=True,
        arret=_Interrupteur(demande=True),
    )
    assert rapport.interrompu is True
    assert rapport.motif_arret is MotifArret.OPERATEUR
    assert _ecritures(boitier) == []


def test_un_arret_demande_avant_la_premiere_ecriture_ne_pose_pas_la_confirmation() -> None:
    """Demander l'autorisation d'écrire un lot que l'opérateur vient d'arrêter n'aurait
    aucun sens, et rien ne doit partir."""
    boitier = BoitierMemoire()
    questions: list[Plan] = []

    def noter(plan: Plan) -> bool:
        questions.append(plan)
        return True

    rapport, _ = _lancer(
        boitier,
        [_utilisateur("dupont", "compta")],
        confirmer=noter,
        arret=_Interrupteur(demande=True),
    )
    assert questions == []
    assert _ecritures(boitier) == []
    assert rapport.motif_arret is MotifArret.OPERATEUR


def test_la_barre_gele_sous_son_total_sur_un_arret_demande() -> None:
    """Contrat de progression : la barre ne ment pas en s'achevant. Son total ne croît
    qu'une fois, à la confirmation de l'écriture — jamais après, et jamais sur un arrêt.
    C'est `rapport.interrompu` qui dit si le lot est allé au bout."""
    boitier = BoitierMemoire()
    interrupteur = _Interrupteur()

    def cliquer_au_premier_compte(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "dupont":
            interrupteur.demander()

    boitier.declencheur = cliquer_au_premier_compte
    _, evenements = _lancer(
        boitier,
        [_utilisateur("dupont"), _utilisateur("martin")],
        arret=interrupteur,
    )
    progressions = _progressions(evenements)
    assert progressions[-1].accomplies < progressions[-1].total
    totaux = [progression.total for progression in progressions]
    assert max(totaux) == totaux[-1]


def test_l_arret_demande_laisse_une_ligne_de_journal() -> None:
    """Le journal est la seule trace : il doit dire que le lot s'est arrêté sur ordre,
    et non sur une panne."""
    boitier = BoitierMemoire()
    _, evenements = _lancer(
        boitier, [_utilisateur("dupont")], arret=_Interrupteur(demande=True)
    )
    assert any("arrêt demandé" in texte for texte in _textes(evenements))


def test_l_arret_pendant_l_inventaire_ne_construit_aucun_plan() -> None:
    """Une lecture interrompue ne construit aucun plan et n'écrit rien ; son bilan est
    celui d'un arrêt demandé à zéro compte créé, et son journal ne parle d'aucun compte
    mené à son terme — il n'y en avait pas."""
    boitier = BoitierMemoire(groupes=["compta", "rh"])
    interrupteur = _Interrupteur()

    def arreter_apres_la_premiere_lecture(operation: str, cible: str) -> None:
        if operation == "lister_membres" and cible == "compta":
            interrupteur.demander()

    boitier.declencheur = arreter_apres_la_premiere_lecture
    rapport, evenements = _lancer(
        boitier,
        [_utilisateur("dupont", "compta", "rh")],
        simulation=False,
        arret=interrupteur,
    )
    assert ("lister_membres", "rh") not in boitier.journal_appels
    assert not [message for message in evenements if isinstance(message, PlanPret)]
    assert rapport.motif_arret is MotifArret.OPERATEUR
    assert rapport.comptes_crees == []
    assert _ecritures(boitier) == []
    (ligne,) = [texte for texte in _textes(evenements) if texte.startswith("arrêt demandé")]
    assert "aucun plan n'a été construit" in ligne
    assert "le compte en cours" not in ligne


def test_l_arret_juste_apres_le_plan_ne_pretend_pas_qu_un_compte_est_alle_a_son_terme() -> None:
    """Seul point d'arrêt qu'une simulation atteint, et atteignable en lot réel avant la
    confirmation : le plan existe, mais aucun compte n'a encore été créé. Le journal ne
    doit pas prétendre qu'un compte en cours est allé à son terme — il n'y en avait pas."""
    boitier = BoitierMemoire()
    rapport, evenements = _lancer(
        boitier,
        [_utilisateur("dupont")],
        simulation=True,
        arret=_Interrupteur(demande=True),
    )
    assert rapport.motif_arret is MotifArret.OPERATEUR
    assert rapport.comptes_crees == []
    assert _ecritures(boitier) == []
    (ligne,) = [texte for texte in _textes(evenements) if texte.startswith("arrêt demandé")]
    assert "le compte en cours" not in ligne


def test_l_arret_apres_une_adhesion_sur_un_compte_existant_ne_pretend_pas_de_creation() -> None:
    """Une écriture a bien eu lieu — l'ADDUSER sur dupont, déjà présent — sans qu'aucun
    compte n'ait été créé : le second message reste celui qui s'applique, et non « avant
    la première écriture », prédicat que ce chemin met en défaut."""
    boitier = BoitierMemoire(utilisateurs=["dupont"], groupes=["compta"])
    interrupteur = _Interrupteur()

    def arreter_apres_l_adhesion_de_dupont(operation: str, cible: str) -> None:
        if operation == "ajouter_membre" and cible == "compta/dupont":
            interrupteur.demander()

    boitier.declencheur = arreter_apres_l_adhesion_de_dupont
    rapport, evenements = _lancer(
        boitier,
        [_utilisateur("dupont", "compta"), _utilisateur("martin")],
        arret=interrupteur,
    )
    assert boitier.membres["compta"] == [dn_de("dupont")]
    assert rapport.motif_arret is MotifArret.OPERATEUR
    assert rapport.comptes_crees == []
    (ligne,) = [texte for texte in _textes(evenements) if texte.startswith("arrêt demandé")]
    assert "aucun compte n'a encore été créé" in ligne
    assert "le compte en cours" not in ligne


def test_l_arret_apres_un_compte_cree_dit_qu_il_est_alle_a_son_terme() -> None:
    """Pendant du test précédent : ce troisième message n'était couvert par aucun test —
    seule son absence l'était, dans les deux autres cas."""
    boitier = BoitierMemoire()
    interrupteur = _Interrupteur()

    def arreter_apres_la_creation_de_dupont(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "dupont":
            interrupteur.demander()

    boitier.declencheur = arreter_apres_la_creation_de_dupont
    rapport, evenements = _lancer(
        boitier,
        [_utilisateur("dupont"), _utilisateur("martin")],
        arret=interrupteur,
    )
    assert rapport.comptes_crees != []
    assert rapport.motif_arret is MotifArret.OPERATEUR
    (ligne,) = [texte for texte in _textes(evenements) if texte.startswith("arrêt demandé")]
    assert "le compte en cours est allé à son terme" in ligne


def test_sans_demande_d_arret_le_lot_va_jusqu_au_bout() -> None:
    """La valeur par défaut ne doit jamais arrêter quoi que ce soit : c'est le sens sûr,
    l'inverse d'une confirmation par défaut."""
    boitier = BoitierMemoire()
    rapport = executer(
        boitier,
        [_utilisateur("dupont"), _utilisateur("martin")],
        POLITIQUE,
        simulation=False,
        emettre=lambda _evenement: None,
        confirmer=lambda _plan: True,
        patience=PATIENCE,
        generer_mot_de_passe=lambda _politique: "MotDePasse1!",
    )
    assert boitier.utilisateurs == ["dupont", "martin"]
    assert rapport.interrompu is False


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


def test_erreur_fatale_a_la_connexion_initiale_arrete_sans_reconnecter() -> None:
    """Un mot de passe d'administration faux ne doit jamais déclencher de réessai :
    chaque tentative de connexion alimente le verrouillage anti-bruteforce."""
    boitier = BoitierMemoire()

    def refuser_l_authentification(operation: str, _cible: str) -> None:
        if operation == "connecter":
            raise ErreurFatale("authentification refusée")

    boitier.declencheur = refuser_l_authentification
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont")])
    assert rapport.interrompu is True
    assert boitier.connexions == 0
    assert [operation for operation, _ in boitier.journal_appels].count("connecter") == 1
    assert any(isinstance(evenement, Termine) for evenement in evenements)
    assert any("corrigez" in texte for texte in _textes(evenements))


def test_erreur_fatale_en_cours_d_ecriture_arrete_sans_reconnecter() -> None:
    """Une ErreurFatale surgie pendant l'écriture ne doit provoquer aucune tentative
    de reconnexion, contrairement à une ErreurReseau."""
    boitier = BoitierMemoire()

    def refuser_legrand(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "legrand":
            raise ErreurFatale("configuration incomplète")

    boitier.declencheur = refuser_legrand
    rapport, evenements = _lancer(
        boitier, [_utilisateur("dupont"), _utilisateur("legrand", ligne=3)]
    )
    assert rapport.interrompu is True
    assert [compte.identifiant for compte in rapport.comptes_crees] == ["dupont"]
    assert boitier.connexions == 1
    assert [operation for operation, _ in boitier.journal_appels].count("connecter") == 1
    assert any(isinstance(evenement, Termine) for evenement in evenements)
    assert any("corrigez" in texte for texte in _textes(evenements))


def test_erreur_fatale_a_la_reconnexion_n_essaie_qu_une_fois() -> None:
    """Coupure réseau puis identifiants devenus invalides : un seul appel de
    reconnexion, jamais les trois tentatives prévues pour une panne réseau."""
    boitier = BoitierMemoire()
    appels_apres_coupure = 0

    def couper_puis_refuser_la_reconnexion(operation: str, cible: str) -> None:
        nonlocal appels_apres_coupure
        if operation == "creer_utilisateur" and cible == "dupont" and boitier.connexions == 1:
            raise ErreurReseau("liaison perdue")
        if operation == "connecter" and boitier.connexions >= 1:
            appels_apres_coupure += 1
            raise ErreurFatale("authentification refusée")

    boitier.declencheur = couper_puis_refuser_la_reconnexion
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont")])
    assert appels_apres_coupure == 1
    assert rapport.interrompu is True
    assert boitier.connexions == 1
    assert any(isinstance(evenement, Termine) for evenement in evenements)
    assert any("corrigez" in texte for texte in _textes(evenements))


def test_erreur_fatale_pendant_la_replanification_arrete_net() -> None:
    """La reconnexion réussit, mais la relecture qui suit révèle une configuration
    incomplète : arrêt net, message d'arrêt fatal, pas un « relecture impossible »
    générique qui laisserait croire à une simple panne réseau."""
    boitier = BoitierMemoire()

    def couper_puis_bloquer_la_relecture(operation: str, cible: str) -> None:
        if operation == "creer_utilisateur" and cible == "dupont" and boitier.connexions == 1:
            raise ErreurReseau("liaison perdue")
        if operation == "lister_utilisateurs" and boitier.connexions >= 2:
            raise ErreurFatale("configuration incomplète")

    boitier.declencheur = couper_puis_bloquer_la_relecture
    rapport, evenements = _lancer(boitier, [_utilisateur("dupont")])
    assert rapport.interrompu is True
    assert any(isinstance(evenement, Termine) for evenement in evenements)
    assert any("corrigez" in texte for texte in _textes(evenements))
