"""Des **milliers de parties** en parallèle, et la distribution de leurs durées.

Une campagne joue une suite de graines (une partie par graine, toutes reproductibles) et agrège :
combien de parties **saines**, quelles **anomalies** (chacune avec sa graine, donc rejouable en une
commande), et la **distribution** du nombre de tours et de coups. Cette distribution est le capteur
du risque nommé par la fiche : une partie « trop longue » n'est pas un artefact, c'est la forme
d'une boucle d'effets entre deux cartes — on la mesure, on ne l'ignore pas.

Le parallélisme passe par :mod:`concurrent.futures` (un processus par cœur) : le moteur est pur et
chaque partie est indépendante, donc elles se répartissent sans partage d'état. Sur la machine qui
construit (chimera, 16 fils), 10 000 parties tiennent en moins d'une minute. Chaque worker ne
renvoie qu'un **résumé** léger (jamais le journal complet) : la mémoire reste plate quel que soit le
nombre de parties.
"""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

from .orchestrateur import Anomalie, ResultatPartie, jouer_partie


def graines(prefixe: str, nombre: int) -> Iterator[str]:
    """Les ``nombre`` graines ``"{prefixe}:{i}"`` d'une campagne — déterministes et distinctes.

    Même préfixe et même nombre ⇒ exactement les mêmes parties : une campagne est elle-même
    reproductible, pas seulement chacune de ses parties.
    """
    if nombre < 0:
        raise ValueError("Le nombre de parties d'une campagne ne peut pas être négatif.")
    for i in range(nombre):
        yield f"{prefixe}:{i}"


@dataclass
class Distribution:
    """La distribution d'une grandeur entière (tours, coups) sur les parties d'une campagne."""

    minimum: int = 0
    maximum: int = 0
    moyenne: float = 0.0
    mediane: float = 0.0
    p95: float = 0.0

    @classmethod
    def depuis(cls, valeurs: list[int]) -> Distribution:
        """Calcule la distribution d'une liste de valeurs (tout à zéro si la liste est vide)."""
        if not valeurs:
            return cls()
        ordonnees = sorted(valeurs)
        # p95 par rang (pas d'interpolation) : robuste et lisible, sans dépendance externe.
        rang95 = max(0, min(len(ordonnees) - 1, round(0.95 * (len(ordonnees) - 1))))
        return cls(
            minimum=ordonnees[0],
            maximum=ordonnees[-1],
            moyenne=statistics.fmean(ordonnees),
            mediane=statistics.median(ordonnees),
            p95=float(ordonnees[rang95]),
        )


@dataclass
class RapportCampagne:
    """Le bilan agrégé d'une campagne — ce que :mod:`pbm_sim.rapport` met en forme et publie."""

    nombre: int = 0
    saines: int = 0
    anomalies: list[Anomalie] = field(default_factory=list)
    distribution_tours: Distribution = field(default_factory=Distribution)
    distribution_pas: Distribution = field(default_factory=Distribution)
    #: Nombre de parties par raison de fin (``derniere_recompense``, ``pioche_impossible``…).
    raisons: dict[str, int] = field(default_factory=dict)
    #: Nombre de parties par affrontement de decks (``"deckA vs deckB"``), pour voir la couverture.
    affrontements: dict[str, int] = field(default_factory=dict)

    @property
    def toutes_saines(self) -> bool:
        """Vrai si **toutes** les parties se sont terminées sans anomalie."""
        return self.nombre > 0 and self.saines == self.nombre and not self.anomalies


def _resumer(resultat: ResultatPartie) -> ResultatPartie:
    """Aucun journal ne traverse les processus (mémoire plate) : ``partie`` est remis à ``None``."""
    resultat.partie = None
    return resultat


def _jouer_pour_campagne(args: tuple[str, int, bool]) -> ResultatPartie:
    """Worker de processus : joue une partie et n'en renvoie que le résumé (jamais le journal)."""
    graine, max_pas, verifier_chaque_pas = args
    return _resumer(
        jouer_partie(graine, verifier_chaque_pas=verifier_chaque_pas, max_pas=max_pas)
    )


def campagne(
    liste_graines: Iterable[str],
    *,
    parallele: bool = True,
    processus: int | None = None,
    max_pas: int | None = None,
    verifier_chaque_pas: bool = True,
) -> RapportCampagne:
    """Joue toutes les ``liste_graines`` et renvoie le :class:`RapportCampagne` agrégé.

    * ``parallele`` — réparti sur plusieurs processus (défaut) ; ``False`` joue en série (utile en
      test, où le coût de démarrage des processus dépasserait le gain) ;
    * ``processus`` — nombre de processus (défaut : autant que de cœurs) ;
    * ``max_pas`` — plafond de coups par partie (défaut de :func:`jouer_partie` si ``None``) ;
    * ``verifier_chaque_pas`` — contrôle d'invariants après chaque coup (défaut vrai).

    Ne s'arrête **jamais** au premier pépin : toutes les parties sont jouées, toutes les anomalies
    collectées. C'est ce qui donne une mesure (« X anomalies sur N »), pas juste un premier échec.
    """
    graines_liste = list(liste_graines)
    from .orchestrateur import MAX_PAS_DEFAUT

    plafond = MAX_PAS_DEFAUT if max_pas is None else max_pas
    args = [(g, plafond, verifier_chaque_pas) for g in graines_liste]

    if parallele and len(args) > 1:
        with ProcessPoolExecutor(max_workers=processus) as pool:
            resultats = list(pool.map(_jouer_pour_campagne, args, chunksize=16))
    else:
        resultats = [_jouer_pour_campagne(a) for a in args]

    rapport = RapportCampagne(nombre=len(resultats))
    tours: list[int] = []
    pas: list[int] = []
    raisons: Counter[str] = Counter()
    affrontements: Counter[str] = Counter()
    for r in resultats:
        tours.append(r.tours)
        pas.append(r.pas)
        if r.saine:
            rapport.saines += 1
        else:
            rapport.anomalies.extend(r.anomalies)
        if r.raison_fin is not None:
            raisons[r.raison_fin] += 1
        affrontements[f"{r.deck0} vs {r.deck1}"] += 1
    rapport.distribution_tours = Distribution.depuis(tours)
    rapport.distribution_pas = Distribution.depuis(pas)
    rapport.raisons = dict(sorted(raisons.items()))
    rapport.affrontements = dict(sorted(affrontements.items()))
    return rapport


__all__ = [
    "graines",
    "Distribution",
    "RapportCampagne",
    "campagne",
]
