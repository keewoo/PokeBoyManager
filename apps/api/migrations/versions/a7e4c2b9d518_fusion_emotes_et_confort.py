"""Fusion de deux têtes : `jeu_emote_reglages` et `jeu_confort_reglages`.

Migration **vide**, et c'est tout ce qu'elle doit être. Deux lots menés en parallèle
(`j-echanges-emotes` et `j-accessibilite-jeu`) ont chacun ajouté une révision — l'une crée la table
du réglage d'emotes, l'autre celle du confort de jeu. Les deux sont légitimes et indépendantes, mais
leur coexistence donne **deux têtes**, et ``alembic upgrade head`` refuse alors d'avancer
(« Multiple head revisions are present »).

⚠️ La CI ne le voit que sur ``main`` : chaque branche n'a que sa propre tête, et tout paraît vert
jusqu'à la fusion. Le réflexe est donc de lancer ``alembic heads`` **dans la branche, après avoir
fusionné ``github/main``, avant de pousser** — c'est ce qui a produit ce fichier.

Elle ne crée, ne modifie et ne supprime **rien**. Son seul rôle est de rejoindre les deux branches
pour qu'une tête unique existe à nouveau. Le retour arrière la retire sans toucher aux données.

Revision ID: a7e4c2b9d518
Revises: b8d3f0c47a51, d5b9e3c7f214
Create Date: 2026-10-14
"""

from __future__ import annotations

revision = "a7e4c2b9d518"
down_revision = ("b8d3f0c47a51", "d5b9e3c7f214")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rien à faire : cette révision ne joint que deux branches de l'historique."""


def downgrade() -> None:
    """Rien à défaire : voir :func:`upgrade`."""
