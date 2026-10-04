"""Les **talents** — passifs, activés une fois par tour, déclenchés — et leur annulation.

Module **pur** (aucune E/S, ni HTTP, ni base, ni React), comme tout ``pbm_game``. Importer ce
module n'a **aucun effet de bord** : il ne livre que le *cadre* des talents (la transition du
talent **activé**, elle, s'enregistre dans le ``REGISTRE`` du journal depuis
:mod:`pbm_game.effets.talents_actives`, comme ``effets.objets``).

**Les talents sont la partie la plus difficile du jeu moderne** (fiche ``j-cartes-talents``) : ils
agissent depuis le banc, en permanence, parfois pour éteindre d'autres talents. Ce module ne
réinvente rien — il **branche** les talents sur l'architecture d'effets déjà livrée :

* **continu** (toujours actif, banc compris) → un
  :data:`~pbm_game.effets.continus.ProducteurContinu` dérivé de ce qui est en jeu ;
* **déclenché** (sur un moment de jeu) → un :class:`~pbm_game.effets.bus.Reacteur` abonné au bus ;
* **activé** (une fois par tour, à son tour) → une **action de joueur** journalisée
  (:mod:`pbm_game.effets.talents_actives`), suivie **par Pokémon** (pas par joueur) grâce au
  drapeau ``Tour.talents_actives_ce_tour``.

Trois natures, **un seul portillon** : :func:`talent_actif`. Un talent n'agit que si son Pokémon
est en jeu (critère n°2 : il cesse **à l'instant** où le Pokémon quitte le jeu, *par
construction* — rien n'est « défait », la source disparaît de l'état), qu'il n'est pas
**neutralisé** par un talent (:func:`identites_neutralisees`), et qu'il n'est pas **désactivé** par
un état spécial de son porteur (``desactive_si_etat``, « selon la carte »).

**Décision — l'annulation mutuelle de talents** (critère n°1, tranchée par écrit dans
``docs/jeu/TALENTS.md``, servie par R-12.3). Un talent qui « éteint les talents » (type *Garbodor*
/ *Garbotoxine*) porte la clause « **sauf lui-même** » : il n'éteint ni lui-même, ni les autres
talents-verrous. Conséquence : **deux talents-verrous ne s'annulent pas l'un l'autre** (ils
survivent tous les deux) et éteignent, des **deux** camps, tous les **autres** talents. C'est le
comportement officiel (« each Pokémon has no Abilities, except Garbotoxin ») et le seul qui ne se
contredise pas : un verrou qui s'éteindrait lui-même rallumerait aussitôt ce qu'il éteint.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..journal.modele import Evenement
from ..rng import Rng
from ..state.modele import ETATS_SPECIAUX, EtatPartie, PokemonEnJeu, carte_active
from .bus import Bus
from .continus import ProducteurContinu, RegistreContinus
from .evenements import MECANISME_ACTIVE, MECANISME_CONTINU, MECANISME_DECLENCHE, EvenementJeu
from .pile import PileEffets

# --- Les trois natures d'un talent -------------------------------------------
# On **réutilise** le vocabulaire des mécanismes (``effets.evenements``) plutôt que d'inventer des
# constantes jumelles : un talent continu, activé ou déclenché partage la valeur du mécanisme
# correspondant. Un talent ne peut pas être « porté par une attaque » (ce mécanisme n'est pas une
# nature de talent) : la liste est donc fermée aux trois ci-dessous (D9).
NATURE_CONTINU = MECANISME_CONTINU
NATURE_ACTIVE = MECANISME_ACTIVE
NATURE_DECLENCHE = MECANISME_DECLENCHE

#: Les trois natures reconnues d'un talent. Une autre est refusée (D9) : jamais approximée.
NATURES_TALENT: frozenset[str] = frozenset({NATURE_CONTINU, NATURE_ACTIVE, NATURE_DECLENCHE})


@dataclass(frozen=True)
class Talent:
    """La **fiche** d'un talent — ce que le moteur doit savoir pour le porter correctement.

    Le *comportement* vit ailleurs (un producteur continu, un réacteur de bus, un script de talent
    activé) ; cette fiche porte ce qui **gouverne** ce comportement, et que le portillon
    :func:`talent_actif` consulte :

    * ``ref`` — la référence catalogue de la **carte porteuse** (le sommet de la pile
      d'évolutions) : c'est elle qui, trouvée en jeu, fait exister le talent ;
    * ``nom`` — le libellé lisible (journal, refus : « neutralisé par *Garbotoxine* ») ;
    * ``nature`` — une des :data:`NATURES_TALENT` ;
    * ``regle`` — l'identifiant ``R-x.y`` que le talent sert (jamais vide, D9) ;
    * ``supprime_talents`` — ce talent **éteint les talents** (type *Garbodor*) ; il est alors
      **auto-excepté** (voir :func:`identites_neutralisees`) ;
    * ``desactive_si_etat`` — les états spéciaux qui **désactivent** le talent quand son porteur
      en est affecté (« tant que ce Pokémon n'est pas Endormi… ») ; ⊆ :data:`ETATS_SPECIAUX` ;
    * ``depuis_banc`` — le talent agit-il **aussi depuis le banc** (défaut) ou **seulement** tant
      que son porteur est l'Actif.
    """

    ref: str
    nom: str
    nature: str
    regle: str
    supprime_talents: bool = False
    desactive_si_etat: frozenset[str] = field(default_factory=frozenset)
    depuis_banc: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.ref, str) or not self.ref:
            raise ValueError("Un talent doit nommer la référence de sa carte porteuse.")
        if not isinstance(self.nom, str) or not self.nom.strip():
            raise ValueError("Un talent doit porter un libellé lisible (journal).")
        if self.nature not in NATURES_TALENT:
            raise ValueError(
                f"Nature de talent inconnue : {self.nature!r} — jamais approximée (D9). "
                f"Connues : {sorted(NATURES_TALENT)}."
            )
        if not isinstance(self.regle, str) or not self.regle.strip():
            raise ValueError("Un talent doit citer la règle R-x.y qu'il sert (D9).")
        inconnus = set(self.desactive_si_etat) - ETATS_SPECIAUX
        if inconnus:
            raise ValueError(
                f"États désactivants inconnus : {sorted(inconnus)} — hors des cinq états de "
                f"R-11.1 ({sorted(ETATS_SPECIAUX)})."
            )


#: Un registre de talents, **par référence catalogue** de la carte porteuse. Vide par défaut (D9) :
#: ce sont les cartes réellement scriptées qui le peuplent. La clé est la ``ref`` du talent.
RegistreTalents = dict[str, Talent]


@dataclass(frozen=True)
class TalentEnJeu:
    """Un talent **effectivement présent** en jeu, avec le contexte qui sert le portillon.

    ``identite`` est l'identité **stable** du Pokémon porteur (``instance_id`` de sa carte de base,
    inchangée à travers les évolutions). ``est_actif`` dit s'il est l'Actif (par opposition au
    banc). ``etats`` sont ses états spéciaux courants (désactivation « selon la carte »).
    """

    joueur: str
    identite: str
    est_actif: bool
    etats: frozenset[str]
    talent: Talent


@dataclass(frozen=True)
class VerdictTalent:
    """Le verdict du portillon : le talent agit-il **ici et maintenant**, et sinon **pourquoi**.

    ``raison`` est non vide **si et seulement si** ``actif`` est faux — un talent qui n'agit pas le
    **dit** (nommément : pas en jeu, neutralisé par telle carte, désactivé par tel état), jamais
    un silence (interdiction du repli muet, comme un coup refusé qui cite sa règle).
    """

    actif: bool
    raison: str | None = None


def _identite(pokemon: PokemonEnJeu) -> str:
    return pokemon.cartes[0].instance_id


def _pokemons_en_jeu(etat: EtatPartie) -> list[tuple[str, PokemonEnJeu, bool]]:
    """``(joueur_id, pokemon, est_actif)`` pour chaque Pokémon en jeu, l'Actif puis le banc."""
    res: list[tuple[str, PokemonEnJeu, bool]] = []
    for joueur in etat.joueurs:
        if joueur.actif is not None:
            res.append((joueur.id, joueur.actif, True))
        for p in joueur.banc:
            res.append((joueur.id, p, False))
    return res


def talents_en_jeu(etat: EtatPartie, registre: RegistreTalents) -> list[TalentEnJeu]:
    """Tous les talents **en jeu** : un par Pokémon dont la carte au sommet est au registre.

    Enregistrement « automatique à l'entrée, retrait à la sortie » du critère de la mission, sans
    aucun état à tenir : un talent **existe** exactement tant que sa carte porteuse est en jeu —
    c'est dérivé de l'état, jamais stocké ni défait. Un Pokémon sans talent scripté ne contribue
    rien (l'absence réelle d'effet, D9).
    """
    res: list[TalentEnJeu] = []
    for jid, pok, est_actif in _pokemons_en_jeu(etat):
        talent = registre.get(carte_active(pok).ref)
        if talent is not None:
            res.append(TalentEnJeu(jid, _identite(pok), est_actif, pok.etats_speciaux, talent))
    return res


def _agit_a_sa_place(tej: TalentEnJeu) -> bool:
    """Le talent agit-il depuis la place de son porteur (Actif, ou banc si ``depuis_banc``) ?"""
    return tej.est_actif or tej.talent.depuis_banc


def _desactive_par_etat(tej: TalentEnJeu) -> frozenset[str]:
    """Les états spéciaux du porteur qui **désactivent** ce talent (``desactive_si_etat``)."""
    return tej.etats & tej.talent.desactive_si_etat


def _est_verrou_effectif(tej: TalentEnJeu) -> bool:
    """Un talent-verrou agit-il **intrinsèquement** (place et état), sans tenir compte des autres ?

    On ne demande **pas** ici s'il est neutralisé : un verrou n'est jamais neutralisé par un autre
    verrou (clause « sauf lui-même »). Il n'est mis en échec que par sa propre place (banc
    interdit) ou son propre état spécial. Éviter cette récursion est ce qui rend l'annulation
    mutuelle **décidable** plutôt que circulaire.
    """
    return tej.talent.supprime_talents and _agit_a_sa_place(tej) and not _desactive_par_etat(tej)


def source_neutralisation(etat: EtatPartie, registre: RegistreTalents) -> str | None:
    """Le **nom** du premier talent-verrou effectif en jeu — pour que tout refus le nomme."""
    for tej in talents_en_jeu(etat, registre):
        if _est_verrou_effectif(tej):
            return tej.talent.nom
    return None


def identites_neutralisees(etat: EtatPartie, registre: RegistreTalents) -> frozenset[str]:
    """Les identités des Pokémon dont le talent est **éteint** par un talent-verrou (critère n°1).

    La **décision d'annulation mutuelle** (``docs/jeu/TALENTS.md``, R-12.3), en une règle : s'il
    existe **au moins un** talent-verrou effectif en jeu (:func:`_est_verrou_effectif`), alors
    **tous les autres** talents des **deux** camps sont éteints — mais **aucun** talent-verrou ne
    l'est (clause « sauf lui-même »). Donc deux verrous coexistent sans s'annuler, et un verrou
    n'éteint pas son propre contrôleur de verrou. Sans verrou effectif, l'ensemble est vide.
    """
    tous = talents_en_jeu(etat, registre)
    if not any(_est_verrou_effectif(tej) for tej in tous):
        return frozenset()
    return frozenset(tej.identite for tej in tous if not tej.talent.supprime_talents)


def talent_actif(etat: EtatPartie, registre: RegistreTalents, identite: str) -> VerdictTalent:
    """Le **portillon unique** des trois natures : le talent du Pokémon ``identite`` agit-il ?

    Dans l'ordre, chaque échec **nommé** (jamais un silence) : le Pokémon n'a pas de talent en jeu
    (il a quitté le jeu, ou sa carte au sommet n'en porte pas) ; le talent n'agit pas depuis le
    banc alors que son porteur y est ; un **état spécial** le désactive (« selon la carte ») ; un
    **talent-verrou** le neutralise (:func:`identites_neutralisees`). Sinon : il agit.

    ``identite`` est l'identité **stable** (``instance_id`` de carte de base). Consulté au moment
    du **calcul** (dégâts, Checkup, activation), jamais figé en début de tour — c'est le piège
    nommé par la fiche (un talent continu consulté au mauvais moment est juste en apparence et faux
    aux cas limites).
    """
    cible = next(
        (tej for tej in talents_en_jeu(etat, registre) if tej.identite == identite), None
    )
    if cible is None:
        return VerdictTalent(False, f"« {identite} » n'a pas de talent en jeu")
    talent = cible.talent
    if not _agit_a_sa_place(cible):
        return VerdictTalent(False, f"le talent « {talent.nom} » n'agit que depuis l'Actif")
    etats_bloquants = sorted(_desactive_par_etat(cible))
    if etats_bloquants:
        etats_txt = ", ".join(etats_bloquants)
        return VerdictTalent(
            False, f"le talent « {talent.nom} » est désactivé par l'état {etats_txt} (R-11)"
        )
    if not talent.supprime_talents and identite in identites_neutralisees(etat, registre):
        src = source_neutralisation(etat, registre)
        return VerdictTalent(
            False, f"le talent « {talent.nom} » est neutralisé par « {src} » (R-12.3)"
        )
    return VerdictTalent(True, None)


# --- Brancher les talents sur l'architecture d'effets (builders gardés) -------

# Un réacteur de talent **déclenché** : comme un :class:`~pbm_game.effets.bus.Reacteur`, mais
# averti de l'**identité du porteur** (dernier argument) — un même talent peut être porté par
# plusieurs Pokémon en jeu, chacun réagit pour lui-même.
ReacteurTalent = Callable[
    [EtatPartie, EvenementJeu, PileEffets, Rng, str],
    tuple[PileEffets, list[Evenement]],
]


def construire_registre_continus(
    registre: RegistreTalents, producteurs: dict[str, ProducteurContinu]
) -> RegistreContinus:
    """Enveloppe les producteurs continus des talents d'une **garde** : seulement si le talent agit.

    ``producteurs`` associe une ``ref`` de talent à son producteur « nu » (ce que le talent ajoute
    au calcul). Le registre renvoyé se branche tel quel dans
    :func:`~pbm_game.effets.continus.collecter_effets_continus` : pour chaque source, le producteur
    gardé consulte :func:`talent_actif` sur le porteur (``cible``) et ne renvoie ses effets **que**
    s'il agit — neutralisé, désactivé par un état ou porteur parti, il renvoie ``[]`` (l'absence
    réelle d'effet, dérivée de l'état, exactement comme un Outil retiré).
    """
    construit: RegistreContinus = {}
    for ref, producteur in producteurs.items():
        construit[ref] = _garde_continue(registre, producteur)
    return construit


def _garde_continue(registre: RegistreTalents, producteur: ProducteurContinu) -> ProducteurContinu:
    def _producteur(etat: EtatPartie, ref: str, cible: str | None):
        # Un talent appartient toujours à un Pokémon : ``cible`` est son identité. Sans porteur
        # (cas d'un Stade, jamais d'un talent), il ne contribue rien.
        if cible is None:
            return []
        if talent_actif(etat, registre, cible).actif:
            return producteur(etat, ref, cible)
        return []

    return _producteur


def construire_bus(
    registre: RegistreTalents,
    reacteurs: dict[str, tuple[str, ReacteurTalent]],
    bus: Bus | None = None,
) -> Bus:
    """Abonne les talents **déclenchés** au bus, chacun **gardé** par :func:`talent_actif`.

    ``reacteurs`` associe une ``ref`` de talent à ``(type_evenement, reacteur)``. Le réacteur
    abonné cherche, à la publication de l'événement, **chaque** porteur de cette ``ref`` en jeu
    dont le talent est actif, et le fait réagir pour lui-même (identité passée en dernier
    argument). Un porteur neutralisé, désactivé ou absent n'empile **rien** — l'absence réelle
    d'effet, comme une fenêtre vide du socle. Renvoie un **nouveau** bus (jamais de mutation).
    """
    bus = bus if bus is not None else Bus()
    for ref, (type_evenement, reacteur) in reacteurs.items():
        bus = bus.abonner(type_evenement, _garde_reacteur(registre, ref, reacteur))
    return bus


def _garde_reacteur(registre: RegistreTalents, ref: str, reacteur: ReacteurTalent):
    def _reacteur(etat: EtatPartie, evenement: EvenementJeu, pile: PileEffets, rng: Rng):
        evenements: list[Evenement] = []
        for tej in talents_en_jeu(etat, registre):
            if tej.talent.ref != ref:
                continue
            if not talent_actif(etat, registre, tej.identite).actif:
                continue
            pile, evts = reacteur(etat, evenement, pile, rng, tej.identite)
            evenements.extend(evts)
        return pile, evenements

    return _reacteur


__all__ = [
    "NATURE_CONTINU",
    "NATURE_ACTIVE",
    "NATURE_DECLENCHE",
    "NATURES_TALENT",
    "Talent",
    "TalentEnJeu",
    "VerdictTalent",
    "RegistreTalents",
    "ReacteurTalent",
    "talents_en_jeu",
    "identites_neutralisees",
    "source_neutralisation",
    "talent_actif",
    "construire_registre_continus",
    "construire_bus",
]
