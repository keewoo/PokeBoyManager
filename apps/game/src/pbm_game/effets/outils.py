"""Les **Outils Pokémon** — un par Pokémon, attaché, défaussé au K.O. (R-3.7).

Module **pur** (aucune E/S, ni HTTP, ni base, ni React), comme tout ``pbm_game``. Il livre ce
dont un Outil a besoin au jalon J2, et rien de plus :

1. **La transition ``attacher_outil``** (R-3.7/R-5.5). La carte quitte la main du joueur actif
   pour rejoindre **un** de ses Pokémon (Actif ou banc). On peut jouer **autant d'Outils qu'on
   veut par tour** (R-5.5, comme un Objet — donc aucun drapeau de tour), mais **au plus un par
   Pokémon** (R-3.7, refusé bruyamment).
2. **La transition ``retirer_outil``** (R-3.7/R-13.2). Un effet (souvent adverse) retire l'Outil :
   il part à la **défausse de son propriétaire** et son effet continu **cesse par construction**
   (la source disparaît de l'état). Comme le retrait d'un Outil de PV abaisse le **seuil de K.O.**
   (R-13.1), la transition **résout un K.O. immédiat** — avec le PV effectif post-retrait fourni
   par le service, exactement comme la résolution d'attaque (:func:`~pbm_game.combat.fin.\
resoudre_kos`), donc rejouable sans catalogue.
3. **Trois Outils réels** exprimés en :data:`~pbm_game.effets.continus.ProducteurContinu` — ce que
   l'Outil **ajoute au calcul** tant qu'il est attaché, jamais une mutation de l'état.

**Le cadre d'effets continus (``effets.continus``) gère déjà l'Outil.** ``collecter_effets_\
continus`` relit ``pokemon.outil`` à chaque calcul et, si sa ``ref`` est dans le registre, consulte
son producteur avec ``cible`` = l'identité stable du porteur. Un Outil de PV déplace donc le seuil
de K.O. (``seuil_ko``) ; un Outil de dégâts ajoute un modificateur de défense (``modificateurs_\
degats``). Retirer l'Outil le fait disparaître de l'état → le producteur n'est plus consulté →
l'effet s'évanouit **sans rien défaire**. C'est le critère « le retrait restaure les calculs
antérieurs », vrai *par construction*.

**La défausse au K.O. est déjà portée** par :func:`~pbm_game.combat.ko.cartes_a_defausser`
(R-13.2 : un K.O. défausse le Pokémon avec sa pile, ses énergies **et son Outil**). Ce module n'y
touche pas ; il en dépend.

**Les conditions des Outils portent sur des données de catalogue** (« Pokémon de type Metal »),
que le moteur pur ne lit jamais (D9). Les producteurs sont donc des **fabriques** : chacune capte
une métadonnée ``ref → {type, …}`` — ce que le service extrait du catalogue — et renvoie un
producteur **pur**. C'est le même branchement que les Stades
(:func:`~pbm_game.effets.stades.registre_stades`) et les talents.

Les trois Outils livrés — le seul sous-ensemble d'Outils que le **catalogue de jeu** enrichit à ce
jour (``docs/jeu/OUTILS.md``) :

* **Protective Poncho** (``B2-147`` et ``B2-234``, deux impressions) — tant que le porteur est
  **au banc**, **prévient tous les dégâts** des attaques et talents adverses (un modificateur de
  défense qui ramène les dégâts à ``0``) ;
* **Metal Core Barrier** (``B2-148``) — le Pokémon **Metal** porteur subit **−50 dégâts** des
  attaques adverses (un modificateur de défense ``−50``). Sa clause « se défausse à la fin du tour
  adverse » s'obtient par un ``retirer_outil`` émis par le service à ce moment (le moteur fournit
  le retrait, le service en orchestre l'instant — voir ``docs/jeu/OUTILS.md``).
"""

from __future__ import annotations

from dataclasses import replace

from ..combat.modele import modificateur_ajout, modificateur_fixe
from ..journal.modele import (
    ACTION_ATTACHER_OUTIL,
    ACTION_RETIRER_OUTIL,
    EVT_OUTIL_ATTACHE,
    EVT_OUTIL_RETIRE,
    Action,
    Evenement,
)
from ..journal.transitions import REGISTRE
from ..rng import Rng
from ..state.modele import (
    PHASE_PRINCIPALE,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    carte_active,
)
from ..tour.drapeaux import identite_pokemon
from .continus import (
    FACE_DEFENSEUR,
    PORTEE_OUTIL,
    EffetContinu,
    ProducteurContinu,
    RegistreContinus,
)
from .pile import SourceEffet

# Zones où vit un Pokémon en jeu (mêmes repères que ``cartes.attache``).
ZONE_ACTIF = "actif"
ZONE_BANC = "banc"


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


def _remplacer_joueur(etat: EtatPartie, index: int, joueur: Joueur) -> EtatPartie:
    joueurs = list(etat.joueurs)
    joueurs[index] = joueur
    return replace(etat, joueurs=(joueurs[0], joueurs[1]))


def _localiser(joueur: Joueur, identite: str) -> tuple[str, int] | None:
    """Localise le Pokémon ``identite`` : ``("actif", -1)`` / ``("banc", i)``, ou ``None``."""
    if joueur.actif is not None and identite_pokemon(joueur.actif) == identite:
        return (ZONE_ACTIF, -1)
    for i, pokemon in enumerate(joueur.banc):
        if identite_pokemon(pokemon) == identite:
            return (ZONE_BANC, i)
    return None


def _pokemon_a(joueur: Joueur, loc: tuple[str, int]) -> PokemonEnJeu:
    zone, i = loc
    pokemon = joueur.actif if zone == ZONE_ACTIF else joueur.banc[i]
    assert pokemon is not None  # garanti par _localiser
    return pokemon


def _poser_pokemon(joueur: Joueur, loc: tuple[str, int], pokemon: PokemonEnJeu) -> Joueur:
    """Repose ``pokemon`` à l'emplacement ``loc`` du joueur (immuable)."""
    zone, i = loc
    if zone == ZONE_ACTIF:
        return replace(joueur, actif=pokemon)
    banc = list(joueur.banc)
    banc[i] = pokemon
    return replace(joueur, banc=tuple(banc))


# --- Transition : attacher un Outil (R-3.7/R-5.5) ----------------------------------------


def appliquer_attacher_outil(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Transition ``attacher_outil`` : attache un Outil de la main à un Pokémon du joueur actif.

    Gardes serveur (le serveur tient les règles seul) : partie vivante (R-14.6), **joueur actif**
    seulement et **phase principale** (R-5.1/R-5.3), carte réellement **en main** (sinon
    ``ValueError``, D9), Pokémon cible bien **en jeu** chez l'auteur. Règle clé **R-3.7** : si le
    Pokémon cible porte **déjà** un Outil, on refuse — au plus un Outil par Pokémon. Aucun drapeau
    de tour n'est levé : on joue autant d'Outils qu'on veut par tour (R-5.5, contrairement au
    Supporter). Toute validation précède la moindre mutation (jamais un demi-coup). ``rng`` est
    inutilisé (attacher un Outil n'a aucun aléa).

    ``params`` : ``carte_main`` (instance_id de l'Outil en main), ``cible`` (identité du Pokémon
    qui le reçoit, voir :func:`~pbm_game.tour.drapeaux.identite_pokemon`), ``nom`` (libellé pour le
    journal). Émet :data:`~pbm_game.journal.modele.EVT_OUTIL_ATTACHE`.
    """
    if etat.terminee:
        raise ValueError("Partie terminée : aucun Outil n'est attaché (R-14.6).")
    jid = action.auteur
    if jid != etat.tour.joueur_actif:
        raise ValueError(
            f"Seul le joueur actif attache un Outil ; le tour est à "
            f"« {etat.tour.joueur_actif} » (R-5.5)."
        )
    if etat.tour.phase != PHASE_PRINCIPALE:
        raise ValueError(
            f"« attacher un Outil » se joue en phase principale (phase : {etat.tour.phase!r}, "
            "R-5.3)."
        )

    params = action.params
    carte_id = params.get("carte_main")
    if not isinstance(carte_id, str) or not carte_id:
        raise ValueError("« carte_main » (instance_id de l'Outil en main) est requis (R-3.7).")
    cible_id = params.get("cible")
    if not isinstance(cible_id, str) or not cible_id:
        raise ValueError(
            "« cible » (identité du Pokémon qui reçoit l'Outil) est requise (R-3.7)."
        )

    index, joueur = _joueur(etat, jid)
    carte = next((c for c in joueur.main if c.instance_id == carte_id), None)
    if carte is None:
        raise ValueError(
            f"Outil « {carte_id} » absent de la main de « {jid} » : on n'attache qu'un Outil de "
            "sa propre main (R-3.7)."
        )
    loc = _localiser(joueur, cible_id)
    if loc is None:
        raise ValueError(
            f"Aucun Pokémon de « {jid} » n'a l'identité « {cible_id} » pour recevoir l'Outil "
            "(R-3.7)."
        )
    cible_pk = _pokemon_a(joueur, loc)
    if cible_pk.outil is not None:
        raise ValueError(
            "Ce Pokémon porte déjà un Outil : au plus un Outil par Pokémon (R-3.7)."
        )

    # Toutes les gardes sont passées : la carte quitte la main et rejoint le Pokémon ciblé.
    reste_main = tuple(c for c in joueur.main if c.instance_id != carte_id)
    attache = replace(cible_pk, outil=carte)
    joueur = _poser_pokemon(replace(joueur, main=reste_main), loc, attache)
    etat = _remplacer_joueur(etat, index, joueur)

    evt = Evenement(
        EVT_OUTIL_ATTACHE,
        {
            "joueur": jid,
            "outil": carte.instance_id,
            "ref": carte.ref,
            "cible": cible_id,
            "nom": str(params.get("nom") or "Outil"),
        },
    )
    return etat, [evt]


# --- Transition : retirer un Outil (R-3.7/R-13.2), avec K.O. immédiat (R-13.1) ------------


def appliquer_retirer_outil(
    etat: EtatPartie, action: Action, rng: Rng
) -> tuple[EtatPartie, list[Evenement]]:
    """Transition ``retirer_outil`` : un effet retire l'Outil d'un Pokémon et le défausse (R-13.2).

    L'Outil rejoint la **défausse de son propriétaire** (``proprietaire``) et son effet continu
    cesse par simple disparition de l'état. Le retrait est **journalisé** (:data:`~pbm_game.\
journal.modele.EVT_OUTIL_RETIRE`) : la fin de ses effets est explicite, jamais un retrait muet.

    **K.O. immédiat (R-13.1).** Un Outil de PV maintenait peut-être le porteur en vie ; une fois
    retiré, le seuil de K.O. redescend et les compteurs déjà posés peuvent le dépasser. La
    transition appelle donc :func:`~pbm_game.combat.fin.resoudre_kos` avec les ``fiches`` fournies
    par le service — le **PV effectif post-retrait** (construit par :func:`~pbm_game.effets.\
continus.fiches_avec_seuils_continus`), donc le K.O. se rejoue sans catalogue. Le résolveur est
    **partagé** avec l'attaque et le Checkup : récompenses, promotion et conditions de victoire
    suivent le même chemin.

    ``params`` : ``proprietaire`` (joueur dont le Pokémon porte l'Outil), ``cible`` (identité du
    Pokémon), ``fiches`` (PV effectif + marqueur, par ``instance_id`` du sommet). ``rng`` est
    inutilisé (le retrait n'a pas d'aléa ; passé pour l'uniformité des signatures de transition).
    """
    # Import local : ``combat.fin`` est un module bas niveau ; on le tire à l'appel pour ne créer
    # aucun cycle à l'import de ``effets.outils`` par ``pbm_game`` (même motif que ``effets.objets``
    # pour le DSL).
    from ..combat.fin import resoudre_kos

    if etat.terminee:
        raise ValueError("Partie terminée : aucun Outil n'est retiré (R-14.6).")
    params = action.params
    prop = params.get("proprietaire")
    if not isinstance(prop, str) or not prop:
        raise ValueError(
            "« proprietaire » (le joueur dont le Pokémon porte l'Outil) est requis (R-13.2)."
        )
    cible_id = params.get("cible")
    if not isinstance(cible_id, str) or not cible_id:
        raise ValueError(
            "« cible » (identité du Pokémon dont on retire l'Outil) est requise (R-3.7)."
        )

    index, joueur = _joueur(etat, prop)
    loc = _localiser(joueur, cible_id)
    if loc is None:
        raise ValueError(
            f"Aucun Pokémon de « {prop} » n'a l'identité « {cible_id} » (R-3.7)."
        )
    cible_pk = _pokemon_a(joueur, loc)
    if cible_pk.outil is None:
        raise ValueError(
            f"Le Pokémon « {cible_id} » ne porte aucun Outil à retirer (R-3.7)."
        )

    outil = cible_pk.outil
    # R-13.2 : l'Outil retiré rejoint la défausse de SON propriétaire ; l'effet cesse par
    # disparition de la source (plus aucun ``pokemon.outil`` au prochain calcul continu).
    joueur = _poser_pokemon(joueur, loc, replace(cible_pk, outil=None))
    joueur = replace(joueur, defausse=joueur.defausse + (outil,))
    etat = _remplacer_joueur(etat, index, joueur)

    evt = Evenement(
        EVT_OUTIL_RETIRE,
        {
            "joueur": prop,
            "outil": outil.instance_id,
            "ref": outil.ref,
            "cible": cible_id,
            "par": action.auteur,
        },
    )

    # R-13.1 — K.O. immédiat si les compteurs dépassent le nouveau seuil. ``fiches`` porte le PV
    # EFFECTIF post-retrait (le +PV de l'Outil a déjà disparu) : le résolveur voit donc le bon
    # seuil. Ordre déterministe : le propriétaire d'abord (c'est son Pokémon qui peut tomber).
    adversaire = _autre(etat, prop)
    etat, evts_ko = resoudre_kos(etat, params.get("fiches", {}), (prop, adversaire))
    return etat, [evt, *evts_ko]


# Enregistrement dans le REGISTRE des transitions (voir l'en-tête) : ``appliquer`` reconnaît
# désormais ``attacher_outil`` et ``retirer_outil``, journalisés et rejouables.
REGISTRE[ACTION_ATTACHER_OUTIL] = appliquer_attacher_outil
REGISTRE[ACTION_RETIRER_OUTIL] = appliquer_retirer_outil


# --- Trois Outils réels, en producteurs d'effets continus (D9 : scriptés et testés) ----------

#: Références catalogue (``tcgdex_id``) des Outils scriptés par ce lot. Protective Poncho existe
#: en **deux impressions** (``B2-147`` et ``B2-234``) : même effet, deux ``ref`` qu'un deck peut
#: porter.
PROTECTIVE_PONCHO_A = "B2-147"
PROTECTIVE_PONCHO_B = "B2-234"
METAL_CORE_BARRIER = "B2-148"

#: Valeur d'``element_type`` (catalogue) du type **Metal** — la condition de Metal Core Barrier.
_TYPE_METAL = "metal"


def _localiser_porteur(etat: EtatPartie, identite: str) -> tuple[PokemonEnJeu, bool] | None:
    """Le Pokémon d'identité stable ``identite`` et **s'il est au banc**. ``None`` s'il a quitté
    le jeu. Sert les conditions d'Outils qui dépendent de la position (Protective Poncho) ou de
    l'espèce (Metal Core Barrier) du porteur.
    """
    for joueur in etat.joueurs:
        if joueur.actif is not None and joueur.actif.cartes[0].instance_id == identite:
            return joueur.actif, False
        for pok in joueur.banc:
            if pok.cartes[0].instance_id == identite:
                return pok, True
    return None


def _source_outil(porteur: PokemonEnJeu, ref: str, libelle: str) -> SourceEffet:
    """La source lisible de l'Outil porté (journal) ; repli sur ``ref`` si l'état n'en a pas."""
    instance = porteur.outil.instance_id if porteur.outil is not None else ref
    return SourceEffet(libelle=libelle, ref=ref, instance_id=instance)


def producteur_protective_poncho(meta: dict[str, dict]) -> ProducteurContinu:
    """**Protective Poncho** (``B2-147``/``B2-234``) — **prévient tous les dégâts** au banc.

    Tant que le porteur est **au banc**, les dégâts des attaques et talents adverses qui le visent
    sont ramenés à **0** (un modificateur de défense ``fixe 0``, R-10.1 étape 5). L'effet ne vaut
    **que** au banc (la carte le dit) : quand le porteur est Actif, le producteur ne contribue
    rien — l'absence réelle d'effet, pas un silence (D9). « Prévient tous les dégâts » porte sur
    les **dégâts** (tout dégât passe par :func:`~pbm_game.combat.resolution.resoudre_degats`), pas
    sur les compteurs posés directement (« placez N compteurs », R-10.6), qui ne sont pas des
    dégâts — fidèle au texte. ``meta`` est inutilisé (la condition est positionnelle).
    """

    def _p(etat: EtatPartie, ref: str, cible: str | None) -> list[EffetContinu]:
        if cible is None:
            return []
        trouve = _localiser_porteur(etat, cible)
        if trouve is None:
            return []
        porteur, au_banc = trouve
        if not au_banc:
            return []
        return [
            EffetContinu(
                libelle="Protective Poncho : prévient tous les dégâts (porteur au banc)",
                regle="R-3.7",
                source=_source_outil(porteur, ref, "Protective Poncho"),
                portee=PORTEE_OUTIL,
                cible=cible,
                modificateur=modificateur_fixe("Protective Poncho", "R-3.7", 0),
                face=FACE_DEFENSEUR,
            )
        ]

    return _p


def producteur_metal_core_barrier(meta: dict[str, dict]) -> ProducteurContinu:
    """**Metal Core Barrier** (``B2-148``) — le Pokémon **Metal** porteur subit **−50 dégâts**.

    Un modificateur de défense ``−50`` (R-10.1 étape 5) pour le porteur, **uniquement** si son
    type (``element_type`` du catalogue) est **Metal**. La condition porte sur l'espèce : ``meta``
    doit fournir le ``type`` de chaque ``ref`` (le service l'a depuis le catalogue ; le moteur ne
    le devine pas, D9). Un porteur non-Metal ne reçoit rien — l'Outil peut être attaché, mais son
    effet de réduction ne s'applique qu'au bon type (fidèle au texte).

    La clause « se défausse à la fin du tour adverse » n'est **pas** un effet continu : le moteur
    la sert par un :func:`appliquer_retirer_outil` que le **service** émet à ce moment (il fournit
    le retrait ; le service en orchestre l'instant, comme il orchestre le Checkup) — voir
    ``docs/jeu/OUTILS.md``.
    """

    def _p(etat: EtatPartie, ref: str, cible: str | None) -> list[EffetContinu]:
        if cible is None:
            return []
        trouve = _localiser_porteur(etat, cible)
        if trouve is None:
            return []
        porteur, _au_banc = trouve
        m = meta.get(carte_active(porteur).ref)
        if m is None or str(m.get("type", "")).strip().lower() != _TYPE_METAL:
            return []
        return [
            EffetContinu(
                libelle="Metal Core Barrier : −50 dégâts (porteur Metal)",
                regle="R-3.7",
                source=_source_outil(porteur, ref, "Metal Core Barrier"),
                portee=PORTEE_OUTIL,
                cible=cible,
                modificateur=modificateur_ajout("Metal Core Barrier", "R-3.7", -50),
                face=FACE_DEFENSEUR,
            )
        ]

    return _p


def registre_outils(meta: dict[str, dict]) -> RegistreContinus:
    """Le registre des **Outils réels** de ce lot, lié à la métadonnée catalogue ``meta``.

    Prêt à fusionner dans le registre continu d'une partie
    (:attr:`~pbm_game.actions.familles_jeu.CatalogueJeu.registre_continus`) par le service, aux
    côtés des producteurs de Stades et de talents. Chaque clé est une ``ref`` réelle (D9) ; un
    Outil absent du registre ne contribue rien (l'absence réelle d'effet, pas un silence).
    """
    poncho = producteur_protective_poncho(meta)
    return {
        PROTECTIVE_PONCHO_A: poncho,
        PROTECTIVE_PONCHO_B: poncho,
        METAL_CORE_BARRIER: producteur_metal_core_barrier(meta),
    }


__all__ = [
    "ZONE_ACTIF",
    "ZONE_BANC",
    "appliquer_attacher_outil",
    "appliquer_retirer_outil",
    "PROTECTIVE_PONCHO_A",
    "PROTECTIVE_PONCHO_B",
    "METAL_CORE_BARRIER",
    "producteur_protective_poncho",
    "producteur_metal_core_barrier",
    "registre_outils",
]
