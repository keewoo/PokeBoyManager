"""Parité journal : tout événement projetable a sa traduction française côté client.

Lot ``j-plateau-journal``. Le moteur ``pbm_game`` produit des événements ``{type, donnees}`` ; le
serveur ne diffuse au client que ceux déclarés dans :data:`PROJECTEURS` (un type sans projecteur est
refusé, jamais diffusé brut — voir ``pbm_game.sortie.evenements``). Le **journal de partie** côté
front (``apps/web/src/lib/game/journal.ts``) doit savoir traduire **chacun** de ces types : sinon le
joueur verrait un identifiant technique (``etat_checkup``) au lieu d'une phrase.

Ce test **lit le source TypeScript** et vérifie que chaque type projetable y a son traducteur.
C'est un test de *parité* (CLAUDE.md § « on corrige, on blinde les tests ») : il tourne dans le
job ``game`` de la CI et **casse** dès qu'un événement est ajouté au moteur sans sa traduction
front — « un test qui échoue sur un événement non traduit » plutôt qu'un identifiant brut servi au
joueur. Les deux langages ne pouvant pas partager de constante, la parité est gardée ici, au point
de vérité (le registre ``PROJECTEURS``).
"""

from __future__ import annotations

import re
from pathlib import Path

from pbm_game.sortie.evenements import PROJECTEURS

# Racine du dépôt depuis apps/game/tests/ → apps/game → apps → racine.
_RACINE = Path(__file__).resolve().parents[3]
_JOURNAL_TS = _RACINE / "apps" / "web" / "src" / "lib" / "game" / "journal.ts"


def _types_traduits_front() -> set[str]:
    """Les types d'événement déclarés dans le registre ``TRADUCTEURS`` de ``journal.ts``.

    On isole le bloc ``TRADUCTEURS`` puis on relève ses clés (``<type>: {``), avec ou sans
    guillemets. Lire le source plutôt que d'exécuter du TS garde le test dans le job Python pur.
    """
    source = _JOURNAL_TS.read_text(encoding="utf-8")
    debut = source.index("TRADUCTEURS")
    # Chaque clé de premier niveau du registre est écrite « <type>: { » en début de ligne indentée.
    cles = re.findall(r"^\s{2}[\"']?([a-z_]+)[\"']?:\s*\{", source[debut:], re.MULTILINE)
    return set(cles)


def test_tout_evenement_projetable_a_sa_traduction_front() -> None:
    """Chaque type de :data:`PROJECTEURS` a un traducteur dans ``journal.ts`` (aucun type brut)."""
    assert _JOURNAL_TS.exists(), f"Module journal front introuvable : {_JOURNAL_TS}"
    traduits = _types_traduits_front()
    manquants = set(PROJECTEURS) - traduits
    assert not manquants, (
        "Événements projetables sans traduction dans apps/web/src/lib/game/journal.ts : "
        f"{sorted(manquants)}. Ajoute leur traducteur au registre TRADUCTEURS, sinon le joueur "
        "verrait l'identifiant technique au lieu d'une phrase française."
    )
