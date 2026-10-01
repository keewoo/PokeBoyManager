"""Résolution des états **à la déclaration d'attaque** — blocage et confusion (R-11.3/5/6).

Module **pur** (aucune E/S), mais, contrairement à :mod:`pbm_game.etats.matrice`, il a besoin
de l'aléatoire (:class:`~pbm_game.rng.Rng`) et du journal : la confusion **tire un pile ou
face** (R-11.5) et chaque tirage est journalisé.

Appelé par la transition ``declarer_attaque`` (:mod:`pbm_game.journal.transitions`) **avant**
que l'attaque ne produise ses effets :

* **Endormi / Paralysé** (R-11.3/R-11.6, rappelés par R-11.2) : l'Actif **ne peut pas
  attaquer** → ``ValueError`` motivée (le serveur refuse le coup, jamais un refus muet) ;
* **Confus** (R-11.5) : pile ou face **avant** d'attaquer — **face** = l'attaque a lieu
  normalement ; **pile** = l'attaque **n'a pas lieu** et **3 compteurs de dégâts** sont posés
  sur le Pokémon confus. Le tour se termine quand même (R-5.8 : déclarer une attaque termine le
  tour), ce dont se charge l'appelant.

Comme un seul état d'orientation coexiste (R-11.8), ces trois cas sont **exclusifs** : l'Actif
est au plus Endormi *ou* Confus *ou* Paralysé. Les marqueurs (Brûlé, Empoisonné) n'affectent pas
la déclaration d'attaque — ils se résolvent au Checkup (R-11.4/R-11.7).
"""

from __future__ import annotations

from dataclasses import replace

from ..journal.modele import EVT_CONFUSION, Evenement
from ..rng import FACE, Rng, flux_confusion
from ..state.modele import CONFUS, EtatPartie, Joueur
from .matrice import etat_bloquant_attaque

#: Compteurs de dégâts posés sur soi quand la confusion fait rater l'attaque (R-11.5).
CONFUSION_COMPTEURS = 3
#: Dégâts d'un compteur (R-10.4/R-10.6) : 1 compteur = 10 dégâts.
DEGATS_PAR_COMPTEUR = 10

# Note : la pose des 3 compteurs est faite **ici** par ``replace`` plutôt que via
# ``pbm_game.combat.resolution.poser_compteurs`` (même calcul, R-10.6) pour ne PAS tirer le
# paquet ``combat`` — il importe ``actions`` qui importe ``journal.transitions``, lequel importe
# ce module : la dépendance créerait un cycle d'import au chargement. La règle reste citée.


def _index_joueur(etat: EtatPartie, jid: str) -> int:
    for i, joueur in enumerate(etat.joueurs):
        if joueur.id == jid:
            return i
    raise ValueError(f"Joueur « {jid} » absent de la partie.")


def _remplacer_joueur(etat: EtatPartie, index: int, joueur: Joueur) -> EtatPartie:
    joueurs = list(etat.joueurs)
    joueurs[index] = joueur
    return replace(etat, joueurs=(joueurs[0], joueurs[1]))


def resoudre_etats_avant_attaque(
    etat: EtatPartie, jid: str, rng: Rng
) -> tuple[EtatPartie, bool, list[Evenement]]:
    """Résout les états de l'Actif de ``jid`` **avant** son attaque (R-11.3/5/6).

    Renvoie ``(etat, attaque_a_lieu, evenements)`` :

    * **attaque_a_lieu** est ``False`` uniquement sur une confusion qui tombe sur **pile**
      (R-11.5) — l'attaque n'a alors aucun effet, mais le tour se termine (c'est à l'appelant de
      le faire). Il est ``True`` sinon (Actif sain, ou confusion sur **face**) ;
    * ``etat`` est modifié seulement sur **pile** de confusion (3 compteurs posés sur l'Actif).

    Lève ``ValueError`` si l'Actif est **Endormi** ou **Paralysé** (R-11.3/R-11.6 : il ne peut
    pas attaquer) ou si ``jid`` n'a pas d'Actif (R-9.1 : rien pour porter l'attaque). L'appelant
    (``declarer_attaque``) a déjà vérifié la partie vivante, le joueur actif et la phase.
    """
    index = _index_joueur(etat, jid)
    actif = etat.joueurs[index].actif
    if actif is None:
        raise ValueError("Aucun Pokémon Actif ne peut porter l'attaque (R-9.1).")

    # R-11.3 / R-11.6 (R-11.2) : Sommeil et Paralysie interdisent d'attaquer.
    bloquant = etat_bloquant_attaque(actif)
    if bloquant is not None:
        raise ValueError(
            f"L'Actif ne peut pas attaquer sous l'état « {bloquant} » (R-11.3/R-11.6)."
        )

    # R-11.5 : Confusion → pile ou face AVANT d'attaquer.
    if CONFUS not in actif.etats_speciaux:
        return etat, True, []

    tirage = rng.pile_ou_face(flux_confusion(jid), "R-11.5 confusion")
    if tirage == FACE:
        # Face : l'attaque a lieu normalement (R-11.5). Rien à poser.
        evt = Evenement(
            EVT_CONFUSION,
            {"joueur": jid, "etat": CONFUS, "regle": "R-11.5", "pile_ou_face": tirage,
             "attaque_annulee": False, "degats": 0},
        )
        return etat, True, [evt]

    # Pile : l'attaque n'a pas lieu, 3 compteurs de dégâts sur le Pokémon confus (R-11.5 ;
    # posés en **compteurs**, jamais en PV soustraits — R-10.4/R-10.6).
    actif2 = replace(
        actif, compteurs_degats=actif.compteurs_degats + CONFUSION_COMPTEURS * DEGATS_PAR_COMPTEUR
    )
    etat2 = _remplacer_joueur(etat, index, replace(etat.joueurs[index], actif=actif2))
    evt = Evenement(
        EVT_CONFUSION,
        {"joueur": jid, "etat": CONFUS, "regle": "R-11.5", "pile_ou_face": tirage,
         "attaque_annulee": True, "degats": CONFUSION_COMPTEURS * 10},
    )
    return etat2, False, [evt]


__all__ = [
    "CONFUSION_COMPTEURS",
    "resoudre_etats_avant_attaque",
]
