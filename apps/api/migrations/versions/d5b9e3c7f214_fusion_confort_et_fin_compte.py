"""Fusion de deux têtes : `jeu_confort_reglages` et `fin de partie côté compte`.

Migration **vide**, et c'est tout ce qu'elle doit être. Deux lots menés en parallèle
(`j-accessibilite-jeu` et `j-fin-effets-compte`) ont chacun ajouté une révision depuis la même tête
``a1f7c3d9e5b2``. Les deux sont légitimes et indépendantes — l'une crée une table de réglages,
l'autre écrit le résultat d'une partie sur le compte — mais leur coexistence donne **deux têtes**, et
``alembic upgrade head`` refuse alors d'avancer (« Multiple head revisions are present »). La CI le
voit sur ``main``, pas sur les branches : chacune n'a que sa propre tête.

Elle ne crée, ne modifie et ne supprime **rien**. Son seul rôle est de rejoindre les deux branches
pour qu'une tête unique existe à nouveau. Le retour arrière la retire sans toucher aux données.

Revision ID: d5b9e3c7f214
Revises: c4f1a8b7e2d3, e2a7b4c1d6f9
Create Date: 2026-10-14
"""

from __future__ import annotations

revision = "d5b9e3c7f214"
down_revision = ("c4f1a8b7e2d3", "e2a7b4c1d6f9")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rien à faire : la fusion n'existe que pour rendre une tête unique au graphe."""


def downgrade() -> None:
    """Rien à défaire — les deux branches redeviennent deux têtes."""
