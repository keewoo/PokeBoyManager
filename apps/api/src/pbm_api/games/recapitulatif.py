"""Récapitulatif d'une partie finie — l'adaptateur entre le journal en base et le moteur pur.

Lot ``j-partie-fin-ui`` (jalon J4). Le calcul lui-même vit dans le moteur
(:func:`pbm_game.journal.recapitulatif.construire_recapitulatif`), qui est **pur** : il reçoit des
entrées de journal et rend des chiffres. Ce module fait le reste, et seulement le reste : il lit le
journal en base, nomme les joueurs, et compose la réponse HTTP.

**Pourquoi le serveur et pas l'écran.** L'écran *pourrait* compter depuis les coups qu'il reçoit :
le canal temps réel les rejoue tous depuis le coup 0, donc ils y sont. Mais ces coups sont
**projetés par destinataire** — chaque joueur n'en voit qu'une partie — et un récapitulatif dont
les chiffres dépendent de qui regarde n'est pas un récapitulatif. Le journal en base, lui, est
complet et autoritaire : le même récapitulatif est servi aux deux joueurs.

**Pourquoi seulement une partie finie.** Même raison que le replay (:mod:`pbm_api.games.replay`) :
le récapitulatif n'a de sens qu'à la fin, et une porte qui ne s'ouvre qu'après la fin ne peut pas
fuiter pendant. Les chiffres servis ne sont que des faits publics (dégâts annoncés, K.O.,
récompenses prises), mais on ne multiplie pas les fenêtres sur une partie en cours.

**Qui peut le voir** : les deux joueurs, et personne d'autre (404 sinon, jamais 403 — même choix
que partout ailleurs : révéler l'existence d'une partie d'autrui serait une fuite). Un compte à qui
un replay a été *ouvert* n'y a pas droit ici : il a le journal coup par coup, qui porte déjà tout ;
lui ajouter une seconde route n'apporterait rien et agrandirait la surface.
"""

from __future__ import annotations

import uuid

from pbm_game.journal.recapitulatif import construire_recapitulatif
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.games.construction import joueur_id_de
from pbm_api.games.errors import GameError
from pbm_api.games.service import _entrees_queue, _game_pour_participant
from pbm_api.models import GAME_STATUS_EN_COURS, GamePlayer, User


class RecapPartieEnCours(GameError):
    """Récapitulatif demandé sur une partie encore en cours → 409 (voir l'en-tête du module)."""


async def recapitulatif_de_partie(
    db: AsyncSession, *, game_id: uuid.UUID, user_id: uuid.UUID
) -> dict:
    """Le récapitulatif d'une partie finie, recalculé depuis son journal.

    Lève :class:`~pbm_api.games.errors.PartieIntrouvable` (404) si l'utilisateur ne joue pas cette
    partie, et :class:`RecapPartieEnCours` (409) si elle n'est pas finie.

    Le journal est lu **en entier** (une requête, bornée par ``current_numero``) : c'est ce qui
    rend le chiffre exact et insensible aux reconnexions — rien n'est compté au fil de l'eau. Aucun
    état n'est rejoué : on ne lit que les événements déjà écrits, donc le coût est celui d'une
    lecture de table, pas d'un rejeu de partie.
    """
    game = await _game_pour_participant(db, game_id, user_id)
    if game.status == GAME_STATUS_EN_COURS:
        raise RecapPartieEnCours(
            f"Partie {game_id} encore en cours : son récapitulatif s'ouvre à la fin."
        )

    sieges = list(
        (
            await db.execute(
                select(GamePlayer)
                .where(GamePlayer.game_id == game_id)
                .order_by(GamePlayer.seat)
            )
        )
        .scalars()
        .all()
    )
    entrees = await _entrees_queue(db, game.id, 0, game.current_numero)
    recap = construire_recapitulatif(entrees, [joueur_id_de(s.user_id) for s in sieges])

    pseudos = await _pseudos(db, [s.user_id for s in sieges])
    stats_par_jid = {s.joueur: s for s in recap.joueurs}

    return {
        "game_id": str(game.id),
        "statut": game.status,
        "raison_fin": game.raison_fin,
        "vainqueur_user_id": (
            str(game.vainqueur_user_id) if game.vainqueur_user_id is not None else None
        ),
        "entrainement": game.entrainement,
        "coups": recap.coups,
        "tours": recap.tours,
        "debut": recap.debut,
        "fin": recap.fin,
        "duree_s": recap.duree_s,
        "joueurs": [
            {
                "seat": s.seat,
                "user_id": str(s.user_id),
                "pseudo": pseudos.get(s.user_id),
                "degats_infliges": stats.degats_infliges,
                "kos_infliges": stats.kos_infliges,
                "recompenses_prises": stats.recompenses_prises,
                "cartes_jouees": stats.cartes_jouees,
                "energies_attachees": stats.energies_attachees,
                "coups_joues": stats.coups_joues,
            }
            for s, stats in (
                (s, stats_par_jid[joueur_id_de(s.user_id)]) for s in sieges
            )
        ],
        "meilleur_coup": (
            None
            if recap.meilleur_coup is None
            else {
                "numero": recap.meilleur_coup.numero,
                # Rendu en identifiant de **compte** : l'écran ne connaît que ceux-là (il compare
                # au joueur connecté). L'identifiant moteur ne sort pas d'ici.
                "user_id": _user_id_du_jid(sieges, recap.meilleur_coup.joueur),
                "degats": recap.meilleur_coup.degats,
                "ko": recap.meilleur_coup.ko,
            }
        ),
    }


def _user_id_du_jid(sieges: list[GamePlayer], joueur_id: str) -> str | None:
    """L'identifiant de compte derrière un identifiant moteur, ou ``None`` s'il n'est pas assis.

    ``None`` ne devrait pas arriver (le récapitulatif n'attribue qu'aux joueurs qu'on lui a
    donnés) ; s'il arrivait, l'écran affichera le meilleur coup sans l'attribuer plutôt que de
    l'attribuer au mauvais joueur.
    """
    for siege in sieges:
        if joueur_id_de(siege.user_id) == joueur_id:
            return str(siege.user_id)
    return None


async def _pseudos(db: AsyncSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, str | None]:
    """Les pseudos des comptes donnés, pour nommer les joueurs à l'écran (une requête)."""
    if not user_ids:
        return {}
    rows = await db.execute(select(User.id, User.pseudo).where(User.id.in_(user_ids)))
    return {uid: pseudo for uid, pseudo in rows.all()}


__all__ = ["RecapPartieEnCours", "recapitulatif_de_partie"]
