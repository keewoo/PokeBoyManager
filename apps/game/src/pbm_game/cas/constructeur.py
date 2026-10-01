"""Constructeur d'états de partie **à partir d'une description concise** — pour les cas.

Module **pur** (aucune E/S, ni HTTP, ni base, ni React), comme tout ``pbm_game``. Il traduit
une description lisible (le champ ``etat`` d'un cas de ``docs/jeu/cas-executables/``) en un
:class:`~pbm_game.state.EtatPartie` réel, **et** en la table ``fiches`` (PV + récompenses par
Pokémon) que le Checkup et la résolution des K.O. réclament du service (D9 : le moteur ne
devine ni PV ni récompenses).

Pourquoi ce module existe : écrire à la main un ``EtatPartie`` complet — chaque carte avec son
``instance_id`` et son ``ref`` — pour 200 cas serait illisible et fautif. Ici, un cas écrit
« un Actif avec 2 énergies, 50 de dégâts, Empoisonné » et le constructeur fabrique les cartes,
avec des identifiants **déterministes** (documentés dans ``docs/jeu/CAS-EXECUTABLES.md``) qu'un
cas peut citer (une énergie à défausser pour une retraite, par exemple).

Le constructeur **ne juge pas** la validité du plateau (il n'appelle pas ``verifier``) : beaucoup
de cas de règles ont besoin d'états limites (un Pokémon dont les compteurs dépassent ses PV, un
banc sans Actif après un K.O.). C'est l'opération testée qui valide ce qu'elle doit.
"""

from __future__ import annotations

from ..rng import FACE, GRAINE_MIN_OCTETS, PILE, Rng
from ..state.modele import (
    Carte,
    EtatPartie,
    Joueur,
    PokemonEnJeu,
    Tour,
)

#: Identifiants de joueurs par défaut quand le cas ne les nomme pas.
JOUEURS_DEFAUT: tuple[str, str] = ("alice", "bob")

#: Graine par défaut (16 octets) pour un cas **sans aucun tirage** d'aléatoire : sa valeur n'a
#: aucune importance tant qu'aucun pile ou face n'est consulté. Les cas qui dépendent d'un tirage
#: passent par :func:`trouver_graine`, qui cherche une graine produisant les résultats voulus.
GRAINE_DEFAUT: bytes = bytes(range(GRAINE_MIN_OCTETS))

# Champs d'un joueur qui sont de simples **comptes de cartes** d'une zone cachée/visible : le
# constructeur fabrique autant de cartes anonymes. Le détail des cartes n'importe pas à ces
# zones pour un test de règle (seul leur nombre compte).
_ZONES_COMPTEES: tuple[str, ...] = (
    "pioche",
    "main",
    "defausse",
    "recompenses",
    "zone_perdue",
)
#: Préfixe d'``instance_id`` de chaque zone comptée (``alice.pioche0``, ``alice.main3``…).
_PREFIXE_ZONE: dict[str, str] = {
    "pioche": "pioche",
    "main": "main",
    "defausse": "defausse",
    "recompenses": "recompense",
    "zone_perdue": "perdue",
}


def _carte(instance_id: str) -> Carte:
    """Une carte au ``ref`` dérivé de son ``instance_id`` (unique, traçable)."""
    return Carte(instance_id=instance_id, ref=f"ref:{instance_id}")


def _cartes(prefixe: str, nombre: object, champ: str) -> tuple[Carte, ...]:
    if not isinstance(nombre, int) or isinstance(nombre, bool) or nombre < 0:
        raise ValueError(f"« {champ} » doit être un entier ≥ 0, reçu {nombre!r}.")
    return tuple(_carte(f"{prefixe}{i}") for i in range(nombre))


def _pokemon(spec: object, prefixe: str, fiches: dict) -> PokemonEnJeu:
    """Construit un :class:`PokemonEnJeu` depuis une spec concise et alimente ``fiches``.

    Spec (toutes les clés sont facultatives) :

    * ``cartes`` : taille de la pile d'évolutions (défaut 1 — un Pokémon de base) ;
    * ``degats`` : compteurs de dégâts (défaut 0) ;
    * ``etats`` : liste d'états spéciaux (défaut aucun) ;
    * ``energies`` : nombre d'énergies attachées (défaut 0) ;
    * ``outil`` : vrai pour attacher un Outil (défaut faux) ;
    * ``pv`` + (``recompenses`` | ``marqueur``) : la fiche catalogue du Pokémon (R-13.1/R-13.3),
      indexée sur l'``instance_id`` de sa carte au sommet. Omise, le Pokémon n'a pas de fiche
      (il n'est pas candidat au K.O. dans ce cas).
    """
    if not isinstance(spec, dict):
        raise ValueError(f"Un Pokémon se décrit par un mapping, reçu {type(spec).__name__}.")
    inconnues = set(spec) - {
        "cartes",
        "degats",
        "etats",
        "energies",
        "outil",
        "pv",
        "recompenses",
        "marqueur",
    }
    if inconnues:
        raise ValueError(f"Clés de Pokémon inconnues : {sorted(inconnues)} (prefixe {prefixe}).")

    nb_cartes = spec.get("cartes", 1)
    if not isinstance(nb_cartes, int) or isinstance(nb_cartes, bool) or nb_cartes < 1:
        raise ValueError(f"« cartes » (pile d'évolutions) : entier ≥ 1, reçu {nb_cartes!r}.")
    cartes = tuple(_carte(f"{prefixe}/{i}" if i else prefixe) for i in range(nb_cartes))

    degats = spec.get("degats", 0)
    if not isinstance(degats, int) or isinstance(degats, bool) or degats < 0:
        raise ValueError(f"« degats » doit être un entier ≥ 0, reçu {degats!r}.")

    etats = spec.get("etats", [])
    if not isinstance(etats, list) or any(not isinstance(e, str) for e in etats):
        raise ValueError(f"« etats » doit être une liste de chaînes, reçu {etats!r}.")

    energies = _cartes(f"{prefixe}.e", spec.get("energies", 0), "energies")
    outil = _carte(f"{prefixe}.outil") if spec.get("outil", False) else None

    pokemon = PokemonEnJeu(
        cartes=cartes,
        energies=energies,
        outil=outil,
        compteurs_degats=degats,
        etats_speciaux=frozenset(etats),
    )

    # Fiche catalogue (PV + récompenses) — indexée sur la carte au sommet (R-13.1/R-13.3).
    if "pv" in spec or "recompenses" in spec or "marqueur" in spec:
        if "pv" not in spec:
            raise ValueError(f"Fiche de {prefixe} : « pv » requis dès qu'une fiche est décrite.")
        fiche: dict = {"pv": spec["pv"]}
        if "marqueur" in spec:
            fiche["marqueur"] = spec["marqueur"]
        elif "recompenses" in spec:
            fiche["recompenses"] = spec["recompenses"]
        else:
            raise ValueError(
                f"Fiche de {prefixe} : « recompenses » ou « marqueur » requis avec « pv » (R-13.3)."
            )
        fiches[cartes[-1].instance_id] = fiche

    return pokemon


def _joueur(jid: str, spec: object, fiches: dict) -> Joueur:
    if not isinstance(spec, dict):
        raise ValueError(f"Le joueur « {jid} » se décrit par un mapping.")
    inconnues = set(spec) - ({"actif", "banc"} | set(_ZONES_COMPTEES))
    if inconnues:
        raise ValueError(f"Clés de joueur « {jid} » inconnues : {sorted(inconnues)}.")

    actif_spec = spec.get("actif")
    actif = _pokemon(actif_spec, f"{jid}.actif", fiches) if actif_spec is not None else None

    banc_spec = spec.get("banc", [])
    if isinstance(banc_spec, int) and not isinstance(banc_spec, bool):
        banc_spec = [{} for _ in range(banc_spec)]
    if not isinstance(banc_spec, list):
        raise ValueError(f"« banc » de « {jid} » : entier (nb de Pokémon) ou liste de specs.")
    banc = tuple(
        _pokemon(p, f"{jid}.banc{i}", fiches) for i, p in enumerate(banc_spec)
    )

    zones = {
        z: _cartes(f"{jid}.{_PREFIXE_ZONE[z]}", spec.get(z, 0), z) for z in _ZONES_COMPTEES
    }
    return Joueur(
        id=jid,
        actif=actif,
        banc=banc,
        pioche=zones["pioche"],
        main=zones["main"],
        defausse=zones["defausse"],
        recompenses=zones["recompenses"],
        zone_perdue=zones["zone_perdue"],
    )


def _tour(spec: object, ids: tuple[str, str]) -> Tour:
    spec = spec or {}
    if not isinstance(spec, dict):
        raise ValueError("« tour » se décrit par un mapping.")
    inconnues = set(spec) - {
        "joueur_actif",
        "joueur",
        "numero",
        "phase",
        "energie_posee",
        "supporter_joue",
        "retraite_faite",
        "entres",
        "evolues",
    }
    if inconnues:
        raise ValueError(f"Clés de tour inconnues : {sorted(inconnues)}.")
    joueur_actif = spec.get("joueur_actif", spec.get("joueur", ids[0]))
    numero = spec.get("numero", 3)  # défaut : ni le 1er tour, ni le 2e (R-6.*) sauf mention
    if not isinstance(numero, int) or isinstance(numero, bool) or numero < 1:
        raise ValueError(f"« numero » de tour invalide : {numero!r} (entier ≥ 1).")
    phase = spec.get("phase", "principale")
    entres = spec.get("entres", [])
    if not isinstance(entres, list) or any(not isinstance(e, str) for e in entres):
        raise ValueError("« entres » (entrés en jeu ce tour) doit être une liste de chaînes.")
    evolues = spec.get("evolues", [])
    if not isinstance(evolues, list) or any(not isinstance(e, str) for e in evolues):
        raise ValueError("« evolues » (évolués ce tour) doit être une liste de chaînes.")

    def _drapeau(cle: str) -> bool:
        v = spec.get(cle, False)
        if not isinstance(v, bool):
            raise ValueError(f"« {cle} » du tour doit être un booléen, reçu {v!r}.")
        return v

    return Tour(
        joueur_actif=joueur_actif,
        numero=numero,
        phase=phase,
        energie_posee=_drapeau("energie_posee"),
        supporter_joue=_drapeau("supporter_joue"),
        retraite_faite=_drapeau("retraite_faite"),
        entres_en_jeu_ce_tour=frozenset(entres),
        evolues_ce_tour=frozenset(evolues),
    )


def construire(spec: object) -> tuple[EtatPartie, dict]:
    """Construit ``(EtatPartie, fiches)`` depuis la description concise ``spec`` d'un cas.

    ``spec`` nomme chaque joueur (par défaut ``alice`` et ``bob``) et, facultativement, le
    ``tour``, le ``stade``, et l'issue (``terminee``/``vainqueur``/``raison_fin``). ``fiches`` est
    la table ``instance_id → {pv, recompenses|marqueur}`` agrégée des Pokémon qui en décrivent une
    — ce que le Checkup et la résolution des K.O. attendent du service (D9). Lève ``ValueError``
    sur toute clé inconnue ou valeur malformée : un cas mal écrit est une panne, jamais un repli
    silencieux.
    """
    if not isinstance(spec, dict):
        raise ValueError("« etat » d'un cas se décrit par un mapping.")

    joueurs_nommes = [c for c in spec if c not in _META_ETAT]
    if joueurs_nommes:
        ids = tuple(joueurs_nommes)
    else:
        ids = JOUEURS_DEFAUT
    if len(ids) != 2:
        raise ValueError(f"Une partie compte exactement deux joueurs, décrits : {list(ids)}.")

    fiches: dict = {}
    j0 = _joueur(ids[0], spec.get(ids[0], {}), fiches)
    j1 = _joueur(ids[1], spec.get(ids[1], {}), fiches)

    tour = _tour(spec.get("tour"), ids)

    stade_spec = spec.get("stade")
    stade = _carte("stade") if stade_spec else None
    stade_proprietaire = spec.get("stade_proprietaire")
    if stade_proprietaire is not None and not isinstance(stade_proprietaire, str):
        raise ValueError("« stade_proprietaire » doit être une chaîne.")

    terminee = spec.get("terminee", False)
    if not isinstance(terminee, bool):
        raise ValueError("« terminee » doit être un booléen.")
    vainqueur = spec.get("vainqueur")
    raison_fin = spec.get("raison_fin")

    etat = EtatPartie(
        joueurs=(j0, j1),
        tour=tour,
        stade=stade,
        stade_proprietaire=stade_proprietaire,
        terminee=terminee,
        vainqueur=vainqueur,
        raison_fin=raison_fin,
    )
    return etat, fiches


#: Clés de ``spec`` qui ne sont PAS des identifiants de joueur (le reste des clés nomme les deux
#: joueurs). Garde l'écriture d'un cas lisible : ``{alice: {...}, bob: {...}, tour: {...}}``.
_META_ETAT: frozenset[str] = frozenset(
    {"tour", "stade", "stade_proprietaire", "terminee", "vainqueur", "raison_fin"}
)


# --- Recherche d'une graine produisant des tirages voulus (pile ou face) ------------------


def trouver_graine(exigences: list[tuple[str, str]], *, limite: int = 200_000) -> bytes:
    """Cherche une graine 16 octets produisant les pile ou face ``exigences``, dans l'ordre.

    ``exigences`` est une liste de ``(flux, resultat)`` où ``resultat`` ∈ {``face``, ``pile``} :
    chaque entrée est le **prochain** tirage de son flux (le k-ième appel à ``pile_ou_face`` sur
    ce flux). Comme les flux sont indépendants et indexés en séquence (voir ``pbm_game.rng``), on
    prédit chaque résultat sans exécuter le moteur. On énumère des graines déterministes (compteur
    0, 1, 2…) et on renvoie la première qui satisfait **toutes** les exigences.

    Lève ``ValueError`` si aucune graine n'est trouvée sous ``limite`` (jamais un repli silencieux
    sur un tirage approximatif) ou si une exigence est malformée.
    """
    # Regroupe par flux, en attribuant l'indice d'occurrence (0, 1, …) dans l'ordre d'apparition.
    besoins: dict[str, list[str]] = {}
    for flux, resultat in exigences:
        if resultat not in (FACE, PILE):
            raise ValueError(f"Résultat de tirage attendu « {resultat} » : « face » ou « pile ».")
        besoins.setdefault(flux, []).append(resultat)

    for compteur in range(limite):
        graine = compteur.to_bytes(GRAINE_MIN_OCTETS, "big")
        if _graine_convient(graine, besoins):
            return graine
    raise ValueError(
        f"Aucune graine trouvée sous {limite} essais pour {exigences} — exigences trop nombreuses ?"
    )


def _graine_convient(graine: bytes, besoins: dict[str, list[str]]) -> bool:
    for flux, attendus in besoins.items():
        rng = Rng(graine)
        for attendu in attendus:
            if rng.pile_ou_face(flux, "recherche de graine") != attendu:
                return False
    return True


__all__ = [
    "JOUEURS_DEFAUT",
    "GRAINE_DEFAUT",
    "construire",
    "trouver_graine",
]
