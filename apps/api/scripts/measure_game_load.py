#!/usr/bin/env python
"""Mesure la **tenue en charge** du jeu : ce qu'une partie coûte, et combien on en tient à la fois.

Lot ``j-charge-temps-reel``. Le jeu est servi par un serveur partagé (2 vCPU, 3,8 Go) qui héberge
déjà d'autres sites : il faut savoir **avant**, pas pendant. Ce script produit les quatre chiffres
qui fixent le plafond de ``settings.jeu_parties_simultanees_max`` et dimensionnent la purge, et
``docs/jeu/CHARGE.md`` les recopie avec leur date — ce sont eux qu'on relira le jour d'un incident.

Il ne tourne **jamais** sur la machine qui sert (règle d'or de la flotte : on ne construit pas, et
on ne mesure pas, sur le serveur qui répond aux joueurs). Sa place est chimera, bornée à deux cœurs
pour ressembler à la cible :

    taskset -c 0,1 uv run python scripts/measure_game_load.py --json /tmp/charge.json

Ce qu'il mesure, et pourquoi chacun compte :

1. **Octets en base par partie** (``--parties-completes``) — des parties jouées **jusqu'à leur
   fin** par les bots, et la taille des trois tables avant/après. C'est la mesure qui dimensionne
   la purge : sans elle, « purger au bout de 30 jours » est un chiffre sans contenu. Mesure exacte,
   insensible au bruit de la machine.
2. **Coups par partie** — le journal est append-only, donc son volume *est* l'activité. Une partie
   médiane tourne autour de 215 coups (campagne de bots du lot ``j-simulation-bots``) ; on le
   revérifie ici avec la base dans la boucle.
3. **Coût processeur d'un coup** — temps CPU du processus (``getrusage``), et, quand le conteneur
   Postgres est lisible, son temps CPU à lui (``cpu.stat`` du cgroup). Les deux comptent : sur la
   cible, l'API et la base se partagent les mêmes deux cœurs.
4. **Latence d'un coup sous concurrence** (``--paliers``) — K parties qui jouent en même temps, et
   la distribution des durées. Le **point de rupture** est le premier palier dont la p95 dépasse
   :data:`SEUIL_JOUABILITE_MS` : au-delà, le joueur sent le serveur, et toutes les parties se
   dégradent ensemble — ce que le plafond existe pour éviter.

⚠️ Ce que ce script **ne** prouve **pas**, et qu'il faut lire dans ``docs/jeu/CHARGE.md`` : chimera
a seize cœurs dont ce script n'utilise que deux, mais son Postgres garde les autres. La part
« base de données » est donc mesurée, pas *contrainte* — la cible, où les deux cœurs sont partagés
entre tout, sera plus lente. Le plafond retenu en tient compte par une marge explicite.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import resource
import statistics
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import familles_jeu
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pbm_api.config import settings
from pbm_api.games.bot import BOT_USER_ID, jouer_coups_bot
from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.service import (
    appliquer_action,
    creer_partie,
    demarrer_partie,
    purger,
    reprendre_partie,
)
from pbm_api.models import Card, CollectionItem, Deck, DeckCard, Game, Set, User
from pbm_api.models.games import GAME_STATUS_TERMINEE

#: Au-delà de cette latence au 95e centile, un coup se *sent* : l'écran reste muet le temps d'un
#: battement de cœur, et le jeu cesse d'être agréable. C'est le critère qui définit le point de
#: rupture — un serveur « qui répond encore » à 3 s par coup est déjà cassé pour un enfant de onze
#: ans, et c'est lui qu'on sert (principe du jeu).
SEUIL_JOUABILITE_MS = 500.0

#: Paliers de concurrence par défaut : assez serrés autour de la zone utile (une poignée de
#: parties) pour que le point de rupture ne soit pas « entre 8 et 32 ».
PALIERS_DEFAUT = (1, 2, 4, 8, 12, 16, 24, 32)

#: Nom du conteneur Postgres de chimera (``docs/infra/JOBS-LOURDS.md``). Sert uniquement à **lire**
#: son temps processeur ; ce script n'écrit jamais dans une base partagée.
CONTENEUR_POSTGRES = "pbm-shared-postgres-1"

#: Les trois tables dont le volume suit les parties. ``jeu_incidents`` n'y est pas : elle survit
#: délibérément à la purge des parties (``ON DELETE SET NULL``), son volume est celui des pannes.
TABLES_DU_JEU = ("games", "game_events", "game_snapshots")

#: Bases que ce script refuse de toucher : la référence du catalogue de chimera est **partagée** et
#: en lecture seule pour les lots (``docs/infra/JOBS-LOURDS.md``). La mesure crée des joueurs, des
#: cartes et des parties : elle veut sa propre base, et le refus est la réponse — pas un
#: contournement par option.
BASES_INTERDITES = ("pbm_catalogue_ref", "pokeboy_prod", "pokeboy_uat")

#: Fabrique de sessions du script, posée par :func:`ouvrir_moteur`. On n'emprunte pas celle de
#: l'application (``pbm_api.db``) : son pool de cinq connexions (plus dix de débordement) se
#: saturerait au-delà de quinze parties simultanées, et on mesurerait alors la file d'attente de
#: SQLAlchemy en croyant mesurer celle du serveur.
_fabrique: async_sessionmaker | None = None


def ouvrir_moteur(parties_max: int):
    """Ouvre un moteur dont le pool tient ``parties_max`` parties, et refuse une base partagée.

    Chaque partie simultanée veut sa connexion : un pool plus petit sérialiserait la mesure. On
    prend donc ``parties_max + 4`` connexions (les quatre de marge servent aux mesures de taille et
    à la purge de contrôle, qui tournent hors des parties).
    """
    global _fabrique
    url = settings.database_url
    nom_base = url.rsplit("/", 1)[-1].split("?")[0]
    if nom_base in BASES_INTERDITES:
        raise SystemExit(
            f"⛔ DATABASE_URL pointe sur « {nom_base} », une base partagée ou de production. "
            "Cette mesure écrit (joueurs, cartes, parties) : donne-lui une base dédiée, par "
            "exemple TEST_DATABASE_URL=…/pbm_charge_test."
        )
    moteur = create_async_engine(
        url, pool_pre_ping=True, pool_size=parties_max + 4, max_overflow=4
    )
    _fabrique = async_sessionmaker(moteur, expire_on_commit=False)
    return moteur, nom_base


def async_session_factory():
    """La fabrique du script, posée par :func:`ouvrir_moteur` — le reste du code l'ignore."""
    if _fabrique is None:  # pragma: no cover — erreur de programmation, jamais un cas d'usage
        raise RuntimeError("ouvrir_moteur() n'a pas été appelé : aucune fabrique de session.")
    return _fabrique()


@dataclass
class Palier:
    """Ce qu'un palier de concurrence a donné."""

    parties_simultanees: int
    coups: int
    duree_totale_s: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    coups_par_seconde: float
    cpu_process_ms_par_coup: float
    cpu_postgres_ms_par_coup: float | None
    rss_max_mo: float
    tenable: bool


@dataclass
class Mesure:
    """Le relevé complet, tel qu'il part en JSON et tel que ``CHARGE.md`` le recopie."""

    machine: str
    coeurs_utilisables: int
    date_mesure: str
    parties_completes: int
    coups_par_partie_median: float | None = None
    coups_par_partie_moyen: float | None = None
    octets_par_partie: dict[str, float] = field(default_factory=dict)
    octets_par_partie_total: float = 0.0
    octets_par_partie_apres_purge: float | None = None
    #: La grandeur la plus transférable : une partie longue en écrit plus, mais le coût d'un coup
    #: ne dépend pas de la longueur. C'est elle qu'on multiplie pour projeter un volume.
    octets_par_coup: float | None = None
    paliers: list[dict] = field(default_factory=list)
    point_de_rupture: int | None = None
    plafond_tenable: int | None = None
    avertissements: list[str] = field(default_factory=list)


# --- Lecture des coûts système -----------------------------------------------------------------


def _cpu_process_ms() -> float:
    """Temps processeur consommé par ce processus (utilisateur + système), en millisecondes."""
    r = resource.getrusage(resource.RUSAGE_SELF)
    return (r.ru_utime + r.ru_stime) * 1000.0


def _rss_max_mo() -> float:
    """Pic de mémoire résidente du processus, en mégaoctets (Linux rend des kilooctets)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _cpu_postgres_ms(avertissements: list[str]) -> float | None:
    """Temps processeur cumulé du conteneur Postgres, en millisecondes (``None`` si illisible).

    Lu dans ``cpu.stat`` du cgroup du conteneur : c'est un **cumul**, donc une différence entre
    deux lectures donne la consommation de l'intervalle. On ne retombe pas en silence sur « 0 » si
    la lecture échoue — un coût mesuré à zéro serait un mensonge ; on rend ``None`` et on le dit.

    ⚠️ Le conteneur est **partagé** sur chimera : un autre travail qui interroge la base pendant la
    mesure gonfle ce chiffre. Il est indicatif, et c'est écrit dans le rapport.
    """
    try:
        sortie = subprocess.run(
            ["docker", "exec", CONTENEUR_POSTGRES, "cat", "/sys/fs/cgroup/cpu.stat"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError) as exc:
        message = f"temps CPU de Postgres non mesuré ({type(exc).__name__}) : part base inconnue"
        if message not in avertissements:
            avertissements.append(message)
        return None
    for ligne in sortie.splitlines():
        if ligne.startswith("usage_usec"):
            return float(ligne.split()[1]) / 1000.0
    avertissements.append("cpu.stat lu mais sans usage_usec : part base inconnue")
    return None


async def _vacuum(moteur) -> None:
    """``VACUUM ANALYZE`` sur les tables du jeu — en AUTOCOMMIT, seul mode où Postgres l'accepte."""
    async with moteur.connect() as connexion:
        await connexion.execution_options(isolation_level="AUTOCOMMIT")
        await connexion.execute(text("VACUUM ANALYZE games, game_events, game_snapshots"))


async def _taille_tables(db) -> dict[str, int]:
    """Taille totale (table + index + TOAST) des tables du jeu, en octets."""
    tailles = {}
    for table in TABLES_DU_JEU:
        tailles[table] = int(
            (
                await db.execute(
                    text("SELECT pg_total_relation_size(:t)"), {"t": f"public.{table}"}
                )
            ).scalar_one()
        )
    return tailles


# --- Fabrique d'un plateau jouable -------------------------------------------------------------


async def _semer_joueur(db) -> tuple[User, Deck]:
    """Un joueur et un deck de **soixante cartes** à dégâts secs, entièrement jouable (D9).

    Les proportions comptent pour la mesure, et la première version de ce script l'a appris à ses
    dépens : avec vingt cartes et un attaquant qui met K.O. d'un coup, les parties finissaient en
    **sept coups** et l'empreinte par partie était vingt fois trop basse. Ici l'attaquant a 120 PV
    et frappe à 30 : il faut quatre attaques pour un K.O., et les parties retrouvent la longueur
    des campagnes de bots (médiane ~215 coups, lot ``j-simulation-bots``). C'est la seule façon de
    mesurer des octets par partie qui veuillent dire quelque chose.
    """
    joueur = User(
        email=f"charge-{uuid.uuid4().hex[:10]}@example.invalid",
        password_hash="x",
        game_access=True,
        last_name="Mesure",
        birth_date=date(2000, 1, 1),
        terms_version="mesure",
        terms_accepted_at=datetime(2000, 1, 1),
    )
    db.add(joueur)
    await db.flush()

    jeu_de_cartes = Set(
        code=f"chg-{uuid.uuid4().hex[:8]}", name="Set de mesure", series="Mesure de charge"
    )
    db.add(jeu_de_cartes)
    await db.flush()
    attaquant = Card(
        set_id=jeu_de_cartes.id, number=str(uuid.uuid4().int % 100000), name="Pikachu",
        supertype="Pokémon", energy_type="electrique", element_type="electrique", hp=120,
        stage="Base", retreat_cost=1, prize_marker="ordinaire",
        attacks=[{"name": "Charge", "cost": ["electrique"], "damage": "30", "effect": ""}],
    )
    energie = Card(
        set_id=jeu_de_cartes.id, number=str(uuid.uuid4().int % 100000),
        name="Énergie Électrique", supertype="Énergie", energy_type="Normal",
        element_type="electrique",
    )
    db.add_all([attaquant, energie])
    await db.flush()

    deck = Deck(user_id=joueur.id, name="Deck de mesure")
    db.add(deck)
    await db.flush()
    for carte, quantite in ((attaquant, 20), (energie, 40)):
        db.add(DeckCard(deck_id=deck.id, card_id=carte.id, quantity=quantite))
        if carte.supertype == "Pokémon":
            for _ in range(quantite):
                db.add(CollectionItem(user_id=joueur.id, card_id=carte.id))
    await db.commit()
    return joueur, deck


def _choisir_coup(etat, jid, catalogue, alea: random.Random):
    """Stratégie de mesure : promouvoir, placer, attaquer, charger l'Actif, sinon avancer.

    Volontairement la même que celle des tests du mode solo : on mesure le coût d'une partie
    *vraisemblable*, pas celui d'un bot qui passe son tour (qui ne chargerait rien) ni d'un bot qui
    abandonne (qui finirait la partie en trois coups et fausserait les octets par partie).
    """
    legales = actions_legales(etat, jid, familles=familles_jeu(catalogue))
    par_type: dict[str, list] = {}
    for coup in legales:
        par_type.setdefault(coup.action.type, []).append(coup)
    for prefere in ("promouvoir", "placer_mise_en_place", "declarer_attaque"):
        if prefere in par_type:
            return par_type[prefere][0].action
    joueur = next(j for j in etat.joueurs if j.id == jid)
    if "attacher_energie" in par_type and joueur.actif is not None and not joueur.actif.energies:
        cible = joueur.actif.cartes[0].instance_id
        attaches = par_type["attacher_energie"]
        sur_actif = [c for c in attaches if c.action.params.get("cible") == cible]
        if sur_actif:
            return sur_actif[0].action
    if "avancer_phase" in par_type:
        return par_type["avancer_phase"][0].action
    if not legales:
        return None
    return alea.choice(legales).action


async def _jouer_une_partie(
    *, max_coups: int, latences_ms: list[float] | None, graine: int
) -> tuple[int, bool]:
    """Joue une partie d'entraînement dans **sa propre session**, et rend (coups joués, finie).

    Chaque partie ouvre sa session : c'est ce qui rend la mesure de concurrence honnête — K parties
    qui se partageraient une connexion se sérialiseraient d'elles-mêmes, et on mesurerait la file
    d'attente de SQLAlchemy plutôt que celle du serveur.

    Un coup qui ne peut pas être choisi arrête la partie **en le rendant** (``finie=False``) :
    jamais un coup inventé, jamais un ``continue`` muet.
    """
    alea = random.Random(graine)
    coups = 0
    finie = False
    async with async_session_factory() as db:
        joueur, deck = await _semer_joueur(db)
        partie = await creer_partie(
            db,
            joueur_a=(joueur.id, deck.id),
            joueur_b=(BOT_USER_ID, deck.id),
            entrainement=True,
            bot_niveau="correct",
        )
        await demarrer_partie(db, partie)
        await jouer_coups_bot(db, partie.id)

        jid = joueur_id_de(joueur.id)
        for _ in range(max_coups):
            partie = await db.get(Game, partie.id)
            if partie.status != "en_cours":
                finie = True
                break
            etat, _rng = await reprendre_partie(db, partie)
            catalogue = await construire_catalogue_jeu(db, etat)
            if etat.mise_en_place is not None:
                indice = next(i for i, j in enumerate(etat.joueurs) if j.id == jid)
                if etat.mise_en_place.placements[indice] is not None:
                    await jouer_coups_bot(db, partie.id)
                    continue
            elif etat.tour.joueur_actif != jid:
                await jouer_coups_bot(db, partie.id)
                continue
            action = _choisir_coup(etat, jid, catalogue, alea)
            if action is None:
                break
            depart = time.perf_counter()
            await appliquer_action(
                db,
                game_id=partie.id,
                user_id=joueur.id,
                type=action.type,
                params=action.params,
                numero_attendu=partie.current_numero,
            )
            if latences_ms is not None:
                latences_ms.append((time.perf_counter() - depart) * 1000.0)
            coups += 1
    return coups, finie


# --- Les quatre mesures ------------------------------------------------------------------------


async def mesurer_empreinte_en_base(mesure: Mesure, parties: int, moteur) -> None:
    """Mesure 1 et 2 : octets en base par partie **jouée jusqu'au bout**, et coups par partie.

    On joue de vraies parties complètes, puis on divise : une partie tronquée à quarante coups
    sous-estimerait le journal d'un facteur cinq, et c'est le journal qui pèse.
    """
    async with async_session_factory() as db:
        avant = await _taille_tables(db)
        parties_avant = int((await db.execute(select(func.count()).select_from(Game))).scalar_one())

    coups_par_partie: list[int] = []
    for i in range(parties):
        coups, finie = await _jouer_une_partie(max_coups=4000, latences_ms=None, graine=1000 + i)
        coups_par_partie.append(coups)
        if not finie:
            mesure.avertissements.append(
                f"partie {i + 1} arrêtée à {coups} coups sans conclusion : empreinte sous-estimée"
            )

    # VACUUM hors transaction : sans lui, les tailles lues comptent aussi les lignes mortes des
    # mises à jour de `games`, et l'octet par partie serait surévalué.
    await _vacuum(moteur)
    async with async_session_factory() as db:
        apres = await _taille_tables(db)
        parties_apres = int((await db.execute(select(func.count()).select_from(Game))).scalar_one())

    creees = max(1, parties_apres - parties_avant)
    mesure.octets_par_partie = {
        table: round((apres[table] - avant[table]) / creees, 1) for table in TABLES_DU_JEU
    }
    mesure.octets_par_partie_total = round(sum(mesure.octets_par_partie.values()), 1)
    total_coups = sum(coups_par_partie)
    mesure.octets_par_coup = (
        round(sum(apres[t] - avant[t] for t in TABLES_DU_JEU) / total_coups, 1)
        if total_coups
        else None
    )
    mesure.coups_par_partie_median = (
        statistics.median(coups_par_partie) if coups_par_partie else None
    )
    mesure.coups_par_partie_moyen = (
        round(statistics.fmean(coups_par_partie), 1) if coups_par_partie else None
    )

    # Mesure 1 bis : ce que la purge rend. Elle efface les parties mortes anciennes *et* les
    # instantanés intermédiaires de toutes les parties — c'est ce second effet qu'on mesure ici,
    # les parties venant d'être jouées n'étant pas encore anciennes.
    async with async_session_factory() as db:
        await db.execute(
            text(
                "UPDATE games SET status = :fini, updated_at = now() - interval '400 days' "
                "WHERE id IN (SELECT id FROM games ORDER BY created_at DESC LIMIT :n)"
            ),
            {"fini": GAME_STATUS_TERMINEE, "n": creees},
        )
        await db.commit()
        rapport = await purger(db)
    await _vacuum(moteur)
    async with async_session_factory() as db:
        apres_purge = await _taille_tables(db)
    mesure.octets_par_partie_apres_purge = round(
        sum(apres_purge[t] - avant[t] for t in TABLES_DU_JEU) / creees, 1
    )
    mesure.avertissements.append(
        f"purge de contrôle : {rapport.get('parties_purgees', 0)} partie(s), "
        f"{rapport.get('instantanes_purges', 0)} instantané(s)"
    )


async def mesurer_palier(parties_simultanees: int, coups: int, avertissements: list[str]) -> Palier:
    """Mesure 3 et 4 : K parties jouées en même temps, et la distribution des latences d'un coup."""
    latences: list[float] = []
    cpu_pg_avant = _cpu_postgres_ms(avertissements)
    cpu_avant = _cpu_process_ms()
    depart = time.perf_counter()

    resultats = await asyncio.gather(
        *(
            _jouer_une_partie(max_coups=coups, latences_ms=latences, graine=i)
            for i in range(parties_simultanees)
        ),
        return_exceptions=True,
    )
    duree = time.perf_counter() - depart
    cpu = _cpu_process_ms() - cpu_avant
    cpu_pg_apres = _cpu_postgres_ms(avertissements)

    for i, r in enumerate(resultats):
        if isinstance(r, BaseException):
            # Jamais avalé : une partie qui casse sous charge est le résultat le plus intéressant
            # de la mesure, pas un détail d'intendance.
            avertissements.append(
                f"palier {parties_simultanees} : partie {i} en échec — "
                f"{type(r).__name__}: {r}"
            )

    joues = len(latences)
    if joues == 0:
        avertissements.append(f"palier {parties_simultanees} : aucun coup joué — palier non mesuré")
        return Palier(
            parties_simultanees=parties_simultanees, coups=0, duree_totale_s=round(duree, 2),
            p50_ms=0.0, p95_ms=0.0, p99_ms=0.0, max_ms=0.0, coups_par_seconde=0.0,
            cpu_process_ms_par_coup=0.0, cpu_postgres_ms_par_coup=None,
            rss_max_mo=round(_rss_max_mo(), 1), tenable=False,
        )

    ordonnees = sorted(latences)

    def centile(part: float) -> float:
        return round(ordonnees[min(len(ordonnees) - 1, int(part * len(ordonnees)))], 1)

    cpu_pg = (
        round((cpu_pg_apres - cpu_pg_avant) / joues, 3)
        if cpu_pg_avant is not None and cpu_pg_apres is not None
        else None
    )
    p95 = centile(0.95)
    return Palier(
        parties_simultanees=parties_simultanees,
        coups=joues,
        duree_totale_s=round(duree, 2),
        p50_ms=centile(0.50),
        p95_ms=p95,
        p99_ms=centile(0.99),
        max_ms=round(ordonnees[-1], 1),
        coups_par_seconde=round(joues / duree, 1) if duree > 0 else 0.0,
        cpu_process_ms_par_coup=round(cpu / joues, 3),
        cpu_postgres_ms_par_coup=cpu_pg,
        rss_max_mo=round(_rss_max_mo(), 1),
        tenable=p95 <= SEUIL_JOUABILITE_MS,
    )


# --- Rapport -----------------------------------------------------------------------------------


def _coeurs_utilisables() -> int:
    """Nombre de cœurs réellement accessibles (``taskset`` compris), pas ceux de la machine."""
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:  # pragma: no cover — hors Linux
        return os.cpu_count() or 1


def afficher(mesure: Mesure) -> None:
    """Le rapport lisible : d'abord les chiffres, ensuite ce qu'ils ne disent pas."""
    print(f"\n=== Tenue en charge du jeu — {mesure.machine}, "
          f"{mesure.coeurs_utilisables} cœur(s) utilisable(s), {mesure.date_mesure}\n")
    print(f"Parties complètes jouées : {mesure.parties_completes}")
    print(f"Coups par partie : médiane {mesure.coups_par_partie_median}, "
          f"moyenne {mesure.coups_par_partie_moyen}")
    print("\nEmpreinte en base, par partie :")
    for table, octets in mesure.octets_par_partie.items():
        print(f"  {table:<16} {octets / 1024:>9.1f} Kio")
    print(f"  {'TOTAL':<16} {mesure.octets_par_partie_total / 1024:>9.1f} Kio")
    if mesure.octets_par_coup is not None:
        print(f"  {'par coup':<16} {mesure.octets_par_coup:>9.0f} o")
    if mesure.octets_par_partie_apres_purge is not None:
        print(f"  {'après purge':<16} {mesure.octets_par_partie_apres_purge / 1024:>9.1f} Kio")

    print(
        f"\nLatence d'un coup par palier "
        f"(seuil de jouabilité : p95 ≤ {SEUIL_JOUABILITE_MS:.0f} ms)"
    )
    print(f"  {'K':>3} {'coups':>7} {'p50':>8} {'p95':>8} {'p99':>8} {'max':>9} "
          f"{'coups/s':>8} {'CPU/coup':>9} {'PG/coup':>8} {'RSS Mo':>8}  verdict")
    for p in mesure.paliers:
        pg = f"{p['cpu_postgres_ms_par_coup']:.1f}" if p["cpu_postgres_ms_par_coup"] else "  n/d"
        print(f"  {p['parties_simultanees']:>3} {p['coups']:>7} {p['p50_ms']:>7.1f}ms "
              f"{p['p95_ms']:>7.1f}ms {p['p99_ms']:>7.1f}ms {p['max_ms']:>8.1f}ms "
              f"{p['coups_par_seconde']:>8.1f} {p['cpu_process_ms_par_coup']:>8.1f}ms {pg:>8} "
              f"{p['rss_max_mo']:>8.1f}  {'tenable' if p['tenable'] else 'ROMPU'}")

    print(f"\nPoint de rupture : {mesure.point_de_rupture or 'non atteint sur ces paliers'}")
    print(f"Plafond tenable mesuré : {mesure.plafond_tenable}")
    if mesure.avertissements:
        print("\nCe que cette mesure ne dit pas :")
        for a in mesure.avertissements:
            print(f"  — {a}")


async def _liberer_les_places(moteur) -> None:
    """Clôt les parties du palier qui vient de finir, pour que le suivant démarre d'une base nette.

    Sans ça, les paliers s'additionnent : le palier 32 trouverait les 63 parties des paliers
    précédents encore « en cours », et mesurerait une base qui n'a rien à voir avec 32 parties.
    """
    async with async_session_factory() as db:
        await db.execute(
            text("UPDATE games SET status = :fini WHERE status = :encours"),
            {"fini": GAME_STATUS_TERMINEE, "encours": "en_cours"},
        )
        await db.commit()


async def principal(args: argparse.Namespace) -> int:
    import socket

    moteur, nom_base = ouvrir_moteur(max(args.paliers))
    mesure = Mesure(
        machine=socket.gethostname(),
        coeurs_utilisables=_coeurs_utilisables(),
        date_mesure=datetime.now().isoformat(timespec="seconds"),
        parties_completes=args.parties_completes,
    )
    mesure.avertissements.append(f"base de mesure : {nom_base}")
    if mesure.coeurs_utilisables > 4:
        mesure.avertissements.append(
            f"mesure faite sur {mesure.coeurs_utilisables} cœurs alors que la cible en a 2 : "
            "relancer sous « taskset -c 0,1 » pour un résultat transférable"
        )

    # Le plafond de capacité est **levé pendant la mesure**, et c'est le seul endroit du dépôt où
    # ça se fait : on mesure précisément pour savoir où le poser. Hors de ce script, le refus du
    # plafond est la réponse (jamais une variable de contournement).
    plafond_initial = settings.jeu_parties_simultanees_max
    settings.jeu_parties_simultanees_max = max(args.paliers) * 4 + 100
    mesure.avertissements.append(
        f"plafond de capacité levé pour la mesure ({plafond_initial} → "
        f"{settings.jeu_parties_simultanees_max}) : sans quoi la mesure buterait sur la garde "
        "qu'elle sert à calibrer"
    )

    try:
        if args.parties_completes > 0:
            print(f"→ empreinte en base ({args.parties_completes} parties complètes)…", flush=True)
            await mesurer_empreinte_en_base(mesure, args.parties_completes, moteur)
            await _liberer_les_places(moteur)

        for k in args.paliers:
            print(f"→ palier {k} partie(s) simultanée(s)…", flush=True)
            palier = await mesurer_palier(k, args.coups_par_partie, mesure.avertissements)
            mesure.paliers.append(asdict(palier))
            if not palier.tenable and mesure.point_de_rupture is None:
                mesure.point_de_rupture = k
            await _liberer_les_places(moteur)
    finally:
        settings.jeu_parties_simultanees_max = plafond_initial

    tenables = [p["parties_simultanees"] for p in mesure.paliers if p["tenable"]]
    mesure.plafond_tenable = max(tenables) if tenables else 0
    if mesure.point_de_rupture is None and tenables:
        mesure.avertissements.append(
            f"aucun palier rompu jusqu'à {max(tenables)} : le plafond tenable est au moins "
            "celui-là, la vraie limite n'a pas été atteinte"
        )

    afficher(mesure)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as sortie:
            json.dump(asdict(mesure), sortie, ensure_ascii=False, indent=2)
        print(f"\nJSON écrit : {args.json}")
    await moteur.dispose()
    return 0


def analyser_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(
        description="Mesure la tenue en charge du jeu (lot j-charge-temps-reel).",
        epilog="À lancer sur chimera, borné à deux cœurs : « taskset -c 0,1 uv run python … ».",
    )
    analyseur.add_argument(
        "--paliers",
        type=lambda v: tuple(int(x) for x in v.split(",")),
        default=PALIERS_DEFAUT,
        help="paliers de parties simultanées, séparés par des virgules",
    )
    analyseur.add_argument(
        "--coups-par-partie", type=int, default=40,
        help="coups joués par partie dans un palier (40 suffit : on mesure une latence)",
    )
    analyseur.add_argument(
        "--parties-completes", type=int, default=6,
        help="parties jouées jusqu'au bout pour l'empreinte en base (0 pour sauter cette mesure)",
    )
    analyseur.add_argument("--json", help="fichier où écrire le relevé complet")
    return analyseur.parse_args(argv)


if __name__ == "__main__":
    sys.exit(asyncio.run(principal(analyser_arguments())))
