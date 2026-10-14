"""Les **règles** de notification du jeu : notifier ou pas, et jusqu'où (`j-notifications-jeu`).

Module **pur** : aucune base, aucun réseau, aucune horloge implicite — on lui passe les réglages du
joueur, ce que la partie a déjà produit, et l'instant. Il rend une :class:`Decision` qui porte
*toujours* son motif. C'est voulu, et c'est le cœur du lot : les trois critères d'acceptation
(chaque genre désactivable, silence nocturne respecté, plafond par partie jamais dépassé) se
vérifient ici, par des tests qui n'ont besoin ni de Postgres ni de serveur SMTP.

**Le risque que ce module existe pour écarter** (nommé par la fiche du lot) : notifier chaque tour.
Un jeu qui sonne à chaque coup se fait couper au niveau du système — et on perd alors *aussi* les
invitations, les seules notifications qui comptent vraiment. D'où trois freins qui se cumulent, du
plus doux au plus dur :

1. **l'anti-doublon** — on ne redit pas « c'est ton tour » tant que la précédente n'a pas été lue.
   C'est le frein qui fait le plus de travail en pratique : un joueur devant son écran ne reçoit
   qu'une notification par absence, pas une par coup ;
2. **le plafond par genre et par partie** — même lues, les répétitions s'épuisent
   (:data:`PLAFOND_PAR_GENRE`) ;
3. **le plafond global de la partie** (:data:`PLAFOND_PAR_PARTIE`) — la garantie que le critère
   « aucune partie ne produit plus de notifications que le plafond fixé » tient *quoi qu'il arrive*,
   y compris si un genre futur oubliait son propre plafond. Il est **inférieur à la somme** des
   plafonds par genre : c'est lui qui mord en dernier, et il mord toujours.

Le **silence nocturne**, lui, ne refuse rien : il enregistre sans réveiller. Pendant la fenêtre, la
notification existe (elle sera lue au matin — on ne perd pas une invitation parce qu'elle est
arrivée à 23 h) mais aucun relais ne part et l'écran ne la sonne pas. C'est la lecture retenue du
critère « le silence nocturne est respecté, y compris pour les invitations » : l'invitation reste
visible dans l'application, son **e-mail** attend le réveil.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, time
from zoneinfo import ZoneInfo

from pbm_api.models.notifications import (
    NOTIF_ADVERSAIRE_REVENU,
    NOTIF_ADVERSAIRE_TROUVE,
    NOTIF_GENRES,
    NOTIF_INVITATION_RECUE,
    NOTIF_PARTIE_FORFAIT,
    NOTIF_TEMPS_BIENTOT_ECOULE,
    NOTIF_TON_TOUR,
)

# --- Plafonds ---------------------------------------------------------------------------------

#: **Le** plafond du critère d'acceptation : nombre maximal de notifications qu'une partie peut
#: produire **pour un même destinataire**, tous genres confondus. Dix sur une partie entière, c'est
#: déjà beaucoup pour un enfant ; au-delà, ce n'est plus une information mais une sonnerie.
PLAFOND_PAR_PARTIE = 10

#: Plafonds par genre, **par partie et par destinataire**. Leur somme (11) dépasse délibérément
#: :data:`PLAFOND_PAR_PARTIE` : aucun genre ne peut à lui seul épuiser la partie, et le plafond
#: global reste celui qui tranche. Un genre absent de cette table n'a pas de plafond propre — seul
#: le plafond global le borne (c'est le cas de l'invitation, qui n'a pas de partie).
PLAFOND_PAR_GENRE: Mapping[str, int] = {
    NOTIF_ADVERSAIRE_TROUVE: 1,  # une partie n'est trouvée qu'une fois
    NOTIF_TON_TOUR: 4,  # le genre à risque : quatre rappels sur une partie, pas un par coup
    NOTIF_TEMPS_BIENTOT_ECOULE: 3,
    NOTIF_ADVERSAIRE_REVENU: 2,
    NOTIF_PARTIE_FORFAIT: 1,  # une partie ne se termine qu'une fois
}

#: Genres pour lesquels un relais **e-mail** est légitime. Un seul, et c'est un choix de la fiche du
#: lot : une invitation peut attendre des heures, donc elle mérite un canal asynchrone. « C'est ton
#: tour » par e-mail serait du harcèlement par un autre moyen.
GENRES_RELAIS_EMAIL: frozenset[str] = frozenset({NOTIF_INVITATION_RECUE})

# --- Défauts des réglages ---------------------------------------------------------------------

#: Début du silence nocturne par défaut (heure locale du joueur).
SILENCE_DEBUT_DEFAUT = time(21, 0)
#: Fin du silence nocturne par défaut. La fenêtre franchit minuit — c'est le cas normal.
SILENCE_FIN_DEFAUT = time(7, 0)
#: Fuseau par défaut : le produit est francophone et privé (D11), ses joueurs sont en France.
FUSEAU_DEFAUT = "Europe/Paris"


class GenreInconnu(ValueError):
    """Genre de notification hors du vocabulaire (:data:`NOTIF_GENRES`) — un bug d'appelant.

    On lève plutôt que d'enregistrer : une notification dont l'écran ne sait pas fabriquer la
    phrase est une ligne illisible en base, et un repli silencieux de plus.
    """


@dataclass(frozen=True)
class Reglages:
    """Les réglages d'un compte, vus par les règles — **sans** la base.

    Les défauts sont ceux d'un compte qui n'a jamais ouvert ses réglages : tout est activé, et le
    silence nocturne **l'est aussi** (21 h → 7 h). Le jeu est celui d'un enfant de onze ans : il
    vaut mieux avoir à demander « réveille-moi » que d'avoir été réveillé.
    """

    genres_desactives: frozenset[str] = frozenset()
    silence_actif: bool = True
    silence_debut: time = SILENCE_DEBUT_DEFAUT
    silence_fin: time = SILENCE_FIN_DEFAUT
    fuseau: str = FUSEAU_DEFAUT
    relais_email_invitation: bool = True
    relais_push: bool = True


@dataclass(frozen=True)
class Compteurs:
    """Ce que la partie a **déjà** produit pour ce destinataire — l'entrée des plafonds.

    ``total_partie`` : toutes genres confondus. ``par_genre`` : le détail. ``doublon_non_lu`` : une
    notification du même genre, sur la même partie, attend déjà d'être lue. Pour une invitation
    reçue (sans partie), ``total_partie`` et ``par_genre`` valent zéro : aucun plafond de partie ne
    s'y applique — une invitation est un événement unique, pas une répétition.
    """

    total_partie: int = 0
    par_genre: Mapping[str, int] = field(default_factory=dict)
    doublon_non_lu: bool = False


@dataclass(frozen=True)
class Decision:
    """Ce que les règles répondent — et **pourquoi**, toujours.

    ``enregistrer`` : la notification entre dans l'application. ``silencieuse`` : elle y entre sans
    alerte (silence nocturne). ``relais_email`` / ``relais_push`` : les canaux hors application
    autorisés pour cette émission-là. ``motif`` est renseigné dans tous les cas, refus **comme**
    acceptation : un refus muet serait indébogable, et le service le journalise tel quel.
    """

    enregistrer: bool
    silencieuse: bool
    relais_email: bool
    relais_push: bool
    motif: str


def _refus(motif: str) -> Decision:
    """Fabrique un refus complet : rien n'est enregistré, rien n'est relayé, le motif est dit."""
    return Decision(
        enregistrer=False, silencieuse=False, relais_email=False, relais_push=False, motif=motif
    )


def dans_silence_nocturne(reglages: Reglages, instant: datetime) -> bool:
    """Vrai si ``instant`` tombe dans la fenêtre de silence, **à l'heure locale du joueur**.

    ``instant`` doit être conscient du fuseau (UTC en production) : il est converti dans
    ``reglages.fuseau`` avant comparaison, parce que « 21 h » veut dire 21 h chez le joueur.

    La fenêtre est **inclusive au début, exclusive à la fin** (``[debut, fin[``) et peut franchir
    minuit — c'est le cas par défaut (21 h → 7 h). Une fenêtre dont le début égale la fin est
    traitée comme **vide** (aucun silence) : « de 21 h à 21 h » ne peut pas vouloir dire « toute la
    journée », ce serait désactiver les notifications par un chemin détourné — pour ça il y a
    ``genres_desactives``.
    """
    if not reglages.silence_actif:
        return False
    if reglages.silence_debut == reglages.silence_fin:
        return False
    locale = instant.astimezone(ZoneInfo(reglages.fuseau)).time()
    if reglages.silence_debut < reglages.silence_fin:
        # Fenêtre dans la même journée (ex. 13 h → 14 h).
        return reglages.silence_debut <= locale < reglages.silence_fin
    # Fenêtre à cheval sur minuit (ex. 21 h → 7 h) : l'un OU l'autre côté suffit.
    return locale >= reglages.silence_debut or locale < reglages.silence_fin


def plafond_du_genre(genre: str) -> int | None:
    """Le plafond propre au genre (par partie et destinataire), ou ``None`` s'il n'en a pas."""
    return PLAFOND_PAR_GENRE.get(genre)


def decider(genre: str, *, reglages: Reglages, compteurs: Compteurs, instant: datetime) -> Decision:
    """Décide si l'on notifie ``genre``, et par quels canaux — la seule porte d'entrée des règles.

    L'ordre des contrôles n'est pas décoratif ; il est le produit des trois critères du lot :

    1. **genre inconnu** → :class:`GenreInconnu` (bug d'appelant, jamais enregistré) ;
    2. **genre désactivé par le joueur** → refus. Chaque genre se coupe séparément, et sa coupure
       prime sur tout le reste : c'est son réglage, pas une suggestion ;
    3. **doublon non lu** → refus. Le frein anti-sonnerie ;
    4. **plafond du genre**, puis **plafond de la partie** → refus. Dans cet ordre pour que le motif
       nomme la cause la plus précise ;
    5. **silence nocturne** → on enregistre, en silence, sans aucun relais ;
    6. sinon → on enregistre, et on relaie sur les canaux autorisés (e-mail pour l'invitation
       seulement, notification web si le joueur l'accepte).
    """
    if genre not in NOTIF_GENRES:
        raise GenreInconnu(f"Genre de notification inconnu : {genre!r}.")

    if genre in reglages.genres_desactives:
        return _refus(f"genre « {genre} » désactivé par le joueur")

    if compteurs.doublon_non_lu:
        return _refus(f"une notification « {genre} » de cette partie attend déjà d'être lue")

    plafond_genre = plafond_du_genre(genre)
    deja_genre = compteurs.par_genre.get(genre, 0)
    if plafond_genre is not None and deja_genre >= plafond_genre:
        return _refus(
            f"plafond du genre « {genre} » atteint pour cette partie "
            f"({deja_genre}/{plafond_genre})"
        )

    if compteurs.total_partie >= PLAFOND_PAR_PARTIE:
        return _refus(
            f"plafond de la partie atteint ({compteurs.total_partie}/{PLAFOND_PAR_PARTIE})"
        )

    if dans_silence_nocturne(reglages, instant):
        return Decision(
            enregistrer=True,
            silencieuse=True,
            relais_email=False,
            relais_push=False,
            motif="silence nocturne : enregistrée sans alerte ni relais",
        )

    return Decision(
        enregistrer=True,
        silencieuse=False,
        relais_email=genre in GENRES_RELAIS_EMAIL and reglages.relais_email_invitation,
        relais_push=reglages.relais_push,
        motif="notifiée",
    )
