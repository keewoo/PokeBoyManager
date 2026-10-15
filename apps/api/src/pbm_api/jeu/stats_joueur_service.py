"""Mes parties, côté base : ce qu'on lit pour l'historique et les agrégats (lot `j-stats-joueur`).

La seule couche du lot qui touche la base. Le calcul est dans :mod:`pbm_api.jeu.stats_joueur`
(pur), la route dans :mod:`pbm_api.routers.stats_joueur`.

**Une requête, pas une par ligne.** Tout part de ``game_result_players`` filtrée sur ``user_id``,
jointe à ``game_results`` (le genre de partie et sa raison de fin), et en jointure *externe* au
deck joué et au compte adverse — pour le nom et le pseudo. Les deux jointures externes sont
volontaires : un deck supprimé laisse ``deck_id`` à nul (``ON DELETE SET NULL``) et l'historique
doit rester lisible. Un ``INNER JOIN`` y perdrait les parties d'un deck effacé, silencieusement.

**Pourquoi ``player_stats`` n'est pas lu.** Ce cache dit déjà les totaux, mais il peut être en
retard (son recalcul est reporté quand l'écriture de la trace échoue, `docs/jeu/FIN-COMPTE.md`).
Afficher le cache au-dessus de l'historique exposerait à montrer un total qui contredit la liste
juste en dessous, sans que personne sache lequel croire. Les totaux sont donc recalculés depuis les
mêmes lignes que la liste : les deux ne *peuvent pas* divergir.

**Le lien vers le replay dit la vérité.** La purge supprime les parties mortes de plus de trente
jours, pas leur trace (volontairement sans clé étrangère). Une ligne d'historique peut donc n'avoir
plus de replay : ``replay_disponible`` le dit en rendant la liste, à partir de l'existence réelle de
la partie — plutôt que de proposer un lien qui répondrait 404.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from pbm_api.jeu.stats_joueur import PartieJouee, Statistiques, calculer
from pbm_api.models import Deck, Game, GameResult, GameResultPlayer, User
from pbm_api.models.fin_compte import RESULTATS

#: Nombre de parties rendues par défaut sur une page d'historique. Vingt : de quoi remplir un écran
#: sans faire descendre, et de quoi mesurer le critère « cent parties en moins d'une seconde » en
#: cinq pages.
PAGE_DEFAUT = 20

#: Plafond d'une page. Cent, exactement le volume du critère d'acceptation du lot : une page plus
#: large n'a jamais été mesurée, donc elle n'est pas promise.
PAGE_MAX = 100


@dataclass(frozen=True)
class LignePartie:
    """Une ligne d'historique : la partie, ce qu'elle a donné, et si son replay existe encore.

    ``raison_fin`` est le code du moteur (``abandon``, ``temps_ecoule``, ``derniere_recompense``…),
    rendu brut : l'écran a déjà son registre de libellés (``apps/web/src/lib/game/fin.ts``), et le
    traduire ici en ferait un second, qui divergerait.
    """

    partie: PartieJouee
    raison_fin: str | None
    #: Vrai quand la partie existe encore : son replay est alors consultable. Faux après la purge.
    replay_disponible: bool


@dataclass(frozen=True)
class Historique:
    """Une page d'historique, et le total pour que l'écran sache combien il en reste."""

    lignes: tuple[LignePartie, ...]
    total: int


def _colonnes() -> Select:
    """La requête commune à l'historique et aux agrégats — une seule définition des jointures.

    L'écrire deux fois serait le plus sûr moyen qu'un filtre (``user_id``, en particulier) finisse
    par manquer d'un côté. ``GameResult`` est joint en interne : les deux lignes sont écrites dans
    la même transaction par ``enregistrer_fin_si_due``, une trace de joueur sans son résultat de
    partie serait un bug, pas un cas à rattraper ici.
    """
    adversaire = aliased(User)
    return (
        select(
            GameResultPlayer.game_id,
            GameResultPlayer.finie_a,
            GameResultPlayer.resultat,
            GameResultPlayer.comptabilisee,
            GameResultPlayer.deck_id,
            GameResultPlayer.adversaire_user_id,
            GameResultPlayer.adversaire_bot,
            GameResultPlayer.duree_s,
            GameResultPlayer.degats_infliges,
            GameResultPlayer.kos_infliges,
            GameResultPlayer.recompenses_prises,
            GameResultPlayer.cartes_jouees,
            GameResultPlayer.energies_attachees,
            GameResultPlayer.coups_joues,
            GameResult.entrainement,
            GameResult.raison_fin,
            Deck.name.label("deck_nom"),
            adversaire.pseudo.label("adversaire_pseudo"),
            Game.id.label("partie_encore_la"),
        )
        .join(GameResult, GameResult.game_id == GameResultPlayer.game_id)
        .outerjoin(Deck, Deck.id == GameResultPlayer.deck_id)
        .outerjoin(adversaire, adversaire.id == GameResultPlayer.adversaire_user_id)
        # Jointure externe sur la partie elle-même : purgée, la ligne reste, sans replay.
        .outerjoin(Game, Game.id == GameResultPlayer.game_id)
    )


def _ligne(rang) -> LignePartie:
    """Traduit une ligne de résultat SQL en :class:`LignePartie` (une seule fois, ici)."""
    return LignePartie(
        partie=PartieJouee(
            game_id=rang.game_id,
            finie_a=rang.finie_a,
            resultat=rang.resultat,
            comptabilisee=rang.comptabilisee,
            entrainement=rang.entrainement,
            deck_id=rang.deck_id,
            deck_nom=rang.deck_nom,
            adversaire_user_id=rang.adversaire_user_id,
            adversaire_pseudo=rang.adversaire_pseudo,
            adversaire_bot=rang.adversaire_bot,
            duree_s=rang.duree_s,
            degats_infliges=rang.degats_infliges,
            kos_infliges=rang.kos_infliges,
            recompenses_prises=rang.recompenses_prises,
            cartes_jouees=rang.cartes_jouees,
            energies_attachees=rang.energies_attachees,
            coups_joues=rang.coups_joues,
        ),
        raison_fin=rang.raison_fin,
        replay_disponible=rang.partie_encore_la is not None,
    )


@dataclass(frozen=True)
class Filtres:
    """Les filtres de l'historique. Tous facultatifs, tous combinables, tous validés par la route.

    ``entrainement`` à ``None`` veut dire « les deux » : c'est le défaut, parce que masquer
    l'entraînement par défaut ferait croire à un historique amputé (« où sont mes parties contre le
    bot ? »). À ``True``, seules les parties d'entraînement ; à ``False``, seules les vraies.
    """

    resultat: str | None = None
    deck_id: uuid.UUID | None = None
    adversaire_user_id: uuid.UUID | None = None
    entrainement: bool | None = None


def _appliquer(requete: Select, *, user_id: uuid.UUID, filtres: Filtres) -> Select:
    """Borne la requête au joueur courant, puis applique ses filtres.

    Le filtre sur ``user_id`` est posé **ici et nulle part ailleurs** : c'est l'isolation exigée
    par le dépôt (« toute route utilisateur filtre par ``user_id`` issu de la session »), et la
    mettre dans la fonction que les deux chemins partagent la rend impossible à oublier.
    """
    requete = requete.where(GameResultPlayer.user_id == user_id)
    if filtres.resultat is not None:
        requete = requete.where(GameResultPlayer.resultat == filtres.resultat)
    if filtres.deck_id is not None:
        requete = requete.where(GameResultPlayer.deck_id == filtres.deck_id)
    if filtres.adversaire_user_id is not None:
        requete = requete.where(
            GameResultPlayer.adversaire_user_id == filtres.adversaire_user_id
        )
    if filtres.entrainement is not None:
        requete = requete.where(GameResult.entrainement.is_(filtres.entrainement))
    return requete


async def charger_historique(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    filtres: Filtres | None = None,
    limite: int = PAGE_DEFAUT,
    offset: int = 0,
) -> Historique:
    """Une page d'historique, la plus récente d'abord, et le nombre total de parties filtrées.

    Deux requêtes : la page et son total. Le total est nécessaire pour que l'écran puisse dire
    « 20 sur 134 » — sans lui, un bouton « suivant » ne sait pas quand s'éteindre, et le joueur ne
    sait pas si sa liste est complète.
    """
    filtres = filtres or Filtres()
    requete = _appliquer(_colonnes(), user_id=user_id, filtres=filtres)
    rangs = (
        await db.execute(
            requete.order_by(GameResultPlayer.finie_a.desc()).limit(limite).offset(offset)
        )
    ).all()

    total_requete = _appliquer(
        select(func.count())
        .select_from(GameResultPlayer)
        .join(GameResult, GameResult.game_id == GameResultPlayer.game_id),
        user_id=user_id,
        filtres=filtres,
    )
    total = (await db.execute(total_requete)).scalar_one()
    return Historique(lignes=tuple(_ligne(rang) for rang in rangs), total=int(total))


async def charger_statistiques(
    db: AsyncSession, *, user_id: uuid.UUID, filtres: Filtres | None = None
) -> Statistiques:
    """Les agrégats d'un joueur, recalculés depuis **toutes** ses parties (pas seulement la page).

    Les agrégats ne sont pas paginés, et c'est le point : un taux de victoire calculé sur la page
    affichée changerait en faisant « suivant ». Ils portent sur l'historique complet du joueur, au
    filtre près — ce qui permet à la fiche d'un deck de demander « seulement ce deck » et d'obtenir
    exactement le même chiffre que la ligne de ce deck dans le tableau général.

    Le coût est une requête sur les lignes d'un seul compte : à cent parties, le calcul est en
    microsecondes (mesuré par ``test_cent_parties_se_calculent_en_moins_d_une_seconde``).
    """
    rangs = (
        await db.execute(_appliquer(_colonnes(), user_id=user_id, filtres=filtres or Filtres()))
    ).all()
    return calculer([_ligne(rang).partie for rang in rangs])


def resultat_valide(resultat: str) -> bool:
    """Dit si un filtre de résultat appartient au vocabulaire — la route refuse le reste en 422.

    Un résultat inconnu rendrait une liste vide, que l'écran lirait « tu n'as jamais gagné » : un
    refus explicite vaut mieux qu'un vide qui ressemble à une réponse.
    """
    return resultat in RESULTATS


__all__ = [
    "PAGE_DEFAUT",
    "PAGE_MAX",
    "Filtres",
    "Historique",
    "LignePartie",
    "charger_historique",
    "charger_statistiques",
    "resultat_valide",
]
