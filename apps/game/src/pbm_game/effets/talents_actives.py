"""Transition « activer un talent » — le script d'un talent **activé** se résout (j-cartes-talents).

Module **pur** (aucune E/S), jumeau de :mod:`pbm_game.effets.objets` et
:mod:`pbm_game.effets.supporters` : il branche le **langage d'effets** sur un coup de joueur, mais
pour un **talent activé** — « une fois pendant votre tour, vous pouvez… » (type *Bibarel*,
*Oranguru*). Comme eux, la transition s'enregistre dans le ``REGISTRE`` du journal **en bas de ce
module**, ``pbm_game`` l'importe à son chargement, et les imports du DSL sont **locaux**.

Ce qu'un talent activé a de propre, et que cette transition tient côté **serveur** (jamais
l'écran) :

* **une fois par tour, PAR POKÉMON — pas par joueur** (mission n°3) : le drapeau
  ``Tour.talents_actives_ce_tour`` porte la clé ``« identité|nom »`` du talent déjà utilisé ce
  tour ; un second usage du **même** talent du **même** Pokémon est refusé, mais un **autre**
  Pokémon qui porte le même talent peut l'utiliser. Porté par l'état → sérialisé → le refus
  **survit à un F5**, et le drapeau est remis à vide à chaque tour neuf (comme l'énergie du tour) ;
* **désactivé par un état spécial** « selon la carte » (``desactive_si_etat``) : un porteur
  Endormi / Confus / Paralysé ne peut pas activer le talent — le refus **nomme** l'état ;
* **éteint par un talent-verrou** (type *Garbodor*) : si l'état porte un verrou
  :data:`~pbm_game.effets.verrous.VERROU_TALENTS_SANS_EFFET`, le coup est refusé en **nommant** la
  carte responsable. La neutralisation *dérivée* (:func:`pbm_game.effets.talents.talent_actif`,
  avec le registre des talents) est ce que le service consulte pour **proposer** ou non le coup ;
  ce verrou matérialisé est le garde-fou serveur côté transition, qui ignore le registre.

Le talent activé ne quitte **pas** la main (ce n'est pas une carte jouée : le Pokémon reste en
jeu). Sinon, la mécanique est celle d'un Objet : coût payé atomiquement d'abord, puis le script se
résout, et les Pokémon forcés à devenir Actifs sont reportés dans ``EVT_TALENT_ACTIVE`` pour que
l'orchestrateur publie :data:`~pbm_game.effets.evenements.EJ_DEVIENT_ACTIF` sur le bus.
"""

from __future__ import annotations

from dataclasses import replace

from ..journal.modele import ACTION_ACTIVER_TALENT, EVT_TALENT_ACTIVE, Action, Evenement
from ..journal.transitions import REGISTRE
from ..rng import Rng
from ..state.modele import EtatPartie, Joueur, PokemonEnJeu


def _joueur(etat: EtatPartie, jid: str) -> tuple[int, Joueur]:
    for i, j in enumerate(etat.joueurs):
        if j.id == jid:
            return i, j
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _autre(etat: EtatPartie, jid: str) -> str:
    for j in etat.joueurs:
        if j.id != jid:
            return j.id
    raise ValueError(f"Pas d'adversaire pour « {jid} ».")


def _pokemon_porteur(joueur: Joueur, identite: str) -> PokemonEnJeu | None:
    """Le Pokémon en jeu de ``joueur`` dont l'identité stable (carte de base) est ``identite``."""
    en_jeu = ([joueur.actif] if joueur.actif is not None else []) + list(joueur.banc)
    for pok in en_jeu:
        if pok.cartes[0].instance_id == identite:
            return pok
    return None


def appliquer_activer_talent(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Transition ``activer_talent`` : vérifie les règles, résout le script, marque l'usage.

    Gardes serveur (le serveur tient les règles seul) : partie vivante (R-14.6, en plus de la garde
    centrale d'``appliquer``), **joueur actif** seulement, porteur **réellement en jeu** et à soi
    (D9), talent **pas déjà activé ce tour par ce Pokémon** (R-5), **pas désactivé** par un état
    spécial du porteur, **pas éteint** par un verrou ``talents_sans_effet``, script présent (un
    effet non scripté n'est jamais approximé, D9), coût **payable** d'abord (jamais un demi-effet).
    En sortie, la clé ``« identité|nom »`` est marquée sur le tour.
    """
    from ..tour.drapeaux import marquer_talent_active, talent_active_ce_tour
    from .dsl.chargement import charger_programme
    from .dsl.contexte import ContexteEffet
    from .dsl.interprete import cout_payable, executer_programme
    from .pile import SourceEffet
    from .verrous import VERROU_TALENTS_SANS_EFFET, VERROUS_VIDES, JeuDeVerrous

    if etat.terminee:
        raise ValueError("Partie terminée : aucun talent n'est activé (R-14.6).")
    jid = action.auteur
    if jid != etat.tour.joueur_actif:
        raise ValueError(
            f"Seul le joueur actif active un talent ; le tour est à "
            f"« {etat.tour.joueur_actif} » (R-5.1)."
        )

    params = action.params
    identite = params.get("pokemon")
    if not isinstance(identite, str) or not identite:
        raise ValueError("« pokemon » (identité du porteur en jeu) est requise (R-5).")
    nom = params.get("nom")
    if not isinstance(nom, str) or not nom.strip():
        raise ValueError("« nom » (libellé du talent) est requis (journal, D9).")
    programme_brut = params.get("programme")
    if programme_brut is None:
        raise ValueError(
            f"Talent « {nom} » sans script : un effet non implémenté n'est jamais "
            "approximé (D9)."
        )

    index, joueur = _joueur(etat, jid)
    porteur = _pokemon_porteur(joueur, identite)
    if porteur is None:
        raise ValueError(
            f"Talent « {nom} » : son porteur « {identite} » n'est pas en jeu chez "
            f"« {jid} » — un talent n'agit que tant que son Pokémon est en jeu (R-12.3)."
        )

    # Une fois par tour, PAR POKÉMON (pas par joueur) : la clé distingue chaque talent de chaque
    # Pokémon, pour qu'un autre Pokémon portant le même talent reste libre de l'activer (mission).
    cle = f"{identite}|{nom}"
    une_fois = params.get("une_fois_par_tour", True)
    if une_fois and talent_active_ce_tour(etat.tour, cle):
        raise ValueError(
            f"Talent « {nom} » déjà activé ce tour par ce Pokémon : une seule fois par "
            "tour (R-5)."
        )

    # Désactivé par un état spécial « selon la carte » : un porteur dans un de ces états ne peut
    # pas activer le talent. La liste vient de la fiche du talent (params), fournie par le service.
    desactive_si_etat = params.get("desactive_si_etat") or []
    if not isinstance(desactive_si_etat, list):
        raise ValueError("« desactive_si_etat » doit être une liste d'états spéciaux.")
    bloquants = sorted(porteur.etats_speciaux & frozenset(desactive_si_etat))
    if bloquants:
        raise ValueError(
            f"Talent « {nom} » désactivé : son porteur est {', '.join(bloquants)} (R-11)."
        )

    # Éteint par un talent-verrou (type Garbodor) matérialisé en verrou : refus qui nomme la carte
    # responsable, jamais muet (comme la garde du Supporter sous « pas_de_supporter »).
    if etat.verrous is not None and etat.verrous.est_verrouille(
        VERROU_TALENTS_SANS_EFFET, cible=jid
    ):
        src = etat.verrous.source_du_verrou(VERROU_TALENTS_SANS_EFFET, cible=jid)
        responsable = src.libelle if src is not None else "un effet"
        raise ValueError(
            f"Talent « {nom} » sans effet — les talents sont éteints par "
            f"« {responsable} » (R-12.3)."
        )

    programme = charger_programme(programme_brut)
    source_brut = params.get("source") or {}
    source = SourceEffet(
        libelle=str(source_brut.get("libelle") or nom),
        ref=source_brut.get("ref"),
        instance_id=source_brut.get("instance_id"),
    )
    metadonnees = params.get("metadonnees")
    ctx = ContexteEffet(
        source=source,
        joueur=jid,
        adversaire=_autre(etat, jid),
        acteur_actif=identite,
        metadonnees=metadonnees if isinstance(metadonnees, dict) else {},
    )

    if programme.cout and not cout_payable(etat, programme.cout, ctx):
        raise ValueError(
            f"Talent « {nom} » : son coût ne peut pas être payé — il n'aurait pas dû "
            "être proposé (R-5/D9)."
        )

    resultat = executer_programme(etat, programme, ctx, rng)
    etat = resultat.etat
    if resultat.verrous:
        base = etat.verrous if etat.verrous is not None else VERROUS_VIDES
        etat = replace(etat, verrous=JeuDeVerrous(base.verrous + tuple(resultat.verrous)))

    # Le talent du tour est consommé : on marque la clé (porté par l'état, donc sérialisé → un
    # second usage est refusé, et le drapeau survit à un F5).
    if une_fois:
        etat = replace(etat, tour=marquer_talent_active(etat.tour, cle))

    evenement = Evenement(
        EVT_TALENT_ACTIVE,
        {
            "joueur": jid,
            "pokemon": identite,
            "nom": source.libelle,
            "ref": source.ref,
            "devient_actif": [list(da) for da in resultat.devenus_actifs],
        },
    )
    return etat, [evenement, *resultat.evenements]


# Enregistrement dans le REGISTRE des transitions (voir l'en-tête) : ``appliquer`` reconnaît
# désormais ``activer_talent``, qui est donc journalisé et rejouable.
REGISTRE[ACTION_ACTIVER_TALENT] = appliquer_activer_talent


__all__ = ["appliquer_activer_talent"]
