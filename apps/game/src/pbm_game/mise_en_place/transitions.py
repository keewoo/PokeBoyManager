"""Transitions de **mise en place** (R-4) — mélange, mulligans, placement face caché, révélation.

Module **pur** (aucune E/S), comme tout ``pbm_game``. Il enregistre ses deux transitions dans le
``REGISTRE`` du journal en bas du module (comme ``banc``, ``cartes`` et ``checkup``) : le noyau des
transitions ne peut pas le faire lui-même (cycle d'import), donc ``pbm_game`` importe
``mise_en_place`` à son chargement.

Deux transitions, deux natures :

* ``mise_en_place_initiale`` (système) — **déterministe à partir de la graine** : mélange des deux
  decks (R-4.1), pioche de sept, et la **boucle de mulligan** (R-4.4/R-4.6) jusqu'à ce que les deux
  joueurs aient une main avec un Pokémon de base. Elle révèle la main au bon moment (R-4.4), compte
  les mulligans et les cartes bonus dues à l'adversaire (R-4.5). Aucun choix de joueur ici ;
* ``placer_mise_en_place`` (joueur) — chaque joueur place son Actif et son banc **face cachée**
  (R-4.2) ; le choix reste secret tant que les deux n'ont pas placé. Quand le **second** place, la
  même transition résout la **révélation simultanée** : Actif/banc deviennent publics, six
  récompenses sont posées face cachée (R-4.3), les cartes bonus sont piochées (R-4.5), et la partie
  commence (``mise_en_place`` repasse à ``None``).

**Le serveur fait autorité, et un effet n'est jamais approximé (D9).** Le moteur ne devine aucun
stade : les deux actions portent les ``definitions`` (fiches catalogue), fournies par le service —
c'est ainsi qu'on sait si une carte est un Pokémon **de base** (R-4.2/R-4.4). Une définition
manquante **bloque** bruyamment, jamais devinée.

Règles de référence servies (``docs/jeu/REGLES.md``) :

* **R-4.1** — mélange des deux decks, pioche de sept ;
* **R-4.4 / R-4.6** — mulligan (main sans base révélée, remélangée, repiochée ; double mulligan
  sans carte bonus) ;
* **R-4.5 / R-16.9** — cartes bonus dues à l'adversaire pour chaque mulligan pris seul ;
* **R-4.2 / R-3.2** — Actif de base obligatoire, banc ≤ 5 bases, face caché ;
* **R-4.3 / R-3.4** — six récompenses posées face cachée à la révélation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from ..cartes.modele import STADE_BASE
from ..journal.modele import (
    ACTION_MISE_EN_PLACE_INITIALE,
    ACTION_PLACER_MISE_EN_PLACE,
    EVT_CARTES_PIOCHEES,
    EVT_MAIN_REVELEE,
    EVT_MISE_EN_PLACE_PRETE,
    EVT_MISE_EN_PLACE_REVELEE,
    EVT_MULLIGAN,
    EVT_PIOCHE_MELANGEE,
    EVT_PLACEMENT_CACHE,
    Action,
    Evenement,
)
from ..journal.transitions import REGISTRE
from ..rng import Rng, flux_melange_deck
from ..state.modele import Carte, EtatPartie, Joueur, PokemonEnJeu
from .modele import BANC_MAX, MAIN_INITIALE, RECOMPENSES, MiseEnPlace, PlacementCache

# --- Helpers immuables -------------------------------------------------------


def _index_joueur(etat: EtatPartie, jid: str) -> int:
    for i, joueur in enumerate(etat.joueurs):
        if joueur.id == jid:
            return i
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _remplacer_joueur(etat: EtatPartie, index: int, joueur: Joueur) -> EtatPartie:
    joueurs = list(etat.joueurs)
    joueurs[index] = joueur
    return replace(etat, joueurs=(joueurs[0], joueurs[1]))


def _definitions(params: dict) -> dict[str, Mapping]:
    """Lit ``params["definitions"]`` (mapping ``ref → fiche``) sans :class:`DefinitionCarte`.

    Le service fournit ces fiches depuis le catalogue (le moteur est pur, D9). Une carte
    **non-Pokémon**
    (énergie, Dresseur) n'a pas de ``DefinitionCarte`` : sa fiche porte seulement un ``stade``.
    Ici, la mise en place n'a besoin que de « est-ce un Pokémon de **base** ? » (R-4.2/R-4.4) —
    on garde les fiches brutes et on ne lit que leur ``stade``. Un mapping absent/vide **bloque**
    (sans lui, le stade d'une carte est inconnu, jamais deviné — D9).
    """
    brut = params.get("definitions")
    if not isinstance(brut, Mapping) or not brut:
        raise ValueError(
            "« definitions » (mapping ref→fiche catalogue) requis pour la mise en place — sans lui "
            "le stade d'une carte est inconnu, jamais deviné (D9, R-4.2/R-4.4)."
        )
    return dict(brut)


def _est_base(defs: dict[str, Mapping], ref: str) -> bool:
    """Vrai si la carte de référence ``ref`` est un Pokémon de **base** (R-4.2), sinon faux.

    Lève si ``ref`` n'a aucune fiche : un stade inconnu **bloque** (D9), il n'est jamais supposé
    « pas une base » par défaut — l'absence est une panne de données, pas une réponse. Une carte
    non-Pokémon (énergie, Dresseur) porte un ``stade`` non-base : elle n'est pas une base.
    """
    fiche = defs.get(ref)
    if fiche is None or not isinstance(fiche, Mapping):
        raise ValueError(
            f"Fiche de catalogue absente pour « {ref} » : stade inconnu, jamais deviné (D9)."
        )
    return fiche.get("stade") == STADE_BASE


def _main_a_une_base(joueur: Joueur, defs: dict[str, Mapping]) -> bool:
    """Vrai si la main du joueur a au moins un Pokémon de base (R-4.2, condition de R-4.4)."""
    return any(_est_base(defs, carte.ref) for carte in joueur.main)


# --- Mélange et pioche initiale (R-4.1) --------------------------------------


def _melanger_et_piocher(
    etat: EtatPartie, index: int, rng: Rng, motif: str
) -> tuple[EtatPartie, list[Evenement]]:
    """Mélange toute la zone deck+main du joueur ``index`` et lui (re)pioche sept cartes (R-4.1).

    Sert la pioche d'ouverture **et** le remélange d'un mulligan (R-4.4) : dans les deux cas, on
    remet l'éventuelle main dans la pioche, on mélange le tout par le flux dédié au joueur (son
    indice avance, ce que le vérificateur d'aléatoire contrôle), puis on pioche sept cartes du
    sommet. Refuse une zone de moins de sept cartes (R-4.1 ne se joue pas sur un deck trop petit) :
    jamais de repli silencieux.
    """
    joueur = etat.joueurs[index]
    zone = joueur.pioche + joueur.main
    if len(zone) < MAIN_INITIALE:
        raise ValueError(
            f"Deck de « {joueur.id} » : {len(zone)} carte(s), moins que les {MAIN_INITIALE} de la "
            "main d'ouverture (R-4.1)."
        )
    melangee = tuple(rng.melanger(flux_melange_deck(joueur.id), motif, zone))
    main = melangee[:MAIN_INITIALE]
    pioche = melangee[MAIN_INITIALE:]
    etat2 = _remplacer_joueur(etat, index, replace(joueur, main=main, pioche=pioche))
    evenements = [
        Evenement(EVT_PIOCHE_MELANGEE, {"joueur": joueur.id, "taille": len(melangee)}),
        Evenement(
            EVT_CARTES_PIOCHEES,
            {
                "joueur": joueur.id,
                "nombre": MAIN_INITIALE,
                "instance_ids": [c.instance_id for c in main],
            },
        ),
    ]
    return etat2, evenements


def _mise_en_place_initiale(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Mise en place système (R-4.1/R-4.4/R-4.6) : mélange, pioche de sept, boucle de mulligan.

    Déterministe à partir de la graine (via ``rng``) : aucun choix de joueur. Elle laisse l'état
    en attente du **placement** (``mise_en_place`` non ``None``), avec, par joueur, le nombre de
    mulligans pris (R-4.4) et les cartes bonus dues (R-4.5). Gardes (le serveur fait autorité) :
    la partie n'est pas terminée, la mise en place n'a pas déjà eu lieu, l'état est **vierge**
    (mains vides, aucun Pokémon en jeu, aucune récompense), et **chaque deck a au moins un Pokémon
    de base** — sinon la boucle de mulligan ne terminerait jamais (R-2/R-4.4), ce qu'on refuse
    bruyamment plutôt que de boucler en silence.
    """
    if etat.terminee:
        raise ValueError("Partie terminée : aucune mise en place (R-14.6).")
    if etat.mise_en_place is not None:
        raise ValueError(
            "Mise en place déjà en cours : « mise_en_place_initiale » ne se rejoue pas."
        )
    for joueur in etat.joueurs:
        if joueur.main or joueur.actif or joueur.banc or joueur.recompenses:
            raise ValueError(
                f"Mise en place initiale sur un état non vierge pour « {joueur.id} » : mains, "
                "Pokémon en jeu et récompenses doivent être vides (R-4.1)."
            )

    defs = _definitions(action.params)
    for joueur in etat.joueurs:
        if not any(_est_base(defs, c.ref) for c in joueur.pioche):
            raise ValueError(
                f"Deck de « {joueur.id} » sans aucun Pokémon de base : la mise en place ne peut "
                "pas aboutir (R-2/R-4.4) — un deck légal porte au moins une base."
            )

    evenements: list[Evenement] = []

    # R-4.1 — mélange des deux decks et pioche de sept, chacun par son flux dédié.
    for index, joueur in enumerate(etat.joueurs):
        etat, evts = _melanger_et_piocher(
            etat, index, rng, f"R-4.1 mélange et pioche de sept {joueur.id}"
        )
        evenements.extend(evts)

    # R-4.4 / R-4.6 — boucle de mulligan. Un **tour** de boucle regarde les deux mains à la fois :
    # si les deux sont sans base, c'est un double mulligan **sans carte bonus** (R-4.6) ; si un seul
    # l'est, l'adversaire gagne une carte bonus (R-4.5). On recommence jusqu'à deux mains valides.
    mulligans = [0, 0]
    bonus = [0, 0]
    while True:
        bases = [_main_a_une_base(joueur, defs) for joueur in etat.joueurs]
        if all(bases):
            break
        simultane = not bases[0] and not bases[1]
        for index, a_une_base in enumerate(bases):
            if a_une_base:
                continue
            etat, evts = _un_mulligan(etat, index, rng)
            evenements.extend(evts)
            mulligans[index] += 1
            donnees: dict = {
                "joueur": etat.joueurs[index].id,
                "numero": mulligans[index],
                "simultane": simultane,
            }
            if not simultane:
                # R-4.5 : le mulligan pris SEUL donne une carte bonus à l'adversaire.
                adverse = 1 - index
                bonus[adverse] += 1
                donnees["bonus_pour"] = etat.joueurs[adverse].id
            evenements.append(Evenement(EVT_MULLIGAN, donnees))

    mise_en_place = MiseEnPlace(mulligans=(mulligans[0], mulligans[1]), bonus=(bonus[0], bonus[1]))
    etat = replace(etat, mise_en_place=mise_en_place)
    evenements.append(
        Evenement(
            EVT_MISE_EN_PLACE_PRETE,
            {
                "joueurs": [
                    {"id": j.id, "mulligans": mulligans[i], "bonus": bonus[i]}
                    for i, j in enumerate(etat.joueurs)
                ]
            },
        )
    )
    return etat, evenements


def _un_mulligan(
    etat: EtatPartie, index: int, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Un mulligan du joueur ``index`` (R-4.4) : révéler la main, remélanger, repiocher sept.

    La révélation est journalisée **avec son contenu** (R-4.4) — c'est le seul moment où une main
    est publique, et le journal en garde la trace (exigence « le contenu révélé est journalisé »).
    """
    joueur = etat.joueurs[index]
    evt_revelee = Evenement(
        EVT_MAIN_REVELEE,
        {
            "joueur": joueur.id,
            "cartes": [{"instance_id": c.instance_id, "ref": c.ref} for c in joueur.main],
        },
    )
    etat2, evts_remelange = _melanger_et_piocher(
        etat, index, rng, f"R-4.4 mulligan {joueur.id}"
    )
    return etat2, [evt_revelee, *evts_remelange]


# --- Placement face caché et révélation simultanée (R-4.2/R-4.3) -------------


def _placer_mise_en_place(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Un joueur place son Actif et son banc **face cachée** (R-4.2) ; révèle si les deux ont placé.

    Valide (le serveur fait autorité) : l'Actif est un Pokémon de **base** présent dans la main
    (R-4.2), le banc contient au plus cinq bases distinctes de la main (R-3.2/R-4.2), aucune carte
    n'est choisie deux fois. Le placement est stocké **caché** : l'événement produit ne porte que le
    joueur, jamais son contenu (non-fuite). Si, après ce placement, les **deux** joueurs ont placé,
    la **révélation simultanée** est résolue ici même — un seul moment, un seul événement.
    """
    if etat.terminee:
        raise ValueError("Partie terminée : aucun placement (R-14.6).")
    mise_en_place = etat.mise_en_place
    if mise_en_place is None:
        raise ValueError(
            "Aucune mise en place en cours : « placer_mise_en_place » ne vaut qu'avant le premier "
            "tour (R-4.2)."
        )
    jid = action.auteur
    index = _index_joueur(etat, jid)
    joueur = etat.joueurs[index]
    defs = _definitions(action.params)

    actif_id = action.params.get("actif")
    if not isinstance(actif_id, str) or not actif_id:
        raise ValueError(
            "« actif » (instance_id du Pokémon de base posé comme Actif) requis (R-4.2)."
        )
    banc_ids = action.params.get("banc", [])
    if not isinstance(banc_ids, list) or not all(isinstance(b, str) and b for b in banc_ids):
        raise ValueError("« banc » doit être une liste d'instance_id (R-4.2).")
    if len(banc_ids) > BANC_MAX:
        raise ValueError(
            f"Banc de « {jid} » : {len(banc_ids)} Pokémon demandés, le banc en porte au plus "
            f"{BANC_MAX} (R-3.2/R-4.2)."
        )

    choisis = [actif_id, *banc_ids]
    if len(set(choisis)) != len(choisis):
        raise ValueError(
            f"Même carte choisie deux fois à la mise en place de « {jid} » : une carte ne peut pas "
            "être à la fois Actif et au banc (R-4.2)."
        )

    main_par_id = {c.instance_id: c for c in joueur.main}
    for cid in choisis:
        carte = main_par_id.get(cid)
        if carte is None:
            raise ValueError(
                f"Carte « {cid} » absente de la main de « {jid} » : on ne place que ses propres "
                "cartes (R-4.2)."
            )
        if not _est_base(defs, carte.ref):
            raise ValueError(
                f"« {cid} » (ref {carte.ref}) n'est pas un Pokémon de base : seul un Pokémon de "
                "base se pose à la mise en place (R-4.2)."
            )

    placement = PlacementCache(actif=actif_id, banc=tuple(banc_ids))
    mise_en_place = mise_en_place.avec_placement(index, placement)
    etat = replace(etat, mise_en_place=mise_en_place)
    evenements: list[Evenement] = [Evenement(EVT_PLACEMENT_CACHE, {"joueur": jid})]

    if mise_en_place.tous_places:
        etat, evts_revelation = _reveler(etat, rng)
        evenements.extend(evts_revelation)
    return etat, evenements


def _poser_pokemon(main_par_id: dict[str, Carte], instance_id: str, jid: str) -> Carte:
    carte = main_par_id.get(instance_id)
    if carte is None:
        # Ne doit pas arriver (le placement a été validé) : on le dit plutôt que de poser du vide.
        raise ValueError(
            f"Révélation : carte « {instance_id} » introuvable dans la main de « {jid} » (R-4.2)."
        )
    return carte


def _reveler(etat: EtatPartie, rng: Rng) -> tuple[EtatPartie, list[Evenement]]:
    """Révélation **simultanée** (R-4.2/R-4.3) : les deux placements deviennent publics d'un coup.

    Pour chaque joueur : son Actif et son banc choisis sortent de la main vers les zones publiques
    (R-4.2) ; six récompenses sont posées face cachée depuis le sommet de la pioche (R-4.3) ; puis
    ses éventuelles cartes bonus sont piochées (R-4.5, « après que l'adversaire a fini sa mise en
    place » : à la révélation). L'ordre est **récompenses puis bonus** — les récompenses se posent
    pendant la mise en place, la carte bonus se pioche ensuite. ``mise_en_place`` repasse à ``None``
    (la partie commence pour de bon). Un **seul** événement porte les deux côtés : aucun joueur
    n'est révélé avant l'autre, même s'il a validé dix secondes plus tôt.
    """
    mise_en_place = etat.mise_en_place
    assert mise_en_place is not None  # garanti par l'appelant (tous_places)
    nouveaux: list[Joueur] = list(etat.joueurs)
    resume: list[dict] = []
    for index, joueur in enumerate(etat.joueurs):
        placement = mise_en_place.placements[index]
        assert placement is not None  # tous_places
        main_par_id = {c.instance_id: c for c in joueur.main}
        actif_carte = _poser_pokemon(main_par_id, placement.actif, joueur.id)
        banc_cartes = [_poser_pokemon(main_par_id, b, joueur.id) for b in placement.banc]

        retires = {placement.actif, *placement.banc}
        reste_main = tuple(c for c in joueur.main if c.instance_id not in retires)

        nb_bonus = mise_en_place.bonus[index]
        if len(joueur.pioche) < RECOMPENSES + nb_bonus:
            raise ValueError(
                f"Pioche de « {joueur.id} » insuffisante pour poser {RECOMPENSES} récompenses "
                f"(R-4.3) et piocher {nb_bonus} carte(s) bonus (R-4.5) : "
                f"{len(joueur.pioche)} carte(s) restantes."
            )
        recompenses = joueur.pioche[:RECOMPENSES]
        reste_pioche = joueur.pioche[RECOMPENSES:]
        bonus_cartes = reste_pioche[:nb_bonus]
        reste_pioche = reste_pioche[nb_bonus:]

        actif = PokemonEnJeu(cartes=(actif_carte,))
        banc = tuple(PokemonEnJeu(cartes=(c,)) for c in banc_cartes)
        nouveaux[index] = replace(
            joueur,
            main=reste_main + bonus_cartes,
            pioche=reste_pioche,
            actif=actif,
            banc=banc,
            recompenses=recompenses,
        )
        resume.append(
            {
                "joueur": joueur.id,
                "actif": actif_carte.ref,
                "banc": [c.ref for c in banc_cartes],
                "recompenses_nombre": len(recompenses),
                "bonus_pioches": len(bonus_cartes),
            }
        )

    etat2 = replace(etat, joueurs=(nouveaux[0], nouveaux[1]), mise_en_place=None)
    return etat2, [Evenement(EVT_MISE_EN_PLACE_REVELEE, {"joueurs": resume})]


# Enregistrement dans le REGISTRE des transitions (voir l'en-tête du module). ``pbm_game`` importe
# ``mise_en_place`` à son chargement pour que ``appliquer`` reconnaisse ces deux actions.
REGISTRE[ACTION_MISE_EN_PLACE_INITIALE] = _mise_en_place_initiale
REGISTRE[ACTION_PLACER_MISE_EN_PLACE] = _placer_mise_en_place


__all__ = ["MAIN_INITIALE", "RECOMPENSES", "BANC_MAX"]
