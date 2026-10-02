"""Vérification et **paiement** du coût d'une attaque (R-9.1, R-9.2) — en verdict motivé.

Module **pur** (aucune E/S). Il répond à deux questions :

* *l'Actif porte-t-il de quoi payer cette attaque ?* — :func:`cout_satisfait`, un verdict
  d'accord ou un refus motivé (règle citée), jamais un refus muet (pas de repli silencieux) ;
* *avec QUOI la paie-t-il ?* — :func:`payer_cout`, qui construit une **combinaison valide**
  (quelle énergie paie quel symbole) et l'**explique** : c'est elle que la déclaration
  d'attaque (lot ``j-cartes-attaques``) journalisera, pour que le joueur lise « feu ← Énergie
  Feu, ★ ← Double Énergie Incolore » plutôt qu'un « coût OK » opaque.

**Ce que le moteur reçoit.** Les ``Carte`` d'énergie attachées à un Pokémon ne portent, dans
l'état, que leur ``instance_id`` et leur ``ref`` : ce qu'une énergie **fournit** est une
**capacité de la carte**, extraite du catalogue par le service et portée par
:class:`pbm_game.cartes.energie.DefinitionEnergie`. La vérification travaille donc sur des
**fournitures** déjà extraites — pour chaque énergie attachée, un mapping ``{type: unités}`` :

* une Énergie Feu de base → ``{"feu": 1}`` ;
* une Double Énergie Incolore → ``{"incolore": 2}`` (R-9.2 : une énergie peut fournir
  plusieurs unités) ;
* une énergie spéciale bi-type → ``{"feu": 1, "eau": 1}`` (deux unités, une par type).

**Règle de paiement (R-9.2).** Le coût demande « **au moins** » l'énergie requise : de
l'énergie en trop ne gêne pas. Un symbole **coloré** d'un type se paie par **une unité de ce
type exact** ; un symbole **incolore** (★) se paie par **n'importe quelle** unité. On paie
donc d'abord les symboles colorés (ils n'acceptent que leur type), puis les incolores avec ce
qui reste : c'est **optimal et complet** dans ce modèle où chaque unité porte un type fixe —
une unité de type ``T`` ne peut payer qu'un symbole coloré ``T`` ou un symbole incolore, donc
réserver les unités colorées à leur couleur ne prive jamais un autre symbole coloré, et les
incolores se servent du reste. C'est le piège nommé par la fiche : comparer de simples
compteurs totaux (« assez d'unités ? ») accepterait de l'incolore pour un symbole coloré et
refuserait, à l'inverse, une attaque parfaitement légale.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..actions.modele import ACCORD, Verdict, refus
from ..journal.modele import Evenement
from .modele import INCOLORE, CoutAttaque

#: Le coût d'une attaque a été payé — événement journalisé par la déclaration d'attaque. Porte
#: le **détail lisible** (R-9.2) et la combinaison retenue (quelle énergie a payé quel symbole),
#: pour que le journal de partie explique le paiement au lieu de l'avaler.
EVT_COUT_PAYE = "cout_paye"

#: Étiquette d'un symbole **incolore** dans le détail et les affectations (★ du corpus).
SYMBOLE_INCOLORE = "★"
#: Genres de symbole d'un coût (fermés) : coloré (par type exact) ou incolore (par n'importe quoi).
GENRE_SYMBOLE_COLORE = "colore"
GENRE_SYMBOLE_INCOLORE = "incolore"


def pool_energies(fournitures: Sequence[Mapping[str, int]]) -> Counter[str]:
    """Agrège les fournitures de chaque énergie en un **pool** ``{type: unités totales}``.

    Lève ``ValueError`` si une fourniture est malformée (type vide, unités négatives ou non
    entières) : une énergie dont on ne sait pas ce qu'elle fournit est une panne, jamais un
    zéro silencieux.
    """
    pool: Counter[str] = Counter()
    for i, fourniture in enumerate(fournitures):
        if not isinstance(fourniture, Mapping):
            raise ValueError(f"Fourniture d'énergie #{i} : attendu un mapping {{type: unités}}.")
        for t, n in fourniture.items():
            if not isinstance(t, str) or not t:
                raise ValueError(f"Fourniture d'énergie #{i} : type invalide {t!r}.")
            if not isinstance(n, int) or isinstance(n, bool) or n < 0:
                raise ValueError(
                    f"Fourniture d'énergie #{i} : unités invalides pour « {t} » : {n!r} "
                    "(entier ≥ 0)."
                )
            pool[t] += n
    return pool


def cout_satisfait(cout: CoutAttaque, fournitures: Sequence[Mapping[str, int]]) -> Verdict:
    """L'énergie ``fournitures`` paie-t-elle ``cout`` (R-9.2) ? Accord, ou refus motivé.

    Renvoie :data:`~pbm_game.actions.ACCORD` si le coût est satisfait, sinon un refus citant
    **R-9.2** et nommant ce qui manque. Un coût vide est toujours satisfait (attaque gratuite).
    """
    pool = pool_energies(fournitures)

    # (1) Symboles COLORÉS : chacun n'accepte que son type exact (R-9.2).
    manquants: dict[str, int] = {}
    for type_requis, besoin in cout.types.items():
        disponible = pool.get(type_requis, 0)
        if disponible < besoin:
            manquants[type_requis] = besoin - disponible
            pool[type_requis] = 0
        else:
            pool[type_requis] = disponible - besoin
    if manquants:
        detail = ", ".join(f"{n} « {t} »" for t, n in sorted(manquants.items()))
        return refus(
            "R-9.2",
            f"Coût non satisfait : il manque {detail} (l'Actif doit porter au moins "
            "l'énergie colorée requise, R-9.2).",
        )

    # (2) Symboles INCOLORES : payés par n'importe quelle unité restante (R-9.2).
    restant = sum(pool.values())
    if restant < cout.incolore:
        return refus(
            "R-9.2",
            f"Coût incolore non satisfait : {cout.incolore} symbole(s) incolore(s) requis, "
            f"{restant} unité(s) d'énergie restante(s) pour les payer (R-9.2).",
        )
    return ACCORD


@dataclass(frozen=True)
class EnergieAttachee:
    """Une énergie **attachée** à un Pokémon, identifiée, et ce qu'elle fournit (R-9.2).

    C'est le descripteur que :func:`payer_cout` consomme : le service résout chaque ``Carte``
    d'énergie de l'état (``instance_id``, ``ref``) en sa :class:`~pbm_game.cartes.energie.\
DefinitionEnergie` (via le catalogue) puis en une :class:`EnergieAttachee`. Le moteur ne
    devine donc jamais ce qu'une énergie fournit (D9) — il le reçoit.

    * ``instance_id`` — l'exemplaire précis en jeu (sert à nommer l'énergie dans le journal) ;
    * ``fournit`` — ``{type: unités}`` (p. ex. ``{"incolore": 2}``) ; au moins une unité ;
    * ``libelle`` — le nom lisible affiché dans le détail (« Double Énergie Incolore »).
    """

    instance_id: str
    fournit: Mapping[str, int]
    libelle: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, str) or not self.instance_id.strip():
            raise ValueError("Une énergie attachée doit porter un instance_id (journal, R-9.2).")
        # Valide la forme de la fourniture par le même garde que le pool (type/unités) ; une
        # énergie malformée est une panne bruyante, jamais un zéro silencieux.
        total = sum(pool_energies([self.fournit]).values())
        if total < 1:
            raise ValueError(
                f"Énergie « {self.instance_id} » : une énergie attachée fournit au moins une "
                "unité (R-9.2) — une fourniture vide est une panne, pas un cas normal."
            )


@dataclass(frozen=True)
class Affectation:
    """Une **affectation** : un symbole du coût payé par une unité d'une énergie précise.

    * ``symbole`` — l'étiquette du symbole payé (le type pour un coloré, ``★`` pour un incolore) ;
    * ``genre`` — :data:`GENRE_SYMBOLE_COLORE` ou :data:`GENRE_SYMBOLE_INCOLORE` ;
    * ``energie_instance_id`` / ``energie_libelle`` — l'énergie qui l'a payé ;
    * ``type_unite`` — le type de l'unité consommée (le même que ``symbole`` pour un coloré).
    """

    symbole: str
    genre: str
    energie_instance_id: str
    energie_libelle: str
    type_unite: str

    def en_json(self) -> dict:
        """L'affectation en valeurs JSON natives, pour la charge utile d'un événement."""
        return {
            "symbole": self.symbole,
            "genre": self.genre,
            "energie": self.energie_instance_id,
            "libelle": self.energie_libelle,
            "type_unite": self.type_unite,
        }


@dataclass(frozen=True)
class PaiementCout:
    """Le résultat d'un :func:`payer_cout` — payé (avec combinaison) ou refusé (avec raison).

    * ``paye`` — vrai si une combinaison valide a été trouvée ;
    * ``verdict`` — l'accord ou le refus motivé (règle citée) de :func:`cout_satisfait` ;
    * ``affectations`` — quelle énergie paie quel symbole (vide si refusé) ;
    * ``detail`` — l'explication lisible (« feu ← Énergie Feu, ★ ← Double Énergie Incolore »).
    """

    paye: bool
    verdict: Verdict
    affectations: tuple[Affectation, ...] = ()
    detail: str = ""

    def evenement(self, cout: CoutAttaque) -> Evenement:
        """L'événement :data:`EVT_COUT_PAYE` à journaliser quand le coût est payé.

        Lève ``ValueError`` si le coût n'a pas été payé : on ne journalise jamais un paiement
        qui n'a pas eu lieu (pas de repli silencieux).
        """
        if not self.paye:
            raise ValueError(
                "Aucun paiement à journaliser : le coût n'a pas été payé "
                f"({self.verdict.message})."
            )
        return Evenement(
            EVT_COUT_PAYE,
            {
                "cout": {"types": dict(cout.types), "incolore": cout.incolore},
                "detail": self.detail,
                "affectations": [a.en_json() for a in self.affectations],
            },
        )


def payer_cout(cout: CoutAttaque, energies: Sequence[EnergieAttachee]) -> PaiementCout:
    """Trouve une **combinaison valide** d'énergies qui paie ``cout``, et l'explique (R-9.2).

    Si le coût ne peut pas être payé, renvoie un :class:`PaiementCout` **refusé** portant le
    verdict motivé de :func:`cout_satisfait` (règle R-9.2 citée, ce qui manque nommé). Sinon,
    affecte chaque symbole à une unité d'énergie — les **colorés** d'abord (chacun à une unité
    de son type exact), puis les **incolores** (à n'importe quelle unité restante) — et renvoie
    la combinaison avec son détail lisible. Déterministe (énergies dans l'ordre donné, types
    triés) : rejouer la même situation redonne la même combinaison, ce qui tient le rejeu.

    La combinaison existe **toujours** dès que :func:`cout_satisfait` accorde (même modèle
    additif) : la recherche par unité ci-dessous ne peut donc échouer après un accord. Si elle
    le faisait, ce serait une incohérence interne — on la lève bruyamment plutôt que de rendre
    un paiement partiel silencieux.
    """
    verdict = cout_satisfait(cout, [e.fournit for e in energies])
    if verdict.refuse:
        return PaiementCout(paye=False, verdict=verdict)

    # Les unités disponibles, chacune rattachée à son énergie et à son type (ordre déterministe).
    unites: list[tuple[int, str]] = []  # (index d'énergie, type de l'unité)
    for i, e in enumerate(energies):
        for t in sorted(e.fournit):
            for _ in range(e.fournit[t]):
                unites.append((i, t))
    utilisee = [False] * len(unites)

    def _prendre(predicat) -> int:
        for idx, (_, t) in enumerate(unites):
            if not utilisee[idx] and predicat(t):
                utilisee[idx] = True
                return idx
        raise ValueError(
            "Incohérence interne : coût accordé mais aucune unité pour un symbole — "
            "jamais un paiement partiel silencieux (R-9.2)."
        )

    affectations: list[Affectation] = []

    # (1) Symboles COLORÉS : chacun à une unité de son type exact.
    for type_requis in sorted(cout.types):
        for _ in range(cout.types[type_requis]):
            idx = _prendre(lambda t, cible=type_requis: t == cible)
            i_energie, type_unite = unites[idx]
            e = energies[i_energie]
            affectations.append(
                Affectation(
                    symbole=type_requis,
                    genre=GENRE_SYMBOLE_COLORE,
                    energie_instance_id=e.instance_id,
                    energie_libelle=e.libelle,
                    type_unite=type_unite,
                )
            )

    # (2) Symboles INCOLORES : chacun à n'importe quelle unité restante.
    for _ in range(cout.incolore):
        idx = _prendre(lambda t: True)
        i_energie, type_unite = unites[idx]
        e = energies[i_energie]
        affectations.append(
            Affectation(
                symbole=SYMBOLE_INCOLORE,
                genre=GENRE_SYMBOLE_INCOLORE,
                energie_instance_id=e.instance_id,
                energie_libelle=e.libelle,
                type_unite=type_unite,
            )
        )

    return PaiementCout(
        paye=True,
        verdict=verdict,
        affectations=tuple(affectations),
        detail=_detail(affectations),
    )


def _detail(affectations: Sequence[Affectation]) -> str:
    """Le détail lisible d'un paiement (R-9.2), p. ex. « feu ← Énergie Feu, ★ ← Double Énergie »."""
    if not affectations:
        return "Coût gratuit : aucune énergie requise."
    morceaux = []
    for a in affectations:
        nom = a.energie_libelle.strip() or a.energie_instance_id
        # Pour un symbole incolore payé par une unité d'un type nommé, on dit lequel (lisibilité).
        if a.genre == GENRE_SYMBOLE_INCOLORE and a.type_unite != INCOLORE:
            morceaux.append(f"{a.symbole} ← {nom} ({a.type_unite})")
        else:
            morceaux.append(f"{a.symbole} ← {nom}")
    return "Coût payé : " + ", ".join(morceaux) + "."


__all__ = [
    "EVT_COUT_PAYE",
    "SYMBOLE_INCOLORE",
    "GENRE_SYMBOLE_COLORE",
    "GENRE_SYMBOLE_INCOLORE",
    "pool_energies",
    "cout_satisfait",
    "EnergieAttachee",
    "Affectation",
    "PaiementCout",
    "payer_cout",
]
