"""Réglage d'**emotes en jeu** d'un compte (lot ``j-echanges-emotes``, décision DJ10).

Une seule colonne, et c'est tout ce qu'il faut : *est-ce que j'échange des emotes ?* Le reste —
le catalogue, le débit, la diffusion — ne se stocke pas, parce que **rien d'une emote ne survit à
la partie** (critère du lot). Ce qui se mémorise, c'est le **choix du joueur** : « couper les
emotes » doit valoir pour la prochaine partie aussi, sinon ce n'est pas un réglage, c'est un geste
à refaire à chaque fois.

Comme ``jeu_rendu_reglages`` (lot ``j-rendu-carte``) et ``notification_reglages`` (lot
``j-notifications-jeu``), la ligne n'est créée qu'à la **première modification** : son absence vaut
les défauts de :class:`pbm_api.games.emotes.ReglagesEmotes`, ce qui évite d'écrire une ligne pour
chaque compte qui n'a jamais touché à ce réglage.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin


class JeuEmoteReglages(Base, TimestampMixin):
    """Est-ce que ce compte échange des emotes en partie ? Un interrupteur, les deux sens.

    ``recevoir_emotes`` à faux coupe la réception **et** l'envoi : le serveur ne délivre plus
    d'emote à ce joueur, et refuse celles qu'il tenterait d'envoyer (:data:`
    pbm_api.games.emotes.ERREUR_COUPEES`). Le sens exact, et pourquoi un seul interrupteur plutôt
    que deux, sont documentés sur :class:`pbm_api.games.emotes.ReglagesEmotes`.

    ⚠️ Le défaut (``true``) doit rester d'accord avec celui de la vue pure — un test le vérifie.
    """

    __tablename__ = "jeu_emote_reglages"

    #: Clé primaire **et** clé étrangère : un compte a au plus une ligne de réglage.
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    recevoir_emotes: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


__all__ = ["JeuEmoteReglages"]
