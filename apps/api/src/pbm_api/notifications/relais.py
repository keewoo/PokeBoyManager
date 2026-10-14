"""Les relais **hors application** d'une notification : e-mail, et notification web (PWA).

Deux canaux, deux statuts très différents — et c'est le point de ce module :

* **l'e-mail est branché** et ne sert qu'à l'invitation reçue (le seul genre listé par
  :data:`~pbm_api.notifications.regles.GENRES_RELAIS_EMAIL`). Il réutilise l'émetteur injectable
  de l'application (:mod:`pbm_api.email`) : en l'absence de SMTP
  configuré, c'est ``DisabledEmailSender`` qui journalise l'envoi non fait — un choix de
  configuration tracé, pas un repli muet ;
* **la notification web (PWA) n'est pas branchée**, parce que le lot `v6-pwa` n'est pas livré. La
  mission du lot dit « quand elle existe, sans en dépendre » : on respecte donc le réglage
  ``relais_push`` **dès maintenant** (il décide déjà si l'on *tenterait* un envoi) et, quand la
  décision autorise un envoi, on **dit** qu'il n'y a pas de transport — un INFO par tentative, qui
  nomme le lot manquant. Ni `pass`, ni `except`, ni `2>/dev/null` : le jour où `v6-pwa` arrive,
  brancher le transport ici est la seule chose à faire, et la trace prouve d'ici là que la décision
  était bien prise.

Pourquoi un module à part : le service de notification décide et persiste ; les transports sortent
du processus. Les séparer permet de tester les règles et la persistance sans toucher à un canal
externe, et de nommer précisément ce qui n'existe pas encore.
"""

from __future__ import annotations

import logging
import uuid

from pbm_api.config import settings
from pbm_api.email import EmailSender
from pbm_api.models import User
from pbm_api.models.notifications import NOTIF_INVITATION_RECUE

logger = logging.getLogger(__name__)

#: Sujets d'e-mail par genre. Un genre absent n'a pas de relais e-mail — et
#: :data:`~pbm_api.notifications.regles.GENRES_RELAIS_EMAIL` le garantit en amont ; cette table ne
#: fait que porter le texte.
_SUJETS = {NOTIF_INVITATION_RECUE: "Invitation à jouer sur PokeBoy"}


def _lien_jeu() -> str:
    """L'URL publique de l'espace jeu — le seul lien qu'un e-mail de notification porte.

    Jamais un lien qui agit (accepter, jouer) : un e-mail n'est pas un canal d'autorisation, et un
    jeton dans une URL d'e-mail fuite dans les journaux de tous les relais traversés.
    """
    return f"{settings.app_public_url.rstrip('/')}/jeu"


def _corps_invitation(pseudo_inviteur: str | None) -> str:
    """Le texte de l'e-mail d'invitation : qui invite, et où retrouver l'invitation.

    Le pseudo est le seul élément d'identité cité — ni e-mail, ni nom : le destinataire sait déjà
    qui joue avec lui, et un e-mail transite en clair.
    """
    nom = pseudo_inviteur or "Un joueur"
    return (
        f"{nom} vous invite à jouer une partie sur PokeBoy.\n\n"
        f"Retrouvez l'invitation dans votre espace jeu : {_lien_jeu()}\n"
    )


async def relayer_par_email(
    email_sender: EmailSender, *, destinataire: User, genre: str, donnees: dict
) -> None:
    """Envoie le relais e-mail d'une notification — appelé **seulement** si la décision l'autorise.

    Un genre sans sujet connu est un bug d'appelant : on journalise en ERROR et on n'envoie rien,
    plutôt que d'expédier un e-mail sans objet. Les règles
    (:data:`~pbm_api.notifications.regles.GENRES_RELAIS_EMAIL`) rendent ce cas impossible par
    construction ; la garde existe pour qu'il ne devienne pas possible en silence.
    """
    sujet = _SUJETS.get(genre)
    if sujet is None:
        logger.error(
            "relais e-mail demandé pour le genre « %s », qui n'a pas de sujet : rien n'est envoyé.",
            genre,
        )
        return
    await email_sender.send(
        to=destinataire.email, subject=sujet, body=_corps_invitation(donnees.get("pseudo"))
    )


async def relayer_par_push(*, destinataire_id: uuid.UUID, genre: str) -> None:
    """Relais de **notification web (PWA)** — pas de transport tant que `v6-pwa` n'est pas livré.

    La décision d'envoyer, elle, est bien prise en amont (réglage ``relais_push``, silence nocturne,
    plafonds) : ce qui manque est le service worker et l'abonnement du navigateur, c'est-à-dire le
    lot `v6-pwa`. On le **dit** à chaque tentative plutôt que de l'ignorer, pour deux raisons : la
    mission interdit tout repli silencieux, et ce journal est la mesure de ce que la PWA apportera
    le jour où elle arrivera.
    """
    logger.info(
        "notification web (PWA) non branchée — lot `v6-pwa` non livré ; genre=%s destinataire=%s "
        "(décision prise, transport absent).",
        genre,
        destinataire_id,
    )
