"""Le **bus d'événements de jeu** — et le pont vers les fenêtres du socle.

Module **pur** (aucune E/S). Le bus relie les deux moitiés de l'architecture : d'un côté les
:class:`~pbm_game.effets.evenements.EvenementJeu` (les *moments*), de l'autre la
:class:`~pbm_game.effets.pile.PileEffets` (la *résolution*). Un **réacteur** est un effet
déclenché qui écoute un moment : quand le bus **publie** cet événement, le réacteur **empile**
ce qu'il veut faire ; la pile se résout ensuite en LIFO.

**Le point qui vérifie le critère d'acceptation n°4 — « le socle n'a pas été modifié ».** Le
socle de la machine à tour ouvre déjà des **fenêtres** (``pbm_game.tour.fenetres`` :
``FENETRE_DEBUT_TOUR``, ``FENETRE_FIN_TOUR``, ``FENETRE_EXPIRATION_EFFETS``) et sait en exécuter
les *déclencheurs* enregistrés — son docstring annonce explicitement que « la pile d'effets
viendra plus tard enregistrer ses déclencheurs ». :func:`declencheur_fenetre` fabrique
précisément ce déclencheur : une fonction de la signature attendue par
``pbm_game.tour.fenetres.declencher`` qui, à l'ouverture d'une fenêtre, publie l'événement de
jeu correspondant, résout la pile, et rend les événements — **sans toucher une ligne du
socle**. On se branche sur le point d'accroche existant ; on ne le réécrit pas.

Pour les moments que le socle n'ouvre pas encore de lui-même (avant/après les dégâts, pose,
évolution, K.O., attachement d'énergie), ce sont les **lots de résolution** correspondants qui
publieront sur le bus au bon endroit (``j-cartes-pokemon`` pour la pose, ``j-cartes-attaques-
effets`` pour les dégâts…). Le bus est le mécanisme ; chaque lot y branche sa publication. Ce
lot ne câble pas ces publications dans le socle, exprès : ce serait le modifier.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from ..journal.modele import Evenement
from ..rng import Rng
from ..state.modele import EtatPartie
from .evenements import EJ_DEVIENT_ACTIF, EVENEMENTS_JEU, EvenementJeu
from .pile import Interruption, PileEffets, RegistreEffets, resoudre_pile

# Un réacteur reçoit l'état, l'événement de jeu publié et la pile courante ; il rend la pile
# (augmentée des effets qu'il empile) et, le cas échéant, des événements d'information. Pur
# côté état ; ``rng`` est le seul collaborateur mutable (tirages rejouables).
Reacteur = Callable[
    [EtatPartie, EvenementJeu, PileEffets, Rng],
    tuple[PileEffets, list[Evenement]],
]


@dataclass(frozen=True)
class Bus:
    """Le registre des réacteurs, **par type d'événement de jeu** — immuable.

    ``reacteurs`` associe un :data:`~pbm_game.effets.evenements.EVENEMENTS_JEU` à la suite
    **ordonnée** de ses réacteurs (l'ordre compte : R-12.3 impose un ordre fixe entre les
    tours). Vide par défaut (D9) : les lots de cartes y enregistrent leurs talents déclenchés.
    ``abonner`` renvoie un nouveau bus (jamais de mutation).
    """

    reacteurs: dict[str, tuple[Reacteur, ...]] = field(default_factory=dict)

    def abonner(self, evenement: str, reacteur: Reacteur) -> Bus:
        """Renvoie un bus où ``reacteur`` écoute ``evenement`` (ajouté en fin d'ordre)."""
        if evenement not in EVENEMENTS_JEU:
            raise ValueError(
                f"Abonnement à un événement inconnu : {evenement!r} — jamais approximé (D9). "
                f"Connus : {sorted(EVENEMENTS_JEU)}."
            )
        copie = {k: v for k, v in self.reacteurs.items()}
        copie[evenement] = copie.get(evenement, ()) + (reacteur,)
        return Bus(copie)

    def publier(
        self, etat: EtatPartie, evenement: EvenementJeu, pile: PileEffets, rng: Rng
    ) -> tuple[PileEffets, list[Evenement]]:
        """Fait réagir, dans l'ordre, les réacteurs abonnés à ``evenement.type``.

        Chaque réacteur peut **empiler** des effets sur ``pile``. Rend la pile augmentée et les
        événements d'information produits. **Sans réacteur abonné, ne produit rien et n'empile
        rien** — l'absence réelle d'effet (jamais un repli masqué), exactement comme une fenêtre
        vide du socle. Publier un type inconnu est impossible : :class:`EvenementJeu` l'a déjà
        refusé à sa construction (D9).
        """
        evenements: list[Evenement] = []
        for reacteur in self.reacteurs.get(evenement.type, ()):
            pile, evts = reacteur(etat, evenement, pile, rng)
            evenements.extend(evts)
        return pile, evenements


# Un fabricant de la charge utile d'un événement de jeu depuis l'état, au moment où la fenêtre
# du socle s'ouvre (le socle ne connaît pas les événements de jeu : c'est le pont qui les
# construit). Pur.
ChargeUtile = Callable[[EtatPartie], dict]


def _charge_tour(etat: EtatPartie) -> dict:
    """Charge utile par défaut des moments de tour : joueur actif et numéro (R-5.1)."""
    return {"joueur_actif": etat.tour.joueur_actif, "numero": etat.tour.numero}


def declencheur_fenetre(
    bus: Bus,
    type_evenement: str,
    registre: RegistreEffets,
    *,
    charge_utile: ChargeUtile = _charge_tour,
    interruption: Interruption | None = None,
):
    """Fabrique un **déclencheur** branchable sur ``pbm_game.tour.fenetres.declencher``.

    Le déclencheur renvoyé a la signature exacte attendue par le socle —
    ``(etat, rng) -> (etat, list[Evenement])`` — et, à l'ouverture de la fenêtre : construit
    l':class:`EvenementJeu` ``type_evenement`` (via ``charge_utile``), le **publie** sur le
    ``bus`` pour peupler une pile neuve, **résout** la pile avec ``registre`` (interruptions
    comprises), et rend les événements. C'est ainsi que la pile d'effets se branche sur le
    socle **sans le modifier** : on enregistre ce déclencheur dans
    ``pbm_game.tour.fenetres.DECLENCHEURS`` (ou on l'injecte via le paramètre ``declencheurs``
    de ``declencher`` / ``resoudre_checkup``, prévu pour cela).

    Sans réacteur ni effet, il renvoie ``(etat, [])`` : la fenêtre reste un no-op, le
    comportement du socle est **inchangé** — c'est ce qui le rend sûr à enregistrer.
    """
    if type_evenement not in EVENEMENTS_JEU:
        raise ValueError(
            f"Déclencheur pour un événement inconnu : {type_evenement!r} (D9). "
            f"Connus : {sorted(EVENEMENTS_JEU)}."
        )

    def _declencheur(etat: EtatPartie, rng: Rng) -> tuple[EtatPartie, list[Evenement]]:
        evenement = EvenementJeu(type_evenement, charge_utile(etat))
        pile, evts_pub = bus.publier(etat, evenement, PileEffets(), rng)
        etat, evts_pile = resoudre_pile(etat, pile, registre, rng, interruption=interruption)
        return etat, evts_pub + evts_pile

    return _declencheur


def publier_devient_actif(
    etat: EtatPartie,
    devenus_actifs: Sequence[tuple[str, str]],
    bus: Bus,
    registre: RegistreEffets,
    rng: Rng,
) -> tuple[EtatPartie, list[Evenement]]:
    """Publie :data:`~pbm_game.effets.evenements.EJ_DEVIENT_ACTIF` pour chaque Pokémon devenu Actif.

    C'est le **passage par le bus** que réclame l'appât (fiche ``j-cartes-objets``). Quand une carte
    force un Pokémon à devenir Actif — l'appât sort du banc le Pokémon fragile de l'adversaire, un
    *Switch* change le sien — le DSL l'a noté dans
    :attr:`~pbm_game.effets.dsl.interprete.ResultatProgramme.devenus_actifs` (une liste de
    ``(joueur, identité)``). **Sans ce passage, les déclencheurs « quand ce Pokémon devient
    Actif… » seraient oubliés** (le risque central nommé par la fiche) : l'appât amène souvent au
    front un Pokémon porteur d'un tel talent.

    Pour chaque ``(joueur, pokemon)``, dans l'ordre : construit l':class:`EvenementJeu`, le
    **publie** sur le ``bus`` (les réacteurs abonnés empilent leurs effets), **résout** la pile avec
    le ``registre``, et accumule les événements. Sans réacteur abonné, ne fait **rien** — l'absence
    réelle d'effet, jamais un repli masqué (comme une fenêtre vide du socle). Pur côté état ;
    ``rng`` est le seul collaborateur mutable (tirages rejouables).
    """
    evenements: list[Evenement] = []
    for joueur, pokemon in devenus_actifs:
        evenement = EvenementJeu(EJ_DEVIENT_ACTIF, {"joueur": joueur, "pokemon": pokemon})
        pile, evts_pub = bus.publier(etat, evenement, PileEffets(), rng)
        etat, evts_pile = resoudre_pile(etat, pile, registre, rng)
        evenements.extend(evts_pub)
        evenements.extend(evts_pile)
    return etat, evenements


__all__ = [
    "Reacteur",
    "Bus",
    "ChargeUtile",
    "declencheur_fenetre",
    "publier_devient_actif",
]
