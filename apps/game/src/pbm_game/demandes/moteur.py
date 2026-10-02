"""Le **moteur de résolution suspendable** — résout la pile d'effets, et sait s'arrêter.

Module **pur** (aucune E/S). C'est l'extension promise par ``pbm_game.effets.pile`` : là où
:func:`~pbm_game.effets.pile.resoudre_pile` résout la pile *d'un seul trait*, ici la résolution
peut **se suspendre** quand un effet réclame une décision (via le
:class:`~pbm_game.demandes.gestionnaire.Gestionnaire`), poser la demande dans l'état, et rendre la
main. Le joueur répond plus tard (:func:`repondre`), ou le délai expire (:func:`expirer`) ; la
résolution **reprend** là où elle s'était arrêtée.

**Le re-déroulé, et pourquoi il est correct.** À la reprise, on ne « continue » pas une fonction
Python figée en mémoire (ce serait insérialisable, donc perdu au premier F5). On **re-déroule** la
pile suspendue depuis le début de l'effet suspendu, le gestionnaire fournissant les réponses déjà
données. Pour que ce re-déroulé soit identique :

* l'**état** progresse par effet : l'effet qui se suspend voit son travail partiel **jeté** (on
  renvoie l'état des effets déjà terminés, pas le sien) ;
* l'**aléatoire** est **ramené en arrière** avant l'effet suspendu (:meth:`Rng.restaurer`) : à la
  reprise, ses éventuels tirages (pile ou face) retombent à l'identique — aucun tirage compté deux
  fois dans le journal d'anti-triche ;
* les **décisions** gardent un indice global stable (``base`` + compteur du gestionnaire), donc une
  réponse s'apparie toujours à la bonne décision.

Chaque effet terminé émet ses événements **une seule fois** (dans la passe où il aboutit), jamais à
chaque re-déroulé. Les demandes imbriquées (un effet qui, pour se résoudre, en déclenche un autre
qui demande à son tour) tombent naturellement en ordre : la pile est LIFO, les indices sont globaux.

Le moteur ne connaît **aucune horloge** (il est pur) : :func:`expirer` applique une réponse par
défaut *quand on le lui dit*, c'est l'extérieur (lot ``j-timer``) qui décide *quand*.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from ..effets.pile import (
    EffetEnAttente,
    PileEffets,
    evenement_resolu,
)
from ..journal.modele import Evenement
from ..rng import Rng
from ..state.modele import EtatPartie
from .gestionnaire import Gestionnaire, SuspensionDemande
from .modele import DemandeDecision, Reponse, reponse_par_defaut, valider_reponse

#: Une demande de décision vient d'être **posée** : la résolution est suspendue. Porte la demande
#: (destinataire, catégorie, options, source, règle, obligatoire, horloge) pour journal et écran.
EVT_DEMANDE_EMISE = "demande_emise"
#: Un joueur a **répondu** à une demande (:func:`repondre`) : porte l'id et le choix retenu.
EVT_DEMANDE_REPONDUE = "demande_repondue"
#: Le délai d'une demande a **expiré** (:func:`expirer`) : la réponse par défaut est appliquée et
#: **écrite** ici (jamais un abandon muet) — porte l'id et le choix par défaut effectivement joué.
EVT_DEMANDE_EXPIREE = "demande_expiree"

#: Un résolveur qui sait demander des décisions : comme un
#: :data:`~pbm_game.effets.pile.Resolveur`, mais reçoit en plus le
#: :class:`~pbm_game.demandes.gestionnaire.Gestionnaire` par lequel il réclame un choix.
ResolveurDecision = Callable[
    [EtatPartie, EffetEnAttente, Rng, Gestionnaire],
    tuple[EtatPartie, list[Evenement], list[EffetEnAttente]],
]

#: Registre **module-level** des résolveurs sachant demander, peuplé à l'import (comme
#: ``journal.transitions.REGISTRE``). Le résolveur DSL s'y enregistre via ``pbm_game`` ; les
#: lots de cartes (Objets, Supporters, talents) y ajouteront les leurs. Les transitions
#: ``repondre_demande`` / ``expirer_demande`` le lisent pour **reprendre** une résolution.
REGISTRE_EFFETS: dict[str, ResolveurDecision] = {}

# Garde-fou anti-boucle, même esprit que la pile : un enchaînement d'effets qui ne s'arrête jamais
# doit tomber bruyamment, jamais tourner en silence.
_RESOLUTIONS_MAX = 10_000


def enregistrer(type_effet: str, resolveur: ResolveurDecision) -> None:
    """Enregistre un résolveur sachant demander pour ``type_effet`` (pas d'écrasement muet)."""
    if type_effet in REGISTRE_EFFETS and REGISTRE_EFFETS[type_effet] is not resolveur:
        raise ValueError(f"Un résolveur est déjà enregistré pour « {type_effet} ».")
    REGISTRE_EFFETS[type_effet] = resolveur


@dataclass(frozen=True)
class ResolutionEnCours:
    """L'instantané d'une résolution **suspendue** — porté par l'état, donc sérialisé, donc repris.

    * ``pile`` — la pile d'effets restant à résoudre, l'effet suspendu au sommet ;
    * ``demande`` — la décision en attente (celle que le destinataire doit trancher) ;
    * ``reponses`` — les réponses **déjà données** depuis le début de cette résolution ;
    * ``base`` — le nombre de décisions des effets déjà terminés (indice de départ du compteur à la
      reprise : voir :class:`~pbm_game.demandes.gestionnaire.Gestionnaire`).

    C'est cette structure, nichée dans :class:`~pbm_game.state.modele.EtatPartie`, qui fait qu'une
    partie interrompue **au milieu d'une demande** reprend exactement à cette demande.
    """

    pile: PileEffets
    demande: DemandeDecision
    reponses: tuple[Reponse, ...] = ()
    base: int = 0

    def en_json(self) -> dict:
        return {
            "pile": self.pile.en_json(),
            "demande": self.demande.en_json(),
            "reponses": [r.en_json() for r in self.reponses],
            "base": self.base,
        }

    @staticmethod
    def depuis_json(donnees: object) -> ResolutionEnCours:
        if not isinstance(donnees, dict):
            raise ValueError("Une résolution en cours doit être un mapping.")
        reponses = donnees.get("reponses", [])
        if not isinstance(reponses, list):
            raise ValueError("Résolution en cours : « reponses » doit être une liste.")
        base = donnees.get("base", 0)
        if not isinstance(base, int) or isinstance(base, bool) or base < 0:
            raise ValueError("Résolution en cours : « base » doit être un entier ≥ 0.")
        return ResolutionEnCours(
            pile=PileEffets.depuis_json(donnees.get("pile")),
            demande=DemandeDecision.depuis_json(donnees.get("demande")),
            reponses=tuple(Reponse.depuis_json(r) for r in reponses),
            base=base,
        )


def evenement_demande_emise(demande: DemandeDecision) -> Evenement:
    """L'événement :data:`EVT_DEMANDE_EMISE` décrivant la demande posée (lisible, non secret)."""
    d = demande.en_json()
    # Pour un ensemble CACHÉ, on ne diffuse pas les identités d'option dans le journal : seul leur
    # nombre (anti-triche). La projection par joueur applique la même règle côté écran.
    if demande.ensemble_cache:
        d = {**d, "options": [], "options_nombre": len(demande.options)}
    return Evenement(EVT_DEMANDE_EMISE, d)


def resoudre(
    etat: EtatPartie,
    pile: PileEffets,
    registre: dict[str, ResolveurDecision],
    rng: Rng,
    gestionnaire: Gestionnaire,
) -> tuple[EtatPartie, list[Evenement], ResolutionEnCours | None]:
    """Résout ``pile`` en LIFO jusqu'à l'épuisement **ou** jusqu'à une demande de décision.

    Renvoie ``(etat, evenements, resolution)`` : ``resolution`` vaut ``None`` si la pile s'est
    résolue entièrement, sinon la :class:`ResolutionEnCours` à poser dans l'état. Pur côté état ;
    ``rng`` est mutable (tirages rejouables) et peut être **ramené en arrière** à une suspension.

    Lève ``ValueError`` si un ``type_effet`` est absent du registre (D9) ou si la chaîne dépasse
    :data:`_RESOLUTIONS_MAX` (boucle d'effets — arrêt bruyant).
    """
    evenements: list[Evenement] = []
    resolutions = 0
    while not pile.est_vide:
        resolutions += 1
        if resolutions > _RESOLUTIONS_MAX:
            raise ValueError(
                f"Résolution : plus de {_RESOLUTIONS_MAX} effets enchaînés — boucle probable, "
                "arrêt bruyant (jamais un silence)."
            )
        effet, pile_restante = pile.depiler()
        resolveur = registre.get(effet.type_effet)
        if resolveur is None:
            raise ValueError(
                f"Type d'effet inconnu : {effet.type_effet!r} — un effet non implémenté n'est "
                f"jamais approximé (D9). Types connus : {sorted(registre)}."
            )
        offset = gestionnaire.compteur  # décisions déjà faites par les effets terminés de la passe
        rng_avant = rng.etat()
        try:
            etat2, evts, empiles = resolveur(etat, effet, rng, gestionnaire)
        except SuspensionDemande as suspension:
            # L'effet n'a pas abouti : on jette son travail partiel (état + tirages) et on le
            # laisse au sommet de la pile pour le re-dérouler à la réponse.
            rng.restaurer(rng_avant)
            resolution = ResolutionEnCours(
                pile=pile_restante.empiler(effet),
                demande=suspension.demande,
                reponses=gestionnaire.reponses,
                base=gestionnaire.base + offset,
            )
            evenements.append(evenement_demande_emise(suspension.demande))
            return etat, evenements, resolution
        etat = etat2
        evenements.append(evenement_resolu(effet.source, effet))
        evenements.extend(evts)
        pile = pile_restante.empiler(*empiles) if empiles else pile_restante
    return etat, evenements, None


def demarrer_resolution(
    etat: EtatPartie,
    pile: PileEffets,
    rng: Rng,
    *,
    registre: dict[str, ResolveurDecision] | None = None,
) -> tuple[EtatPartie, list[Evenement]]:
    """Lance une résolution neuve et renvoie ``(etat, evenements)``, demande posée dans l'état.

    Point d'entrée des lots qui **déclenchent** un effet (attaques, Dresseurs) : ils empilent leurs
    effets et appellent ceci. Si la résolution se suspend, ``etat.resolution`` porte la demande ;
    sinon elle est ``None``. ``registre`` vaut :data:`REGISTRE_EFFETS` par défaut.
    """
    reg = REGISTRE_EFFETS if registre is None else registre
    gestionnaire = Gestionnaire(reponses=(), base=0)
    etat2, evenements, resolution = resoudre(etat, pile, reg, rng, gestionnaire)
    return replace(etat2, resolution=resolution), evenements


def _reprendre(
    etat: EtatPartie,
    reponse: Reponse,
    registre: dict[str, ResolveurDecision],
    rng: Rng,
    *,
    evenement_reponse: Evenement,
) -> tuple[EtatPartie, list[Evenement]]:
    """Fabrique commune à :func:`repondre` / :func:`expirer` : enregistre ``reponse`` et re-déroule.

    La réponse est validée (le serveur fait autorité), ajoutée aux réponses de la résolution, puis
    la pile suspendue est re-déroulée. Si une **nouvelle** demande surgit (décision imbriquée), elle
    remplace la précédente dans l'état ; sinon la résolution est finie (``resolution`` à ``None``).
    """
    resolution = etat.resolution
    if resolution is None:
        raise ValueError(
            "Aucune résolution en cours : il n'y a pas de demande à laquelle répondre."
        )
    valider_reponse(resolution.demande, reponse)
    reponses = resolution.reponses + (reponse,)
    gestionnaire = Gestionnaire(reponses=reponses, base=resolution.base)
    etat_sans = replace(etat, resolution=None)
    etat2, evts, suite = resoudre(etat_sans, resolution.pile, registre, rng, gestionnaire)
    evenements = [evenement_reponse, *evts]
    return replace(etat2, resolution=suite), evenements


def repondre(
    etat: EtatPartie,
    reponse: Reponse,
    rng: Rng,
    *,
    registre: dict[str, ResolveurDecision] | None = None,
) -> tuple[EtatPartie, list[Evenement]]:
    """Applique la **réponse d'un joueur** à la demande en cours et reprend la résolution.

    Lève ``ValueError`` si aucune demande n'est en cours, ou si la réponse est irrecevable
    (mauvaise demande, hors ensemble, mauvaise cardinalité — jamais de repli silencieux).
    """
    reg = REGISTRE_EFFETS if registre is None else registre
    resolution = etat.resolution
    if resolution is None:
        raise ValueError(
            "Aucune résolution en cours : il n'y a pas de demande à laquelle répondre."
        )
    evt = Evenement(
        EVT_DEMANDE_REPONDUE, {"demande_id": reponse.demande_id, "choix": list(reponse.choix)}
    )
    return _reprendre(etat, reponse, reg, rng, evenement_reponse=evt)


def expirer(
    etat: EtatPartie,
    rng: Rng,
    *,
    registre: dict[str, ResolveurDecision] | None = None,
) -> tuple[EtatPartie, list[Evenement]]:
    """Applique la **réponse par défaut** à la demande en cours (le délai a expiré) et reprend.

    La réponse par défaut (:func:`~pbm_game.demandes.modele.reponse_par_defaut`) est **écrite** au
    journal (``EVT_DEMANDE_EXPIREE``) : un effet qui tombe par expiration ne disparaît jamais en
    silence. Lève ``ValueError`` s'il n'y a aucune demande en cours.
    """
    reg = REGISTRE_EFFETS if registre is None else registre
    resolution = etat.resolution
    if resolution is None:
        raise ValueError("Aucune résolution en cours : rien à faire expirer.")
    defaut = reponse_par_defaut(resolution.demande)
    evt = Evenement(
        EVT_DEMANDE_EXPIREE, {"demande_id": defaut.demande_id, "choix": list(defaut.choix)}
    )
    return _reprendre(etat, defaut, reg, rng, evenement_reponse=evt)


__all__ = [
    "EVT_DEMANDE_EMISE",
    "EVT_DEMANDE_REPONDUE",
    "EVT_DEMANDE_EXPIREE",
    "ResolveurDecision",
    "REGISTRE_EFFETS",
    "enregistrer",
    "ResolutionEnCours",
    "evenement_demande_emise",
    "resoudre",
    "demarrer_resolution",
    "repondre",
    "expirer",
]
