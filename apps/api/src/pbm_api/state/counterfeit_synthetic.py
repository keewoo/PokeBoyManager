"""Jeu de 60 cartes étiquetées (mission `v6-contrefacon` point 1 : « jeu de 30 contrefaçons
connues et 30 vraies cartes ») pour mesurer la précision de `pbm_api.state.counterfeit.
assess_counterfeit` — pas une image, comme `pbm_api.identification.synthetic` : ce module simule
directement les entrées de la fonction (signal IA + carte catalogue rapprochée), pas une photo
(aucune carte physique ni clé IA réelle sur chimera).

30 cas étiquetés `contrefaçon` (mission point 1) répartis en trois familles, une par canal de
détection : signal explicite de l'IA (indices visuels), variante absente du catalogue, total de
série imprimé incohérent avec l'extension. 30 cas étiquetés `authentique`, dont des pièges
délibérés qui ne doivent JAMAIS déclencher un signal (mission « risques & pièges ») : variante
confirmée par le catalogue, secret rare dont le numéro dépasse le total sans que le total change,
variante `full_art`/`other` non modélisée par TCGdex, catalogue incomplet pour la carte (clé de
variante absente plutôt que `False` explicite).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LabeledCard:
    set_code: str
    set_name: str
    total_cards: int | None
    number: str
    name: str
    rarity: str | None
    variants: dict | None


@dataclass(frozen=True)
class SyntheticCounterfeitCase:
    id: str
    is_counterfeit: bool
    card: LabeledCard
    ai_suspected: bool
    ai_reason: str | None
    variant_guess: str | None
    extraction_total: int | None


def _card(i: int, *, total_cards: int = 102, rarity: str = "Common", variants: dict) -> LabeledCard:
    return LabeledCard(
        set_code="syn-cf",
        set_name="Ensemble synthétique contrefaçon",
        total_cards=total_cards,
        number=str(i + 1),
        name=f"Carte synthétique {i + 1}",
        rarity=rarity,
        variants=variants,
    )


def _counterfeit_via_ai_signal(i: int) -> SyntheticCounterfeitCase:
    """Famille A (10 cas) : aucun contrôle déterministe ne peut trancher (carte et total
    cohérents avec le catalogue) — seul l'indice visuel rendu par le LLM (police, couleurs,
    format du numéro) révèle la contrefaçon."""
    card = _card(i, variants={"normal": True, "holo": False, "reverse": False})
    return SyntheticCounterfeitCase(
        id=f"cf_ai_{i:02d}",
        is_counterfeit=True,
        card=card,
        ai_suspected=True,
        ai_reason="police et couleurs incohérentes avec une impression officielle",
        variant_guess="normal",
        extraction_total=card.total_cards,
    )


def _counterfeit_via_variant_absent(i: int) -> SyntheticCounterfeitCase:
    """Famille B (10 cas) : variante perçue (holo, reverse holo, 1ère édition en rotation) alors
    que le catalogue déclare explicitement cette variante absente pour la carte — mission point 1,
    « variante absente du catalogue »."""
    perceived = ["holo", "reverse_holo", "first_edition"][i % 3]
    catalog_key = {"holo": "holo", "reverse_holo": "reverse", "first_edition": "firstEdition"}[
        perceived
    ]
    card = _card(
        i,
        variants={"normal": True, "holo": False, "reverse": False, "firstEdition": False}
        | {catalog_key: False},
    )
    return SyntheticCounterfeitCase(
        id=f"cf_variant_{i:02d}",
        is_counterfeit=True,
        card=card,
        ai_suspected=False,
        ai_reason=None,
        variant_guess=perceived,
        extraction_total=card.total_cards,
    )


def _counterfeit_via_impossible_total(i: int) -> SyntheticCounterfeitCase:
    """Famille C (10 cas) : total de série imprimé qui ne correspond à aucun total officiel de
    l'extension reconnue — mission point 1, « numéro impossible »."""
    card = _card(i, total_cards=102, variants={"normal": True, "holo": False, "reverse": False})
    return SyntheticCounterfeitCase(
        id=f"cf_total_{i:02d}",
        is_counterfeit=True,
        card=card,
        ai_suspected=False,
        ai_reason=None,
        variant_guess="normal",
        extraction_total=999,
    )


def _genuine_plain(i: int) -> SyntheticCounterfeitCase:
    """Famille D (10 cas) : carte normale, rien d'inhabituel."""
    card = _card(i, variants={"normal": True, "holo": False, "reverse": False})
    return SyntheticCounterfeitCase(
        id=f"ok_plain_{i:02d}",
        is_counterfeit=False,
        card=card,
        ai_suspected=False,
        ai_reason=None,
        variant_guess="normal",
        extraction_total=card.total_cards,
    )


def _genuine_variant_confirmed(i: int) -> SyntheticCounterfeitCase:
    """Famille E (10 cas) : variante rare mais réellement documentée par le catalogue pour cette
    carte — ne doit jamais être confondue avec la famille B."""
    perceived = ["holo", "reverse_holo", "first_edition"][i % 3]
    catalog_key = {"holo": "holo", "reverse_holo": "reverse", "first_edition": "firstEdition"}[
        perceived
    ]
    card = _card(
        i,
        rarity="Rare Holo",
        variants={"normal": False, "holo": False, "reverse": False, "firstEdition": False}
        | {catalog_key: True},
    )
    return SyntheticCounterfeitCase(
        id=f"ok_variant_{i:02d}",
        is_counterfeit=False,
        card=card,
        ai_suspected=False,
        ai_reason=None,
        variant_guess=perceived,
        extraction_total=card.total_cards,
    )


def _genuine_edge_case(i: int) -> SyntheticCounterfeitCase:
    """Famille F (10 cas) : pièges délibérés — un contrôle naïf les signalerait à tort (mission
    « risques & pièges », faux positifs sur promos/secrets rares)."""
    kind = i % 4
    if kind == 0:
        # Secret rare : numéro au-delà du total, mais le TOTAL imprimé est inchangé.
        card = _card(i, total_cards=198, rarity="Rare Secret", variants={"normal": True})
        return SyntheticCounterfeitCase(
            id=f"ok_secret_{i:02d}",
            is_counterfeit=False,
            card=card,
            ai_suspected=False,
            ai_reason=None,
            variant_guess="normal",
            extraction_total=198,
        )
    if kind == 1:
        # Variante non modélisée par TCGdex (full art) : aucun contrôle possible, jamais un signal.
        card = _card(i, rarity="Rare Ultra", variants={"normal": False, "holo": False})
        return SyntheticCounterfeitCase(
            id=f"ok_fullart_{i:02d}",
            is_counterfeit=False,
            card=card,
            ai_suspected=False,
            ai_reason=None,
            variant_guess="full_art",
            extraction_total=card.total_cards,
        )
    if kind == 2:
        # Catalogue incomplet pour cette carte : clé de variante absente du JSONB (pas `False`
        # explicite) -> pas de preuve, pas de signal.
        card = _card(i, variants={"normal": True})
        return SyntheticCounterfeitCase(
            id=f"ok_incomplete_{i:02d}",
            is_counterfeit=False,
            card=card,
            ai_suspected=False,
            ai_reason=None,
            variant_guess="reverse_holo",
            extraction_total=card.total_cards,
        )
    # Total non lu sur la photo (None) : pas de comparaison possible, pas de signal.
    card = _card(i, variants={"normal": True, "holo": False, "reverse": False})
    return SyntheticCounterfeitCase(
        id=f"ok_nototal_{i:02d}",
        is_counterfeit=False,
        card=card,
        ai_suspected=False,
        ai_reason=None,
        variant_guess="normal",
        extraction_total=None,
    )


def generate_dataset() -> list[SyntheticCounterfeitCase]:
    """30 contrefaçons connues (mission point 1) + 30 vraies cartes, aucune aléa (chaque famille
    exerce un canal de détection ou un piège précis, pas un bruit à faire varier d'un tirage à
    l'autre)."""
    cases: list[SyntheticCounterfeitCase] = []
    for i in range(10):
        cases.append(_counterfeit_via_ai_signal(i))
    for i in range(10):
        cases.append(_counterfeit_via_variant_absent(i))
    for i in range(10):
        cases.append(_counterfeit_via_impossible_total(i))
    for i in range(10):
        cases.append(_genuine_plain(i))
    for i in range(10):
        cases.append(_genuine_variant_confirmed(i))
    for i in range(10):
        cases.append(_genuine_edge_case(i))
    assert len(cases) == 60
    assert sum(1 for c in cases if c.is_counterfeit) == 30
    assert sum(1 for c in cases if not c.is_counterfeit) == 30
    return cases
