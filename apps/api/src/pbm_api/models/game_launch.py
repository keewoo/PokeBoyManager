"""Modèle de persistance de la **machine de lancement d'une partie** (lot `j-lancement-partie`).

Entre le **salon d'attente à deux** (`j-invitations`, une invitation acceptée) et la **partie en
cours** (`j-partie-service`, `Game`), il y a une étape que JF a nommée :
*« qui commence »*. Ce lot la porte comme une **machine à états persistée** — un rechargement au
milieu ne perd rien — plutôt que comme un échange éphémère en mémoire :

1. **préparation** — chaque camp choisit son deck parmi les siens et se déclare prêt. Le deck est
   recontrôlé (légalité, possession, scripts D9) à chaque étape : une carte vendue ou dont le script
   a été retiré depuis l'entrée rend le deck injouable, et le lancement le dit (jamais une partie
   fantôme) ;
2. **tirage** — dès que les deux sont prêts, le serveur tire la **graine** d'aléatoire, **publie son
   empreinte** (engagement, commit-reveal) *avant* le tirage, puis fait le **pile ou face R-4.7**
   (`pbm_game.rng`, flux :data:`~pbm_game.rng.FLUX_QUI_COMMENCE`). Le résultat et son gagnant sont
   publics immédiatement ; la graine reste **secrète** jusqu'à la fin de la partie (révéler tôt
   rendrait la pioche prévisible). Le gagnant choisit de commencer ou non (livret officiel R-1.1),
   avec un **délai** et un **choix par défaut** (commencer — lecture littérale de R-4.7) ;
3. **lancé** — le choix tranché, les decks recontrôlés une dernière fois, la partie est créée
   (:func:`~pbm_api.games.service.creer_partie`) avec **cette** graine et le premier joueur assis au
   siège 0 (invariant du moteur : le tour 1 est celui qui commence). ``game_id`` pointe la partie ;
4. **abandonné** — un joueur quitte avant le lancement (déconnexion, renoncement) : figé, aucune
   partie n'est créée.

Le **tirage est vérifiable après coup** par les deux joueurs : ``engagement`` (publié avant),
``tirage`` (le :class:`~pbm_game.rng.Tirage` sérialisé du pile ou face) et, une fois la partie
terminée, la ``graine`` révélée suffisent à recalculer le pile ou face hors du serveur
(`pbm_game.rng.verifier_engagement` + `rejouer_tirage`). Rien ici ne décide d'une règle : le serveur
fait autorité, l'écran ne fait que montrer l'animation d'un résultat déjà tombé côté serveur.

Une invitation n'a **qu'un** lancement (unicité sur ``invitation_id``) : la machine est idempotente
par invitation. Les decks choisis sont en ``SET NULL`` (supprimer un deck n'efface pas la trace du
lancement) ; ``game_id`` aussi (purger une partie morte n'efface pas son lancement).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin

# --- Statuts de la machine de lancement (stables, lus par le service et les écrans) ----------
#: Les deux camps choisissent leur deck et se déclarent prêts — seul statut où l'on « se prépare ».
LANCEMENT_STATUT_PREPARATION = "preparation"
#: Les deux sont prêts : graine engagée, pile ou face tiré, le gagnant doit choisir (ou le défaut).
LANCEMENT_STATUT_TIRAGE = "tirage"
#: Le choix est tranché, la partie est créée : ``game_id`` la désigne. État final heureux.
LANCEMENT_STATUT_LANCE = "lance"
#: Un joueur a quitté avant le lancement : figé, aucune partie créée. État final.
LANCEMENT_STATUT_ABANDONNE = "abandonne"

#: L'ensemble des statuts reconnus. Un statut hors de cet ensemble est un bug, jamais écrit.
LANCEMENT_STATUTS: frozenset[str] = frozenset(
    {
        LANCEMENT_STATUT_PREPARATION,
        LANCEMENT_STATUT_TIRAGE,
        LANCEMENT_STATUT_LANCE,
        LANCEMENT_STATUT_ABANDONNE,
    }
)


class GameLaunch(Base, TimestampMixin):
    """Le lancement d'une partie : choix des decks, prêt, graine engagée, tirage, premier joueur.

    ``graine`` est le **secret** d'aléatoire (commit-reveal) : jamais renvoyé au client tant que la
    partie n'est pas terminée. ``engagement`` est l'empreinte, publiable au tirage. ``tirage``
    porte le pile ou face R-4.7 sérialisé (`pbm_game.rng.tirage_vers_json`) — public, c'est la pièce
    que les deux joueurs revérifient. ``tirage_gagnant_user_id`` est le gagnant du pile ou face ;
    ``choix_commencer`` son choix (``None`` tant qu'il n'a pas tranché) ; ``premier_joueur_user_id``
    le joueur qui commencera réellement, et ``choix_expire_at`` l'échéance au-delà de laquelle le
    choix par défaut (le gagnant commence) s'applique.
    """

    __tablename__ = "game_launches"
    __table_args__ = (
        # Une invitation n'a qu'un lancement : la machine est idempotente par invitation.
        UniqueConstraint("invitation_id", name="uq_game_launches_invitation"),
        # Un lancement crée au plus une partie.
        UniqueConstraint("game_id", name="uq_game_launches_game"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # L'invitation acceptée dont ce lancement part. CASCADE : effacer l'invitation efface son
    # lancement (il n'a aucun sens sans elle).
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("game_invitations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    statut: Mapped[str] = mapped_column(
        String(16), nullable=False, default=LANCEMENT_STATUT_PREPARATION, index=True
    )
    # Decks finalement choisis par chaque camp — SET NULL : supprimer un deck n'efface pas la trace.
    inviter_deck_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("decks.id", ondelete="SET NULL"), nullable=True
    )
    invitee_deck_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("decks.id", ondelete="SET NULL"), nullable=True
    )
    # « Prêt à jouer » de chaque camp : le tirage ne part que lorsque les deux sont vrais.
    inviter_pret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    invitee_pret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Graine d'aléatoire (hex) — secret serveur, posée au tirage, révélée en fin de partie.
    graine: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Engagement (empreinte de la graine) publiable dès le tirage (commit-reveal).
    engagement: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Le pile ou face R-4.7 sérialisé (public) — la pièce que les deux joueurs revérifient.
    tirage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Gagnant du pile ou face, son choix (commencer ou non), et le premier joueur retenu.
    tirage_gagnant_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    choix_commencer: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    premier_joueur_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Échéance du choix : au-delà, le choix par défaut (le gagnant commence) s'applique.
    choix_expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # La partie créée au lancement (SET NULL : purger une partie morte n'efface pas son lancement).
    game_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("games.id", ondelete="SET NULL"), nullable=True
    )
