"""Le **fournisseur de génération** — l'aller-retour avec l'IA, et son double factice.

L'assistance appelle l'IA deux fois par effet : une fois pour **proposer** (script + cas de test),
une fois pour **contredire** (DJ8). Ce module isole cet aller-retour derrière une interface, pour
trois raisons :

* la clé est la **clé plateforme** (DJ8), jamais celle d'un utilisateur, et elle ne doit apparaître
  nulle part (ni journal, ni sortie) — l'implémentation réelle la garde en en-tête HTTP et ne la
  journalise jamais ;
* **sans clé**, DJ8 impose de livrer l'outillage, ses tests et une **mesure sur un fournisseur
  factice**, sans dépense : :class:`FournisseurFactice` est ce double déterministe ;
* la suite de tests n'a aucune clé IA (règle du dépôt) : elle injecte le double.

Les réponses sont du JSON strict (cf. :mod:`.gabarit`) ; ce module les **parse et valide** en
:class:`Proposition` / :class:`VerdictContradicteur`. Un JSON absent ou non conforme est une erreur
explicite, jamais une réponse inventée (règle du dépôt contre les replis silencieux).
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field, field_validator

_CONFIANCES = {"haute", "moyenne", "basse"}
_VERDICTS = {"approuve", "rejete"}
#: URL de l'API Messages (appel synchrone, pas la Message Batches API : pas de remise Batch).
_ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class Usage:
    """Jetons facturés d'un appel — la seule base de calcul du coût (jamais une estimation)."""

    input_tokens: int
    output_tokens: int


class Proposition(BaseModel):
    """La proposition de l'IA pour un texte d'effet : un script + ses cas de test, ou un refus.

    ``non_supporte`` dit que l'effet n'entre pas dans le langage (D9) : alors ``raison`` nomme la
    tournure manquante et ``script`` est nul. Sinon ``script`` porte le programme et ``essais`` les
    cas qui le prouvent (au moins un, exigé par la porte de vérification)."""

    non_supporte: bool = False
    raison: str | None = None
    confiance: str = "basse"
    script: dict | None = None
    essais: list[dict] = Field(default_factory=list)

    @field_validator("confiance")
    @classmethod
    def _confiance_connue(cls, v: str) -> str:
        if v not in _CONFIANCES:
            raise ValueError(f"confiance inconnue {v!r} (attendu : {sorted(_CONFIANCES)})")
        return v


class VerdictContradicteur(BaseModel):
    """Le verdict de la seconde IA (DJ8) : approuve ou rejette, avec sa raison et un contre-cas."""

    verdict: str
    raison: str = ""
    essai_contre: dict | None = None

    @field_validator("verdict")
    @classmethod
    def _verdict_connu(cls, v: str) -> str:
        if v not in _VERDICTS:
            raise ValueError(f"verdict inconnu {v!r} (attendu : {sorted(_VERDICTS)})")
        return v


class ReponseIllisibleError(RuntimeError):
    """La réponse de l'IA ne contient pas de JSON exploitable — jamais une réponse inventée."""


def _extraire_json(texte: str) -> dict:
    """Le premier objet JSON d'une réponse, même entourée de prose (le modèle déborde parfois).

    On tente d'abord la réponse entière ; à défaut, le premier bloc ``{...}`` équilibré. Lève
    :class:`ReponseIllisibleError` si rien n'est exploitable — on ne devine jamais un contenu."""
    texte = texte.strip()
    try:
        obj = json.loads(texte)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", texte, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    raise ReponseIllisibleError("aucun objet JSON exploitable dans la réponse de l'IA")


def parser_proposition(texte: str) -> Proposition:
    """Parse et valide une réponse de proposeur en :class:`Proposition` (lève si non conforme)."""
    return Proposition.model_validate(_extraire_json(texte))


def parser_verdict(texte: str) -> VerdictContradicteur:
    """Parse et valide une réponse de contradicteur en :class:`VerdictContradicteur`."""
    return VerdictContradicteur.model_validate(_extraire_json(texte))


class GenerateurScript(ABC):
    """L'aller-retour minimal avec l'IA : un prompt → un texte + l'usage facturé."""

    @abstractmethod
    async def generer(self, prompt: str) -> tuple[str, Usage]:
        """Rend la réponse brute de l'IA au prompt, et les jetons facturés."""

    async def aclose(self) -> None:  # noqa: B027 — défaut no-op volontaire (le factice n'a rien à fermer)
        """Libère les ressources (client HTTP) — sans effet par défaut."""


class FournisseurFactice(GenerateurScript):
    """Double **déterministe** sans réseau ni dépense — pour les tests et la mesure sans clé (DJ8).

    ``handler`` reçoit le prompt et rend la réponse brute (une chaîne JSON) ; ``usage`` est l'usage
    déclaré pour chaque appel (0 jeton par défaut = coût nul, le cas « clé absente » de DJ8). On
    garde la trace des prompts reçus (``prompts``) pour que les tests vérifient ce qui est demandé.
    """

    def __init__(
        self, handler: Callable[[str], str], *, usage: Usage | None = None
    ) -> None:
        self._handler = handler
        # Défaut 0 jeton = coût nul (le cas « clé absente » de DJ8) ; construit ici, pas en
        # valeur par défaut d'argument (un appel de fonction en défaut est partagé entre appels).
        self._usage = usage if usage is not None else Usage(0, 0)
        self.prompts: list[str] = []

    async def generer(self, prompt: str) -> tuple[str, Usage]:
        self.prompts.append(prompt)
        return self._handler(prompt), self._usage


class AnthropicGenerateur(GenerateurScript):
    """Appel réel à l'API Messages d'Anthropic avec la **clé plateforme** (DJ8).

    La clé voyage en en-tête ``x-api-key`` (jamais en URL, jamais journalisée) et n'est pas
    conservée en clair au-delà de cet objet. Un statut non-200 lève une erreur **sans** recopier le
    corps (qui pourrait refléter la requête) : on remonte le code, pas un repli silencieux.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        max_tokens: int = 4096,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("AnthropicGenerateur exige une clé plateforme non vide (DJ8).")
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._client = http_client or httpx.AsyncClient(timeout=_TIMEOUT_SECONDS)
        self._owns_client = http_client is None

    async def generer(self, prompt: str) -> tuple[str, Usage]:
        response = await self._client.post(
            _ANTHROPIC_MESSAGES_URL,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self._model,
                "max_tokens": self._max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Anthropic Messages a répondu {response.status_code} "
                "(clé plateforme : ni corps ni clé recopiés ici)."
            )
        data = response.json()
        blocs = data.get("content") or []
        texte = "".join(b.get("text", "") for b in blocs if b.get("type") == "text")
        usage_brut = data.get("usage") or {}
        usage = Usage(
            input_tokens=int(usage_brut.get("input_tokens", 0)),
            output_tokens=int(usage_brut.get("output_tokens", 0)),
        )
        return texte, usage

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


__all__ = [
    "Usage",
    "Proposition",
    "VerdictContradicteur",
    "ReponseIllisibleError",
    "parser_proposition",
    "parser_verdict",
    "GenerateurScript",
    "FournisseurFactice",
    "AnthropicGenerateur",
]
