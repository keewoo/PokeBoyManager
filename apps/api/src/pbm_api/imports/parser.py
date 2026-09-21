"""Lecture d'un CSV d'import (mission `v6-import-export`) : notre propre format d'export
(`pbm_api.export.archive.CSV_FIELDS`, réimportable tel quel) et les exports courants d'autres
outils de suivi de collection, réconciliés par un dictionnaire d'alias d'en-têtes plutôt qu'un
format figé — TCGdex/Pokémon TCG API n'imposent aucune norme commune aux outils tiers.

Pas de dépendance à FastAPI, SQLAlchemy ni au stockage : reçoit des octets, renvoie des lignes
déjà normalisées. Testable seul, comme `pbm_api.export.archive`.
"""

import csv
import io
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pbm_api.imports.errors import (
    ImportFileEmptyError,
    ImportFileUndecodableError,
    ImportTooManyRowsError,
)

# Alias reconnus par champ canonique, déjà normalisés (voir `_normalize`) — couvre notre propre
# export (`carte`/`extension`/`numero`/...) et les libellés les plus courants vus sur des exports
# tiers en français ou en anglais.
_HEADER_ALIASES: dict[str, str] = {
    "carte": "name", "nom": "name", "name": "name", "card name": "name", "card": "name",
    "numero": "number", "num": "number", "number": "number", "card number": "number",
    "card #": "number", "no": "number",
    "extension": "set_code", "set": "set_code", "set code": "set_code", "set_code": "set_code",
    "edition": "set_code", "set name": "set_code",
    "langue": "language", "language": "language", "lang": "language",
    "variante": "variant", "variant": "variant", "holo": "variant",
    "quantite": "quantity", "quantity": "quantity", "qty": "quantity", "count": "quantity",
    "etat": "condition_grade", "état": "condition_grade", "condition": "condition_grade",
    "grade": "condition_grade",
    "prix_achat": "purchase_price", "prix d'achat": "purchase_price",
    "purchase_price": "purchase_price", "price": "purchase_price", "prix": "purchase_price",
    "acquis_le": "acquired_at", "date": "acquired_at", "purchase_date": "acquired_at",
    "date_ajout": "acquired_at", "acquired_at": "acquired_at",
}

# Alias de variante — mêmes valeurs que `pbm_api.models.catalog.PriceVariant`, jamais devinées :
# une valeur non reconnue reste `None` (variante par défaut appliquée par le rapprochement),
# jamais une variante inventée à partir d'un texte incertain.
_VARIANT_ALIASES: dict[str, str] = {
    "normal": "normal", "normale": "normal", "": "normal",
    "holo": "holo", "holographique": "holo", "holofoil": "holo",
    "reverse": "reverse_holo", "reverse holo": "reverse_holo", "reverse holofoil": "reverse_holo",
    "1ere edition": "first_edition", "1st edition": "first_edition",
    "first edition": "first_edition",
}

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")


def _normalize(text: str) -> str:
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return " ".join(stripped.casefold().split())


@dataclass(frozen=True)
class ParsedImportRow:
    line_number: int
    name: str | None
    number: str | None
    set_code: str | None
    language: str | None
    variant: str
    quantity: int
    condition_grade: str | None
    purchase_price: Decimal | None
    acquired_at: date | None


@dataclass(frozen=True)
class ParsedImportResult:
    rows: list[ParsedImportRow]
    # Ligne (1-based, en-tête compris) et motif — une ligne ignorée n'est jamais retirée en
    # silence (`CLAUDE.md` : « un repli silencieux ... est interdit »).
    ignored: list[tuple[int, str]]


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportFileUndecodableError


def _sniff_dialect(sample: str) -> type[csv.Dialect]:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        # Un seul en-tête sur la première ligne (aucun délimiteur à détecter) : virgule par
        # défaut, format le plus commun — jamais une exception qui bloquerait tout l'import.
        return csv.excel


def _parse_quantity(raw: str | None) -> int:
    if not raw or not raw.strip():
        return 1
    try:
        value = int(float(raw.strip().replace(",", ".")))
    except ValueError:
        return 1
    return value if value > 0 else 1


def _parse_price(raw: str | None) -> Decimal | None:
    if not raw or not raw.strip():
        return None
    cleaned = raw.strip().replace("€", "").replace(" ", "").replace(",", ".")
    try:
        price = Decimal(cleaned)
    except InvalidOperation:
        return None
    return price if price >= 0 else None


def _parse_date(raw: str | None) -> date | None:
    if not raw or not raw.strip():
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_variant(raw: str | None) -> str:
    if not raw:
        return "normal"
    return _VARIANT_ALIASES.get(_normalize(raw), "normal")


def parse_csv(data: bytes, *, max_rows: int) -> ParsedImportResult:
    text = _decode(data)
    sample = text[:4096]
    dialect = _sniff_dialect(sample)
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if reader.fieldnames is None:
        raise ImportFileEmptyError

    field_by_column: dict[str, str] = {}
    for raw_header in reader.fieldnames:
        canonical = _HEADER_ALIASES.get(_normalize(raw_header))
        if canonical:
            field_by_column[raw_header] = canonical

    rows: list[ParsedImportRow] = []
    ignored: list[tuple[int, str]] = []
    line_number = 1  # ligne 1 = en-tête, les données commencent à 2

    for raw_row in reader:
        line_number += 1
        if line_number - 1 > max_rows:
            raise ImportTooManyRowsError

        if not any((value or "").strip() for value in raw_row.values()):
            continue  # ligne entièrement vide (fin de fichier, ligne blanche) — pas une erreur

        values: dict[str, str | None] = {}
        for raw_header, value in raw_row.items():
            canonical = field_by_column.get(raw_header)
            if canonical and canonical not in values:
                values[canonical] = value

        name = (values.get("name") or "").strip() or None
        number = (values.get("number") or "").strip() or None
        if name is None and number is None:
            ignored.append((line_number, "ni nom ni numéro reconnu sur cette ligne"))
            continue

        rows.append(
            ParsedImportRow(
                line_number=line_number,
                name=name,
                number=number,
                set_code=(values.get("set_code") or "").strip() or None,
                language=(values.get("language") or "").strip().lower() or None,
                variant=_parse_variant(values.get("variant")),
                quantity=_parse_quantity(values.get("quantity")),
                condition_grade=(values.get("condition_grade") or "").strip() or None,
                purchase_price=_parse_price(values.get("purchase_price")),
                acquired_at=_parse_date(values.get("acquired_at")),
            )
        )

    if not rows and not ignored:
        raise ImportFileEmptyError

    return ParsedImportResult(rows=rows, ignored=ignored)
