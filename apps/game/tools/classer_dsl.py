#!/usr/bin/env python3
"""Dépouille 500 textes d'effet réels et **classe chacun par primitive du langage**.

Outil d'**étude** (lot ``j-effets-dsl``), pas une pièce du moteur : il vit *hors* du paquet pur
``src/pbm_game`` (il lit un fichier). Il répond au critère d'acceptation n°1 — « le vocabulaire
couvre au moins 80 % des 500 textes dépouillés **sans primitive code libre** ».

Entrée : le JSON brut extrait du catalogue de référence (``apps/game/tools/extraire_effets_dsl.sql``
le produit) — une liste de ``{id, name, supertype, trainer_type, texte}`` où ``texte`` concatène
les effets de talents, d'attaques et de Dresseurs/Énergies d'une carte. Sortie : un JSON **gelé
et versionné** où chaque carte porte la liste des **primitives** que son texte réclame, et un
drapeau ``couvert`` (vrai dès qu'au moins une primitive du vocabulaire s'applique). Le test
``test_dsl_couverture`` relit cette sortie **sans** la base et **échoue** si la couverture tombe
sous 80 % — exactement la dent du critère.

Le vocabulaire est importé de ``pbm_game.effets.dsl.vocabulaire`` : **une seule** source de
vérité. Ajouter une primitive, c'est l'ajouter là, puis ajouter ici les tournures qui la
trahissent — jamais une liste de mots séparée qui dériverait.

**Ce que la mesure dit, et ne dit pas (honnêtement).** La couverture ici est détectée par
tournures : un texte est « couvert » dès qu'une de ses phrases se range sous une primitive du
vocabulaire. Elle prouve que le langage *a des mots* pour parler de 80 %+ des effets réels. Elle
ne prouve pas que chaque carte est scriptée fidèlement — ça, c'est le travail des lots de cartes
(D9), carte par carte, test par test. Les textes non couverts sont **listés** dans la sortie
(jamais avalés), pour que le trou soit visible et devienne du travail nommé.

Usage : ``uv run python apps/game/tools/classer_dsl.py <brut.json> <sortie.json>``
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

# L'outil tourne depuis apps/game ; on ajoute src au chemin pour importer le vocabulaire.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pbm_game.effets.dsl.vocabulaire import (  # noqa: E402
    CTRL_REPETER,
    CTRL_SI,
    OP_ANNULER,
    OP_ATTACHER,
    OP_CHANGER_ACTIF,
    OP_CHERCHER,
    OP_CHOISIR,
    OP_DEFAUSSER,
    OP_DEPLACER,
    OP_EMPECHER,
    OP_INFLIGER_DEGATS,
    OP_MELANGER,
    OP_PILE_OU_FACE,
    OP_PIOCHER,
    OP_POSER_COMPTEURS,
    OP_POSER_ETAT,
    OP_REGARDER,
    OP_RETIRER_ETAT,
    OP_REVELER,
    OP_SOIGNER,
    OPS,
)

VERSION_ECHANTILLON = 1
SEUIL_COUVERTURE = 0.80


def _norm(txt: str) -> str:
    """Minuscule, apostrophe droite et accents retirés — les mots-clés sont écrits en ASCII.

    Les textes du catalogue sont accentués (« énergie », « dégâts ») ; les mots-clés ci-dessous
    sont en ASCII pour rester lisibles. On déplie les deux au même alphabet avant comparaison,
    sinon « energie » ne retrouverait jamais « énergie » (même raison que classer_echantillon).
    """
    base = (txt or "").replace("’", "'").lower()
    decompose = unicodedata.normalize("NFKD", base)
    return "".join(c for c in decompose if not unicodedata.combining(c))


# Pour chaque primitive, les tournures qui la trahissent dans le texte d'une carte. L'ordre
# n'importe pas : un texte peut réclamer plusieurs primitives (on les collecte toutes).
_TOURNURES: dict[str, list[str]] = {
    OP_PIOCHER: [
        "piochez",
        "piochent",
        "pioche une carte",
        "piochez une carte",
        "piochez des",
        "jusqu'a ce que vous ayez",
        "draw a card",
        "draw ",
        "draw cards",
    ],
    OP_CHERCHER: [
        "cherchez dans votre deck",
        "cherchez dans votre pioche",
        "cherchez une",
        "cherchez un",
        "cherchez jusqu'a",
        "cherchez 1",
        "cherchez 2",
        "cherchez des",
        "search your deck",
    ],
    OP_DEFAUSSER: [
        "defaussez",
        "defausse",
        "mettez a la defausse",
        "defausser",
        "discard",
    ],
    OP_ATTACHER: [
        "attachez",
        "attachee a ce pokemon",
        "attacher",
        "attach it to",
        "attach a",
    ],
    OP_DEPLACER: [
        "deplacez",
        "deplacer",
        "deplace",
        "transferez",
        "deplacez une energie",
        "deplacez autant de",
        "move an energy",
        "move ",
        "sur le dessus de son deck",
    ],
    OP_SOIGNER: [
        "soignez",
        "soigne",
        "retirez tous les degats",
        "plus aucun degat",
        "retirez autant de",
        "retirez des degats",
        "retirez des compteurs",
        "retirez a 1 de vos pokemon",
        "retirez-en",
        "marqueurs de degat de",
        "marqueur de degat de",
        "retirez 1 marqueur",
        "retirez 2 marqueurs",
        "retirez 3 marqueurs",
        "heal",
    ],
    OP_POSER_COMPTEURS: [
        "placez des compteurs",
        "placez autant de compteurs",
        "placez 1 compteur",
        "compteurs de degats sur",
        "compteur de degats sur",
        "placez n compteurs",
        "placez un marqueur de degats",
        "placez 1 marqueur de degats",
        "placez 2 marqueurs de degats",
        "placez 3 marqueurs de degats",
        "placez 4 marqueurs de degats",
        "placez 5 marqueurs de degats",
        "placez des marqueurs de degats",
        "placez autant de marqueurs",
        "marqueur de degats sur",
        "marqueurs de degats sur",
        "damage counter",
    ],
    OP_INFLIGER_DEGATS: [
        "degats supplementaires",
        "inflige",
        "degats a",
        "degats a chacun",
        "degats a ce pokemon",
        "degats a 1 de",
        "degats a son",
        "degats de plus",
        "+ 10 degats",
        "+10 degats",
        "degats pour chaque",
        "more damage",
        "does 20 damage",
        "this attack does",
        "damage for each",
    ],
    OP_MELANGER: ["melangez", "melanger", "melange ensuite", "shuffle"],
    OP_REVELER: ["montrez", "montrez-la", "montrez-le", "revelez", "montrez-les", "reveal"],
    OP_REGARDER: ["regardez", "regardez les", "regardez la carte du dessus", "look at"],
    OP_CHOISIR: [
        "choisissez",
        "choisit",
        "choisir",
        "au choix",
        "de votre choix",
        "choose ",
    ],
    OP_PILE_OU_FACE: [
        "lancez une piece",
        "lancez 2 pieces",
        "lancez une piece pour",
        "si c'est face",
        "si c'est pile",
        "lancez autant de pieces",
        "pile ou face",
        "jusqu'a ce que vous obteniez pile",
        "pour chaque face",
        "flip a coin",
        "flip 2 coins",
        "flip 3 coins",
        "flip ",
        "for each heads",
    ],
    OP_CHANGER_ACTIF: [
        "changez votre pokemon actif",
        "changez le pokemon actif",
        "le nouveau pokemon actif",
        "echangez ce pokemon",
        "votre adversaire change",
        "nouveau pokemon actif de votre adversaire",
        "contre 1 de ses pokemon de banc",
        "echange son pokemon actif",
        "echange 1 de ses pokemon",
        "echange ce pokemon",
        "echange son pokemon actif contre",
        "switch ",
        "echange 1 de ses pokemon defenseurs",
    ],
    OP_POSER_ETAT: [
        "est maintenant empoisonne",
        "est maintenant endormi",
        "est maintenant confus",
        "est maintenant paralyse",
        "est maintenant brule",
        "est desormais empoisonne",
        "devient empoisonne",
        "est empoisonne",
        "est endormi",
        "est confus",
        "est paralyse",
        "est brule",
        "maintenant empoisonne et",
        "votre adversaire est",
        "sont maintenant confus",
        "is now asleep",
        "is now poisoned",
        "is now confused",
        "is now paralyzed",
        "is now burned",
    ],
    OP_RETIRER_ETAT: [
        "n'est plus empoisonne",
        "n'est plus endormi",
        "n'est plus confus",
        "n'est plus paralyse",
        "n'est plus brule",
        "retirez tous les etats speciaux",
        "plus affecte par aucun etat special",
        "guerir de tous les etats",
        "n'est plus affecte",
    ],
    OP_EMPECHER: [
        "ne peut pas attaquer",
        "ne peut pas utiliser d'attaque",
        "ne peut pas jouer de supporter",
        "ne peut pas battre en retraite",
        "ne peut pas se retirer",
        "ne peuvent pas attaquer",
        "ne peut pas utiliser d'objet",
        "ne peut pas jouer de carte",
        "ne peut pas evoluer",
        "pas de supporter",
        "ne pourra pas attaquer",
        "can't attack",
        "can't retreat",
        "n'a pas de cout de retraite",
        "cout de retraite est de 0",
        "cout de retraite de 0",
    ],
    OP_ANNULER: [
        "prevenez tous les degats",
        "prevenez ces degats",
        "prevenez les degats",
        "n'a aucun effet",
        "sont annules",
        "annulez",
        "aucun effet des attaques",
        "ignore l'effet",
        "cette attaque ne fait rien",
        "prevent all damage",
    ],
}

# Les structures de contrôle (elles ne « couvrent » pas à elles seules — un « si » sans
# primitive ne dit rien — mais on les relève pour montrer que le langage les exerce).
_TOURNURES_CTRL: dict[str, list[str]] = {
    CTRL_REPETER: ["pour chaque", "autant de fois", "fois que", "chaque carte energie"],
    CTRL_SI: ["si c'est face", "si c'est pile", "si votre adversaire", "si ce pokemon", "si le"],
}


def _primitives_du_texte(texte: str) -> list[str]:
    """Les primitives du vocabulaire que ce texte réclame (par tournure), triées, sans doublon."""
    t = _norm(texte)
    trouvees = {op for op, cles in _TOURNURES.items() if any(c in t for c in cles)}
    return sorted(trouvees)


def _controles_du_texte(texte: str) -> list[str]:
    t = _norm(texte)
    return sorted(c for c, cles in _TOURNURES_CTRL.items() if any(k in t for k in cles))


def _classer_carte(carte: dict) -> dict:
    texte = carte.get("texte") or ""
    primitives = _primitives_du_texte(texte)
    controles = _controles_du_texte(texte)
    couvert = bool(primitives)
    resultat = {
        "id": carte.get("id"),
        "name": carte.get("name"),
        "supertype": carte.get("supertype"),
        "trainer_type": carte.get("trainer_type"),
        "primitives": primitives,
        "controles": controles,
        "couvert": couvert,
    }
    # Un texte non couvert est TRACÉ (jamais avalé) : on garde un extrait pour nommer le trou.
    if not couvert:
        resultat["extrait"] = texte.strip()[:200]
    return resultat


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    brut = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    classees = [_classer_carte(c) for c in brut]
    n = len(classees)
    couvertes = [c for c in classees if c["couvert"]]
    non_couvertes = [c for c in classees if not c["couvert"]]
    taux = (len(couvertes) / n) if n else 0.0
    # Histogramme : combien de textes réclament chaque primitive (pour DSL.md et la revue).
    histogramme = {op: sum(1 for c in classees if op in c["primitives"]) for op in sorted(OPS)}
    sortie = {
        "version": VERSION_ECHANTILLON,
        "n": n,
        "couvertes": len(couvertes),
        "taux_couverture": round(taux, 4),
        "seuil": SEUIL_COUVERTURE,
        "histogramme_primitives": histogramme,
        "cartes": classees,
    }
    Path(sys.argv[2]).write_text(
        json.dumps(sortie, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"{n} textes classés — couverture {taux:.1%} (seuil {SEUIL_COUVERTURE:.0%})")
    print(f"Histogramme : {histogramme}")
    print(f"Non couverts : {len(non_couvertes)}")
    for c in non_couvertes[:25]:
        print(f"  - {c['name']} [{c['supertype']}]: {c.get('extrait', '')[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
