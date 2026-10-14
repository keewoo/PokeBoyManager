"""Réglages de **confort et d'accessibilité** d'un compte (lot ``j-accessibilite-jeu``).

Même forme que ``jeu_rendu_reglages`` et ``notification_reglages``, et pour la même raison : la
ligne n'est créée qu'à la **première modification**. Son absence vaut les défauts du code
(:class:`pbm_api.jeu.confort.ReglagesConfort`) — on n'écrit pas une ligne pour chaque compte qui
n'a jamais ouvert ces réglages, et le jeu n'a pas besoin qu'elle existe pour se jouer.

Pourquoi en base plutôt que dans le navigateur : « ne pas animer » et « texte très grand » sont des
besoins de la personne, pas de son appareil. Un enfant qui les a posés sur la tablette du salon ne
doit pas les redemander sur l'ordinateur de sa chambre. Le client en garde une copie locale, mais
seulement pour ne pas clignoter au chargement (``apps/web/src/lib/confort-provider.tsx``).
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin


class JeuConfortReglages(Base, TimestampMixin):
    """Ce qu'un compte demande pour jouer confortablement : animations, taille du texte, temps.

    ``animations`` et ``taille_texte`` sont du vocabulaire fermé, validé à l'écriture par le service
    (:mod:`pbm_api.jeu.confort_service`) : une valeur hors vocabulaire ferait silencieusement
    retomber l'écran sur le défaut, c'est-à-dire mentir au joueur sur ce qu'il a réglé.

    ``temps_rallonge`` n'est pas un réglage d'affichage : il **double les horloges** de la partie
    (DJ4), et il est lu **au lancement** d'une partie — jamais pendant, puisqu'une partie fige sa
    configuration d'horloges à sa création.
    """

    __tablename__ = "jeu_confort_reglages"

    #: Clé primaire **et** clé étrangère : un compte a au plus une ligne de réglages.
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    animations: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'completes'")
    )
    taille_texte: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'normale'")
    )
    temps_rallonge: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


__all__ = ["JeuConfortReglages"]
