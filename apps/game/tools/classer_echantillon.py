#!/usr/bin/env python3
"""Dépouille un échantillon de cartes et **classe le moment de chaque effet**.

Outil d'**étude** (lot ``j-effets-architecture``), pas une pièce du moteur : il vit *hors* du
paquet pur ``src/pbm_game`` (il lit un fichier). Il répond à la mission « définir la liste des
événements à partir des besoins réels relevés sur 200 cartes prises au hasard du catalogue ».

Entrée : le JSON brut extrait du catalogue de référence (``cards`` : ``id, name, supertype,
rule_marker, talents, attaques`` — les textes d'effet des talents et des attaques). Sortie : un
JSON **gelé et versionné** où chaque carte porte ses *mécanismes* et, pour les effets
déclenchés, le *moment* (:data:`~pbm_game.effets.evenements.EVENEMENTS_JEU`). Le test
``test_effets_echantillon`` relit cette sortie **sans** le catalogue : il prouve en CI que le
vocabulaire couvre l'échantillon, et **échoue** si une carte réclame un moment hors de la liste
(critère d'acceptation : « ou la liste est complétée et le test refait »).

Le vocabulaire est importé de ``pbm_game.effets.evenements`` : une seule source de vérité.

Usage : ``uv run python apps/game/tools/classer_echantillon.py <brut.json> <sortie.json>``
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

# L'outil tourne depuis apps/game ; on ajoute src au chemin pour importer le vocabulaire.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pbm_game.effets.evenements import (  # noqa: E402
    EJ_APRES_DEGATS,
    EJ_ATTACHEMENT_ENERGIE,
    EJ_AVANT_DEGATS,
    EJ_DEBUT_TOUR,
    EJ_DEVIENT_ACTIF,
    EJ_ENTRE_TOURS,
    EJ_EVOLUTION,
    EJ_FIN_TOUR,
    EJ_KO,
    EJ_PIOCHE,
    EJ_POSE,
    MECANISME_ACTIVE,
    MECANISME_ATTAQUE,
    MECANISME_CONTINU,
    MECANISME_DECLENCHE,
)

VERSION_ECHANTILLON = 1


def _norm(txt: str) -> str:
    """Minuscule, apostrophe droite et **accents retirés** — mots-clés écrits sans accent.

    Les textes du catalogue sont accentués (« énergie », « dégâts », « évolue ») ; les mots-clés
    ci-dessous sont écrits en ASCII pour rester lisibles et robustes. On déplie donc les deux au
    même alphabet avant comparaison, sinon « energie » ne retrouverait jamais « énergie ».
    """
    base = (txt or "").replace("’", "'").lower()
    decompose = unicodedata.normalize("NFKD", base)
    return "".join(c for c in decompose if not unicodedata.combining(c))


# --- Détection du MOMENT d'un effet déclenché (ordre : du plus spécifique au plus général) ---
# Chaque entrée : (moment, [mots-clés]). On s'arrête au premier moment dont un mot-clé apparaît.
_MOMENTS: list[tuple[str, list[str]]] = [
    (EJ_ENTRE_TOURS, ["entre les tours", "entre chaque tour", "pokemon checkup", "checkup"]),
    (EJ_DEVIENT_ACTIF, [
        "devient votre pokemon actif", "devient le pokemon actif", "devient actif",
        "placant ce pokemon comme pokemon actif", "ce pokemon devient votre nouveau pokemon actif",
    ]),
    (EJ_ATTACHEMENT_ENERGIE, [
        "lorsque vous attachez une energie", "chaque fois que vous attachez une energie",
        "quand vous attachez une energie", "attachez une carte energie",
        "attachez une energie", "energie est attachee a ce pokemon depuis votre main",
    ]),
    (EJ_POSE, [
        "jouez ce pokemon de votre main", "mis en jeu depuis votre main",
        "placez ce pokemon de base", "jouez ce pokemon de base de votre main",
        "entre en jeu", "jouez ce pokemon de votre main sur votre banc",
        "de votre main a votre banc", "de votre main sur votre banc",
    ]),
    (EJ_PIOCHE, [
        "lorsque vous piochez", "chaque fois que vous piochez", "quand vous piochez",
    ]),
    (EJ_KO, [
        "lorsque ce pokemon est mis k.o.", "quand ce pokemon est mis k.o.",
        "lorsque ce pokemon est k.o.", "si ce pokemon est mis k.o. par des degats",
        "lorsqu'un de vos pokemon est mis k.o.",
    ]),
    (EJ_DEBUT_TOUR, ["au debut de votre tour", "au debut de chaque tour", "debut de votre tour"]),
    (EJ_FIN_TOUR, ["a la fin de votre tour", "a la fin de chaque tour", "fin de votre tour"]),
    (EJ_APRES_DEGATS, [
        "subit des degats", "est blesse par une attaque", "chaque fois que ce pokemon est blesse",
        "apres les degats", "est blesse par les degats",
    ]),
    (EJ_AVANT_DEGATS, ["avant les degats", "chaque fois que ce pokemon est attaque par"]),
]

# Un effet d'évolution ne se déclenche QUE si le texte ne l'interdit pas (« ne peut évoluer »
# est un effet CONTINU, pas un déclencheur « lorsque ça évolue »).
_EVOLUE_DECLENCHE = [
    "lorsque ce pokemon evolue", "quand vous faites evoluer", "lorsqu'il evolue",
    "pour faire evoluer", "lorsque vous faites evoluer",
]

# Phrases qui marquent un effet ACTIVÉ par le joueur (une action, pas une réaction à un moment).
_ACTIVE = [
    "aussi souvent que vous le souhaitez", "une fois pendant votre tour",
    "deux fois pendant votre tour", "fois pendant votre tour", "une seule fois par tour",
    "pendant votre tour (avant votre attaque)", "pendant votre tour, vous pouvez",
    "pendant votre tour vous pouvez", "une fois par tour",
]

# Phrases/mots d'un effet CONTINU (consulté au calcul, pas déclenché).
_CONTINU = [
    "tant que", "chaque pokemon", "tous les pokemon", "les attaques de",
    "ne peut pas", "ne peuvent pas", "n'est pas affecte", "ne sont pas affectes",
    "n'a pas d'effet", "sans effet", "ignore", "reduits de", "reduites de",
    "degats supplementaires", "coute", "coutent", "aucune carte", "ne reçoit pas",
    "n'est jamais", "sont reduits", "chaque fois que",
]

# Marqueurs d'un DÉCLENCHEUR (un « lorsque/quand <moment> ») — hors contextes qui ne décrivent
# pas un moment de jeu (pile ou face, choix du joueur, activé « pendant votre tour »).
_MARQUEURS = ["lorsque", "lorsqu'", "quand ", "des que", "a chaque fois qu"]
_MARQUEURS_FAUX = [
    "lorsque c'est face", "lorsque c'est pile", "lorsque vous le souhaitez",
    "pendant votre tour", "lorsque vous jouez cette carte", "lorsque vous jouez cet",
]


def _classer_talent(type_talent: str, effet: str) -> dict:
    """Classe UN talent : son mécanisme, et pour un déclenché son moment. Audit dans ``motif``."""
    t = _norm(effet)
    typ = _norm(type_talent)

    # 1) Moment déclenché explicite.
    for moment, cles in _MOMENTS:
        if any(c in t for c in cles):
            return {
                "mecanisme": MECANISME_DECLENCHE, "evenement": moment, "motif": "moment-explicite",
            }
    if any(c in t for c in _EVOLUE_DECLENCHE):
        return {"mecanisme": MECANISME_DECLENCHE, "evenement": EJ_EVOLUTION, "motif": "evolue"}

    # 2) Activé par le joueur.
    if any(c in t for c in _ACTIVE):
        return {"mecanisme": MECANISME_ACTIVE, "evenement": None, "motif": "active-pendant-tour"}

    # 3) Continu — par type de talent (Poké-BODY, Trait Antique) ou par tournure.
    if typ in ("poke-body", "trait antique") or any(c in t for c in _CONTINU):
        return {"mecanisme": MECANISME_CONTINU, "evenement": None, "motif": "continu"}

    # 4) Un marqueur de déclencheur non mappé = on NE DEVINE PAS : on le signale (D9).
    faux = any(f in t for f in _MARQUEURS_FAUX)
    if not faux and any(m in t for m in _MARQUEURS):
        return {
            "mecanisme": MECANISME_DECLENCHE, "evenement": None,
            "motif": "DECLENCHEUR_NON_RECONNU", "extrait": effet[:140],
        }

    # 5) Défaut assumé et tracé : un talent sans marqueur de moment ni tournure continue est
    #    soit un Poké-POWER activé, soit un passif. On tranche par le type, et on l'ÉCRIT.
    if typ in ("poke-power", "pouvoir pokemon", "talent"):
        return {"mecanisme": MECANISME_ACTIVE, "evenement": None, "motif": "defaut-type-active"}
    return {"mecanisme": MECANISME_CONTINU, "evenement": None, "motif": "defaut-type-continu"}


def _classer_carte(carte: dict) -> dict:
    """Classe une carte : la liste de ses porteurs (talents + une entrée attaque si présente)."""
    porteurs: list[dict] = []
    talents = carte.get("talents") or ""
    for brut in [b for b in talents.split("|||") if b.strip()]:
        type_talent, _, effet = brut.partition("::")
        porteurs.append(_classer_talent(type_talent.strip(), effet.strip()))
    if (carte.get("attaques") or "").strip():
        # Les effets d'attaque se résolvent PENDANT l'attaque (entre avant/après dégâts) ; leurs
        # sous-effets (pile ou face, états infligés) relèvent du langage d'effets (j-effets-dsl).
        porteurs.append({"mecanisme": MECANISME_ATTAQUE, "evenement": None, "motif": "attaque"})

    evenements = sorted({p["evenement"] for p in porteurs if p["evenement"]})
    mecanismes = sorted({p["mecanisme"] for p in porteurs})
    non_reconnu = any(p["motif"] == "DECLENCHEUR_NON_RECONNU" for p in porteurs)
    return {
        "id": carte["id"],
        "name": carte["name"],
        "supertype": carte["supertype"],
        "rule_marker": carte.get("rule_marker"),
        "mecanismes": mecanismes,
        "evenements": evenements,
        "declencheur_non_reconnu": non_reconnu,
        "porteurs": porteurs,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    brut = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    classees = [_classer_carte(c) for c in brut]
    non_reconnus = [c for c in classees if c["declencheur_non_reconnu"]]
    tous_evenements = sorted({e for c in classees for e in c["evenements"]})
    sortie = {
        "version": VERSION_ECHANTILLON,
        "n": len(classees),
        "evenements_rencontres": tous_evenements,
        "declencheurs_non_reconnus": len(non_reconnus),
        "cartes": classees,
    }
    Path(sys.argv[2]).write_text(
        json.dumps(sortie, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"{len(classees)} cartes classées. Moments rencontrés : {tous_evenements}")
    print(f"Déclencheurs non reconnus : {len(non_reconnus)}")
    for c in non_reconnus[:20]:
        extraits = [
            p.get("extrait", "") for p in c["porteurs"]
            if p["motif"] == "DECLENCHEUR_NON_RECONNU"
        ]
        print(f"  - {c['name']}: {extraits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
