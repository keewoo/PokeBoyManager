"""Ce qu'une partie laisse sur le compte — lot ``j-fin-effets-compte`` (jalon J4, DJ6).

Les trois critères d'acceptation du lot, chacun mesuré sur une partie **réellement jouée** par le
service (pas un résultat fabriqué à la main) :

1. **« Rejouer la clôture d'une partie ne modifie rien la deuxième fois »** —
   :func:`test_rejouer_la_cloture_ne_modifie_rien`. On photographie *toutes* les lignes écrites,
   on rappelle la clôture, et on compare les deux photos. Un ``if`` mal placé, une insertion sans
   contrainte, un compteur incrémenté : n'importe lequel de ces trois défauts fait rougir ce test.
2. **« Les statistiques recalculées depuis le journal correspondent à la partie jouée »** —
   :func:`test_les_chiffres_du_resultat_viennent_du_journal`. Les totaux attendus sont recomptés
   **ici**, à la main, depuis les lignes de ``game_events`` : si le service et ce test divergent,
   c'est le test qui le dit.
3. **« Une partie d'entraînement contre le bot n'affecte ni classement ni série »** —
   :func:`test_partie_entrainement_n_affecte_ni_totaux_ni_serie`.

Plus ce que la mission exige au-delà des critères : les fins **anormales** passent par le même
chemin d'écriture (abandon, inactivité), le **balayage** reprend une clôture manquante, et les
totaux sont bien un **cache** (les supprimer puis recalculer redonne la même ligne — c'est ce qui
rend le risque « un compteur faux que personne ne remarque » structurellement impossible).

Enfin quatre tests **purs** sur :func:`~pbm_api.games.fin_compte.cumuler`, sans base : c'est là que
vivent les séries, et une série se teste par cas, pas par partie jouée.

Les fixtures de partie sont reprises de ``test_games_fin_ui`` (qui les tenait de
``test_games_replay``) : ce trio de cartes mène déjà une partie jusqu'à la victoire par les
récompenses, et réinventer des fixtures ici ne mesurerait que mes propres approximations.

**Aucune route n'est ajoutée par ce lot** (couloir J-SRV) : l'écran « Mes parties » qui lira ces
tables est `j-stats-joueur`. Il n'y a donc pas de test d'accès croisé à écrire — il viendra avec la
route, et les lignes de ce lot sont déjà filtrées par ``user_id`` par construction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import familles_jeu
from sqlalchemy import select

from pbm_api.games.bot import BOT_USER_ID
from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.fin_compte import (
    LignePartie,
    cumuler,
    enregistrer_fin_de_partie,
    recalculer_stats_joueur,
    reprendre_fins_non_enregistrees,
)
from pbm_api.games.service import (
    abandonner_partie,
    appliquer_action,
    creer_partie,
    demarrer_partie,
    expirer_parties,
    reprendre_partie,
)
from pbm_api.models import (
    Card,
    CollectionItem,
    Deck,
    DeckCard,
    Game,
    GameEvent,
    GameResult,
    GameResultPlayer,
    PlayerStats,
    Set,
    User,
)
from pbm_api.models.fin_compte import (
    RESULTAT_DEFAITE,
    RESULTAT_EGALITE,
    RESULTAT_VICTOIRE,
)

GRAINE = "c3" * 32


# --- Fixtures : deux comptes, trois cartes, une partie qui va jusqu'au bout ---


#: L'identité minimale qu'exige la table `users` (reprise de ``test_games_mode_solo``).
_IDENTITE = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}


async def _user(db) -> User:
    """Un compte qui a l'accès jeu (D11) — le minimum pour s'asseoir à une partie."""
    u = User(
        email=f"fc-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="x",
        game_access=True,
        **_IDENTITE,
    )
    db.add(u)
    await db.flush()
    return u


async def _set(db) -> Set:
    s = Set(code=f"fc-{uuid.uuid4().hex[:8]}", name="Set fin de partie", series="Série test")
    db.add(s)
    await db.flush()
    return s


async def _pikachu(db, set_row) -> Card:
    """Attaquant : « Charge » coûte 1 énergie électrique, inflige 60 (K.O. une cible de 60 PV)."""
    c = Card(
        set_id=set_row.id, number=str(uuid.uuid4().int % 100000), name="Pikachu",
        supertype="Pokémon", energy_type="electrique", element_type="electrique", hp=60,
        stage="Base", retreat_cost=1, prize_marker="ordinaire",
        attacks=[{"name": "Charge", "cost": ["electrique"], "damage": "60", "effect": ""}],
    )
    db.add(c)
    await db.flush()
    return c


async def _energie(db, set_row) -> Card:
    c = Card(
        set_id=set_row.id, number=str(uuid.uuid4().int % 100000), name="Énergie Électrique",
        supertype="Énergie", energy_type="Normal", element_type="electrique",
    )
    db.add(c)
    await db.flush()
    return c


async def _cible(db, set_row) -> Card:
    """Défenseur : 3 récompenses (``tag_team``), 60 PV, aucune attaque (il ne riposte pas)."""
    c = Card(
        set_id=set_row.id, number=str(uuid.uuid4().int % 100000), name="Duo Tag",
        supertype="Pokémon", energy_type="incolore", element_type="incolore", hp=60,
        stage="Base", retreat_cost=0, prize_marker="tag_team", attacks=[],
    )
    db.add(c)
    await db.flush()
    return c


async def _deck(db, user_id: uuid.UUID, cartes: list[tuple[Card, int]]) -> Deck:
    """Un deck, et la collection qui va avec (chaque exemplaire possédé)."""
    deck = Deck(user_id=user_id, name="Deck fin de partie")
    db.add(deck)
    await db.flush()
    for card, qte in cartes:
        db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=qte))
        for _ in range(qte):
            db.add(CollectionItem(user_id=user_id, card_id=card.id))
    await db.flush()
    return deck


def _choisir(etat, jid, catalogue):
    """Stratégie minimale (reprise de ``test_games_fin_ui``) : avancer vers la victoire."""
    legales = actions_legales(etat, jid, familles=familles_jeu(catalogue))
    par_type: dict[str, list] = {}
    for coup in legales:
        par_type.setdefault(coup.action.type, []).append(coup)
    if "promouvoir" in par_type:
        return par_type["promouvoir"][0].action
    if "placer_mise_en_place" in par_type:
        return par_type["placer_mise_en_place"][0].action
    if "declarer_attaque" in par_type:
        return par_type["declarer_attaque"][0].action
    joueur = next(j for j in etat.joueurs if j.id == jid)
    if "attacher_energie" in par_type and joueur.actif is not None and not joueur.actif.energies:
        actif_id = joueur.actif.cartes[0].instance_id
        sur_actif = [
            c for c in par_type["attacher_energie"] if c.action.params.get("cible") == actif_id
        ]
        if sur_actif:
            return sur_actif[0].action
    if "avancer_phase" in par_type:
        return par_type["avancer_phase"][0].action
    return legales[0].action if legales else None


async def _jouer(db, game: Game, a_id: uuid.UUID, b_id: uuid.UUID, *, plafond: int) -> Game:
    """Joue la partie coup par coup, au plus ``plafond`` coups (ou jusqu'à sa fin)."""
    user_par_jid = {joueur_id_de(a_id): a_id, joueur_id_de(b_id): b_id}
    for _ in range(plafond):
        game = await db.get(Game, game.id)
        if game.status != "en_cours":
            break
        etat, _rng = await reprendre_partie(db, game)
        catalogue = await construire_catalogue_jeu(db, etat)
        if etat.mise_en_place is not None:
            idx = next(i for i, p in enumerate(etat.mise_en_place.placements) if p is None)
            acteur = etat.joueurs[idx].id
        else:
            acteur = etat.tour.joueur_actif
        action = _choisir(etat, acteur, catalogue)
        assert action is not None, f"aucun coup pour {acteur} (phase {etat.tour.phase})"
        await appliquer_action(
            db,
            game_id=game.id,
            user_id=user_par_jid[acteur],
            type=action.type,
            params=action.params,
            numero_attendu=game.current_numero,
        )
    return await db.get(Game, game.id)


async def _partie_finie(db) -> tuple[Game, User, User, uuid.UUID, uuid.UUID]:
    """Deux comptes, une partie jouée **jusqu'à une victoire par les récompenses**."""
    a, b = await _user(db), await _user(db)
    s = await _set(db)
    deck_a = await _deck(db, a.id, [(await _pikachu(db, s), 6), (await _energie(db, s), 14)])
    deck_b = await _deck(db, b.id, [(await _cible(db, s), 20)])
    game = await creer_partie(
        db, joueur_a=(a.id, deck_a.id), joueur_b=(b.id, deck_b.id), graine_hex=GRAINE
    )
    await demarrer_partie(db, game)
    game = await _jouer(db, game, a.id, b.id, plafond=600)
    assert game.status == "terminee", f"la partie devait se terminer (statut : {game.status})"
    assert game.vainqueur_user_id is not None, "cette partie se gagne par les récompenses"
    return game, a, b, deck_a.id, deck_b.id


async def _resultat(db, game_id: uuid.UUID) -> GameResult | None:
    return (
        await db.execute(select(GameResult).where(GameResult.game_id == game_id))
    ).scalar_one_or_none()


async def _stats(db, user_id: uuid.UUID) -> PlayerStats | None:
    """Les totaux d'un joueur **relus depuis la base**, pas depuis la session.

    ``populate_existing`` n'est pas un détail : sans lui, la session rendrait l'objet qu'elle a
    déjà en mémoire, et un test « rien n'a changé » pourrait passer en ne regardant qu'un cache.
    (Et un objet simplement expiré se rechargerait hors du pont greenlet de SQLAlchemy async,
    ce qui lève ``MissingGreenlet`` au premier attribut lu.)
    """
    return (
        await db.execute(
            select(PlayerStats)
            .where(PlayerStats.user_id == user_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def _lignes(db, game_id: uuid.UUID) -> list[GameResultPlayer]:
    rows = await db.execute(
        select(GameResultPlayer)
        .where(GameResultPlayer.game_id == game_id)
        .order_by(GameResultPlayer.seat)
    )
    return list(rows.scalars().all())


def _photo_resultat(resultat: GameResult) -> dict:
    """Tout ce qu'une ligne de résultat porte — pour comparer un avant et un après."""
    return {
        c.key: getattr(resultat, c.key) for c in GameResult.__mapper__.column_attrs
    }


def _photo_stats(stats: PlayerStats) -> dict:
    """Les totaux d'un joueur, sans ``updated_at`` : on compare des chiffres, pas une date.

    ``updated_at`` est exclu *exprès* : il bouge à chaque réécriture de la ligne, et l'inclure
    ferait passer ce test pour « rien n'a changé » uniquement par chance. Ce qu'on veut savoir,
    c'est qu'aucun **compteur** n'a bougé.
    """
    return {
        "parties": stats.parties,
        "victoires": stats.victoires,
        "defaites": stats.defaites,
        "egalites": stats.egalites,
        "serie_en_cours": stats.serie_en_cours,
        "meilleure_serie": stats.meilleure_serie,
        "temps_jeu_s": stats.temps_jeu_s,
        "parties_entrainement": stats.parties_entrainement,
        "temps_jeu_entrainement_s": stats.temps_jeu_entrainement_s,
        "derniere_partie_a": stats.derniere_partie_a,
    }


# --- Les totaux : fonction pure, testée par cas ------------------------------


def _ligne(resultat: str, *, jour: int, comptabilisee: bool = True, duree: int | None = 60):
    """Une ligne de partie datée du ``jour`` de janvier 2026 — pour fixer l'ordre sans ambiguïté."""
    return LignePartie(
        resultat=resultat,
        comptabilisee=comptabilisee,
        duree_s=duree,
        finie_a=datetime(2026, 1, jour, 12, 0, tzinfo=UTC),
    )


def test_cumuler_compte_les_resultats_et_la_serie_en_cours():
    """Trois victoires de suite après une défaite : série en cours 3, meilleure série 3."""
    totaux = cumuler(
        [
            _ligne(RESULTAT_VICTOIRE, jour=1),
            _ligne(RESULTAT_DEFAITE, jour=2),
            _ligne(RESULTAT_VICTOIRE, jour=3),
            _ligne(RESULTAT_VICTOIRE, jour=4),
            _ligne(RESULTAT_VICTOIRE, jour=5),
        ]
    )
    assert (totaux.parties, totaux.victoires, totaux.defaites) == (5, 4, 1)
    assert totaux.serie_en_cours == 3
    assert totaux.meilleure_serie == 3
    assert totaux.temps_jeu_s == 300


def test_cumuler_garde_la_meilleure_serie_quand_elle_est_cassee():
    """La meilleure série ne redescend jamais : 3 victoires, une défaite, une victoire → 1 et 3."""
    totaux = cumuler(
        [
            _ligne(RESULTAT_VICTOIRE, jour=1),
            _ligne(RESULTAT_VICTOIRE, jour=2),
            _ligne(RESULTAT_VICTOIRE, jour=3),
            _ligne(RESULTAT_DEFAITE, jour=4),
            _ligne(RESULTAT_VICTOIRE, jour=5),
        ]
    )
    assert totaux.serie_en_cours == 1
    assert totaux.meilleure_serie == 3


def test_cumuler_interrompt_la_serie_sur_une_egalite():
    """Une égalité n'est pas une victoire : elle casse la série au lieu de la prolonger."""
    totaux = cumuler(
        [
            _ligne(RESULTAT_VICTOIRE, jour=1),
            _ligne(RESULTAT_EGALITE, jour=2),
            _ligne(RESULTAT_VICTOIRE, jour=3),
        ]
    )
    assert (totaux.victoires, totaux.egalites) == (2, 1)
    assert totaux.serie_en_cours == 1, "la série repart de zéro après l'égalité"
    assert totaux.meilleure_serie == 1


def test_cumuler_ignore_les_parties_non_comptabilisees_jusque_dans_la_serie():
    """Critère 3, au niveau du calcul : l'entraînement ne nourrit ni ne casse une série.

    Deux victoires classées encadrant une **défaite** d'entraînement : la série vaut 2, et non 1.
    C'est le cas qui échouerait si l'entraînement était simplement exclu des totaux sans l'être
    de la série.
    """
    totaux = cumuler(
        [
            _ligne(RESULTAT_VICTOIRE, jour=1),
            _ligne(RESULTAT_DEFAITE, jour=2, comptabilisee=False, duree=30),
            _ligne(RESULTAT_VICTOIRE, jour=3),
        ]
    )
    assert (totaux.parties, totaux.victoires, totaux.defaites) == (2, 2, 0)
    assert totaux.serie_en_cours == 2
    assert totaux.parties_entrainement == 1
    assert totaux.temps_jeu_entrainement_s == 30
    assert totaux.temps_jeu_s == 120, "le temps d'entraînement ne gonfle pas le temps classé"


def test_cumuler_n_invente_pas_un_temps_de_jeu_inconnu():
    """Une durée illisible (``None``) n'ajoute rien : un temps sous-estimé plutôt qu'inventé."""
    totaux = cumuler([_ligne(RESULTAT_VICTOIRE, jour=1, duree=None)])
    assert totaux.parties == 1
    assert totaux.temps_jeu_s == 0


# --- Critère 2 : les chiffres viennent du journal ----------------------------


async def test_la_cloture_ecrit_le_resultat_les_lignes_et_les_totaux(db_session):
    """La fin d'une partie jouée laisse une trace complète, sans qu'on ait rien à déclencher.

    Le service l'écrit au passage du coup final : ce test ne rappelle **aucune** fonction de
    clôture, il joue la partie et regarde la base.
    """
    game, a, b, deck_a, deck_b = await _partie_finie(db_session)

    resultat = await _resultat(db_session, game.id)
    assert resultat is not None, "la partie close n'a laissé aucun résultat"
    assert resultat.statut == "terminee"
    assert resultat.raison_fin == game.raison_fin
    assert resultat.vainqueur_user_id == game.vainqueur_user_id
    assert resultat.entrainement is False
    assert resultat.comptabilisee is True
    assert resultat.journal_numero == game.current_numero
    assert resultat.coups == game.current_numero

    lignes = await _lignes(db_session, game.id)
    assert [ligne.seat for ligne in lignes] == [0, 1]
    assert [ligne.deck_id for ligne in lignes] == [deck_a, deck_b]
    assert lignes[0].adversaire_user_id == b.id and lignes[1].adversaire_user_id == a.id
    assert all(ligne.adversaire_bot is False for ligne in lignes)
    resultats = {ligne.user_id: ligne.resultat for ligne in lignes}
    assert resultats[game.vainqueur_user_id] == RESULTAT_VICTOIRE
    perdant = next(uid for uid in (a.id, b.id) if uid != game.vainqueur_user_id)
    assert resultats[perdant] == RESULTAT_DEFAITE

    gagnant = await _stats(db_session, game.vainqueur_user_id)
    assert (gagnant.parties, gagnant.victoires, gagnant.defaites) == (1, 1, 0)
    assert gagnant.serie_en_cours == 1 and gagnant.meilleure_serie == 1
    assert gagnant.parties_entrainement == 0
    assert gagnant.derniere_partie_a == resultat.finie_a
    battu = await _stats(db_session, perdant)
    assert (battu.parties, battu.victoires, battu.defaites) == (1, 0, 1)
    assert battu.serie_en_cours == 0


async def test_les_chiffres_du_resultat_viennent_du_journal(db_session):
    """Critère 2 — chaque chiffre écrit est celui du journal, recompté **ici** indépendamment.

    On ne compare pas le service à lui-même : les totaux attendus sont reconstruits par un parcours
    écrit à la main des lignes de ``game_events``.
    """
    game, _a, _b, _da, _db = await _partie_finie(db_session)
    entrees = list(
        (
            await db_session.execute(
                select(GameEvent).where(GameEvent.game_id == game.id).order_by(GameEvent.numero)
            )
        )
        .scalars()
        .all()
    )

    degats: dict[str, int] = {}
    kos: dict[str, int] = {}
    recompenses: dict[str, int] = {}
    energies: dict[str, int] = {}
    tours = 0
    for entree in entrees:
        for evt in entree.evenements:
            donnees = evt.get("donnees") or {}
            genre = evt.get("type")
            if genre == "tour_commence":
                tours = max(tours, int(donnees.get("numero") or 0))
            elif genre == "attaque_declaree":
                jid = donnees.get("joueur")
                degats[jid] = degats.get(jid, 0) + int(donnees.get("degats") or 0)
            elif genre == "ko":
                par = donnees.get("par")
                kos[par] = kos.get(par, 0) + 1
                recompenses[par] = recompenses.get(par, 0) + int(
                    donnees.get("recompenses_prises") or 0
                )
            elif genre == "energie_attachee":
                jid = donnees.get("joueur")
                energies[jid] = energies.get(jid, 0) + 1

    resultat = await _resultat(db_session, game.id)
    assert resultat.coups == len(entrees)
    assert resultat.tours == tours

    for ligne in await _lignes(db_session, game.id):
        jid = joueur_id_de(ligne.user_id)
        assert ligne.degats_infliges == degats.get(jid, 0), jid
        assert ligne.kos_infliges == kos.get(jid, 0), jid
        assert ligne.recompenses_prises == recompenses.get(jid, 0), jid
        assert ligne.energies_attachees == energies.get(jid, 0), jid
        assert ligne.coups_joues == sum(1 for e in entrees if e.auteur == jid), jid

    # La partie se gagne par les récompenses : le vainqueur en a donc pris, et a frappé.
    gagnante = next(
        ligne
        for ligne in await _lignes(db_session, game.id)
        if ligne.user_id == game.vainqueur_user_id
    )
    assert gagnante.recompenses_prises > 0 and gagnante.degats_infliges > 0


# --- Critère 1 : rejouer la clôture ne modifie rien --------------------------


async def test_rejouer_la_cloture_ne_modifie_rien(db_session):
    """Critère 1 — la deuxième clôture de la même partie n'écrit rien, et ne double rien.

    C'est le test que ferait rougir un compteur incrémenté : une victoire comptée deux fois, une
    seconde ligne de résultat, une série à 2 sur une seule partie. On compare les lignes **champ
    par champ**, avant et après.
    """
    game, a, b, _da, _db = await _partie_finie(db_session)

    avant_resultat = _photo_resultat(await _resultat(db_session, game.id))
    avant_lignes = [
        (ligne.id, ligne.user_id, ligne.resultat, ligne.degats_infliges, ligne.coups_joues)
        for ligne in await _lignes(db_session, game.id)
    ]
    avant_stats = {
        uid: _photo_stats(await _stats(db_session, uid)) for uid in (a.id, b.id)
    }

    # Le rejeu : exactement ce qu'un second événement de fin, une reprise ou le balayage ferait.
    assert await enregistrer_fin_de_partie(db_session, game.id) is False, (
        "la seconde clôture doit se déclarer sans effet"
    )

    toutes = (
        (await db_session.execute(select(GameResult).where(GameResult.game_id == game.id)))
        .scalars()
        .all()
    )
    assert len(toutes) == 1, "une partie n'a qu'un résultat"
    assert _photo_resultat(await _resultat(db_session, game.id)) == avant_resultat
    assert [
        (ligne.id, ligne.user_id, ligne.resultat, ligne.degats_infliges, ligne.coups_joues)
        for ligne in await _lignes(db_session, game.id)
    ] == avant_lignes
    for uid in (a.id, b.id):
        assert _photo_stats(await _stats(db_session, uid)) == avant_stats[uid], uid


async def test_une_troisieme_cloture_ne_change_rien_non_plus(db_session):
    """Et ce n'est pas « la deuxième seulement » : la clôture est sans effet autant de fois qu'on
    la rejoue (rejeu d'un coup, reprise après F5, balayage — ils peuvent tous se cumuler)."""
    game, a, _b, _da, _db = await _partie_finie(db_session)
    for _ in range(3):
        assert await enregistrer_fin_de_partie(db_session, game.id) is False
    stats = await _stats(db_session, a.id)
    assert stats.parties == 1, "une partie jouée, une partie comptée"


# --- Critère 3 : l'entraînement ne compte pas -------------------------------


async def test_partie_entrainement_n_affecte_ni_totaux_ni_serie(db_session):
    """Critère 3 — une partie contre le bot entre dans l'historique, mais ne compte pas.

    On la clôt par un abandon : c'est la fin la plus courte, et elle emprunte le même chemin
    d'écriture que la victoire par les règles (mission du lot).
    """
    humain = await _user(db_session)
    s = await _set(db_session)
    deck = await _deck(
        db_session,
        humain.id,
        [(await _pikachu(db_session, s), 6), (await _energie(db_session, s), 14)],
    )
    game = await creer_partie(
        db_session,
        joueur_a=(humain.id, deck.id),
        joueur_b=(BOT_USER_ID, deck.id),
        entrainement=True,
        bot_niveau="hasard",
        graine_hex=GRAINE,
    )
    await demarrer_partie(db_session, game)
    await abandonner_partie(db_session, game.id, humain.id)
    game = await db_session.get(Game, game.id)
    assert game.status == "terminee" and game.entrainement is True

    resultat = await _resultat(db_session, game.id)
    assert resultat is not None, "l'entraînement entre bien dans l'historique (DJ6)"
    assert resultat.entrainement is True
    assert resultat.comptabilisee is False, "elle ne compte ni pour les totaux ni pour la série"

    lignes = await _lignes(db_session, game.id)
    ligne_humaine = next(ligne for ligne in lignes if ligne.user_id == humain.id)
    assert ligne_humaine.resultat == RESULTAT_DEFAITE, "il a abandonné"
    assert ligne_humaine.adversaire_bot is True, "son adversaire était le bot, pas un compte"
    assert ligne_humaine.comptabilisee is False

    stats = await _stats(db_session, humain.id)
    assert (stats.parties, stats.victoires, stats.defaites) == (0, 0, 0)
    assert stats.serie_en_cours == 0 and stats.meilleure_serie == 0
    assert stats.parties_entrainement == 1, "l'entraînement est compté à part, pas perdu"
    assert stats.derniere_partie_a is not None, "il a bien joué, et ça se voit"


# --- Les fins anormales passent par le même chemin ---------------------------


async def test_abandon_entre_deux_comptes_laisse_la_trace_du_forfait(db_session):
    """Un abandon (R-14.3) écrit la même trace qu'une fin par les règles : l'adversaire gagne."""
    a, b = await _user(db_session), await _user(db_session)
    s = await _set(db_session)
    deck_a = await _deck(
        db_session, a.id, [(await _pikachu(db_session, s), 6), (await _energie(db_session, s), 14)]
    )
    deck_b = await _deck(db_session, b.id, [(await _cible(db_session, s), 20)])
    game = await creer_partie(
        db_session, joueur_a=(a.id, deck_a.id), joueur_b=(b.id, deck_b.id), graine_hex=GRAINE
    )
    await demarrer_partie(db_session, game)
    await abandonner_partie(db_session, game.id, a.id)

    resultat = await _resultat(db_session, game.id)
    assert resultat is not None and resultat.comptabilisee is True
    assert resultat.vainqueur_user_id == b.id
    assert resultat.raison_fin == "abandon"

    stats_a = await _stats(db_session, a.id)
    stats_b = await _stats(db_session, b.id)
    assert (stats_a.victoires, stats_a.defaites) == (0, 1)
    assert (stats_b.victoires, stats_b.defaites) == (1, 0)
    assert stats_b.serie_en_cours == 1


async def test_partie_expiree_entre_dans_l_historique_sans_compter(db_session):
    """Une partie close faute d'activité : trace oui, résultat non.

    Personne ne l'a jouée jusqu'au bout — la compter en défaite pour les deux joueurs serait
    inventer un résultat (D9). Elle est donc enregistrée en égalité, non comptabilisée.
    """
    a, b = await _user(db_session), await _user(db_session)
    s = await _set(db_session)
    deck_a = await _deck(
        db_session, a.id, [(await _pikachu(db_session, s), 6), (await _energie(db_session, s), 14)]
    )
    deck_b = await _deck(db_session, b.id, [(await _cible(db_session, s), 20)])
    game = await creer_partie(
        db_session, joueur_a=(a.id, deck_a.id), joueur_b=(b.id, deck_b.id), graine_hex=GRAINE
    )
    await demarrer_partie(db_session, game)
    # Quelques coups d'abord : pendant la mise en place (R-4), le moteur refuse — à juste titre —
    # le coup système d'expiration. Une partie fantôme est une partie commencée puis délaissée.
    game = await _jouer(db_session, game, a.id, b.id, plafond=10)
    assert game.status == "en_cours", "dix coups ne finissent pas cette partie"
    game.expires_at = game.expires_at - timedelta(days=30)
    await db_session.flush()

    assert await expirer_parties(db_session) == 1
    game = await db_session.get(Game, game.id)
    assert game.status == "expiree"

    resultat = await _resultat(db_session, game.id)
    assert resultat is not None, "une partie expirée laisse quand même sa trace"
    assert resultat.statut == "expiree"
    assert resultat.comptabilisee is False
    assert all(
        ligne.resultat == RESULTAT_EGALITE for ligne in await _lignes(db_session, game.id)
    ), "sans vainqueur, personne n'a perdu"

    stats = await _stats(db_session, a.id)
    assert (stats.parties, stats.defaites) == (0, 0)


# --- Reprise après panne, et le cache qui se recalcule -----------------------


async def test_le_balayage_reprend_une_cloture_manquante_et_le_dit(db_session):
    """Mission 4 — une partie close dont l'écriture a échoué est reprise par le balayage.

    On simule l'échec en supprimant ce que la clôture avait écrit : c'est l'état exact d'un serveur
    tué entre le commit du coup et celui de la trace, et celui d'une partie close avant ce lot.
    """
    game, a, b, _da, _db = await _partie_finie(db_session)
    attendu = _photo_resultat(await _resultat(db_session, game.id))

    for ligne in await _lignes(db_session, game.id):
        await db_session.delete(ligne)
    await db_session.delete(await _resultat(db_session, game.id))
    await db_session.flush()
    assert await _resultat(db_session, game.id) is None

    rapport = await reprendre_fins_non_enregistrees(db_session)
    assert rapport["reprises"] >= 1, "le balayage doit avoir repris cette partie"
    assert rapport["restantes"] == 0

    repare = await _resultat(db_session, game.id)
    assert repare is not None
    # Tout est retrouvé à l'identique, sauf l'identifiant de ligne et sa date d'écriture : les
    # chiffres viennent du journal, qui n'a pas bougé.
    photo = _photo_resultat(repare)
    for champ in ("id", "created_at"):
        attendu.pop(champ)
        photo.pop(champ)
    assert photo == attendu
    assert len(await _lignes(db_session, game.id)) == 2

    assert (await _stats(db_session, game.vainqueur_user_id)).victoires == 1

    # Et un second passage ne trouve plus rien : un balayage qui répare deux fois doublerait tout.
    assert await reprendre_fins_non_enregistrees(db_session) == {"reprises": 0, "restantes": 0}


async def test_les_totaux_sont_un_cache_qui_se_recalcule_a_l_identique(db_session):
    """Le risque nommé du lot, pris à la racine : les totaux ne sont jamais incrémentés.

    On supprime la ligne de totaux et on la recalcule depuis les parties : elle revient identique.
    Ce test est la garantie qu'une erreur de compteur n'est jamais définitive — il n'y a pas de
    compteur, seulement une relecture.
    """
    game, a, _b, _da, _db = await _partie_finie(db_session)
    attendu = _photo_stats(await _stats(db_session, a.id))

    await db_session.delete(await _stats(db_session, a.id))
    await db_session.flush()
    assert await _stats(db_session, a.id) is None

    totaux = await recalculer_stats_joueur(db_session, a.id)
    await db_session.flush()
    assert _photo_stats(await _stats(db_session, a.id)) == attendu
    assert totaux.parties == 1

    # Et le recalcul est idempotent : le refaire ne change rien non plus.
    await recalculer_stats_joueur(db_session, a.id)
    await db_session.flush()
    assert _photo_stats(await _stats(db_session, a.id)) == attendu


async def test_une_partie_en_cours_ne_laisse_aucune_trace(db_session):
    """Rien n'est écrit avant la fin : une partie en cours n'a ni résultat ni totaux.

    Sans ce test, une écriture déclenchée trop tôt (à chaque coup, par exemple) passerait inaperçue
    tant que les chiffres finissent par être justes.
    """
    a, b = await _user(db_session), await _user(db_session)
    s = await _set(db_session)
    deck_a = await _deck(
        db_session, a.id, [(await _pikachu(db_session, s), 6), (await _energie(db_session, s), 14)]
    )
    deck_b = await _deck(db_session, b.id, [(await _cible(db_session, s), 20)])
    game = await creer_partie(
        db_session, joueur_a=(a.id, deck_a.id), joueur_b=(b.id, deck_b.id), graine_hex=GRAINE
    )
    await demarrer_partie(db_session, game)
    game = await _jouer(db_session, game, a.id, b.id, plafond=6)
    assert game.status == "en_cours", "six coups ne suffisent pas à finir cette partie"

    assert await _resultat(db_session, game.id) is None
    assert await _lignes(db_session, game.id) == []
    assert await _stats(db_session, a.id) is None
    assert await enregistrer_fin_de_partie(db_session, game.id) is False
