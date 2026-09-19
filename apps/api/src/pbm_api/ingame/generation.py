"""Synthèse IA sur les données de jeu — mission `v4-jeu` point 3.

Contrairement à `pbm_api.insights.generation` (anecdotes), l'IA ne reçoit ici aucun texte
externe non vérifié : légalités, règle des Prix, attaques/talents viennent du catalogue
(déterministe) et les decklists viennent de `card_tournament_presence`, déjà vérifiées et
datées par le relevé périodique (`pbm_api.ingame.tournaments`). Le risque « hallucination »
porte donc uniquement sur le risque de la mission ("ne jamais inventer un résultat de
tournoi") : le prompt interdit explicitement d'affirmer une présence en tournoi au-delà des
decks listés, et de citer un placement non fourni.
"""

from pydantic import BaseModel, Field

MAX_RELATED_CARDS = 8


class InGameStudyExtraction(BaseModel):
    role: str = Field(min_length=1, max_length=400)
    strengths: str = Field(min_length=1, max_length=400)
    weaknesses: str = Field(min_length=1, max_length=400)
    related_cards: list[str] = Field(default_factory=list, max_length=MAX_RELATED_CARDS)
    playability_note: str = Field(min_length=1, max_length=300)


def render_study_text(extraction: InGameStudyExtraction) -> str:
    lines = [
        f"Rôle : {extraction.role}",
        f"Forces : {extraction.strengths}",
        f"Limites : {extraction.weaknesses}",
        f"Note de jouabilité : {extraction.playability_note}",
    ]
    if extraction.related_cards:
        lines.append(f"Cartes associées : {', '.join(extraction.related_cards)}")
    return "\n".join(lines)


def build_prompt(
    *,
    card_name: str,
    set_name: str,
    legal_standard: bool | None,
    legal_expanded: bool | None,
    prize_label: str,
    attacks: list | None,
    abilities: list | None,
    tournament_decks: list[dict] | None,
) -> str:
    def _yes_no(value: bool | None) -> str:
        if value is None:
            return "inconnu"
        return "légale" if value else "non légale"

    lines = [
        f'Tu rédiges, pour la fiche de la carte Pokémon "{card_name}" (extension "{set_name}"), '
        "une étude d'utilisation en jeu : rôle typique dans un deck, forces, limites, cartes "
        "associées, et une note de jouabilité courte.",
        "",
        f"Format Standard : {_yes_no(legal_standard)}.",
        f"Format Étendu : {_yes_no(legal_expanded)}.",
        f"Règle des Prix : {prize_label}.",
    ]
    if attacks:
        lines.append(f"Attaques (données du catalogue, à ne pas réinventer) : {attacks}")
    if abilities:
        lines.append(f"Talents (données du catalogue, à ne pas réinventer) : {abilities}")

    if tournament_decks:
        decks_text = "; ".join(
            f'{d["deck_name"]} — {d["tournament_name"]} ({d["placement"]})'
            for d in tournament_decks
        )
        lines.append(
            "Présence en tournoi relevée (source Limitless TCG, n'utilise que ces résultats, "
            f"n'invente aucun autre tournoi ni placement) : {decks_text}"
        )
    else:
        lines.append(
            "Aucune présence en tournoi n'a été relevée pour cette carte à ce jour : ne "
            "prétends pas le contraire, indique plutôt si son profil (légalités, règle des "
            "Prix, attaques) explique cette absence."
        )

    lines.append(
        "Règle stricte : base-toi uniquement sur les informations ci-dessus, n'invente aucun "
        "tournoi, aucun placement, aucune règle absente de ce message."
    )
    return "\n".join(lines)
