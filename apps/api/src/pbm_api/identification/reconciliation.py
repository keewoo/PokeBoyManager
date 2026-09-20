"""Rapprochement d'une extraction avec le catalogue (mission point 2) : numéro + extension
exacts, sinon numéro + nom, sinon recherche floue sur le nom seul ; score combiné (score du
rapprochement catalogue × confiance moyenne des champs utilisés) ; le premier candidat est
présélectionné (« Tout ajouter » l'ajoute sans clic) quand il est à la fois assez sûr et
nettement détaché du suivant.

⚠️ Calibrage de la présélection (lot `pbm-parcours-validation`, demande JF 20/09/2026). Le
score catalogue de `pbm_api.catalog.search.match_candidates` est une SOMME de poids bornée
(nom ≤ 0,5 + numéro 0,4 + total 0,1 + indice d'extension ≤ 0,15), multipliée ensuite par la
confiance moyenne (< 1) : un `combined_score` > 0,9 est donc quasi inatteignable, même pour une
carte parfaitement lue (mesuré en PROD : un numéro+extension exact plafonne vers 0,85, un nom
seul à 0,49). L'ancien seuil de 0,9 ne présélectionnait donc presque JAMAIS rien — « Tout
ajouter » n'ajoutait aucune ligne (0 `collection_items` malgré 143 détections). Le seuil est
ramené à `PRESELECTION_THRESHOLD` = 0,6, ce qui exclut par construction les paliers les
moins sûrs (nom seul ≤ 0,5, numéro seul ≤ 0,55) et retient un numéro+nom / numéro+extension
lu avec une confiance correcte ; une marge (`PRESELECTION_MARGIN`) évite d'ajouter d'office
la mauvaise extension quand un même numéro+nom existe dans plusieurs sets (ex-aequo → à
trancher par l'humain).

Réutilise `pbm_api.catalog.search.match_candidates` tel quel (mission `v2-recherche`, prévu pour
cet usage) : `set_code` filtre strictement (tier « numéro + extension »), `set_hint` ne fait que
pondérer (tiers suivants, un code d'extension mal lu par l'OCR ne doit jamais faire disparaître
la bonne carte).

Point 3 de la mission (« comparaison visuelle recadrage / image officielle des 3 candidats par
le LLM ») n'est pas implémenté : un second appel IA par carte contredirait le principe cadre
« un seul appel IA par carte, dès le premier tir » (`docs/ARCHITECTURE.md` § « la base sait,
l'IA reconnaît », qui l'emporte sur ce prompt de lot en cas de contradiction). À la place, un
score combiné sous le seuil de présélection renvoie tout de même les trois candidats, avec leur
score, pour la validation humaine (lot `v3-validation`) — voir le compte rendu.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.catalog.search import CardCandidate, match_candidates
from pbm_api.identification.schemas import CardExtraction, IdentificationCandidate

PRESELECTION_THRESHOLD = 0.6
# Écart minimal entre le meilleur candidat et le suivant pour présélectionner : sans lui, deux
# extensions partageant le même numéro+nom (même `combined_score`) verraient la première
# ajoutée arbitrairement par « Tout ajouter ». En dessous de cette marge, aucun candidat n'est
# présélectionné — l'utilisateur tranche (le bon candidat reste proposé en tête, à un clic).
PRESELECTION_MARGIN = 0.08
CANDIDATES_LIMIT = 3

# Champs de confiance pris en compte par palier — voir `_combined_score`.
_TIER_CONFIDENCE_FIELDS: dict[str, tuple[str, ...]] = {
    "numero_extension": ("number_confidence", "set_code_confidence", "name_confidence"),
    "numero_nom": ("number_confidence", "name_confidence"),
    "numero_seul": ("number_confidence",),
    "nom_flou": ("name_confidence",),
}


@dataclass(frozen=True)
class ReconciliationResult:
    tier: str
    candidates: list[IdentificationCandidate]


def _combined_score(catalog_score: float, extraction: CardExtraction, tier: str) -> float:
    fields = _TIER_CONFIDENCE_FIELDS[tier]
    confidences = [getattr(extraction, field) for field in fields if getattr(extraction, field)]
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return max(0.0, min(1.0, catalog_score)) * mean_confidence


def _to_candidates(
    raw: list[CardCandidate], extraction: CardExtraction, tier: str
) -> list[IdentificationCandidate]:
    scored = [(c, _combined_score(c.score, extraction, tier)) for c in raw]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    # Présélection : le meilleur candidat seulement, s'il est à la fois assez sûr (au-dessus du
    # seuil) ET nettement détaché du suivant (un numéro+nom qui colle à plusieurs extensions
    # reste ambigu, jamais ajouté d'office). Voir le docstring du module pour le calibrage.
    top_combined = scored[0][1] if scored else 0.0
    runner_up = scored[1][1] if len(scored) > 1 else 0.0
    top_preselected = top_combined > PRESELECTION_THRESHOLD and (
        len(scored) == 1 or (top_combined - runner_up) >= PRESELECTION_MARGIN
    )
    return [
        IdentificationCandidate(
            card_id=str(candidate.card_id),
            set_id=str(candidate.set_id),
            name=candidate.name,
            number=candidate.number,
            set_name=candidate.set_name,
            set_code=candidate.set_code,
            catalog_score=candidate.score,
            combined_score=combined,
            preselected=index == 0 and top_preselected,
        )
        for index, (candidate, combined) in enumerate(scored)
    ]


async def reconcile(session: AsyncSession, extraction: CardExtraction) -> ReconciliationResult:
    """Cascade décrite en mission point 2, dans l'ordre : un palier n'est tenté que si le
    précédent n'a rien trouvé (numéro et/ou nom mal lus, extension absente du catalogue local,
    etc. — jamais une exception, juste le palier suivant)."""
    attempts: list[tuple[str, dict]] = []
    if extraction.number and extraction.set_code:
        attempts.append(
            (
                "numero_extension",
                {
                    "numero": extraction.number,
                    "nom": extraction.name,
                    "set_code": extraction.set_code,
                },
            )
        )
    if extraction.number:
        tier = "numero_nom" if extraction.name else "numero_seul"
        attempts.append(
            (
                tier,
                {
                    "numero": extraction.number,
                    "nom": extraction.name,
                    "set_hint": extraction.set_code,
                },
            )
        )
    if extraction.name:
        # Palier final : le numéro est délibérément omis (les paliers précédents, qui le
        # filtraient strictement, viennent d'échouer — le garder ici écarterait le bon candidat
        # si c'est justement le numéro qui a été mal lu).
        attempts.append(("nom_flou", {"nom": extraction.name, "set_hint": extraction.set_code}))

    for tier, match_kwargs in attempts:
        raw = await match_candidates(
            session,
            total=extraction.total,
            langue=extraction.language,
            limit=CANDIDATES_LIMIT,
            **match_kwargs,
        )
        if raw:
            return ReconciliationResult(tier=tier, candidates=_to_candidates(raw, extraction, tier))

    return ReconciliationResult(tier="aucun_indice", candidates=[])
