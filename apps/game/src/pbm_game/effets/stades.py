"""Les **Stades** — une zone partagée, un seul en jeu, des effets continus pour les deux camps.

Module **pur** (aucune E/S, ni HTTP, ni base, ni React), comme tout ``pbm_game``. Il livre deux
choses, et c'est tout ce dont un Stade a besoin au jalon J2 :

1. **La transition ``jouer_stade``** (R-3.5/R-5.5). La carte quitte la main pour la **zone Stade
   partagée** (:attr:`~pbm_game.state.modele.EtatPartie.stade`) ; le Stade précédent part à la
   **défausse de SON propriétaire** (``stade_proprietaire``) et **son effet cesse** ; le drapeau
   « un Stade ce tour » est levé. Enregistrée dans le ``REGISTRE`` du journal à l'import, comme
   :mod:`pbm_game.effets.objets`.
2. **Trois Stades réels** exprimés en :data:`~pbm_game.effets.continus.ProducteurContinu` — ce que
   le Stade **ajoute au calcul** tant qu'il est en jeu, jamais une mutation de l'état.

**Le piège que ce module évite** (fiche ``j-cartes-stades``) : *appliquer l'effet d'un Stade au
moment où il est joué (mutation) au lieu de le consulter au calcul — son remplacement laisse
alors des traces indélébiles.* Ici, l'effet d'un Stade n'existe **nulle part** dans l'état : il se
**dérive** du Stade en jeu à chaque calcul (:func:`~pbm_game.effets.continus.collecter_effets_\
continus`). Jouer un autre Stade change ``etat.stade`` ; au calcul suivant, l'ancien producteur
n'est plus consulté, donc son bonus disparaît — **sans rien défaire**. Le critère d'acceptation
n°1 (« le retrait d'un Stade restaure exactement les calculs antérieurs ») est vrai *par
construction*. Et comme la ``cible`` du Stade est ``None`` (il n'appartient à personne, R-3.5),
ses effets frappent **les deux camps** (critère n°2).

**Les conditions des Stades portent sur des données de catalogue** (« Pokémon de base », « de
Niveau 2 », « Psykokwak »), que le moteur pur ne lit jamais (D9). Les producteurs sont donc des
**fabriques** : chacune capte une métadonnée ``ref → {stade, nom, …}`` — exactement ce que le
service extrait du catalogue à la création de la partie
(:meth:`~pbm_game.actions.familles_jeu.CatalogueJeu.metadonnees_completes`) — et renvoie un
producteur **pur**. C'est le même branchement que les talents
(:func:`~pbm_game.effets.talents.construire_registre_continus`), appliqué au Stade.

Les trois Stades livrés (tous « les vôtres **et** ceux de votre adversaire ») :

* **Stade en Liesse** (``sv08-180``) — chaque Pokémon **de base** en jeu reçoit **+30 PV** ;
* **Montagne Gravité** (``sv08-177``) — chaque Pokémon de **Niveau 2** en jeu **perd 30 PV** ;
* **Hôtel « Au paradis des Pokémon »** (``svp-224``) — le **coût de retraite** de chaque
  **Psykokwak** en jeu est **diminué de 1** (c'est ce dernier qui prouve le critère « un Stade
  modifie le coût de retraite des deux camps »).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

from ..cartes.modele import STADE_2, STADE_BASE
from ..journal.modele import ACTION_JOUER_STADE, EVT_STADE_JOUE, Action, Evenement
from ..journal.transitions import REGISTRE
from ..rng import Rng
from ..state.modele import EtatPartie, Joueur, PokemonEnJeu, carte_active
from .continus import PORTEE_STADE, EffetContinu, ProducteurContinu, RegistreContinus
from .pile import SourceEffet


def _joueur(etat: EtatPartie, jid: str) -> tuple[int, Joueur]:
    for i, j in enumerate(etat.joueurs):
        if j.id == jid:
            return i, j
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _remplacer_joueur(etat: EtatPartie, index: int, joueur: Joueur) -> EtatPartie:
    joueurs = list(etat.joueurs)
    joueurs[index] = joueur
    return replace(etat, joueurs=(joueurs[0], joueurs[1]))


def appliquer_jouer_stade(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Transition ``jouer_stade`` : pose le Stade, défausse l'ancien, lève le drapeau du tour.

    Gardes serveur (le serveur tient les règles seul, R-3.5/R-5.5) : partie vivante (R-14.6, en
    plus de la garde centrale d'``appliquer``), **joueur actif** seulement, **un seul Stade par
    tour** (:func:`~pbm_game.tour.contraintes.peut_jouer_stade`), carte réellement **en main**
    (sinon ``ValueError``, D9). Défense R-3.5 : on refuse de rejouer un Stade de **même référence**
    que celui en jeu — l'interdiction par **nom** (deux impressions du même Stade) est portée, de
    façon autoritaire, par :class:`~pbm_game.actions.familles_jeu.FamilleJouerStade` qui connaît le
    catalogue et que ``valider`` recalcule ; cette garde-ci couvre le rejeu du journal.

    Effet (R-3.5) : la carte quitte la main pour ``etat.stade`` ; **s'il y avait un Stade**, il
    part à la **défausse de son propriétaire** (``stade_proprietaire``) — c'est la fin de son
    effet, par simple disparition de l'état. ``stade_proprietaire`` devient l'auteur. En sortie,
    ``Tour.stade_joue`` est levé (porté par l'état, donc un second Stade est refusé et le drapeau
    survit à une reprise après un F5). ``rng`` est inutilisé (un Stade n'a pas d'aléa à la pose),
    reçu pour l'uniformité de la signature des transitions.
    """
    from ..tour.contraintes import peut_jouer_stade
    from ..tour.drapeaux import marquer_stade_joue

    if etat.terminee:
        raise ValueError("Partie terminée : aucun Stade n'est joué (R-14.6).")
    jid = action.auteur
    if jid != etat.tour.joueur_actif:
        raise ValueError(
            f"Seul le joueur actif joue un Stade ; le tour est à "
            f"« {etat.tour.joueur_actif} » (R-5.5)."
        )

    verdict = peut_jouer_stade(etat.tour)  # R-5.5 — un seul Stade par tour
    if verdict.refuse:
        raise ValueError(f"{verdict.message} ({verdict.regle})")

    params = action.params
    carte_main = params.get("carte_main")
    if not isinstance(carte_main, str) or not carte_main:
        raise ValueError("« carte_main » (instance_id du Stade en main) est requise (R-3.5).")

    index, joueur = _joueur(etat, jid)
    carte = next((c for c in joueur.main if c.instance_id == carte_main), None)
    if carte is None:
        raise ValueError(
            f"Stade « {carte_main} » absent de la main de « {jid} » : on ne joue pas une carte "
            "qu'on n'a pas (R-3.5)."
        )

    # Défense R-3.5 (rejeu/sécurité) : un Stade de même **référence** déjà en jeu ne se rejoue pas.
    if etat.stade is not None and etat.stade.ref == carte.ref:
        raise ValueError(
            "Un Stade de même nom est déjà en jeu : on ne peut pas le rejouer (R-3.5)."
        )

    nom = str(params.get("nom") or "Stade")

    # La carte quitte la main (avant toute défausse de l'ancien : zones distinctes, aucun mélange).
    main = tuple(c for c in joueur.main if c.instance_id != carte_main)
    etat = _remplacer_joueur(etat, index, replace(joueur, main=main))

    # R-3.5 — l'ancien Stade part à la défausse de son propriétaire ; son effet cesse à ce retrait.
    remplace: str | None = None
    proprietaire_remplace: str | None = None
    if etat.stade is not None:
        ancien = etat.stade
        prop = etat.stade_proprietaire
        if prop is None:
            raise ValueError(
                "Stade en jeu sans propriétaire : état incohérent (R-3.5) — jamais deviné (D9)."
            )
        remplace = ancien.instance_id
        proprietaire_remplace = prop
        pindex, pjoueur = _joueur(etat, prop)
        etat = _remplacer_joueur(
            etat, pindex, replace(pjoueur, defausse=pjoueur.defausse + (ancien,))
        )

    # Le nouveau Stade entre en zone partagée ; son propriétaire est l'auteur (R-3.5).
    etat = replace(etat, stade=carte, stade_proprietaire=jid)
    etat = replace(etat, tour=marquer_stade_joue(etat.tour))

    evenement = Evenement(
        EVT_STADE_JOUE,
        {
            "joueur": jid,
            "ref": carte.ref,
            "nom": nom,
            "carte": carte.instance_id,
            "remplace": remplace,
            "proprietaire_remplace": proprietaire_remplace,
        },
    )
    return etat, [evenement]


# Enregistrement dans le REGISTRE des transitions (voir l'en-tête) : ``appliquer`` reconnaît
# désormais ``jouer_stade``, qui est donc journalisé et rejouable.
REGISTRE[ACTION_JOUER_STADE] = appliquer_jouer_stade


# --- Trois Stades réels, en producteurs d'effets continus (D9 : scriptés et testés) ----------

#: Références catalogue (``tcgdex_id``) des trois Stades scriptés par ce lot.
STADE_EN_LIESSE = "sv08-180"
MONTAGNE_GRAVITE = "sv08-177"
HOTEL_PARADIS = "svp-224"

#: Noms (FR/EN) du Pokémon **Psykokwak** — la condition de l'Hôtel « Au paradis des Pokémon ».
_NOMS_PSYKOKWAK: frozenset[str] = frozenset({"psykokwak", "psyduck"})


def _en_jeu(etat: EtatPartie) -> Iterator[PokemonEnJeu]:
    """Chaque Pokémon en jeu des deux joueurs (Actif puis banc), dans un ordre déterministe."""
    for joueur in etat.joueurs:
        if joueur.actif is not None:
            yield joueur.actif
        yield from joueur.banc


def _identite(pokemon: PokemonEnJeu) -> str:
    """L'identité stable du Pokémon (``instance_id`` de la carte de base) — clé des deltas."""
    return pokemon.cartes[0].instance_id


def _source(etat: EtatPartie, ref: str, libelle: str) -> SourceEffet:
    """La source lisible du Stade en jeu (journal) ; repli sur ``ref`` si l'état n'en a pas."""
    instance = etat.stade.instance_id if etat.stade is not None else ref
    return SourceEffet(libelle=libelle, ref=ref, instance_id=instance)


def producteur_stade_en_liesse(meta: dict[str, dict]) -> ProducteurContinu:
    """**Stade en Liesse** (``sv08-180``) — chaque Pokémon **de base** en jeu reçoit **+30 PV**.

    Effet continu symétrique (R-3.5) : un delta de PV de +30 par Pokémon dont la carte au sommet
    est de stade « base » (:data:`~pbm_game.cartes.modele.STADE_BASE`), des **deux** camps. Le
    seuil de K.O. monte tant que le Stade est en jeu (:func:`~pbm_game.effets.continus.seuil_ko`,
    R-13.1) ; le remplacer rend les PV *par construction*. ``meta`` associe chaque ``ref`` à sa
    métadonnée catalogue (au moins ``stade``).
    """

    def _p(etat: EtatPartie, ref: str, cible: str | None) -> list[EffetContinu]:
        source = _source(etat, ref, "Stade en Liesse")
        effets: list[EffetContinu] = []
        for pok in _en_jeu(etat):
            m = meta.get(carte_active(pok).ref)
            if m is not None and m.get("stade") == STADE_BASE:
                effets.append(
                    EffetContinu(
                        libelle="Stade en Liesse : +30 PV (Pokémon de base)",
                        regle="R-3.5",
                        source=source,
                        portee=PORTEE_STADE,
                        cible=_identite(pok),
                        pv=30,
                    )
                )
        return effets

    return _p


def producteur_montagne_gravite(meta: dict[str, dict]) -> ProducteurContinu:
    """**Montagne Gravité** (``sv08-177``) — chaque Pokémon de **Niveau 2** en jeu **perd 30 PV**.

    Effet continu symétrique (R-3.5) : un delta de PV de −30 par Pokémon dont la carte au sommet
    est de stade « stade2 » (:data:`~pbm_game.cartes.modele.STADE_2`), des **deux** camps. Le seuil
    de K.O. descend tant que le Stade est en jeu (R-13.1) ; le retirer le remonte, sans rien
    défaire. ``meta`` associe chaque ``ref`` à sa métadonnée catalogue (au moins ``stade``).
    """

    def _p(etat: EtatPartie, ref: str, cible: str | None) -> list[EffetContinu]:
        source = _source(etat, ref, "Montagne Gravité")
        effets: list[EffetContinu] = []
        for pok in _en_jeu(etat):
            m = meta.get(carte_active(pok).ref)
            if m is not None and m.get("stade") == STADE_2:
                effets.append(
                    EffetContinu(
                        libelle="Montagne Gravité : −30 PV (Pokémon de Niveau 2)",
                        regle="R-3.5",
                        source=source,
                        portee=PORTEE_STADE,
                        cible=_identite(pok),
                        pv=-30,
                    )
                )
        return effets

    return _p


def producteur_hotel_paradis(meta: dict[str, dict]) -> ProducteurContinu:
    """**Hôtel « Au paradis des Pokémon »** (``svp-224``) — retraite des **Psykokwak** **−1**.

    Effet continu symétrique (R-3.5) qui touche le **coût de retraite** (R-8.2) : −1 symbole pour
    chaque Psykokwak en jeu, des **deux** camps. C'est le Stade qui prouve le critère « un Stade
    modifie le coût de retraite des deux camps » : quand l'Actif d'un joueur est un Psykokwak, sa
    retraite coûte une énergie de moins (plancher à 0, :func:`~pbm_game.effets.continus.cout_\
retraite_effectif`). La condition porte sur l'**espèce** : ``meta`` doit donc fournir le ``nom``
    de chaque ``ref`` (le service l'a depuis le catalogue ; le moteur ne le devine pas, D9).
    """

    def _p(etat: EtatPartie, ref: str, cible: str | None) -> list[EffetContinu]:
        source = _source(etat, ref, "Hôtel « Au paradis des Pokémon »")
        effets: list[EffetContinu] = []
        for pok in _en_jeu(etat):
            m = meta.get(carte_active(pok).ref)
            if m is not None and str(m.get("nom", "")).strip().lower() in _NOMS_PSYKOKWAK:
                effets.append(
                    EffetContinu(
                        libelle="Hôtel « Au paradis des Pokémon » : −1 retraite (Psykokwak)",
                        regle="R-3.5",
                        source=source,
                        portee=PORTEE_STADE,
                        cible=_identite(pok),
                        cout_retraite=-1,
                    )
                )
        return effets

    return _p


def registre_stades(meta: dict[str, dict]) -> RegistreContinus:
    """Le registre des **trois Stades réels** de ce lot, lié à la métadonnée catalogue ``meta``.

    Prêt à fusionner dans le registre continu d'une partie
    (:attr:`~pbm_game.actions.familles_jeu.CatalogueJeu.registre_continus`) par le service, aux
    côtés des producteurs d'Outils et de talents. Chaque clé est une ``ref`` réelle (D9) ; un Stade
    absent du registre ne contribue rien (l'absence réelle d'effet, pas un silence).
    """
    return {
        STADE_EN_LIESSE: producteur_stade_en_liesse(meta),
        MONTAGNE_GRAVITE: producteur_montagne_gravite(meta),
        HOTEL_PARADIS: producteur_hotel_paradis(meta),
    }


__all__ = [
    "appliquer_jouer_stade",
    "STADE_EN_LIESSE",
    "MONTAGNE_GRAVITE",
    "HOTEL_PARADIS",
    "producteur_stade_en_liesse",
    "producteur_montagne_gravite",
    "producteur_hotel_paradis",
    "registre_stades",
]
