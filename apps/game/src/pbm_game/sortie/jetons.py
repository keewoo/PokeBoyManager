"""Jetons opaques pour les cartes cachées — lot ``j-autorite-vues``.

**Le serveur fait autorité.** Quand un client doit pouvoir *désigner* une carte d'une zone
cachée (ses récompenses face cachée, par exemple) sans jamais en apprendre l'identité, on ne
lui donne pas l'``instance_id`` réel : on lui donne un **jeton opaque**. Le serveur, seul à
détenir le secret, retraduit le jeton en ``instance_id`` au moment où le client agit
(:meth:`Jetonneur.resoudre`).

Deux propriétés, toutes deux vérifiées par les tests, font tenir l'anti-triche :

* **Opacité.** Le jeton est un HMAC-SHA256 tronqué, clé par un **secret serveur** dérivé de
  la graine de la partie (jamais révélée avant la fin, R-4). Sans le secret, on ne remonte
  pas du jeton à l'``instance_id`` : il n'y a rien à « décoder » côté client.
* **Non-corrélation entre deux mélanges.** L'``epoque`` — le nombre de fois que le deck
  concerné a été mélangé — entre dans la clé du HMAC. Un même ``instance_id`` produit donc un
  jeton **différent** à chaque mélange, et un jeton capturé avant un mélange ne **résout
  plus rien** après (``resoudre`` renvoie ``None``) : impossible de suivre une carte d'un
  mélange à l'autre, ce qui est précisément le vecteur de triche que ce lot ferme.

Ce module est **pur** (aucune E/S) comme tout ``pbm_game`` : le secret et l'époque lui sont
**fournis** par l'appelant (le service de parties les dérive de la graine et du journal du
Rng). Il ne lit ni la base ni l'horloge.
"""

from __future__ import annotations

import hmac
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256

#: Préfixe des jetons produits — rend un jeton reconnaissable dans une trace et interdit de le
#: confondre avec un ``instance_id`` réel (aucun ``instance_id`` du moteur ne commence ainsi).
PREFIXE_JETON = "jc_"

#: Longueur (en caractères hex) de la partie signifiante du jeton. 20 hex = 80 bits : assez pour
#: qu'une collision entre deux cartes d'une même zone soit hors de portée, assez court pour rester
#: lisible. La résolution reste exacte (on compare au HMAC complet recalculé), ce n'est pas une
#: table de hachage sujette aux collisions silencieuses.
LONGUEUR_JETON_HEX = 20

#: Étiquette de dérivation du secret des jetons depuis la graine de partie. Une étiquette dédiée
#: isole cet usage de tout autre dérivé de la graine (engagement, flux de Rng) : compromettre un
#: jeton n'apprend rien sur les autres secrets, et réciproquement.
ETIQUETTE_SECRET = b"pbm-jetons-cartes-cachees"


def secret_jetons(graine: bytes) -> bytes:
    """Dérive le **secret serveur** des jetons depuis la graine de la partie.

    La graine est elle-même un secret (commit-reveal, R-4) : on ne l'emploie jamais telle quelle
    comme clé, on en dérive une clé dédiée par HMAC sous :data:`ETIQUETTE_SECRET`. Déterministe,
    donc stable d'un redémarrage à l'autre (un F5 redonne les mêmes jetons dans la même époque).
    """
    if not isinstance(graine, (bytes, bytearray)):
        raise TypeError("La graine doit être des octets (bytes).")
    return hmac.new(bytes(graine), ETIQUETTE_SECRET, sha256).digest()


@dataclass(frozen=True)
class Jetonneur:
    """Traduit un ``instance_id`` caché en jeton opaque, et un jeton en ``instance_id``.

    * ``secret`` — le secret serveur (voir :func:`secret_jetons`), **jamais** sérialisé vers un
      client ni journalisé ;
    * ``epoque`` — le nombre de mélanges du deck concerné : il entre dans la clé pour que les
      jetons changent à chaque mélange (non-corrélation).
    """

    secret: bytes
    epoque: int

    def __post_init__(self) -> None:
        if not isinstance(self.secret, (bytes, bytearray)) or not self.secret:
            raise ValueError("Le secret d'un Jetonneur doit être des octets non vides.")
        if not isinstance(self.epoque, int) or isinstance(self.epoque, bool) or self.epoque < 0:
            raise ValueError(
                f"L'époque d'un Jetonneur doit être un entier ≥ 0 (reçu {self.epoque!r})."
            )

    def jeton(self, instance_id: str) -> str:
        """Le jeton opaque de ``instance_id`` pour l'époque courante.

        Déterministe dans une époque (même carte → même jeton, pour que l'écran garde un repère
        stable entre deux vues), différent d'une époque à l'autre (non-corrélation entre mélanges).
        """
        if not isinstance(instance_id, str) or not instance_id:
            raise ValueError("Un instance_id à jetonner doit être une chaîne non vide.")
        message = f"{self.epoque}:{instance_id}".encode()
        empreinte = hmac.new(self.secret, message, sha256).hexdigest()
        return PREFIXE_JETON + empreinte[:LONGUEUR_JETON_HEX]

    def resoudre(self, jeton: str, candidats: Iterable[str]) -> str | None:
        """Retrouve l'``instance_id`` d'un jeton **parmi un ensemble légitime de candidats**.

        ``candidats`` est l'ensemble des cartes que le client a le droit de désigner dans cette
        action (p. ex. ses propres récompenses) : on ne résout jamais un jeton « dans le vide ».
        Renvoie l'``instance_id`` correspondant, ou ``None`` si aucun candidat ne produit ce jeton
        — ce qui arrive aussi quand le jeton vient d'une **autre époque** (après un mélange) : on ne
        suit pas une carte d'un mélange à l'autre. ``None`` est un refus explicite, jamais un repli
        silencieux : l'appelant doit rejeter l'action, pas deviner une cible.
        """
        for candidat in candidats:
            if hmac.compare_digest(self.jeton(candidat), jeton):
                return candidat
        return None
