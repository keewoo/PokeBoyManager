"""Recherche catalogue (mission `v2-recherche`).

`test_search_catalog_route_exists` échoue sans ce lot (`404 Not Found`, aucune route
`/catalog/search`) et passe une fois le routeur posé.

Catalogue public, pas d'utilisateur : pas de test d'accès croisé ici (voir
`docs/roadmap/comptes-rendus/v2-recherche.md`, tâche `securite` sans objet).

`CATALOG_QUERIES` fournit les 50 requêtes de référence exigées par la mission (point 3),
couvrant noms FR/EN, accents/tirets, casse, requêtes partielles, numéros simples et zéro-remplis,
formats promo/galerie (`TG05`, `GG10`, `SV107`, `XY121`), format `numéro/total`, désambiguïsation
par le total quand plusieurs cartes partagent un numéro, filtres explicites `set`/`lang`, et
requêtes combinant nom de carte + nom d'extension dans une seule chaîne.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from pbm_api.db import get_session
from pbm_api.main import app
from pbm_api.models import Card, CardName, Set


async def _make_set(session, *, code, name, series, total_cards) -> Set:
    set_row = Set(code=code, name=name, series=series, total_cards=total_cards)
    session.add(set_row)
    await session.flush()
    return set_row


async def _make_card(session, set_row, *, number, name, fr, en) -> Card:
    card = Card(set_id=set_row.id, number=number, name=name)
    session.add(card)
    await session.flush()
    session.add(CardName(card_id=card.id, language="fr", name=fr))
    session.add(CardName(card_id=card.id, language="en", name=en))
    await session.flush()
    return card


@pytest.fixture
async def catalog(db_session):
    """~20 cartes sur 7 extensions — assez pour désambiguïser (numéros partagés entre
    extensions, noms proches) sans dépendre du volume réel du catalogue importé."""
    suffix = uuid.uuid4().hex[:8]  # évite toute collision d'`UniqueConstraint` entre tests

    sv1 = await _make_set(
        db_session,
        code=f"sv01-{suffix}",
        name="Écarlate et Violet",
        series="Écarlate et Violet",
        total_cards=198,
    )
    sv151 = await _make_set(
        db_session,
        code=f"sv03pt5-{suffix}",
        name="151",
        series="Écarlate et Violet",
        total_cards=165,
    )
    fusion = await _make_set(
        db_session,
        code=f"swsh07-{suffix}",
        name="Poing de Fusion",
        series="Épée et Bouclier",
        total_cards=163,
    )
    voltage = await _make_set(
        db_session,
        code=f"swsh04-{suffix}",
        name="Voltage Éclatant",
        series="Épée et Bouclier",
        total_cards=185,
    )
    stars = await _make_set(
        db_session,
        code=f"swsh12-{suffix}",
        name="Stars Étincelantes",
        series="Épée et Bouclier",
        total_cards=195,
    )
    svp = await _make_set(
        db_session,
        code=f"svp-{suffix}",
        name="Promos Écarlate et Violet",
        series="Écarlate et Violet",
        total_cards=None,
    )
    xyp = await _make_set(
        db_session,
        code=f"xyp-{suffix}",
        name="Promos XY",
        series="XY",
        total_cards=None,
    )

    cards = {
        "dracaufeu_ex": await _make_card(
            db_session, sv1, number="006", name="Dracaufeu-ex", fr="Dracaufeu-ex", en="Charizard ex"
        ),
        "chochodile": await _make_card(
            db_session, sv1, number="020", name="Chochodile", fr="Chochodile", en="Quaxwell"
        ),
        "miraidon_ex": await _make_card(
            db_session, sv1, number="234", name="Miraidon-ex", fr="Miraidon-ex", en="Miraidon ex"
        ),
        "nymphali_163": await _make_card(
            db_session, sv1, number="163", name="Nymphali", fr="Nymphali", en="Sylveon"
        ),
        "mewtwo_151": await _make_card(
            db_session, sv151, number="006", name="Mewtwo", fr="Mewtwo", en="Mewtwo"
        ),
        "pikachu_151": await _make_card(
            db_session, sv151, number="025", name="Pikachu", fr="Pikachu", en="Pikachu"
        ),
        "mew_ex_151": await _make_card(
            db_session, sv151, number="151", name="Mew-ex", fr="Mew-ex", en="Mew ex"
        ),
        "germignon": await _make_card(
            db_session, fusion, number="001", name="Germignon", fr="Germignon", en="Chikorita"
        ),
        "dracaufeu_v": await _make_card(
            db_session, fusion, number="154", name="Dracaufeu-V", fr="Dracaufeu-V", en="Charizard V"
        ),
        "dracaufeu_vmax": await _make_card(
            db_session,
            fusion,
            number="155",
            name="Dracaufeu-VMAX",
            fr="Dracaufeu-VMAX",
            en="Charizard VMAX",
        ),
        "fantominus_163": await _make_card(
            db_session, fusion, number="163", name="Fantominus", fr="Fantominus", en="Gengar"
        ),
        "pikachu_v": await _make_card(
            db_session, voltage, number="043", name="Pikachu V", fr="Pikachu V", en="Pikachu V"
        ),
        "pikachu_vmax": await _make_card(
            db_session,
            voltage,
            number="044",
            name="Pikachu VMAX",
            fr="Pikachu VMAX",
            en="Pikachu VMAX",
        ),
        "pikachu_tg": await _make_card(
            db_session, stars, number="TG05", name="Pikachu", fr="Pikachu", en="Pikachu"
        ),
        "evoli_gg": await _make_card(
            db_session, stars, number="GG10", name="Évoli", fr="Évoli", en="Eevee"
        ),
        "ho_oh": await _make_card(
            db_session, stars, number="030", name="Ho-Oh", fr="Ho-Oh", en="Ho-Oh"
        ),
        "pikachu_ex_promo": await _make_card(
            db_session, svp, number="SV107", name="Pikachu-ex", fr="Pikachu-ex", en="Pikachu ex"
        ),
        "mew_promo_xy": await _make_card(
            db_session, xyp, number="XY121", name="Mew", fr="Mew", en="Mew"
        ),
    }
    return {
        "cards": cards,
        "sets": {
            "sv1": sv1,
            "sv151": sv151,
            "fusion": fusion,
            "voltage": voltage,
            "stars": stars,
            "svp": svp,
            "xyp": xyp,
        },
    }


async def _search(db_session, **params) -> list[dict]:
    async def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/catalog/search", params=params)
        assert response.status_code == 200, response.text
        return response.json()
    finally:
        app.dependency_overrides.clear()


async def test_search_catalog_route_exists(db_session):
    results = await _search(db_session, q="a")
    assert isinstance(results, list)


async def test_search_missing_q_is_rejected(db_session):
    async def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/catalog/search")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


# --- 50 requêtes de référence (mission point 3) ---------------------------------------------
#
# Chaque cas : `params` passés à `/catalog/search`, et soit `top` (clé de `cards` attendue en
# première position), soit `contains` (clés attendues quelque part dans les résultats), soit
# `empty=True` (aucun résultat, ex : gibberish ou carte inconnue).

CATALOG_QUERIES = [
    # -- Noms simples, langue non fixée (FR et EN doivent tous les deux fonctionner) --
    {"id": "nom-fr-exact", "params": {"q": "Dracaufeu-ex"}, "top": "dracaufeu_ex"},
    {
        "id": "nom-fr-simple",
        "params": {"q": "dracaufeu"},
        "contains": ["dracaufeu_ex", "dracaufeu_v", "dracaufeu_vmax"],
    },
    {
        "id": "nom-en-simple",
        "params": {"q": "charizard"},
        "contains": ["dracaufeu_ex", "dracaufeu_v", "dracaufeu_vmax"],
    },
    {"id": "nom-en-exact-cross-lang", "params": {"q": "Charizard ex"}, "top": "dracaufeu_ex"},
    {"id": "nom-casse-majuscules", "params": {"q": "CHOCHODILE"}, "top": "chochodile"},
    {"id": "nom-casse-minuscules", "params": {"q": "mewtwo"}, "top": "mewtwo_151"},
    {"id": "nom-accent-sans-accent", "params": {"q": "evoli"}, "top": "evoli_gg"},
    {"id": "nom-accent-avec-accent", "params": {"q": "Évoli"}, "top": "evoli_gg"},
    {"id": "nom-en-accent-sans", "params": {"q": "eevee"}, "top": "evoli_gg"},
    {"id": "nom-tiret-espace", "params": {"q": "ho oh"}, "top": "ho_oh"},
    {"id": "nom-tiret-exact", "params": {"q": "Ho-Oh"}, "top": "ho_oh"},
    {
        "id": "nom-espaces-en-trop",
        "params": {"q": "  pikachu   "},
        "contains": ["pikachu_151", "pikachu_v", "pikachu_vmax", "pikachu_tg", "pikachu_ex_promo"],
    },
    {"id": "nom-gengar-en", "params": {"q": "gengar"}, "top": "fantominus_163"},
    {"id": "nom-sylveon-en", "params": {"q": "sylveon"}, "top": "nymphali_163"},
    {"id": "nom-chikorita-en", "params": {"q": "chikorita"}, "top": "germignon"},
    {"id": "nom-quaxwell-en", "params": {"q": "quaxwell"}, "top": "chochodile"},
    {"id": "nom-partiel-court", "params": {"q": "miraidon"}, "top": "miraidon_ex"},
    {"id": "nom-avec-suffixe-ex", "params": {"q": "Mew-ex"}, "top": "mew_ex_151"},
    {
        "id": "nom-mew-seul-ambigu",
        "params": {"q": "mew"},
        "contains": ["mew_ex_151", "mew_promo_xy"],
    },
    {"id": "nom-inconnu", "params": {"q": "zzzzznotexist"}, "empty": True},
    {"id": "nom-gibberish", "params": {"q": "qwjkzxqvwp"}, "empty": True},
    # -- Numéros simples et zéro-remplissage --
    {"id": "numero-simple-25", "params": {"q": "25"}, "top": "pikachu_151"},
    {
        "id": "numero-zero-remplis-006",
        "params": {"q": "006"},
        "contains": ["dracaufeu_ex", "mewtwo_151"],
    },
    {"id": "numero-sans-zero-6", "params": {"q": "6"}, "contains": ["dracaufeu_ex", "mewtwo_151"]},
    {"id": "numero-234", "params": {"q": "234"}, "top": "miraidon_ex"},
    {
        "id": "numero-partage-163",
        "params": {"q": "163"},
        "contains": ["nymphali_163", "fantominus_163"],
    },
    # -- Formats promo / galerie --
    {"id": "numero-tg-minuscule", "params": {"q": "tg05"}, "top": "pikachu_tg"},
    {"id": "numero-tg-majuscule", "params": {"q": "TG05"}, "top": "pikachu_tg"},
    {"id": "numero-gg", "params": {"q": "GG10"}, "top": "evoli_gg"},
    {"id": "numero-sv-promo", "params": {"q": "SV107"}, "top": "pikachu_ex_promo"},
    {"id": "numero-xy-promo", "params": {"q": "XY121"}, "top": "mew_promo_xy"},
    {"id": "numero-xy-promo-minuscule", "params": {"q": "xy121"}, "top": "mew_promo_xy"},
    # -- Format numéro/total (désambiguïsation) --
    {"id": "numero-total-234-198", "params": {"q": "234/198"}, "top": "miraidon_ex"},
    {"id": "numero-total-6-165", "params": {"q": "6/165"}, "top": "mewtwo_151"},
    {"id": "numero-total-desambiguise-163-sv1", "params": {"q": "163/198"}, "top": "nymphali_163"},
    {
        "id": "numero-total-desambiguise-163-fusion",
        "params": {"q": "163/163"},
        "top": "fantominus_163",
    },
    {
        "id": "numero-total-inconnu-conserve-le-numero",
        "params": {"q": "25/999"},
        "top": "pikachu_151",
    },
    # -- Filtre explicite `set` (code ou nom exact) --
    {
        "id": "filtre-set-par-code",
        "params": {"q": "pikachu"},
        "set_key": "voltage",
        "contains": ["pikachu_v", "pikachu_vmax"],
        "excludes": ["pikachu_151", "pikachu_tg"],
    },
    {"id": "filtre-set-par-nom", "params": {"q": "pikachu", "set": "151"}, "top": "pikachu_151"},
    {
        "id": "filtre-set-exclut-les-autres",
        "params": {"q": "dracaufeu"},
        "set_key": "fusion",
        "contains": ["dracaufeu_v", "dracaufeu_vmax"],
        "excludes": ["dracaufeu_ex"],
    },
    # -- Filtre explicite `lang` --
    {"id": "filtre-lang-en-sur-nom-fr", "params": {"q": "Dracaufeu", "lang": "en"}, "empty": True},
    {"id": "filtre-lang-fr-sur-nom-en", "params": {"q": "Charizard", "lang": "fr"}, "empty": True},
    {
        "id": "filtre-lang-en-matching",
        "params": {"q": "Charizard", "lang": "en"},
        "contains": ["dracaufeu_ex", "dracaufeu_v", "dracaufeu_vmax"],
    },
    # -- Nom de carte + nom d'extension combinés dans une seule chaîne --
    {
        "id": "nom-plus-extension-pikachu-vmax-voltage",
        "params": {"q": "Pikachu VMAX Voltage Éclatant"},
        "top": "pikachu_vmax",
    },
    {"id": "nom-plus-extension-mewtwo-151", "params": {"q": "Mewtwo 151"}, "top": "mewtwo_151"},
    {
        "id": "nom-plus-extension-dracaufeu-poing-de-fusion",
        "params": {"q": "Dracaufeu VMAX Poing de Fusion"},
        "top": "dracaufeu_vmax",
    },
    # -- Casse / robustesse générale --
    {"id": "numero-espace-autour-slash", "params": {"q": "234 / 198"}, "top": "miraidon_ex"},
    {"id": "nom-avec-apostrophe-non-genante", "params": {"q": "l'evoli"}, "top": "evoli_gg"},
    {
        "id": "nom-tres-long-hors-catalogue",
        "params": {"q": "une carte qui n'existe vraiment pas du tout"},
        "empty": True,
    },
    {"id": "numero-hors-limites", "params": {"q": "9999"}, "empty": True},
]

assert len(CATALOG_QUERIES) >= 50, f"seulement {len(CATALOG_QUERIES)} requêtes de référence"


@pytest.mark.parametrize("case", CATALOG_QUERIES, ids=[c["id"] for c in CATALOG_QUERIES])
async def test_catalog_search_reference_queries(db_session, catalog, case):
    params = dict(case["params"])
    if "set_key" in case:
        params["set"] = catalog["sets"][case["set_key"]].code

    results = await _search(db_session, **params)
    result_keys = set()
    cards_by_id = {str(card.id): key for key, card in catalog["cards"].items()}
    for row in results:
        key = cards_by_id.get(row["card_id"])
        if key is not None:
            result_keys.add(key)

    if case.get("empty"):
        assert result_keys == set(), f"attendu vide, obtenu {result_keys}"
        return

    if "top" in case:
        assert results, "aucun résultat, attendu au moins un candidat"
        top_key = cards_by_id.get(results[0]["card_id"])
        assert top_key == case["top"], f"premier résultat = {top_key}, attendu {case['top']}"

    if "contains" in case:
        expected = set(case["contains"])
        assert expected <= result_keys, f"manquants: {expected - result_keys}"

    if "excludes" in case:
        for key in case["excludes"]:
            assert key not in result_keys, f"{key} ne devrait pas apparaître"
