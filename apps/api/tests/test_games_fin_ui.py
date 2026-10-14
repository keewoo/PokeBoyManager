"""Fin de partie : récapitulatif depuis le journal et revanche — lot ``j-partie-fin-ui``.

Les trois critères d'acceptation du lot, mesurés sur des parties **réellement jouées** par l'API
(pas un journal fabriqué à la main) :

1. **« Chaque raison de fin possible a son libellé propre »** — la partie des libellés est gardée
   côté moteur (``apps/game/tests/test_parite_raisons_fin_front.py``, qui lit ``fin.ts``). Ici on
   vérifie le pendant serveur : le récapitulatif **rend** la raison de fin et le vainqueur, qui
   sont ce que l'écran traduit. Sans eux, il n'y aurait rien à libeller.
2. **« La revanche relance une partie sans repasser par la file »** — un seul appel, et la
   nouvelle partie existe, avec les mêmes joueurs et les mêmes decks, le perdant au siège 0. Plus
   le cas de la course : les deux joueurs cliquent, et les deux arrivent sur la **même** partie.
3. **« Le récapitulatif est exact, recalculé depuis le journal »** — on compare chaque chiffre à ce
   que porte le journal en base, relevé indépendamment par SQL. Et on le demande **deux fois** :
   deux lectures rendent les mêmes chiffres (rien n'est accumulé entre les deux).

Plus les gardes d'isolation, obligatoires sur toute route utilisateur : un compte qui ne joue pas
la partie reçoit **404** sur le récapitulatif comme sur la revanche — jamais 403, qui révélerait
l'existence de la partie.

Les fixtures de partie sont reprises de ``test_games_replay`` : ce trio de cartes y mène déjà une
partie jusqu'à la victoire par les récompenses, et réinventer des fixtures ici ne mesurerait que
mes propres approximations.
"""

import re
import uuid

import httpx
import pytest
from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import familles_jeu
from sqlalchemy import select

from pbm_api.config import settings
from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.service import (
    appliquer_action,
    creer_partie,
    demarrer_partie,
    reprendre_partie,
)
from pbm_api.models import (
    Card,
    CollectionItem,
    Deck,
    DeckCard,
    Game,
    GameEvent,
    GamePlayer,
    Set,
    User,
)
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"
GRAINE = "a1" * 32


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> str:
    """Inscrit, vérifie et connecte un compte ; renvoie son identifiant."""
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "last_name": "Dresseur",
            "birth_date": "2000-01-01",
            "accept_terms": True,
        },
    )
    assert response.status_code == 202, response.text
    sent = client.email_sender.sent  # type: ignore[attr-defined]
    match = re.search(r"token=(\S+)", sent[-1]["body"])
    assert match
    await client.post("/auth/verify-email", json={"token": match.group(1)})
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return login.json()["id"]


async def _login(client: httpx.AsyncClient, email: str) -> str:
    """Connecte un compte et renvoie son jeton CSRF (exigé par les routes d'écriture)."""
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return client.cookies.get(settings.csrf_cookie_name)


async def _set(db) -> Set:
    s = Set(code=f"fu-{uuid.uuid4().hex[:8]}", name="Set fin", series="Série test")
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
    """Un deck, **et la collection qui va avec** : chaque exemplaire est possédé.

    La possession n'est pas un détail de fixture : la revanche recontrôle les decks avec
    :func:`~pbm_api.games.lancement.verifier_lancable`, qui exige que chaque carte non-Énergie soit
    possédée en quantité suffisante. Un deck sans collection serait refusé — exactement comme une
    carte vendue entre deux parties, ce que teste
    :func:`test_revanche_refusee_quand_une_carte_a_ete_vendue`.
    """
    deck = Deck(user_id=user_id, name="Deck fin")
    db.add(deck)
    await db.flush()
    for card, qte in cartes:
        db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=qte))
        for _ in range(qte):
            db.add(CollectionItem(user_id=user_id, card_id=card.id))
    await db.flush()
    return deck


def _choisir(etat, jid, catalogue):
    """Stratégie minimale (reprise de `test_games_replay`) : avancer vers la victoire."""
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


async def _partie_jouee(
    db, a_id: uuid.UUID, b_id: uuid.UUID, *, jusqu_a_la_fin: bool
) -> tuple[Game, uuid.UUID, uuid.UUID]:
    """Crée une partie entre deux comptes, la joue, et renvoie ``(partie, deck_a, deck_b)``."""
    s = await _set(db)
    deck_a = await _deck(db, a_id, [(await _pikachu(db, s), 6), (await _energie(db, s), 14)])
    deck_b = await _deck(db, b_id, [(await _cible(db, s), 20)])
    game = await creer_partie(
        db, joueur_a=(a_id, deck_a.id), joueur_b=(b_id, deck_b.id), graine_hex=GRAINE
    )
    await demarrer_partie(db, game)
    game = await _jouer(db, game, a_id, b_id, plafond=600 if jusqu_a_la_fin else 6)
    return game, deck_a.id, deck_b.id


async def _trois_comptes(api_client, db_session):
    """Trois comptes invités (D11) : les deux joueurs A et B, et l'intrus C."""
    emails = {k: _email(k) for k in ("a", "b", "c")}
    ids: dict[str, uuid.UUID] = {}
    for k, email in emails.items():
        ids[k] = uuid.UUID(await _register_verify_login(api_client, email))
    for k, uid in ids.items():
        u = await db_session.get(User, uid)
        u.pseudo = f"{k}-{uuid.uuid4().hex[:6]}"
        u.game_access = True
    await db_session.flush()
    return emails, ids


async def _journal(db, game_id: uuid.UUID) -> list[GameEvent]:
    """Le journal de la partie, dans l'ordre — la **référence** à laquelle on compare."""
    rows = await db.execute(
        select(GameEvent).where(GameEvent.game_id == game_id).order_by(GameEvent.numero)
    )
    return list(rows.scalars().all())


# --- Critère 3 : le récapitulatif est exact, et recalculé depuis le journal ---


async def test_recapitulatif_correspond_au_journal_en_base(api_client, db_session):
    """Chaque chiffre du récapitulatif est celui que porte le journal, relevé indépendamment.

    On ne compare pas le service à lui-même : les totaux attendus sont recomptés **ici**, depuis
    les lignes de ``game_events``, par un parcours écrit à la main. Si le moteur et ce test
    divergent, c'est le test qui le dit.
    """
    emails, ids = await _trois_comptes(api_client, db_session)
    game, _deck_a, _deck_b = await _partie_jouee(
        db_session, ids["a"], ids["b"], jusqu_a_la_fin=True
    )
    assert game.status == "terminee", f"la partie devait se terminer (statut : {game.status})"

    entrees = await _journal(db_session, game.id)
    attendu_degats: dict[str, int] = {}
    attendu_kos: dict[str, int] = {}
    attendu_recompenses: dict[str, int] = {}
    tours = 0
    for entree in entrees:
        for evt in entree.evenements:
            donnees = evt.get("donnees") or {}
            if evt.get("type") == "tour_commence":
                tours = max(tours, int(donnees.get("numero") or 0))
            elif evt.get("type") == "attaque_declaree":
                jid = donnees.get("joueur")
                attendu_degats[jid] = attendu_degats.get(jid, 0) + int(donnees.get("degats") or 0)
            elif evt.get("type") == "ko":
                par = donnees.get("par")
                attendu_kos[par] = attendu_kos.get(par, 0) + 1
                attendu_recompenses[par] = attendu_recompenses.get(par, 0) + int(
                    donnees.get("recompenses_prises") or 0
                )

    await _login(api_client, emails["a"])
    r = await api_client.get(f"/games/{game.id}/recapitulatif")
    assert r.status_code == 200, r.text
    recap = r.json()

    assert recap["coups"] == len(entrees), "le nombre de coups est celui du journal"
    assert recap["tours"] == tours
    assert recap["statut"] == "terminee"
    assert recap["raison_fin"] == game.raison_fin
    assert recap["vainqueur_user_id"] == (
        str(game.vainqueur_user_id) if game.vainqueur_user_id else None
    )
    sieges_rendus = [j["seat"] for j in recap["joueurs"]]
    assert sieges_rendus == [0, 1], "les joueurs sont dans l'ordre des sièges"

    for joueur in recap["joueurs"]:
        jid = joueur_id_de(uuid.UUID(joueur["user_id"]))
        assert joueur["degats_infliges"] == attendu_degats.get(jid, 0), joueur["user_id"]
        assert joueur["kos_infliges"] == attendu_kos.get(jid, 0), joueur["user_id"]
        assert joueur["recompenses_prises"] == attendu_recompenses.get(jid, 0), joueur["user_id"]
        assert joueur["coups_joues"] == sum(1 for e in entrees if e.auteur == jid)

    # Le vainqueur de cette partie gagne par les récompenses : il en a donc pris au moins une.
    gagnant = next(
        j for j in recap["joueurs"] if j["user_id"] == recap["vainqueur_user_id"]
    )
    assert gagnant["recompenses_prises"] > 0
    assert gagnant["degats_infliges"] > 0


async def test_deux_lectures_du_recapitulatif_donnent_les_memes_chiffres(api_client, db_session):
    """Le risque nommé du lot : rien ne s'accumule entre deux demandes.

    C'est le test qui échouerait si le récapitulatif était tenu au fil de l'eau quelque part : on
    le demande deux fois d'affilée, et les deux réponses doivent être identiques à l'octet près (le
    second appel ne doit rien ajouter à ce qu'a compté le premier).
    """
    emails, ids = await _trois_comptes(api_client, db_session)
    game, _a, _b = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=True)
    await _login(api_client, emails["a"])

    premier = await api_client.get(f"/games/{game.id}/recapitulatif")
    second = await api_client.get(f"/games/{game.id}/recapitulatif")
    assert premier.status_code == 200 and second.status_code == 200
    assert premier.json() == second.json()


async def test_les_deux_joueurs_voient_le_meme_recapitulatif(api_client, db_session):
    """Un récapitulatif dont les chiffres dépendent de qui regarde n'est pas un récapitulatif.

    C'est pour ça qu'il est calculé depuis le journal **en base** (complet) et non depuis les
    événements projetés que chaque joueur reçoit (filtrés par destinataire).
    """
    emails, ids = await _trois_comptes(api_client, db_session)
    game, _a, _b = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=True)

    await _login(api_client, emails["a"])
    vu_par_a = (await api_client.get(f"/games/{game.id}/recapitulatif")).json()
    await _login(api_client, emails["b"])
    vu_par_b = (await api_client.get(f"/games/{game.id}/recapitulatif")).json()
    assert vu_par_a == vu_par_b


async def test_recapitulatif_d_une_partie_en_cours_est_refuse(api_client, db_session):
    """Une partie en cours n'a pas de récapitulatif : 409, comme le replay."""
    emails, ids = await _trois_comptes(api_client, db_session)
    game, _a, _b = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=False)
    assert game.status == "en_cours"
    await _login(api_client, emails["a"])
    r = await api_client.get(f"/games/{game.id}/recapitulatif")
    assert r.status_code == 409, r.text


async def test_recapitulatif_d_une_partie_d_autrui_repond_404(api_client, db_session):
    """Accès croisé : l'intrus reçoit 404 (jamais 403 — l'existence ne se révèle pas)."""
    emails, ids = await _trois_comptes(api_client, db_session)
    game, _a, _b = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=True)
    await _login(api_client, emails["c"])
    r = await api_client.get(f"/games/{game.id}/recapitulatif")
    assert r.status_code == 404, r.text


# --- Critère 2 : la revanche relance sans repasser par la file ---------------


async def test_la_revanche_relance_la_partie_avec_les_memes_joueurs_et_decks(
    api_client, db_session
):
    """Un seul appel, et la partie existe : mêmes comptes, mêmes decks, **perdant d'abord**.

    « Sans repasser par la file » se mesure ici : aucun appel à ``/matchmaking``, aucune invitation,
    et la partie est déjà démarrée (sa mise en place est faite) quand la réponse arrive.
    """
    emails, ids = await _trois_comptes(api_client, db_session)
    game, deck_a, deck_b = await _partie_jouee(
        db_session, ids["a"], ids["b"], jusqu_a_la_fin=True
    )
    assert game.status == "terminee"
    assert game.vainqueur_user_id is not None, "cette partie se gagne (pas d'égalité attendue)"
    perdant = next(u for u in (ids["a"], ids["b"]) if u != game.vainqueur_user_id)

    csrf = await _login(api_client, emails["a"])
    r = await api_client.post(
        f"/games/{game.id}/revanche", headers={CSRF_HEADER_NAME: csrf}
    )
    assert r.status_code == 201, r.text
    corps = r.json()
    assert corps["deja_creee"] is False
    nouvelle_id = uuid.UUID(corps["game_id"])
    assert nouvelle_id != game.id

    nouvelle = await db_session.get(Game, nouvelle_id)
    assert nouvelle is not None and nouvelle.status == "en_cours"
    assert nouvelle.current_numero > 0, "la revanche est déjà démarrée (mise en place jouée)"

    sieges = list(
        (
            await db_session.execute(
                select(GamePlayer)
                .where(GamePlayer.game_id == nouvelle_id)
                .order_by(GamePlayer.seat)
            )
        )
        .scalars()
        .all()
    )
    assert {s.user_id for s in sieges} == {ids["a"], ids["b"]}, "mêmes joueurs"
    assert {s.deck_id for s in sieges} == {deck_a, deck_b}, "mêmes decks"
    assert sieges[0].user_id == perdant, "le perdant commence (siège 0)"


async def test_deux_demandes_de_revanche_menent_a_la_meme_partie(api_client, db_session):
    """Les deux joueurs cliquent « Revanche » : ils arrivent sur le **même** plateau, pas deux.

    Sans cette idempotence, le second recevrait un conflit (« vous êtes déjà en partie ») alors
    qu'il demande exactement la partie que le premier vient de créer. La réponse passe alors de
    201 à 200, et le dit (``deja_creee``).
    """
    emails, ids = await _trois_comptes(api_client, db_session)
    game, _a, _b = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=True)

    csrf_a = await _login(api_client, emails["a"])
    premier = await api_client.post(
        f"/games/{game.id}/revanche", headers={CSRF_HEADER_NAME: csrf_a}
    )
    assert premier.status_code == 201, premier.text

    csrf_b = await _login(api_client, emails["b"])
    second = await api_client.post(
        f"/games/{game.id}/revanche", headers={CSRF_HEADER_NAME: csrf_b}
    )
    assert second.status_code == 200, second.text
    assert second.json()["deja_creee"] is True
    assert second.json()["game_id"] == premier.json()["game_id"]


async def test_revanche_refusee_sur_une_partie_en_cours(api_client, db_session):
    """On ne demande pas de revanche d'une partie qu'on n'a pas finie : 409."""
    emails, ids = await _trois_comptes(api_client, db_session)
    game, _a, _b = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=False)
    csrf = await _login(api_client, emails["a"])
    r = await api_client.post(f"/games/{game.id}/revanche", headers={CSRF_HEADER_NAME: csrf})
    assert r.status_code == 409, r.text


async def test_revanche_refusee_quand_un_deck_n_existe_plus(api_client, db_session):
    """Un siège sans deck arrête la revanche en le disant (422), jamais en silence.

    ``game_players.deck_id`` est ``ON DELETE SET NULL`` : supprimer un deck laisse un siège sans
    deck. On reproduit cet **état** directement (c'est lui que le code doit savoir refuser ; le
    ``SET NULL`` lui-même est une propriété du schéma, pas de ce module). Sans ce contrôle, la
    revanche partirait sur un ``None`` et finirait en trace de pile — ou, pire, sur un deck choisi
    à la place du joueur.
    """
    emails, ids = await _trois_comptes(api_client, db_session)
    game, _deck_a, _deck_b = await _partie_jouee(
        db_session, ids["a"], ids["b"], jusqu_a_la_fin=True
    )
    siege = (
        await db_session.execute(
            select(GamePlayer).where(
                GamePlayer.game_id == game.id, GamePlayer.user_id == ids["a"]
            )
        )
    ).scalar_one()
    siege.deck_id = None
    await db_session.flush()

    csrf = await _login(api_client, emails["a"])
    r = await api_client.post(f"/games/{game.id}/revanche", headers={CSRF_HEADER_NAME: csrf})
    assert r.status_code == 422, r.text
    assert "deck" in r.text.lower(), "le refus doit nommer ce qui manque"


async def test_revanche_refusee_quand_une_carte_a_ete_vendue(api_client, db_session):
    """Une carte vendue entre les deux parties fait refuser la revanche, **en la nommant**.

    C'est le dernier contrôle de possession, rejoué pour les deux joueurs : on ne relance pas une
    partie sur un deck que son propriétaire ne possède plus (D9 — jamais approximé, jamais une
    partie fantôme). Le refus porte la liste des cartes refusées, pas un « deck invalide ».
    """
    emails, ids = await _trois_comptes(api_client, db_session)
    game, deck_a, _deck_b = await _partie_jouee(
        db_session, ids["a"], ids["b"], jusqu_a_la_fin=True
    )
    # « Vendre » : retirer de la collection les exemplaires d'une carte du deck (le deck reste).
    cartes_du_deck = [
        cid
        for (cid,) in (
            await db_session.execute(select(DeckCard.card_id).where(DeckCard.deck_id == deck_a))
        ).all()
    ]
    await db_session.execute(
        CollectionItem.__table__.delete().where(
            (CollectionItem.user_id == ids["a"]) & (CollectionItem.card_id.in_(cartes_du_deck))
        )
    )
    await db_session.flush()

    csrf = await _login(api_client, emails["a"])
    r = await api_client.post(f"/games/{game.id}/revanche", headers={CSRF_HEADER_NAME: csrf})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["refus"], "le refus doit nommer les cartes, pas seulement dire « non »"


async def test_revanche_d_une_partie_d_autrui_repond_404(api_client, db_session):
    """Accès croisé en écriture : l'intrus reçoit 404, et aucune partie n'est créée."""
    emails, ids = await _trois_comptes(api_client, db_session)
    game, _a, _b = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=True)
    avant = len(
        (await db_session.execute(select(Game.id).where(Game.status == "en_cours"))).all()
    )

    csrf = await _login(api_client, emails["c"])
    r = await api_client.post(f"/games/{game.id}/revanche", headers={CSRF_HEADER_NAME: csrf})
    assert r.status_code == 404, r.text
    apres = len(
        (await db_session.execute(select(Game.id).where(Game.status == "en_cours"))).all()
    )
    assert apres == avant, "un refus ne crée aucune partie"


async def test_revanche_exige_le_jeton_csrf(api_client, db_session):
    """Route d'écriture : sans en-tête CSRF, elle est refusée (comme toutes les autres)."""
    emails, ids = await _trois_comptes(api_client, db_session)
    game, _a, _b = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=True)
    await _login(api_client, emails["a"])
    r = await api_client.post(f"/games/{game.id}/revanche")
    assert r.status_code in (401, 403), r.text


@pytest.mark.parametrize("route", ["recapitulatif"])
async def test_recapitulatif_d_une_partie_inexistante_repond_404(api_client, db_session, route):
    """Un identifiant inventé répond 404, pas 500 : l'écran y voit une page inexistante."""
    emails, _ids = await _trois_comptes(api_client, db_session)
    await _login(api_client, emails["a"])
    r = await api_client.get(f"/games/{uuid.uuid4()}/{route}")
    assert r.status_code == 404, r.text
