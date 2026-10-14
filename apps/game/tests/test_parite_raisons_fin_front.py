"""Parité des raisons de fin : chacune a son libellé français côté écran.

Lot ``j-partie-fin-ui``, critère d'acceptation n° 1 : « chaque raison de fin possible a son libellé
propre ». Le moteur en définit **huit** — sept constantes ``RAISON_*`` dans
``pbm_game.journal.modele``, plus ``RAISON_EGALITE`` dans ``pbm_game.state.modele``. Et c'est
précisément la huitième qu'on oublie : au moment d'écrire ce lot, ``journal.ts`` en connaissait
sept, l'égalité tombant sur le repli « affiche le code brut » — un joueur à qui l'écran dit
« egalite » n'a pas reçu une explication, il a reçu un identifiant.

Ce test **lit le source TypeScript** et vérifie la parité dans les deux sens : aucune raison du
moteur sans libellé (sinon un code brut à l'écran), et aucun libellé sans raison correspondante
(sinon du texte mort qu'on croirait utilisé). Même motif que
``test_parite_journal_front.py`` : les deux langages ne partagent pas de constante, donc la parité
est gardée ici, au point de vérité.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pbm_game

# apps/game/tests/ -> apps/game -> apps -> racine du dépôt.
_RACINE = Path(__file__).resolve().parents[3]
_FIN_TS = _RACINE / "apps" / "web" / "src" / "lib" / "game" / "fin.ts"
_PBM_GAME = Path(pbm_game.__file__).parent


def _raisons_du_moteur() -> set[str]:
    """Toutes les constantes ``RAISON_* = "..."`` du paquet moteur, **où qu'elles vivent**.

    Relevé **statique** sur tout ``pbm_game`` plutôt qu'une liste de modules à tenir à jour : une
    raison ajoutée demain dans un fichier auquel ce test ne pense pas entre quand même dans la
    parité. C'est le même choix que les autres tests de parité du dépôt — lire le point de vérité,
    ne pas en recopier une image.
    """
    raisons: set[str] = set()
    for fichier in sorted(_PBM_GAME.rglob("*.py")):
        arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Assign) or not isinstance(noeud.value, ast.Constant):
                continue
            if not isinstance(noeud.value.value, str):
                continue
            for cible in noeud.targets:
                if isinstance(cible, ast.Name) and cible.id.startswith("RAISON_"):
                    raisons.add(noeud.value.value)
    return raisons


def _raisons_du_front() -> set[str]:
    """Les clés du registre ``RAISONS_FIN`` de ``fin.ts``.

    On isole le bloc du registre puis on relève ses clés de premier niveau (``<code>: {``), avec ou
    sans guillemets. Lire le source plutôt qu'exécuter du TypeScript garde le test dans le job
    Python pur, comme la parité du journal.
    """
    source = _FIN_TS.read_text(encoding="utf-8")
    debut = source.index("RAISONS_FIN: Record<string, LibellesRaison>")
    return set(re.findall(r"^\s{2}[\"']?([a-z_]+)[\"']?:\s*\{", source[debut:], re.MULTILINE))


def test_huit_raisons_de_fin_cote_moteur() -> None:
    """Le moteur définit bien huit raisons : si ce chiffre bouge, le lot doit en être informé.

    Garde-fou de lecture : ce test n'interdit pas d'en ajouter une, il oblige à passer ici (et donc
    par ``fin.ts``) quand on le fait.
    """
    raisons = _raisons_du_moteur()
    assert raisons == {
        "abandon",
        "derniere_recompense",
        "desertion",
        "egalite",
        "inactivite",
        "pioche_impossible",
        "plus_de_pokemon",
        "temps_ecoule",
    }, f"Raisons de fin du moteur inattendues : {sorted(raisons)}"


def test_toute_raison_de_fin_a_son_libelle_front() -> None:
    """Chaque raison du moteur a son entrée dans ``RAISONS_FIN`` (jamais un code brut à l'écran)."""
    assert _FIN_TS.exists(), f"Module de fin front introuvable : {_FIN_TS}"
    manquantes = _raisons_du_moteur() - _raisons_du_front()
    assert not manquantes, (
        "Raisons de fin sans libellé dans apps/web/src/lib/game/fin.ts : "
        f"{sorted(manquantes)}. Ajoute-les au registre RAISONS_FIN (nom court + une phrase par "
        "issue), sinon le joueur lirait l'identifiant technique au lieu d'une explication."
    )


def test_aucun_libelle_front_sans_raison_moteur() -> None:
    """Et l'inverse : un libellé sans raison correspondante est du texte mort, donc trompeur."""
    orphelins = _raisons_du_front() - _raisons_du_moteur()
    assert not orphelins, (
        "Libellés de fin sans raison correspondante dans le moteur : "
        f"{sorted(orphelins)}. Soit la raison a été retirée du moteur, soit la clé est mal "
        "orthographiée — dans les deux cas ce texte ne s'affichera jamais."
    )
