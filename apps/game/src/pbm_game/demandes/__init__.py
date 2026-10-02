"""`pbm_game.demandes` — les **demandes de décision** : quand le moteur doit attendre un joueur.

Lot ``j-effets-choix``. Une carte peut réclamer un choix — à son joueur ou à l'**adversaire**, en
plein tour de l'autre : choisir une carte, plusieurs, un ordre, oui/non, un type, un nombre ; de
façon obligatoire ou facultative ; parmi un ensemble visible ou caché ; avec une réponse par défaut
et un délai. Le moteur **suspend** alors la résolution, l'état porte la demande en cours, et une
reprise après un F5 retrouve la demande intacte, **temps restant compris**.

Le piège que ce paquet évite : bloquer un fil d'exécution côté serveur (une partie sur deux figée à
la première déconnexion). La demande est une **donnée** (``ResolutionEnCours`` dans l'état), pas une
attente de code — voir :mod:`pbm_game.demandes.moteur`.

Trois briques :

* :mod:`~pbm_game.demandes.modele` — la demande, la réponse, les six catégories, la validation et la
  **réponse par défaut** (premier choix valide, ou abandon d'un effet facultatif) ;
* :mod:`~pbm_game.demandes.gestionnaire` — le point par lequel un effet *demande* sans bloquer :
  il rend la réponse déjà connue, ou lève une suspension ;
* :mod:`~pbm_game.demandes.moteur` — la résolution **suspendable** (``resoudre`` / ``repondre`` /
  ``expirer``), re-déroulée à l'identique à la reprise, aléatoire ramené en arrière.

Les transitions ``repondre_demande`` / ``expirer_demande`` (coups journalisés) s'enregistrent dans
le ``REGISTRE`` du journal **à l'import de ce paquet** (motif ``banc``/``cartes``).
"""

from __future__ import annotations

# Enregistre les transitions ``repondre_demande`` / ``expirer_demande`` dans le ``REGISTRE`` du
# journal à l'import (effet de bord voulu — comme ``pbm_game.banc`` et ``pbm_game.cartes``).
from . import transitions as _transitions  # noqa: F401
from .gestionnaire import Gestionnaire, SuspensionDemande
from .modele import (
    CAT_CARTE,
    CAT_CARTES,
    CAT_NOMBRE,
    CAT_ORDRE,
    CAT_OUI_NON,
    CAT_TYPE,
    DemandeDecision,
    Reponse,
    reponse_par_defaut,
    valider_reponse,
)
from .moteur import (
    REGISTRE_EFFETS,
    ResolutionEnCours,
    demarrer_resolution,
    enregistrer,
    expirer,
    repondre,
    resoudre,
)

__all__ = [
    "Gestionnaire",
    "SuspensionDemande",
    "DemandeDecision",
    "Reponse",
    "reponse_par_defaut",
    "valider_reponse",
    "CAT_CARTE",
    "CAT_CARTES",
    "CAT_ORDRE",
    "CAT_OUI_NON",
    "CAT_TYPE",
    "CAT_NOMBRE",
    "ResolutionEnCours",
    "REGISTRE_EFFETS",
    "enregistrer",
    "resoudre",
    "demarrer_resolution",
    "repondre",
    "expirer",
]
