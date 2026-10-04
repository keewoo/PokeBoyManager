"""Le **tableau de couverture** : ce qui est jouable, ce qui manque, et pour qui (lot
`j-effets-couverture-outil`).

Deux grains de lecture, et ils ne disent pas la même chose :

* au grain de l'**effet** (texte distinct) — combien de textes d'effet sont scriptés, combien
  restent (non supportés, à revoir, ou jamais écrits). C'est la mesure du *chantier de scriptage* ;
* au grain de la **carte** — combien de cartes sont *entièrement* jouables (tous leurs effets
  scriptés). Une carte à deux attaques à effet n'est jouable que si les deux textes le sont.

**La mesure qui compte est celle des collections réelles** (risque nommé du lot). Une couverture
calculée sur les trente mille cartes du catalogue — dont 99 % que personne ne possède — donne un
chiffre flatteur et inutile. L'adaptateur base (:func:`charger_couverture`) ne regarde donc que
l'**univers réel** : les cartes possédées par un joueur du jeu (compte `game_access`) ou présentes
dans l'un de leurs decks. Le cœur ci-dessous reste **pur** (aucune E/S) : il opère sur des données
déjà chargées, ce qui le rend testable par cas, et fait que le choix de l'univers vit en un seul
endroit (l'adaptateur), pas éparpillé.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from pbm_api.jeu.scripts.empreinte import effets_scriptables
from pbm_api.models.card_scripts import (
    SCRIPT_STATUT_A_REVOIR,
    SCRIPT_STATUT_NON_SUPPORTE,
    SCRIPT_STATUT_SCRIPTE,
)

#: Statut d'un effet dont aucune ligne n'existe au registre `card_scripts` (jamais écrit).
STATUT_ABSENT = "absent"

#: Raison lisible par statut bloquant — nommée, jamais un « au mieux » (D9).
_RAISON_PAR_STATUT = {
    STATUT_ABSENT: "aucun script écrit pour ce texte d'effet",
    SCRIPT_STATUT_NON_SUPPORTE: "effet hors du langage v1 (non supporté)",
    SCRIPT_STATUT_A_REVOIR: "script à revoir (texte modifié ou jamais validé)",
}


def _pct(n: int, d: int) -> float:
    """Pourcentage ``n/d`` arrondi à 0,01 — ``0.0`` si le dénominateur est nul (jamais ``NaN``)."""
    return round(n / d * 100.0, 2) if d else 0.0


@dataclass(frozen=True)
class EffetRef:
    """Un effet d'une carte réduit à ce qui sert la couverture : son empreinte et son origine."""

    empreinte: str
    origine: str  # talent / attaque / dresseur (cf. `pbm_api.jeu.scripts.empreinte`)


@dataclass(frozen=True)
class CarteCouverture:
    """Une carte de l'univers : identité, extension, et ses effets dé-dupliqués par texte."""

    card_id: uuid.UUID
    set_id: uuid.UUID | None
    effets: tuple[EffetRef, ...]


def statut_effet(empreinte: str, registre: Mapping[str, str]) -> str:
    """Le statut d'un texte au registre, ou :data:`STATUT_ABSENT` si aucune ligne n'existe."""
    return registre.get(empreinte, STATUT_ABSENT)


def carte_jouable(carte: CarteCouverture, registre: Mapping[str, str]) -> bool:
    """Vrai si **tous** les effets de la carte sont scriptés (une carte sans effet l'est d'office).

    C'est la porte D9 au grain de la carte : un seul texte non scripté, et la carte n'est pas
    jouable — jamais « partiellement », jamais « au mieux ».
    """
    return all(
        registre.get(e.empreinte, STATUT_ABSENT) == SCRIPT_STATUT_SCRIPTE for e in carte.effets
    )


def raison_blocage(carte: CarteCouverture, registre: Mapping[str, str]) -> str | None:
    """La raison du **premier** effet non jouable de la carte, ou ``None`` si elle est jouable."""
    for e in carte.effets:
        st = registre.get(e.empreinte, STATUT_ABSENT)
        if st != SCRIPT_STATUT_SCRIPTE:
            raison = _RAISON_PAR_STATUT.get(st, f"statut inattendu « {st} »")
            return f"{e.origine} — {raison}"
    return None


# ----------------------------------------------------------------------- couverture au grain effet


@dataclass(frozen=True)
class CouvertureEffets:
    """Couverture au grain de l'EFFET (texte distinct) : scriptés vs le reste du chantier."""

    effets_distincts: int
    scriptes: int
    non_supportes: int
    a_revoir: int
    absents: int
    pct_scriptes: float


def couverture_effets(
    cartes: Iterable[CarteCouverture], registre: Mapping[str, str]
) -> CouvertureEffets:
    """Compte les textes d'effet **distincts** de l'univers par statut (un texte = une fois)."""
    empreintes: set[str] = set()
    for carte in cartes:
        empreintes.update(e.empreinte for e in carte.effets)
    scriptes = non_supportes = a_revoir = absents = 0
    for emp in empreintes:
        st = registre.get(emp, STATUT_ABSENT)
        if st == SCRIPT_STATUT_SCRIPTE:
            scriptes += 1
        elif st == SCRIPT_STATUT_NON_SUPPORTE:
            non_supportes += 1
        elif st == SCRIPT_STATUT_A_REVOIR:
            a_revoir += 1
        else:
            absents += 1
    total = len(empreintes)
    return CouvertureEffets(
        effets_distincts=total,
        scriptes=scriptes,
        non_supportes=non_supportes,
        a_revoir=a_revoir,
        absents=absents,
        pct_scriptes=_pct(scriptes, total),
    )


# ----------------------------------------------------------------------- couverture au grain carte


@dataclass(frozen=True)
class CouvertureCartes:
    """Couverture au grain de la CARTE : combien sont entièrement jouables.

    ``pct`` est calculé sur les cartes **porteuses d'effet** (``avec_effet``) : une extension pleine
    de Pokémon à dégâts secs afficherait sinon 100 % sans qu'aucun script n'ait été écrit.
    """

    cartes_total: int
    avec_effet: int
    jouables: int  # jouables au total (sans effet comprises)
    jouables_avec_effet: int
    pct: float


def couverture_cartes(
    cartes: Iterable[CarteCouverture], registre: Mapping[str, str]
) -> CouvertureCartes:
    """Compte les cartes entièrement jouables, en isolant celles qui portent réellement un effet."""
    total = avec_effet = jouables = jouables_avec_effet = 0
    for carte in cartes:
        total += 1
        porte = bool(carte.effets)
        jouable = carte_jouable(carte, registre)
        if porte:
            avec_effet += 1
            if jouable:
                jouables_avec_effet += 1
        if jouable:
            jouables += 1
    return CouvertureCartes(
        cartes_total=total,
        avec_effet=avec_effet,
        jouables=jouables,
        jouables_avec_effet=jouables_avec_effet,
        pct=_pct(jouables_avec_effet, avec_effet),
    )


@dataclass(frozen=True)
class CouvertureGroupe:
    """La couverture d'un sous-ensemble nommé (une extension, une famille d'effet, un joueur)."""

    cle: str
    libelle: str
    couverture: CouvertureCartes


def couverture_par_extension(
    cartes: Iterable[CarteCouverture],
    registre: Mapping[str, str],
    libelles: Mapping[uuid.UUID, str],
) -> list[CouvertureGroupe]:
    """Couverture carte par extension (``set_id``), triée de la moins couverte à la mieux couverte.

    Trier par couverture croissante met en tête les extensions où l'effort de scriptage paie le
    plus — l'outil sert à *diriger* l'effort, pas seulement à le constater.
    """
    par_set: dict[uuid.UUID, list[CarteCouverture]] = {}
    for carte in cartes:
        if carte.set_id is None:
            continue
        par_set.setdefault(carte.set_id, []).append(carte)
    groupes = [
        CouvertureGroupe(
            cle=str(set_id),
            libelle=libelles.get(set_id, str(set_id)),
            couverture=couverture_cartes(lot, registre),
        )
        for set_id, lot in par_set.items()
    ]
    groupes.sort(key=lambda g: (g.couverture.pct, g.libelle))
    return groupes


def couverture_par_famille(
    cartes: Iterable[CarteCouverture], registre: Mapping[str, str]
) -> list[CouvertureGroupe]:
    """Couverture au grain de l'EFFET par **famille** (origine : talent / attaque / dresseur).

    Le grain est l'effet, pas la carte : un même texte compte une fois par origine où il apparaît.
    """
    par_origine: dict[str, set[str]] = {}
    for carte in cartes:
        for e in carte.effets:
            par_origine.setdefault(e.origine, set()).add(e.empreinte)
    groupes: list[CouvertureGroupe] = []
    for origine, empreintes in par_origine.items():
        scriptes = sum(
            1 for emp in empreintes if registre.get(emp, STATUT_ABSENT) == SCRIPT_STATUT_SCRIPTE
        )
        total = len(empreintes)
        groupes.append(
            CouvertureGroupe(
                cle=origine,
                libelle=origine,
                couverture=CouvertureCartes(
                    cartes_total=total,
                    avec_effet=total,
                    jouables=scriptes,
                    jouables_avec_effet=scriptes,
                    pct=_pct(scriptes, total),
                ),
            )
        )
    groupes.sort(key=lambda g: (g.couverture.pct, g.libelle))
    return groupes


# ------------------------------------------------------------------------ couverture par collection


@dataclass(frozen=True)
class CouvertureCollection:
    """La couverture de la collection d'UN joueur : ce qu'il possède, et ce qu'il peut jouer."""

    user_id: str
    pseudo: str
    possedees_distinctes: int
    avec_effet: int
    jouables: int
    pct: float


def couverture_collections(
    collections: Sequence[tuple[uuid.UUID, str, set[uuid.UUID]]],
    cartes_par_id: Mapping[uuid.UUID, CarteCouverture],
    registre: Mapping[str, str],
) -> list[CouvertureCollection]:
    """Couverture pour chaque joueur, sur les cartes qu'il **possède réellement** (critère n°2).

    ``collections`` : la liste ``(user_id, pseudo, {card_id possédés})``. On trie de la collection
    la moins jouable à la plus jouable : c'est là que le joueur sent le manque, donc là où scripter
    aide le plus.
    """
    out: list[CouvertureCollection] = []
    for user_id, pseudo, card_ids in collections:
        cartes = [cartes_par_id[cid] for cid in card_ids if cid in cartes_par_id]
        cv = couverture_cartes(cartes, registre)
        out.append(
            CouvertureCollection(
                user_id=str(user_id),
                pseudo=pseudo,
                possedees_distinctes=len(card_ids),
                avec_effet=cv.avec_effet,
                jouables=cv.jouables_avec_effet,
                pct=cv.pct,
            )
        )
    out.sort(key=lambda c: (c.pct, c.pseudo))
    return out


# ------------------------------------------------------------------------- cartes qui bloquent le +


@dataclass(frozen=True)
class CarteManquante:
    """Une carte non jouable, pondérée par l'impact réel : decks bloqués, joueurs concernés."""

    card_id: str
    nom: str
    set_code: str
    raison: str
    decks_bloques: int
    joueurs_concernes: int
    exemplaires_possedes: int


def classer_cartes_manquantes(
    cartes: Iterable[CarteCouverture],
    registre: Mapping[str, str],
    noms: Mapping[uuid.UUID, str],
    set_codes: Mapping[uuid.UUID, str],
    decks_par_carte: Mapping[uuid.UUID, int],
    joueurs_par_carte: Mapping[uuid.UUID, int],
    exemplaires_par_carte: Mapping[uuid.UUID, int],
    limite: int | None = None,
) -> list[CarteManquante]:
    """Classe les cartes non jouables par impact décroissant : d'abord celles qui bloquent le plus
    de decks, puis le plus de joueurs (mission n°2). Scripter en tête de cette liste débloque le
    plus de monde pour le moins d'effort."""
    out: list[CarteManquante] = []
    for carte in cartes:
        raison = raison_blocage(carte, registre)
        if raison is None:  # jouable : rien à demander
            continue
        out.append(
            CarteManquante(
                card_id=str(carte.card_id),
                nom=noms.get(carte.card_id, str(carte.card_id)),
                set_code=set_codes.get(carte.set_id, "") if carte.set_id else "",
                raison=raison,
                decks_bloques=decks_par_carte.get(carte.card_id, 0),
                joueurs_concernes=joueurs_par_carte.get(carte.card_id, 0),
                exemplaires_possedes=exemplaires_par_carte.get(carte.card_id, 0),
            )
        )
    out.sort(
        key=lambda m: (m.decks_bloques, m.joueurs_concernes, m.exemplaires_possedes, m.nom),
        reverse=True,
    )
    return out[:limite] if limite is not None else out


# -------------------------------------------------------------------------------- rapport complet


@dataclass(frozen=True)
class DemandeAgregee:
    """Une carte demandée, agrégée pour la priorisation (combien de joueurs la veulent)."""

    card_id: str
    nom: str
    demandeurs: int
    en_attente: int
    jouable_maintenant: bool


@dataclass
class RapportCouverture:
    """Le rapport complet : global, par extension, par famille, par collection, + ce qui manque.

    ``univers_vide`` est posé quand aucun joueur du jeu ne possède de carte : le rapport le **dit**
    plutôt que d'afficher un 0 trompeur (la mesure n'a alors aucune collection réelle à mesurer).
    """

    joueurs: int
    univers_cartes: int
    effets: CouvertureEffets
    cartes: CouvertureCartes
    par_extension: list[CouvertureGroupe]
    par_famille: list[CouvertureGroupe]
    par_collection: list[CouvertureCollection]
    cartes_manquantes: list[CarteManquante]
    file_demandes: list[DemandeAgregee] = field(default_factory=list)
    univers_vide: bool = False


# --------------------------------------------------------------------------- adaptateur base (I/O)


async def charger_couverture(db, *, limite_manquantes: int | None = 50) -> RapportCouverture:
    """Construit le :class:`RapportCouverture` depuis la base — le seul endroit qui lit (donc hors
    du cœur pur). L'univers mesuré est volontairement **réduit aux collections réelles** des joueurs
    du jeu (`game_access`) et à leurs decks : mesurer le catalogue entier serait flatteur et inutile
    (risque du lot). Les lourds comptages (possession, decks) se font en SQL agrégé, jamais une
    requête par carte.
    """
    # Import local : l'adaptateur touche la base, le cœur pur ci-dessus n'importe pas SQLAlchemy.
    from sqlalchemy import func, select

    from pbm_api.jeu.scripts import demandes
    from pbm_api.models import (
        Card,
        CardScript,
        CollectionItem,
        Deck,
        DeckCard,
        Set,
        User,
    )

    # 1. Les joueurs du jeu (comptes invités) et leurs collections.
    joueurs = (
        await db.execute(
            select(User.id, User.pseudo).where(User.game_access.is_(True))
        )
    ).all()
    joueur_ids = [uid for uid, _ in joueurs]

    owned_rows: list = []
    if joueur_ids:
        owned_rows = (
            await db.execute(
                select(CollectionItem.user_id, CollectionItem.card_id)
                .where(CollectionItem.user_id.in_(joueur_ids))
                .distinct()
            )
        ).all()

    collections: dict[uuid.UUID, set[uuid.UUID]] = {uid: set() for uid in joueur_ids}
    joueurs_par_carte: dict[uuid.UUID, int] = {}
    for uid, cid in owned_rows:
        collections[uid].add(cid)
        joueurs_par_carte[cid] = joueurs_par_carte.get(cid, 0) + 1

    # Exemplaires possédés (toutes copies) par carte, chez les joueurs — pour pondérer le manque.
    exemplaires_par_carte: dict[uuid.UUID, int] = {}
    if joueur_ids:
        for cid, n in (
            await db.execute(
                select(CollectionItem.card_id, func.count())
                .where(CollectionItem.user_id.in_(joueur_ids))
                .group_by(CollectionItem.card_id)
            )
        ).all():
            exemplaires_par_carte[cid] = n

    # 2. Les decks de ces joueurs, et combien chacun contient une carte donnée.
    decks_par_carte: dict[uuid.UUID, int] = {}
    deck_card_ids: set[uuid.UUID] = set()
    if joueur_ids:
        for cid, n in (
            await db.execute(
                select(DeckCard.card_id, func.count(func.distinct(DeckCard.deck_id)))
                .join(Deck, Deck.id == DeckCard.deck_id)
                .where(Deck.user_id.in_(joueur_ids))
                .group_by(DeckCard.card_id)
            )
        ).all():
            decks_par_carte[cid] = n
            deck_card_ids.add(cid)

    # 3. L'univers réel : cartes possédées par un joueur, ou présentes dans l'un de leurs decks.
    univers_ids: set[uuid.UUID] = set(joueurs_par_carte) | deck_card_ids

    # 4. Le registre des scripts : empreinte → statut (table modeste, chargée en entier).
    registre: dict[str, str] = {
        emp: statut
        for emp, statut in (
            await db.execute(select(CardScript.text_fingerprint, CardScript.statut))
        ).all()
    }

    # 5. Les cartes de l'univers, avec leurs effets (abilities/attacks/effect lus par le cœur).
    cartes_par_id: dict[uuid.UUID, CarteCouverture] = {}
    noms: dict[uuid.UUID, str] = {}
    set_codes: dict[uuid.UUID, str] = {}
    libelles_set: dict[uuid.UUID, str] = {}
    if univers_ids:
        rows = (
            await db.execute(
                select(Card, Set.code, Set.name)
                .join(Set, Card.set_id == Set.id)
                .where(Card.id.in_(univers_ids))
            )
        ).all()
        for card, set_code, set_name in rows:
            effets = tuple(
                EffetRef(empreinte=e.empreinte, origine=e.origine)
                for e in effets_scriptables(card)
            )
            cartes_par_id[card.id] = CarteCouverture(
                card_id=card.id, set_id=card.set_id, effets=effets
            )
            noms[card.id] = card.name
            set_codes[card.set_id] = set_code
            libelles_set[card.set_id] = f"{set_name} ({set_code})"

    cartes = list(cartes_par_id.values())
    collections_seq = [
        (uid, pseudo, collections.get(uid, set())) for uid, pseudo in joueurs
    ]

    # 6. La file de demandes, agrégée pour la priorisation.
    file = await demandes.file_agregee(db)
    file_demandes = [
        DemandeAgregee(
            card_id=str(d.card_id),
            nom=d.nom,
            demandeurs=d.demandeurs,
            en_attente=d.en_attente,
            jouable_maintenant=d.jouable_maintenant,
        )
        for d in file
    ]

    return RapportCouverture(
        joueurs=len(joueur_ids),
        univers_cartes=len(cartes),
        effets=couverture_effets(cartes, registre),
        cartes=couverture_cartes(cartes, registre),
        par_extension=couverture_par_extension(cartes, registre, libelles_set),
        par_famille=couverture_par_famille(cartes, registre),
        par_collection=couverture_collections(collections_seq, cartes_par_id, registre),
        cartes_manquantes=classer_cartes_manquantes(
            cartes,
            registre,
            noms,
            set_codes,
            decks_par_carte,
            joueurs_par_carte,
            exemplaires_par_carte,
            limite=limite_manquantes,
        ),
        file_demandes=file_demandes,
        univers_vide=not cartes,
    )


# ------------------------------------------------------------------------------------- rendu / CLI


def rendu_texte(rapport: RapportCouverture) -> str:
    """Rend le rapport en texte lisible — la « page d'administration » de l'exploitation (critère
    n°2 : le chiffre par collection de joueur, pas seulement global)."""
    lignes: list[str] = []
    a = lignes.append
    a("=== Couverture des cartes jouables (collections réelles des joueurs) ===")
    a(f"Joueurs : {rapport.joueurs} · cartes dans l'univers mesuré : {rapport.univers_cartes}")
    if rapport.univers_vide:
        a("")
        a("AUCUNE carte dans l'univers : aucun joueur du jeu ne possède de carte, et aucun deck.")
        a("La couverture n'a aucune collection réelle à mesurer (c'est un fait, pas un 0 jouable).")
        return "\n".join(lignes)
    e = rapport.effets
    a("")
    a(f"Effets distincts : {e.effets_distincts} — scriptés {e.scriptes} ({e.pct_scriptes} %), "
      f"non supportés {e.non_supportes}, à revoir {e.a_revoir}, absents {e.absents}")
    c = rapport.cartes
    a(f"Cartes : {c.cartes_total} dont {c.avec_effet} avec effet — "
      f"jouables (avec effet) {c.jouables_avec_effet} ({c.pct} %)")

    a("")
    a("-- Par collection de joueur --")
    for col in rapport.par_collection:
        a(f"  {col.pseudo:<20} possédées {col.possedees_distinctes:>5} · avec effet "
          f"{col.avec_effet:>5} · jouables {col.jouables:>5} ({col.pct} %)")

    a("")
    a("-- Par famille d'effet --")
    for g in rapport.par_famille:
        cv = g.couverture
        a(f"  {g.libelle:<12} {cv.jouables_avec_effet}/{cv.avec_effet} ({cv.pct} %)")

    a("")
    a("-- Par extension (les moins couvertes d'abord) --")
    for g in rapport.par_extension[:20]:
        cv = g.couverture
        a(f"  {g.libelle:<40} {cv.jouables_avec_effet}/{cv.avec_effet} ({cv.pct} %)")

    a("")
    a("-- Cartes qui bloquent le plus (decks / joueurs) --")
    for m in rapport.cartes_manquantes[:20]:
        a(f"  {m.nom:<28} {m.set_code:<8} decks {m.decks_bloques:>3} · joueurs "
          f"{m.joueurs_concernes:>3} · {m.raison}")

    a("")
    a("-- File de demandes « je voudrais jouer cette carte » --")
    if not rapport.file_demandes:
        a("  (aucune demande)")
    for d in rapport.file_demandes:
        etat = "déjà jouable" if d.jouable_maintenant else "en attente"
        a(f"  {d.nom:<28} demandeurs {d.demandeurs:>3} · {etat}")
    return "\n".join(lignes)


def _rapport_en_dict(rapport: RapportCouverture) -> dict:
    """Le rapport en dict sérialisable JSON (pour un pilotage machine ou un futur affichage web)."""
    from dataclasses import asdict

    return asdict(rapport)


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée CLI (`python -m pbm_api.jeu.scripts.couverture [--json]`) — la page
    d'administration de la couverture, exécutée sur le serveur (jamais exposée en HTTP : le détail
    par collection est une donnée d'exploitation, pas ce qu'un joueur verrait d'un autre)."""
    import argparse
    import asyncio
    import json

    from pbm_api.db import async_session_factory

    parser = argparse.ArgumentParser(prog="python -m pbm_api.jeu.scripts.couverture")
    parser.add_argument("--json", action="store_true", help="Sort le rapport complet en JSON.")
    parser.add_argument(
        "--limite-manquantes",
        type=int,
        default=50,
        help="Nombre de cartes manquantes listées (défaut 50 ; 0 = toutes).",
    )
    args = parser.parse_args(argv)
    limite = args.limite_manquantes or None

    async def _run() -> RapportCouverture:
        async with async_session_factory() as db:
            return await charger_couverture(db, limite_manquantes=limite)

    rapport = asyncio.run(_run())
    if args.json:
        print(json.dumps(_rapport_en_dict(rapport), ensure_ascii=False, indent=2, default=str))
    else:
        print(rendu_texte(rapport))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "STATUT_ABSENT",
    "EffetRef",
    "CarteCouverture",
    "statut_effet",
    "carte_jouable",
    "raison_blocage",
    "CouvertureEffets",
    "couverture_effets",
    "CouvertureCartes",
    "couverture_cartes",
    "CouvertureGroupe",
    "couverture_par_extension",
    "couverture_par_famille",
    "CouvertureCollection",
    "couverture_collections",
    "CarteManquante",
    "classer_cartes_manquantes",
    "DemandeAgregee",
    "RapportCouverture",
    "charger_couverture",
    "rendu_texte",
    "main",
]
