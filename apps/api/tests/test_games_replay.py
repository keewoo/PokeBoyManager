"""Replay d'une partie finie (`/games/{id}/replay`) — lot `j-replay`.

Ces tests portent les trois critères d'acceptation du lot, et chacun est mesuré sur une partie
**réellement jouée** par l'API (pas un journal fabriqué à la main) :

1. **« Le replay reproduit exactement les états successifs (empreintes comparées) »** — on joue une
   partie complète jusqu'à la victoire, puis on redemande son replay et on compare, rang par rang,
   l'empreinte servie à celle du journal en base. Le contrôle de fond (le replay recalcule et
   refuse une divergence) est du côté du moteur, pur : `apps/game/tests/test_replay_etapes.py`.
2. **« Aucune information cachée n'est servie avant la fin de la partie »** — le replay d'une
   partie en cours répond 409 et ne porte aucun rang. Et comme un 409 ne prouve pas l'absence de
   fuite ailleurs dans la réponse, on vérifie aussi, sur le replay d'une partie **finie**, que la
   vue d'un joueur ne contient jamais les cartes de la main adverse.
3. **« Le lien de replay n'est pas accessible à un compte non autorisé »** — l'intrus reçoit 404 ;
   il ne lui suffit pas de connaître l'URL. Un partage ouvert le lui donne, un partage fermé le
   lui retire.

Plus le cas du lot : **une partie interrompue par abandon** se rejoue comme une autre.
"""

import re
import uuid

import httpx
import pytest
from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import familles_jeu
from pbm_game.journal import empreinte
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
from pbm_api.models import Card, Deck, DeckCard, Game, GameEvent, Set, User
from pbm_api.security.csrf import CSRF_HEADER_NAME

PASSWORD = "correct horse battery staple"
GRAINE = "a1" * 32


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _register_verify_login(client: httpx.AsyncClient, email: str) -> str:
    """Inscrit, vérifie et connecte un compte ; renvoie son identifiant.

    Le **pseudo** et le droit d'accès au jeu ne se posent pas à l'inscription : ils sont écrits en
    base par :func:`_trois_comptes` (comme dans `test_invitations_routes`) — l'inscription est
    libre (D8), le droit au jeu se donne hors ligne (D11).
    """
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
    s = Set(code=f"rp-{uuid.uuid4().hex[:8]}", name="Set replay", series="Série test")
    db.add(s)
    await db.flush()
    return s


# Les trois cartes qui font une partie courte et déterministe. Reprises **à l'identique** de
# `test_games_partie_complete` : ce trio y mène déjà une partie jusqu'à la victoire par les
# récompenses, et réinventer des fixtures ici ne mesurerait que mes propres approximations.
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
    deck = Deck(user_id=user_id, name="Deck replay")
    db.add(deck)
    await db.flush()
    for card, qte in cartes:
        db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=qte))
    await db.flush()
    return deck


def _choisir(etat, jid, catalogue):
    """Stratégie minimale (reprise de `test_games_partie_complete`) : avancer vers la victoire."""
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


async def _partie_jouee(db, a_id: uuid.UUID, b_id: uuid.UUID, *, jusqu_a_la_fin: bool) -> Game:
    """Crée une partie entre deux comptes et la joue (jusqu'à la victoire, ou quelques coups).

    `jusqu_a_la_fin=False` sert aux cas « partie en cours » : on joue assez de coups pour avoir un
    journal non vide, sans clore la partie.
    """
    s = await _set(db)
    deck_a = await _deck(db, a_id, [(await _pikachu(db, s), 6), (await _energie(db, s), 14)])
    deck_b = await _deck(db, b_id, [(await _cible(db, s), 20)])
    game = await creer_partie(
        db, joueur_a=(a_id, deck_a.id), joueur_b=(b_id, deck_b.id), graine_hex=GRAINE
    )
    await demarrer_partie(db, game)

    user_par_jid = {joueur_id_de(a_id): a_id, joueur_id_de(b_id): b_id}
    plafond = 600 if jusqu_a_la_fin else 6
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


async def _empreintes_du_journal(db, game_id: uuid.UUID) -> list[str]:
    """Les empreintes du journal en base, dans l'ordre des coups — la référence à comparer."""
    rows = await db.execute(
        select(GameEvent.empreinte).where(GameEvent.game_id == game_id).order_by(GameEvent.numero)
    )
    return [e for (e,) in rows.all()]


async def _trois_comptes(api_client, db_session):
    """Trois comptes invités (D11) : les deux joueurs A et B, et l'intrus C."""
    emails = {k: _email(k) for k in ("a", "b", "c")}
    ids: dict[str, uuid.UUID] = {}
    pseudos: dict[str, str] = {}
    for k, email in emails.items():
        pseudos[k] = f"{k}-{uuid.uuid4().hex[:6]}"
        ids[k] = uuid.UUID(await _register_verify_login(api_client, email))
    for k, uid in ids.items():
        u = await db_session.get(User, uid)
        u.pseudo = pseudos[k]
        u.game_access = True
    await db_session.flush()
    return emails, ids, pseudos


# --- Critère 1 : le replay reproduit exactement les états successifs ---------


async def test_replay_reproduit_les_empreintes_de_la_partie_jouee(api_client, db_session):
    """Chaque rang du replay porte l'empreinte du coup correspondant **du journal en base**.

    La partie est jouée pour de vrai par l'API, jusqu'à la victoire ; le replay est ensuite
    demandé par HTTP, comme le ferait l'écran. Les deux suites doivent coïncider coup pour coup —
    c'est le critère d'acceptation central du lot.
    """
    emails, ids, _pseudos = await _trois_comptes(api_client, db_session)
    game = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=True)
    assert game.status == "terminee", f"la partie devait se terminer (statut : {game.status})"
    attendu = await _empreintes_du_journal(db_session, game.id)

    await _login(api_client, emails["a"])
    # On enchaîne les pages jusqu'à `complet` : aucune troncature muette, et on mesure sur la
    # partie entière, pas sur sa première page.
    rangs: list[dict] = []
    depuis = 0
    while True:
        r = await api_client.get(
            f"/games/{game.id}/replay", params={"vue": "moi", "depuis": depuis, "limite": 50}
        )
        assert r.status_code == 200, r.text
        page = r.json()
        rangs.extend(page["etapes"])
        if page["complet"]:
            break
        depuis = page["depuis"] + len(page["etapes"])

    assert page["total"] == len(attendu), "le total annoncé doit être le nombre de coups joués"
    # Un coup = un rang, plus le rang 0 (l'état d'avant le premier coup).
    assert [e["rang"] for e in rangs] == list(range(len(attendu) + 1))
    assert rangs[0]["coup"] is None, "aucun coup ne mène à l'état initial"
    assert [e["coup"]["empreinte"] for e in rangs[1:]] == attendu, "empreintes rang par rang"
    assert [e["coup"]["numero"] for e in rangs[1:]] == list(range(len(attendu)))

    # Le dernier rang montre bien la partie finie, avec son vainqueur.
    jid_a = joueur_id_de(ids["a"])
    assert rangs[-1]["vues"][jid_a]["terminee"] is True
    assert rangs[-1]["vues"][jid_a]["vainqueur"] == jid_a
    # …et les rangs d'avant ne la montrent pas finie (un replay ne réécrit pas l'histoire).
    assert not any(e["vues"][jid_a]["terminee"] for e in rangs[:-1])


async def test_replay_vue_complete_donne_les_deux_vues_de_joueur(api_client, db_session):
    """`vue=complete` sert les deux vues de joueur — et rien d'autre (aucune sortie non projetée).

    Chaque vue reste celle d'un joueur : on vérifie qu'elle porte bien son propre destinataire
    (`pour`), ce qui est la preuve qu'elle est passée par la projection du moteur.
    """
    emails, ids, _pseudos = await _trois_comptes(api_client, db_session)
    game = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=True)
    jid_a, jid_b = joueur_id_de(ids["a"]), joueur_id_de(ids["b"])

    await _login(api_client, emails["a"])
    r = await api_client.get(f"/games/{game.id}/replay", params={"vue": "complete"})
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["vue"] == "complete"
    for etape in page["etapes"]:
        assert set(etape["vues"]) == {jid_a, jid_b}
        assert etape["vues"][jid_a]["pour"] == jid_a
        assert etape["vues"][jid_b]["pour"] == jid_b


# --- Critère 2 : aucune information cachée avant la fin ----------------------


async def test_replay_d_une_partie_en_cours_est_refuse_sans_rien_servir(api_client, db_session):
    """Une partie **en cours** n'a pas de replay : 409, et aucun rang dans la réponse.

    C'est le risque nommé du lot — « servir le journal complet d'une partie en cours sous prétexte
    de replay ». On vérifie les deux vues : ni l'une ni l'autre n'ouvre la porte.
    """
    emails, ids, _pseudos = await _trois_comptes(api_client, db_session)
    game = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=False)
    assert game.status == "en_cours"
    assert game.current_numero > 0, "la partie doit avoir un journal non vide pour que ça prouve"

    await _login(api_client, emails["a"])
    for vue in ("moi", "complete"):
        r = await api_client.get(f"/games/{game.id}/replay", params={"vue": vue})
        assert r.status_code == 409, (vue, r.text)
        assert "etapes" not in r.json(), f"la réponse 409 ne doit porter aucun rang ({vue})"


async def test_le_replay_ne_montre_pas_la_main_adverse(api_client, db_session):
    """La vue d'un joueur, dans le replay, ne porte jamais les cartes de la main adverse.

    Un 409 sur une partie en cours ne suffit pas : il faut aussi que ce qu'on sert d'une partie
    finie reste **projeté**. La main de l'adversaire n'apparaît qu'en nombre, comme en jeu.
    """
    emails, ids, _pseudos = await _trois_comptes(api_client, db_session)
    game = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=True)
    jid_a, jid_b = joueur_id_de(ids["a"]), joueur_id_de(ids["b"])

    await _login(api_client, emails["a"])
    r = await api_client.get(f"/games/{game.id}/replay", params={"vue": "moi"})
    assert r.status_code == 200, r.text
    page = r.json()
    assert set(page["etapes"][0]["vues"]) == {jid_a}, "vue=moi ne sert qu'un destinataire"

    for etape in page["etapes"]:
        vue = etape["vues"][jid_a]
        adverse = next(j for j in vue["joueurs"] if j["id"] == jid_b)
        # La main adverse est un nombre, jamais une liste de cartes (comme en jeu).
        assert "main" not in adverse, "la main adverse ne doit jamais être servie"
        assert isinstance(adverse["main_nombre"], int)
        moi = next(j for j in vue["joueurs"] if j["id"] == jid_a)
        # Et personne ne reçoit l'ordre de sa propre pioche.
        assert "pioche" not in moi and isinstance(moi["pioche_nombre"], int)


# --- Critère 3 : le lien n'est pas accessible à un compte non autorisé -------


async def test_acces_croise_puis_partage_ouvert_puis_ferme(api_client, db_session):
    """L'intrus reçoit 404 ; un partage le lui ouvre ; le fermer le lui retire.

    C'est le critère « le lien de replay n'est pas accessible à un compte non autorisé » : C
    connaît l'URL exacte du début à la fin du test — ce qui change, c'est uniquement son **droit**.
    """
    emails, ids, pseudos = await _trois_comptes(api_client, db_session)
    game = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=True)
    url = f"/games/{game.id}/replay"

    # 1. C connaît l'URL mais n'a aucun droit : 404, pas 403 (pas de fuite d'existence).
    await _login(api_client, emails["c"])
    assert (await api_client.get(url)).status_code == 404
    # Il ne gère pas non plus les partages de cette partie.
    assert (await api_client.get(f"{url}/partages")).status_code == 404

    # 2. Le joueur A ouvre le replay à C.
    csrf_a = await _login(api_client, emails["a"])
    r = await api_client.post(
        f"{url}/partages", json={"pseudo": pseudos["c"]}, headers={CSRF_HEADER_NAME: csrf_a}
    )
    assert r.status_code == 201, r.text
    assert r.json()["user_id"] == str(ids["c"])
    assert r.json()["partage_par_user_id"] == str(ids["a"])
    # Idempotent : rouvrir ne duplique rien.
    r2 = await api_client.post(
        f"{url}/partages", json={"pseudo": pseudos["c"]}, headers={CSRF_HEADER_NAME: csrf_a}
    )
    assert r2.status_code == 201, r2.text
    liste = await api_client.get(f"{url}/partages")
    assert liste.status_code == 200
    assert [p["user_id"] for p in liste.json()] == [str(ids["c"])]

    # 3. C voit maintenant le replay — en vue complète (il n'a pas de siège, donc pas de « moi »).
    await _login(api_client, emails["c"])
    assert (await api_client.get(url, params={"vue": "moi"})).status_code == 422
    r_c = await api_client.get(url, params={"vue": "complete"})
    assert r_c.status_code == 200, r_c.text
    assert r_c.json()["etapes"], "le spectateur autorisé doit recevoir des rangs"
    # Mais il n'administre toujours pas les partages : regarder n'est pas administrer.
    assert (await api_client.get(f"{url}/partages")).status_code == 404

    # 4. B (l'autre joueur) ferme le partage : le droit se reprend aussi simplement.
    csrf_b = await _login(api_client, emails["b"])
    r_del = await api_client.delete(
        f"{url}/partages/{ids['c']}", headers={CSRF_HEADER_NAME: csrf_b}
    )
    assert r_del.status_code == 204, r_del.text
    # Fermer deux fois ne prétend pas avoir fermé quelque chose.
    r_del2 = await api_client.delete(
        f"{url}/partages/{ids['c']}", headers={CSRF_HEADER_NAME: csrf_b}
    )
    assert r_del2.status_code == 404

    # 5. C est revenu à la case départ, avec la même URL.
    await _login(api_client, emails["c"])
    assert (await api_client.get(url, params={"vue": "complete"})).status_code == 404


async def test_partage_refuse_un_compte_non_invite_et_un_joueur_de_la_partie(
    api_client, db_session
):
    """Un compte ordinaire (sans droit au jeu) est introuvable ; l'autre joueur, refusé en 422."""
    emails, ids, pseudos = await _trois_comptes(api_client, db_session)
    game = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=True)
    url = f"/games/{game.id}/replay/partages"

    # Un compte ordinaire : inscrit, vérifié, avec un pseudo, mais sans droit au jeu (D11).
    pseudo_ordinaire = f"ord-{uuid.uuid4().hex[:6]}"
    ord_id = uuid.UUID(await _register_verify_login(api_client, _email("ord")))
    (await db_session.get(User, ord_id)).pseudo = pseudo_ordinaire
    await db_session.flush()

    csrf_a = await _login(api_client, emails["a"])
    r = await api_client.post(
        url, json={"pseudo": pseudo_ordinaire}, headers={CSRF_HEADER_NAME: csrf_a}
    )
    assert r.status_code == 404, r.text

    # L'autre joueur a déjà le droit : le « partager » serait un droit en double.
    r_b = await api_client.post(
        url, json={"pseudo": pseudos["b"]}, headers={CSRF_HEADER_NAME: csrf_a}
    )
    assert r_b.status_code == 422, r_b.text


# --- Le cas du lot : une partie interrompue par abandon ----------------------


async def test_replay_d_une_partie_interrompue_par_abandon(api_client, db_session):
    """Une partie close par **abandon** se rejoue, dernier rang compris (R-14.3).

    Cas explicitement demandé par le lot : la trace d'une partie qui s'arrête en cours de route
    vaut celle d'une partie menée à son terme — c'est souvent celle-là qu'on veut relire.
    """
    emails, ids, _pseudos = await _trois_comptes(api_client, db_session)
    game = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=False)
    assert game.status == "en_cours"

    csrf_b = await _login(api_client, emails["b"])
    r_ab = await api_client.post(
        f"/games/{game.id}/abandon", headers={CSRF_HEADER_NAME: csrf_b}
    )
    assert r_ab.status_code == 200, r_ab.text
    game = await db_session.get(Game, game.id)
    await db_session.refresh(game)
    assert game.status == "terminee" and game.raison_fin == "abandon"

    attendu = await _empreintes_du_journal(db_session, game.id)
    r = await api_client.get(f"/games/{game.id}/replay", params={"vue": "moi"})
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["complet"] is True
    rangs = page["etapes"]
    assert [e["coup"]["empreinte"] for e in rangs[1:]] == attendu
    assert rangs[-1]["coup"]["type"] == "abandonner"

    # C'est **B** qui est connecté (il vient d'abandonner) : `vue=moi` est donc la sienne. Il voit
    # la partie close et son adversaire A vainqueur — on relit sa propre défaite, c'est le cas
    # d'usage du lot (« comprendre un désaccord »).
    jid_a, jid_b = joueur_id_de(ids["a"]), joueur_id_de(ids["b"])
    assert set(rangs[-1]["vues"]) == {jid_b}, "vue=moi sert le joueur de la session, lui seul"
    assert rangs[-1]["vues"][jid_b]["terminee"] is True
    assert rangs[-1]["vues"][jid_b]["vainqueur"] == jid_a

    # L'état servi au dernier rang est bien celui du journal : on recalcule son empreinte depuis
    # la base et on la retrouve. Le replay ne recopie pas une valeur, il l'atteint.
    etat_final, _rng = await reprendre_partie(db_session, game)
    assert empreinte(etat_final) == attendu[-1]


# --- Pagination : elle dit toujours ce qu'elle n'a pas servi -----------------


async def test_pagination_annonce_son_total_et_refuse_une_page_inexistante(
    api_client, db_session
):
    """Une page partielle le dit (`complet: false`) ; une page hors bornes est refusée (422)."""
    emails, ids, _pseudos = await _trois_comptes(api_client, db_session)
    game = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=True)
    total = game.current_numero
    assert total > 2, "la partie doit être assez longue pour se paginer"

    await _login(api_client, emails["a"])
    r = await api_client.get(f"/games/{game.id}/replay", params={"limite": 2, "depuis": 0})
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["total"] == total
    assert len(page["etapes"]) == 2
    assert page["complet"] is False, "une page partielle doit le dire, jamais le taire"

    # Une page qui commence après le dernier rang n'existe pas : on le dit (422) plutôt que de
    # rendre une page vide qui ressemblerait à « la partie finit ici ».
    r_hors = await api_client.get(f"/games/{game.id}/replay", params={"depuis": total + 1})
    assert r_hors.status_code == 422, r_hors.text


@pytest.mark.parametrize("vue", ["", "tout", "spectateur"])
async def test_vue_inconnue_est_refusee_jamais_repliee(api_client, db_session, vue: str):
    """Une vue hors du vocabulaire est refusée (422), pas repliée sur un défaut permissif."""
    emails, ids, _pseudos = await _trois_comptes(api_client, db_session)
    game = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=True)
    await _login(api_client, emails["a"])
    r = await api_client.get(f"/games/{game.id}/replay", params={"vue": vue})
    assert r.status_code == 422, r.text


async def test_replay_sans_droit_au_jeu_est_introuvable(api_client, db_session):
    """Sans droit au jeu (D11), aucun replay : 404 — le jeu n'existe pas pour ce compte."""
    emails, ids, _pseudos = await _trois_comptes(api_client, db_session)
    game = await _partie_jouee(db_session, ids["a"], ids["b"], jusqu_a_la_fin=True)

    # On retire son droit d'accès au jeu au joueur A : même participant, il ne voit plus rien.
    u = await db_session.get(User, ids["a"])
    u.game_access = False
    await db_session.flush()

    await _login(api_client, emails["a"])
    assert (await api_client.get(f"/games/{game.id}/replay")).status_code == 404
