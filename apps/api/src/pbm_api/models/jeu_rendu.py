"""Réglages de **rendu des cartes en jeu** d'un compte (lot ``j-rendu-carte``, décision DJ5).

La promesse du produit est de jouer avec **ses** cartes — celles qu'on a photographiées, cornées,
avec leur reflet. Mais une photo personnelle est une donnée personnelle : elle part chez
l'adversaire. DJ5 tranche : montrée **par défaut**, réglable par deck, et avec un interrupteur
« ne jamais montrer mes photos » qui l'emporte sur tout le reste.

Ces trois niveaux vivent à trois endroits différents, et c'est voulu :

* le **défaut du compte** et l'interdiction globale, ici (une ligne par compte) ;
* la préférence **du deck**, sur ``decks.rendu_cartes`` (nulle = suit le compte) ;
* la **variante d'image** et la note de qualité d'un exemplaire, sur ``collection_items``.

Comme pour ``notification_reglages`` (lot ``j-notifications-jeu``), la ligne n'est créée qu'à la
première modification : son absence vaut les défauts de :mod:`pbm_api.jeu.rendu`, ce qui évite
d'écrire une ligne pour chaque compte qui n'a jamais ouvert ces réglages.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin


class JeuRenduReglages(Base, TimestampMixin):
    """Ce qu'un compte montre de ses cartes en jeu : son rendu par défaut, et son veto.

    ``rendu_defaut`` est le rendu appliqué aux decks qui n'ont rien choisi : ``"photo"`` (défaut
    DJ5) ou ``"officielle"``. Le vocabulaire est validé à l'écriture par l'API
    (:mod:`pbm_api.routers.jeu_rendu`) — une valeur hors vocabulaire ferait silencieusement replier
    tout le rendu sur l'officielle, c'est-à-dire mentir au joueur sur ce qu'il montre.

    ``jamais_montrer_mes_photos`` est un **veto**, pas une préférence : il l'emporte sur le réglage
    du deck comme sur le défaut du compte, et ne s'applique qu'au **regard de l'adversaire** — son
    propriétaire continue de voir ses propres photos (les lui cacher serait punir qui se protège).
    """

    __tablename__ = "jeu_rendu_reglages"

    #: Clé primaire **et** clé étrangère : un compte a au plus une ligne de réglages.
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    rendu_defaut: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'photo'")
    )
    jamais_montrer_mes_photos: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


__all__ = ["JeuRenduReglages"]
