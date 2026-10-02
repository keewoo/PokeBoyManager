"""`pbm_game.rng` — aléatoire **reproductible, vérifiable et journalisé** du moteur.

Pur comme tout le moteur : ni HTTP, ni base, ni réseau, ni fichier (l'outillage en
ligne de commande vit dans :mod:`pbm_game.rng.__main__`, séparé pour que ce module
reste importable sans aucune E/S).

Trois exigences du jalon J1 — « tout est rejouable » — portées ici :

1. **Encapsulation.** Aucun appel à l'aléatoire global (``random``) nulle part dans le
   moteur : le hasard passe **uniquement** par un objet :class:`Rng` reçu explicitement.
   Un test de grep (``tests/test_rng.py``) garde cette propriété pour toujours.
2. **Flux séparés.** Chaque usage tire dans son propre **flux nommé** (le mélange de
   chaque joueur, le pile ou face de début de partie, chaque effet aléatoire). Ajouter
   un tirage dans un flux **ne décale jamais** la suite d'un autre flux : les compteurs
   sont indépendants.
3. **Vérifiabilité (engagement-révélation / commit-reveal).** On publie
   :func:`engagement` (une empreinte de la graine) **avant** la partie, et on révèle la
   graine **à la fin**. :func:`verifier_journal` recalcule alors chaque tirage et
   confirme qu'il est **exactement** le i-ème tirage de son flux sous cette graine, dans
   l'ordre, sans trou — ce qui interdit d'avoir « rejoué le mélange en boucle jusqu'à un
   bon résultat ».

Mécanique (documentée pour qu'un vérificateur indépendant la réimplémente —
``docs/jeu/ALEATOIRE.md``) : chaque tirage est un flux d'octets déterministe
``HMAC-SHA256(graine, flux || 0x00 || indice || sous_bloc)`` concaténé sur
``sous_bloc = 0, 1, …`` autant que nécessaire. Les entiers sont tirés **sans biais** par
rejet. Un tirage = **une** incrémentation du compteur de son flux, quel que soit le
nombre d'octets qu'il consomme (un mélange de 60 cartes comme un pile ou face).

Règles de référence servies (``docs/jeu/REGLES.md``) : **R-4.1** (chaque joueur mélange
son deck), **R-4.7** (pile ou face pour déterminer qui commence), **R-11.3 / R-11.4 /
R-11.5** (pile ou face des états Endormi / Brûlé / Confus au Checkup ou avant l'attaque).
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

# Version de la mécanique d'aléatoire. Toute évolution INCOMPATIBLE du calcul (fonction
# de bloc, échantillonnage, séparation de domaine) l'incrémente : un journal produit sous
# une version ne se revérifie pas sous une autre sans le dire.
RNG_VERSION = 1

# Séparation de domaine : empêche qu'une même graine, réutilisée ailleurs, produise par
# accident la même suite que l'engagement ou que les tirages.
_DOMAINE_ENGAGEMENT = b"pbm-rng-v1:engagement:"
_DOMAINE_FLUX = b"pbm-rng-v1:flux"

# Les deux faces (R-4.7, R-11.3/4/5). Le pile ou face est journalisé par ces chaînes —
# jamais un booléen nu — pour qu'un journal se lise sans table de correspondance.
FACE = "face"
PILE = "pile"

# Genres de tirage (ce que porte ``Tirage.genre``).
GENRE_PILE_OU_FACE = "pile_ou_face"
GENRE_ENTIER = "entier"
GENRE_MELANGE = "melange"

#: Longueur minimale d'une graine, en octets. 16 octets = 128 bits : assez pour qu'une
#: graine ne soit pas devinable, et pour que l'engagement ne soit pas attaquable par force
#: brute. Le moteur ne fabrique pas la graine (il est pur) — l'appelant la tire
#: (``os.urandom(32)`` côté serveur) et la lui passe.
GRAINE_MIN_OCTETS = 16


def flux_melange_deck(joueur_id: str) -> str:
    """Nom de flux du mélange du deck d'un joueur (R-4.1) — un flux **par joueur**."""
    if not joueur_id:
        raise ValueError("joueur_id vide : un flux doit être nommé.")
    return f"melange:deck:{joueur_id}"


def flux_checkup(etat_nom: str, joueur_id: str) -> str:
    """Nom de flux d'un pile ou face du Checkup (R-11.3/R-11.4) — un flux **par état et joueur**.

    Le réveil (Endormi, R-11.3) et la guérison de brûlure (R-11.4) tirent un pile ou face **à
    chaque Checkup**. Chaque (état, joueur) a son propre flux : un Checkup de plus pour l'un ne
    décale jamais la suite de tirages de l'autre (exigence « flux séparés » du jalon J1). Les
    tirages successifs d'un même (état, joueur) forment la suite 0, 1, 2… que
    :func:`verifier_journal` contrôle. ``etat_nom`` est un des états à pile ou face au Checkup
    (``endormi``, ``brule``) ; les refuser ici serait un flux muet, jamais approximé.
    """
    if etat_nom not in ("endormi", "brule"):
        raise ValueError(
            f"Flux de Checkup inconnu : {etat_nom!r} — seuls « endormi » (R-11.3) et « brule » "
            "(R-11.4) tirent un pile ou face au Checkup."
        )
    if not joueur_id:
        raise ValueError("joueur_id vide : un flux doit être nommé.")
    return f"checkup:{etat_nom}:{joueur_id}"


def flux_confusion(joueur_id: str) -> str:
    """Nom de flux du pile ou face de **confusion avant l'attaque** (R-11.5) — par joueur.

    La confusion tire un pile ou face **à la déclaration d'attaque** (R-11.5), pas au Checkup :
    c'est un moment distinct, donc un **flux distinct** de ceux du Checkup (R-11.3/R-11.4). Un
    flux par joueur, pour qu'une attaque de plus de l'un ne décale jamais la suite de l'autre
    (exigence « flux séparés » du jalon J1). Les tirages successifs forment la suite 0, 1, 2…
    que :func:`verifier_journal` contrôle.
    """
    if not joueur_id:
        raise ValueError("joueur_id vide : un flux doit être nommé.")
    return f"confusion:{joueur_id}"


#: Flux du pile ou face de début de partie — qui commence (R-4.7).
FLUX_QUI_COMMENCE = "partie:qui-commence"


# --- Mécanique de bloc (déterministe, sans biais) ----------------------------


def _bloc(graine: bytes, flux: str, indice: int, sous_bloc: int) -> bytes:
    """Un bloc de 32 octets pseudo-aléatoires pour (graine, flux, indice, sous_bloc)."""
    message = (
        _DOMAINE_FLUX
        + flux.encode("utf-8")
        + b"\x00"
        + indice.to_bytes(8, "big")
        + sous_bloc.to_bytes(8, "big")
    )
    return hmac.new(graine, message, hashlib.sha256).digest()


def _octets(graine: bytes, flux: str, indice: int) -> Iterator[int]:
    """Flux d'octets illimité d'**un** tirage : blocs concaténés sur sous_bloc = 0, 1, …"""
    sous_bloc = 0
    while True:
        yield from _bloc(graine, flux, indice, sous_bloc)
        sous_bloc += 1


def _entier_borne(octets: Iterator[int], n: int) -> int:
    """Entier uniforme dans ``[0, n)`` tiré **sans biais** (échantillonnage par rejet)."""
    if n <= 0:
        raise ValueError(f"borne n doit être strictement positive, reçu {n}.")
    if n == 1:
        return 0
    k = (n.bit_length() + 7) // 8  # octets nécessaires pour couvrir [0, n)
    espace = 1 << (8 * k)
    plafond = espace - (espace % n)  # plus grand multiple de n tenant dans k octets
    while True:
        valeur = 0
        for _ in range(k):
            valeur = (valeur << 8) | next(octets)
        if valeur < plafond:
            return valeur % n
        # valeur dans la zone de rejet : on retire, sans quoi les petits restes seraient
        # sur-représentés. C'est le prix d'un tirage non biaisé — jamais un repli silencieux.


def _permutation(graine: bytes, flux: str, indice: int, taille: int) -> tuple[int, ...]:
    """Permutation de ``range(taille)`` par Fisher–Yates piloté par le flux du tirage.

    ``perm[k]`` est l'indice d'origine placé en position ``k``. Parcours du haut vers le
    bas : à chaque rang ``i`` on échange avec un rang ``j`` tiré sans biais dans
    ``[0, i]``. Tous les tirages de ce mélange consomment le **même** flux d'octets, à la
    suite : un seul incrément de compteur pour tout le mélange.
    """
    if taille < 0:
        raise ValueError(f"taille négative : {taille}.")
    perm = list(range(taille))
    octets = _octets(graine, flux, indice)
    for i in range(taille - 1, 0, -1):
        j = _entier_borne(octets, i + 1)
        perm[i], perm[j] = perm[j], perm[i]
    return tuple(perm)


# --- Tirage journalisé -------------------------------------------------------


@dataclass(frozen=True)
class Tirage:
    """Un tirage journalisé — autosuffisant pour être revérifié sans contexte.

    * ``flux`` — le flux nommé dans lequel il a été tiré ;
    * ``indice`` — son rang dans ce flux (0-based) ; les tirages d'un flux forment la
      suite 0, 1, 2, … sans trou — c'est ce que :func:`verifier_journal` contrôle ;
    * ``motif`` — pourquoi ce tirage (ex. « R-4.7 qui commence », « R-11.5 confusion ») ;
    * ``genre`` — :data:`GENRE_PILE_OU_FACE`, :data:`GENRE_ENTIER` ou :data:`GENRE_MELANGE` ;
    * ``parametre`` — le **domaine** du tirage : 2 pour un pile ou face, ``n`` pour un
      entier dans ``[0, n)``, la **taille** pour un mélange. C'est ce qui rend le tirage
      rejouable sans deviner sa borne ;
    * ``resultat`` — ``FACE``/``PILE`` (pile ou face), un entier (entier), ou la
      **permutation** (tuple d'indices) appliquée (mélange).
    """

    flux: str
    indice: int
    motif: str
    genre: str
    parametre: int
    resultat: str | int | tuple[int, ...]


class Rng:
    """Source d'aléatoire d'une partie : une graine, des flux nommés, un journal.

    Objet **mutable** (les compteurs de flux avancent, le journal s'allonge) mais sans
    aucune E/S : il reste pur au sens du moteur. Son état complet — graine, compteurs,
    journal — est sérialisable (:meth:`etat`) et reconstructible (:meth:`depuis_etat`),
    donc la partie reste rejouable à l'identique.
    """

    __slots__ = ("_graine", "_compteurs", "_journal")

    def __init__(self, graine: bytes) -> None:
        if not isinstance(graine, (bytes, bytearray)):
            raise TypeError("La graine doit être des octets (bytes).")
        if len(graine) < GRAINE_MIN_OCTETS:
            raise ValueError(
                f"Graine trop courte : {len(graine)} octets, minimum {GRAINE_MIN_OCTETS}."
            )
        self._graine = bytes(graine)
        self._compteurs: dict[str, int] = {}
        self._journal: list[Tirage] = []

    # -- Lecture ------------------------------------------------------------

    @property
    def graine_hex(self) -> str:
        """La graine en hexadécimal (à **révéler** seulement à la fin de la partie)."""
        return self._graine.hex()

    @property
    def engagement(self) -> str:
        """L'empreinte de la graine à **publier avant** la partie (commit-reveal)."""
        return engagement(self._graine)

    def journal(self) -> tuple[Tirage, ...]:
        """Le journal des tirages, dans l'ordre où ils ont eu lieu (copie figée)."""
        return tuple(self._journal)

    def compteurs(self) -> dict[str, int]:
        """Combien de tirages chaque flux a consommés (copie)."""
        return dict(self._compteurs)

    # -- Tirages ------------------------------------------------------------

    def _prochain_indice(self, flux: str, motif: str) -> int:
        if not flux:
            raise ValueError("Un tirage doit nommer son flux (chaîne non vide).")
        if not motif:
            raise ValueError("Un tirage doit nommer son motif (chaîne non vide).")
        indice = self._compteurs.get(flux, 0)
        self._compteurs[flux] = indice + 1
        return indice

    def pile_ou_face(self, flux: str, motif: str) -> str:
        """Un pile ou face dans ``flux`` : renvoie :data:`FACE` ou :data:`PILE` (R-4.7, R-11)."""
        indice = self._prochain_indice(flux, motif)
        valeur = _entier_borne(_octets(self._graine, flux, indice), 2)
        resultat = FACE if valeur == 0 else PILE
        self._journal.append(Tirage(flux, indice, motif, GENRE_PILE_OU_FACE, 2, resultat))
        return resultat

    def entier(self, flux: str, motif: str, n: int) -> int:
        """Un entier uniforme dans ``[0, n)`` dans ``flux`` (effets aléatoires divers)."""
        indice = self._prochain_indice(flux, motif)
        resultat = _entier_borne(_octets(self._graine, flux, indice), n)
        self._journal.append(Tirage(flux, indice, motif, GENRE_ENTIER, n, resultat))
        return resultat

    def melanger(self, flux: str, motif: str, sequence: Iterable) -> list:
        """Mélange ``sequence`` (R-4.1) et renvoie une **nouvelle** liste réordonnée.

        La permutation appliquée est journalisée, pas les cartes : le journal ne révèle
        pas le contenu d'une zone cachée, il prouve seulement comment elle a été battue.
        """
        elements = list(sequence)
        indice = self._prochain_indice(flux, motif)
        perm = _permutation(self._graine, flux, indice, len(elements))
        self._journal.append(Tirage(flux, indice, motif, GENRE_MELANGE, len(elements), perm))
        return [elements[p] for p in perm]

    # -- Sérialisation (partie rejouable) -----------------------------------

    def etat(self) -> dict:
        """État complet sérialisable : version, graine, compteurs, journal."""
        return {
            "rng_version": RNG_VERSION,
            "graine": self.graine_hex,
            "compteurs": dict(self._compteurs),
            "journal": [tirage_vers_json(t) for t in self._journal],
        }

    @classmethod
    def depuis_etat(cls, donnees: object) -> Rng:
        """Reconstruit un :class:`Rng` depuis la sortie de :meth:`etat` (ou lève ``ValueError``)."""
        if not isinstance(donnees, dict):
            raise ValueError("L'état du Rng doit être un mapping.")
        version = donnees.get("rng_version")
        if version != RNG_VERSION:
            raise ValueError(
                f"rng_version inconnue : {version!r} (ce moteur lit la version {RNG_VERSION})."
            )
        graine_hex = donnees.get("graine")
        if not isinstance(graine_hex, str):
            raise ValueError("État Rng : « graine » (hex) manquante ou invalide.")
        try:
            graine = bytes.fromhex(graine_hex)
        except ValueError as exc:
            raise ValueError(f"État Rng : graine hex illisible ({exc}).") from exc
        rng = cls(graine)
        compteurs = donnees.get("compteurs", {})
        if not isinstance(compteurs, dict) or not all(
            isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)
            for k, v in compteurs.items()
        ):
            raise ValueError("État Rng : « compteurs » doit être un mapping flux→entier.")
        rng._compteurs = dict(compteurs)
        journal_brut = donnees.get("journal", [])
        if not isinstance(journal_brut, list):
            raise ValueError("État Rng : « journal » doit être une liste.")
        rng._journal = [tirage_depuis_json(d) for d in journal_brut]
        return rng

    def restaurer(self, donnees: object) -> None:
        """Recharge **en place** l'état de :meth:`etat` — un *retour en arrière* des tirages.

        Même contrat que :meth:`depuis_etat`, mais au lieu de fabriquer un nouvel objet, elle
        ramène **celui-ci** à un instantané antérieur (mêmes compteurs de flux, même journal). Elle
        sert au mécanisme de **demandes de décision** (lot ``j-effets-choix``) : quand la résolution
        d'un effet se **suspend** en attendant la réponse d'un joueur, on annule les tirages que son
        déroulé partiel avait consommés, puis on le **re-déroule à l'identique** à la reprise. Comme
        le Rng est déterministe à position donnée (graine + indice), re-tirer après un
        retour en arrière redonne **exactement** les mêmes valeurs — aucun tirage compté
        deux fois dans le journal. La graine ne peut pas changer : restaurer une autre graine
        est refusé (jamais un retour en arrière silencieux vers un autre hasard).
        """
        remis = Rng.depuis_etat(donnees)
        if remis.graine_hex != self.graine_hex:
            raise ValueError(
                "Restauration d'un Rng vers une graine différente : refusée (changerait le hasard)."
            )
        self._compteurs = dict(remis._compteurs)
        self._journal = list(remis._journal)


# --- Engagement / révélation (commit-reveal) ---------------------------------


def engagement(graine: bytes) -> str:
    """Empreinte de la graine à **publier avant** la partie (révélée en fin de partie)."""
    if not isinstance(graine, (bytes, bytearray)):
        raise TypeError("La graine doit être des octets (bytes).")
    return hashlib.sha256(_DOMAINE_ENGAGEMENT + bytes(graine)).hexdigest()


def verifier_engagement(graine: bytes, engagement_publie: str) -> bool:
    """Vrai si ``graine`` correspond bien à l'engagement publié avant la partie."""
    return hmac.compare_digest(engagement(graine), engagement_publie)


# --- Vérificateur de journal (le cœur de l'anti-triche) ----------------------


@dataclass(frozen=True)
class Anomalie:
    """Un écart relevé par :func:`verifier_journal` — jamais tu silencieusement."""

    rang: int  # position du tirage fautif dans le journal
    flux: str
    probleme: str


def rejouer_tirage(graine: bytes, tirage: Tirage) -> str | int | tuple[int, ...]:
    """Recalcule le résultat d'**un** tirage depuis la graine, sans compteur ni journal."""
    if tirage.genre == GENRE_MELANGE:
        return _permutation(graine, tirage.flux, tirage.indice, tirage.parametre)
    valeur = _entier_borne(_octets(graine, tirage.flux, tirage.indice), tirage.parametre)
    if tirage.genre == GENRE_PILE_OU_FACE:
        return FACE if valeur == 0 else PILE
    if tirage.genre == GENRE_ENTIER:
        return valeur
    raise ValueError(f"Genre de tirage inconnu : {tirage.genre!r}.")


def verifier_journal(graine: bytes, journal: Sequence[Tirage]) -> list[Anomalie]:
    """Revérifie tout un journal contre la graine révélée.

    Renvoie la liste (vide si tout va bien) des :class:`Anomalie`. Contrôle, pour chaque
    tirage :

    * **la séquence** — les tirages d'un même flux sont 0, 1, 2, … sans trou ni
      réordonnancement (interdit de choisir un indice favorable) ;
    * **le résultat** — il correspond exactement à ce que la graine produit à cet indice
      (interdit de truquer un pile ou face ou un mélange).
    """
    compteurs: dict[str, int] = {}
    anomalies: list[Anomalie] = []
    for rang, tirage in enumerate(journal):
        attendu = compteurs.get(tirage.flux, 0)
        if tirage.indice != attendu:
            anomalies.append(
                Anomalie(
                    rang,
                    tirage.flux,
                    f"indice {tirage.indice} hors séquence (attendu {attendu}).",
                )
            )
        # On suit l'indice enregistré pour continuer à contrôler la suite même après un
        # écart — un trou ne doit pas masquer les tirages qui le suivent.
        compteurs[tirage.flux] = tirage.indice + 1
        try:
            recalcule = rejouer_tirage(graine, tirage)
        except ValueError as exc:
            anomalies.append(Anomalie(rang, tirage.flux, str(exc)))
            continue
        if recalcule != tirage.resultat:
            anomalies.append(
                Anomalie(
                    rang,
                    tirage.flux,
                    f"résultat {tirage.resultat!r} ne correspond pas à la graine "
                    f"(recalculé {recalcule!r}).",
                )
            )
    return anomalies


# --- Sérialisation d'un tirage -----------------------------------------------


def tirage_vers_json(tirage: Tirage) -> dict:
    """Projette un :class:`Tirage` en ``dict`` JSON-sérialisable et déterministe."""
    resultat = tirage.resultat
    return {
        "flux": tirage.flux,
        "indice": tirage.indice,
        "motif": tirage.motif,
        "genre": tirage.genre,
        "parametre": tirage.parametre,
        "resultat": list(resultat) if isinstance(resultat, tuple) else resultat,
    }


def tirage_depuis_json(donnees: object) -> Tirage:
    """Relit un ``dict`` produit par :func:`tirage_vers_json` (ou lève ``ValueError``)."""
    if not isinstance(donnees, dict):
        raise ValueError("Un tirage doit être un mapping.")

    def _chaine(cle: str) -> str:
        valeur = donnees.get(cle)
        if not isinstance(valeur, str) or not valeur:
            raise ValueError(f"Tirage : « {cle} » manquant ou invalide.")
        return valeur

    def _entier(cle: str) -> int:
        valeur = donnees.get(cle)
        if not isinstance(valeur, int) or isinstance(valeur, bool):
            raise ValueError(f"Tirage : « {cle} » doit être un entier.")
        return valeur

    flux = _chaine("flux")
    motif = _chaine("motif")
    genre = _chaine("genre")
    indice = _entier("indice")
    parametre = _entier("parametre")
    resultat_brut = donnees.get("resultat")
    if genre == GENRE_PILE_OU_FACE:
        if resultat_brut not in (FACE, PILE):
            raise ValueError(f"Tirage pile ou face : résultat {resultat_brut!r} invalide.")
        resultat: str | int | tuple[int, ...] = resultat_brut
    elif genre == GENRE_ENTIER:
        if not isinstance(resultat_brut, int) or isinstance(resultat_brut, bool):
            raise ValueError("Tirage entier : « resultat » doit être un entier.")
        resultat = resultat_brut
    elif genre == GENRE_MELANGE:
        if not isinstance(resultat_brut, list) or not all(
            isinstance(x, int) and not isinstance(x, bool) for x in resultat_brut
        ):
            raise ValueError("Tirage mélange : « resultat » doit être une liste d'entiers.")
        resultat = tuple(resultat_brut)
    else:
        raise ValueError(f"Tirage : genre inconnu {genre!r}.")
    return Tirage(
        flux=flux, indice=indice, motif=motif, genre=genre, parametre=parametre, resultat=resultat
    )


__all__ = [
    "RNG_VERSION",
    "FACE",
    "PILE",
    "GENRE_PILE_OU_FACE",
    "GENRE_ENTIER",
    "GENRE_MELANGE",
    "GRAINE_MIN_OCTETS",
    "FLUX_QUI_COMMENCE",
    "flux_melange_deck",
    "flux_checkup",
    "flux_confusion",
    "Tirage",
    "Rng",
    "engagement",
    "verifier_engagement",
    "Anomalie",
    "rejouer_tirage",
    "verifier_journal",
    "tirage_vers_json",
    "tirage_depuis_json",
]
