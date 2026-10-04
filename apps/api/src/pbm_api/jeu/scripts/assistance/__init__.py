"""`pbm_api.jeu.scripts.assistance` — l'**assistance IA** qui propose les scripts de cartes (DJ8).

Lot `j-effets-assistance-ia` (jalon J2). Écrire à la main les scripts d'effet de dizaines de
milliers de cartes n'arrivera jamais au bout. L'IA sait lire un texte de carte et proposer un
script — **à condition que rien n'entre en jeu sans être prouvé**. Ce paquet est ce garde-fou.

DJ8, la décision qui fait foi : l'IA propose un script **ET** ses cas de test ; le script n'entre en
jeu que si **ses tests passent ET** qu'une **seconde IA, chargée de le contredire, l'a approuvé** —
sans relecture humaine carte par carte. Un **rapport par famille** est fait à JF, qui peut retirer
une famille d'un mot. Clé **plateforme** uniquement, jamais celle d'un utilisateur. Plafond cumulé
**50 €**, coût journalisé par carte, reprise après interruption. **Sans clé**, le lot livre son
outillage, ses tests et une **mesure sur un fournisseur factice**, sans dépense.

Les briques :

* :mod:`.familles` — classe un effet par famille (pur), le grain du rapport et du veto de JF ;
* :mod:`.gabarit` — construit les prompts (proposeur, contradicteur), grammaire dérivée du moteur ;
* :mod:`.fournisseur` — l'aller-retour IA (réel, et le double factice) + le parsing strict ;
* :mod:`.pricing` — le coût d'un appel (tarif standard, pas Batch) ;
* :mod:`.budget` — le grand livre : dépense cumulée, coût par carte, reprise ;
* :mod:`.verification` — la **porte** DJ8 (pure) : décide d'après les tests et le contradicteur ;
* :mod:`.runner` — l'orchestration d'un passage (sélection DJ2, appels, écriture, rapport).

Le cœur (familles, gabarit, verification) est **pur** ; le runner et le fournisseur réel touchent la
base, le réseau et le grand livre — la même séparation que partout dans ``jeu/scripts``.
"""

from __future__ import annotations

from pbm_api.jeu.scripts.assistance.verification import (
    GATE_A_REVOIR,
    GATE_NON_SUPPORTE,
    GATE_SCRIPTE,
    ResultatPorte,
    evaluer,
)

__all__ = [
    "GATE_SCRIPTE",
    "GATE_NON_SUPPORTE",
    "GATE_A_REVOIR",
    "ResultatPorte",
    "evaluer",
]
