"""Les effets de carte **branchés dans le service**, prouvés par une partie réelle — lot
``j-effets-cablage-service``.

Les lots d'effets (Objets, Supporters, talents, Outils, Stades, attaques à effet) avaient écrit le
moteur et laissé le **branchement côté service** « à un lot ultérieur » : ``CatalogueJeu`` sans
effets, ``card_scripts`` jamais lue pour fabriquer des définitions, familles manquantes, décisions
jamais répondues par l'API. Ce test est la preuve que ce lot a fermé le trou : une partie jouée par
les **routes HTTP** et diffusée sur le **WebSocket** résout, par le chemin réel, une attaque à
effet, un Objet, un Supporter, un talent, un Outil et un Stade — avec une **fenêtre de décision**
ouverte et répondue — sans jamais fuiter une carte cachée (R-autorité des vues). La CI fait foi.

Deux contrôles complémentaires :

* ``test_deck_a_effets_passe_ou_refuse_selon_les_scripts`` — critère D9 : un deck à effets passe la
  construction **dès que** les scripts sont au registre (Objet/Supporter/attaque) ou couverts par le
  moteur (Outil/Stade/talent), et est **refusé** sinon, en nommant la carte.
* ``test_partie_a_effets_par_http_et_ws`` — la partie réelle de bout en bout.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

import httpx
from pbm_game.actions import actions_legales
from pbm_game.actions.familles_jeu import familles_jeu
from pbm_game.demandes.moteur import EVT_DEMANDE_REPONDUE
from pbm_game.journal.modele import (
    EVT_OBJET_JOUE,
    EVT_OUTIL_ATTACHE,
    EVT_STADE_JOUE,
    EVT_SUPPORTER_JOUE,
    EVT_TALENT_ACTIVE,
)

from pbm_api.config import settings
from pbm_api.games.catalogue_jeu import construire_catalogue_jeu
from pbm_api.games.construction import joueur_id_de
from pbm_api.games.entry import DeckInjouable, verifier_deck
from pbm_api.games.service import creer_partie, demarrer_partie, reprendre_partie
from pbm_api.games.temps_reel import HUB
from pbm_api.jeu.scripts.depot import enregistrer_script
from pbm_api.models import Card, Deck, DeckCard, Game, Set, User
from pbm_api.models.card_scripts import SCRIPT_STATUT_SCRIPTE

PASSWORD = "correct horse battery staple"
UID_A = uuid.UUID("aaaaaaaa-0000-4000-8000-0000000000e1")
UID_B = uuid.UUID("bbbbbbbb-0000-4000-8000-0000000000e2")
_GRAINE = "pbm-effets-cablage-0001".ljust(32, "-").encode().hex()

# Textes d'effet (FR) et leurs scripts DSL **écrits à la main**, fidèles au texte (D9).
TXT_GUST = "Changez un des Pokémon de Banc de votre adversaire par son Pokémon Actif."
DSL_GUST = {
    "version": 1,
    "effets": [
        {
            "op": "choisir",
            "cible": {"zone": "banc", "proprietaire": "adversaire", "nombre": 1},
            "alors": [{"op": "changer_actif"}],
        }
    ],
}
TXT_SUPP = "Piochez 3 cartes."
DSL_SUPP = {"version": 1, "effets": [{"op": "piocher", "nombre": 3}]}
TXT_ATTAQUE = "Piochez une carte."
DSL_ATTAQUE = {"version": 1, "effets": [{"op": "piocher", "nombre": 1}]}

# Référence réelle du talent activé écrit à la main (Radiant Greninja « Cartes Cachées »), couvert
# par ``pbm_api.jeu.couverture_jeu`` — elle rend le talent jouable sans ligne card_scripts.
REF_GRENINJA = "swsh12-46"
TXT_TALENT = "Une fois pendant votre tour, défaussez une Énergie de votre main : piochez 2 cartes."
REF_STADE = "sv08-180"  # Stade en Liesse — couvert par le moteur (registre_stades)
REF_OUTIL = "B2-148"  # Metal Core Barrier — couvert par le moteur (registre_outils)


# --- Fabriques de base ------------------------------------------------------------------------


async def _creer_compte(db, client: httpx.AsyncClient, uid: uuid.UUID) -> str:
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
    s = Set(code=f"eff-{uuid.uuid4().hex[:8]}", name="Set effets", series="Série test")
    db.add(s)
    await db.flush()
    return s


async def _carte(db, set_row, **kw) -> Card:
    kw.setdefault("number", str(uuid.uuid4().int % 100000))
    c = Card(set_id=set_row.id, **kw)
    db.add(c)
    await db.flush()
    return c


async def _attaquant_metal(db, s, tcgdex_id: str) -> Card:
    """Un Pokémon de base Metal, 150 PV, avec une attaque **à effet** (Piochez une carte)."""
    return await _carte(
        db, s, tcgdex_id=tcgdex_id, name="Métalosse", supertype="Pokémon",
        energy_type="metal", element_type="metal", hp=150, stage="Base", retreat_cost=1,
        prize_marker="ordinaire",
        attacks=[{"name": "Frappe", "cost": ["metal"], "damage": "30", "effect": TXT_ATTAQUE}],
    )


async def _greninja(db, s) -> Card:
    """Radiant Greninja : base 70 PV, **talent activé** « Cartes Cachées » (ref réelle couverte) et
    une **attaque à effet** (Éclaboussure : 20 dégâts puis « Piochez une carte », scriptée)."""
    return await _carte(
        db, s, tcgdex_id=REF_GRENINJA, name="Amphinobi Radieux", supertype="Pokémon",
        energy_type="water", element_type="water", hp=70, stage="Base", retreat_cost=1,
        prize_marker="ordinaire",
        attacks=[
            {"name": "Éclaboussure", "cost": ["incolore"], "damage": "20",
             "effect": TXT_ATTAQUE}
        ],
        abilities=[{"name": "Cartes Cachées", "effect": TXT_TALENT}],
    )


async def _bob_basic(db, s, tcgdex_id: str) -> Card:
    return await _carte(
        db, s, tcgdex_id=tcgdex_id, name="Ronflex", supertype="Pokémon",
        energy_type="incolore", element_type="incolore", hp=130, stage="Base", retreat_cost=2,
        prize_marker="ordinaire", attacks=[],
    )


async def _energie_metal(db, s) -> Card:
    return await _carte(
        db, s, name="Énergie Métal", supertype="Énergie", energy_type="Normal",
        element_type="metal",
    )


async def _objet(db, s) -> Card:
    return await _carte(
        db, s, tcgdex_id=f"obj-{uuid.uuid4().hex[:6]}", name="Pokémon Catcher",
        supertype="Dresseur",
        trainer_type="Objet", effect=TXT_GUST,
    )


async def _supporter(db, s) -> Card:
    return await _carte(
        db, s, tcgdex_id=f"sup-{uuid.uuid4().hex[:6]}", name="Nabil", supertype="Dresseur",
        trainer_type="Supporter", effect=TXT_SUPP,
    )


async def _stade(db, s) -> Card:
    return await _carte(
        db, s, tcgdex_id=REF_STADE, name="Stade en Liesse", supertype="Dresseur",
        trainer_type="Stade", effect="Chaque Pokémon de base (des deux joueurs) a +30 PV.",
    )


async def _outil(db, s) -> Card:
    return await _carte(
        db, s, tcgdex_id=REF_OUTIL, name="Metal Core Barrier", supertype="Dresseur",
        trainer_type="Outil",
        effect="Le Pokémon Metal qui porte cet Outil subit 50 dégâts de moins.",
    )


async def _deck(db, user_id, cartes: list[tuple[Card, int]], nom="Deck effets") -> Deck:
    deck = Deck(user_id=user_id, name=nom)
    db.add(deck)
    await db.flush()
    for card, qty in cartes:
        db.add(DeckCard(deck_id=deck.id, card_id=card.id, quantity=qty))
    await db.flush()
    return deck


async def _semer_scripts(db) -> None:
    """Sème les scripts DSL écrits à la main (Objet, Supporter, attaque) au registre `card_scripts`.

    Comme le ferait ``scripts_effets.py importer`` en production : chaque texte d'effet → son
    programme, au statut `scripte` (``enregistrer_script`` pose ``validated_at`` et
    ``review_tests_ok`` — la contrainte ``ck_card_scripts_scripte_gate`` est satisfaite).
    """
    for texte, dsl in ((TXT_GUST, DSL_GUST), (TXT_SUPP, DSL_SUPP), (TXT_ATTAQUE, DSL_ATTAQUE)):
        await enregistrer_script(
            db, source_text=texte, statut=SCRIPT_STATUT_SCRIPTE, dsl_version=1, script=dsl,
            author="j-effets-cablage-service", tests=["cablage"],
        )


# --- Critère D9 : construction du deck -------------------------------------------------------


async def test_deck_a_effets_passe_ou_refuse_selon_les_scripts(api_client, db_session):
    """Un deck à effets passe la construction dès que ses scripts sont là, est refusé sinon (D9)."""
    s = await _set(db_session)
    user = User(
        id=uuid.uuid4(), email=f"{uuid.uuid4()}@ex.com", password_hash="x", last_name="T",
        birth_date=datetime(2000, 1, 1).date(), terms_version="t",
        terms_accepted_at=datetime(2000, 1, 1), email_verified_at=datetime(2020, 1, 1),
        game_access=True,
    )
    db_session.add(user)
    await db_session.flush()

    metal = await _attaquant_metal(db_session, s, "mtl-gate")
    objet = await _objet(db_session, s)
    outil = await _outil(db_session, s)
    stade = await _stade(db_session, s)
    greninja = await _greninja(db_session, s)
    energie = await _energie_metal(db_session, s)
    deck = await _deck(
        db_session, user.id,
        [(metal, 2), (greninja, 1), (objet, 1), (outil, 1), (stade, 1), (energie, 4)],
    )

    # Sans aucun script : l'Objet (DSL) et l'attaque à effet du Métalosse sont refusés ; l'Outil, le
    # Stade et le talent de Greninja sont couverts par le moteur (aucun script dû).
    try:
        await verifier_deck(db_session, user.id, deck.id)
        raise AssertionError("deck accepté sans script d'Objet/attaque — la porte D9 n'a pas mordu")
    except DeckInjouable as exc:
        noms = " ".join(nom for nom, _ in exc.refus)
        assert "Pokémon Catcher" in noms, f"l'Objet non scripté devrait être nommé : {exc.refus}"
        assert "Metal Core Barrier" not in noms, "l'Outil est couvert par le moteur, pas à refuser"
        assert "Stade en Liesse" not in noms, "le Stade est couvert par le moteur, pas à refuser"

    # Scripts semés : le deck passe (attaque + Objet scriptés ; Outil/Stade/talent couverts).
    await _semer_scripts(db_session)
    await verifier_deck(db_session, user.id, deck.id)  # ne lève plus


# --- Critère central : la partie réelle ------------------------------------------------------


def _vider(abonne) -> list[dict]:
    messages: list[dict] = []
    while True:
        try:
            messages.append(abonne.file.get_nowait())
        except asyncio.QueueEmpty:
            break
    return messages


def _caches_pour(etat, jid: str) -> set[str]:
    caches: set[str] = set()
    for j in etat.joueurs:
        caches |= {c.instance_id for c in j.pioche}
        caches |= {c.instance_id for c in j.recompenses}
        if j.id != jid:
            caches |= {c.instance_id for c in j.main}
    return caches


def _chaines(obj) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, str):
        out.add(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            out |= _chaines(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _chaines(v)
    return out


def _sans_fuite(vue, etat, jid, contexte):
    fuite = _caches_pour(etat, jid) & _chaines(vue)
    assert not fuite, f"Fuite ({contexte}) pour {jid} : {sorted(fuite)}"


async def test_partie_a_effets_par_http_et_ws(api_client, db_session):
    """Une partie jouée par HTTP + WS résout attaque-à-effet, Objet, Supporter, talent, Outil, Stade
    avec une fenêtre de décision ouverte et répondue — sans fuite."""
    await _semer_scripts(db_session)
    token_a = await _creer_compte(db_session, api_client, UID_A)
    token_b = await _creer_compte(db_session, api_client, UID_B)
    cookie_domain = next(
        c.domain for c in api_client.cookies.jar if c.name == settings.session_cookie_name
    )

    def _devenir(token: str) -> None:
        api_client.cookies.set(settings.session_cookie_name, token, domain=cookie_domain)

    s = await _set(db_session)
    greninja = await _greninja(db_session, s)
    objet = await _objet(db_session, s)
    supporter = await _supporter(db_session, s)
    stade = await _stade(db_session, s)
    outil = await _outil(db_session, s)
    energie = await _energie_metal(db_session, s)
    bob1 = await _bob_basic(db_session, s, "bob-1")

    # Deck d'alice : beaucoup de Greninja (Actif attaquant + talent + porteur d'Outil) pour qu'il
    # soit à coup sûr dans la main d'ouverture, et plusieurs exemplaires de chaque effet pour que,
    # sur quelques tours, chacun soit en main — des énergies pour payer attaque et talent.
    deck_a = await _deck(
        db_session, UID_A,
        [(greninja, 6), (objet, 3), (supporter, 3), (stade, 4), (outil, 3), (energie, 10)],
        nom="Deck alice",
    )
    # Bob : des Ronflex sans attaque — il ne met jamais K.O. (la partie ne finit pas sous nous).
    deck_b = await _deck(db_session, UID_B, [(bob1, 20)], nom="Deck bob")

    game = await creer_partie(
        db_session, joueur_a=(UID_A, deck_a.id), joueur_b=(UID_B, deck_b.id), graine_hex=_GRAINE
    )
    await demarrer_partie(db_session, game)

    jid_a, jid_b = joueur_id_de(UID_A), joueur_id_de(UID_B)
    token_par_jid = {jid_a: token_a, jid_b: token_b}
    user_par_jid = {jid_a: UID_A, jid_b: UID_B}
    abonnes = {UID_A: HUB.souscrire(game.id, UID_A), UID_B: HUB.souscrire(game.id, UID_B)}

    requis = {"attaque_effet", "objet", "supporter", "talent", "outil", "stade", "decision"}
    prouves: set[str] = set()

    async def _poster(jid: str, type_: str, params: dict, numero: int):
        _devenir(token_par_jid[jid])
        r = await api_client.post(
            f"/games/{game.id}/actions",
            json={"type": type_, "params": params, "numero_attendu": numero},
        )
        return r

    try:
        for _ in range(400):
            game = await db_session.get(Game, game.id)
            if game.status != "en_cours":
                break
            etat, _rng = await reprendre_partie(db_session, game)
            if requis <= prouves:
                break

            # Demande de décision en attente : le destinataire répond (fenêtre ouverte+répondue).
            if etat.resolution is not None:
                dem = etat.resolution.demande
                jid = dem.destinataire
                choix = list(dem.options[: max(1, dem.nombre if hasattr(dem, "nombre") else 1)])
                r = await _poster(jid, "repondre_demande", {"choix": choix}, game.current_numero)
                assert r.status_code == 200, f"repondre_demande : {r.status_code} {r.text}"
                prouves.add("decision")
                if any(e["type"] == EVT_DEMANDE_REPONDUE for e in r.json()["evenements"]):
                    prouves.add("decision_evt")
                continue

            if etat.mise_en_place is not None:
                idx = next(i for i, p in enumerate(etat.mise_en_place.placements) if p is None)
                acteur = etat.joueurs[idx].id
            else:
                acteur = etat.tour.joueur_actif
            catalogue = await construire_catalogue_jeu(db_session, etat)
            legales = actions_legales(etat, acteur, familles=familles_jeu(catalogue))
            par_type: dict[str, list] = {}
            for c in legales:
                par_type.setdefault(c.action.type, []).append(c)

            action = _prochain_coup(etat, acteur, jid_a, par_type, prouves)
            assert action is not None, (
                f"aucun coup pour {acteur} (phase {etat.tour.phase}, prouvés {sorted(prouves)})"
            )
            numero = game.current_numero
            r = await _poster(acteur, action.type, action.params, numero)
            assert r.status_code == 200, (
                f"coup {action.type} #{numero} : {r.status_code} {r.text}"
            )

            etat_apres, _ = await reprendre_partie(db_session, await db_session.get(Game, game.id))
            _sans_fuite(r.json()["vue"], etat_apres, acteur, f"HTTP {action.type}")
            # Diffusion aux deux joueurs, sans fuite.
            for user_id, ab in abonnes.items():
                for msg in _vider(ab):
                    jid_dest = next(j for j, u in user_par_jid.items() if u == user_id)
                    _sans_fuite(msg["vue"], etat_apres, jid_dest, f"WS {action.type}")
            _noter_preuves(r.json()["evenements"], prouves)

        manquants = requis - prouves
        assert not manquants, (
            f"effets non prouvés par l'API : {sorted(manquants)} (prouvés {sorted(prouves)})"
        )
    finally:
        for ab in abonnes.values():
            HUB.desouscrire(game.id, ab)


def _noter_preuves(evenements: list[dict], prouves: set[str]) -> None:
    types = {e["type"] for e in evenements}
    if EVT_OBJET_JOUE in types:
        prouves.add("objet")
    if EVT_SUPPORTER_JOUE in types:
        prouves.add("supporter")
    if EVT_STADE_JOUE in types:
        prouves.add("stade")
    if EVT_OUTIL_ATTACHE in types:
        prouves.add("outil")
    if EVT_TALENT_ACTIVE in types:
        prouves.add("talent")
    if EVT_DEMANDE_REPONDUE in types:
        prouves.add("decision")
    # Une attaque à effet : des dégâts ET un effet de script (ici une pioche) au même coup.
    if "degats" in types and "attaque_declaree" in types:
        prouves.add("attaque_effet")


def _prochain_coup(etat, acteur, jid_a, par_type, prouves):
    """Choisit le prochain coup : alice joue ses effets un à un ; sinon fait avancer la partie."""

    def premier(type_):
        return par_type[type_][0].action if par_type.get(type_) else None

    # Mise en place / promotion obligatoire : toujours en priorité. Greninja (seule base d'alice)
    # devient donc l'Actif — il porte l'attaque à effet, le talent et recevra l'Outil.
    if "placer_mise_en_place" in par_type:
        return par_type["placer_mise_en_place"][0].action
    if "promouvoir" in par_type:
        return premier("promouvoir")

    if acteur != jid_a:
        # Bob : avance/passe — il ne fait aucun effet (son banc, posé à la mise en place, sert de
        # cible à l'appât d'alice).
        if "avancer_phase" in par_type:
            return premier("avancer_phase")
        return par_type and next(iter(par_type.values()))[0].action or None

    joueur = next(j for j in etat.joueurs if j.id == acteur)
    # Énergie sur l'Actif (paye l'attaque et nourrit la main pour le coût du talent).
    if "attacher_energie" in par_type and joueur.actif is not None:
        actif_id = joueur.actif.cartes[0].instance_id
        for c in par_type["attacher_energie"]:
            if c.action.params.get("cible") == actif_id:
                return c.action

    # Les effets, un à un (ordre : ceux qui n'ont pas besoin de finir le tour d'abord).
    if "supporter" not in prouves and par_type.get("jouer_supporter"):
        return premier("jouer_supporter")
    if "talent" not in prouves and par_type.get("activer_talent"):
        return premier("activer_talent")
    if "stade" not in prouves and par_type.get("jouer_stade"):
        return premier("jouer_stade")
    if "outil" not in prouves and par_type.get("attacher_outil"):
        return premier("attacher_outil")
    if ("objet" not in prouves or "decision" not in prouves) and par_type.get("jouer_objet"):
        return premier("jouer_objet")
    # Attaque à effet en dernier (elle termine le tour).
    if "attaque_effet" not in prouves and par_type.get("declarer_attaque"):
        return premier("declarer_attaque")
    if "avancer_phase" in par_type:
        return premier("avancer_phase")
    return next(iter(par_type.values()))[0].action if par_type else None
