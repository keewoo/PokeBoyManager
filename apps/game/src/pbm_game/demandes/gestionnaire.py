"""Le **gestionnaire de décisions** — ce par quoi un effet *demande* un choix sans bloquer un fil.

Module **pur**. Un résolveur d'effet (ou l'interprète DSL) qui a besoin d'une décision n'appelle
pas une fonction qui « attend » : il appelle :meth:`Gestionnaire.demander`, qui fait l'une de deux
choses, et **jamais** une troisième :

* la décision a **déjà** une réponse enregistrée (on est en train de **re-dérouler** la résolution
  après que le joueur a répondu) → il la renvoie, et l'effet continue ;
* la décision est **nouvelle** → il lève :class:`SuspensionDemande`, qui remonte jusqu'au moteur
  de résolution : celui-ci fige la pile, pose la demande dans l'état, et rend la main.

**Pourquoi un compteur, et pourquoi il est déterministe.** Chaque décision reçoit un identifiant
``d0``, ``d1``… dans l'ordre où elle est rencontrée. À la reprise, le moteur **re-déroule** la
résolution depuis l'effet suspendu : les mêmes décisions sont rencontrées dans le même ordre (le
moteur est déterministe, l'aléatoire est ramené en arrière avant le re-déroulé), donc les mêmes
identifiants retombent sur les mêmes décisions, et l'appariement réponse ↔ décision tient. Le
compteur part de ``base`` : les décisions des effets **déjà résolus** (sortis de la pile) ne sont
pas re-comptées, mais leurs réponses occupent les premiers indices — ``base`` saute par-dessus.
"""

from __future__ import annotations

from dataclasses import dataclass

from .modele import DemandeDecision, Reponse, valider_reponse


class SuspensionDemande(Exception):
    """Levée par :meth:`Gestionnaire.demander` quand une décision **nouvelle** est rencontrée.

    Elle n'est pas une erreur : c'est le signal normal « la résolution s'arrête ici, en attendant
    la réponse d'un joueur ». Elle porte la :class:`~pbm_game.demandes.modele.DemandeDecision`
    (déjà munie de son ``id``) que le moteur posera dans l'état.
    """

    def __init__(self, demande: DemandeDecision) -> None:
        self.demande = demande
        super().__init__(f"Décision requise : « {demande.id} » ({demande.libelle}).")


@dataclass
class Gestionnaire:
    """Fournit les réponses déjà connues, lève pour les nouvelles — le temps d'une résolution.

    * ``reponses`` — les réponses **déjà données** par les joueurs (dans l'ordre des décisions) ;
    * ``base`` — le nombre de décisions des effets déjà résolus (indice de départ du compteur) ;
    * ``compteur`` — avance à chaque :meth:`demander` ; ``base + compteur`` est l'indice global de
      la prochaine décision.

    Objet **mutable** (le compteur avance) mais partagé par tous les effets d'**une passe** de
    résolution : c'est ce qui donne aux décisions un ordre global cohérent d'un effet à l'autre.
    """

    reponses: tuple[Reponse, ...] = ()
    base: int = 0
    compteur: int = 0

    @property
    def indice_courant(self) -> int:
        """L'indice global de la prochaine décision à rencontrer (``base + compteur``)."""
        return self.base + self.compteur

    def demander(self, demande: DemandeDecision) -> Reponse:
        """Rend la réponse enregistrée pour cette décision, ou lève :class:`SuspensionDemande`.

        ``demande`` arrive **sans** ``id`` (le gestionnaire l'attribue : ``d{indice}``). Si une
        réponse existe à cet indice, elle est **revalidée** (elle a pu être forgée par un client :
        le serveur revérifie toujours) et renvoyée. Sinon, la demande est levée pour suspendre.
        """
        indice = self.indice_courant
        identifiant = f"d{indice}"
        demande = demande.avec_id(identifiant)
        self.compteur += 1
        if indice < len(self.reponses):
            reponse = self.reponses[indice]
            valider_reponse(demande, reponse)  # le serveur fait autorité, toujours
            return reponse
        raise SuspensionDemande(demande)


__all__ = ["SuspensionDemande", "Gestionnaire"]
