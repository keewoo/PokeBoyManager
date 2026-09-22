"""Comparaison d'un recadrage à l'index visuel de toutes les cartes (mission
`v3-identification-visuelle` point 2) : plus proches voisins par distance de Hamming pondérée
(illustration + carte entière), score calibré, décision « reconnue sans IA » au-delà d'un seuil
avec une marge sur le deuxième candidat d'une **carte différente** — deux lignes de la même carte
(fr/en) qui arrivent toutes deux en tête ne sont jamais une ambiguïté, seul un concurrent d'un
autre `card_id` (réimpression, reverse, promo à la même illustration) en est une (mission point
1, « risques & pièges »).

Recherche en mémoire (numpy), pas en SQL comme `pbm_api.identification.cache` : l'index visuel
vise ~20 000 cartes × 2 langues, largement au-delà du volume "modeste" pour lequel ce module a
documenté qu'un scan SQL par XOR + `bit_count` resterait acceptable. Deux hachages 64 bits par
ligne tiennent en quelques centaines de Ko en mémoire (mission point 5, « pas de modèle lourd sur
le serveur de 4 Go ») ; la recherche elle-même est un XOR + comptage de bits vectorisés, mesurée
par `scripts/measure_visual_index_performance.py`.
"""

import uuid
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.models.identification import CardVisualIndex

HASH_BITS = 64
_UNSIGNED_64_MASK = 0xFFFFFFFFFFFFFFFF

# Poids de la distance combinée (mission point 2) : l'illustration est le signal le plus fiable
# (partagé même entre langues et souvent entre réimpressions), le cadre entier départage les
# variantes qui changent le liseré/le fond (holo, reverse) sans changer l'illustration.
ILLUSTRATION_WEIGHT = 0.6
FULL_CARD_WEIGHT = 0.4

# Calibrés par `scripts/measure_visual_index_performance.py` et `scripts/
# measure_visual_identification_rate.py` sur le jeu synthétique (mission point 4) : au-dessus de
# `CONFIDENT_SCORE_THRESHOLD`, un candidat isolé (pas de concurrent d'une autre carte à moins de
# `AMBIGUITY_MARGIN`) est considéré comme reconnu sans IA.
CONFIDENT_SCORE_THRESHOLD = 0.85
AMBIGUITY_MARGIN = 0.06
TOP_K = 5


def _unsigned64(value: int) -> int:
    return value & _UNSIGNED_64_MASK


def _popcount64(values: np.ndarray) -> np.ndarray:
    """Nombre de bits à 1 de chaque entier 64 bits d'un tableau — vectorisé (une conversion en
    octets + `unpackbits`), pas une boucle Python par ligne."""
    as_bytes = values.view(np.uint8).reshape(-1, 8)
    return np.unpackbits(as_bytes, axis=1).sum(axis=1)


@dataclass(frozen=True)
class VisualMatch:
    card_id: uuid.UUID
    language: str
    score: float
    illustration_distance: int
    full_distance: int


class VisualIndex:
    """Empreintes de toutes les cartes chargées en mémoire depuis `card_visual_index` — un
    chargement par appel de `run_identification_for_upload` (une photo, potentiellement
    plusieurs cartes), jamais par carte : le coût de lecture (~20 000 × 2 lignes) est amorti sur
    toutes les détections d'un même envoi."""

    def __init__(
        self,
        card_ids: list[uuid.UUID],
        languages: list[str],
        full_phashes: np.ndarray,
        illustration_phashes: np.ndarray,
    ) -> None:
        self._card_ids = card_ids
        self._languages = languages
        self._full = full_phashes
        self._illustration = illustration_phashes

    def __len__(self) -> int:
        return len(self._card_ids)

    @property
    def arrays_memory_bytes(self) -> int:
        """Octets occupés par les deux tableaux d'empreintes — mission point 5 (« pas de modèle
        lourd sur le serveur de 4 Go »), mesuré par
        `scripts/measure_visual_index_performance.py`."""
        return int(self._full.nbytes + self._illustration.nbytes)

    @classmethod
    def empty(cls) -> "VisualIndex":
        """Index sans aucune empreinte : `search` rend une liste vide, donc l'identification
        passe forcément par l'IA. Sert à la seconde passe (`h1-seconde-passe-ia`), où JF
        demande que l'IA fasse ET la découpe ET la reconnaissance."""
        vide = np.array([], dtype=np.uint64)
        return cls([], [], vide, vide)

    @classmethod
    async def load(cls, session: AsyncSession) -> "VisualIndex":
        result = await session.execute(
            select(
                CardVisualIndex.card_id,
                CardVisualIndex.language,
                CardVisualIndex.full_phash,
                CardVisualIndex.illustration_phash,
            )
        )
        rows = result.all()
        card_ids = [row[0] for row in rows]
        languages = [row[1] for row in rows]
        full = np.array([_unsigned64(row[2]) for row in rows], dtype=np.uint64)
        illustration = np.array([_unsigned64(row[3]) for row in rows], dtype=np.uint64)
        return cls(card_ids, languages, full, illustration)

    def search(
        self, *, full_phash: int, illustration_phash: int, limit: int = TOP_K
    ) -> list[VisualMatch]:
        """Meilleur score par carte (une carte peut apparaître deux fois, une par langue) —
        `limit` cartes distinctes au plus, triées par score décroissant."""
        if len(self) == 0:
            return []

        full_distance = _popcount64(self._full ^ np.uint64(_unsigned64(full_phash)))
        illustration_distance = _popcount64(
            self._illustration ^ np.uint64(_unsigned64(illustration_phash))
        )
        score = 1.0 - (
            ILLUSTRATION_WEIGHT * (illustration_distance / HASH_BITS)
            + FULL_CARD_WEIGHT * (full_distance / HASH_BITS)
        )

        # `order` visite les lignes par score décroissant : la première fois qu'un `card_id`
        # apparaît, c'est déjà sa meilleure ligne (fr ou en) — jamais besoin de mettre à jour une
        # entrée déjà vue. Une fois `limit` cartes distinctes trouvées, aucune ligne restante
        # (score forcément inférieur ou égal) ne peut plus entrer dans le top — on arrête là.
        order = np.argsort(-score)
        best_by_card: dict[uuid.UUID, VisualMatch] = {}
        for i in order:
            card_id = self._card_ids[i]
            if card_id in best_by_card:
                continue
            best_by_card[card_id] = VisualMatch(
                card_id=card_id,
                language=self._languages[i],
                score=float(score[i]),
                illustration_distance=int(illustration_distance[i]),
                full_distance=int(full_distance[i]),
            )
            if len(best_by_card) >= limit:
                break

        return sorted(best_by_card.values(), key=lambda m: m.score, reverse=True)


@dataclass(frozen=True)
class VisualResolution:
    """Résultat de la comparaison visuelle (mission point 2) : `confident_match` n'est renseigné
    que si un seul candidat domine clairement (au-dessus du seuil, sans concurrent d'une autre
    carte à moins de la marge) — sinon `None` et `candidates` porte le groupe ambigu, à trancher
    par l'IA si une clé est disponible (mission point 3), ou laissé à la validation humaine
    (D4)."""

    confident_match: VisualMatch | None
    candidates: list[VisualMatch]


def resolve(matches: list[VisualMatch]) -> VisualResolution:
    if not matches:
        return VisualResolution(confident_match=None, candidates=[])

    best = matches[0]
    if best.score < CONFIDENT_SCORE_THRESHOLD:
        return VisualResolution(confident_match=None, candidates=matches)

    runner_up = next((m for m in matches[1:] if m.card_id != best.card_id), None)
    if runner_up is not None and best.score - runner_up.score < AMBIGUITY_MARGIN:
        # Groupe « même illustration » (mission « risques & pièges ») : plusieurs cartes
        # distinctes se disputent le premier rang à la marge près — jamais tranché par la seule
        # comparaison visuelle (pas d'OCR local disponible sur chimera, voir le compte rendu ;
        # « sinon IA » est la solution que la mission elle-même prévoit pour ce cas).
        return VisualResolution(confident_match=None, candidates=matches)

    return VisualResolution(confident_match=best, candidates=matches)
