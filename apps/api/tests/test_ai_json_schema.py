"""Normalisation d'un schéma Pydantic pour la sortie structurée de chaque fournisseur
(`pbm_api.ai.json_schema`) — risque nommé par la mission `v3-ia-providers` (§4) : les formats
diffèrent d'un fournisseur à l'autre (Anthropic/OpenAI acceptent `$ref`, Gemini non)."""

from pydantic import BaseModel

from pbm_api.ai.json_schema import to_gemini_schema, to_strict_schema


class _Attack(BaseModel):
    name: str
    damage: int


class _CardExtraction(BaseModel):
    name: str
    number: str
    variant: str | None = None
    attacks: list[_Attack]


def test_to_strict_schema_resolves_refs_into_the_nested_object() -> None:
    schema = to_strict_schema(_CardExtraction)

    assert "$defs" not in schema
    attacks_items = schema["properties"]["attacks"]["items"]
    assert "$ref" not in attacks_items
    assert attacks_items["properties"]["damage"]["type"] == "integer"


def test_to_strict_schema_forbids_additional_properties_at_every_level() -> None:
    schema = to_strict_schema(_CardExtraction)

    assert schema["additionalProperties"] is False
    assert schema["properties"]["attacks"]["items"]["additionalProperties"] is False


def test_to_strict_schema_requires_every_property_including_optional_ones() -> None:
    """OpenAI en mode strict exige que `required` liste toutes les propriétés — un champ
    optionnel Pydantic (`variant: str | None = None`) reste `required`, sa nullité passant par
    le type (`anyOf` avec `null`), pas par son absence."""
    schema = to_strict_schema(_CardExtraction)

    assert set(schema["required"]) == {"name", "number", "variant", "attacks"}


def test_to_gemini_schema_has_no_ref_and_no_additional_properties() -> None:
    schema = to_gemini_schema(_CardExtraction)

    assert "$defs" not in schema
    assert "additionalProperties" not in schema
    assert "additionalProperties" not in schema["properties"]["attacks"]["items"]


def test_to_gemini_schema_converts_optional_field_to_nullable() -> None:
    schema = to_gemini_schema(_CardExtraction)

    variant_schema = schema["properties"]["variant"]
    assert variant_schema["nullable"] is True
    assert variant_schema["type"] == "string"
    assert "anyOf" not in variant_schema
