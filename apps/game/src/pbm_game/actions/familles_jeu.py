"""Familles de coups qui **ont besoin du catalogue** — le jeu devient jouable (``j-coups-joueur``).

Module **pur** (aucune E/S, ni HTTP, ni base, ni React), comme tout ``pbm_game``. Il complète le
cadre livré par :mod:`pbm_game.actions.generateur` (la :class:`Famille`, ``actions_legales`` et
``valider``) avec les familles qui demandent des **données de carte** : poser un Pokémon de base,
faire évoluer, attacher une énergie, déclarer une attaque, battre en retraite, promouvoir après un
K.O. Ces familles **ne vivent pas** dans :data:`~pbm_game.actions.generateur.FAMILLES_DEFAUT` (qui
reste le jeu de familles sans catalogue, celui que teste le générateur sur des milliers d'états) :
elles sont assemblées par :func:`familles_jeu`, que le service appelle avec le catalogue de la
partie.

**Une seule source de vérité : la liste.** Chaque famille **liste** les coups légaux depuis
l'état et
le catalogue ; la **transition** (déjà livrée : ``poser``, ``evoluer``, ``attacher_energie``,
``declarer_attaque``, ``retraite``, ``promouvoir``) les **applique** ; la **validation** de
:func:`pbm_game.actions.valider` vérifie l'appartenance d'un coup à la liste. Une famille ne réécrit
**jamais** une règle de transition — elle réutilise les gardes de tour
(:mod:`pbm_game.tour.contraintes`)
et le calcul de coût (:func:`pbm_game.combat.cout.cout_satisfait`), pour que la liste et
l'application
ne divergent pas (le piège nommé par la fiche du lot).

**Le catalogue, pas l'écran, décide.** :class:`CatalogueJeu` donne, pour une ``ref``, la
:class:`~pbm_game.cartes.modele.DefinitionCarte` (Pokémon) ou la
:class:`~pbm_game.cartes.energie.DefinitionEnergie` (énergie) — le service les extrait du
catalogue à
la création de la partie. Une carte dont la définition manque **ne produit aucun coup** (D9) : elle
n'est pas jouée de travers. Les ``params`` d'un coup portent la ``definition`` et les fiches PV, que
le journal transporte — le rejeu n'a donc pas besoin du catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..cartes.energie import DefinitionEnergie
from ..cartes.modele import DefinitionCarte, definition_vers_dict
from ..combat.cout import EnergieAttachee, cout_satisfait
from ..journal.modele import (
    ACTION_ATTACHER_ENERGIE,
    ACTION_DECLARER_ATTAQUE,
    ACTION_EVOLUER,
    ACTION_POSER,
    ACTION_PROMOUVOIR,
    ACTION_RETRAITE,
    Action,
)
from ..state.modele import (
    ENDORMI,
    PARALYSE,
    PHASE_ATTAQUE,
    PHASE_PRINCIPALE,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    carte_active,
)
from ..tour.contraintes import (
    attaque_permise,
    peut_attacher_energie,
    peut_battre_retraite,
    peut_evoluer,
)
from ..tour.drapeaux import identite_pokemon
from .generateur import Famille, FamilleAbandonner, FamilleAvancerPhase
from .modele import (
    GENRE_POKEMON_EN_JEU,
    ActionLegale,
    Cible,
    Verdict,
    refus,
)

# Zone de pose ordinaire (R-5.3) : au jalon J1, on ne pose un Pokémon de base qu'au banc (l'entrée
# directe en Actif est un cas d'effet, hors périmètre). Même constante que ``cartes.transitions``.
ZONE_BANC = "banc"


@dataclass(frozen=True)
class CatalogueJeu:
    """Les définitions de carte des deux decks d'une partie, par ``ref`` (fourni par le service).

    * ``pokemon`` — ``ref → DefinitionCarte`` pour les cartes Pokémon ;
    * ``energies`` — ``ref → DefinitionEnergie`` pour les cartes Énergie.

    Le moteur ne lit **jamais** la base : ce catalogue est extrait une fois, à la création de la
    partie, et passé aux familles. Une ``ref`` absente des deux mappings **ne produit aucun coup**
    (D9) — on ne devine pas ce qu'une carte est.
    """

    pokemon: dict[str, DefinitionCarte] = field(default_factory=dict)
    energies: dict[str, DefinitionEnergie] = field(default_factory=dict)

    def pokemon_de(self, ref: str) -> DefinitionCarte | None:
        return self.pokemon.get(ref)

    def energie_de(self, ref: str) -> DefinitionEnergie | None:
        return self.energies.get(ref)


def _energie_vers_dict(ef: DefinitionEnergie) -> dict:
    """Projette une :class:`DefinitionEnergie` en ``dict`` JSON-natif pour les ``params`` (D9)."""
    return {
        "ref": ef.ref,
        "nom": ef.nom,
        "fournit": dict(ef.fournit),
        "effets": [
            {
                "type_effet": e.type_effet,
                "regle": e.regle,
                "libelle": e.libelle,
                "params": dict(e.params),
            }
            for e in ef.effets
        ],
    }


def _joueur_de(etat: EtatPartie, jid: str) -> Joueur | None:
    for j in etat.joueurs:
        if j.id == jid:
            return j
    return None


def _autre(etat: EtatPartie, jid: str) -> Joueur:
    for j in etat.joueurs:
        if j.id != jid:
            return j
    raise ValueError(f"Pas d'adversaire pour « {jid} ».")


def _en_jeu(joueur: Joueur) -> list[PokemonEnJeu]:
    """Les Pokémon en jeu du joueur (Actif puis banc), dans un ordre déterministe."""
    return ([joueur.actif] if joueur.actif is not None else []) + list(joueur.banc)


def _cible_pokemon(catalogue: CatalogueJeu, pokemon: PokemonEnJeu) -> Cible:
    """Une :class:`Cible` illuminable pour un Pokémon en jeu, par son identité stable (R-3.6)."""
    sommet = carte_active(pokemon)
    definition = catalogue.pokemon_de(sommet.ref)
    nom = definition.nom if definition is not None else sommet.ref
    return Cible(GENRE_POKEMON_EN_JEU, identite_pokemon(pokemon), nom)


def _fiches(catalogue: CatalogueJeu, etat: EtatPartie) -> dict:
    """Les fiches ``instance_id (carte au sommet) → {pv, marqueur}`` de tous les Pokémon en jeu.

    C'est ce que :func:`pbm_game.combat.fin.resoudre_kos` consomme pour trancher un K.O. (R-13). Un
    Pokémon dont la définition manque est **omis** : il ne pourra pas être mis K.O. faute de fiche,
    ce qui lèverait bruyamment plutôt que de deviner ses PV (D9).
    """
    fiches: dict[str, dict] = {}
    for joueur in etat.joueurs:
        for pokemon in _en_jeu(joueur):
            sommet = carte_active(pokemon)
            definition = catalogue.pokemon_de(sommet.ref)
            if definition is not None:
                fiches[sommet.instance_id] = definition.fiche()
    return fiches


class _FamilleCatalogue(Famille):
    """Base des familles qui portent un :class:`CatalogueJeu` (injecté par :func:`familles_jeu`)."""

    def __init__(self, catalogue: CatalogueJeu) -> None:
        self.catalogue = catalogue


class FamillePoser(_FamilleCatalogue):
    """Poser un Pokémon de base de la main au banc (R-5.3) — joueur actif, phase principale."""

    nom = "poser"

    def gouverne(self, action: Action) -> bool:
        return action.type == ACTION_POSER

    def generer(self, etat: EtatPartie, joueur: str) -> list[ActionLegale]:
        j = _joueur_de(etat, joueur)
        if j is None or joueur != etat.tour.joueur_actif or etat.tour.phase != PHASE_PRINCIPALE:
            return []
        if j.actif is None:  # Actif absent : il faut d'abord promouvoir (R-8.7), pas poser.
            return []
        if len(j.banc) >= 5:  # R-3.2 — banc plein.
            return []
        coups: list[ActionLegale] = []
        for carte in j.main:
            definition = self.catalogue.pokemon_de(carte.ref)
            if definition is None or definition.stade != "base":
                continue
            coups.append(
                ActionLegale(
                    action=Action(
                        ACTION_POSER,
                        joueur,
                        {
                            "carte_main": carte.instance_id,
                            "definition": definition_vers_dict(definition),
                            "zone": ZONE_BANC,
                        },
                    ),
                    etiquette=f"Poser {definition.nom} au banc",
                )
            )
        return coups

    def refuser(self, etat: EtatPartie, action: Action) -> Verdict:
        if action.auteur != etat.tour.joueur_actif:
            return refus("R-5.3", "Seul le joueur actif peut poser un Pokémon (R-5.3).")
        if etat.tour.phase != PHASE_PRINCIPALE:
            return refus("R-5.3", "On pose un Pokémon en phase principale (R-5.3).")
        return refus("R-5.3", "Cette pose n'est pas possible dans cet état (R-5.3).")


class FamilleEvoluer(_FamilleCatalogue):
    """Faire évoluer un Pokémon en jeu (R-7.1) — joueur actif, phase principale, bonne chaîne."""

    nom = "evoluer"

    def gouverne(self, action: Action) -> bool:
        return action.type == ACTION_EVOLUER

    def generer(self, etat: EtatPartie, joueur: str) -> list[ActionLegale]:
        j = _joueur_de(etat, joueur)
        if j is None or joueur != etat.tour.joueur_actif or etat.tour.phase != PHASE_PRINCIPALE:
            return []
        if j.actif is None:
            return []
        coups: list[ActionLegale] = []
        for carte in j.main:
            evo = self.catalogue.pokemon_de(carte.ref)
            if evo is None or not evo.est_evolution:
                continue
            for pokemon in _en_jeu(j):
                base_id = identite_pokemon(pokemon)
                if peut_evoluer(etat.tour, base_id).refuse:
                    continue
                sommet = carte_active(pokemon)
                def_sommet = self.catalogue.pokemon_de(sommet.ref)
                if def_sommet is None or evo.evolue_depuis != def_sommet.nom:
                    continue  # R-7.1 — l'évolution se pose sur son prédécesseur imprimé.
                coups.append(
                    ActionLegale(
                        action=Action(
                            ACTION_EVOLUER,
                            joueur,
                            {
                                "base": base_id,
                                "carte_main": carte.instance_id,
                                "definition": definition_vers_dict(evo),
                                "nom_base": def_sommet.nom,
                            },
                        ),
                        etiquette=f"Faire évoluer {def_sommet.nom} en {evo.nom}",
                        cibles=(_cible_pokemon(self.catalogue, pokemon),),
                    )
                )
        return coups

    def refuser(self, etat: EtatPartie, action: Action) -> Verdict:
        return refus("R-7.1", "Cette évolution n'est pas possible dans cet état (R-7.1).")


class FamilleAttacherEnergie(_FamilleCatalogue):
    """Attacher une énergie de la main à un Pokémon en jeu (R-5.4) — une seule fois par tour."""

    nom = "attacher_energie"

    def gouverne(self, action: Action) -> bool:
        return action.type == ACTION_ATTACHER_ENERGIE

    def generer(self, etat: EtatPartie, joueur: str) -> list[ActionLegale]:
        j = _joueur_de(etat, joueur)
        if j is None or joueur != etat.tour.joueur_actif or etat.tour.phase != PHASE_PRINCIPALE:
            return []
        if j.actif is None or peut_attacher_energie(etat.tour).refuse:
            return []
        coups: list[ActionLegale] = []
        for carte in j.main:
            ef = self.catalogue.energie_de(carte.ref)
            if ef is None:
                continue
            for pokemon in _en_jeu(j):
                base_id = identite_pokemon(pokemon)
                coups.append(
                    ActionLegale(
                        action=Action(
                            ACTION_ATTACHER_ENERGIE,
                            joueur,
                            {
                                "carte_main": carte.instance_id,
                                "cible": base_id,
                                "definition": _energie_vers_dict(ef),
                            },
                        ),
                        etiquette=f"Attacher {ef.nom}",
                        cibles=(_cible_pokemon(self.catalogue, pokemon),),
                    )
                )
        return coups

    def refuser(self, etat: EtatPartie, action: Action) -> Verdict:
        if action.auteur == etat.tour.joueur_actif:
            v = peut_attacher_energie(etat.tour)
            if v.refuse:
                return v
        return refus("R-5.4", "Cet attachement d'énergie n'est pas possible dans cet état (R-5.4).")


class FamilleAttaquer(_FamilleCatalogue):
    """Déclarer une attaque de l'Actif dont le coût est payé (R-9/R-10) — termine le tour."""

    nom = "attaquer"

    def gouverne(self, action: Action) -> bool:
        return action.type == ACTION_DECLARER_ATTAQUE

    def _fournitures(self, actif: PokemonEnJeu) -> list[EnergieAttachee]:
        energies: list[EnergieAttachee] = []
        for carte in actif.energies:
            ef = self.catalogue.energie_de(carte.ref)
            if ef is None:
                continue  # énergie inconnue du catalogue : elle ne paie rien (D9).
            energies.append(ef.attachee(carte.instance_id))
        return energies

    def generer(self, etat: EtatPartie, joueur: str) -> list[ActionLegale]:
        j = _joueur_de(etat, joueur)
        if j is None or joueur != etat.tour.joueur_actif:
            return []
        if etat.tour.phase not in (PHASE_PRINCIPALE, PHASE_ATTAQUE):
            return []
        if j.actif is None or attaque_permise(etat.tour).refuse:
            return []
        def_actif = self.catalogue.pokemon_de(carte_active(j.actif).ref)
        if def_actif is None:
            return []
        energies = self._fournitures(j.actif)
        adv = _autre(etat, joueur)
        faiblesse = resistance = None
        cibles: tuple[Cible, ...] = ()
        if adv.actif is not None:
            def_adv = self.catalogue.pokemon_de(carte_active(adv.actif).ref)
            if def_adv is not None and def_adv.faiblesse is not None:
                faiblesse = {"type": def_adv.faiblesse.type, "facteur": def_adv.faiblesse.facteur}
            if def_adv is not None and def_adv.resistance is not None:
                resistance = {
                    "type": def_adv.resistance.type,
                    "reduction": def_adv.resistance.reduction,
                }
            cibles = (_cible_pokemon(self.catalogue, adv.actif),)
        fiches = _fiches(self.catalogue, etat)
        coups: list[ActionLegale] = []
        for attaque in def_actif.attaques:
            if not attaque.degats_secs:
                continue  # D9 — une attaque à effet n'est pas scriptée au jalon J1.
            if cout_satisfait(attaque.cout, [e.fournit for e in energies]).refuse:
                continue
            params: dict = {
                "attaque": {
                    "nom": attaque.nom,
                    "cout": {"types": dict(attaque.cout.types), "incolore": attaque.cout.incolore},
                    "degats": attaque.degats,
                    "effet": "",
                },
                "type_attaque": def_actif.type,
                "energies": [
                    {"instance_id": e.instance_id, "fournit": dict(e.fournit), "libelle": e.libelle}
                    for e in energies
                ],
                "fiches": fiches,
            }
            if faiblesse is not None:
                params["faiblesse"] = faiblesse
            if resistance is not None:
                params["resistance"] = resistance
            coups.append(
                ActionLegale(
                    action=Action(ACTION_DECLARER_ATTAQUE, joueur, params),
                    etiquette=f"Attaquer : {attaque.nom} ({attaque.degats})",
                    cibles=cibles,
                )
            )
        return coups

    def refuser(self, etat: EtatPartie, action: Action) -> Verdict:
        if action.auteur == etat.tour.joueur_actif:
            v = attaque_permise(etat.tour)
            if v.refuse:
                return v
        return refus("R-9.1", "Cette attaque n'est pas possible dans cet état (R-9.1/R-9.2).")


class FamilleRetraite(_FamilleCatalogue):
    """Battre en retraite (R-8.2) — une fois par tour, coût en énergies payé, un banc où aller."""

    nom = "retraite"

    def gouverne(self, action: Action) -> bool:
        return action.type == ACTION_RETRAITE

    def generer(self, etat: EtatPartie, joueur: str) -> list[ActionLegale]:
        j = _joueur_de(etat, joueur)
        if j is None or joueur != etat.tour.joueur_actif:
            return []
        if etat.tour.phase not in (PHASE_PRINCIPALE, PHASE_ATTAQUE):
            return []
        if j.actif is None or not j.banc or peut_battre_retraite(etat.tour).refuse:
            return []
        if j.actif.etats_speciaux & {ENDORMI, PARALYSE}:  # R-8.4/R-11.10
            return []
        def_actif = self.catalogue.pokemon_de(carte_active(j.actif).ref)
        if def_actif is None:
            return []
        cout = def_actif.cout_retraite
        if len(j.actif.energies) < cout:
            return []
        # Au choix du joueur (R-8.2) : au jalon J1, on défausse les `cout` premières énergies
        # attachées (déterministe). Le choix fin de QUELLES énergies défausser est une finition.
        a_defausser = [e.instance_id for e in j.actif.energies[:cout]]
        coups: list[ActionLegale] = []
        for i, pokemon in enumerate(j.banc):
            coups.append(
                ActionLegale(
                    action=Action(
                        ACTION_RETRAITE,
                        joueur,
                        {
                            "banc_index": i,
                            "cout_retraite": cout,
                            "energies_defaussees": list(a_defausser),
                        },
                    ),
                    etiquette=f"Battre en retraite (coût {cout})",
                    cibles=(_cible_pokemon(self.catalogue, pokemon),),
                )
            )
        return coups

    def refuser(self, etat: EtatPartie, action: Action) -> Verdict:
        if action.auteur == etat.tour.joueur_actif:
            v = peut_battre_retraite(etat.tour)
            if v.refuse:
                return v
        return refus("R-8.2", "Cette retraite n'est pas possible dans cet état (R-8.2).")


class FamillePromouvoir(Famille):
    """Promouvoir un Pokémon du banc après un K.O. (R-8.7), l'Actif étant absent."""

    nom = "promouvoir"

    def gouverne(self, action: Action) -> bool:
        return action.type == ACTION_PROMOUVOIR

    def generer(self, etat: EtatPartie, joueur: str) -> list[ActionLegale]:
        j = _joueur_de(etat, joueur)
        if j is None or j.actif is not None or not j.banc:
            return []
        coups: list[ActionLegale] = []
        for i, pokemon in enumerate(j.banc):
            sommet = carte_active(pokemon)
            coups.append(
                ActionLegale(
                    action=Action(ACTION_PROMOUVOIR, joueur, {"banc_index": i}),
                    etiquette="Promouvoir au poste d'Actif",
                    cibles=(Cible(GENRE_POKEMON_EN_JEU, identite_pokemon(pokemon), sommet.ref),),
                )
            )
        return coups

    def refuser(self, etat: EtatPartie, action: Action) -> Verdict:
        return refus("R-8.7", "La promotion ne s'applique qu'après un K.O. (Actif absent, R-8.7).")


class FamilleAvancerPhaseJeu(FamilleAvancerPhase):
    """``avancer_phase`` du jeu : comme la famille de base, mais interdite tant qu'un Actif manque.

    Un joueur dont l'Actif est K.O. (absent) doit d'abord **promouvoir** (R-8.7) : il ne peut pas
    passer la phase en laissant son poste d'Actif vide. Sans cette garde, un joueur pourrait rester
    sans Actif un tour entier (intouchable, injouable) — ce que les règles interdisent.
    """

    def generer(self, etat: EtatPartie, joueur: str) -> list[ActionLegale]:
        if joueur == etat.tour.joueur_actif:
            j = _joueur_de(etat, joueur)
            if j is not None and j.actif is None and j.banc:
                return []  # promotion obligatoire d'abord (R-8.7)
        return super().generer(etat, joueur)


def familles_jeu(catalogue: CatalogueJeu) -> tuple[Famille, ...]:
    """Le jeu complet de familles pour une partie, dans l'ordre d'affichage (le service l'utilise).

    Comme :data:`~pbm_game.actions.generateur.FAMILLES_DEFAUT`, mais enrichi des familles qui ont
    besoin du ``catalogue`` : poser, évoluer, attacher une énergie, attaquer, battre en retraite,
    promouvoir. ``actions_legales(etat, joueur, familles=familles_jeu(catalogue))`` et
    ``valider(...)`` restent **cohérents** (une seule source : la liste).
    """
    return (
        FamilleAvancerPhaseJeu(),
        FamillePoser(catalogue),
        FamilleEvoluer(catalogue),
        FamilleAttacherEnergie(catalogue),
        FamilleAttaquer(catalogue),
        FamilleRetraite(catalogue),
        FamillePromouvoir(),
        FamilleAbandonner(),
    )


__all__ = [
    "CatalogueJeu",
    "FamillePoser",
    "FamilleEvoluer",
    "FamilleAttacherEnergie",
    "FamilleAttaquer",
    "FamilleRetraite",
    "FamillePromouvoir",
    "FamilleAvancerPhaseJeu",
    "familles_jeu",
]
