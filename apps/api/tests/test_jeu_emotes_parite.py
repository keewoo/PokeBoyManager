"""Parité du catalogue d'emotes, et **interdiction du texte libre** dans l'interface de plateau.

Lot ``j-echanges-emotes``, décision DJ10. Deux gardes statiques, qui lisent le **point de vérité**
plutôt que d'en recopier une image — même motif que ``test_parite_raisons_fin_front.py`` et
``test_parite_journal_front.py`` côté moteur :

1. **parité du catalogue** : les dix emotes du serveur et celles de
   ``apps/web/src/lib/game/emotes.ts`` sont les mêmes, dans les deux sens. Le doublon côté écran est
   assumé (ouvrir la palette n'attend aucun réseau), mais il ne doit pas pouvoir dériver : un code
   présent d'un seul côté donnerait une emote que le serveur refuse, ou une emote reçue que l'écran
   n'affiche pas ;

2. **aucune saisie de texte libre dans l'interface de plateau** — le critère d'acceptation n° 1 du
   lot, et le risque nommé : *« ajouter juste un petit chat plus tard : ce serait un autre produit,
   avec une obligation de modération »*. Un champ de saisie ajouté au plateau n'est pas interdit par
   nature (le filtre de cartes d'une fenêtre de décision en est un, légitime : il filtre une liste
   locale, il ne parle à personne) — ce qui est interdit, c'est qu'il apparaisse **sans que personne
   le remarque**. Le test fige donc l'inventaire : un champ de plus fait rougir la CI, avec la
   phrase qui dit quoi vérifier.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from pbm_api.games.emotes import CATALOGUE

# apps/api/tests/ -> apps/api -> apps -> racine du dépôt.
_RACINE = Path(__file__).resolve().parents[3]
_EMOTES_TS = _RACINE / "apps" / "web" / "src" / "lib" / "game" / "emotes.ts"

#: L'interface de **plateau** : les composants de jeu et la page d'une partie en cours. Le replay
#: (``parties/[id]/replay/``) n'en fait pas partie : c'est un écran d'après-partie, où un champ
#: (le pseudo d'un invité à qui partager le replay) est légitime et ne parle pas à un adversaire.
_PLATEAU = (
    _RACINE / "apps" / "web" / "src" / "components" / "game",
    _RACINE / "apps" / "web" / "src" / "app" / "jeu" / "parties" / "[id]",
)

#: Les seuls champs de saisie tolérés dans l'interface de plateau, et **pourquoi**.
#:
#: Chaque entrée est ``(fichier, type d'input, raison)``. Une entrée en trop fait échouer le test :
#: c'est le but. Pour en ajouter une, il faut pouvoir écrire ici en une ligne pourquoi ce champ ne
#: transporte pas un message d'un joueur à l'autre.
_SAISIES_TOLEREES = {
    (
        "fenetre-decision.tsx",
        "search",
        "filtre les cartes d'une liste locale (choix d'une décision) — rien n'est transmis",
    ),
}


def _emotes_du_serveur() -> list[tuple[str, str, str]]:
    """Le catalogue du serveur, dans l'ordre : ``(code, phrase, pictogramme)``."""
    return [(e.code, e.phrase, e.pictogramme) for e in CATALOGUE]


def _emotes_du_front() -> list[tuple[str, str, str]]:
    """Les entrées du tableau ``EMOTES`` de ``emotes.ts``, dans l'ordre du source.

    Lire le source plutôt qu'exécuter du TypeScript garde ce test dans le job Python, comme les
    autres parités du dépôt. L'objet est en forme littérale constante : un relevé par expression
    régulière suffit, et il casse bruyamment si la forme change (zéro entrée trouvée).
    """
    source = _EMOTES_TS.read_text(encoding="utf-8")
    debut = source.index("export const EMOTES")
    fin = source.index("] as const;", debut)
    bloc = source[debut:fin]
    return re.findall(
        r'\{\s*code:\s*"([^"]+)",\s*phrase:\s*"([^"]*)",\s*pictogramme:\s*"([^"]*)"\s*\}',
        bloc,
    )


def test_le_front_porte_bien_le_catalogue() -> None:
    """Garde de lecture : la forme attendue est trouvée (sinon le relevé serait vide et muet)."""
    assert _EMOTES_TS.exists(), f"Catalogue front introuvable : {_EMOTES_TS}"
    assert len(_emotes_du_front()) == len(CATALOGUE) > 0, (
        "Le relevé du catalogue front n'a pas trouvé le bon nombre d'entrées : la forme de "
        f"`EMOTES` dans {_EMOTES_TS.name} a changé, et cette parité ne garde donc plus rien."
    )


def test_parite_catalogue_emotes() -> None:
    """Serveur et écran disent exactement la même chose — code, phrase et pictogramme.

    Dans les deux sens : un code que seul le serveur connaît arriverait sur un écran qui ne sait pas
    l'afficher ; un code que seul l'écran connaît partirait pour être refusé en « emote inconnue ».
    """
    assert _emotes_du_front() == _emotes_du_serveur(), (
        "Le catalogue d'emotes a dérivé entre apps/api/src/pbm_api/games/emotes.py et "
        "apps/web/src/lib/game/emotes.ts. Les deux listes doivent être identiques, dans le même "
        "ordre (l'ordre est celui de la palette)."
    )


# --- Aucune saisie de texte libre dans l'interface de plateau --------------------------------


def _fichiers_du_plateau() -> list[Path]:
    """Les sources TSX de l'interface de plateau, replay exclu (voir :data:`_PLATEAU`)."""
    fichiers: list[Path] = []
    for racine in _PLATEAU:
        for fichier in sorted(racine.rglob("*.tsx")):
            if "replay" in fichier.parts:
                continue
            fichiers.append(fichier)
    return fichiers


def _saisies_trouvees() -> set[tuple[str, str, str]]:
    """Relève les champs de saisie du plateau : ``(fichier, type, "")``.

    On cherche ``<input``, ``<textarea`` et ``contentEditable``. Le ``type`` d'un ``<input>`` est lu
    sur les lignes qui suivent la balise (JSX multi-lignes) ; absent, il vaut ``"text"`` — c'est le
    défaut HTML, et le cas le plus dangereux, donc jamais celui qu'on suppose innocent.
    """
    trouvees: set[tuple[str, str, str]] = set()
    for fichier in _fichiers_du_plateau():
        lignes = fichier.read_text(encoding="utf-8").splitlines()
        for i, ligne in enumerate(lignes):
            if "<textarea" in ligne:
                trouvees.add((fichier.name, "textarea", ""))
            if "contentEditable" in ligne:
                trouvees.add((fichier.name, "contentEditable", ""))
            if "<input" not in ligne:
                continue
            # Fenêtre de lecture : les attributs d'une balise JSX tiennent sur quelques lignes.
            fenetre = "\n".join(lignes[i : i + 12])
            attribut = re.search(r'type=\{?"([a-z]+)"\}?', fenetre)
            trouvees.add((fichier.name, attribut.group(1) if attribut else "text", ""))
    return trouvees


def test_aucun_champ_de_saisie_non_declare_dans_le_plateau() -> None:
    """Critère n° 1 : aucune saisie de texte libre dans l'interface de jeu.

    L'inventaire des champs est **figé** : un champ ajouté au plateau fait échouer ce test, avec la
    question à se poser. C'est la mécanisation du risque nommé du lot — « juste un petit chat »
    n'arrivera pas par inadvertance, parce qu'il faudra l'écrire ici.
    """
    tolerees = {(f, t) for f, t, _ in _SAISIES_TOLEREES}
    trouvees = {(f, t) for f, t, _ in _saisies_trouvees()}

    nouvelles = trouvees - tolerees
    assert not nouvelles, (
        f"Champ(s) de saisie non déclaré(s) dans l'interface de plateau : {sorted(nouvelles)}.\n"
        "DJ10 interdit le texte libre entre joueurs : les emotes sont une liste fermée de codes, "
        "et le serveur ne transporte rien d'autre. Si ce champ ne parle à personne (un filtre "
        "local, par exemple), ajoute-le à _SAISIES_TOLEREES dans ce fichier avec sa raison. S'il "
        "sert à envoyer du texte à l'adversaire, c'est un autre produit — il faut l'arbitrage de "
        "JF et une modération, pas un test modifié."
    )

    disparues = tolerees - trouvees
    assert not disparues, (
        f"Saisie(s) déclarée(s) mais absente(s) : {sorted(disparues)}. L'inventaire garde quelque "
        "chose qui n'existe plus — retire ces entrées de _SAISIES_TOLEREES."
    )


def test_le_moteur_ne_connait_pas_les_emotes() -> None:
    """Une emote n'est pas une règle du jeu : ``pbm_game`` ne doit pas en entendre parler.

    Le moteur reste pur et sans E/S (son test d'import le garde) ; ce test garde la frontière
    **fonctionnelle** : aucune mention d'emote dans le paquet moteur. Un jour où une emote
    déclencherait un effet de jeu, elle entrerait dans le journal — et la promesse « rien ne
    survit à la partie » tomberait sans que rien ne le dise.
    """
    import pbm_game

    moteur = Path(pbm_game.__file__).parent
    fautifs = [
        str(f.relative_to(moteur))
        for f in sorted(moteur.rglob("*.py"))
        if "emote" in f.read_text(encoding="utf-8").lower()
    ]
    assert not fautifs, (
        f"Le moteur mentionne les emotes ({fautifs}). Une emote n'est pas un coup : elle ne "
        "touche ni l'état, ni le journal, ni le rejeu — c'est ce qui permet de ne rien conserver "
        "au-delà de la partie."
    )


def test_le_module_de_regles_des_emotes_est_pur() -> None:
    """``pbm_api.games.emotes`` ne fait aucune E/S : relevé **statique** de ses imports.

    Le débit et le catalogue se testent par milliers de cas précisément parce qu'ils ne touchent ni
    base, ni réseau, ni horloge (c'est l'appelant qui fournit l'instant). Un import de SQLAlchemy ou
    de ``datetime`` ici serait le premier pas vers un test qui doit dormir pour passer.
    """
    source = (
        _RACINE / "apps" / "api" / "src" / "pbm_api" / "games" / "emotes.py"
    ).read_text(encoding="utf-8")
    modules: set[str] = set()
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            modules.add(noeud.module.split(".")[0])
    assert modules <= {"__future__", "collections", "dataclasses"}, (
        f"Le module de règles des emotes importe {sorted(modules)} : il doit rester pur "
        "(aucune base, aucun réseau, aucune horloge)."
    )
