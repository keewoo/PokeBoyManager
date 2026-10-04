"""Normalisation et **empreinte** d'un texte d'effet, et extraction des effets d'une carte.

Module **pur** (aucune E/S) : il ne lit ni base ni réseau, il travaille sur des chaînes et des
objets déjà chargés. C'est le socle du registre `card_scripts` et de son regroupement.

**Pourquoi une empreinte, et pas le texte.** Des centaines de cartes portent le *même* texte
d'effet. On ne scripte pas chacune : on scripte le **texte**, repéré par l'empreinte SHA-256 de sa
forme normalisée. Deux cartes au texte identique donnent la même empreinte, donc partagent le même
script — c'est le regroupement qui réduit le travail (critère n°2 du lot).

**La normalisation décide de ce qui « change ».** Elle met les variations purement cosmétiques
(espaces, retours à la ligne, casse, forme Unicode) hors du calcul : un simple reformatage du
catalogue ne doit **pas** faire repasser un script « à revoir » (ce serait une fausse alerte
d'errata, du bruit qui use la relecture). En revanche, un mot ou un nombre qui change — une vraie
*errata* — change l'empreinte, et la carte ne se joue plus avec l'ancien script (critère n°1). Ce
choix est délibéré : on groupe au plus large sans jamais confondre deux effets réellement distincts.

**Le grain, c'est l'effet, pas la carte.** Une carte peut porter plusieurs textes (un talent, deux
attaques à effet, ou le texte d'un Dresseur). Chacun est une unité scriptable à part — un
:class:`~pbm_game.effets.dsl.modele.Programme` du langage décrit *un* effet. On groupe donc au grain
de l'effet : le talent « Fouille » est identique sur des dizaines de cartes dont les attaques
diffèrent, et un script unique le couvre toutes.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

#: Origine d'un effet sur une carte — pour nommer précisément ce qui manque dans un refus.
ORIGINE_TALENT = "talent"
ORIGINE_ATTAQUE = "attaque"
ORIGINE_DRESSEUR = "dresseur"  # couvre aussi une Énergie spéciale (même colonne `effect`)

_ESPACES = re.compile(r"\s+")


def normaliser_texte(texte: str) -> str:
    """Forme normalisée d'un texte d'effet, invariante aux variations cosmétiques.

    NFC (formes Unicode équivalentes réunies), espaces (y compris retours à la ligne et tabulations)
    réduits à une espace simple, bords rognés, casse repliée (``casefold``). Le résultat est ce qui
    « compte » : deux textes qui ne diffèrent que par la mise en forme ou la casse sont **le même**
    effet. Un texte vide ou fait d'espaces rend ``""``.
    """
    sans_accents_parasites = unicodedata.normalize("NFC", texte)
    compacte = _ESPACES.sub(" ", sans_accents_parasites).strip()
    return compacte.casefold()


def empreinte_texte(texte: str) -> str:
    """Empreinte SHA-256 (hex) de la forme normalisée d'un texte d'effet — la clé de regroupement.

    Deux textes de même forme normalisée ont la même empreinte (donc le même script). Un texte dont
    la normalisation est vide lève :class:`ValueError` : on n'enregistre pas de script « pour
    rien », et une carte sans texte d'effet n'a tout simplement aucune empreinte à exiger.
    """
    forme = normaliser_texte(texte)
    if not forme:
        raise ValueError("Texte d'effet vide : aucune empreinte à calculer.")
    return hashlib.sha256(forme.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EffetCarte:
    """Un effet scriptable d'une carte : son origine, son intitulé, son texte, son empreinte.

    ``empreinte`` est celle du texte normalisé : c'est elle qui sert de clé dans `card_scripts`.
    ``intitule`` nomme l'effet (le nom du talent ou de l'attaque) pour que le refus d'un deck dise
    *quelle* partie de la carte n'est pas scriptée, pas seulement « la carte ».
    """

    origine: str
    intitule: str
    texte: str
    empreinte: str


def _textes_d_effet(valeur: object, cle: str) -> Iterable[tuple[str, str]]:
    """Les ``(intitulé, texte)`` d'effet d'une liste JSONB d'``abilities``/``attacks``.

    Ne retient que les entrées dont le champ ``cle`` (``effect``) porte un texte non vide : une
    attaque à dégâts secs, sans texte, n'a rien à scripter. L'intitulé est le ``name`` quand il
    existe, pour nommer l'effet dans un refus.
    """
    if not isinstance(valeur, (list, tuple)):
        return
    for item in valeur:
        if not isinstance(item, Mapping):
            continue
        texte = item.get(cle)
        if isinstance(texte, str) and texte.strip():
            intitule = item.get("name")
            yield (str(intitule) if intitule else ""), texte


def effets_scriptables(card: object) -> list[EffetCarte]:
    """Les effets d'une carte qui **exigent** un script — talents, attaques à effet, Dresseurs.

    Lit les mêmes champs que l'étude du langage (``abilities[].effect``, ``attacks[].effect`` et le
    ``effect`` des Dresseurs/Énergies spéciales — cf. ``apps/game/tools/extraire_effets_dsl.sql``).
    Une carte **sans** aucun de ces textes (Pokémon aux attaques à dégâts secs, Énergie de base)
    rend une liste **vide** : elle n'a aucun effet à scripter, donc rien ne la bloque côté scripts.

    Dé-duplique par empreinte **dans la carte** : si deux textes y sont identiques après
    normalisation, ils comptent pour une seule exigence (un seul script les couvre). L'ordre de
    sortie est stable (talent, puis attaques, puis texte de Dresseur) pour un refus lisible.
    """
    brut: list[tuple[str, str, str]] = []
    for intitule, texte in _textes_d_effet(getattr(card, "abilities", None), "effect"):
        brut.append((ORIGINE_TALENT, intitule, texte))
    for intitule, texte in _textes_d_effet(getattr(card, "attacks", None), "effect"):
        brut.append((ORIGINE_ATTAQUE, intitule, texte))
    effet_dresseur = getattr(card, "effect", None)
    if isinstance(effet_dresseur, str) and effet_dresseur.strip():
        brut.append((ORIGINE_DRESSEUR, "", effet_dresseur))

    effets: list[EffetCarte] = []
    vues: set[str] = set()
    for origine, intitule, texte in brut:
        empreinte = empreinte_texte(texte)
        if empreinte in vues:
            continue
        vues.add(empreinte)
        effets.append(
            EffetCarte(origine=origine, intitule=intitule, texte=texte, empreinte=empreinte)
        )
    return effets


__all__ = [
    "ORIGINE_TALENT",
    "ORIGINE_ATTAQUE",
    "ORIGINE_DRESSEUR",
    "EffetCarte",
    "normaliser_texte",
    "empreinte_texte",
    "effets_scriptables",
]
