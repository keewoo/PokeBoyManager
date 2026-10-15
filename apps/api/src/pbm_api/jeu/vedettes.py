"""Le registre des Pokémon vedettes — qui a une apparition, et ce qu'elle vaut.

DJ3 prévoit « une liste restreinte de Pokémon vedettes » : ce module en est la source unique, et
elle est **versionnée** (``apparitions.json``), pas devinée à l'exécution.

**Pourquoi un fichier et pas une table.** Trois raisons, dans l'ordre d'importance :

1. *Le serveur doit répondre sans chercher.* Une vue de partie résout jusqu'à 120 cartes ; demander
   au stockage objet « cette découpe existe-t-elle ? » pour chacune ferait 120 allers-retours par
   écran. Ici l'appartenance se lit dans un ``frozenset`` en mémoire.
2. *Ce qui est annoncé doit être ce qui est servi.* Le registre n'est pas une intention : le champ
   ``publie`` est écrit par la chaîne de découpe après une production réussie, avec la note
   mesurée. Une vedette qu'on ajoute à la main sans découpe ferait tenter un chargement en 404 à
   chaque partie.
3. *Une liste éditoriale se relit.* « Les préférés d'Aymeric d'abord » est une décision humaine :
   elle doit apparaître dans une revue de code, pas dans une ligne de base de données.

Les identifiants sont des ``tcgdex_id`` (``base1-4``), **pas** des UUID de ``cards`` : les UUID sont
tirés à l'import du catalogue et diffèrent d'un environnement à l'autre, alors que le registre, lui,
est le même partout.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: Le registre, à côté du code qui le lit.
CHEMIN_REGISTRE = Path(__file__).with_name("apparitions.json")

#: Préfixe des découpes dans le stockage objet. Rangées à part des images de cartes
#: (``cards/{uuid}/…``) parce qu'elles sont nommées par ``tcgdex_id`` : un préfixe par convention
#: de nommage, pour qu'on ne cherche jamais une découpe là où elle ne peut pas être.
PREFIXE_STOCKAGE = "jeu/apparitions"

#: Forme admise d'un ``tcgdex_id``. Sert de garde sur la route : un identifiant hors de ce motif ne
#: peut pas fabriquer un chemin de stockage, et donc pas sortir du préfixe.
MOTIF_ID = re.compile(r"^[a-z0-9]+-[a-z0-9]+$")

#: La découpe a été regardée et elle est bonne — **seul** verdict qui autorise la publication.
VERDICT_ACCEPTE = "accepte"
#: Regardée et mauvaise, avec le motif à côté : elle ne sera pas publiée tant qu'elle n'est pas
#: reprise. Le motif sert au lot suivant, qui saura quoi corriger.
VERDICT_REFUSE = "refuse"
#: Personne ne l'a encore regardée. État par défaut, et il n'autorise **rien** : une découpe que la
#: note accepte mais que personne n'a vue ne part pas en production (critère du lot).
VERDICT_A_REVOIR = "a_revoir"


@dataclass(frozen=True)
class Vedette:
    """Une carte dont le Pokémon peut apparaître au-dessus d'elle."""

    tcgdex_id: str
    nom: str
    type: str
    illustration: str
    publie: bool
    #: Le verdict humain sur la découpe : ``"accepte"``, ``"refuse"`` ou ``"a_revoir"`` tant que
    #: personne ne l'a regardée. La note mesurée ne sait pas dire qu'une aile a été coupée ni qu'un
    #: morceau de fond sombre est resté accroché — seul l'œil le voit, sur la planche de contrôle.
    verdict_oeil: str
    motif_oeil: str
    note: dict


def cle_apparition(tcgdex_id: str) -> str:
    """La clé de stockage de la découpe.

    Refuse un identifiant hors motif plutôt que de l'assainir : assainir, c'est accepter une
    entrée douteuse — et cette clé est construite depuis l'URL d'une route publique.
    """
    if not MOTIF_ID.match(tcgdex_id):
        raise ValueError(f"identifiant de carte invalide : {tcgdex_id!r}")
    return f"{PREFIXE_STOCKAGE}/{tcgdex_id}.webp"


def url_apparition(tcgdex_id: str) -> str:
    """L'URL que l'écran chargera pour cette découpe."""
    return f"/img/apparitions/{tcgdex_id}"


@lru_cache(maxsize=1)
def _registre() -> dict:
    """Le registre lu une fois.

    Il ne change qu'au déploiement, le relire à chaque vue serait absurde.
    """
    return json.loads(CHEMIN_REGISTRE.read_text(encoding="utf-8"))


def charger() -> list[Vedette]:
    """Toutes les vedettes, publiées ou non — l'ordre du fichier est l'ordre éditorial."""
    return [
        Vedette(
            tcgdex_id=ligne["tcgdex_id"],
            nom=ligne["nom"],
            type=ligne["type"],
            illustration=ligne["illustration"],
            publie=bool(ligne.get("publie")),
            verdict_oeil=ligne.get("verdict_oeil") or VERDICT_A_REVOIR,
            motif_oeil=ligne.get("motif_oeil") or "",
            note=ligne.get("note") or {},
        )
        for ligne in _registre()["vedettes"]
    ]


@lru_cache(maxsize=1)
def publiees() -> frozenset[str]:
    """Les ``tcgdex_id`` dont la découpe est réellement déposée — ceux-là seuls sont annoncés."""
    return frozenset(v.tcgdex_id for v in charger() if v.publie)


def ecrire_notes(notes: dict[str, dict]) -> None:
    """Réinscrit note, poids et statut mesurés par la chaîne de découpe.

    Une vedette absente de ``notes`` n'est pas touchée : un passage limité à une carte
    (``--vedette``) ne doit pas dépublier les seize autres. Une vedette présente **sans** mesure de
    poids est une découpe refusée : elle est dépubliée, parce qu'annoncer ce qu'on ne sert pas est
    précisément ce que ce registre existe pour empêcher.

    ⛔ **La mesure ne publie jamais à elle seule.** Il faut en plus ``verdict_oeil == accepte``,
    posé à la main après lecture de la planche de contrôle. C'est le critère du lot (« les découpes
    des vedettes sont validées à l'œil, une par une ») rendu impossible à sauter : une chaîne qui
    publierait sur la seule foi de ses propres mesures finirait par servir une aile coupée.
    """
    registre = json.loads(CHEMIN_REGISTRE.read_text(encoding="utf-8"))
    for ligne in registre["vedettes"]:
        note = notes.get(ligne["tcgdex_id"])
        if note is None:
            continue
        ligne["note"] = note
        mesure_bonne = "octets" in note and not note.get("refus")
        ligne["publie"] = mesure_bonne and ligne.get("verdict_oeil") == VERDICT_ACCEPTE
    CHEMIN_REGISTRE.write_text(
        json.dumps(registre, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _registre.cache_clear()
    publiees.cache_clear()


__all__ = [
    "CHEMIN_REGISTRE",
    "MOTIF_ID",
    "PREFIXE_STOCKAGE",
    "VERDICT_ACCEPTE",
    "VERDICT_A_REVOIR",
    "VERDICT_REFUSE",
    "Vedette",
    "charger",
    "cle_apparition",
    "ecrire_notes",
    "publiees",
    "url_apparition",
]
