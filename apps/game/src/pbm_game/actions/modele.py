"""Structures du **générateur d'actions légales** — ce qui est jouable, et ses cibles.

Ce module est **pur** : aucune entrée/sortie, aucune dépendance à HTTP, à une base de
données ou à React, comme tout le moteur ``pbm_game`` (principe du jalon J1).

Trois objets :

* :class:`Cible` — une cible valide d'une action (un Pokémon en jeu, une carte de la main,
  un joueur…), **calculée depuis l'état**, jamais fournie par l'interface ;
* :class:`ActionLegale` — un coup jouable : l':class:`~pbm_game.journal.Action` à
  journaliser, une **étiquette lisible**, et ses **cibles valides** ;
* :class:`Verdict` — le résultat de :func:`~pbm_game.actions.valider` : soit l'accord, soit
  un **refus motivé** citant la règle ``R-x.y`` qui l'interdit.

Principe porté par ce lot (``j-actions-legales``) — **une seule source de vérité** : la
liste des actions légales. La validation vérifie l'**appartenance** à cette liste (plus,
pour un refus, la règle qui bloque) ; elle ne redérive jamais la légalité par un second
chemin qui finirait par diverger (voir le risque nommé dans la fiche du lot).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..journal.modele import Action

# --- Genres de cible (ce que porte ``Cible.genre``) --------------------------
# Un genre dit à l'interface COMMENT présenter la cible ; sa ``reference`` l'identifie de
# façon stable (``instance_id`` d'une carte / d'un Pokémon en jeu, ou identifiant de
# joueur). Les familles d'actions des lots suivants réutilisent ces genres ou en ajoutent.
GENRE_JOUEUR = "joueur"
GENRE_POKEMON_EN_JEU = "pokemon_en_jeu"
GENRE_CARTE_MAIN = "carte_main"


@dataclass(frozen=True)
class Cible:
    """Une cible valide d'une action — calculée depuis l'état, jamais depuis l'écran.

    * ``genre`` — un des ``GENRE_*`` : dit à l'interface quel type d'objet est visé ;
    * ``reference`` — l'identifiant stable de la cible (``instance_id`` ou id de joueur) ;
    * ``etiquette`` — un libellé lisible par un humain (« Pikachu de l'adversaire »).
    """

    genre: str
    reference: str
    etiquette: str


@dataclass(frozen=True)
class ActionLegale:
    """Un coup jouable, tel que l'interface doit l'afficher et le proposer.

    * ``action`` — l':class:`~pbm_game.journal.Action` **exacte** à journaliser si le joueur
      choisit ce coup ; c'est elle que :func:`~pbm_game.actions.valider` retrouvera ;
    * ``etiquette`` — le libellé lisible du coup (« Passer à la phase suivante ») ;
    * ``cibles`` — les cibles valides de ce coup (vide quand le coup n'en a pas, comme
      « abandonner »). L'interface n'en calcule aucune : elle affiche celles-ci.
    """

    action: Action
    etiquette: str
    cibles: tuple[Cible, ...] = ()


@dataclass(frozen=True)
class Verdict:
    """Le résultat de :func:`~pbm_game.actions.valider` : accord, ou refus motivé.

    ``accepte`` vrai = le coup est légal (``regle`` et ``message`` restent vides). Sinon,
    ``regle`` porte l'identifiant ``R-x.y`` du corpus (``docs/jeu/REGLES.md``) qui motive
    le refus, et ``message`` l'explique en français pour l'affichage. Un refus sans règle
    citée est interdit : c'est la garantie « le joueur lit la raison, pas un bug ».
    """

    accepte: bool
    regle: str = ""
    message: str = ""

    @property
    def refuse(self) -> bool:
        """Inverse lisible de ``accepte`` (sucre pour les appelants et les tests)."""
        return not self.accepte


#: Verdict d'accord partagé : immuable, donc réutilisable sans risque.
ACCORD = Verdict(accepte=True)


def refus(regle: str, message: str) -> Verdict:
    """Construit un :class:`Verdict` de refus en exigeant une règle citée (non vide).

    Lève ``ValueError`` si ``regle`` ou ``message`` est vide : un refus doit toujours dire
    *pourquoi*, en nommant une règle — jamais un refus muet (pas de repli silencieux).
    """
    if not regle or not regle.strip():
        raise ValueError("Un refus doit citer une règle R-x.y (jamais un refus muet).")
    if not message or not message.strip():
        raise ValueError("Un refus doit porter un message lisible pour le joueur.")
    return Verdict(accepte=False, regle=regle, message=message)


__all__ = [
    "GENRE_JOUEUR",
    "GENRE_POKEMON_EN_JEU",
    "GENRE_CARTE_MAIN",
    "Cible",
    "ActionLegale",
    "Verdict",
    "ACCORD",
    "refus",
]
