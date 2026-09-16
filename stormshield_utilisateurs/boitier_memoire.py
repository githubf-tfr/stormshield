"""Boîtier en mémoire : support de la totalité des tests métier, aucun réseau."""

from collections.abc import Callable, Iterable

from stormshield_utilisateurs.boitier import ErreurCommande
from stormshield_utilisateurs.modele import PlancherPolitique

PLANCHER_PAR_DEFAUT = PlancherPolitique(longueur_min=12, nombre_classes_min=3, entropie_min=0)


def _sans_panne(operation: str, cible: str) -> None:
    """Déclencheur neutre ; les tests le remplacent pour injecter une panne."""


class BoitierMemoire:
    """Implémente le Protocol Boitier contre un état en mémoire."""

    def __init__(
        self,
        utilisateurs: Iterable[str] = (),
        groupes: Iterable[str] = (),
        annuaires: Iterable[str] = ("interne.local",),
        plancher: PlancherPolitique = PLANCHER_PAR_DEFAUT,
    ) -> None:
        self.utilisateurs: list[str] = list(utilisateurs)
        self.groupes: list[str] = list(groupes)
        self.annuaires: list[str] = list(annuaires)
        self.plancher = plancher
        self.membres: dict[str, list[str]] = {}
        self.mots_de_passe: dict[str, str] = {}
        self.connecte = False
        self.connexions = 0
        self.journal_appels: list[tuple[str, str]] = []
        self.declencheur: Callable[[str, str], None] = _sans_panne
        self._annuaire_en_attente: str | None = None

    def _appel(self, operation: str, cible: str = "") -> None:
        self.journal_appels.append((operation, cible))
        self.declencheur(operation, cible)

    def connecter(self) -> None:
        self._appel("connecter")
        self.connecte = True
        self.connexions += 1

    def deconnecter(self) -> None:
        self._appel("deconnecter")
        self.connecte = False

    def lister_annuaires(self) -> list[str]:
        self._appel("lister_annuaires")
        return list(self.annuaires)

    def initialiser_annuaire(
        self, domainname: str, organisation: str, dc: str, mot_de_passe: str
    ) -> None:
        del organisation, dc, mot_de_passe
        self._appel("initialiser_annuaire", domainname)
        if self.annuaires:
            raise ErreurCommande(200, "un annuaire existe déjà")
        self._annuaire_en_attente = domainname

    def activer_annuaire(self) -> None:
        self._appel("activer_annuaire")
        if self._annuaire_en_attente is None:
            raise ErreurCommande(200, "aucun annuaire à activer")
        self.annuaires.append(self._annuaire_en_attente)
        self._annuaire_en_attente = None

    def lire_politique(self) -> PlancherPolitique:
        self._appel("lire_politique")
        return self.plancher

    def lister_utilisateurs(self) -> list[str]:
        self._appel("lister_utilisateurs")
        return list(self.utilisateurs)

    def lister_groupes(self) -> list[str]:
        self._appel("lister_groupes")
        return list(self.groupes)

    def creer_groupe(self, nom: str) -> None:
        self._appel("creer_groupe", nom)
        if nom in self.groupes:
            raise ErreurCommande(200, f"le groupe {nom} existe déjà")
        if '"' in nom:
            # Le nom est transmis verbatim entre guillemets doubles : un guillemet
            # dans le nom ne peut pas passer. Échec de création, pas rejet de ligne.
            raise ErreurCommande(200, "guillemet double interdit dans un nom de groupe")
        self.groupes.append(nom)

    def creer_utilisateur(self, identifiant: str, nom: str, prenom: str, domaine: str) -> None:
        del nom, prenom, domaine
        self._appel("creer_utilisateur", identifiant)
        if identifiant in self.utilisateurs:
            raise ErreurCommande(200, f"l'utilisateur {identifiant} existe déjà")
        self.utilisateurs.append(identifiant)

    def definir_mot_de_passe(self, identifiant: str, mot_de_passe: str) -> None:
        self._appel("definir_mot_de_passe", identifiant)
        if identifiant not in self.utilisateurs:
            raise ErreurCommande(200, f"utilisateur {identifiant} inconnu")
        self.mots_de_passe[identifiant] = mot_de_passe

    def ajouter_membre(self, groupe: str, identifiant: str) -> None:
        self._appel("ajouter_membre", f"{groupe}/{identifiant}")
        if groupe not in self.groupes:
            raise ErreurCommande(200, f"groupe {groupe} inconnu")
        self.membres.setdefault(groupe, []).append(identifiant)
