"""Le **modèle** des horloges d'une partie — une donnée calculée depuis des horodatages.

Module **pur** (aucune E/S, ni HTTP, ni base, ni réseau, ni horloge système), comme tout
``pbm_game``. C'est le point précis où les moteurs se cassent : une horloge codée en *minuteur
vivant* meurt au redéploiement et fait perdre des parties (risque nommé du lot ``j-timer``). Ici,
une horloge n'est **jamais** un compte à rebours en mémoire : c'est un **état sérialisable**
(:class:`EtatHorloges`) que l'extérieur décrémente en lui faisant descendre un **instant** (époque
en secondes). Le temps restant se **recalcule** à la demande à partir de cet instant et des
horodatages portés par l'état — donc il survit à un F5, à un redémarrage, à une reprise de journal.

Trois horloges (décision DJ4), toutes exprimées en secondes, toutes des **paramètres de
configuration** (:class:`ConfigHorloges`) — modifiables sans redéployer le moteur, puisque la
config voyage dans l'état et n'est jamais codée en dur ici :

* **par tour** — le joueur actif a ``par_tour_s`` pour jouer son tour ;
* **par joueur** — chaque joueur a ``par_joueur_s`` au total sur toute la partie (plafond dur) ;
* **par décision** — répondre à une demande (même hors de son tour) a ``par_decision_s``.

Et deux marges : ``tolerance_reseau_s`` (une horloge n'expire qu'au-delà de la limite **plus** cette
tolérance — la latence ne fait pas perdre un tour) et ``pause_deconnexion_s`` (durée de grâce
pendant laquelle les horloges sont gelées quand un joueur se déconnecte).

Le moteur ne consulte **aucune** horloge système : partout, ``maintenant`` est un ``float``
(secondes depuis l'époque) que l'appelant fournit. C'est ce qui garde le module pur et testable par
milliers de cas, et déterministe (donc rejouable).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

# Version du schéma d'horloges sérialisé : toute évolution incompatible l'incrémente.
# ``depuis_json`` refuse une version inconnue (jamais de repli silencieux sur un état partiel).
SCHEMA_HORLOGES_VERSION = 1

# --- Genres d'horloge active (ce que porte ``CompteurActif.genre``) ----------
#: Le compteur qui tourne mesure le **tour** du joueur actif (R-5, DJ4 « temps par tour »).
GENRE_TOUR = "tour"
#: Le compteur qui tourne mesure une **décision** en attente (DJ4 « temps par décision », y compris
#: quand c'est l'adversaire qui doit trancher, en plein tour de l'autre).
GENRE_DECISION = "decision"

#: Les deux genres reconnus. Un genre hors de cet ensemble est refusé (D9, jamais deviné).
GENRES: frozenset[str] = frozenset({GENRE_TOUR, GENRE_DECISION})

# --- Causes d'expiration (ce que renvoie ``pbm_game.horloges.calcul.premiere_echeance``) -----
#: L'horloge **par tour** a expiré : action par défaut = fin de tour (DJ4).
CAUSE_TOUR = "tour"
#: L'horloge **par décision** a expiré : action par défaut = réponse par défaut de la demande (DJ4).
CAUSE_DECISION = "decision"
#: Le **budget total** du joueur est épuisé : aucune action par défaut n'a de sens → défaite au
#: temps (DJ4 « sinon défaite au temps »).
CAUSE_BUDGET = "budget"


def _positif(nom: str, valeur: object, *, strict: bool) -> float:
    """Valide qu'une durée est un nombre ≥ 0 (``strict`` : > 0) et la renvoie en ``float``.

    Lève ``ValueError`` sinon : une durée absurde est une panne de configuration, jamais un repli
    silencieux sur une valeur « raisonnable ».
    """
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        raise ValueError(f"Horloges : « {nom} » doit être un nombre, reçu {valeur!r}.")
    v = float(valeur)
    if strict and v <= 0:
        raise ValueError(f"Horloges : « {nom} » doit être > 0 (reçu {v}).")
    if not strict and v < 0:
        raise ValueError(f"Horloges : « {nom} » doit être ≥ 0 (reçu {v}).")
    return v


@dataclass(frozen=True)
class ConfigHorloges:
    """Les durées des trois horloges et les deux marges (secondes) — **de la configuration**.

    Elle voyage dans l'état (:class:`EtatHorloges`) : changer les durées côté serveur (variables
    d'environnement) ne touche pas une partie déjà lancée, qui garde la config qu'elle a reçue à sa
    création — et aucune durée n'est codée en dur dans le moteur (critère d'acceptation du lot).
    """

    par_tour_s: float
    par_joueur_s: float
    par_decision_s: float
    tolerance_reseau_s: float = 0.0
    pause_deconnexion_s: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "par_tour_s", _positif("par_tour_s", self.par_tour_s, strict=True))
        object.__setattr__(
            self, "par_joueur_s", _positif("par_joueur_s", self.par_joueur_s, strict=True)
        )
        object.__setattr__(
            self, "par_decision_s", _positif("par_decision_s", self.par_decision_s, strict=True)
        )
        object.__setattr__(
            self,
            "tolerance_reseau_s",
            _positif("tolerance_reseau_s", self.tolerance_reseau_s, strict=False),
        )
        object.__setattr__(
            self,
            "pause_deconnexion_s",
            _positif("pause_deconnexion_s", self.pause_deconnexion_s, strict=False),
        )

    def limite(self, genre: str) -> float:
        """La limite (secondes) de l'horloge courte du ``genre`` donné, **hors** tolérance."""
        if genre == GENRE_TOUR:
            return self.par_tour_s
        if genre == GENRE_DECISION:
            return self.par_decision_s
        raise ValueError(f"Genre d'horloge inconnu : {genre!r} (connus : {sorted(GENRES)}).")

    def en_json(self) -> dict:
        return {
            "par_tour_s": self.par_tour_s,
            "par_joueur_s": self.par_joueur_s,
            "par_decision_s": self.par_decision_s,
            "tolerance_reseau_s": self.tolerance_reseau_s,
            "pause_deconnexion_s": self.pause_deconnexion_s,
        }

    @staticmethod
    def depuis_json(donnees: object) -> ConfigHorloges:
        if not isinstance(donnees, dict):
            raise ValueError("ConfigHorloges : un mapping est attendu.")
        return ConfigHorloges(
            par_tour_s=donnees.get("par_tour_s"),
            par_joueur_s=donnees.get("par_joueur_s"),
            par_decision_s=donnees.get("par_decision_s"),
            tolerance_reseau_s=donnees.get("tolerance_reseau_s", 0.0),
            pause_deconnexion_s=donnees.get("pause_deconnexion_s", 0.0),
        )


@dataclass(frozen=True)
class CompteurActif:
    """Le compteur qui **tourne** en ce moment : pour qui, de quel genre, depuis quand.

    ``depuis`` est l'**instant de départ** (époque en secondes) du compteur courant : le temps
    écoulé se calcule ``maintenant - depuis``, jamais par un minuteur vivant. Un seul compteur
    tourne à la fois (le tour du joueur actif, **ou** une décision en attente).
    """

    joueur: str
    genre: str
    depuis: float

    def __post_init__(self) -> None:
        if not self.joueur:
            raise ValueError("CompteurActif : un joueur est requis.")
        if self.genre not in GENRES:
            raise ValueError(
                f"CompteurActif : genre {self.genre!r} inconnu (connus : {sorted(GENRES)})."
            )
        if isinstance(self.depuis, bool) or not isinstance(self.depuis, (int, float)):
            raise ValueError(
                f"CompteurActif : « depuis » doit être un instant, reçu {self.depuis!r}."
            )
        object.__setattr__(self, "depuis", float(self.depuis))

    def en_json(self) -> dict:
        return {"joueur": self.joueur, "genre": self.genre, "depuis": self.depuis}

    @staticmethod
    def depuis_json(donnees: object) -> CompteurActif:
        if not isinstance(donnees, dict):
            raise ValueError("CompteurActif : un mapping est attendu.")
        return CompteurActif(
            joueur=donnees.get("joueur", ""),
            genre=donnees.get("genre", ""),
            depuis=donnees.get("depuis", 0.0),
        )


@dataclass(frozen=True)
class EtatHorloges:
    """L'état des horloges d'une partie — **sérialisable**, porté par la partie, repris après un F5.

    * ``config`` — les durées (voyagent avec l'état : la config d'une partie ne change pas en vol) ;
    * ``budgets_s`` — pour chaque joueur, le **budget total restant** (secondes). Débité à chaque
      bascule de compteur, borné à 0 : c'est le plafond dur « temps par joueur » (DJ4) ;
    * ``actif`` — le :class:`CompteurActif` qui tourne, ou ``None`` quand rien ne décompte (partie
      terminée) ;
    * ``pause_depuis`` / ``pause_joueur`` — quand un joueur s'est déconnecté : l'instant de début de
      la pause (les horloges sont **gelées** tant qu'il est non ``None``) et qui s'est déconnecté.
      C'est ce qui donne l'affichage honnête « l'adversaire s'est déconnecté, 1 min 47 ».

    Aucun minuteur : tout se recalcule depuis ``maintenant`` (les fonctions de
    :mod:`pbm_game.horloges.calcul`).
    """

    config: ConfigHorloges
    budgets_s: dict[str, float] = field(default_factory=dict)
    actif: CompteurActif | None = None
    pause_depuis: float | None = None
    pause_joueur: str | None = None
    schema_version: int = SCHEMA_HORLOGES_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.budgets_s, dict):
            raise ValueError("EtatHorloges : « budgets_s » doit être un mapping joueur → secondes.")
        budgets = {}
        for jid, v in self.budgets_s.items():
            if not isinstance(jid, str) or not jid:
                raise ValueError(f"EtatHorloges : identifiant de joueur invalide {jid!r}.")
            budgets[jid] = _positif(f"budgets_s[{jid}]", v, strict=False)
        object.__setattr__(self, "budgets_s", budgets)
        if (self.pause_depuis is None) != (self.pause_joueur is None):
            raise ValueError(
                "EtatHorloges : « pause_depuis » et « pause_joueur » vont ensemble (ou aucun)."
            )

    @property
    def en_pause(self) -> bool:
        """Vrai si une pause de déconnexion gèle les horloges."""
        return self.pause_depuis is not None

    def en_json(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "config": self.config.en_json(),
            "budgets_s": dict(self.budgets_s),
            "actif": self.actif.en_json() if self.actif is not None else None,
            "pause_depuis": self.pause_depuis,
            "pause_joueur": self.pause_joueur,
        }

    @staticmethod
    def depuis_json(donnees: object) -> EtatHorloges:
        """Relit un ``dict`` produit par :meth:`en_json`. Refuse une version inconnue (D9)."""
        if not isinstance(donnees, dict):
            raise ValueError("EtatHorloges : un mapping est attendu à la racine.")
        version = donnees.get("schema_version")
        if version != SCHEMA_HORLOGES_VERSION:
            raise ValueError(
                f"EtatHorloges : schema_version inconnue {version!r} "
                f"(ce moteur lit {SCHEMA_HORLOGES_VERSION})."
            )
        actif_brut = donnees.get("actif")
        return EtatHorloges(
            config=ConfigHorloges.depuis_json(donnees.get("config")),
            budgets_s=dict(donnees.get("budgets_s", {})),
            actif=CompteurActif.depuis_json(actif_brut) if actif_brut is not None else None,
            pause_depuis=donnees.get("pause_depuis"),
            pause_joueur=donnees.get("pause_joueur"),
            schema_version=version,
        )

    def avec(self, **remplacements: object) -> EtatHorloges:
        """Sucre immuable : une copie avec les champs remplacés (``dataclasses.replace``)."""
        return replace(self, **remplacements)


__all__ = [
    "SCHEMA_HORLOGES_VERSION",
    "GENRE_TOUR",
    "GENRE_DECISION",
    "GENRES",
    "CAUSE_TOUR",
    "CAUSE_DECISION",
    "CAUSE_BUDGET",
    "ConfigHorloges",
    "CompteurActif",
    "EtatHorloges",
]
