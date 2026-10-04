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

from dataclasses import dataclass, field, replace

from ..cartes.energie import DefinitionEnergie
from ..cartes.modele import DefinitionCarte, definition_vers_dict
from ..combat.cout import EnergieAttachee, cout_satisfait
from ..combat.pouvoirs_uniques import deja_utilise
from ..effets.dsl.contexte import ContexteEffet
from ..effets.dsl.jouabilite import programme_jouable
from ..effets.dsl.modele import Programme
from ..effets.pile import SourceEffet
from ..effets.verrous import VERROU_PAS_DE_SUPPORTER
from ..journal.modele import (
    ACTION_ATTACHER_ENERGIE,
    ACTION_DECLARER_ATTAQUE,
    ACTION_EVOLUER,
    ACTION_JOUER_OBJET,
    ACTION_JOUER_SUPPORTER,
    ACTION_PLACER_MISE_EN_PLACE,
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
    peut_jouer_supporter,
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

#: Marqueur de « stade » d'une carte non-Pokémon (énergie, Dresseur) dans les fiches de mise en
#: place : tout sauf ``base``, pour que ``_est_base`` la reconnaisse comme non-base (R-4.2).
_STADE_NON_POKEMON = "non_pokemon"


@dataclass(frozen=True)
class DefinitionObjet:
    """Définition catalogue d'une carte **Objet** — ce que le service extrait pour la jouer.

    Un Objet n'a pas de données de combat : il a un **script d'effet**. C'est le service qui, depuis
    le registre ``card_scripts`` (texte → script DSL validé), construit cette définition — le moteur
    ne lit jamais la base (D9).

    * ``ref`` — référence catalogue de la carte ;
    * ``nom`` — nom lisible (étiquette du coup, journal) ;
    * ``programme`` — le script d'effet déjà **chargé et validé** (:class:`Programme`) ;
    * ``source_text`` — le texte d'effet d'origine (empreinte / errata, tenus côté service).
    """

    ref: str
    nom: str
    programme: Programme
    source_text: str = ""


@dataclass(frozen=True)
class DefinitionSupporter:
    """Définition catalogue d'une carte **Supporter** — même forme qu'un :class:`DefinitionObjet`.

    Un Supporter n'a pas de données de combat : il porte un **script d'effet** (pioche, recherche,
    perturbation de l'adversaire, effet conditionnel). Le service le construit depuis le registre
    ``card_scripts`` (texte → script DSL validé), exactement comme un Objet ; ce qui le distingue à
    l'usage, c'est la **règle du tour** — un seul par tour (R-5.5), aucun au premier tour du joueur
    qui commence (R-6.2) — et le **verrou** ``pas_de_supporter`` (R-5.5). Ces contraintes sont
    portées par :class:`FamilleJouerSupporter` et la transition ``jouer_supporter``, pas par cette
    fiche (qui ne dit que « voici le script de cette carte »).
    """

    ref: str
    nom: str
    programme: Programme
    source_text: str = ""


@dataclass(frozen=True)
class CatalogueJeu:
    """Les définitions de carte des deux decks d'une partie, par ``ref`` (fourni par le service).

    * ``pokemon`` — ``ref → DefinitionCarte`` pour les cartes Pokémon ;
    * ``energies`` — ``ref → DefinitionEnergie`` pour les cartes Énergie ;
    * ``objets`` — ``ref → DefinitionObjet`` pour les cartes Objet scriptées (``j-cartes-objets``).
    * ``supporters`` — ``ref → DefinitionSupporter`` pour les Supporters (``j-cartes-supporters``).

    Le moteur ne lit **jamais** la base : ce catalogue est extrait une fois, à la création de la
    partie, et passé aux familles. Une ``ref`` absente des mappings **ne produit aucun coup**
    (D9) — on ne devine pas ce qu'une carte est.
    """

    pokemon: dict[str, DefinitionCarte] = field(default_factory=dict)
    energies: dict[str, DefinitionEnergie] = field(default_factory=dict)
    objets: dict[str, DefinitionObjet] = field(default_factory=dict)
    supporters: dict[str, DefinitionSupporter] = field(default_factory=dict)

    def pokemon_de(self, ref: str) -> DefinitionCarte | None:
        return self.pokemon.get(ref)

    def energie_de(self, ref: str) -> DefinitionEnergie | None:
        return self.energies.get(ref)

    def objet_de(self, ref: str) -> DefinitionObjet | None:
        return self.objets.get(ref)

    def supporter_de(self, ref: str) -> DefinitionSupporter | None:
        return self.supporters.get(ref)

    def metadonnees_completes(self) -> dict:
        """Les métadonnées ``ref → {categorie, stade, type}`` de **toutes** les cartes connues.

        Nécessaire aux sélecteurs **filtrés** d'un script d'Objet qui fouillent une zone de cartes
        (« cherchez un Pokémon dans votre deck ») : la sélection (:func:`candidats`) ne retient une
        carte de la pioche/défausse que si ses métadonnées disent sa catégorie. Une ``ref`` absente
        n'est simplement pas retenue par un filtre (jamais devinée, D9). Couvre les Pokémon (avec
        stade et type), les énergies et les Objets connus.
        """
        meta: dict[str, dict] = {}
        for ref, d in self.pokemon.items():
            meta[ref] = {"categorie": "pokemon", "stade": d.stade, "type": d.type}
        for ref in self.energies:
            meta.setdefault(ref, {"categorie": "energie"})
        for ref in self.objets:
            meta.setdefault(ref, {"categorie": "dresseur"})
        for ref in self.supporters:
            meta.setdefault(ref, {"categorie": "dresseur"})
        return meta

    def definitions(self) -> dict[str, dict]:
        """Le mapping ``ref → fiche`` attendu par la mise en place (R-4.2).

        Pour un Pokémon, la fiche complète (porte son ``stade``) ; pour une énergie, un marqueur de
        stade **non-base** suffit (la mise en place n'a besoin que de « est-ce une base ? »).
        """
        fiches: dict[str, dict] = {ref: definition_vers_dict(d) for ref, d in self.pokemon.items()}
        for ref in self.energies:
            fiches[ref] = {"stade": _STADE_NON_POKEMON}
        return fiches


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


def _index_de(etat: EtatPartie, jid: str) -> int | None:
    for i, j in enumerate(etat.joueurs):
        if j.id == jid:
            return i
    return None


def _autre(etat: EtatPartie, jid: str) -> Joueur:
    for j in etat.joueurs:
        if j.id != jid:
            return j
    raise ValueError(f"Pas d'adversaire pour « {jid} ».")


def _etat_sans_carte_main(etat: EtatPartie, jid: str, instance_id: str) -> EtatPartie:
    """L'état où ``instance_id`` a quitté la main de ``jid`` — pour sonder la jouabilité d'un Objet.

    Un Objet se défausse avant que son effet ne s'applique (R-5.5) : la sonde de jouabilité doit
    regarder la main **sans** lui, sinon son texte « défaussez N autres cartes » se compterait
    lui-même. Renvoie l'état inchangé si la carte n'y est pas (la sonde n'est appelée que sur des
    cartes réellement en main).
    """
    idx = _index_de(etat, jid)
    if idx is None:
        return etat
    j = etat.joueurs[idx]
    main = tuple(c for c in j.main if c.instance_id != instance_id)
    if len(main) == len(j.main):
        return etat
    joueurs = list(etat.joueurs)
    joueurs[idx] = replace(j, main=main)
    return replace(etat, joueurs=(joueurs[0], joueurs[1]))


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


def _metadonnees(catalogue: CatalogueJeu, etat: EtatPartie) -> dict:
    """Les métadonnées de catalogue des Pokémon en jeu — ``ref → {categorie, stade, type}``.

    Portées dans les ``params`` d'une attaque à effet (le journal les transporte, D9) : le script
    DSL en a besoin pour ses sélecteurs filtrés (``categorie``/``stade``) et sa condition
    ``type_cible`` (« si le Défenseur est de type Eau »). Le moteur ne lit jamais le catalogue :
    une ``ref`` absente d'ici n'est simplement pas retenue par un filtre (jamais devinée).
    """
    meta: dict[str, dict] = {}
    for joueur in etat.joueurs:
        for pokemon in _en_jeu(joueur):
            ref = carte_active(pokemon).ref
            definition = catalogue.pokemon_de(ref)
            if definition is not None:
                meta[ref] = {
                    "categorie": "pokemon",
                    "stade": definition.stade,
                    "type": definition.type,
                }
    return meta


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
        metadonnees = _metadonnees(self.catalogue, etat)
        coups: list[ActionLegale] = []
        for attaque in def_actif.attaques:
            if not attaque.jouable:
                continue  # D9 — une attaque à effet sans script n'est pas résoluble.
            # Pouvoir à usage unique déjà dépensé (attaque GX R-15.3, VSTAR Power R-15.6) : on ne le
            # propose plus comme coup légal — l'interdiction est portée par l'état du joueur.
            if attaque.pouvoir_unique is not None and deja_utilise(j, attaque.pouvoir_unique):
                continue
            if cout_satisfait(attaque.cout, [e.fournit for e in energies]).refuse:
                continue
            # Dégâts : secs (entier) ou variables (formule calculée à la résolution, R-10.1).
            degats = (
                attaque.degats_variables if attaque.degats_variables is not None else attaque.degats
            )
            fiche_attaque: dict = {
                "nom": attaque.nom,
                "cout": {"types": dict(attaque.cout.types), "incolore": attaque.cout.incolore},
                "degats": degats,
                "effet": attaque.effet,
            }
            if attaque.script is not None:
                fiche_attaque["script"] = attaque.script
            if attaque.pouvoir_unique is not None:
                fiche_attaque["pouvoir_unique"] = attaque.pouvoir_unique
            params: dict = {
                "attaque": fiche_attaque,
                "type_attaque": def_actif.type,
                "ref_attaquant": carte_active(j.actif).ref,
                "energies": [
                    {"instance_id": e.instance_id, "fournit": dict(e.fournit), "libelle": e.libelle}
                    for e in energies
                ],
                "fiches": fiches,
                "metadonnees": metadonnees,
            }
            if faiblesse is not None:
                params["faiblesse"] = faiblesse
            if resistance is not None:
                params["resistance"] = resistance
            etiquette = (
                f"Attaquer : {attaque.nom}"
                if attaque.degats_variables is not None
                else f"Attaquer : {attaque.nom} ({attaque.degats})"
            )
            coups.append(
                ActionLegale(
                    action=Action(ACTION_DECLARER_ATTAQUE, joueur, params),
                    etiquette=etiquette,
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


class FamillePlacer(_FamilleCatalogue):
    """Placer son Actif et son banc face cachée à la mise en place (R-4.2) — avant le premier tour.

    Un coup par Pokémon de **base** de la main qu'on peut poser comme **Actif** ; le reste des bases
    de la main part au **banc** (au plus cinq). Ce banc automatique est une simplification du jalon
    J1 : le joueur choisit son Actif, les autres bases le suivent au banc. Le choix fin du banc est
    une finition d'interface ultérieure.
    """

    nom = "placer"

    def gouverne(self, action: Action) -> bool:
        return action.type == ACTION_PLACER_MISE_EN_PLACE

    def generer(self, etat: EtatPartie, joueur: str) -> list[ActionLegale]:
        mep = etat.mise_en_place
        if mep is None:
            return []
        idx = _index_de(etat, joueur)
        if idx is None or mep.placements[idx] is not None:
            return []  # pas de mise en place en cours pour lui, ou il a déjà placé.
        j = etat.joueurs[idx]
        bases = [
            c
            for c in j.main
            if (d := self.catalogue.pokemon_de(c.ref)) is not None and d.stade == "base"
        ]
        if not bases:
            return []
        fiches = self.catalogue.definitions()
        coups: list[ActionLegale] = []
        for carte in bases:
            banc = [b.instance_id for b in bases if b.instance_id != carte.instance_id][:5]
            nom = self.catalogue.pokemon_de(carte.ref).nom
            coups.append(
                ActionLegale(
                    action=Action(
                        ACTION_PLACER_MISE_EN_PLACE,
                        joueur,
                        {"actif": carte.instance_id, "banc": banc, "definitions": fiches},
                    ),
                    etiquette=f"Placer {nom} comme Actif (banc : {len(banc)})",
                )
            )
        return coups

    def refuser(self, etat: EtatPartie, action: Action) -> Verdict:
        return refus("R-4.2", "Ce placement n'est pas possible dans cet état (R-4.2).")


class FamilleJouerObjet(_FamilleCatalogue):
    """Jouer une carte **Objet** (R-5.5) — joueur actif, phase principale, **autant qu'on veut**.

    Contrairement au Supporter (un par tour) ou à l'énergie (une par tour), un Objet se joue sans
    limite de nombre (R-5.5) : aucune garde de tour. La contrainte propre à ce lot — **un Objet
    n'est listé que s'il a une cible valide** :
    :func:`~pbm_game.effets.dsl.jouabilite.programme_jouable` vérifie, sur la main *sans* l'Objet
    (son texte ne peut pas se défausser lui-même), que le coût est payable et qu'au moins un effet
    pourrait agir. Un **appât sur un banc adverse vide** n'apparaît
    donc pas, et son refus en cite la raison (critère d'acceptation). Pendant une **demande de
    décision** (``etat.resolution``), la partie est en pause : aucun Objet n'est proposé — la garde
    centrale d'``appliquer`` le refuse aussi, mais on ne le **liste** pas, pour que liste et
    validation restent cohérentes (une seule source de vérité).
    """

    nom = "jouer_objet"

    def gouverne(self, action: Action) -> bool:
        return action.type == ACTION_JOUER_OBJET

    def generer(self, etat: EtatPartie, joueur: str) -> list[ActionLegale]:
        j = _joueur_de(etat, joueur)
        if j is None or joueur != etat.tour.joueur_actif or etat.tour.phase != PHASE_PRINCIPALE:
            return []
        if etat.resolution is not None:
            return []  # une décision est en attente : seule la réponse (ou l'abandon) est permise
        meta = self.catalogue.metadonnees_completes()
        adversaire = _autre(etat, joueur).id
        coups: list[ActionLegale] = []
        for carte in j.main:
            objet = self.catalogue.objet_de(carte.ref)
            if objet is None:
                continue
            ctx = ContexteEffet(
                source=SourceEffet(libelle=objet.nom, ref=objet.ref, instance_id=carte.instance_id),
                joueur=joueur,
                adversaire=adversaire,
                metadonnees=meta,
            )
            etat_probe = _etat_sans_carte_main(etat, joueur, carte.instance_id)
            jouable, _raison = programme_jouable(etat_probe, objet.programme, ctx)
            if not jouable:
                continue
            coups.append(
                ActionLegale(
                    action=Action(
                        ACTION_JOUER_OBJET,
                        joueur,
                        {
                            "carte_main": carte.instance_id,
                            "programme": objet.programme.en_json(),
                            "source": {
                                "libelle": objet.nom,
                                "ref": objet.ref,
                                "instance_id": carte.instance_id,
                            },
                            "metadonnees": meta,
                            "nom": objet.nom,
                        },
                    ),
                    etiquette=f"Jouer {objet.nom}",
                )
            )
        return coups

    def refuser(self, etat: EtatPartie, action: Action) -> Verdict:
        if action.auteur != etat.tour.joueur_actif:
            return refus("R-5.5", "Seul le joueur actif joue un Objet (R-5.3/R-5.5).")
        if etat.tour.phase != PHASE_PRINCIPALE:
            return refus("R-5.5", "On joue un Objet en phase principale (R-5.3).")
        if etat.resolution is not None:
            return refus(
                "R-5.5",
                "Une décision est en attente : seule la réponse (ou l'abandon) est permise, "
                "pas un Objet.",
            )
        return refus(
            "R-5.5",
            "Cet Objet n'est pas jouable ici — il n'a aucune cible valide (p. ex. un appât sur un "
            "banc adverse vide, R-5.5).",
        )


class FamilleJouerSupporter(_FamilleCatalogue):
    """Jouer une carte **Supporter** (R-5.5) — joueur actif, phase principale, **un seul par tour**.

    Contrairement à l'Objet (illimité), le Supporter est contraint par le tour : **un seul** par
    tour (R-5.5) et **aucun** au premier tour du joueur qui commence (R-6.2). On ne le **liste**
    que si :func:`~pbm_game.tour.contraintes.peut_jouer_supporter` l'accorde **et** qu'aucun verrou
    ``pas_de_supporter`` (type *Marnie* inversé, un talent — R-5.5) ne pèse sur le joueur. La
    jouabilité du **script** se vérifie ensuite comme pour un Objet
    (:func:`~pbm_game.effets.dsl.jouabilite.programme_jouable`, sur la main *sans* la carte, qui se
    défausse d'abord). Le refus **nomme** toujours la cause : premier tour (R-6.2), Supporter déjà
    joué (R-5.5), verrou (R-5.5, avec la carte responsable), ou script sans cible — jamais muet.

    Le drapeau « un Supporter ce tour » (``Tour.supporter_joue``) est **levé par la transition**
    ``jouer_supporter`` (le serveur tient la règle), pas par cette famille qui ne fait que lister.
    """

    nom = "jouer_supporter"

    def gouverne(self, action: Action) -> bool:
        return action.type == ACTION_JOUER_SUPPORTER

    def _verrouille(self, etat: EtatPartie, joueur: str) -> bool:
        """Un verrou ``pas_de_supporter`` pèse-t-il sur ``joueur`` (ou globalement) ? (R-5.5)"""
        return etat.verrous is not None and etat.verrous.est_verrouille(
            VERROU_PAS_DE_SUPPORTER, cible=joueur
        )

    def generer(self, etat: EtatPartie, joueur: str) -> list[ActionLegale]:
        j = _joueur_de(etat, joueur)
        if j is None or joueur != etat.tour.joueur_actif or etat.tour.phase != PHASE_PRINCIPALE:
            return []
        if etat.resolution is not None:
            return []  # une décision est en attente : seule la réponse (ou l'abandon) est permise
        if peut_jouer_supporter(etat.tour).refuse:
            return []  # premier tour du joueur qui commence (R-6.2) ou Supporter déjà joué (R-5.5)
        if self._verrouille(etat, joueur):
            return []  # un verrou « pas de Supporter ce tour » pèse sur lui (R-5.5)
        meta = self.catalogue.metadonnees_completes()
        adversaire = _autre(etat, joueur).id
        coups: list[ActionLegale] = []
        for carte in j.main:
            supp = self.catalogue.supporter_de(carte.ref)
            if supp is None:
                continue
            ctx = ContexteEffet(
                source=SourceEffet(libelle=supp.nom, ref=supp.ref, instance_id=carte.instance_id),
                joueur=joueur,
                adversaire=adversaire,
                metadonnees=meta,
            )
            etat_probe = _etat_sans_carte_main(etat, joueur, carte.instance_id)
            jouable, _raison = programme_jouable(etat_probe, supp.programme, ctx)
            if not jouable:
                continue
            coups.append(
                ActionLegale(
                    action=Action(
                        ACTION_JOUER_SUPPORTER,
                        joueur,
                        {
                            "carte_main": carte.instance_id,
                            "programme": supp.programme.en_json(),
                            "source": {
                                "libelle": supp.nom,
                                "ref": supp.ref,
                                "instance_id": carte.instance_id,
                            },
                            "metadonnees": meta,
                            "nom": supp.nom,
                        },
                    ),
                    etiquette=f"Jouer {supp.nom}",
                )
            )
        return coups

    def refuser(self, etat: EtatPartie, action: Action) -> Verdict:
        if action.auteur != etat.tour.joueur_actif:
            return refus("R-5.5", "Seul le joueur actif joue un Supporter (R-5.3/R-5.5).")
        if etat.tour.phase != PHASE_PRINCIPALE:
            return refus("R-5.5", "On joue un Supporter en phase principale (R-5.3).")
        if etat.resolution is not None:
            return refus(
                "R-5.5",
                "Une décision est en attente : seule la réponse (ou l'abandon) est permise, "
                "pas un Supporter.",
            )
        v = peut_jouer_supporter(etat.tour)  # R-6.2 (premier tour) ou R-5.5 (déjà joué)
        if v.refuse:
            return v
        if self._verrouille(etat, action.auteur):
            src = etat.verrous.source_du_verrou(VERROU_PAS_DE_SUPPORTER, cible=action.auteur)
            nom = src.libelle if src is not None else "un effet"
            return refus(
                "R-5.5",
                f"Aucun Supporter ne peut être joué ce tour — bloqué par « {nom} » (R-5.5).",
            )
        return refus(
            "R-5.5",
            "Ce Supporter n'est pas jouable ici — son effet n'aurait aucune cible valide (R-5.5).",
        )


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
        FamillePlacer(catalogue),
        FamilleAvancerPhaseJeu(),
        FamillePoser(catalogue),
        FamilleEvoluer(catalogue),
        FamilleAttacherEnergie(catalogue),
        FamilleJouerObjet(catalogue),
        FamilleJouerSupporter(catalogue),
        FamilleAttaquer(catalogue),
        FamilleRetraite(catalogue),
        FamillePromouvoir(),
        FamilleAbandonner(),
    )


__all__ = [
    "CatalogueJeu",
    "DefinitionObjet",
    "DefinitionSupporter",
    "FamillePoser",
    "FamilleEvoluer",
    "FamilleAttacherEnergie",
    "FamilleJouerObjet",
    "FamilleJouerSupporter",
    "FamilleAttaquer",
    "FamilleRetraite",
    "FamillePromouvoir",
    "FamillePlacer",
    "FamilleAvancerPhaseJeu",
    "familles_jeu",
]
