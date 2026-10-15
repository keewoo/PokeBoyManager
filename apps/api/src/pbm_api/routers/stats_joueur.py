"""Routes de **Mes parties** — historique et statistiques (lot `j-stats-joueur`, jalon J4).

Deux routes, en lecture seule :

* ``GET /jeu/mes-parties`` — l'historique filtrable et paginé, une ligne par partie jouée ;
* ``GET /jeu/mes-statistiques`` — les agrégats (totaux, par deck, par adversaire), non paginés.

Comme toute route du jeu, elles sont gardées par
:func:`~pbm_api.auth.dependencies.require_game_access` (D11) : un compte sans accès au jeu reçoit un
**404**, pas un 403. Et elles ne lisent que l'historique du compte de la session : il n'existe aucun
paramètre permettant de demander les parties de quelqu'un d'autre — l'isolation n'est pas un filtre
qu'on pense à mettre, c'est la seule forme que la requête sait prendre
(:func:`pbm_api.jeu.stats_joueur_service._appliquer`).

**Il n'y a pas de route d'écriture**, et il n'y en aura pas : rien n'est stocké. Les agrégats sont
recalculés à chaque appel depuis ``game_result_players``, comme le classement privé. Le « reset de
mes statistiques » n'existe donc pas non plus — effacer son historique, c'est supprimer son compte
(qui emporte bien ses lignes, ``ON DELETE CASCADE``).

**Le seuil de significativité traverse la sortie HTTP.** Chaque taux rendu porte ``significatif``
et ``parties_manquantes`` : le serveur ne laisse jamais un client décider seul si « 100 % de
victoires » mérite d'être affiché en grand. C'est la parade au risque nommé du lot, et elle vit du
côté qui calcule.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pbm_api.auth.dependencies import require_game_access
from pbm_api.db import get_session
from pbm_api.jeu.stats_joueur import (
    SEUIL_SIGNIFICATIVITE,
    AgregatAdversaire,
    AgregatDeck,
    Chiffres,
    Statistiques,
    Taux,
)
from pbm_api.jeu.stats_joueur_service import (
    PAGE_DEFAUT,
    PAGE_MAX,
    Filtres,
    Historique,
    LignePartie,
    charger_historique,
    charger_statistiques,
    resultat_valide,
)
from pbm_api.models import User

router = APIRouter(prefix="/jeu", tags=["jeu-stats"])


class TauxOut(BaseModel):
    """Un bilan et **ce qu'il vaut** — jamais un pourcentage nu.

    ``pourcentage`` est nul sans aucune partie (zéro pour cent se lirait « il perd toujours »), et
    ``significatif`` est faux en dessous de :data:`~pbm_api.jeu.stats_joueur.SEUIL_SIGNIFICATIVITE`
    parties. ``parties_manquantes`` dit combien il en faut encore : l'écran peut alors écrire
    « encore 2 parties pour que ce taux veuille dire quelque chose » plutôt qu'un avertissement
    générique.
    """

    parties: int
    victoires: int
    defaites: int
    egalites: int
    pourcentage: int | None
    significatif: bool
    parties_manquantes: int

    @classmethod
    def de(cls, taux: Taux) -> TauxOut:
        """Traduit un taux calculé en sortie HTTP."""
        return cls(
            parties=taux.parties,
            victoires=taux.victoires,
            defaites=taux.defaites,
            egalites=taux.egalites,
            pourcentage=taux.pourcentage,
            significatif=taux.significatif,
            parties_manquantes=taux.parties_manquantes,
        )


class ChiffresOut(BaseModel):
    """Les six compteurs du récapitulatif, cumulés, plus deux moyennes par partie."""

    parties: int
    degats_infliges: int
    kos_infliges: int
    recompenses_prises: int
    cartes_jouees: int
    energies_attachees: int
    coups_joues: int
    degats_par_partie: float | None
    coups_par_partie: float | None

    @classmethod
    def de(cls, chiffres: Chiffres) -> ChiffresOut:
        """Traduit les chiffres cumulés en sortie HTTP (les moyennes sont des propriétés)."""
        return cls(
            parties=chiffres.parties,
            degats_infliges=chiffres.degats_infliges,
            kos_infliges=chiffres.kos_infliges,
            recompenses_prises=chiffres.recompenses_prises,
            cartes_jouees=chiffres.cartes_jouees,
            energies_attachees=chiffres.energies_attachees,
            coups_joues=chiffres.coups_joues,
            degats_par_partie=chiffres.degats_par_partie,
            coups_par_partie=chiffres.coups_par_partie,
        )


class AdversaireOut(BaseModel):
    """Mon bilan face à un adversaire.

    ``user_id`` **est** rendu ici, contrairement au classement privé : il sert à filtrer
    l'historique (« montre-moi mes parties contre lui »), et il désigne un compte que le joueur a
    déjà affronté — donc qu'il connaît. La ligne du bot n'en a pas (``null``) : toutes les parties
    d'entraînement sont regroupées, le compte technique du bot n'a pas à transparaître.
    """

    user_id: uuid.UUID | None
    pseudo: str | None
    bot: bool
    taux: TauxOut
    derniere_partie_a: datetime | None

    @classmethod
    def de(cls, agregat: AgregatAdversaire) -> AdversaireOut:
        """Traduit un agrégat d'adversaire en sortie HTTP."""
        return cls(
            user_id=agregat.user_id,
            pseudo=agregat.pseudo,
            bot=agregat.bot,
            taux=TauxOut.de(agregat.taux),
            derniere_partie_a=agregat.derniere_partie_a,
        )


class DeckStatsOut(BaseModel):
    """Ce qu'un deck a produit, et contre qui.

    ``deck_id`` nul regroupe les parties dont le deck a été supprimé depuis : elles comptent
    toujours (le résultat d'une partie ne s'efface pas avec son deck), et l'écran les nomme
    « deck supprimé » au lieu de les fondre dans un autre.
    """

    deck_id: uuid.UUID | None
    deck_nom: str | None
    taux: TauxOut
    chiffres: ChiffresOut
    duree_moyenne_s: int | None
    derniere_partie_a: datetime | None
    adversaires: list[AdversaireOut]

    @classmethod
    def de(cls, agregat: AgregatDeck) -> DeckStatsOut:
        """Traduit un agrégat de deck (et ses adversaires) en sortie HTTP."""
        return cls(
            deck_id=agregat.deck_id,
            deck_nom=agregat.deck_nom,
            taux=TauxOut.de(agregat.taux),
            chiffres=ChiffresOut.de(agregat.chiffres),
            duree_moyenne_s=agregat.duree_moyenne_s,
            derniere_partie_a=agregat.derniere_partie_a,
            adversaires=[AdversaireOut.de(a) for a in agregat.adversaires],
        )


class TotauxOut(BaseModel):
    """Les totaux d'un compte, recalculés à la lecture (jamais le cache ``player_stats``)."""

    taux: TauxOut
    serie_en_cours: int
    meilleure_serie: int
    temps_jeu_s: int
    parties_entrainement: int
    temps_jeu_entrainement_s: int
    premiere_partie_a: datetime | None
    derniere_partie_a: datetime | None


class StatistiquesOut(BaseModel):
    """Tout ce que la page affiche au-dessus de la liste, plus le seuil qui la gouverne.

    ``seuil_significativite`` est rendu pour que l'écran écrive la règle au lieu de la recoder :
    si JF la change un jour, la phrase affichée suit sans retoucher le front.
    """

    seuil_significativite: int
    totaux: TotauxOut
    chiffres: ChiffresOut
    par_deck: list[DeckStatsOut]
    par_adversaire: list[AdversaireOut]

    @classmethod
    def de(cls, stats: Statistiques) -> StatistiquesOut:
        """Traduit les agrégats calculés en sortie HTTP."""
        totaux = stats.totaux
        return cls(
            seuil_significativite=SEUIL_SIGNIFICATIVITE,
            totaux=TotauxOut(
                taux=TauxOut.de(totaux.taux),
                serie_en_cours=totaux.serie_en_cours,
                meilleure_serie=totaux.meilleure_serie,
                temps_jeu_s=totaux.temps_jeu_s,
                parties_entrainement=totaux.parties_entrainement,
                temps_jeu_entrainement_s=totaux.temps_jeu_entrainement_s,
                premiere_partie_a=totaux.premiere_partie_a,
                derniere_partie_a=totaux.derniere_partie_a,
            ),
            chiffres=ChiffresOut.de(stats.chiffres),
            par_deck=[DeckStatsOut.de(d) for d in stats.par_deck],
            par_adversaire=[AdversaireOut.de(a) for a in stats.par_adversaire],
        )


class PartieOut(BaseModel):
    """Une ligne d'historique : de quoi la lire, et de quoi y retourner.

    ``replay_disponible`` est faux quand la partie a été purgée : l'écran n'affiche alors pas de
    lien plutôt que d'en proposer un qui répondrait 404 (`docs/jeu/FIN-COMPTE.md`).

    ``comptabilisee`` est rendu parce qu'une ligne qui ne compte pas doit le **dire** : une partie
    d'entraînement ou expirée figure dans l'historique sans entrer dans les taux, et un joueur qui
    compte ses victoires à la main doit comprendre l'écart sans avoir à le deviner.
    """

    game_id: uuid.UUID
    finie_a: datetime
    resultat: str
    raison_fin: str | None
    comptabilisee: bool
    entrainement: bool
    deck_id: uuid.UUID | None
    deck_nom: str | None
    adversaire_user_id: uuid.UUID | None
    adversaire_pseudo: str | None
    adversaire_bot: bool
    duree_s: int | None
    replay_disponible: bool

    @classmethod
    def de(cls, ligne: LignePartie) -> PartieOut:
        """Traduit une ligne d'historique en sortie HTTP."""
        partie = ligne.partie
        return cls(
            game_id=partie.game_id,
            finie_a=partie.finie_a,
            resultat=partie.resultat,
            raison_fin=ligne.raison_fin,
            comptabilisee=partie.comptabilisee,
            entrainement=partie.entrainement,
            deck_id=partie.deck_id,
            deck_nom=partie.deck_nom,
            adversaire_user_id=partie.adversaire_user_id,
            adversaire_pseudo=partie.adversaire_pseudo,
            adversaire_bot=partie.adversaire_bot,
            duree_s=partie.duree_s,
            replay_disponible=ligne.replay_disponible,
        )


class HistoriqueOut(BaseModel):
    """Une page d'historique et son total — pour que l'écran sache ce qu'il n'affiche pas."""

    total: int
    limite: int
    offset: int
    parties: list[PartieOut]

    @classmethod
    def de(cls, historique: Historique, *, limite: int, offset: int) -> HistoriqueOut:
        """Traduit une page d'historique en sortie HTTP."""
        return cls(
            total=historique.total,
            limite=limite,
            offset=offset,
            parties=[PartieOut.de(ligne) for ligne in historique.lignes],
        )


def _filtres(
    resultat: str | None,
    deck_id: uuid.UUID | None,
    adversaire_user_id: uuid.UUID | None,
    entrainement: bool | None,
) -> Filtres:
    """Valide les filtres reçus et les assemble — un vocabulaire inconnu est **refusé**.

    Un ``resultat=gagné`` rendrait une liste vide, que l'écran lirait « tu n'as jamais gagné » :
    c'est un repli silencieux, donc interdit. 422 et le vocabulaire attendu dans le message.
    """
    if resultat is not None and not resultat_valide(resultat):
        # 422 en clair : le nom du constant `HTTP_422_*` a changé entre versions de Starlette
        # (ENTITY → CONTENT) ; le code numérique, lui, est stable et sans avertissement — même
        # choix que `pbm_api.routers.games`.
        raise HTTPException(422, "Résultat inconnu : attendu victoire, defaite ou egalite.")
    return Filtres(
        resultat=resultat,
        deck_id=deck_id,
        adversaire_user_id=adversaire_user_id,
        entrainement=entrainement,
    )


@router.get("/mes-parties", response_model=HistoriqueOut)
async def get_mes_parties(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    limite: Annotated[int, Query(ge=1, le=PAGE_MAX)] = PAGE_DEFAUT,
    offset: Annotated[int, Query(ge=0)] = 0,
    resultat: str | None = None,
    deck_id: uuid.UUID | None = None,
    adversaire_user_id: uuid.UUID | None = None,
    entrainement: bool | None = None,
) -> HistoriqueOut:
    """Mes parties closes, la plus récente d'abord — **les miennes seulement**.

    Filtrable par résultat, deck, adversaire et genre de partie (entraînement ou non). Aucun
    paramètre ne désigne un autre compte : l'historique rendu est celui de la session, et c'est
    pourquoi un identifiant de partie d'un autre joueur n'apparaît jamais ici (vérifié par
    ``test_je_ne_vois_pas_les_parties_d_un_autre_compte``).
    """
    filtres = _filtres(resultat, deck_id, adversaire_user_id, entrainement)
    historique = await charger_historique(
        db, user_id=current_user.id, filtres=filtres, limite=limite, offset=offset
    )
    return HistoriqueOut.de(historique, limite=limite, offset=offset)


@router.get("/mes-statistiques", response_model=StatistiquesOut)
async def get_mes_statistiques(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_game_access)],
    deck_id: uuid.UUID | None = None,
    adversaire_user_id: uuid.UUID | None = None,
    entrainement: bool | None = None,
) -> StatistiquesOut:
    """Mes agrégats, recalculés depuis tout mon historique (jamais depuis la page affichée).

    ``deck_id`` permet à la fiche d'un deck de ne demander que ce qui la concerne et d'obtenir
    exactement le chiffre que porte sa ligne dans le tableau général — un seul calcul, deux
    écrans, aucune divergence possible.
    """
    filtres = _filtres(None, deck_id, adversaire_user_id, entrainement)
    stats = await charger_statistiques(db, user_id=current_user.id, filtres=filtres)
    return StatistiquesOut.de(stats)


__all__ = ["router"]
