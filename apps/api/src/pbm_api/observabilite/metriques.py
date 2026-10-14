"""Lecture des **métriques du jeu** en base, et rien d'autre (la décision est dans ``regles``).

Quatre requêtes agrégées, bornées par une fenêtre de temps, qui ne rapatrient **aucune ligne de
partie** : à trois joueurs le volume est modeste, mais une métrique qui charge les parties pour les
compter devient le problème qu'elle était censée détecter.

Ce que ce module **ne fait pas**, délibérément :

* il ne compte pas les **tours** — ils ne sont stockés nulle part et il faudrait rejouer chaque
  partie pour les obtenir. On publie les **coups** journalisés, en le disant (D9 : on ne
  l'approxime pas) ;
* il ne compte pas les **déconnexions passagères** — la présence vit dans Redis (lot
  ``j-temps-reel``) et un joueur qui revient dans sa pause de grâce n'a rien cassé. Ce qu'on
  compte, c'est la déconnexion qui a **coûté la partie** : ``raison_fin = desertion`` ;
* il ne ventile rien **par compte** : la table le permet pour l'administration, l'API ne l'expose
  pas (ce serait une fuite entre joueurs).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.models import GAME_STATUS_EN_COURS, Game, GameEvent
from pbm_api.models.observabilite import (
    INCIDENT_ACTION_REFUSEE,
    INCIDENT_ERREUR_MOTEUR,
    INCIDENT_PARTIE_REFUSEE,
    JeuIncident,
)
from pbm_api.observabilite.releve import RAISON_NON_RENSEIGNEE, Releve

#: Fenêtre par défaut d'un relevé : la journée écoulée, comme la sonde quotidienne.
FENETRE_DEFAUT_H = 24
#: Fenêtre du récapitulatif hebdomadaire.
FENETRE_HEBDO_H = 24 * 7
#: Au-delà de ce silence, une partie « en cours » n'aboutit pas : c'est le signal du jalon J5
#: « des parties qui n'aboutissent pas ». Plus large que l'expiration automatique serait inutile
#: (``expirer_parties`` les clôt) ; plus court produirait du bruit (une partie reprise le soir).
SEUIL_PARTIE_BLOQUEE_H = 48


async def relever(
    db: AsyncSession,
    *,
    maintenant: datetime | None = None,
    fenetre_heures: int = FENETRE_DEFAUT_H,
    seuil_blocage_heures: int = SEUIL_PARTIE_BLOQUEE_H,
) -> Releve:
    """Le relevé des métriques du jeu sur les ``fenetre_heures`` dernières heures.

    ``maintenant`` est injectable pour que les tests fixent la fenêtre sans jouer avec l'horloge
    de la machine (les colonnes sont ``DateTime(timezone=True)``, on reste en UTC *aware* de bout
    en bout — mélanger aware et naïf casse les comparaisons SQL).

    Pour une partie finie, ``last_action_at`` est l'instant de son **dernier coup** : il sert donc
    à la fois de date de fin (fenêtre, durée) et de mesure du silence d'une partie en cours.
    """
    maintenant = maintenant or datetime.now(UTC)
    depuis = maintenant - timedelta(hours=fenetre_heures)
    silence = maintenant - timedelta(hours=seuil_blocage_heures)

    # (1) État de l'instant : parties en cours, et celles qui n'aboutissent pas.
    etat = (
        await db.execute(
            select(
                func.count().label("en_cours"),
                func.count(case((Game.last_action_at < silence, 1))).label("bloquees"),
            ).where(Game.status == GAME_STATUS_EN_COURS)
        )
    ).one()

    # (2) Flux de la fenêtre : créations d'un côté, fins de l'autre (une partie créée hier et finie
    # ce matin compte dans les deux, chacun répondant à une question différente).
    creees = (
        await db.execute(
            select(func.count()).select_from(Game).where(Game.created_at >= depuis)
        )
    ).scalar_one()

    # Regroupement sur la colonne BRUTE, le repli des valeurs nulles étant fait en Python : un
    # `coalesce` répété entre le SELECT et le GROUP BY produit deux paramètres liés distincts, et
    # Postgres refuse alors le regroupement (« must appear in the GROUP BY clause »).
    fins = (
        await db.execute(
            select(
                Game.raison_fin.label("raison"),
                func.count().label("compte"),
                func.avg(
                    func.extract("epoch", Game.last_action_at - Game.created_at) / 60.0
                ).label("duree_min"),
                func.avg(Game.current_numero).label("coups"),
            )
            .where(Game.status != GAME_STATUS_EN_COURS, Game.last_action_at >= depuis)
            .group_by(Game.raison_fin)
        )
    ).all()

    fins_par_raison = {
        (ligne.raison or RAISON_NON_RENSEIGNEE): ligne.compte for ligne in fins
    }
    parties_terminees = sum(fins_par_raison.values())
    # Moyennes pondérées par groupe : `avg` par raison puis recombinaison, pour n'avoir qu'une
    # requête. Sans partie terminée, la moyenne n'existe pas — `None`, jamais 0 (qui se lirait
    # « des parties de zéro minute »).
    duree_moyenne = None
    coups_moyens = None
    if parties_terminees:
        total_duree = sum(
            float(ligne.duree_min) * ligne.compte for ligne in fins if ligne.duree_min is not None
        )
        total_coups = sum(
            float(ligne.coups) * ligne.compte for ligne in fins if ligne.coups is not None
        )
        duree_moyenne = round(total_duree / parties_terminees, 1)
        coups_moyens = round(total_coups / parties_terminees, 1)

    # (3) Coups effectivement joués (le journal est append-only : son volume EST l'activité).
    coups_joues = (
        await db.execute(
            select(func.count()).select_from(GameEvent).where(GameEvent.created_at >= depuis)
        )
    ).scalar_one()

    # (4) Incidents de la fenêtre, par genre et par motif.
    incidents = (
        await db.execute(
            select(JeuIncident.genre, JeuIncident.motif, func.count().label("compte"))
            .where(JeuIncident.created_at >= depuis)
            .group_by(JeuIncident.genre, JeuIncident.motif)
        )
    ).all()

    refus_par_motif: dict[str, int] = {}
    erreurs_moteur = 0
    parties_refusees = 0
    for ligne in incidents:
        if ligne.genre == INCIDENT_ACTION_REFUSEE:
            refus_par_motif[ligne.motif] = refus_par_motif.get(ligne.motif, 0) + ligne.compte
        elif ligne.genre == INCIDENT_ERREUR_MOTEUR:
            erreurs_moteur += ligne.compte
        elif ligne.genre == INCIDENT_PARTIE_REFUSEE:
            parties_refusees += ligne.compte

    return Releve(
        fenetre_heures=fenetre_heures,
        parties_en_cours=etat.en_cours,
        parties_bloquees=etat.bloquees,
        parties_creees=creees,
        parties_terminees=parties_terminees,
        fins_par_raison=fins_par_raison,
        duree_moyenne_minutes=duree_moyenne,
        coups_moyens=coups_moyens,
        coups_joues=coups_joues,
        refus=sum(refus_par_motif.values()),
        refus_par_motif=refus_par_motif,
        erreurs_moteur=erreurs_moteur,
        parties_refusees=parties_refusees,
    )


__all__ = ["FENETRE_DEFAUT_H", "FENETRE_HEBDO_H", "SEUIL_PARTIE_BLOQUEE_H", "relever"]
