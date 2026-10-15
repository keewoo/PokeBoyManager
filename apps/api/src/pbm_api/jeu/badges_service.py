"""Attribuer et relire les badges : ce que la base sait, et ce qu'elle écrit une seule fois
(lot `j-profil-jeu`, jalon J4, DJ6).

La décision — *quel badge pour quels faits* — vit dans :mod:`pbm_api.jeu.badges`, qui est **pur**.
Ce module ne fait que deux choses : **rassembler les faits** d'une partie qui vient d'être close, et
**écrire** ce qui en découle sans jamais écrire deux fois.

**Où les faits sont pris, un par un.** Tous dans ``game_result_players``, la table que
`j-fin-effets-compte` a posée pour ça — sauf un, et c'est le plus intéressant :

====================================== ==========================================================
Fait                                   Sa source
====================================== ==========================================================
``comptabilisee`` / ``victoire``       ma ligne de la partie
``recompenses_perdues``                la ligne de l'**adversaire** (``recompenses_prises``)
``parties_comptabilisees``             le compte de mes lignes comptabilisées, celle-ci incluse
``deck_monotype``                      les types élémentaires des Pokémon du deck joué
``ko_en_un_coup``                      le **journal**, via le récapitulatif du moteur
====================================== ==========================================================

``ko_en_un_coup`` est passé en argument plutôt que relu ici : il vient de
:func:`pbm_game.journal.recapitulatif.construire_recapitulatif`, que la clôture a **déjà** calculé
(`pbm_api.games.fin_compte`). Le relire coûterait une seconde lecture du journal entier pour un
booléen — et surtout, deux lectures pourraient un jour diverger.

**L'attribution tourne même quand les badges sont éteints**, et c'est un choix. DJ6 les veut « en
option, activables par JF » : ce qui est optionnel, c'est **la vitrine** — le réglage
``badges_actifs`` gouverne l'affichage (:mod:`pbm_api.jeu.profil_service`). Si l'attribution
s'arrêtait aussi, le jour où JF allume les badges, tout ce qui a été joué avant serait perdu :
« K.O. en un coup » dépend du journal, purgé à trente jours, donc **irrattrapable**. On écrit donc
la trace pendant que la preuve existe, et on la montre quand JF le décide. Un badge gagné n'est pas
une fonctionnalité visible : c'est une ligne dérivée de l'historique du joueur, qui est déjà
stocké.


**Rien ici ne peut faire échouer une partie.** L'attribution est appelée dans la transaction de la
clôture, qui est elle-même hors du chemin du coup (voir
:func:`pbm_api.games.fin_compte.enregistrer_fin_si_due`) : si elle échoue, c'est la clôture entière
qui est reprise par le balayage, et l'``ON CONFLICT DO NOTHING`` rend cette reprise inoffensive.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.catalog.prize_marker import POKEMON_SUPERTYPES
from pbm_api.jeu.badges import FaitsBadges, attribuer
from pbm_api.models import (
    RESULTAT_VICTOIRE,
    Card,
    DeckCard,
    GameResultPlayer,
)
from pbm_api.models.player_badges import PlayerBadge

logger = logging.getLogger(__name__)


async def _deck_monotype(db: AsyncSession, deck_id: uuid.UUID | None) -> bool:
    """Tous les Pokémon de ce deck sont-ils du **même** type élémentaire ?

    ``False`` dès qu'il y a un doute, et les doutes sont nommés : aucun deck (``None``, deck
    supprimé depuis la partie), aucun Pokémon, ou un Pokémon dont le type est inconnu
    (``element_type IS NULL`` — cartes importées avant l'ajout de la colonne). Un deck dont on ne
    sait pas dire le type n'est pas un deck monotype : on n'attribue pas un badge sur une
    supposition (D9).

    Les Dresseurs et les Énergies sont **hors du compte** : un deck monotype Feu contient des
    Supporters et des Énergies Feu, et exiger qu'ils soient « du même type » viderait le badge de
    tout sens. Seuls les Pokémon portent un type élémentaire.
    """
    if deck_id is None:
        return False
    types = (
        (
            await db.execute(
                select(Card.element_type)
                .join(DeckCard, DeckCard.card_id == Card.id)
                .where(DeckCard.deck_id == deck_id, Card.supertype.in_(POKEMON_SUPERTYPES))
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    if len(types) != 1:
        return False
    return types[0] is not None


async def faits_de_partie(
    db: AsyncSession, *, game_id: uuid.UUID, user_id: uuid.UUID, ko_en_un_coup: bool
) -> FaitsBadges | None:
    """Les faits de cette partie pour ce joueur, ou ``None`` si sa ligne de clôture n'existe pas.

    ``None`` n'est pas une erreur : c'est le cas d'un appel sur une partie dont la clôture n'a pas
    (encore) écrit les lignes de joueurs. On ne devine alors rien.
    """
    ma_ligne = (
        await db.execute(
            select(GameResultPlayer).where(
                GameResultPlayer.game_id == game_id, GameResultPlayer.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if ma_ligne is None:
        return None

    # Les récompenses que j'ai PERDUES sont celles que l'adversaire a PRISES : c'est sa ligne qui
    # les porte. Une partie sans adversaire enregistré (cas dégradé) vaut 0 — et comme le badge
    # exige aussi la victoire, l'absence d'adversaire ne peut pas l'offrir à elle seule.
    prises_par_adverse = (
        await db.execute(
            select(func.coalesce(func.sum(GameResultPlayer.recompenses_prises), 0)).where(
                GameResultPlayer.game_id == game_id,
                GameResultPlayer.user_id != user_id,
            )
        )
    ).scalar_one()

    parties = (
        await db.execute(
            select(func.count())
            .select_from(GameResultPlayer)
            .where(
                GameResultPlayer.user_id == user_id,
                GameResultPlayer.comptabilisee.is_(True),
            )
        )
    ).scalar_one()

    return FaitsBadges(
        comptabilisee=ma_ligne.comptabilisee,
        victoire=ma_ligne.resultat == RESULTAT_VICTOIRE,
        ko_en_un_coup=ko_en_un_coup,
        recompenses_perdues=int(prises_par_adverse or 0),
        parties_comptabilisees=int(parties or 0),
        deck_monotype=await _deck_monotype(db, ma_ligne.deck_id),
    )


async def attribuer_pour_partie(
    db: AsyncSession, *, game_id: uuid.UUID, user_id: uuid.UUID, ko_en_un_coup: bool
) -> frozenset[str]:
    """Écrit les badges mérités par ce joueur dans cette partie, et rend **ceux qui sont nouveaux**.

    L'insertion est un ``INSERT … ON CONFLICT DO NOTHING … RETURNING code`` sur
    ``uq_player_badges_user_code`` : la base tranche ce qui est nouveau. C'est ce qui tient le
    critère d'acceptation (« un badge ne peut être attribué deux fois ») même quand deux clôtures
    concurrentes passent en même temps — un ``SELECT`` puis ``INSERT`` perdrait cette course.

    N'émet aucun ``commit`` : l'appelant (la clôture) décide de la transaction, pour que les badges
    et le résultat de la partie soient écrits **ensemble** ou pas du tout.
    """
    faits = await faits_de_partie(
        db, game_id=game_id, user_id=user_id, ko_en_un_coup=ko_en_un_coup
    )
    if faits is None:
        return frozenset()
    codes = attribuer(faits)
    if not codes:
        return frozenset()

    nouveaux = (
        await db.execute(
            pg_insert(PlayerBadge)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "user_id": user_id,
                        "code": code,
                        "game_id": game_id,
                    }
                    # Trié : l'ordre d'insertion devient déterministe, donc deux clôtures de la même
                    # partie ne peuvent pas s'interbloquer en prenant les lignes dans deux ordres.
                    for code in sorted(codes)
                ]
            )
            .on_conflict_do_nothing(constraint="uq_player_badges_user_code")
            .returning(PlayerBadge.code)
        )
    ).scalars().all()

    if nouveaux:
        logger.info(
            "badges attribués au joueur %s (partie %s) : %s",
            user_id,
            game_id,
            ", ".join(sorted(nouveaux)),
        )
    return frozenset(nouveaux)


async def badges_du_joueur(
    db: AsyncSession, user_id: uuid.UUID
) -> dict[str, tuple[uuid.UUID | None, object]]:
    """Les badges obtenus par ce compte : ``{code: (game_id, obtenu_a)}``.

    Rend **tout** ce que la base porte, y compris un code qui ne serait plus déclaré : c'est la
    vitrine qui filtre sur :data:`pbm_api.jeu.badges.BADGES`, pour qu'un badge retiré par JF cesse
    d'être montré sans que ses lignes soient détruites (il suffirait de le remettre).
    """
    lignes = (
        await db.execute(
            select(PlayerBadge.code, PlayerBadge.game_id, PlayerBadge.obtenu_a)
            .where(PlayerBadge.user_id == user_id)
            .order_by(PlayerBadge.obtenu_a)
        )
    ).all()
    return {code: (game_id, obtenu_a) for code, game_id, obtenu_a in lignes}


__all__ = ["attribuer_pour_partie", "badges_du_joueur", "faits_de_partie"]
