"""`pbm_api.identification.cache` (mission point 4) : recherche par distance de Hamming
(XOR + `bit_count` Postgres) — vérifie la requête SQL elle-même, pas seulement la fonction pure
`hamming_distance` (déjà couverte par `test_identification_fingerprint.py`).
"""

from pbm_api.identification.cache import HAMMING_THRESHOLD, find_cached, store_cache
from pbm_api.identification.schemas import CardExtraction

_EXTRACTION = CardExtraction(
    name="Pikachu", name_confidence=0.9, number="025", number_confidence=0.9
)
_CANDIDATES = [{"card_id": "fixed", "combined_score": 0.9}]


async def test_find_cached_returns_none_on_empty_cache(db_session):
    assert await find_cached(db_session, 123456789) is None


async def test_find_cached_hits_on_exact_phash(db_session):
    await store_cache(db_session, 42, _EXTRACTION, _CANDIDATES, "numero_extension")

    hit = await find_cached(db_session, 42)

    assert hit is not None
    assert hit.candidates == _CANDIDATES
    assert hit.tier == "numero_extension"


async def test_find_cached_hits_within_hamming_threshold(db_session):
    await store_cache(db_session, 0, _EXTRACTION, _CANDIDATES, "nom_flou")

    close_bits = (1 << HAMMING_THRESHOLD) - 1  # HAMMING_THRESHOLD bits différents de 0
    hit = await find_cached(db_session, close_bits)

    assert hit is not None


async def test_find_cached_misses_beyond_hamming_threshold(db_session):
    await store_cache(db_session, 0, _EXTRACTION, _CANDIDATES, "nom_flou")

    far_bits = (1 << (HAMMING_THRESHOLD + 8)) - 1  # bien plus de bits différents que le seuil
    hit = await find_cached(db_session, far_bits)

    assert hit is None


async def test_store_cache_handles_negative_signed_phash(db_session):
    """`compute_phash` peut renvoyer une valeur négative (bit de poids fort à 1, voir
    `pbm_api.identification.fingerprint._to_signed64`) — le cache doit la stocker et la
    retrouver sans erreur de conversion."""
    negative_phash = -(2**62)
    await store_cache(db_session, negative_phash, _EXTRACTION, _CANDIDATES, "numero_extension")

    assert await find_cached(db_session, negative_phash) is not None
