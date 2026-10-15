"""Le classement privé, côté base : ce qu'on lit, et pour qui (lot `j-classement-prive`, DJ6).

La seule couche de ce lot qui touche la base. Le calcul est dans :mod:`pbm_api.jeu.classement`
(pur), le réglage d'activation dans :mod:`pbm_api.jeu.reglages`, la route dans
:mod:`pbm_api.routers.classement`.

**Une seule table lue** : ``game_result_players``, jointe à ``users`` pour le pseudo et pour
l'appartenance aux comptes invités. Pas de jointure à ``games`` — une partie de plus d'un mois a été
purgée, son résultat non (voir `docs/jeu/FIN-COMPTE.md`). C'est exactement l'usage que
`j-fin-effets-compte` avait prévu : « un ``GROUP BY`` suffit, sans jointure à une partie peut-être
purgée ».

**Qui figure au tableau.** Les **comptes invités** (``users.game_access``, D11) ayant au moins une
partie comptabilisée, plus le demandeur lui-même — à zéro s'il n'a encore rien joué, pour qu'il ne
soit jamais absent de son propre classement. Un compte sans accès au jeu n'y figure pas, ce qui
exclut du même coup le compte du bot d'entraînement sans avoir à le nommer.

⚠️ **Ce que le tableau révèle, et pourquoi c'est un réglage.** Il nomme les comptes invités qui ont
joué. C'est la raison d'être d'un classement, mais cela va plus loin que le reste du jeu : les
invitations refusent déjà de dire si un pseudo donné appartient à un compte invité (« révéler qu'un
pseudo donné fait partie des comptes invités serait une fuite sur un jeu délibérément privé »,
:mod:`pbm_api.games.invitations`). Les deux tiennent ensemble parce que le classement est **éteint
par défaut** : c'est JF qui décide de montrer la table de famille, et personne d'autre. Détail :
`docs/jeu/CLASSEMENT.md`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.jeu.classement import (
    Bareme,
    Classement,
    PartieClassante,
    bareme,
    calculer,
)
from pbm_api.jeu.reglages import (
    CLE_CLASSEMENT_ACTIF,
    CLE_CLASSEMENT_BAREME,
    est_actif,
)
from pbm_api.jeu.reglages_service import lire
from pbm_api.models import GameResultPlayer, User

#: Largeur par défaut de la fenêtre « récent » (l'« évolution dans le temps » du plan), en jours.
#: Trente jours : assez long pour qu'une semaine sans jouer ne remette pas tout à zéro, assez court
#: pour que « ce mois-ci » veuille encore dire quelque chose.
FENETRE_RECENTE_JOURS_DEFAUT = 30

#: Bornes acceptées pour la fenêtre demandée par l'écran. Un jour au minimum (une fenêtre nulle ne
#: dirait rien), un an au maximum (au-delà, c'est le classement complet qu'on regarde).
FENETRE_RECENTE_JOURS_MIN = 1
FENETRE_RECENTE_JOURS_MAX = 365


@dataclass(frozen=True)
class VueClassement:
    """Ce que le serveur rend : le tableau, son barème, et s'il est seulement actif.

    ``actif`` à faux n'est **pas** une erreur : c'est l'état par défaut du produit (DJ6). Les lignes
    sont alors vides et *rien n'a été lu* — l'historique n'est pas touché quand le classement est
    éteint. L'écran peut ainsi masquer l'entrée de menu sans avoir à deviner le sens d'un 404.

    ``fenetre_jours`` est rendue avec le reste pour que l'écran puisse écrire « ces 30 derniers
    jours » sans recoder la valeur par défaut de son côté.
    """

    actif: bool
    classement: Classement
    fenetre_jours: int


async def _parties_des_comptes_invites(db: AsyncSession) -> list[PartieClassante]:
    """Toutes les parties **comptabilisées** des comptes invités, sans ordre particulier.

    Filtrer sur ``comptabilisee`` est tout ce qui distingue ce qui compte de ce qui ne compte pas :
    l'entraînement contre le bot et les parties expirées sont faux de ce champ, posé une fois pour
    toutes par `j-fin-effets-compte`. Dupliquer le raisonnement ici (en excluant par exemple la
    raison de fin) ferait exister deux définitions de « ça compte » qui finiraient par se
    contredire.

    Aucun tri : :func:`pbm_api.jeu.classement.calculer` n'en a pas besoin (une somme ignore
    l'ordre), et ne pas en demander à la base économise un tri sur toute la table.
    """
    lignes = (
        await db.execute(
            select(
                GameResultPlayer.user_id,
                GameResultPlayer.resultat,
                GameResultPlayer.finie_a,
            )
            .join(User, User.id == GameResultPlayer.user_id)
            .where(
                GameResultPlayer.comptabilisee.is_(True),
                User.game_access.is_(True),
            )
        )
    ).all()
    return [
        PartieClassante(
            user_id=user_id,
            resultat=resultat,
            # La requête ne rapporte que des lignes comptabilisées : le champ est redit ici pour que
            # la fonction pure reste seule juge, sans supposer ce que l'appelant a filtré.
            comptabilisee=True,
            finie_a=finie_a,
        )
        for user_id, resultat, finie_a in lignes
    ]


async def _pseudos_des_comptes_invites(db: AsyncSession) -> dict[uuid.UUID, str | None]:
    """Le pseudo de chaque compte invité — une requête, pas une par ligne du tableau."""
    lignes = (
        await db.execute(select(User.id, User.pseudo).where(User.game_access.is_(True)))
    ).all()
    return {identifiant: pseudo for identifiant, pseudo in lignes}


def _borne_recente(fenetre_jours: int, maintenant: datetime | None = None) -> datetime:
    """L'instant à partir duquel une partie est « récente ».

    ``maintenant`` est un paramètre pour que les tests n'aient pas à attendre : le calcul lui-même
    reste pur, c'est **ici** que vit la seule lecture d'horloge du lot.
    """
    reference = maintenant or datetime.now(UTC)
    return reference - timedelta(days=fenetre_jours)


async def bareme_actif(db: AsyncSession) -> Bareme:
    """Le barème que JF a choisi, ou celui par défaut s'il n'a rien choisi."""
    return bareme(await lire(db, CLE_CLASSEMENT_BAREME))


async def charger_classement(
    db: AsyncSession,
    *,
    demandeur_id: uuid.UUID,
    fenetre_jours: int = FENETRE_RECENTE_JOURS_DEFAUT,
    maintenant: datetime | None = None,
) -> VueClassement:
    """Le classement tel qu'il doit être rendu au demandeur — recalculé intégralement.

    Rien n'est mis en cache, rien n'est stocké : deux appels à une seconde d'intervalle refont le
    même calcul depuis l'historique. C'est la parade au risque du lot (« la première erreur devient
    définitive ») : il n'existe aucun état de classement à corriger.

    Classement **éteint** (le défaut, DJ6) : on rend une vue vide **sans lire l'historique**. Le
    réglage n'est donc pas qu'un filtre d'affichage — éteint, la donnée ne quitte pas la base.
    """
    formule = await bareme_actif(db)
    if not est_actif(await lire(db, CLE_CLASSEMENT_ACTIF)):
        return VueClassement(
            actif=False,
            classement=Classement(lignes=(), bareme=formule),
            fenetre_jours=fenetre_jours,
        )

    parties = await _parties_des_comptes_invites(db)
    pseudos = await _pseudos_des_comptes_invites(db)
    return VueClassement(
        actif=True,
        classement=calculer(
            parties,
            bareme=formule,
            pseudos=pseudos,
            # Le demandeur figure à son propre tableau même sans partie comptée : absent, il
            # croirait à une panne.
            inclure=(demandeur_id,),
            recent_depuis=_borne_recente(fenetre_jours, maintenant),
        ),
        fenetre_jours=fenetre_jours,
    )


__all__ = [
    "FENETRE_RECENTE_JOURS_DEFAUT",
    "FENETRE_RECENTE_JOURS_MAX",
    "FENETRE_RECENTE_JOURS_MIN",
    "VueClassement",
    "bareme_actif",
    "charger_classement",
]
