"""Modèle de persistance des **incidents du jeu** (lot ``j-observabilite-jeu``).

Trois faits du jeu ne laissaient aucune trace exploitable : un coup **refusé** par le moteur, une
**erreur de moteur**, et une **partie refusée** parce qu'une carte n'est pas scriptée (D9). Les
trois n'existaient que dans la sortie du serveur (``logger``) : perdus au redémarrage, invisibles
sans ouvrir une session SSH, et impossibles à compter. Or ce sont exactement les signaux du jalon
J5 — « une règle qui casse se voit dans une métrique avant de se voir dans une plainte » — et les
joueurs sont deux ou trois : ils ne signaleront pas tout.

**Ce qui n'est pas ici l'est déjà ailleurs, et on ne le duplique pas.** Les parties en cours,
créées, terminées et leur motif de fin se lisent dans ``games`` (``status``, ``raison_fin`` — dont
``temps_ecoule`` pour une expiration d'horloge, ``desertion`` pour une déconnexion non rattrapée,
``inactivite`` pour une partie fantôme close) ; la durée dans ``created_at``/``updated_at`` ; le
nombre de coups dans ``current_numero``. :mod:`pbm_api.observabilite.metriques` les agrège.

``game_id`` et ``user_id`` sont en **SET NULL**, délibérément : la purge des parties mortes
(:func:`pbm_api.games.service.purger`) ne doit pas effacer la trace de supervision qui sert
justement à expliquer un incident. On perd le lien vers la partie, jamais le fait.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base

# --- Genres d'incident (vocabulaire fermé, lu par les métriques et les règles d'alerte) -------
#: Le moteur a refusé un coup (règle non tenue). Le ``motif`` porte la règle citée (``R-x.y``).
INCIDENT_ACTION_REFUSEE = "action_refusee"
#: Le moteur a levé une exception inattendue : un **bug**, jamais un coup illégal. Toujours une
#: alerte, jamais une simple ligne de journal (critère d'acceptation du lot).
INCIDENT_ERREUR_MOTEUR = "erreur_moteur"
#: Une partie a été refusée à la création parce qu'un deck porte une carte non scriptée (D9) :
#: un joueur n'a pas pu jouer. C'est le signal « couverture des cartes insuffisante ».
INCIDENT_PARTIE_REFUSEE = "partie_refusee"

#: L'ensemble des genres reconnus. Un genre hors de cet ensemble est un bug, jamais écrit.
INCIDENT_GENRES: frozenset[str] = frozenset(
    {INCIDENT_ACTION_REFUSEE, INCIDENT_ERREUR_MOTEUR, INCIDENT_PARTIE_REFUSEE}
)


class JeuIncident(Base):
    """Un incident du jeu, horodaté — *append-only*, et volontairement **borné**.

    Ne porte pas de ``TimestampMixin`` : un incident ne se met jamais à jour (il s'est produit).

    ``motif`` appartient à un vocabulaire fermé et borné (:mod:`pbm_api.observabilite.motifs`) :
    c'est lui qu'on agrège, et c'est ce qui garantit qu'aucune donnée d'utilisateur ne finit dans
    une clé de métrique. ``detail`` porte le message d'origine **tronqué**, pour le diagnostic ;
    il n'est jamais renvoyé par l'API de métriques (agrégats seulement).
    """

    __tablename__ = "jeu_incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    genre: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    motif: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    game_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("games.id", ondelete="SET NULL"), nullable=True
    )
    # Quel compte a déclenché l'incident — gardé pour le diagnostic d'une rafale de refus (bug
    # d'interface d'un côté, client modifié de l'autre). Jamais exposé par l'API : la ventilation
    # par compte serait une fuite entre joueurs, elle se lit en SQL par l'administration.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    type_action: Mapped[str | None] = mapped_column(String(48), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
