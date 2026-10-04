"""Les **dégâts variables** d'une attaque — « 20 dégâts par énergie attachée », etc. (R-10.1).

Module **pur** (aucune E/S), comme tout ``pbm_game.combat``. Certaines attaques n'ont pas de
dégâts **secs** : leur base se **calcule** au moment de la résolution, à partir de l'état — nombre
d'énergies attachées, cartes en main, PV manquants, compteurs posés, récompenses restantes, Pokémon
de banc. :class:`ValeurDynamique` porte cette formule en **donnée** (comme un script d'effet), et
:meth:`ValeurDynamique.evaluer` la résout contre l'état.

**Pourquoi au moment de la résolution, et pas de la déclaration (le piège de la fiche).** Un joueur
qui défausse une énergie *entre* la déclaration et la résolution obtiendrait sinon un résultat faux.
La base est donc lue ici, juste avant le calcul des dégâts (``pbm_game.combat.attaque``), sur l'état
**courant** — jamais figée à la déclaration.

**D9 — rien n'est deviné.** Un compteur hors de l'ensemble fermé :data:`COMPTEURS`, une cible qui
ne va pas avec le compteur (compter les énergies « de la main »…), un ``par``/``base`` non entier :
tout cela **lève** au chargement (:class:`ValeurInvalide`), jamais un calcul « au mieux ». La
formule est ``max(0, base + par × compte)``, bornée par ``plafond`` s'il est donné.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..state.modele import EtatPartie, Joueur, PokemonEnJeu

# --- Les compteurs reconnus (ce qu'on sait compter dans l'état) ---------------
#: Énergies attachées à un Pokémon (``cible`` = ``attaquant`` / ``defenseur``).
COMPTE_ENERGIES = "energies"
#: Cartes dans la main d'un joueur (``cible`` = ``moi`` / ``adversaire``).
COMPTE_CARTES_EN_MAIN = "cartes_en_main"
#: PV manquants d'un Pokémon — ses compteurs de dégâts, en PV (``cible`` = Pokémon).
COMPTE_PV_MANQUANTS = "pv_manquants"
#: Marqueurs (compteurs de dégâts) posés sur un Pokémon, en **nombre** (PV ÷ 10).
COMPTE_MARQUEURS = "marqueurs"
#: Récompenses qu'il reste à prendre à un joueur (``cible`` = ``moi`` / ``adversaire``).
COMPTE_RECOMPENSES = "recompenses_restantes"
#: Pokémon sur le banc d'un joueur (``cible`` = ``moi`` / ``adversaire``).
COMPTE_POKEMON_BANC = "pokemon_banc"

#: Compteurs qui portent sur un **Pokémon** (cible attaquant/defenseur).
_COMPTEURS_POKEMON: frozenset[str] = frozenset(
    {COMPTE_ENERGIES, COMPTE_PV_MANQUANTS, COMPTE_MARQUEURS}
)
#: Compteurs qui portent sur un **joueur** (cible moi/adversaire).
_COMPTEURS_JOUEUR: frozenset[str] = frozenset(
    {COMPTE_CARTES_EN_MAIN, COMPTE_RECOMPENSES, COMPTE_POKEMON_BANC}
)
#: L'ensemble **fermé** des compteurs (D9 : un compteur hors liste est refusé, jamais deviné).
COMPTEURS: frozenset[str] = _COMPTEURS_POKEMON | _COMPTEURS_JOUEUR

# --- Les cibles d'un compteur -------------------------------------------------
CIBLE_ATTAQUANT = "attaquant"  # le Pokémon qui attaque
CIBLE_DEFENSEUR = "defenseur"  # le Pokémon Actif adverse
CIBLE_MOI = "moi"  # le joueur qui attaque
CIBLE_ADVERSAIRE = "adversaire"  # l'autre joueur

_CIBLES_POKEMON: frozenset[str] = frozenset({CIBLE_ATTAQUANT, CIBLE_DEFENSEUR})
_CIBLES_JOUEUR: frozenset[str] = frozenset({CIBLE_MOI, CIBLE_ADVERSAIRE})
CIBLES: frozenset[str] = _CIBLES_POKEMON | _CIBLES_JOUEUR


class ValeurInvalide(ValueError):
    """Une description de dégâts variables non conforme — refusée au chargement, pas à l'usage."""


@dataclass(frozen=True)
class ValeurDynamique:
    """Une base de dégâts **calculée** depuis l'état : ``max(0, base + par × compte)``, bornée.

    * ``compter`` — un des :data:`COMPTEURS` (ce qu'on compte) ;
    * ``cible`` — sur quoi on compte (:data:`CIBLES`) ; par défaut ``attaquant`` pour un compteur
      de Pokémon, ``moi`` pour un compteur de joueur ;
    * ``par`` — les dégâts ajoutés **par unité** comptée (p. ex. 20 par énergie) ;
    * ``base`` — des dégâts secs ajoutés en plus (``0`` par défaut) ;
    * ``plafond`` — un maximum facultatif (« au plus 120 »), ``None`` = sans plafond.

    Le résultat est planché à 0 et, s'il est donné, borné à ``plafond`` — jamais négatif, jamais
    au-delà de ce que la carte annonce. La validation **mord** à la construction (D9).
    """

    compter: str
    par: int
    cible: str
    base: int = 0
    plafond: int | None = None

    def __post_init__(self) -> None:
        if self.compter not in COMPTEURS:
            raise ValeurInvalide(
                f"Compteur de dégâts variables inconnu : {self.compter!r} — jamais deviné (D9). "
                f"Connus : {sorted(COMPTEURS)}."
            )
        if self.cible not in CIBLES:
            raise ValeurInvalide(
                f"Cible de comptage inconnue : {self.cible!r} (connues : {sorted(CIBLES)})."
            )
        if self.compter in _COMPTEURS_POKEMON and self.cible not in _CIBLES_POKEMON:
            raise ValeurInvalide(
                f"Le compteur « {self.compter} » porte sur un Pokémon : cible "
                f"{sorted(_CIBLES_POKEMON)} attendue, reçu {self.cible!r}."
            )
        if self.compter in _COMPTEURS_JOUEUR and self.cible not in _CIBLES_JOUEUR:
            raise ValeurInvalide(
                f"Le compteur « {self.compter} » porte sur un joueur : cible "
                f"{sorted(_CIBLES_JOUEUR)} attendue, reçu {self.cible!r}."
            )
        for nom, v in (("par", self.par), ("base", self.base)):
            if not isinstance(v, int) or isinstance(v, bool):
                raise ValeurInvalide(
                    f"Dégâts variables : « {nom} » doit être un entier, reçu {v!r}."
                )
        if self.par < 0 or self.base < 0:
            raise ValeurInvalide("Dégâts variables : « par » et « base » doivent être ≥ 0.")
        if self.plafond is not None and (
            not isinstance(self.plafond, int) or isinstance(self.plafond, bool) or self.plafond < 0
        ):
            raise ValeurInvalide(f"Dégâts variables : « plafond » invalide {self.plafond!r} (≥ 0).")

    def evaluer(self, etat: EtatPartie, *, attaquant: str, adversaire: str) -> int:
        """Résout la formule contre ``etat`` — ``attaquant``/``adversaire`` nomment les joueurs.

        Lit l'état **courant** (jamais une valeur figée à la déclaration) ; renvoie un entier ≥ 0,
        borné par ``plafond``. Une cible absente (pas d'Actif adverse, p. ex.) compte **0** — un
        effet sans substrat ne fabrique pas de dégâts, il n'en fait pas (jamais une panne ici).
        """
        compte = self._compter(etat, attaquant=attaquant, adversaire=adversaire)
        valeur = self.base + self.par * compte
        if valeur < 0:
            valeur = 0
        if self.plafond is not None and valeur > self.plafond:
            valeur = self.plafond
        return valeur

    def _joueur(self, etat: EtatPartie, jid: str) -> Joueur:
        for j in etat.joueurs:
            if j.id == jid:
                return j
        raise ValueError(f"Joueur « {jid} » absent de la partie (dégâts variables).")

    def _pokemon_cible(
        self, etat: EtatPartie, *, attaquant: str, adversaire: str
    ) -> PokemonEnJeu | None:
        jid = attaquant if self.cible == CIBLE_ATTAQUANT else adversaire
        return self._joueur(etat, jid).actif

    def _compter(self, etat: EtatPartie, *, attaquant: str, adversaire: str) -> int:
        if self.compter in _COMPTEURS_POKEMON:
            pok = self._pokemon_cible(etat, attaquant=attaquant, adversaire=adversaire)
            if pok is None:
                return 0
            if self.compter == COMPTE_ENERGIES:
                return len(pok.energies)
            if self.compter == COMPTE_PV_MANQUANTS:
                return pok.compteurs_degats
            return pok.compteurs_degats // 10  # COMPTE_MARQUEURS
        jid = attaquant if self.cible == CIBLE_MOI else adversaire
        joueur = self._joueur(etat, jid)
        if self.compter == COMPTE_CARTES_EN_MAIN:
            return len(joueur.main)
        if self.compter == COMPTE_RECOMPENSES:
            return len(joueur.recompenses)
        return len(joueur.banc)  # COMPTE_POKEMON_BANC

    def en_json(self) -> dict:
        """La formule en valeurs JSON natives — l'inverse de :func:`valeur_depuis`."""
        donnees: dict = {"compter": self.compter, "par": self.par, "cible": self.cible}
        if self.base:
            donnees["base"] = self.base
        if self.plafond is not None:
            donnees["plafond"] = self.plafond
        return donnees


def est_valeur_dynamique(brut: object) -> bool:
    """Vrai si ``brut`` décrit des dégâts **variables** (un mapping), plutôt qu'un entier sec."""
    return isinstance(brut, Mapping)


def valeur_depuis(brut: object) -> ValeurDynamique:
    """Construit une :class:`ValeurDynamique` depuis un mapping (params d'action, catalogue).

    Défaut de ``cible`` : ``attaquant`` pour un compteur de Pokémon, ``moi`` pour un compteur de
    joueur — la cible la plus fréquente, mais toujours surchargeable. Lève :class:`ValeurInvalide`
    sur un mapping non conforme (D9).
    """
    if not isinstance(brut, Mapping):
        raise ValeurInvalide("Des dégâts variables se décrivent par un mapping {compter, par, …}.")
    compter = brut.get("compter")
    cible = brut.get("cible")
    if cible is None:
        cible = CIBLE_ATTAQUANT if compter in _COMPTEURS_POKEMON else CIBLE_MOI
    return ValeurDynamique(
        compter=compter,
        par=brut.get("par", 1),
        cible=cible,
        base=brut.get("base", 0),
        plafond=brut.get("plafond"),
    )


__all__ = [
    "COMPTE_ENERGIES",
    "COMPTE_CARTES_EN_MAIN",
    "COMPTE_PV_MANQUANTS",
    "COMPTE_MARQUEURS",
    "COMPTE_RECOMPENSES",
    "COMPTE_POKEMON_BANC",
    "COMPTEURS",
    "CIBLE_ATTAQUANT",
    "CIBLE_DEFENSEUR",
    "CIBLE_MOI",
    "CIBLE_ADVERSAIRE",
    "CIBLES",
    "ValeurInvalide",
    "ValeurDynamique",
    "est_valeur_dynamique",
    "valeur_depuis",
]
