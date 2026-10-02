"""La **pile d'effets** — résolution en dernier entré, premier sorti (LIFO).

Module **pur** (aucune E/S). Quand plusieurs effets attendent de se résoudre — une attaque
qui pose un état, un talent qui réagit à cet état, un Outil qui réagit à ce talent — l'ordre
n'est pas « celui où le code a été écrit », c'est une **pile** : le dernier effet empilé se
résout en premier, et peut lui-même en empiler d'autres qui passeront avant lui. C'est ce qui
permet aux **interruptions** d'exister : un effet « en réaction à » s'empile *au-dessus* de
celui qu'il interrompt, donc il se résout d'abord.

**Deux garde-fous repris du socle :**

* **chaque résolution est journalisée avec sa source** (``« à cause de l'Outil X »``) :
  :func:`resoudre_pile` émet un :data:`EVT_EFFET_RESOLU` portant la :class:`SourceEffet` avant
  les événements propres de l'effet — le critère d'acceptation l'exige ;
* **un effet sans cible ne bloque pas la partie** : il le **dit** (:data:`EVT_EFFET_SANS_CIBLE`)
  et la résolution continue. Ce n'est pas un repli silencieux — l'absence de cible est
  journalisée, pas avalée.

**D9.** Un type d'effet absent du :class:`RegistreEffets` est **refusé** (``ValueError``),
jamais deviné — exactement comme un ``action.type`` inconnu dans
``pbm_game.journal.transitions.REGISTRE``.

La pile est une donnée **immuable et sérialisable** (``frozen``) : au lot ``j-effets-choix``,
un effet pourra se *suspendre* en attendant la décision d'un joueur, et la pile fera alors
partie de l'état repris après un F5. Ici, elle se résout entièrement au sein d'un appel.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..journal.modele import Evenement
from ..rng import Rng
from ..state.modele import EtatPartie

#: Une résolution d'effet a eu lieu — porte la **source** (la carte responsable) et la règle.
#: C'est l'événement qui satisfait « chaque résolution d'effet est journalisée avec sa carte
#: source » : il précède les événements propres produits par l'effet.
EVT_EFFET_RESOLU = "effet_resolu"
#: Un effet n'avait **aucune cible valide** : il ne fait rien, mais le journal le dit (jamais
#: un repli silencieux). Porte la source et la raison.
EVT_EFFET_SANS_CIBLE = "effet_sans_cible"


@dataclass(frozen=True)
class SourceEffet:
    """La carte **responsable** d'un effet — ce qui rend le journal lisible (« à cause de X »).

    * ``instance_id`` — l'exemplaire précis en jeu (``None`` pour un effet système sans carte) ;
    * ``ref`` — la référence catalogue de la carte ;
    * ``libelle`` — le nom lisible affiché dans le journal (« Bandeau Musclé », « Gardevoir »).
    """

    libelle: str
    ref: str | None = None
    instance_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.libelle, str) or not self.libelle.strip():
            raise ValueError("Une source d'effet doit porter un libellé lisible (journal).")

    def en_json(self) -> dict:
        """La source en valeurs JSON natives, pour la charge utile d'un événement."""
        return {"libelle": self.libelle, "ref": self.ref, "instance_id": self.instance_id}

    @staticmethod
    def depuis_json(donnees: object) -> SourceEffet:
        """Relit une source produite par :meth:`en_json` (ou lève ``ValueError``).

        Sert à reprendre une pile **suspendue** après un F5 (lot ``j-effets-choix``) : la source
        voyage dans l'état sérialisé, et doit en revenir identique.
        """
        if not isinstance(donnees, dict):
            raise ValueError("Une source d'effet doit être un mapping {libelle, ref, instance_id}.")
        return SourceEffet(
            libelle=donnees.get("libelle", ""),
            ref=donnees.get("ref"),
            instance_id=donnees.get("instance_id"),
        )


@dataclass(frozen=True)
class EffetEnAttente:
    """Un effet **empilé**, en attente de résolution — autosuffisant et sérialisable.

    * ``type_effet`` — la clé du :class:`RegistreEffets` qui sait le résoudre (un type absent
      est refusé, D9) ;
    * ``source`` — la carte responsable (:class:`SourceEffet`) ;
    * ``regle`` — l'identifiant ``R-x.y`` que l'effet applique (jamais vide : un effet cite sa
      règle, comme un :class:`~pbm_game.combat.modele.Modificateur`) ;
    * ``params`` — les paramètres de résolution, en valeurs **JSON natives** (pour qu'un effet
      suspendu se reprenne après un F5) ;
    * ``libelle`` — le nom lisible de l'effet lui-même (« Transfert de dégâts »).
    """

    type_effet: str
    source: SourceEffet
    regle: str
    libelle: str
    params: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.type_effet, str) or not self.type_effet:
            raise ValueError("Un effet en attente doit nommer son type de résolution.")
        if not isinstance(self.regle, str) or not self.regle.strip():
            raise ValueError("Un effet en attente doit citer la règle R-x.y qu'il applique (D9).")
        if not isinstance(self.libelle, str) or not self.libelle.strip():
            raise ValueError("Un effet en attente doit porter un libellé lisible.")

    def en_json(self) -> dict:
        """L'effet en valeurs JSON natives — pour une pile **suspendue** reprise après un F5."""
        return {
            "type_effet": self.type_effet,
            "source": self.source.en_json(),
            "regle": self.regle,
            "libelle": self.libelle,
            "params": self.params,
        }

    @staticmethod
    def depuis_json(donnees: object) -> EffetEnAttente:
        """Relit un effet produit par :meth:`en_json` (ou lève ``ValueError``)."""
        if not isinstance(donnees, dict):
            raise ValueError("Un effet en attente doit être un mapping.")
        params = donnees.get("params", {})
        if not isinstance(params, dict):
            raise ValueError("Effet en attente : « params » doit être un mapping.")
        return EffetEnAttente(
            type_effet=donnees.get("type_effet", ""),
            source=SourceEffet.depuis_json(donnees.get("source")),
            regle=donnees.get("regle", ""),
            libelle=donnees.get("libelle", ""),
            params=params,
        )


# Un résolveur transforme l'état, rend ses événements, et peut **empiler** de nouveaux effets
# (qui se résoudront avant la suite — c'est le cœur du LIFO). Pur côté état ; ``rng`` est le
# seul collaborateur mutable (tirages rejouables), comme dans le socle.
Resolveur = Callable[
    [EtatPartie, "EffetEnAttente", Rng],
    tuple[EtatPartie, list[Evenement], list["EffetEnAttente"]],
]

#: Registre des types d'effet reconnus. **Vide par défaut** : au jalon J2 aucun effet de carte
#: n'est scripté (D9) ; les lots de cartes (Outils, Stades, talents, DSL) y enregistrent les
#: leurs, exactement comme les transitions s'enregistrent dans
#: ``pbm_game.journal.transitions.REGISTRE``.
RegistreEffets = dict[str, Resolveur]

#: Un garde d'**interruption** : avant de résoudre le sommet de la pile, il peut empiler des
#: effets « en réaction » (qui passeront alors devant). Rend la pile (éventuellement augmentée)
#: et les événements d'information produits. Pur côté état.
Interruption = Callable[
    [EtatPartie, "EffetEnAttente", "PileEffets", Rng],
    tuple["PileEffets", list[Evenement]],
]

# Garde-fou anti-boucle : un effet qui s'empile lui-même sans fin (talent qui réagit à un
# talent qui réagit…) doit s'arrêter bruyamment, jamais tourner en silence. Très au-dessus de
# toute chaîne réelle (la plus longue connue tient en une poignée de maillons).
_RESOLUTIONS_MAX = 1000


@dataclass(frozen=True)
class PileEffets:
    """Une pile d'effets **immuable** — le sommet est le dernier élément de ``effets``.

    ``empiler`` et ``depiler`` renvoient une **nouvelle** pile (jamais de mutation). Une pile
    vide se résout en un état inchangé et aucun événement — l'absence réelle d'effet, pas un
    silence.
    """

    effets: tuple[EffetEnAttente, ...] = ()

    @property
    def est_vide(self) -> bool:
        return not self.effets

    @property
    def sommet(self) -> EffetEnAttente:
        """L'effet au sommet (le prochain résolu). Lève si la pile est vide."""
        if not self.effets:
            raise ValueError("Pile d'effets vide : aucun sommet à lire.")
        return self.effets[-1]

    def empiler(self, *effets: EffetEnAttente) -> PileEffets:
        """Renvoie une pile avec ``effets`` ajoutés au sommet (le dernier passé sera résolu 1er)."""
        for e in effets:
            if not isinstance(e, EffetEnAttente):
                raise TypeError(f"On n'empile que des EffetEnAttente, reçu {type(e).__name__}.")
        return PileEffets(self.effets + tuple(effets))

    def depiler(self) -> tuple[EffetEnAttente, PileEffets]:
        """Renvoie ``(sommet, pile_sans_sommet)``. Lève si la pile est vide."""
        if not self.effets:
            raise ValueError("Pile d'effets vide : rien à dépiler.")
        return self.effets[-1], PileEffets(self.effets[:-1])

    def en_json(self) -> list[dict]:
        """La pile en liste JSON native, du **bas vers le haut** (le dernier est le sommet)."""
        return [e.en_json() for e in self.effets]

    @staticmethod
    def depuis_json(donnees: object) -> PileEffets:
        """Relit une pile produite par :meth:`en_json` (ou lève ``ValueError``)."""
        if not isinstance(donnees, list):
            raise ValueError("Une pile d'effets sérialisée doit être une liste (bas → haut).")
        return PileEffets(tuple(EffetEnAttente.depuis_json(d) for d in donnees))


def evenement_resolu(source: SourceEffet, effet: EffetEnAttente) -> Evenement:
    """L'événement :data:`EVT_EFFET_RESOLU` attribuant une résolution à sa carte source."""
    return Evenement(
        EVT_EFFET_RESOLU,
        {
            "source": source.en_json(),
            "type_effet": effet.type_effet,
            "regle": effet.regle,
            "libelle": effet.libelle,
        },
    )


def evenement_sans_cible(source: SourceEffet, effet: EffetEnAttente, raison: str) -> Evenement:
    """L'événement :data:`EVT_EFFET_SANS_CIBLE` : l'effet n'a rien pu faire, et le dit."""
    return Evenement(
        EVT_EFFET_SANS_CIBLE,
        {
            "source": source.en_json(),
            "type_effet": effet.type_effet,
            "regle": effet.regle,
            "libelle": effet.libelle,
            "raison": raison,
        },
    )


def resoudre_pile(
    etat: EtatPartie,
    pile: PileEffets,
    registre: RegistreEffets,
    rng: Rng,
    *,
    interruption: Interruption | None = None,
) -> tuple[EtatPartie, list[Evenement]]:
    """Résout la pile **jusqu'à l'épuisement**, en LIFO, et renvoie ``(etat, evenements)``.

    À chaque tour de boucle : (1) le garde d'``interruption`` peut empiler des effets « en
    réaction » qui passeront devant ; (2) le sommet est dépilé et résolu par son résolveur du
    ``registre`` — un :data:`EVT_EFFET_RESOLU` attribuant la résolution à sa **source** est
    émis d'abord, puis les événements propres de l'effet ; (3) les effets que le résolveur
    empile à son tour rejoignent le sommet. Pur côté état.

    Lève ``ValueError`` si un ``type_effet`` est absent du registre (D9 : jamais approximé) ou
    si la chaîne dépasse :data:`_RESOLUTIONS_MAX` (boucle d'effets — panne bruyante, pas un
    silence).
    """
    evenements: list[Evenement] = []
    resolutions = 0
    while not pile.est_vide:
        if interruption is not None:
            pile, evts_int = interruption(etat, pile.sommet, pile, rng)
            evenements.extend(evts_int)
        resolutions += 1
        if resolutions > _RESOLUTIONS_MAX:
            raise ValueError(
                f"Pile d'effets : plus de {_RESOLUTIONS_MAX} résolutions enchaînées — "
                "boucle d'effets probable, arrêt bruyant (jamais un silence)."
            )
        effet, pile = pile.depiler()
        resolveur = registre.get(effet.type_effet)
        if resolveur is None:
            raise ValueError(
                f"Type d'effet inconnu : {effet.type_effet!r} — un effet non implémenté "
                f"n'est jamais approximé (D9). Types connus : {sorted(registre)}."
            )
        evenements.append(evenement_resolu(effet.source, effet))
        etat, evts, empiles = resolveur(etat, effet, rng)
        evenements.extend(evts)
        if empiles:
            pile = pile.empiler(*empiles)
    return etat, evenements


__all__ = [
    "EVT_EFFET_RESOLU",
    "EVT_EFFET_SANS_CIBLE",
    "SourceEffet",
    "EffetEnAttente",
    "Resolveur",
    "RegistreEffets",
    "Interruption",
    "PileEffets",
    "evenement_resolu",
    "evenement_sans_cible",
    "resoudre_pile",
]
