"""La **couverture d'effets scriptés hors DSL** : Outils, Stades et talents activés (lot
`j-effets-cablage-service`).

Tous les effets de carte ne sont pas écrits dans le **langage DSL** du registre `card_scripts`. Deux
familles le sont dans le **moteur**, en Python pur, scriptées et testées (D9) :

* les **Outils** et les **Stades** : leur effet est *continu* (un producteur de
  :mod:`pbm_game.effets.outils` / :mod:`pbm_game.effets.stades`), dérivé de ce qui est en jeu — il
  ne s'exprime pas en instructions DSL. La « couverture » d'un tel effet est l'existence d'un
  producteur réel pour sa ``ref`` ;
* les **talents activés** : leur *fiche* (nature, règle, états désactivants) ne vit nulle part dans
  le catalogue TCGdex ; elle est **écrite à la main** ici, et leur script reste du DSL (porté par la
  fiche, pour que le talent soit auto-suffisant).

Ce module est la **source unique** de ces deux savoirs, partagée par :

* la porte D9 du deck (:mod:`pbm_api.jeu.scripts.chargeur`) — un effet d'Outil/Stade/talent couvert
  ici n'exige **pas** de ligne `card_scripts` : il est déjà scripté et testé, ailleurs ;
* l'assemblage du :class:`~pbm_game.actions.familles_jeu.CatalogueJeu`
  (:mod:`pbm_api.games.catalogue_jeu`) — c'est d'ici que viennent le ``registre_continus`` et les
  fiches de talents d'une partie.

Il vit dans `apps/api` : il importe le moteur (pur) pour en lire les ``ref`` couvertes, mais le
moteur, lui, n'importe jamais ce module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from pbm_game.effets.outils import registre_outils
from pbm_game.effets.stades import registre_stades
from pbm_game.effets.talents import NATURE_ACTIVE, Talent

from pbm_api.jeu.scripts.empreinte import ORIGINE_DRESSEUR, ORIGINE_TALENT


@lru_cache(maxsize=1)
def refs_outils() -> frozenset[str]:
    """Les ``ref`` des Outils réellement scriptés dans le moteur (``registre_outils``).

    Les clés du registre sont des constantes (``B2-147``…), indépendantes de la métadonnée : on
    passe donc ``{}``. Mémoïsé — l'ensemble ne change pas d'un appel à l'autre.
    """
    return frozenset(registre_outils({}).keys())


@lru_cache(maxsize=1)
def refs_stades() -> frozenset[str]:
    """Les ``ref`` des Stades réellement scriptés dans le moteur (``registre_stades``)."""
    return frozenset(registre_stades({}).keys())


@dataclass(frozen=True)
class FicheTalentActive:
    """Fiche **écrite à la main** d'un talent **activé** d'une carte réelle (ce que le catalogue ne
    porte pas).

    * ``nom`` — libellé lisible (journal, étiquette du coup) ;
    * ``regle`` — l'identifiant ``R-x.y`` que le talent sert (jamais vide, D9) ;
    * ``programme`` — le script DSL (``{version, effets, cout?}``) qui **fait** le talent, fidèle au
      texte de la carte (D9) ;
    * ``desactive_si_etat`` — les états spéciaux qui désactivent le talent (⊆ R-11.1) ;
    * ``depuis_banc`` — le talent agit-il depuis le banc (défaut) ou seulement en Actif.
    """

    nom: str
    regle: str
    programme: dict
    desactive_si_etat: frozenset[str] = field(default_factory=frozenset)
    depuis_banc: bool = True

    def talent(self, ref: str) -> Talent:
        """La fiche :class:`~pbm_game.effets.talents.Talent` du moteur pour la ``ref`` porteuse."""
        return Talent(
            ref=ref,
            nom=self.nom,
            nature=NATURE_ACTIVE,
            regle=self.regle,
            desactive_si_etat=frozenset(self.desactive_si_etat),
            depuis_banc=self.depuis_banc,
        )


#: Les talents **activés** écrits à la main, par ``ref`` (``tcgdex_id``) de la carte porteuse.
#: C'est le **point d'extension** du jeu pour les talents activés : y ajouter une carte, c'est y
#: ajouter sa fiche et son script DSL (fidèle au texte, D9). Vide, aucun talent n'est jouable —
#: jamais deviné. Radiant Greninja « Cartes Cachées » (Concealed Cards, Astral Radiance) : une fois
#: par tour, défaussez une Énergie de votre main pour piocher 2 cartes.
TALENTS_ACTIVES: dict[str, FicheTalentActive] = {
    "swsh12-46": FicheTalentActive(
        nom="Cartes Cachées",
        regle="R-5",
        programme={
            "version": 1,
            "cout": [
                {
                    "op": "defausser",
                    "cible": {
                        "zone": "main",
                        "proprietaire": "moi",
                        "categorie": "energie",
                        "nombre": 1,
                    },
                }
            ],
            "effets": [{"op": "piocher", "nombre": 2}],
        },
    ),
}


def fiche_talent_active(ref: str) -> FicheTalentActive | None:
    """La fiche du talent activé porté par la ``ref``, ou ``None`` (aucun talent activé connu)."""
    return TALENTS_ACTIVES.get(ref)


def effet_couvert_hors_dsl(ref: str, origine: str) -> bool:
    """Cet effet est-il scripté **hors** du registre DSL (moteur ou fiche écrite à la main) ?

    Vrai pour l'effet *Dresseur* d'un Outil/Stade dont la ``ref`` a un producteur moteur, et pour
    l'effet *talent* d'une carte dont la ``ref`` a une fiche de talent activé. La porte D9 du deck
    n'exige alors **pas** de ligne `card_scripts` : l'effet est déjà scripté et testé ailleurs. Tout
    autre effet (Objet, Supporter, attaque, talent inconnu) reste du ressort de `card_scripts`.
    """
    if origine == ORIGINE_DRESSEUR:
        return ref in refs_outils() or ref in refs_stades()
    if origine == ORIGINE_TALENT:
        return ref in TALENTS_ACTIVES
    return False


__all__ = [
    "refs_outils",
    "refs_stades",
    "FicheTalentActive",
    "TALENTS_ACTIVES",
    "fiche_talent_active",
    "effet_couvert_hors_dsl",
]
