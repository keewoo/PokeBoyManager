"""Analyseur tolérant d'une liste de deck collée (mission `v7-decks-import-export`, point 1).

Logique pure, sans accès base : reconnaît la forme des lignes d'une liste telle qu'on la colle
depuis un site de tournoi, l'export de Pokémon TCG Live, un forum ou un tableur. Le rapprochement
des noms au catalogue vient ensuite (`import_service`, via `catalog.search.match_candidates`) —
ici on isole seulement quantité / nom / extension / numéro.

Tolérant à dessein (point 1 : « analyseur tolérant ») :
  - quantité en tête, avec ou sans `x` (« 3 », « 3x », « 3 x ») ; absente → 1, signalé ;
  - puce de liste en tête (« - », « * », « • ») ignorée ;
  - en-tête de section (« Pokémon: 12 », « Trainer », « Énergie : 6 », « Total Cards: 60 »)
    reconnu et ignoré, jamais pris pour une carte ;
  - ligne de commentaire (« # … », « // … ») ignorée ;
  - extension + numéro en fin de ligne facultatifs — « PAF 234 », « swsh4 025 », « 234/197 »,
    ou juste « 234 » ; ou entre parenthèses « (PAF 234) » (forme de notre propre export texte) ;
    le reste est le nom (FR ou EN).

Rien n'est jamais rejeté en silence : une ligne non vide qui n'est ni un en-tête ni un
commentaire produit toujours une entrée `card` (avec ses notes) — c'est `import_service` qui dira
si le catalogue la connaît (« ce qui n'existe pas au catalogue »).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Un numéro de carte : préfixe de lettres optionnel (promo/galerie : XY121, TG05, GG10, SV107),
# des chiffres, une lettre de variante optionnelle. Doit contenir au moins un chiffre — un mot de
# nom réel (« ex », « VMAX ») n'en contient pas.
_NUMBER_RE = re.compile(r"^(?:[A-Za-z]{1,4})?\d{1,4}[A-Za-z]?$")
_NUMBER_TOTAL_RE = re.compile(r"^([A-Za-z]{0,4}\d{1,4}[A-Za-z]?)\s*/\s*(\d{1,4})$")
# Une pastille d'extension : commence par une lettre, alphanumérique, 2 à 10 caractères.
_SETCODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{1,9}$")
# Quantité en tête : « 3 », « 3x », « 3 x », « x3 ».
_QTY_RE = re.compile(r"^(?:x\s*)?(\d{1,3})\s*(?:x\b)?\s*(.*)$", re.IGNORECASE)
_BULLET_RE = re.compile(r"^[-*•·]\s+")
_PAREN_RE = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")

# Étiquettes d'en-tête de section (normalisées) — jamais des cartes.
_SECTION_LABELS = {
    "pokemon",
    "pokemons",
    "trainer",
    "trainers",
    "dresseur",
    "dresseurs",
    "supporter",
    "supporters",
    "soutien",
    "item",
    "items",
    "objet",
    "objets",
    "stade",
    "stadium",
    "tool",
    "outil",
    "outils",
    "energy",
    "energie",
    "energies",
    "total",
    "total cards",
    "totalcards",
    "cartes",
    "carte",
}

# Suffixes de NOM qui ressemblent à une pastille d'extension mais n'en sont pas — sinon
# « Dracaufeu VMAX 020 » verrait « VMAX » retiré du nom. La règle des 4 et le trigram
# survivraient au retrait, mais autant garder le nom intact.
_NAME_SUFFIXES = {
    "ex",
    "gx",
    "v",
    "vmax",
    "vstar",
    "vunion",
    "break",
    "prime",
    "star",
    "lv",
    "lvx",
    "tag",
    "tera",
    "mega",
    "prism",
}


def _normalize(text: str) -> str:
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return " ".join(stripped.casefold().split())


@dataclass(frozen=True)
class ParsedLine:
    """Une ligne de la liste collée, décomposée. `kind` vaut `card`, `section`, `comment` ou
    `blank` ; seules les lignes `card` sont rapprochées au catalogue."""

    line_no: int
    raw: str
    kind: str
    quantity: int = 1
    name: str | None = None
    set_code: str | None = None
    number: str | None = None
    total: int | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


def _looks_like_section(stripped: str) -> bool:
    """« Pokémon: 12 », « Trainer », « Total Cards: 60 » — un libellé connu, sans quantité en
    tête. On ne réclame pas de deux-points (certains exports n'en mettent pas)."""
    body = stripped.rstrip(":").strip()
    # « Pokémon: 12 » → « Pokémon » ; « Total Cards: 60 » → « Total Cards ».
    label = re.sub(r"[:\s]*\d+\s*$", "", body).strip()
    return _normalize(label) in _SECTION_LABELS


def _extract_trailing(
    tokens: list[str],
) -> tuple[list[str], str | None, str | None, int | None]:
    """Retire du BOUT d'une liste de tokens le numéro puis l'extension. Renvoie (tokens
    restants, set_code, number, total). Le numéro n'est retiré que s'il en a la forme ;
    l'extension seulement si un numéro l'a précédée (une pastille sans numéro ne veut rien dire
    dans ces listes) et si elle n'est pas un suffixe de nom connu (« VMAX », « ex »…)."""
    set_code: str | None = None
    number: str | None = None
    total: int | None = None
    if not tokens:
        return tokens, None, None, None

    m = _NUMBER_TOTAL_RE.match(tokens[-1])  # « 234/197 » collé
    if m:
        number = m.group(1)
        total = int(m.group(2))
        tokens = tokens[:-1]
    elif _NUMBER_RE.match(tokens[-1]) and not _is_name_suffix(tokens[-1]):
        number = tokens[-1]
        tokens = tokens[:-1]

    if number is not None and tokens:
        candidate = tokens[-1]
        if (
            _SETCODE_RE.match(candidate)
            and (any(ch.isdigit() for ch in candidate) or candidate.isupper())
            and not _is_name_suffix(candidate)
        ):
            set_code = candidate
            tokens = tokens[:-1]

    return tokens, set_code, number, total


def _peel_set_and_number(rest: str) -> tuple[str, str | None, str | None, int | None, list[str]]:
    """Décompose « nom [extension] [numéro] » en (nom, set_code, number, total, notes)."""
    notes: list[str] = []

    # Forme parenthésée en fin : « Dracaufeu ex (PAF 234) » (notre propre export texte).
    paren = _PAREN_RE.match(rest)
    if paren and paren.group(2).strip():
        outer_name = paren.group(1).strip()
        _toks, set_code, number, total = _extract_trailing(paren.group(2).strip().split())
        if number is not None or set_code is not None:
            return outer_name, set_code, number, total, notes
        # Parenthèse non interprétable comme extension/numéro : on la garde dans le nom.
        return rest.strip(), None, None, None, notes

    tokens, set_code, number, total = _extract_trailing(rest.split())
    name = " ".join(tokens).strip()
    if not name:
        # La ligne n'était qu'un numéro : on rend le brut comme nom pour que le rapport la montre
        # plutôt que de la perdre en silence.
        notes.append("aucun nom lisible : numéro seul")
        return rest.strip(), None, None, None, notes
    return name, set_code, number, total, notes


def _is_name_suffix(token: str) -> bool:
    return _normalize(token) in _NAME_SUFFIXES


def parse_line(line_no: int, raw: str) -> ParsedLine:
    stripped = raw.strip()
    if not stripped:
        return ParsedLine(line_no=line_no, raw=raw, kind="blank")
    if stripped.startswith("#") or stripped.startswith("//"):
        return ParsedLine(line_no=line_no, raw=raw, kind="comment")

    body = _BULLET_RE.sub("", stripped)

    notes: list[str] = []
    qty_match = _QTY_RE.match(body)
    if qty_match and qty_match.group(2).strip():
        quantity = int(qty_match.group(1))
        rest = qty_match.group(2).strip()
    else:
        # Pas de quantité en tête (ou rien d'autre que la quantité) : un en-tête de section n'a
        # pas de quantité en tête non plus, on tranche ici.
        if _looks_like_section(body):
            return ParsedLine(line_no=line_no, raw=raw, kind="section")
        quantity = 1
        rest = body
        notes.append("quantité implicite (1)")

    # Même avec une quantité, « 12 Pokémon » n'existe pas : mais un en-tête « Pokémon: 12 » a la
    # quantité en QUEUE, jamais en tête, donc il est déjà écarté ci-dessus.
    if quantity < 1:
        quantity = 1
        notes.append("quantité invalide ramenée à 1")

    name, set_code, number, total, peel_notes = _peel_set_and_number(rest)
    notes.extend(peel_notes)

    return ParsedLine(
        line_no=line_no,
        raw=raw,
        kind="card",
        quantity=quantity,
        name=name,
        set_code=set_code,
        number=number,
        total=total,
        notes=tuple(notes),
    )


def parse_deck_list(text: str) -> list[ParsedLine]:
    """Découpe une liste collée en lignes analysées, dans l'ordre. Les lignes vides et les
    commentaires sont conservés dans le résultat (kind `blank`/`comment`) pour que l'appelant
    décide de les montrer ou non — jamais supprimés en silence."""
    return [parse_line(i, raw) for i, raw in enumerate(text.splitlines(), start=1)]
