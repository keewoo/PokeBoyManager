"""Les **effets continus** — des modificateurs *consultés au calcul*, jamais des mutations.

Module **pur** (aucune E/S). C'est le cœur du lot, et le piège qu'il évite est nommé dans la
fiche : *appliquer l'effet d'un Stade au moment où il est joué (mutation) au lieu de le
consulter au calcul — son remplacement laisse alors des traces indélébiles.*

**Le principe, en une phrase : un effet continu n'existe nulle part dans l'état ; il se
*dérive* de ce qui est en jeu.** Un Outil attaché, un Stade posé, un talent d'un Pokémon en
jeu : au moment d'un calcul de dégâts (ou d'un seuil de K.O.), on **relit** ces sources et on
en tire des :class:`~pbm_game.combat.modele.Modificateur`. Retirer l'Outil, remplacer le
Stade, faire quitter le Pokémon : la source disparaît, donc le modificateur n'est plus produit,
donc le calcul **revient exactement à l'état antérieur** — sans rien avoir à « défaire ». C'est
le critère d'acceptation n°2, et il est vrai *par construction*, pas par discipline.

Ce lot livre le **cadre** ; il ne script aucune carte (D9). Le :class:`RegistreContinus` est
**vide par défaut** : les lots ``j-cartes-outils``, ``j-cartes-stades`` et ``j-cartes-talents``
y enregistrent leurs producteurs, chacun scripté et testé. Les tests de ce lot utilisent des
producteurs *jouets* pour prouver que le cadre tient.

Règles servies : **R-3.5** (le remplacement d'un Stade met fin à son effet), **R-3.7** (l'Outil
et son effet), **R-10.1/2** (les modificateurs s'insèrent dans l'ordre officiel du calcul),
**R-13.1** (le seuil de K.O. dépend des PV, que les PV continus modifient).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..combat.modele import Modificateur
from ..state.modele import EtatPartie, carte_active
from .pile import SourceEffet

# --- Portées d'un effet continu (combien de temps sa source le fait vivre) ----
#: Tant que l'**Outil** reste attaché à son porteur (R-3.7).
PORTEE_OUTIL = "tant_que_outil_attache"
#: Tant que le **Stade** reste en jeu (R-3.5) — partagé par les deux joueurs.
PORTEE_STADE = "tant_que_stade_en_jeu"
#: Tant que le Pokémon reste **Actif** (certains talents n'agissent que depuis l'Actif).
PORTEE_ACTIF = "tant_que_actif"
#: Tant que le Pokémon reste **en jeu**, banc compris (talents de banc).
PORTEE_EN_JEU = "tant_que_en_jeu"

PORTEES: frozenset[str] = frozenset({PORTEE_OUTIL, PORTEE_STADE, PORTEE_ACTIF, PORTEE_EN_JEU})

# --- Face d'un modificateur de dégâts continu ---------------------------------
#: Le modificateur s'applique **côté attaquant** (``modificateurs_attaquant`` de
#: :func:`~pbm_game.combat.resolution.resoudre_degats`, R-10.1 étape 2).
FACE_ATTAQUANT = "attaquant"
#: Le modificateur s'applique **côté défenseur** (``modificateurs_defenseur``, R-10.1 étape 5).
FACE_DEFENSEUR = "defenseur"


@dataclass(frozen=True)
class EffetContinu:
    """Ce qu'une source en jeu **contribue** au calcul, tant qu'elle y est.

    Une contribution est soit un **modificateur de dégâts** (``modificateur`` + ``face``), soit
    un **delta de PV** (``pv`` ≠ 0, qui déplace le seuil de K.O.), soit un **delta de coût de
    retraite** (``cout_retraite`` ≠ 0, type *Stade*, R-8.2), ou plusieurs à la fois. ``cible`` est
    l'identité stable (``instance_id`` de carte de base) du Pokémon concerné : côté PV, c'est
    lui dont le seuil change ; côté dégâts, c'est lui qui attaque (``FACE_ATTAQUANT``) ou qui
    défend (``FACE_DEFENSEUR``). ``source`` nomme la carte responsable (journal), ``portee``
    dit ce qui le maintient en vie.
    """

    libelle: str
    regle: str
    source: SourceEffet
    portee: str
    cible: str | None = None
    modificateur: Modificateur | None = None
    face: str | None = None
    pv: int = 0
    cout_retraite: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.libelle, str) or not self.libelle.strip():
            raise ValueError("Un effet continu doit porter un libellé lisible.")
        if not isinstance(self.regle, str) or not self.regle.strip():
            raise ValueError("Un effet continu doit citer la règle R-x.y qu'il applique (D9).")
        if self.portee not in PORTEES:
            raise ValueError(
                f"Portée d'effet continu inconnue : {self.portee!r} — jamais approximée (D9). "
                f"Connues : {sorted(PORTEES)}."
            )
        if self.modificateur is not None and self.face not in (FACE_ATTAQUANT, FACE_DEFENSEUR):
            raise ValueError(
                f"Un modificateur continu doit dire sa face ({FACE_ATTAQUANT}/{FACE_DEFENSEUR}), "
                f"reçu {self.face!r}."
            )
        if self.modificateur is None and self.pv == 0 and self.cout_retraite == 0:
            raise ValueError(
                "Un effet continu ne contribue rien : ni modificateur de dégâts, ni delta "
                "de PV, ni delta de coût de retraite."
            )
        if not isinstance(self.pv, int) or isinstance(self.pv, bool):
            raise ValueError(f"Delta de PV continu invalide : {self.pv!r} (entier).")
        if not isinstance(self.cout_retraite, int) or isinstance(self.cout_retraite, bool):
            raise ValueError(
                f"Delta de coût de retraite continu invalide : {self.cout_retraite!r} (entier)."
            )


# Un producteur lit l'état et rend les effets continus d'**une** source précise. Il reçoit
# ``(etat, ref, cible)`` : ``cible`` est l'identité stable du Pokémon porteur, ou ``None`` pour
# une source sans propriétaire (le Stade, dont l'effet frappe les deux camps). Pur.
ProducteurContinu = Callable[[EtatPartie, str, "str | None"], list[EffetContinu]]

#: Registre des producteurs d'effets continus, **par référence catalogue**. Vide par défaut
#: (D9) : les lots de cartes l'alimentent. La clé est la ``ref`` de la carte (un Outil, un
#: Stade ou le sommet d'un Pokémon porteur de talent).
RegistreContinus = dict[str, ProducteurContinu]


def _identite(pokemon) -> str:
    return pokemon.cartes[0].instance_id


def collecter_effets_continus(
    etat: EtatPartie, registre: RegistreContinus
) -> list[EffetContinu]:
    """Relit **tout ce qui est en jeu** et en dérive la liste des effets continus actifs.

    Parcours déterministe : le Stade, puis chaque joueur dans l'ordre, pour chacun l'Actif puis
    le banc, et pour chaque Pokémon son **talent** (sommet de pile) puis son **Outil**. Un
    producteur reçoit ``(etat, ref, cible)`` où ``cible`` est l'identité stable du Pokémon
    concerné (chaîne vide pour le Stade, qui n'appartient à personne). Une source sans
    producteur enregistré ne contribue rien — c'est l'absence réelle d'effet (D9), pas un
    silence : la carte n'est jouable que lorsque son effet est scripté.

    Le point clé : cette fonction **ne lit que l'état courant**. Retirer une source de l'état
    (Outil défaussé, Stade remplacé) la fait disparaître d'ici au calcul suivant, sans rien
    défaire.
    """
    effets: list[EffetContinu] = []

    if etat.stade is not None and etat.stade.ref in registre:
        # Le Stade n'appartient à personne (R-3.5) : ``cible=None`` = effet global, les deux camps.
        effets.extend(registre[etat.stade.ref](etat, etat.stade.ref, None))

    for joueur in etat.joueurs:
        pokemons = ((joueur.actif,) if joueur.actif is not None else ()) + joueur.banc
        for pokemon in pokemons:
            cible = _identite(pokemon)
            ref_talent = carte_active(pokemon).ref
            if ref_talent in registre:
                effets.extend(registre[ref_talent](etat, ref_talent, cible))
            if pokemon.outil is not None and pokemon.outil.ref in registre:
                effets.extend(registre[pokemon.outil.ref](etat, pokemon.outil.ref, cible))

    return effets


def modificateurs_degats(
    effets: list[EffetContinu], *, attaquant: str, defenseur: str
) -> tuple[list[Modificateur], list[Modificateur]]:
    """Trie les modificateurs continus pour une attaque donnée en ``(attaquant, defenseur)``.

    Un effet ``FACE_ATTAQUANT`` rejoint les modificateurs de l'attaquant (R-10.1 étape 2) s'il
    cible ``attaquant`` **ou s'il est global** (``cible=None`` : un Stade qui touche les deux
    camps) ; un effet ``FACE_DEFENSEUR`` rejoint ceux du défenseur (étape 5) selon la même règle.
    Les effets ciblant un Pokémon absent de ce combat sont ignorés — ils ne le concernent pas.
    Prêt à passer tel quel à :func:`~pbm_game.combat.resolution.resoudre_degats`.
    """
    att: list[Modificateur] = []
    deff: list[Modificateur] = []
    for e in effets:
        if e.modificateur is None:
            continue
        if e.face == FACE_ATTAQUANT and e.cible in (None, attaquant):
            att.append(e.modificateur)
        elif e.face == FACE_DEFENSEUR and e.cible in (None, defenseur):
            deff.append(e.modificateur)
    return att, deff


def delta_pv(effets: list[EffetContinu], pokemon: str) -> int:
    """La somme des **deltas de PV** continus qui s'appliquent au Pokémon ``pokemon`` (R-13.1)."""
    return sum(e.pv for e in effets if e.cible == pokemon and e.pv)


def seuil_ko(pv_imprime: int, effets: list[EffetContinu], pokemon: str) -> int:
    """Le **seuil de K.O.** d'un Pokémon : ses PV imprimés + les deltas de PV continus (R-13.1).

    C'est ce seuil — et non les compteurs déjà posés — que les PV supplémentaires d'un Outil
    déplacent (fiche ``j-cartes-outils``). Retirer l'Outil le fait redescendre : si les
    compteurs le dépassent alors, le Pokémon est K.O. immédiatement (vérifié par l'appelant,
    lot ``j-cartes-outils``). Ne descend jamais sous 0 (un Pokémon a au moins 0 PV).
    """
    if not isinstance(pv_imprime, int) or isinstance(pv_imprime, bool) or pv_imprime < 0:
        raise ValueError(f"PV imprimés invalides : {pv_imprime!r} (entier ≥ 0).")
    return max(0, pv_imprime + delta_pv(effets, pokemon))


def delta_cout_retraite(effets: list[EffetContinu], pokemon: str) -> int:
    """La somme des **deltas de coût de retraite** continus qui pèsent sur ``pokemon`` (R-8.2).

    Un Stade (``cible=None``) frappe les **deux camps** : son delta s'applique à n'importe quel
    Pokémon, exactement comme un modificateur de dégâts global (:func:`modificateurs_degats`). Un
    effet ciblé (``cible`` renseignée) ne compte que pour ce Pokémon-là. C'est ainsi qu'un Stade
    « le Coût de Retraite de chaque Pokémon est diminué de 1 » touche l'Actif des deux joueurs.
    """
    return sum(
        e.cout_retraite for e in effets if e.cout_retraite and e.cible in (None, pokemon)
    )


def cout_retraite_effectif(base: int, effets: list[EffetContinu], pokemon: str) -> int:
    """Le **coût de retraite effectif** de ``pokemon`` : son coût imprimé + les deltas continus.

    ``base`` est le coût de retraite imprimé (fourni par le service depuis le catalogue, R-8.2).
    Un Stade peut l'augmenter ou le diminuer pour les deux camps ; retirer le Stade (remplacer
    ``etat.stade``) fait disparaître le delta au calcul suivant, sans rien défaire — le coût
    revient *par construction* à sa valeur imprimée. Ne descend jamais sous 0 (un coût de retraite
    négatif n'existe pas : au plancher, la retraite est gratuite).
    """
    if not isinstance(base, int) or isinstance(base, bool) or base < 0:
        raise ValueError(f"Coût de retraite imprimé invalide : {base!r} (entier ≥ 0, R-8.2).")
    return max(0, base + delta_cout_retraite(effets, pokemon))


__all__ = [
    "PORTEE_OUTIL",
    "PORTEE_STADE",
    "PORTEE_ACTIF",
    "PORTEE_EN_JEU",
    "PORTEES",
    "FACE_ATTAQUANT",
    "FACE_DEFENSEUR",
    "EffetContinu",
    "ProducteurContinu",
    "RegistreContinus",
    "collecter_effets_continus",
    "modificateurs_degats",
    "delta_pv",
    "seuil_ko",
    "delta_cout_retraite",
    "cout_retraite_effectif",
]
