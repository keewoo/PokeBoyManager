"""Le **registre des scripts d'effet** : la table `card_scripts`.

Lot `j-effets-catalogue-compilation`.

Le pont entre les trente mille cartes du catalogue et les cartes réellement *jouables*. Une carte
n'est pas scriptée carte par carte : elle l'est **par texte d'effet**. Des centaines de cartes
partagent le même texte (« Piochez 2 cartes. », « Fouille »…) ; un seul script les couvre toutes.
La clé d'une ligne est donc l'**empreinte du texte source** (`text_fingerprint`), pas une carte.

Chaque ligne porte :

* ``text_fingerprint`` — l'empreinte SHA-256 du texte d'effet **normalisé** (voir
  :mod:`pbm_api.jeu.scripts.empreinte`). La clé de regroupement : un script par texte distinct.
* ``source_text`` — le texte d'effet canonique que ce script couvre, gardé **tel quel** (pour la
  relecture, le rapport de couverture, et la détection d'errata — on compare au texte vivant).
* ``lang`` — la langue du texte source (métadonnée de traçabilité ; le catalogue range le texte
  brut, fr avec repli en). L'empreinte seule tranche l'appariement : deux langues donnent deux
  octets donc deux empreintes, elles ne se confondent jamais.
* ``dsl_version`` — la version du langage d'effets dans laquelle le script est écrit (l'interprète
  refuse une version qu'il ne sait pas lire — cf. ``pbm_game.effets.dsl.chargement``).
* ``script`` — le programme DSL (JSON), ``NULL`` quand le statut est « non supporté ».
* ``statut`` — ``scripte`` (jouable), ``non_supporte`` (hors langage v1, refusé au deck en le
  disant — D9), ``a_revoir`` (jamais validé, ou texte modifié depuis : ne se joue plus).
* ``author`` / ``validated_at`` — qui a validé le script, et quand (vide tant qu'il ne l'est pas).
* ``tests`` — les cas de test associés (identifiants), la preuve qu'il fait ce que la carte dit.
* ``notes`` — le *pourquoi* d'un ``non_supporte`` (quelle tournure manque), jamais un effet deviné.

**D9 sans détour.** Un texte sans ligne « scriptée » lisible **bloque** la carte qui le porte à la
construction de la partie — jamais un effet neutre deviné. C'est le chargeur
(:mod:`pbm_api.jeu.scripts.chargeur`) qui applique ce refus, avant la mise en place.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from pbm_api.models.base import Base, TimestampMixin

#: Un script validé et jouable : ses tests passent, l'interprète sait lire sa version.
SCRIPT_STATUT_SCRIPTE = "scripte"
#: Un texte dont l'effet n'entre pas dans le langage v1 — refusé au deck en le disant (D9, jamais
#: approximé). ``notes`` dit quelle tournure manque ; ``script`` est ``NULL``.
SCRIPT_STATUT_NON_SUPPORTE = "non_supporte"
#: Un script jamais validé, ou dont le texte source a changé en base depuis la validation : il ne
#: se joue plus tant qu'une relecture ne l'a pas reconfirmé (détection d'errata).
SCRIPT_STATUT_A_REVOIR = "a_revoir"

#: Les trois statuts reconnus — tout autre est une donnée corrompue, pas un cas « au mieux ».
SCRIPT_STATUTS: frozenset[str] = frozenset(
    {SCRIPT_STATUT_SCRIPTE, SCRIPT_STATUT_NON_SUPPORTE, SCRIPT_STATUT_A_REVOIR}
)


class CardScript(Base, TimestampMixin):
    """Un script d'effet du registre, clé par l'**empreinte du texte source** (pas par carte).

    Un texte identique partagé par N cartes = **une** ligne ici : c'est le regroupement qui réduit
    le travail de scriptage (critère n°2 du lot). L'appariement carte → script se fait par
    empreinte, à la volée (``pbm_api.jeu.scripts.chargeur``) : aucune colonne ne fige de lien par
    carte, sinon le regroupement n'existerait pas.
    """

    __tablename__ = "card_scripts"
    __table_args__ = (
        # L'empreinte est la clé de regroupement : une seule ligne par texte distinct (par langue,
        # mais l'empreinte seule suffit déjà à distinguer deux langues — contrainte de sûreté).
        UniqueConstraint("text_fingerprint", name="uq_card_scripts_fingerprint"),
        # Le rapport de couverture et la détection d'errata listent par statut : un index y aide.
        Index("ix_card_scripts_statut", "statut"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: Empreinte SHA-256 (hex, 64 car.) du texte d'effet normalisé — la clé de regroupement.
    text_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Langue du texte source (fr/en…), traçabilité ; l'appariement passe par l'empreinte.
    lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    #: Le texte d'effet canonique couvert par ce script, gardé **brut** (relecture, errata).
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    #: Version du langage d'effets dans laquelle le script est écrit.
    dsl_version: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Le programme DSL (dict JSON), ``NULL`` quand le statut est « non supporté ».
    script: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    #: ``scripte`` / ``non_supporte`` / ``a_revoir`` — jamais hors de :data:`SCRIPT_STATUTS`.
    statut: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Qui a validé le script (humain ou outil), vide tant qu'il n'est pas validé.
    author: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: Date de validation (passage en ``scripte``), ``NULL`` tant que non validé.
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Cas de test associés (liste d'identifiants) — la preuve que le script fait son effet.
    tests: Mapped[list | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    #: Le *pourquoi* d'un ``non_supporte`` (quelle tournure manque), ou toute note de relecture.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = [
    "CardScript",
    "SCRIPT_STATUT_SCRIPTE",
    "SCRIPT_STATUT_NON_SUPPORTE",
    "SCRIPT_STATUT_A_REVOIR",
    "SCRIPT_STATUTS",
]
