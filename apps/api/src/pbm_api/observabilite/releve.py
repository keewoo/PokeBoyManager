"""La **forme** d'un relevé de métriques du jeu — pure, sérialisable, sans base de données.

Séparée de sa lecture (:mod:`pbm_api.observabilite.metriques`, qui interroge Postgres) pour que
les seuils d'alerte (:mod:`pbm_api.observabilite.regles`) et la mise en forme des messages
(:mod:`pbm_api.observabilite.rapport`) se testent **sans base** : un seuil qu'on ne peut éprouver
qu'en montant une base est un seuil qu'on n'éprouve pas.

Le vocabulaire des raisons de fin est celui du moteur (``pbm_game.journal.modele``) : ``abandon``,
``desertion``, ``temps_ecoule``, ``inactivite``, ``derniere_recompense``, ``plus_de_pokemon``,
``pioche_impossible``, ``egalite``. On ne le recopie pas ici — on le lit tel quel dans ``games``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Raison de fin d'une partie perdue au temps (R-15, horloges du lot ``j-timer``).
RAISON_TEMPS_ECOULE = "temps_ecoule"
#: Raison de fin d'une partie perdue par déconnexion non rattrapée (lot ``j-deconnexion-abandon``).
RAISON_DESERTION = "desertion"
#: Raison de fin d'une partie close faute d'activité (partie fantôme).
RAISON_INACTIVITE = "inactivite"
#: Clé de repli quand ``games.raison_fin`` est vide — jamais inventée, nommée pour ce qu'elle est.
RAISON_NON_RENSEIGNEE = "(non renseignée)"


@dataclass(frozen=True)
class Releve:
    """Les métriques du jeu sur une fenêtre de temps, telles qu'on les publie et qu'on les juge.

    ``fenetre_heures`` borne tous les compteurs « de flux » (créées, terminées, coups, incidents) ;
    les compteurs « d'état » (``parties_en_cours``, ``parties_bloquees``) décrivent l'instant.

    ``coups_moyens`` compte les **coups** journalisés, pas les **tours** : le nombre de tours n'est
    stocké nulle part (il faudrait rejouer chaque partie pour l'obtenir), et un lot ne l'approxime
    pas (D9). L'écart est assumé et écrit dans ``docs/jeu/OBSERVABILITE.md``.
    """

    fenetre_heures: int
    parties_en_cours: int = 0
    parties_bloquees: int = 0
    parties_creees: int = 0
    parties_terminees: int = 0
    fins_par_raison: dict[str, int] = field(default_factory=dict)
    duree_moyenne_minutes: float | None = None
    coups_moyens: float | None = None
    coups_joues: int = 0
    refus: int = 0
    refus_par_motif: dict[str, int] = field(default_factory=dict)
    erreurs_moteur: int = 0
    parties_refusees: int = 0

    @property
    def expirations_horloge(self) -> int:
        """Parties perdues au temps sur la fenêtre (``raison_fin = temps_ecoule``)."""
        return self.fins_par_raison.get(RAISON_TEMPS_ECOULE, 0)

    @property
    def desertions(self) -> int:
        """Parties perdues par déconnexion non rattrapée sur la fenêtre."""
        return self.fins_par_raison.get(RAISON_DESERTION, 0)

    @property
    def taux_refus(self) -> float:
        """Part des coups soumis qui ont été refusés, entre 0 et 1 (0 si aucun coup soumis).

        Dénominateur = coups acceptés (journalisés) **plus** refusés : c'est bien « sur tout ce
        qu'on a soumis, combien ont été rejetés », la seule lecture qui ne bouge pas quand le
        volume de jeu change.
        """
        soumis = self.coups_joues + self.refus
        if soumis <= 0:
            return 0.0
        return self.refus / soumis

    @property
    def motif_dominant(self) -> tuple[str, int] | None:
        """Le motif de refus le plus fréquent et son compte, ou ``None`` s'il n'y a aucun refus."""
        if not self.refus_par_motif:
            return None
        motif = max(self.refus_par_motif.items(), key=lambda item: (item[1], item[0]))
        return motif

    def en_json(self) -> dict:
        """Forme sérialisable du relevé (route HTTP, état de la sonde, corps d'e-mail).

        Les propriétés dérivées sont incluses : le lecteur d'une métrique ne doit pas avoir à
        refaire un calcul pour savoir si une horloge a expiré.
        """
        return {
            "fenetre_heures": self.fenetre_heures,
            "parties_en_cours": self.parties_en_cours,
            "parties_bloquees": self.parties_bloquees,
            "parties_creees": self.parties_creees,
            "parties_terminees": self.parties_terminees,
            "fins_par_raison": dict(sorted(self.fins_par_raison.items())),
            "duree_moyenne_minutes": self.duree_moyenne_minutes,
            "coups_moyens": self.coups_moyens,
            "coups_joues": self.coups_joues,
            "refus": self.refus,
            "refus_par_motif": dict(sorted(self.refus_par_motif.items())),
            "taux_refus": round(self.taux_refus, 4),
            "erreurs_moteur": self.erreurs_moteur,
            "parties_refusees": self.parties_refusees,
            "expirations_horloge": self.expirations_horloge,
            "desertions": self.desertions,
        }


__all__ = [
    "RAISON_DESERTION",
    "RAISON_INACTIVITE",
    "RAISON_NON_RENSEIGNEE",
    "RAISON_TEMPS_ECOULE",
    "Releve",
]
