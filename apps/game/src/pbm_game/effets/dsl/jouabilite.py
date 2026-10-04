"""La **jouabilité** d'un script d'effet — un Objet est-il jouable *maintenant* ? (j-cartes-objets)

Module **pur** (aucune E/S). Il répond à une seule question, sans rien modifier : « si on jouait ce
script sur cet état, ferait-il au moins une chose ? ». C'est la règle qui rend vrai le critère
d'acceptation « un Objet sans cible valide n'est pas jouable, et la raison s'affiche » : le
générateur d'actions (:class:`~pbm_game.actions.familles_jeu.FamilleJouerObjet`) ne liste un Objet
que si :func:`programme_jouable` le déclare jouable, et le refus en cite la raison.

Ce n'est **pas** un demi-moteur : on ne simule pas le script (aucun tirage, aucune mutation, aucun
choix). On vérifie **statiquement** que le coût est payable et qu'au moins un effet a une cible. On
ignore donc l'issue des pile-ou-face et des ``si`` (qui dépend de l'aléa ou de l'état) : une carte
comme *Roller Skates* (« pile ou face ; si face, pioche 3 ») reste **jouable** même si la pièce
pourrait tomber sur pile — on regarde si une branche *pourrait* agir, pas si elle *va* agir.

C'est volontairement **conservateur dans le bon sens** : il vaut mieux proposer un Objet dont
l'effet pourrait tourner court (le journal dira alors « sans cible », jamais un silence) que de
masquer un Objet réellement jouable. Le seul cas qu'on **refuse** est celui où *aucune* branche ne
peut agir — l'appât sur un banc adverse vide en est l'exemple canonique de la fiche.
"""

from __future__ import annotations

from ...state.modele import EtatPartie, Joueur
from .contexte import ContexteEffet
from .interprete import cout_payable
from .modele import Instruction, Programme
from .selection import CiblePokemon, candidats
from .vocabulaire import (
    CTRL_REPETER,
    CTRL_SI,
    OP_ANNULER,
    OP_CHANGER_ACTIF,
    OP_CHOISIR,
    OP_EMPECHER,
    OP_MELANGER,
    OP_PILE_OU_FACE,
    OP_PIOCHER,
    ZONE_PIOCHE,
)


def _joueur(etat: EtatPartie, jid: str) -> Joueur | None:
    for j in etat.joueurs:
        if j.id == jid:
            return j
    return None


def _melange_non_vide(etat: EtatPartie, instr: Instruction, ctx: ContexteEffet) -> bool:
    """Un ``melanger`` peut-il agir ? — sa zone (pioche de ``moi`` par défaut) n'est pas vide."""
    if instr.cible is not None:
        jids = ctx.ids_proprietaire(instr.cible.proprietaire)
        zone = instr.cible.zone
    else:
        jids, zone = (ctx.joueur,), ZONE_PIOCHE
    for jid in jids:
        j = _joueur(etat, jid)
        if j is not None and getattr(j, zone, ()):
            return True
    return False


def _changement_actif_possible(etat: EtatPartie, cands: list[object]) -> bool:
    """Un ``changer_actif`` peut-il agir ? — un Pokémon de banc visé, et un Actif à échanger.

    C'est la porte de l'appât : banc adverse vide ⇒ aucune cible ⇒ **non jouable**, et la raison
    s'affiche (critère d'acceptation). Un joueur sans Actif relève de la promotion (R-8.7), pas de
    l'échange forcé (R-8.8) : on ne le propose pas non plus.
    """
    bancs = [c for c in cands if isinstance(c, CiblePokemon) and c.emplacement == "banc"]
    if not bancs:
        return False
    joueur = _joueur(etat, bancs[0].joueur)
    return joueur is not None and joueur.actif is not None


def _instruction_peut_agir(etat: EtatPartie, instr: Instruction, ctx: ContexteEffet) -> bool:
    """Cette instruction (feuille ou structure de contrôle) pourrait-elle agir sur cet état ?"""
    op = instr.op
    # Structures de contrôle : jouable si **une** branche pourrait agir — on ignore l'issue de
    # l'aléa (``pile_ou_face``) et de la condition (``si``), qu'on ne simule pas ici.
    if op in (CTRL_SI, OP_PILE_OU_FACE):
        return any(_instruction_peut_agir(etat, s, ctx) for s in (instr.alors + instr.sinon))
    if op == CTRL_REPETER:
        return any(_instruction_peut_agir(etat, s, ctx) for s in instr.alors)
    if op == OP_CHOISIR:
        # Le corps agit sur « les choisis » : jouable s'il y a au moins une option à proposer.
        return instr.cible is not None and bool(candidats(etat, instr.cible, ctx))
    # Primitives feuilles sans sélecteur de cible classique.
    if op == OP_PIOCHER:
        # « piochez » agit sur la pioche du joueur visé (``proprietaire`` de la cible, ``moi`` par
        # défaut) : un Supporter peut faire **repiocher l'adversaire** (lot j-cartes-supporters).
        jid = ctx.joueur
        if instr.cible is not None and instr.cible.proprietaire != "moi":
            jid = ctx.adversaire
        joueur = _joueur(etat, jid)
        return joueur is not None and len(joueur.pioche) > 0
    if op == OP_MELANGER:
        return _melange_non_vide(etat, instr, ctx)
    if op in (OP_ANNULER, OP_EMPECHER):
        return True  # agissent sans cible de carte (prévention de dégâts, verrou)
    # Primitives à sélecteur : jouable si le sélecteur (cible, ou source pour deplacer/attacher) a
    # au moins un candidat sur cet état.
    selecteur = instr.cible or instr.source
    if selecteur is None:
        return False
    cands = candidats(etat, selecteur, ctx)
    if op == OP_CHANGER_ACTIF:
        return _changement_actif_possible(etat, cands)
    return bool(cands)


def programme_jouable(
    etat: EtatPartie, programme: Programme, ctx: ContexteEffet
) -> tuple[bool, str]:
    """``(jouable, raison)`` : ce script ferait-il au moins une chose sur ``etat`` ? Pur.

    Jouable si (1) son coût est **payable** (défausser 2 cartes quand il n'y en a qu'une : non
    jouable) et (2) **au moins un** de ses effets pourrait agir. ``raison`` est vide quand c'est
    jouable, sinon elle **cite la règle** et explique — pour l'affichage d'un refus (jamais un refus
    muet). Appelée par le générateur d'actions avant de lister un Objet.
    """
    if programme.cout and not cout_payable(etat, programme.cout, ctx):
        return False, "le coût de cet Objet ne peut pas être payé (R-5.5)"
    if any(_instruction_peut_agir(etat, instr, ctx) for instr in programme.effets):
        return True, ""
    return False, "cet Objet n'a aucune cible valide : son effet ne ferait rien (R-5.5)"


__all__ = ["programme_jouable"]
