"""Normalisation d'un schéma Pydantic pour la sortie structurée de chaque fournisseur.

Anthropic et OpenAI acceptent un JSON Schema « strict » classique (mais OpenAI exige
`additionalProperties: false` et `required` listant toutes les propriétés d'un objet, y
compris optionnelles — nullable via le type, pas via absence). Gemini n'accepte ni `$ref`/
`$defs` ni ces deux clés : `_to_gemini_schema` réduit un `Optional[X]` (`anyOf` avec un membre
`null`, forme émise par Pydantic) en `{"type": "X", "nullable": true}`.
"""

from typing import Any

from pydantic import BaseModel


def to_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema avec `$ref` repliés et `additionalProperties: false` partout — accepté par
    Anthropic (`output_config.format`) et OpenAI (`response_format` en mode strict)."""
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})
    resolved = _resolve_refs(raw, defs)
    _tighten(resolved)
    return resolved


def to_gemini_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Variante OpenAPI 3.0 restreinte pour `generationConfig.responseSchema`."""
    return _to_gemini(to_strict_schema(model))


def _resolve_refs(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if "$ref" in node:
            ref_name = node["$ref"].rsplit("/", 1)[-1]
            return _resolve_refs(defs[ref_name], defs)
        return {key: _resolve_refs(value, defs) for key, value in node.items()}
    if isinstance(node, list):
        return [_resolve_refs(item, defs) for item in node]
    return node


def _tighten(node: Any) -> None:
    if not isinstance(node, dict):
        return
    if node.get("type") == "object" and "properties" in node:
        node["additionalProperties"] = False
        node["required"] = list(node["properties"].keys())
    for value in node.values():
        if isinstance(value, dict):
            _tighten(value)
        elif isinstance(value, list):
            for item in value:
                _tighten(item)


def _to_gemini(node: Any) -> Any:
    if isinstance(node, dict):
        node = dict(node)
        node.pop("additionalProperties", None)
        any_of = node.get("anyOf")
        if isinstance(any_of, list) and any(branch.get("type") == "null" for branch in any_of):
            non_null = [branch for branch in any_of if branch.get("type") != "null"]
            if len(non_null) == 1:
                node.pop("anyOf")
                node.update(non_null[0])
                node["nullable"] = True
        return {key: _to_gemini(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_to_gemini(item) for item in node]
    return node
