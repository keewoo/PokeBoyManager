"""Partie complète jouée par les **routes HTTP et le canal temps réel** — lot
``fix-projection-evenements``.

Pourquoi ce test existe, alors que ``test_games_partie_complete`` joue déjà une partie entière : ce
dernier passe par ``appliquer_action`` / ``reprendre_partie`` (la couche service), **jamais** par le
point de sortie ``pbm_game.sortie.projeter`` / ``projeter_resultat``. C'est exactement l'angle mort
qui a laissé la livraison des coups du joueur échouer en silence (``docs/LIVRAISON.md``) :
sept événements de la mise en place et du timer n'avaient pas de projecteur, donc
``POST /games/{id}/actions`` répondait **500** et le WebSocket ne diffusait rien — mais la CI était
verte, car aucun test ne franchissait la projection.

Ici, chaque coup — de ``placer_mise_en_place`` (le coup même qui faisait 500) jusqu'à la victoire
par les récompenses — est joué par la **vraie route HTTP**, qui appelle ``projeter_resultat`` et
diffuse sur le ``HUB`` du lot ``j-temps-reel``. À chaque coup on vérifie :

* la réponse HTTP est **200** (plus de 500 de projection) ;
* le coup est **diffusé aux deux joueurs** (chacun reçoit un message projeté pour lui) ;
* **aucune fuite** dans la vue de chacun : aucun ``instance_id`` d'une zone cachée au destinataire
  (les deux pioches, les deux lots de récompenses, la main adverse) n'apparaît dans sa vue — même
  parcours que le test de non-fuite de ``j-modele-etat`` / ``test_sortie_projection`` ;
* la main d'un **mulligan** révélée à l'adversaire (R-4.4) lui livre les ``ref`` mais **pas** les
  ``instance_id`` (cartes qui retournent dans la pioche cachée).

La CI fait foi.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

import httpx
from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import familles_jeu
from pbm_game.journal import RAISON_DERNIERE_RECOMPENSE
from sqlalchemy import select

from pbm_api.config import settings
from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.service import creer_partie, demarrer_partie, reprendre_partie
from pbm_api.games.temps_reel import HUB
from pbm_api.models import Card, Deck, DeckCard, Game, Set, User
from pbm_api.models.games import GameEvent

PASSWORD = "correct horse battery staple"
# Identifiants **fixes** : ``joueur_id_de`` dérive le flux de mélange de l'``user_id``, donc des
# UUID stables rendent la mise en place (et son mulligan) reproductible — sinon un UUID aléatoire
# par exécution rendrait le mulligan intermittent, et le test flakerait en CI.
UID_A = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
UID_B = uuid.UUID("bbbbbbbb-0000-4000-8000-000000000002")
# Graine choisie pour que, avec ces UUID et le deck d'alice (1 base sur 20), la mise en place
# produise un mulligan (R-4.4) — le scénario exact de la livraison bloquée. Vérifiée par le test
# (assert « mulligan » dans le coup #0) : un changement de moteur qui la ferait dévier casse ici.
_GRAINE = "pbm-fixproj-seed-000".ljust(32, "-").encode().hex()


async def _creer_compte(db, client: httpx.AsyncClient, uid: uuid.UUID) -> str:
    """Crée un compte **vérifié** au droit de jeu avec un UUID fixe, puis le connecte.

    On crée l'utilisateur directement (UUID maîtrisé, impossible via ``/auth/register`` qui en tire
    un au hasard), avec un vrai hachage de mot de passe pour que ``/auth/login`` pose la session.
    Renvoie le jeton de session HTTP du compte.
    """

    from pbm_api.security.passwords import hash_password

    db.add(
        User(
            id=uid,
            email=f"{uid}@example.com",
            password_hash=hash_password(PASSWORD),
            email_verified_at=datetime(2020, 1, 1),
            last_name="Dresseur",
            birth_date=datetime(2000, 1, 1).date(),
            terms_version="test",
            terms_accepted_at=datetime(2000, 1, 1),
            game_access=True,
        )
    )
    await db.flush()
    login = await client.post(
        "/auth/login", json={"email": f"{uid}@example.com", "password": PASSWORD}
    )
    assert login.status_code == 200, login.text
    return client.cookies.get(settings.session_cookie_name)


async def _set(db) -> Set:
    s = Set(code=f"hw-{uuid.uuid4().hex[:8]}", name="Set HTTP/WS", series="Série test")
    db.add(s)
    await db.flush()
    return s


async def _pokemon(db, set_row, nom: str, *, prize_marker: str, attaque: bool) -> Card:
    """Un Pokémon de base de 60 PV ; attaquant (« Charge », 60 dégâts) ou cible sans attaque."""
    c = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 100000),
        name=nom,
        supertype="Pokémon",
        energy_type="electrique" if attaque else "incolore",
        element_type="electrique" if attaque else "incolore",
        hp=60,
        stage="Base",
        retreat_cost=0,
        prize_marker=prize_marker,
        attacks=[{"name": "Charge", "cost": ["electrique"], "damage": "60", "effect": ""}]
        if attaque
        else [],
    )
    db.add(c)
    await db.flush()
    return c


async def _energie(db, set_row) -> Card:
    c = Card(
        set_id=set_row.id,
        number=str(uuid.uuid4().int % 100000),
        name="Énergie Électrique",
        supertype="Énergie",
        energy_type="Normal",
        element_type="electrique",
    )
    db.add(c)
    await db.flush()
    return c


async def _deck(db, user, cartes: list[tuple[Card, int]]) -> Deck:
    deck = Deck(user_id=user.id, name="Deck HTTP/WS")
    db.add(deck)
    await db.flush()
    for card, qty in cartes:
        db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=qty))
    await db.flush()
    return deck


def _choisir(etat, jid, catalogue):
    """Stratégie minimale : promouvoir, placer, attaquer, charger l'Actif, sinon avancer/passer."""
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


def _instance_ids_caches_pour(etat, joueur_id: str) -> set[str]:
    """Les ``instance_id`` des zones **cachées** au joueur ``joueur_id`` : les deux pioches, les
    deux lots de récompenses (même les siens, face cachée — il n'a que des jetons opaques) et la
    main de l'adversaire. Aucun de ces identifiants ne doit apparaître dans sa vue projetée.

    On compare par ``instance_id`` (unique) et non par ``ref`` : les decks de ce test répètent les
    mêmes cartes (20 cibles identiques), donc un ``ref`` caché coïncide légitimement avec un ``ref``
    public — seul l'``instance_id`` distingue une vraie fuite d'un doublon de type.
    """
    caches: set[str] = set()
    for j in etat.joueurs:
        caches |= {c.instance_id for c in j.pioche}
        caches |= {c.instance_id for c in j.recompenses}
        if j.id != joueur_id:
            caches |= {c.instance_id for c in j.main}
    return caches


def _vider(abonne) -> list[dict]:
    """Retire et renvoie tous les messages en attente dans la file d'un abonné (sans bloquer)."""
    messages: list[dict] = []
    while True:
        try:
            messages.append(abonne.file.get_nowait())
        except asyncio.QueueEmpty:
            break
    return messages


async def test_partie_complete_par_http_et_ws_sans_fuite_ni_500(api_client, db_session):
    # Deux comptes connectés (UUID fixes) ; on garde le jeton de session de chacun pour alterner les
    # coups sans relogin (le relogin est limité en débit, et une partie fait des dizaines de coups).
    a_id, b_id = UID_A, UID_B
    token_a = await _creer_compte(db_session, api_client, a_id)
    token_b = await _creer_compte(db_session, api_client, b_id)
    assert token_a and token_b and token_a != token_b
    # httpx range le cookie de session sous un domaine canonicalisé (``testserver.local``) : pour
    # qu'une réécriture du cookie soit bien renvoyée, on la pose sous CE domaine, lu du bocal plutôt
    # que supposé. Sans ça, le ``set`` est silencieusement ignoré et tous les coups partiraient sous
    # la dernière session connectée.
    cookie_domain = next(
        c.domain for c in api_client.cookies.jar if c.name == settings.session_cookie_name
    )

    def _devenir(token: str) -> None:
        """Bascule la session HTTP du client vers le joueur porteur de ``token``."""
        api_client.cookies.set(settings.session_cookie_name, token, domain=cookie_domain)

    s = await _set(db_session)
    pika = await _pokemon(db_session, s, "Pikachu", prize_marker="ordinaire", attaque=True)
    energie = await _energie(db_session, s)
    cible = await _pokemon(db_session, s, "Duo Tag", prize_marker="tag_team", attaque=False)
    # Alice : une seule base (1 Pikachu sur 20) → avec la graine fixe, sa main d'ouverture est sans
    # base et déclenche un mulligan (R-4.4). Pikachu suffit à gagner : « Charge » met K.O. une cible
    # de 60 PV, et Bob (sans attaque) ne peut jamais le mettre K.O.
    deck_a = await _deck(db_session, await db_session.get(User, a_id), [(pika, 1), (energie, 19)])
    # Bob : 20 cibles « tag_team » (3 récompenses chacune) sans attaque — il ne riposte jamais.
    deck_b = await _deck(db_session, await db_session.get(User, b_id), [(cible, 20)])

    game = await creer_partie(
        db_session, joueur_a=(a_id, deck_a.id), joueur_b=(b_id, deck_b.id), graine_hex=_GRAINE
    )
    await demarrer_partie(db_session, game)

    jid_a, jid_b = joueur_id_de(a_id), joueur_id_de(b_id)
    user_par_jid = {jid_a: (a_id, token_a), jid_b: (b_id, token_b)}
    jid_par_user = {a_id: jid_a, b_id: jid_b}

    # Deux abonnés au canal temps réel : la route HTTP diffuse sur le HUB partagé du process.
    abonne_a = HUB.souscrire(game.id, a_id)
    abonne_b = HUB.souscrire(game.id, b_id)
    abonne_par_user = {a_id: abonne_a, b_id: abonne_b}

    premier_placement_vu = False
    try:
        for _ in range(800):
            game = await db_session.get(Game, game.id)
            if game.status != "en_cours":
                break
            etat, _rng = await reprendre_partie(db_session, game)
            catalogue = await construire_catalogue_jeu(db_session, etat)
            if etat.mise_en_place is not None:
                idx = next(i for i, p in enumerate(etat.mise_en_place.placements) if p is None)
                acteur = etat.joueurs[idx].id
            else:
                acteur = etat.tour.joueur_actif
            action = _choisir(etat, acteur, catalogue)
            assert action is not None, f"aucun coup pour {acteur} (phase {etat.tour.phase})"

            user_id, token = user_par_jid[acteur]
            _devenir(token)
            numero_attendu = game.current_numero
            reponse = await api_client.post(
                f"/games/{game.id}/actions",
                json={
                    "type": action.type,
                    "params": action.params,
                    "numero_attendu": numero_attendu,
                },
            )
            # Le cœur du correctif : le coup passe la projection (plus de 500), y compris le tout
            # premier — placer_mise_en_place — qui faisait échouer la livraison.
            assert reponse.status_code == 200, (
                f"coup {action.type} (#{numero_attendu}) : HTTP {reponse.status_code} "
                f"— {reponse.text}"
            )
            if action.type == "placer_mise_en_place":
                premier_placement_vu = True

            # État autoritaire APRÈS le coup : base du contrôle de non-fuite pour chaque vue.
            etat_apres, _ = await reprendre_partie(db_session, await db_session.get(Game, game.id))

            # La réponse HTTP est la vue de l'acteur : aucune carte cachée ne doit y figurer.
            vue_acteur = reponse.json()["vue"]
            _assert_sans_fuite(
                vue_acteur, etat_apres, acteur, contexte=f"réponse HTTP {action.type}"
            )

            # Diffusion aux DEUX joueurs : chacun reçoit un message projeté pour lui, sans fuite.
            recus = {}
            for user_id_dest, abonne in abonne_par_user.items():
                messages = _vider(abonne)
                assert len(messages) == 1, (
                    f"coup #{numero_attendu} : {len(messages)} message(s) à {user_id_dest}, "
                    "attendu exactement 1 (diffusion aux deux joueurs)."
                )
                msg = messages[0]
                assert msg["type"] == "evenement" and msg["numero"] == numero_attendu
                recus[user_id_dest] = msg
                jid_dest = jid_par_user[user_id_dest]
                _assert_sans_fuite(msg["vue"], etat_apres, jid_dest, contexte=f"WS {action.type}")
                # Défense : si un jour la main d'un mulligan était diffusée en cours de partie, elle
                # ne devrait livrer aucun instance_id à l'adversaire (R-4.4). Aujourd'hui cet
                # événement n'arrive qu'à la mise en place système (coup #0, non diffusé).
                for evt in msg["evenements"]:
                    if evt["type"] == "main_revelee" and evt["donnees"].get("joueur") != jid_dest:
                        cartes = evt["donnees"].get("cartes", [])
                        assert all("instance_id" not in c for c in cartes), (
                            f"main_revelee fuit un instance_id à l'adversaire {jid_dest} : {cartes}"
                        )

        game = await db_session.get(Game, game.id)
        assert game.status == "terminee", f"statut final : {game.status}"
        assert game.vainqueur_user_id == a_id, f"vainqueur : {game.vainqueur_user_id}"
        assert game.raison_fin == RAISON_DERNIERE_RECOMPENSE, f"raison : {game.raison_fin}"
        assert premier_placement_vu, "placer_mise_en_place jamais joué — scénario incomplet."

        # Le scénario exerce bien un **mulligan** (R-4.4) : il a lieu pendant la mise en place
        # SYSTÈME (coup #0, posé par demarrer_partie AVANT tout abonné), donc sa narration ne
        # transite pas par le chemin « coup joueur » HTTP/WS — la projection par destinataire de
        # ``main_revelee`` (refs à l'adversaire, instance_id jamais) est vérifiée au niveau moteur
        # par ``test_sortie_projection.test_main_revelee_donne_les_refs_mais_pas_les_instance_id``.
        # Ici on atteste seulement que la partie rejouée contient un mulligan (deck d'alice pauvre
        # en bases + graine fixe), pour que le scénario reste celui de la livraison bloquée.
        coup_zero = (
            await db_session.execute(
                select(GameEvent).where(GameEvent.game_id == game.id, GameEvent.numero == 0)
            )
        ).scalar_one()
        types_setup = [e["type"] for e in coup_zero.evenements]
        assert "mulligan" in types_setup and "main_revelee" in types_setup, (
            f"mise en place sans mulligan : {types_setup}. Ajuster _GRAINE ou le deck d'alice pour "
            "que le scénario de la livraison (mulligan compris) soit bien exercé."
        )

        # Reprise par le repli HTTP (même charge que la resync WebSocket), pour chaque joueur :
        # aucune carte cachée ne fuit dans la vue reconstruite, et la graine ne sort jamais.
        etat_final, _ = await reprendre_partie(db_session, await db_session.get(Game, game.id))
        for user_id_dest in (a_id, b_id):
            jid_dest = jid_par_user[user_id_dest]
            _devenir(user_par_jid[jid_dest][1])
            r_sync = await api_client.get(f"/games/{game.id}/sync", params={"depuis": 0})
            assert r_sync.status_code == 200, r_sync.text
            assert "graine" not in r_sync.text  # le secret d'aléa ne sort jamais
            _assert_sans_fuite(
                r_sync.json()["vue"], etat_final, jid_dest, contexte="resync vue finale"
            )
    finally:
        HUB.desouscrire(game.id, abonne_a)
        HUB.desouscrire(game.id, abonne_b)


def _chaines(obj) -> set[str]:
    """Toutes les chaînes **scalaires** d'une structure JSON (valeurs et clés de dict, feuilles de
    liste). On compare par égalité de valeur, pas par sous-chaîne : un ``instance_id`` comme ``:d1``
    est un préfixe de ``:d15`` et un test de sous-chaîne crierait à tort à la fuite.
    """
    trouvees: set[str] = set()
    if isinstance(obj, str):
        trouvees.add(obj)
    elif isinstance(obj, dict):
        for cle, valeur in obj.items():
            trouvees.add(cle)
            trouvees |= _chaines(valeur)
    elif isinstance(obj, list):
        for valeur in obj:
            trouvees |= _chaines(valeur)
    return trouvees


def _assert_sans_fuite(vue: dict, etat, joueur_id: str, *, contexte: str) -> None:
    """Assure qu'aucun ``instance_id`` caché à ``joueur_id`` n'apparaît dans sa ``vue`` projetée."""
    visibles = _chaines(vue)
    fuite = _instance_ids_caches_pour(etat, joueur_id) & visibles
    assert not fuite, f"Fuite ({contexte}) pour {joueur_id} : {sorted(fuite)} visible(s)."
