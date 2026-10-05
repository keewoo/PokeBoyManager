"""Les **gabarits de requête** envoyés à l'IA — proposer un script, puis le contredire.

Module **pur** (aucune E/S) : il ne fait que *construire des chaînes*. Il tient deux prompts, et la
**grammaire du langage** qu'ils citent est dérivée du vocabulaire fermé du moteur
(:mod:`pbm_game.effets.dsl.vocabulaire`) — jamais recopiée à la main, pour qu'elle ne puisse pas
dériver du langage réel (le même piège que la primitive « code libre » : une grammaire fausse dans
le prompt ferait proposer des scripts que le chargeur refusera tous).

Deux rôles, deux prompts :

* :func:`prompt_proposition` — « voici le texte d'une carte (FR et EN), voici le langage, voici des
  exemples validés proches : rends un script ET ses cas de test, ou dis que l'effet n'entre pas
  dans le langage ». Les contraintes de sortie sont **strictes** : du JSON, rien d'autre.
* :func:`prompt_contradiction` — la seconde IA (DJ8) : « voici un script et ses tests ; **cherche la
  faille** : un cas où il fait autre chose que ce que la carte dit. Par défaut, rejette si tu as un
  doute. » Son rôle est de contredire, pas d'approuver par politesse.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from pbm_game.effets.dsl.grammaire import EXEMPLES_AMORCE, SPEC_OPS
from pbm_game.effets.dsl.vocabulaire import (
    CATEGORIES,
    CONDITIONS,
    DSL_VERSION,
    POSITIONS,
    PROPRIETAIRES,
    ZONES,
)


@dataclass(frozen=True)
class ExempleValide:
    """Un script déjà validé proche du texte à traiter — ancre la proposition sur du réel.

    Donner au modèle des exemples réels (texte source + script accepté) vaut mieux qu'une grammaire
    seule : il calque une forme qui marche plutôt que d'en inventer une. On en passe quelques-uns,
    choisis proches (même famille, voir :mod:`.familles`).
    """

    source_text: str
    script: dict


def _ligne_spec(op: str) -> str:
    """Le schéma d'une instruction en une ligne : résumé, requis, optionnels, exemple, note.

    Rendu depuis :data:`pbm_game.effets.dsl.grammaire.SPEC_OPS` — les arguments requis y sont
    dérivés des constantes du chargeur (jamais recopiés). C'est ce détail *par primitive* qui
    manquait au premier passage : le modèle inventait ou oubliait des clés faute de le connaître.
    """
    spec = SPEC_OPS[op]
    requis = ", ".join(spec.requis) if spec.requis else "aucun"
    opt = ", ".join(spec.optionnels) if spec.optionnels else "aucun"
    ligne = (
        f"- {op} — {spec.resume}\n"
        f"    requis: {requis} ; optionnels: {opt}\n"
        f"    exemple: {json.dumps(spec.exemple, ensure_ascii=False)}"
    )
    if spec.note:
        ligne += f"\n    note: {spec.note}"
    return ligne


def grammaire_dsl() -> str:
    """Une description **complète** du langage, dérivée du moteur : le schéma *par primitive*.

    Pour **chaque** instruction (:data:`~pbm_game.effets.dsl.grammaire.SPEC_OPS`), le prompt cite
    ses arguments requis et facultatifs, un exemple valide et le piège à éviter (surtout l'unité
    d'un ``nombre`` : marqueurs vs PV). Tout est dérivé des constantes réelles du moteur — si le
    langage gagne ou change une primitive, le texte suit, et ``test_grammaire_dsl`` mord sinon.
    C'est la seule description du langage que le prompt cite : elle ne peut pas mentir au chargeur.
    """
    lignes = [
        f"Langage d'effets PokeBoy, version {DSL_VERSION}. Un script est un objet JSON :",
        '  {"version": <int>, "effets": [...], "cout": [...] (optionnel)}',
        "Une instruction est {\"op\": <op>, ...}.",
        "",
        "Un SÉLECTEUR (cible/source) décrit QUELLES cartes/Pokémon viser :",
        f"  zone ∈ {{{', '.join(sorted(ZONES))}}} (obligatoire)",
        f"  proprietaire ∈ {{{', '.join(sorted(PROPRIETAIRES))}}} (défaut moi)",
        f"  categorie ∈ {{{', '.join(sorted(CATEGORIES))}}} (optionnel)",
        "  stade ∈ {base, stade1, stade2} (optionnel)",
        f"  nombre (optionnel, sinon toutes) ; position ∈ {{{', '.join(sorted(POSITIONS))}}}",
        "",
        "Une CONDITION (pour un si) est {\"type\": <type>, ...} :",
        f"  type ∈ {{{', '.join(sorted(CONDITIONS))}}}",
        "  type_cible exige aussi cible (le Pokémon) et type_pokemon (le type attendu) ;",
        "  a_etat exige etat ; a_degats accepte minimum (en marqueurs) ;",
        "  resultat_pile accepte attendu (face|pile).",
        "",
        "=== LES INSTRUCTIONS (op), avec leur schéma exact ===",
        *[_ligne_spec(op) for op in sorted(SPEC_OPS)],
        "",
        "=== RÈGLES DURES ===",
        "- Aucune primitive « code libre » : un op hors de la liste ci-dessus est REFUSÉ.",
        "- Aucune clé hors du schéma d'une op : une clé inconnue est REFUSÉE (pas ignorée).",
        "- Les dégâts (infliger_degats) se comptent par multiples de 10 (PV).",
        "- soigner et poser_compteurs comptent en MARQUEURS (1 marqueur = 10 PV).",
        "- Un effet déplace des cartes entre zones, il n'en crée ni n'en détruit jamais.",
    ]
    return "\n".join(lignes)


_FORMAT_PROPOSITION = """\
Réponds UNIQUEMENT par un objet JSON (aucun texte autour), de la forme :
{
  "non_supporte": <bool>,          // true si l'effet n'entre pas dans le langage
  "raison": <string|null>,         // si non_supporte : quelle tournure manque (jamais vide)
  "confiance": "haute"|"moyenne"|"basse",
  "script": <objet script|null>,   // null si non_supporte
  "essais": [                      // au moins 1 si script ; chacun PROUVE un comportement
    {
      "nom": <string>,
      "etat": { ... état de départ concis ... },
      "contexte": { "joueur": "alice", "adversaire": "bob", "acteur_actif": <id|null>,
                    "defenseur": <id|null>, "metadonnees": { } },
      "tirages": [ { "flux": <string>, "resultat": "face"|"pile" } ],
      "attendu": { "etat": { ... } }
    }
  ]
}
Format d'un état (concis) : chaque joueur (alice, bob) porte actif/banc (Pokémon : {pv, recompenses,
degats (en PV), energies, etats, cartes}) et des zones comptées (pioche, main, defausse,
recompenses, zone_perdue = entiers). L'attendu.etat ne vérifie QUE les champs qu'il nomme
(assertions partielles) après l'effet. Le contexte et les tirages sont facultatifs (contexte par
défaut : joueur=alice, adversaire=bob ; un pile_ou_face doit lister son tirage, flux
« dsl:pile:alice »). Si l'effet n'entre PAS dans le langage, mets non_supporte=true et explique :
ne force JAMAIS un script approximatif."""


def _exemple_complet_texte() -> str:
    """Un exemple **complet et prouvé** (texte → script → essais qui passent), pour le prompt.

    Montre le format exact d'un essai qui *passe* la porte — c'est ce que le modèle imitait mal au
    premier passage (ses cas de test ne collaient pas à l'état du moteur). On en montre deux, pris
    de :data:`~pbm_game.effets.dsl.grammaire.EXEMPLES_AMORCE` (dont le soin, qui illustre le piège
    des marqueurs), parce qu'ils sont vérifiés en CI : impossible qu'ils dérivent du moteur réel.
    """
    lignes: list[str] = []
    for ex in EXEMPLES_AMORCE[:2]:
        lignes.append(f"Texte : {ex['source_text']}")
        lignes.append(f"script : {json.dumps(ex['script'], ensure_ascii=False)}")
        lignes.append(f"essais : {json.dumps(ex['essais'], ensure_ascii=False)}")
        lignes.append("")
    return "\n".join(lignes).rstrip()


def prompt_proposition(
    *, texte_fr: str, texte_en: str | None, exemples: Sequence[ExempleValide]
) -> str:
    """Le prompt du **proposeur** : texte (FR+EN), langage, exemples proches, format strict.

    L'IA rend un script ET ses cas de test, ou déclare l'effet non supporté (D9). Les exemples
    validés proches sont inclus tels quels (texte source + script accepté) pour ancrer la forme.
    """
    blocs = [
        "Tu écris le script d'effet d'une carte Pokémon dans un langage fermé. Tu rends AUSSI",
        "les cas de test qui prouvent ton script. Si l'effet ne s'exprime pas dans le langage,",
        "tu le dis (mieux vaut « je ne sais pas jouer cette carte » qu'un script faux).",
        "",
        "=== LANGAGE ===",
        grammaire_dsl(),
        "",
        "=== EXEMPLE COMPLET (script + essais qui PASSENT la vérification) ===",
        _exemple_complet_texte(),
    ]
    if exemples:
        blocs += ["", "=== EXEMPLES VALIDÉS PROCHES ==="]
        for ex in exemples:
            blocs.append(f"Texte : {ex.source_text}")
            blocs.append(f"Script : {json.dumps(ex.script, ensure_ascii=False)}")
    blocs += [
        "",
        "=== CARTE À TRAITER ===",
        f"Texte (FR) : {texte_fr}",
    ]
    if texte_en:
        blocs.append(f"Texte (EN) : {texte_en}")
    blocs += ["", "=== FORMAT DE RÉPONSE ===", _FORMAT_PROPOSITION]
    return "\n".join(blocs)


_FORMAT_VERDICT = """\
Réponds UNIQUEMENT par un objet JSON :
{
  "verdict": "approuve"|"rejete",
  "raison": <string>,              // pourquoi (jamais vide)
  "essai_contre": <objet essai|null> // un cas qui met le script en défaut, si tu en vois un
}
Par défaut, REJETTE au moindre doute : un script faux fait perdre des parties en silence."""


def prompt_contradiction(*, texte_fr: str, script: dict, essais: Sequence[dict]) -> str:
    """Le prompt du **contradicteur** (DJ8) : chercher la faille, rejeter au moindre doute.

    La seconde IA ne relit pas pour approuver : elle cherche un cas où le script ferait autre chose
    que ce que la carte dit, et le fournit (``essai_contre``) si elle le trouve. Le script n'entre
    en jeu que si elle **approuve** (en plus des tests verts) — jamais sur sa seule confiance.
    """
    blocs = [
        "Tu es l'avocat du diable. On te donne le texte d'une carte, un script censé l'exprimer,",
        "et ses cas de test. Ta mission : CONTREDIRE. Trouve un cas où le script fait autre chose",
        "que ce que la carte dit (mauvaise cible, mauvais nombre, condition oubliée, effet de",
        "bord). Si tu en trouves un, rejette et donne ce cas. Dans le doute, rejette.",
        "",
        "=== LANGAGE ===",
        grammaire_dsl(),
        "",
        "=== CARTE ===",
        f"Texte (FR) : {texte_fr}",
        "",
        "=== SCRIPT PROPOSÉ ===",
        json.dumps(script, ensure_ascii=False),
        "",
        "=== CAS DE TEST PROPOSÉS ===",
        json.dumps(list(essais), ensure_ascii=False),
        "",
        "=== FORMAT DE RÉPONSE ===",
        _FORMAT_VERDICT,
    ]
    return "\n".join(blocs)


__all__ = [
    "ExempleValide",
    "grammaire_dsl",
    "prompt_proposition",
    "prompt_contradiction",
]
