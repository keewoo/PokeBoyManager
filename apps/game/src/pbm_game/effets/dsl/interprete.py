"""L'**interprète** du langage d'effets — exécute un script au-dessus de la pile d'effets.

Module **pur** (aucune E/S). :func:`executer_programme` déroule un
:class:`~pbm_game.effets.dsl.modele.Programme` : il paie d'abord le **coût** (de façon
**atomique** — tout ou rien), puis exécute les effets, en traitant les structures de contrôle
(``si``, ``repeter``, ``pile_ou_face``, ``choisir``) et en déléguant chaque feuille à
``primitives.py``. Il rend un :class:`ResultatProgramme` : le nouvel état, les événements, les
**verrous** posés, et deux drapeaux (dégâts annulés, coût payé).

**Le pont vers la pile d'effets** (critère « au-dessus de la pile ») : :func:`compiler_en_effet`
emballe un script en :class:`~pbm_game.effets.pile.EffetEnAttente` (type :data:`TYPE_EFFET_DSL`),
et :func:`resolveur_dsl` est le résolveur que l'on enregistre dans un
:class:`~pbm_game.effets.pile.RegistreEffets` (:func:`registre_dsl`). Un script devient alors un
effet comme un autre — journalisé avec sa source, résolu en LIFO, et un jour **suspendable** pour
une demande de décision (lot ``j-effets-choix``), puisque script et contexte sont sérialisables.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...rng import Rng
from ...state.modele import EtatPartie
from ..pile import EffetEnAttente, Evenement, RegistreEffets, SourceEffet
from ..verrous import Verrou
from .chargement import charger_programme
from .contexte import ContexteEffet
from .execution import Execution, StrategieChoix, strategie_canonique
from .modele import Condition, Instruction, Programme
from .primitives import EVT_DSL_PRIMITIVE, PRIMITIVES, restreindre
from .selection import CiblePokemon, candidats
from .vocabulaire import (
    COND_A_DEGATS,
    COND_A_ETAT,
    COND_RESULTAT_PILE,
    COND_ZONE_NON_VIDE,
    CTRL_REPETER,
    CTRL_SI,
    OP_CHOISIR,
    OP_PILE_OU_FACE,
)

#: Le type d'effet, dans un :class:`~pbm_game.effets.pile.RegistreEffets`, qui résout un script DSL.
TYPE_EFFET_DSL = "dsl"
#: Un coût n'a **pas pu être payé** : le programme n'a rien fait, et le dit (jamais un demi-effet).
EVT_COUT_IMPAYABLE = "dsl_cout_impayable"
#: Un ``choisir`` a retenu des cibles — tracé pour que le journal dise *ce qui* a été choisi.
EVT_DSL_CHOIX = "dsl_choix"
#: Un ``pile_ou_face`` a été lancé — porte le nombre de pièces et de faces obtenues.
EVT_DSL_PILE = "dsl_pile_ou_face"


@dataclass(frozen=True)
class ResultatProgramme:
    """Le résultat d'une exécution de script — tout ce que l'appelant doit pouvoir récupérer.

    * ``etat`` — l'état après le script (figé) ;
    * ``evenements`` — la trace, dans l'ordre ;
    * ``verrous`` — les :class:`~pbm_game.effets.verrous.Verrou` posés par un ``empecher`` (à
      intégrer au :class:`~pbm_game.effets.verrous.JeuDeVerrous` par l'appelant : l'état de partie
      ne les porte pas) ;
    * ``degats_annules`` — un ``annuler`` a-t-il levé le drapeau de prévention des dégâts ;
    * ``cout_paye`` — le coût a-t-il été payé (faux ⇒ le script n'a **rien** fait d'autre).
    """

    etat: EtatPartie
    evenements: tuple[Evenement, ...]
    verrous: tuple[Verrou, ...]
    degats_annules: bool
    cout_paye: bool


# --- Conditions --------------------------------------------------------------


def _evaluer(ex: Execution, cond: Condition) -> bool:
    """Évalue une condition — un prédicat **pur** sur l'état courant et le contexte."""
    if cond.type == COND_RESULTAT_PILE:
        return ex.dernier_pile == (cond.attendu or "face")
    if cond.type == COND_ZONE_NON_VIDE:
        return bool(candidats(ex.etat, cond.cible, ex.ctx)) if cond.cible else False
    if cond.type == COND_A_ETAT:
        cibles = candidats(ex.etat, cond.cible, ex.ctx) if cond.cible else []
        return any(
            isinstance(c, CiblePokemon) and cond.etat in _pokemon_etats(ex, c) for c in cibles
        )
    if cond.type == COND_A_DEGATS:
        cibles = candidats(ex.etat, cond.cible, ex.ctx) if cond.cible else []
        seuil_pv = (cond.minimum or 1) * 10  # minimum compté en marqueurs (1 = 10 PV)
        return any(
            isinstance(c, CiblePokemon) and _pokemon_degats(ex, c) >= seuil_pv for c in cibles
        )
    raise ValueError(f"Condition inconnue à l'évaluation : {cond.type!r}.")


def _pokemon_etats(ex: Execution, cible: CiblePokemon) -> frozenset:
    for j in ex.etat.joueurs:
        if j.id != cible.joueur:
            continue
        if j.actif is not None and j.actif.cartes[0].instance_id == cible.identite:
            return j.actif.etats_speciaux
        for p in j.banc:
            if p.cartes[0].instance_id == cible.identite:
                return p.etats_speciaux
    return frozenset()


def _pokemon_degats(ex: Execution, cible: CiblePokemon) -> int:
    for j in ex.etat.joueurs:
        if j.id != cible.joueur:
            continue
        if j.actif is not None and j.actif.cartes[0].instance_id == cible.identite:
            return j.actif.compteurs_degats
        for p in j.banc:
            if p.cartes[0].instance_id == cible.identite:
                return p.compteurs_degats
    return 0


# --- Structures de contrôle --------------------------------------------------


def _executer_si(ex: Execution, instr: Instruction) -> None:
    corps = instr.alors if _evaluer(ex, instr.condition) else instr.sinon
    for sous in corps:
        _executer(ex, sous)


def _executer_repeter(ex: Execution, instr: Instruction) -> None:
    if instr.nombre is not None:
        fois = instr.nombre
    else:  # « pour chaque … » — autant de fois qu'il y a de candidats dans la source
        fois = len(restreindre(ex, candidats(ex.etat, instr.source, ex.ctx), instr.source))
    for _ in range(fois):
        for sous in instr.alors:
            _executer(ex, sous)


def _executer_pile(ex: Execution, instr: Instruction) -> None:
    pieces = instr.nombre if instr.nombre is not None else 1
    faces = 0
    for i in range(pieces):
        resultat = ex.rng.pile_ou_face(
            f"dsl:pile:{ex.ctx.joueur}", f"{ex.ctx.source.libelle} pièce {i + 1}"
        )
        if resultat == "face":
            faces += 1
    ex.dernier_pile = "face" if faces > 0 else "pile"
    ex.evenements.append(Evenement(EVT_DSL_PILE, {"pieces": pieces, "faces": faces}))
    # « si c'est face » = la branche ``alors``, jouée une fois par face ; « sinon » une seule fois.
    if faces > 0:
        for _ in range(faces):
            for sous in instr.alors:
                _executer(ex, sous)
    else:
        for sous in instr.sinon:
            _executer(ex, sous)


def _executer_choisir(ex: Execution, instr: Instruction) -> None:
    cands = candidats(ex.etat, instr.cible, ex.ctx)
    combien = instr.nombre if instr.nombre is not None else 1
    if not cands:
        # Aucune option : on le dit, et le corps ne s'exécute pas (jamais un choix inventé).
        ex.evenements.append(
            Evenement(
                EVT_DSL_CHOIX,
                {"source": ex.ctx.source.en_json(), "demande": combien, "choisis": 0},
            )
        )
        return
    choix = ex.strategie(cands, combien, ex.ctx)
    ex.evenements.append(
        Evenement(
            EVT_DSL_CHOIX,
            {"source": ex.ctx.source.en_json(), "demande": combien, "choisis": len(choix)},
        )
    )
    # Le corps agit sur « les choisis » : on borne la sélection le temps du corps, puis on la rend.
    precedente = ex.selection
    ex.selection = tuple(choix)
    try:
        for sous in instr.alors:
            _executer(ex, sous)
    finally:
        ex.selection = precedente


def _executer(ex: Execution, instr: Instruction) -> None:
    """Exécute une instruction : structure de contrôle, ou primitive feuille."""
    ex.consommer()
    op = instr.op
    if op == CTRL_SI:
        return _executer_si(ex, instr)
    if op == CTRL_REPETER:
        return _executer_repeter(ex, instr)
    if op == OP_PILE_OU_FACE:
        return _executer_pile(ex, instr)
    if op == OP_CHOISIR:
        return _executer_choisir(ex, instr)
    PRIMITIVES[op](ex, instr)


# --- Coût (atomique) ---------------------------------------------------------


def _cout_payable(ex: Execution, cout: tuple[Instruction, ...]) -> bool:
    """Le coût peut-il être payé *en entier* ? — contrôle **sans** rien modifier ni tirer d'aléa.

    Un coût est typiquement « défaussez N cartes » : on vérifie qu'il y a assez de candidats. Le
    contrôle est volontairement conservateur (il ne simule pas les effets de bord), mais il garantit
    qu'on ne paie jamais un demi-coût — si le contrôle passe, l'exécution réelle qui suit aboutit.
    """
    for instr in cout:
        sel = instr.cible or instr.source
        if sel is None:
            continue
        besoin = sel.nombre or 1
        if len(candidats(ex.etat, sel, ex.ctx)) < besoin:
            return False
    return True


# --- Exécution d'un programme complet ----------------------------------------


def executer_programme(
    etat: EtatPartie,
    programme: Programme,
    ctx: ContexteEffet,
    rng: Rng,
    *,
    strategie: StrategieChoix = strategie_canonique,
) -> ResultatProgramme:
    """Exécute un script **chargé et validé**. Pur côté état ; seul ``rng`` est mutable (rejouable).

    Paie d'abord le coût (atomiquement : s'il est impayable, le script ne fait **rien** et le dit),
    puis déroule les effets. La stratégie de choix est **injectable** (défaut déterministe).
    """
    ex = Execution(etat=etat, ctx=ctx, rng=rng, strategie=strategie)
    if programme.cout:
        if not _cout_payable(ex, programme.cout):
            evt = Evenement(
                EVT_COUT_IMPAYABLE,
                {"source": ctx.source.en_json(), "raison": "coût non payable — effet non joué"},
            )
            return ResultatProgramme(etat, (evt,), (), False, False)
        for instr in programme.cout:
            _executer(ex, instr)
    for instr in programme.effets:
        _executer(ex, instr)
    return ResultatProgramme(
        etat=ex.etat,
        evenements=tuple(ex.evenements),
        verrous=tuple(ex.verrous),
        degats_annules=ex.degats_annules,
        cout_paye=True,
    )


# --- Pont vers la pile d'effets ----------------------------------------------


def _contexte_en_json(ctx: ContexteEffet) -> dict:
    """Le contexte en valeurs JSON natives (sans la source : elle vit sur l'EffetEnAttente)."""
    return {
        "joueur": ctx.joueur,
        "adversaire": ctx.adversaire,
        "acteur_actif": ctx.acteur_actif,
        "defenseur": ctx.defenseur,
        "metadonnees": ctx.metadonnees,
    }


def _contexte_depuis_json(source: SourceEffet, donnees: dict) -> ContexteEffet:
    return ContexteEffet(
        source=source,
        joueur=donnees["joueur"],
        adversaire=donnees["adversaire"],
        acteur_actif=donnees.get("acteur_actif"),
        defenseur=donnees.get("defenseur"),
        metadonnees=donnees.get("metadonnees", {}),
    )


def compiler_en_effet(
    programme: Programme,
    ctx: ContexteEffet,
    *,
    libelle: str,
    regle: str,
) -> EffetEnAttente:
    """Emballe un script + son contexte dans un :class:`~pbm_game.effets.pile.EffetEnAttente`.

    L'effet obtenu se résout par :func:`resolveur_dsl` (type :data:`TYPE_EFFET_DSL`) : il entre
    dans la pile comme n'importe quel effet, et son contenu est sérialisable (reprise après F5).
    """
    return EffetEnAttente(
        type_effet=TYPE_EFFET_DSL,
        source=ctx.source,
        regle=regle,
        libelle=libelle,
        params={"programme": programme.en_json(), "contexte": _contexte_en_json(ctx)},
    )


def resolveur_dsl(
    etat: EtatPartie, effet: EffetEnAttente, rng: Rng
) -> tuple[EtatPartie, list[Evenement], list[EffetEnAttente]]:
    """Résolveur de pile pour un effet DSL — charge le script, l'exécute, rend état et événements.

    Signature d'un :data:`~pbm_game.effets.pile.Resolveur`. Les **verrous** éventuels (``empecher``)
    sont tracés dans le journal (``EVT_VERROU_POSE``) mais ne passent pas par cette signature : un
    script qui pose un verrou doit être exécuté par :func:`executer_programme` (qui les rend),
    jusqu'à ce que le :class:`~pbm_game.effets.verrous.JeuDeVerrous` rejoigne l'état (hors lot).
    """
    programme = charger_programme(effet.params["programme"])
    ctx = _contexte_depuis_json(effet.source, effet.params["contexte"])
    resultat = executer_programme(etat, programme, ctx, rng)
    return resultat.etat, list(resultat.evenements), []


def registre_dsl() -> RegistreEffets:
    """Un :class:`~pbm_game.effets.pile.RegistreEffets` qui ne connaît **que** le type DSL.

    À fusionner avec le registre d'un lot de cartes : ``{**registre_dsl(), **autres}``.
    """
    return {TYPE_EFFET_DSL: resolveur_dsl}


def resolveur_dsl_demandes(etat, effet, rng, gestionnaire):
    """Résolveur DSL **sachant se suspendre** — la version du lot ``j-effets-choix``.

    Signature d'un :data:`~pbm_game.demandes.moteur.ResolveurDecision`, comme :func:`resolveur_dsl`,
    mais la stratégie injectée est :func:`~pbm_game.effets.dsl.execution.strategie_demande`,
    qui réclame chaque ``choisir`` au ``gestionnaire``. Si une décision est neuve, la stratégie lève
    ``SuspensionDemande`` ; l'exception **traverse** :func:`executer_programme` (dont le travail
    partiel est donc jeté, état et tirages) et remonte au moteur, qui fige la pile. À la
    reprise, le script est **re-déroulé** depuis le début : les ``choisir`` déjà répondus retombent
    sur leurs réponses, le prochain non répondu suspend à nouveau (demandes imbriquées comprises).

    ``destinataire`` vaut ``ctx.joueur`` (celui qui joue l'effet). Un effet qui doit faire choisir
    l'**adversaire** passera par un type d'effet dédié ou une extension de ``choisir`` (lots
    ``j-cartes-objets`` / ``j-cartes-supporters``) ; le mécanisme de demande, lui, gère déjà un
    destinataire quelconque — c'est prouvé par les tests du moteur de résolution.
    """
    from .execution import strategie_demande

    programme = charger_programme(effet.params["programme"])
    ctx = _contexte_depuis_json(effet.source, effet.params["contexte"])
    strategie = strategie_demande(gestionnaire, destinataire=ctx.joueur, regle=effet.regle)
    resultat = executer_programme(etat, programme, ctx, rng, strategie=strategie)
    return resultat.etat, list(resultat.evenements), []


__all__ = [
    "TYPE_EFFET_DSL",
    "EVT_COUT_IMPAYABLE",
    "EVT_DSL_PRIMITIVE",
    "EVT_DSL_CHOIX",
    "EVT_DSL_PILE",
    "ResultatProgramme",
    "ContexteEffet",
    "StrategieChoix",
    "strategie_canonique",
    "executer_programme",
    "compiler_en_effet",
    "resolveur_dsl",
    "resolveur_dsl_demandes",
    "registre_dsl",
]
