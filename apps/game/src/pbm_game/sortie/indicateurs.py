"""Indicateurs d'affichage du plateau (lot ``j-plateau-etat-visuel``) : PV, énergies, Outil.

Ce que l'écran dessine d'un coup d'œil — PV restants, énergies typées, Outil, états — doit
venir de l'**état projeté par le serveur**, sans recalcul côté client (« l'interface ne décide
de rien »). Mais le moteur reste **pur** : il ne lit jamais le catalogue (D9). Ce module est
donc le pont : il reçoit en **données** les PV imprimés et les codes de type que le service a
résolus du catalogue (:mod:`pbm_api.games.indicateurs`), et enrichit la vue déjà projetée.

Le PV **maximum** n'est pas « les PV imprimés » : c'est le **seuil de K.O.** (R-13.1), soit les
PV imprimés **plus** les deltas de PV continus d'un Outil (``seuil_ko``, R-13.1).
Afficher des dégâts comme des PV simplement soustraits (``imprimés − dégâts``) **mentirait** dès
qu'un Outil ajoute des PV ou qu'un effet change le maximum — c'est le risque nommé par la fiche du
lot. On calcule donc ``pv_max`` par le même chemin que la résolution des K.O., puis
``pv_restants = max(0, pv_max − compteurs_degats)`` (R-10.4 : les dégâts sont des **compteurs**,
jamais des PV déjà soustraits).

Pur : aucune E/S, aucune dépendance au catalogue — testable par milliers de cas, comme tout
``pbm_game``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from ..effets.continus import RegistreContinus, collecter_effets_continus, seuil_ko
from ..state.modele import EtatPartie


def refs_en_jeu(etat: EtatPartie) -> set[str]:
    """Les références catalogue de tout ce qui est **visible** en jeu, à charger pour l'affichage.

    On ne relève que les zones **publiques** (Pokémon en jeu et leur pile d'évolutions, énergies
    attachées, Outils, Stade, défausses, zone perdue) : les zones **cachées** (pioche, main
    adverse, récompenses) n'exposent aucune référence dans la vue, donc rien à charger — et rien à
    révéler. Sert à l'adaptateur API pour ne lire du catalogue que le strict nécessaire.
    """
    refs: set[str] = set()
    if etat.stade is not None:
        refs.add(etat.stade.ref)
    for joueur in etat.joueurs:
        pokemons = ((joueur.actif,) if joueur.actif is not None else ()) + joueur.banc
        for pokemon in pokemons:
            for carte in pokemon.cartes:
                refs.add(carte.ref)
            for energie in pokemon.energies:
                refs.add(energie.ref)
            if pokemon.outil is not None:
                refs.add(pokemon.outil.ref)
        for carte in joueur.defausse:
            refs.add(carte.ref)
        for carte in joueur.zone_perdue:
            refs.add(carte.ref)
    return refs


def _pokemons_vue(joueur_vue: dict) -> Iterable[dict]:
    """Les Pokémon en jeu d'une vue de joueur : l'Actif (s'il existe) puis le banc."""
    if joueur_vue.get("actif") is not None:
        yield joueur_vue["actif"]
    yield from joueur_vue.get("banc", [])


def enrichir_indicateurs(
    vue: dict,
    etat: EtatPartie,
    *,
    pv_imprimes: Mapping[str, int],
    types: Mapping[str, str | None],
    registre: RegistreContinus | None = None,
) -> dict:
    """Ajoute à chaque Pokémon de ``vue`` ses indicateurs d'affichage, puis renvoie ``vue``.

    ``vue`` est le dict d'état projeté (celui qui porte ``joueurs``), mué **en place**.

    Pour chaque Pokémon en jeu :

    * ``pv_max`` et ``pv_restants`` — ``pv_max`` est le **seuil de K.O.** (R-13.1) : PV imprimés du
      **sommet** de la pile (``pv_imprimes[ref du sommet]``) plus les deltas de PV continus d'un
      Outil, via :func:`~pbm_game.effets.continus.seuil_ko`. ``pv_restants = max(0, pv_max −
      compteurs_degats)``. **Absents** si les PV imprimés du sommet sont inconnus : on ne devine
      jamais un PV (D9), l'écran retombe alors sur les seuls compteurs de dégâts ;
    * ``type`` — le code d'élément du Pokémon (sommet), de chaque énergie attachée et de l'Outil,
      pour des pastilles **typées**. ``None`` quand le type est inconnu : l'écran montre un repère
      neutre, jamais une couleur inventée.

    ``pv_imprimes`` (ref → PV) et ``types`` (ref → code d'élément) sont **fournis par le service**
    depuis le catalogue ; ``registre`` porte les producteurs d'effets continus (deltas de PV d'un
    Outil). Vide au jalon J1 — aucune carte à effet continu n'y est encore scriptée — mais c'est
    par lui que ``pv_max`` deviendra exact dès qu'un Outil ajoutera des PV, **sans changer ce code**
    ni l'affichage (le seuil se calcule, il ne s'approxime pas).
    """
    registre = registre or {}
    effets = collecter_effets_continus(etat, registre)

    # pv_max par identité stable (instance de la carte de base) — même clé que ``seuil_ko``/
    # ``collecter_effets_continus`` (:func:`~pbm_game.effets.continus._identite`).
    pv_max_par_base: dict[str, int | None] = {}
    for joueur in etat.joueurs:
        pokemons = ((joueur.actif,) if joueur.actif is not None else ()) + joueur.banc
        for pokemon in pokemons:
            base_id = pokemon.cartes[0].instance_id
            pv_imprime = pv_imprimes.get(pokemon.cartes[-1].ref)
            pv_max_par_base[base_id] = (
                None if pv_imprime is None else seuil_ko(pv_imprime, effets, base_id)
            )

    for joueur_vue in vue["joueurs"]:
        for pokemon_vue in _pokemons_vue(joueur_vue):
            base_id = pokemon_vue["cartes"][0]["instance_id"]
            pv_max = pv_max_par_base.get(base_id)
            if pv_max is not None:
                pokemon_vue["pv_max"] = pv_max
                pokemon_vue["pv_restants"] = max(0, pv_max - pokemon_vue["compteurs_degats"])
            pokemon_vue["type"] = types.get(pokemon_vue["cartes"][-1]["ref"])
            for energie_vue in pokemon_vue["energies"]:
                energie_vue["type"] = types.get(energie_vue["ref"])
            if pokemon_vue.get("outil") is not None:
                pokemon_vue["outil"]["type"] = types.get(pokemon_vue["outil"]["ref"])
    return vue


__all__ = ["refs_en_jeu", "enrichir_indicateurs"]
