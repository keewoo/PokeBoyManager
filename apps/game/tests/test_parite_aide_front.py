"""Parité aide : tout refus du moteur a son explication en français simple côté client.

Lot ``j-plateau-aide``, **premier critère d'acceptation** : « chaque raison de refus produite
par le moteur a son explication en français simple ». Le moteur refuse un coup en citant une règle
du corpus (:func:`pbm_game.actions.modele.refus` l'exige, un refus muet lève). L'aide en jeu
(``apps/web/src/lib/game/aide.ts``) doit savoir traduire **chacune** de ces citations — sinon le
joueur lit « R-9.2 » et un message technique, et ne comprend pas ce qu'il doit faire.

Ce test lit les deux côtés et compare, sur le motif de ``test_parite_journal_front.py`` :

* côté **moteur**, il relève par analyse syntaxique (``ast``) la citation de chaque refus, dans
  tout ``pbm_game`` — une nouvelle famille d'actions qui refuse sans explication casse ce test ;
* côté **front**, il relève les clés du registre ``EXPLICATIONS`` et les règles enseignées par le
  parcours guidé (``guide.ts``) ;
* côté **corpus** (``docs/jeu/REGLES.md``), il relève les identifiants qui existent vraiment.

Et il vérifie les deux sens, parce qu'ils attrapent deux fautes différentes :

#. un refus **sans** explication → le joueur reste devant un refus qu'il ne comprend pas ;
#. une explication (ou une consigne du guide) qui cite un identifiant **absent du corpus** → c'est
   exactement le risque nommé par la fiche du lot : « écrire l'aide à partir du code plutôt que du
   corpus de règles — les deux divergent, et l'aide explique des règles qui ne sont pas celles
   appliquées ». Le corpus fait foi ; l'aide n'invente aucune règle.

Les deux langages ne pouvant pas partager de constante, la parité est gardée ici, côté Python pur
(job ``game`` de la CI, sans base ni service).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

# Racine du dépôt depuis apps/game/tests/ → apps/game → apps → racine.
_RACINE = Path(__file__).resolve().parents[3]
_MOTEUR = _RACINE / "apps" / "game" / "src" / "pbm_game"
_AIDE_TS = _RACINE / "apps" / "web" / "src" / "lib" / "game" / "aide.ts"
_GUIDE_TS = _RACINE / "apps" / "web" / "src" / "lib" / "game" / "guide.ts"
_CORPUS = _RACINE / "docs" / "jeu" / "REGLES.md"

#: Une citation du corpus : une règle (``R-9.2``) ou la section qui la contient (``R-5``).
_CITATION = re.compile(r"^R-\d+(\.\d+)?$")

#: Le module qui **définit** le vocabulaire du refus (``refus()``, ``Verdict``). Il construit un
#: ``Verdict(accepte=False, regle=regle, …)`` depuis son propre paramètre : la citation y est, par
#: construction, non littérale. Ce n'est pas un site de refus, c'est la fabrique — on l'écarte du
#: relevé, sinon le test se plaindrait éternellement de sa propre fonction d'aide.
_FABRIQUE_DU_REFUS = _MOTEUR / "actions" / "modele.py"


def _citations_des_refus() -> dict[str, set[str]]:
    """Les règles citées par les refus du moteur, et où elles sont citées.

    Analyse syntaxique plutôt que ``grep`` : un appel ``refus(...)`` écrit sur plusieurs lignes (le
    cas courant, les messages étant longs) échapperait à une expression régulière. On relève deux
    formes : ``refus(<regle>, <message>)`` et la construction directe d'un ``Verdict`` refusant.

    Rend ``{citation: {chemins relatifs}}``. Une citation **non littérale** (calculée à
    l'exécution) est signalée sous la clé conventionnelle ``"<non littéral>"`` : elle ne peut pas
    être vérifiée statiquement, et c'est au test de le dire plutôt que de l'ignorer en silence.
    """
    trouvees: dict[str, set[str]] = {}
    for chemin in sorted(_MOTEUR.rglob("*.py")):
        if chemin == _FABRIQUE_DU_REFUS:
            continue
        arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
        relatif = str(chemin.relative_to(_RACINE))
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            nom = _nom_appele(noeud.func)
            citation: str | None = None
            if nom == "refus":
                citation = _citation_de(noeud, position=0)
            elif nom == "Verdict" and _verdict_refuse(noeud):
                citation = _citation_de(noeud, position=None)
            if citation is None:
                continue
            trouvees.setdefault(citation, set()).add(relatif)
    return trouvees


def _nom_appele(func: ast.expr) -> str:
    """Le nom simple de la fonction appelée (``refus``, ``Verdict``), vide si indéterminable."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _verdict_refuse(appel: ast.Call) -> bool:
    """Vrai si ce ``Verdict(...)`` est un refus (``accepte=False``) plutôt qu'un accord."""
    for mot_cle in appel.keywords:
        if mot_cle.arg == "accepte" and isinstance(mot_cle.value, ast.Constant):
            return mot_cle.value.value is False
    return False


def _citation_de(appel: ast.Call, *, position: int | None) -> str | None:
    """La citation portée par cet appel : argument positionnel donné, ou mot-clé ``regle``.

    Rend ``None`` quand l'appel ne porte aucune règle (``refus`` redéfini, signature partielle d'un
    module en cours d'écriture), et ``"<non littéral>"`` quand elle est calculée — un cas qu'on veut
    voir échouer bruyamment plutôt que manquer.
    """
    candidat: ast.expr | None = None
    if position is not None and len(appel.args) > position:
        candidat = appel.args[position]
    for mot_cle in appel.keywords:
        if mot_cle.arg == "regle":
            candidat = mot_cle.value
    if candidat is None:
        return None
    if isinstance(candidat, ast.Constant) and isinstance(candidat.value, str):
        return candidat.value
    return "<non littéral>"


def _bloc_registre(source: str, nom: str) -> str:
    """Le texte du source TypeScript à partir de la déclaration ``nom``, pour y relever ses clés."""
    return source[source.index(nom) :]


def _regles_expliquees() -> set[str]:
    """Les clés du registre ``EXPLICATIONS`` de ``aide.ts``.

    Un module absent est signalé comme tel : sans ce contrôle, le test échouerait sur une
    ``FileNotFoundError`` nue, et on chercherait un bug de parité là où il manque un fichier.
    """
    assert _AIDE_TS.exists(), f"Module d'aide front introuvable : {_AIDE_TS}"
    bloc = _bloc_registre(_AIDE_TS.read_text(encoding="utf-8"), "EXPLICATIONS: Record")
    # Chaque entrée est écrite « "R-x.y": { » en début de ligne indentée de deux espaces.
    return set(re.findall(r'^\s{2}"(R-\d+(?:\.\d+)?)":\s*\{', bloc, re.MULTILINE))


def _regles_du_guide() -> set[str]:
    """Les règles enseignées par les étapes du parcours guidé (``guide.ts``)."""
    assert _GUIDE_TS.exists(), f"Module de parcours guidé introuvable : {_GUIDE_TS}"
    bloc = _bloc_registre(_GUIDE_TS.read_text(encoding="utf-8"), "ETAPES_GUIDE")
    return set(re.findall(r'^\s{4}regle:\s*"(R-\d+(?:\.\d+)?)"', bloc, re.MULTILINE))


def _identifiants_du_corpus() -> set[str]:
    """Les identifiants qui existent dans ``docs/jeu/REGLES.md`` : règles **et** sections.

    Une règle est une puce ``- **R-x.y** — …`` ; une section un titre ``## … (R-x)``. Les deux sont
    citables par un refus du moteur, donc les deux comptent comme existants.
    """
    source = _CORPUS.read_text(encoding="utf-8")
    regles = set(re.findall(r"^- \*\*(R-\d+\.\d+)\*\*", source, re.MULTILINE))
    sections = set(re.findall(r"^## .*\((R-\d+)\)\s*$", source, re.MULTILINE))
    return regles | sections


def test_toute_citation_de_refus_est_un_identifiant_du_corpus() -> None:
    """Un refus cite un identifiant qui existe vraiment (R-1.3 : le corpus fait foi)."""
    corpus = _identifiants_du_corpus()
    citations = _citations_des_refus()
    assert citations, "Aucun refus trouvé dans pbm_game : le relevé syntaxique est cassé."

    mal_formees = {c: sorted(f) for c, f in citations.items() if not _CITATION.match(c)}
    assert not mal_formees, (
        "Refus dont la règle citée n'a pas la forme R-x.y (ou R-x) : "
        f"{mal_formees}. Un refus doit nommer un identifiant du corpus, pas une valeur calculée : "
        "sans cela l'aide en jeu ne peut pas l'expliquer au joueur."
    )

    inconnues = {c: sorted(f) for c, f in citations.items() if c not in corpus}
    assert not inconnues, (
        f"Refus citant un identifiant absent de {_CORPUS.relative_to(_RACINE)} : {inconnues}. "
        "Ajoute la règle au corpus (il fait foi) ou corrige la citation."
    )


def test_tout_refus_du_moteur_a_son_explication_cote_joueur() -> None:
    """Chaque règle citable dans un refus a son explication dans ``aide.ts`` (1ᵉʳ critère)."""
    expliquees = _regles_expliquees()
    assert expliquees, "Registre EXPLICATIONS vide ou illisible dans aide.ts."

    citations = _citations_des_refus()
    manquantes = {c: sorted(f) for c, f in citations.items() if c not in expliquees}
    assert not manquantes, (
        "Règles refusées par le moteur et SANS explication dans "
        f"apps/web/src/lib/game/aide.ts : {manquantes}. Ajoute leur entrée au registre "
        "EXPLICATIONS (titre, explication, alternative), écrite depuis docs/jeu/REGLES.md — sinon "
        "le joueur reçoit un refus qu'il ne comprend pas."
    )


def test_l_aide_n_explique_aucune_regle_absente_du_corpus() -> None:
    """L'aide ne cite que des identifiants du corpus — jamais une règle lue dans le code.

    C'est le risque nommé par la fiche du lot : une aide écrite d'après le code finit par expliquer
    des règles qui ne sont pas celles appliquées. Le corpus est la seule source (R-1.1/R-1.3).
    """
    corpus = _identifiants_du_corpus()

    inventees = sorted(_regles_expliquees() - corpus)
    assert not inventees, (
        f"aide.ts explique des identifiants absents de {_CORPUS.relative_to(_RACINE)} : "
        f"{inventees}. L'aide se recopie du corpus, jamais du code."
    )

    hors_corpus = sorted(_regles_du_guide() - corpus)
    assert not hors_corpus, (
        f"guide.ts enseigne des identifiants absents de {_CORPUS.relative_to(_RACINE)} : "
        f"{hors_corpus}. Une consigne de parcours guidé cite une règle réelle."
    )


def test_le_parcours_guide_explique_les_regles_qu_il_enseigne() -> None:
    """Chaque règle citée par une étape du guide est aussi expliquée : le guide apprend la règle."""
    non_expliquees = sorted(_regles_du_guide() - _regles_expliquees())
    assert not non_expliquees, (
        f"Étapes du parcours guidé dont la règle n'est pas expliquée : {non_expliquees}. "
        "Le guide donne un ordre ET la règle derrière, sinon il fait obéir sans apprendre."
    )
