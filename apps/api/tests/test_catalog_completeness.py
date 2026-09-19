"""Complétude minimale sur un échantillon importé — mission `v2-catalogue-complet` point 6.

Réutilise les doublures TCGdex/Pokémon TCG API de `test_import_service.py` (formes réelles
capturées le 2026-09-19) : un import correct doit remplir la quasi-totalité des champs de
complétude sur cet échantillon. `test_completeness_stats_reach_minimum_thresholds` échoue si une
régression fait chuter silencieusement un des taux (ex : un champ qui cesse d'être peuplé par
`import_service`).
"""

from test_import_service import FakePtcgClient, FakeTcgdexClient

from pbm_api.catalog.completeness import compute_completeness_stats
from pbm_api.catalog.import_service import import_catalogue

# Seuils minimaux attendus sur l'échantillon de test (2 cartes, voir FR_CARD_DETAILS) — pas des
# seuils de production (mission point 4 : le vrai rapport se lit dans
# docs/catalogue/COMPLETUDE.md, généré sur le catalogue complet).
MIN_IMAGE_PCT = 100.0
MIN_PTCG_PCT = 100.0
MIN_NAME_FR_PCT = 100.0
MIN_NAME_EN_PCT = 100.0


async def test_completeness_stats_reach_minimum_thresholds(db_session):
    await import_catalogue(db_session, FakeTcgdexClient(), FakePtcgClient(), languages=("fr", "en"))

    stats = await compute_completeness_stats(db_session)

    assert stats.cards_total == 2
    assert stats.pct(stats.cards_with_image) >= MIN_IMAGE_PCT
    assert stats.pct(stats.cards_with_ptcg) >= MIN_PTCG_PCT
    assert stats.pct(stats.names_by_lang.get("fr", 0)) >= MIN_NAME_FR_PCT
    assert stats.pct(stats.names_by_lang.get("en", 0)) >= MIN_NAME_EN_PCT
    # La fixture n'importe que 2 des 165 cartes officielles annoncées par `cardCount.official`
    # (FR_SET_DETAIL) — le trou est réel et attendu, la mission interdit d'annoncer "complet"
    # sans le rapport : le calcul doit le voir, pas le masquer.
    assert stats.gaps == [("sv03.5", "151", 2, 165)]
    # Rapprochée avec Pokémon TCG API (voir PTCG_SETS dans la fixture) : aucune extension orpheline.
    assert stats.sets_without_ptcg == []


async def test_completeness_stats_reflect_partial_fields_honestly(db_session):
    """Le fixture Pikachu (sv03.5-025) n'a ni faiblesses/résistances ni coût de retraite — le
    rapport doit le refléter (50 %), jamais arrondir à 100 % ni planter."""
    await import_catalogue(db_session, FakeTcgdexClient(), FakePtcgClient(), languages=("fr", "en"))

    stats = await compute_completeness_stats(db_session)

    assert stats.cards_with_weaknesses_or_resistances == 1
    assert stats.pct(stats.cards_with_weaknesses_or_resistances) == 50.0
    assert stats.cards_with_retreat == 1
