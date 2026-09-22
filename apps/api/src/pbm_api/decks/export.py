"""Export d'un deck : texte standard et PDF simple (mission `v7-decks-import-export`, point 2).

Deux rendus, logique pure (aucun accès base) sur ce que `service.deck_detail` a déjà chargé :
  - **texte** : une ligne par carte « quantité nom EXTENSION numéro », groupée par type, avec un
    en-tête en commentaire (`#`). Volontairement re-lisible par `parsing.parse_deck_list` : un
    export ré-importé redonne le même deck (round-trip vérifié en test).
  - **PDF** : les vignettes des cartes et la liste. `image_loader(card_id) -> bytes | None` rend
    l'image (basse définition, `cards/{id}/low.webp` du stockage objet) ou `None` : une carte
    sans vignette montre un cadre nommé, jamais un trou silencieux. Police cœur (Helvetica) : pas
    de fonte TTF à télécharger (réseau de chimera lent) ; les textes sont réduits au latin-1 pour
    ne jamais faire échouer le rendu sur un caractère hors jeu.
"""

from __future__ import annotations

import io
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass

# Groupes d'affichage, dans l'ordre d'une liste de tournoi.
_POKEMON = {"pokemon", "pokemons"}
_TRAINER = {"dresseur", "trainer", "supporter", "item", "objet", "stade", "stadium", "outil"}
_ENERGY = {"energie", "energy"}


@dataclass(frozen=True)
class ExportCard:
    """Le strict nécessaire au rendu — découplé de `service.LoadedDeckCard` pour rester testable
    sans base ni ORM."""

    card_id: uuid.UUID
    quantity: int
    name: str
    set_code: str | None
    number: str | None
    supertype: str | None


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return " ".join(stripped.casefold().split())


def _bucket(supertype: str | None) -> str:
    n = _normalize(supertype)
    if n in _POKEMON:
        return "pokemon"
    if n in _ENERGY:
        return "energie"
    if n in _TRAINER:
        return "dresseur"
    return "autre"


_BUCKET_ORDER = ["pokemon", "dresseur", "energie", "autre"]
_BUCKET_LABEL = {
    "pokemon": "Pokémon",
    "dresseur": "Dresseur",
    "energie": "Énergie",
    "autre": "Autres",
}


def _grouped(cards: list[ExportCard]) -> list[tuple[str, list[ExportCard]]]:
    groups: dict[str, list[ExportCard]] = {b: [] for b in _BUCKET_ORDER}
    for c in cards:
        groups[_bucket(c.supertype)].append(c)
    out: list[tuple[str, list[ExportCard]]] = []
    for b in _BUCKET_ORDER:
        entries = sorted(groups[b], key=lambda c: (_normalize(c.name), c.number or ""))
        if entries:
            out.append((b, entries))
    return out


def _card_line(c: ExportCard) -> str:
    parts = [str(c.quantity), c.name]
    if c.set_code:
        parts.append(c.set_code)
    if c.number:
        parts.append(c.number)
    return " ".join(parts)


def render_text(
    *,
    deck_name: str,
    format_label: str,
    card_count: int,
    legal: bool,
    cards: list[ExportCard],
) -> str:
    legal_word = "légal" if legal else "incomplet ou illégal"
    lines = [
        f"# {deck_name}",
        f"# Format : {format_label} · {card_count} cartes · {legal_word}",
        "# Exporté depuis PokeBoyManager",
        "",
    ]
    for bucket, entries in _grouped(cards):
        count = sum(c.quantity for c in entries)
        lines.append(f"# {_BUCKET_LABEL[bucket]} ({count})")
        lines.extend(_card_line(c) for c in entries)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _l1(text: str) -> str:
    """Réduit une chaîne au latin-1 (jeu des fontes cœur de fpdf2) : un caractère hors jeu
    devient « ? » plutôt que de faire échouer tout le rendu PDF."""
    return text.encode("latin-1", "replace").decode("latin-1")


def render_pdf(
    *,
    deck_name: str,
    format_label: str,
    card_count: int,
    legal: bool,
    cards: list[ExportCard],
    image_loader: Callable[[uuid.UUID], bytes | None] | None = None,
) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, _l1(deck_name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    legal_word = "Legal" if legal else "Incomplet / illegal"
    pdf.set_text_color(90, 90, 90)
    pdf.cell(
        0, 7, _l1(f"{format_label} - {card_count} cartes - {legal_word}"),
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # Grille de vignettes. Ratio carte 63x88 mm réduit.
    cols = 4
    margin = 10
    gutter = 4
    page_w = pdf.w - 2 * margin
    cell_w = (page_w - (cols - 1) * gutter) / cols
    img_w = cell_w
    img_h = img_w * 88 / 63
    caption_h = 10
    row_h = img_h + caption_h + gutter

    ordered: list[ExportCard] = []
    for _bucket_name, entries in _grouped(cards):
        ordered.extend(entries)

    col = 0
    x0 = margin
    y = pdf.get_y()
    for c in ordered:
        if y + row_h > pdf.h - 15:
            pdf.add_page()
            y = pdf.get_y()
            col = 0
        x = x0 + col * (cell_w + gutter)
        _draw_card(pdf, c, x, y, img_w, img_h, caption_h, image_loader)
        col += 1
        if col >= cols:
            col = 0
            y += row_h

    # Liste texte en fin de document (« la liste » de la mission, sûre même sans vignette).
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, _l1("Liste"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    for bucket, entries in _grouped(cards):
        count = sum(e.quantity for e in entries)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 6, _l1(f"{_BUCKET_LABEL[bucket]} ({count})"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for e in entries:
            suffix = ""
            if e.set_code or e.number:
                suffix = f"  ({' '.join(p for p in [e.set_code, e.number] if p)})"
            pdf.cell(0, 5, _l1(f"{e.quantity}x {e.name}{suffix}"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    out = pdf.output()
    return bytes(out)


def _draw_card(pdf, c: ExportCard, x, y, img_w, img_h, caption_h, image_loader) -> None:
    data = image_loader(c.card_id) if image_loader else None
    drawn = False
    if data:
        try:
            pdf.image(io.BytesIO(data), x=x, y=y, w=img_w, h=img_h)
            drawn = True
        except Exception:  # noqa: BLE001 — image illisible : on retombe sur le cadre nommé.
            drawn = False
    if not drawn:
        pdf.set_draw_color(180, 180, 180)
        pdf.set_fill_color(238, 238, 238)
        pdf.rect(x, y, img_w, img_h, style="DF")
        pdf.set_xy(x, y + img_h / 2 - 4)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(120, 120, 120)
        pdf.multi_cell(img_w, 3.5, _l1(c.name), align="C")
        pdf.set_text_color(0, 0, 0)

    # Légende : « 3x Nom » + extension/numéro.
    pdf.set_xy(x, y + img_h + 0.5)
    pdf.set_font("Helvetica", "B", 8)
    pdf.multi_cell(img_w, 3.2, _l1(f"{c.quantity}x {c.name}"), align="C")
    ref = " ".join(p for p in [c.set_code, c.number] if p)
    if ref:
        pdf.set_x(x)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(120, 120, 120)
        pdf.multi_cell(img_w, 3.0, _l1(ref), align="C")
        pdf.set_text_color(0, 0, 0)
