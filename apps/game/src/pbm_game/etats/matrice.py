"""Pose d'un état spécial et **matrice de cumul** (R-11.8) — plus la guérison (R-11.9).

Module **pur** (aucune E/S, ni HTTP, ni base, ni React), comme tout ``pbm_game``. Il ne
touche ni à l'aléatoire ni au journal : il **transforme un Pokémon** en lui posant ou en lui
retirant des états. La *résolution* des états (pile ou face au Checkup, confusion avant
l'attaque) vit ailleurs — elle a besoin du :class:`~pbm_game.rng.Rng` et du journal, pas la
simple pose.

Le piège du lot, nommé dans sa fiche : **le cumul**. Selon la version des règles, certains
états coexistent et d'autres se remplacent. Le seul garde-fou est la matrice écrite dans
``docs/jeu/REGLES.md`` (R-11.8) et testée paire par paire. On l'encode ici une fois, sans la
disperser dans les appelants.

La matrice, en une phrase (R-11.8) : **Endormi, Confus et Paralysé orientent la carte → un
seul des trois à la fois, le dernier posé remplace le précédent** ; **Empoisonné et Brûlé sont
des marqueurs → cumulables entre eux ET avec l'état d'orientation en cours**. L'exemple
officiel : un Pokémon peut être **Brûlé + Paralysé + Empoisonné** en même temps.

**R-11.2** — un état spécial ne frappe que le Pokémon **Actif**. Ce module pose l'état sur le
Pokémon qu'on lui donne ; c'est à l'appelant (l'effet qui inflige l'état) de ne viser que
l'Actif. :func:`appliquer_etat` ne devine donc pas la position du Pokémon.
"""

from __future__ import annotations

from dataclasses import replace

from ..state.modele import (
    ENDORMI,
    ETATS_ORIENTATION,
    ETATS_SPECIAUX,
    PARALYSE,
    PokemonEnJeu,
)


def appliquer_etat(pokemon: PokemonEnJeu, etat: str) -> PokemonEnJeu:
    """Pose l'état ``etat`` sur ``pokemon`` selon la matrice de cumul (R-11.8). Pur.

    Renvoie un **nouveau** :class:`~pbm_game.state.modele.PokemonEnJeu` (l'état est figé) :

    * si ``etat`` **oriente** la carte (Endormi, Confus, Paralysé) : il **remplace** l'état
      d'orientation en place — un seul des trois à la fois (R-11.8) — et **laisse** les
      marqueurs (Brûlé, Empoisonné) intacts ;
    * si ``etat`` est un **marqueur** (Brûlé, Empoisonné) : il **s'ajoute** à ce qui est là
      (cumulable), en **laissant** l'orientation en cours. Un marqueur déjà présent reste un
      seul marqueur (« un nouveau remplace l'ancien », R-11.4/R-11.7 : l'ensemble est le même).

    Lève ``ValueError`` si ``etat`` n'est pas l'un des cinq états connus (R-11.1) — un état
    inconnu est une panne, jamais posé « au mieux » (D9 : on n'approxime rien).
    """
    if etat not in ETATS_SPECIAUX:
        raise ValueError(
            f"État spécial inconnu : {etat!r} — les cinq connus sont {sorted(ETATS_SPECIAUX)} "
            "(R-11.1)."
        )
    etats = set(pokemon.etats_speciaux)
    if etat in ETATS_ORIENTATION:
        # Un seul état d'orientation à la fois : le dernier posé remplace (R-11.8). Les
        # marqueurs en place (Brûlé, Empoisonné) sont conservés.
        etats -= ETATS_ORIENTATION
        etats.add(etat)
    else:
        # Marqueur (R-11.8) : cumulable avec l'orientation en cours et l'autre marqueur.
        etats.add(etat)
    nouveaux = frozenset(etats)
    if nouveaux == pokemon.etats_speciaux:
        return pokemon
    return replace(pokemon, etats_speciaux=nouveaux)


def soigner_etats_speciaux(pokemon: PokemonEnJeu) -> PokemonEnJeu:
    """Retire **tous** les états spéciaux de ``pokemon`` (R-11.9). Pur.

    C'est la guérison de **tous** les états que provoquent le **passage au banc** (retraite,
    promotion, échange forcé — voir :mod:`pbm_game.banc.mouvements`) et l'**évolution**
    (lot ``j-cartes-pokemon``). Les effets de **soin** qui guérissent les états passeront aussi
    par ici. Une **seule porte** : la logique de « que garde / que perd un Pokémon qui guérit »
    ne doit pas se dédoubler entre ces chemins (sinon ils divergent).

    Ne touche **qu'aux** états spéciaux : énergies, Outil, compteurs de dégâts et pile
    d'évolutions sont conservés (R-8.6 pour le banc ; l'évolution empile par-dessus). Renvoie le
    Pokémon inchangé s'il n'a aucun état (évite une copie inutile).
    """
    if not pokemon.etats_speciaux:
        return pokemon
    return replace(pokemon, etats_speciaux=frozenset())


def etat_bloquant_attaque(pokemon: PokemonEnJeu) -> str | None:
    """L'état qui **empêche ``pokemon`` d'attaquer**, ou ``None`` s'il le peut (R-11.3/R-11.6).

    Renvoie :data:`~pbm_game.state.modele.ENDORMI` ou :data:`~pbm_game.state.modele.PARALYSE`
    si l'un est présent (ces deux-là interdisent l'attaque), sinon ``None``. La **Confusion**
    n'est **pas** un blocage : elle n'empêche pas de *déclarer* l'attaque, elle impose un pile ou
    face **avant** (R-11.5) — c'est :mod:`pbm_game.etats.attaque` qui la résout. Comme un seul
    état d'orientation coexiste (R-11.8), au plus un état est ici renvoyé.
    """
    bloquants = pokemon.etats_speciaux & {ENDORMI, PARALYSE}
    if not bloquants:
        return None
    # Au plus un état d'orientation à la fois (R-11.8) : il n'y en a jamais deux à départager.
    return next(iter(bloquants))


__all__ = [
    "appliquer_etat",
    "soigner_etats_speciaux",
    "etat_bloquant_attaque",
]
