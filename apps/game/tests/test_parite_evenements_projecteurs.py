"""Parité émetteurs ↔ projecteurs : tout ``EVT_*`` du moteur est traité — lot
``fix-projection-evenements``.

Le défaut qui a bloqué la livraison des coups du joueur (``docs/LIVRAISON.md``, 03/10/2026) :
des événements que le moteur émet n'avaient **aucun projecteur** dans
:data:`~pbm_game.sortie.evenements.PROJECTEURS`. ``projeter_evenement``
les refusait (à raison — jamais de repli silencieux), donc ``POST /games/{id}/actions`` répondait
**500** et le canal temps réel ne diffusait rien. La CI de l'époque était verte parce que les tests
de partie complète passaient par ``appliquer_action`` / ``reprendre_partie``, **jamais** par le
point de sortie ``projeter``. Sept types manquaient côté mise en place / timer ; un huitième
(``cout_paye``) a été débusqué en jouant une partie entière par les routes HTTP
(``apps/api/tests/test_games_http_ws_partie_complete.py``).

Ce test ferme la faille **à la source**, et pour **tout le moteur**, pas seulement
``journal.modele`` : il relève par lecture statique du source **toutes** les constantes ``EVT_*``
du paquet ``pbm_game`` — l'ensemble des types qu'un ``Evenement`` peut porter — et vérifie que
chacune est **soit** projetée (dans ``PROJECTEURS``), **soit** nommément différée
(:data:`DIFFERES_SYSTEME_EFFETS`). Un futur événement ajouté sans projecteur ni mention explicite
casse donc **en CI** (job ``game``), plus jamais en PROD. Lire le source plutôt qu'importer tous les
sous-modules garde le test sans effet de bord — même choix que ``test_parite_journal_front``.
"""

from __future__ import annotations

import re
from pathlib import Path

from pbm_game.sortie.evenements import PROJECTEURS

#: Racine du paquet ``pbm_game`` depuis ``apps/game/tests/`` → ``apps/game`` → ``src/pbm_game``.
_PBM_GAME = Path(__file__).resolve().parents[1] / "src" / "pbm_game"

#: Événements du **système d'effets de carte** (DSL, demandes, choix, primitives) qui peuvent porter
#: des **identités cachées** — p. ex. une primitive ``piocher``/``chercher`` nomme la carte tirée,
#: cachée à l'adversaire. Leur projection n'est donc PAS publique : elle se fait **par
#: destinataire**, et c'est le lot des *effets de carte* qui la livrera, le jour où une carte au
#: script DSL entrera réellement en jeu. Aucune partie J1 ne les émet aujourd'hui (prouvé par
#: ``test_games_http_ws_partie_complete``). Ils sont listés ici **nommément** — pas ignorés en
#: silence : tant qu'ils n'ont pas de projecteur par destinataire, ``projeter_evenement`` les refuse
#: (500 bruyant plutôt que fuite), ce qui est le comportement voulu avant leur livraison.
DIFFERES_SYSTEME_EFFETS: frozenset[str] = frozenset()
# Depuis le lot ``j-effets-cablage-service``, les effets de carte au script DSL entrent réellement
# en jeu par les routes HTTP (prouvé par ``apps/api/tests/test_games_effets_cablage.py``) : les
# événements du système d'effets (``dsl_primitive``, ``dsl_choix``, ``demande_emise``/
# ``demande_repondue``/``demande_expiree``) ont désormais leur **projecteur par destinataire** dans
# ``PROJECTEURS`` (anti-fuite : un ``piocher`` ne livre que le nombre, une demande cache ses options
# à qui n'est pas le destinataire). Plus aucun différé : tout ``EVT_*`` est projeté.

#: Repère une déclaration de constante d'événement : ``EVT_XXX = "type"`` (ou guillemets simples).
_MOTIF_EVT = re.compile(r"^EVT_[A-Z0-9_]+ = [\"']([a-z0-9_]+)[\"']", re.MULTILINE)


def _types_evenement_du_moteur() -> set[str]:
    """Toutes les valeurs de constantes ``EVT_* = \"...\"`` déclarées dans le paquet ``pbm_game``.

    Par convention du dépôt, une constante de module nommée ``EVT_*`` **est** un type d'événement
    que le moteur peut émettre. On balaie tout le source du paquet (combat, effets, demandes,
    horloges, mise en place, journal…) : le défaut d'origine venait justement d'un type défini
    **hors** de ``journal.modele`` (``cout_paye`` dans ``combat/cout.py``).
    """
    types: set[str] = set()
    for fichier in _PBM_GAME.rglob("*.py"):
        types |= set(_MOTIF_EVT.findall(fichier.read_text(encoding="utf-8")))
    return types


def test_tout_evenement_du_moteur_est_projete_ou_differe_nommement() -> None:
    """Chaque ``EVT_*`` du moteur est projeté ou nommément différé (aucun ne peut faire 500 par
    omission)."""
    types = _types_evenement_du_moteur()
    assert types, "Aucune constante EVT_* trouvée dans pbm_game — test à revoir."

    sans_traitement = types - set(PROJECTEURS) - DIFFERES_SYSTEME_EFFETS
    assert not sans_traitement, (
        "Événements que le moteur peut produire sans projecteur ni mention explicite : "
        f"{sorted(sans_traitement)}. projeter_evenement les refuse (ValueError) et "
        "POST /games/{id}/actions répondrait 500. Déclarer leur projecteur dans "
        "pbm_game.sortie.evenements.PROJECTEURS (avec leur visibilité), ou — si le type "
        "appartient au système d'effets et porte des identités cachées — l'ajouter nommément à "
        "DIFFERES_SYSTEME_EFFETS en attendant sa projection par destinataire."
    )


def test_la_liste_des_differes_ne_fuit_pas_dans_les_projecteurs() -> None:
    """Un différé n'est jamais aussi dans ``PROJECTEURS`` (pas projeté « public » par mégarde),
    et la liste des différés ne garde aucun type disparu du moteur."""
    types = _types_evenement_du_moteur()
    double = DIFFERES_SYSTEME_EFFETS & set(PROJECTEURS)
    assert not double, (
        f"Types à la fois différés ET dans PROJECTEURS : {sorted(double)}. Un événement différé ne "
        "doit pas être projeté « public » tant que sa projection par destinataire n'existe pas."
    )
    orphelins = DIFFERES_SYSTEME_EFFETS - types
    assert not orphelins, (
        f"DIFFERES_SYSTEME_EFFETS cite des types absents du moteur : {sorted(orphelins)}. "
        "Retirer ces entrées périmées pour que la liste reste une photo fidèle du différé réel."
    )
