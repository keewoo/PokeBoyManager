"""Le vocabulaire des **événements de jeu** — les moments où un effet se déclenche.

Module **pur** (aucune E/S, ni HTTP, ni base, ni React), comme tout ``pbm_game``.

Un **événement de jeu** (:class:`EvenementJeu`) est un *moment* : « des dégâts viennent
d'être posés », « un Pokémon entre en jeu », « on est entre les deux tours ». C'est ce qu'un
effet déclenché écoute (« Lorsque ce Pokémon est mis K.O., … »). À ne pas confondre avec
l':class:`~pbm_game.journal.modele.Evenement` du journal, qui enregistre ce que le moteur **a
fait** : l'un est le *signal* qui ouvre une fenêtre de réaction, l'autre la *trace* de ce qui
en a résulté. Le bus (:mod:`pbm_game.effets.bus`) publie des :class:`EvenementJeu` ; les
réacteurs produisent, eux, des :class:`~pbm_game.journal.modele.Evenement`.

**La liste est fermée (D9).** Un déclencheur dont le moment n'est pas dans :data:`EVENEMENTS_JEU`
n'est pas approximé : il est refusé, et la liste doit être complétée (puis l'étude des cartes
refaite) avant qu'une telle carte n'entre au jeu. Les onze moments ci-dessous couvrent
l'échantillon de 200 cartes porteuses d'effet relevé dans le catalogue (voir
``apps/game/tools/classer_echantillon.py`` et le test ``test_effets_echantillon``).

Les dix moments nommés dans la fiche du lot :

* **début du tour** / **fin du tour** ;
* **avant les dégâts** / **après les dégâts** ;
* **à la pose** d'un Pokémon / **à l'évolution** ;
* **au K.O.** ;
* **à l'attachement d'énergie** / **à la pioche** ;
* **entre les tours** (le Pokémon Checkup, R-12.1).

Et un onzième, que le dépouillement du catalogue a fait apparaître et que la fiche du lot
``j-cartes-objets`` réclame explicitement (l'appât déclenche « quand ce Pokémon devient
actif… ») : **devient actif**. La liste a donc été complétée, comme le prévoit le critère
d'acceptation, et l'étude refaite sur le même échantillon.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Les onze moments de jeu -------------------------------------------------
#: Début du tour, après la pioche obligatoire (R-5.1). Pendant de la fenêtre socle
#: :data:`~pbm_game.tour.fenetres.FENETRE_DEBUT_TOUR`.
EJ_DEBUT_TOUR = "debut_tour"
#: Fin du tour, à l'entrée du Pokémon Checkup (R-12.1). Pendant de la fenêtre socle
#: :data:`~pbm_game.tour.fenetres.FENETRE_FIN_TOUR`.
EJ_FIN_TOUR = "fin_tour"
#: Le Pokémon Checkup, **entre les deux tours** (R-12.1/R-12.3) : c'est là que se résolvent
#: les effets « au Checkup / entre les tours » (talents de banc, Dresseurs).
EJ_ENTRE_TOURS = "entre_tours"
#: Juste **avant** que les dégâts d'une attaque ne soient calculés (R-10.1) — fenêtre des
#: effets « avant application de la faiblesse » et des réductions.
EJ_AVANT_DEGATS = "avant_degats"
#: Juste **après** que les dégâts ont été posés (R-10) — fenêtre des effets « quand ce Pokémon
#: subit des dégâts » / « est blessé par une attaque ».
EJ_APRES_DEGATS = "apres_degats"
#: Un Pokémon de base est **posé** en jeu (R-5.3) — « Lorsque vous jouez ce Pokémon de votre
#: main… ».
EJ_POSE = "pose"
#: Un Pokémon **évolue** (R-7.1) — « Lorsque ce Pokémon évolue… ».
EJ_EVOLUTION = "evolution"
#: Un Pokémon est **mis K.O.** (R-13.1) — « Lorsque ce Pokémon est mis K.O.… ».
EJ_KO = "ko"
#: Une **énergie est attachée** à un Pokémon (R-5.4) — « Chaque fois que vous attachez une
#: énergie… ».
EJ_ATTACHEMENT_ENERGIE = "attachement_energie"
#: Des cartes sont **piochées** (R-5.2) — « Lorsque vous piochez une carte… ».
EJ_PIOCHE = "pioche"
#: Un Pokémon **devient Actif** (R-8) — déclencheur des effets « quand ce Pokémon devient
#: votre Pokémon Actif… », indispensable aux appâts (fiche ``j-cartes-objets``).
EJ_DEVIENT_ACTIF = "devient_actif"

#: Les onze moments reconnus. En demander un autre est une erreur franche, jamais un silence
#: (D9). Compléter cette liste impose de refaire l'étude de couverture des cartes.
EVENEMENTS_JEU: frozenset[str] = frozenset(
    {
        EJ_DEBUT_TOUR,
        EJ_FIN_TOUR,
        EJ_ENTRE_TOURS,
        EJ_AVANT_DEGATS,
        EJ_APRES_DEGATS,
        EJ_POSE,
        EJ_EVOLUTION,
        EJ_KO,
        EJ_ATTACHEMENT_ENERGIE,
        EJ_PIOCHE,
        EJ_DEVIENT_ACTIF,
    }
)

# --- Les mécanismes d'un effet (au-delà des événements déclenchés) -----------
# Tous les effets ne sont pas « déclenchés par un moment ». Trois mécanismes vivent
# ailleurs, et l'architecture les porte aussi — les nommer évite de forcer un effet continu
# ou activé dans un faux événement.
#: Effet **déclenché** par un :data:`EVENEMENTS_JEU` (le bus le réveille).
MECANISME_DECLENCHE = "declenche"
#: Effet **continu** : un modificateur consulté au calcul (jamais une mutation), tant que sa
#: source est en jeu — voir :mod:`pbm_game.effets.continus`.
MECANISME_CONTINU = "continu"
#: Effet **activé** par le joueur à son tour (« une fois pendant votre tour… », « aussi souvent
#: que vous le souhaitez… ») : une action du joueur, résolue par la pile d'effets.
MECANISME_ACTIVE = "active"
#: Effet porté par une **attaque** : il se résout pendant l'attaque (entre :data:`EJ_AVANT_DEGATS`
#: et :data:`EJ_APRES_DEGATS`), ses sous-effets relevant du langage d'effets (``j-effets-dsl``).
MECANISME_ATTAQUE = "attaque"

#: Les mécanismes reconnus d'un effet de carte.
MECANISMES: frozenset[str] = frozenset(
    {MECANISME_DECLENCHE, MECANISME_CONTINU, MECANISME_ACTIVE, MECANISME_ATTAQUE}
)


@dataclass(frozen=True)
class EvenementJeu:
    """Un **moment de jeu** publié sur le bus, avec sa charge utile.

    * ``type`` — un des :data:`EVENEMENTS_JEU` (sinon ``ValueError`` : jamais approximé, D9) ;
    * ``donnees`` — la charge utile du moment, en valeurs **JSON natives** uniquement
      (``str``/``int``/``bool``/``list``/``dict``/``None``), pour qu'un effet suspendu (lot
      ``j-effets-choix``) puisse être repris après un F5 sans perdre son contexte.

    La **charge utile par moment** (ce que les réacteurs peuvent lire) :

    * :data:`EJ_DEBUT_TOUR` / :data:`EJ_FIN_TOUR` / :data:`EJ_ENTRE_TOURS` —
      ``{"joueur_actif", "numero"}`` ;
    * :data:`EJ_AVANT_DEGATS` / :data:`EJ_APRES_DEGATS` —
      ``{"attaquant", "defenseur", "au_banc"}`` (identités stables), et pour l'après,
      ``"degats"`` et ``"compteurs"`` posés ;
    * :data:`EJ_POSE` — ``{"joueur", "pokemon", "ref", "zone"}`` ;
    * :data:`EJ_EVOLUTION` — ``{"joueur", "pokemon", "ref", "nom"}`` ;
    * :data:`EJ_KO` — ``{"joueur", "pokemon"}`` ;
    * :data:`EJ_ATTACHEMENT_ENERGIE` — ``{"joueur", "pokemon", "energie"}`` ;
    * :data:`EJ_PIOCHE` — ``{"joueur", "nombre"}`` ;
    * :data:`EJ_DEVIENT_ACTIF` — ``{"joueur", "pokemon"}``.
    """

    type: str
    donnees: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in EVENEMENTS_JEU:
            raise ValueError(
                f"Événement de jeu inconnu : {self.type!r} — un moment non prévu n'est "
                f"jamais approximé (D9). Moments connus : {sorted(EVENEMENTS_JEU)}."
            )


__all__ = [
    "EJ_DEBUT_TOUR",
    "EJ_FIN_TOUR",
    "EJ_ENTRE_TOURS",
    "EJ_AVANT_DEGATS",
    "EJ_APRES_DEGATS",
    "EJ_POSE",
    "EJ_EVOLUTION",
    "EJ_KO",
    "EJ_ATTACHEMENT_ENERGIE",
    "EJ_PIOCHE",
    "EJ_DEVIENT_ACTIF",
    "EVENEMENTS_JEU",
    "MECANISME_DECLENCHE",
    "MECANISME_CONTINU",
    "MECANISME_ACTIVE",
    "MECANISME_ATTAQUE",
    "MECANISMES",
    "EvenementJeu",
]
