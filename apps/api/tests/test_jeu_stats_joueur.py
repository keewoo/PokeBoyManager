"""Mes parties : historique, agrégats et honnêteté sur les petits nombres — lot `j-stats-joueur`.

Les trois critères d'acceptation du lot, chacun mesuré :

1. **« Les agrégats correspondent aux parties réellement jouées »** —
   :func:`test_les_agregats_correspondent_aux_parties_jouees` confronte la sortie de la route à un
   historique écrit à la main, deck par deck et adversaire par adversaire, puis
   :func:`test_les_colonnes_du_taux_se_recomptent` vérifie que chaque taux rendu se **recompte**
   depuis ses propres colonnes (un taux qu'on ne peut pas recompter n'est pas contestable).
2. **« Un taux calculé sur moins de cinq parties est signalé comme non significatif »** — deux
   fois : :func:`test_sous_le_seuil_un_taux_est_marque_non_significatif` sur le calcul pur (aux
   deux bords du seuil, 4 et 5), et :func:`test_la_route_marque_les_taux_non_significatifs` de bout
   en bout, y compris sur une ligne de deck.
3. **« La page se charge en moins d'une seconde avec cent parties »** —
   :func:`test_cent_parties_tiennent_la_seconde` mesure les **deux** appels que la page fait
   réellement (l'historique paginé *et* les agrégats sur les cent parties), par le client HTTP.

Plus ce que le lot promet au-delà des critères : l'isolation (un compte ne voit pas les parties
d'un autre, ni par la liste ni par les agrégats), le 404 sans accès au jeu (D11), l'entraînement
présent dans l'historique mais absent des taux, une partie **purgée** qui reste listée sans lien de
replay, un deck supprimé qui garde ses parties, un filtre de résultat inconnu **refusé** en 422, et
des séries qui ne dépendent pas de l'ordre d'écriture.

Comme ``test_jeu_classement``, l'historique est écrit directement dans ``game_results`` /
``game_result_players`` plutôt qu'en jouant des parties : le contrat de ce lot porte sur **ces deux
tables**, et c'est ``test_games_fin_compte`` qui prouve déjà qu'une partie close les écrit juste.
Rejouer des parties ici mesurerait une seconde fois le lot précédent, et ne permettrait pas de
fabriquer à la demande les cas qui comptent (cent parties, un deck effacé, une partie purgée).

Ce lot n'applique **aucune règle de jeu** : il compte des résultats déjà écrits. Aucun test ne cite
donc de ``R-x.y`` — les règles de fin de partie (R-14) sont vérifiées par le moteur et par
``test_games_fin_compte``, pas ici.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from pbm_api.jeu.stats_joueur import (
    SEUIL_SIGNIFICATIVITE,
    PartieJouee,
    calculer,
    taux,
)
from pbm_api.models import Deck, Game, GameResult, GameResultPlayer, User
from pbm_api.models.fin_compte import (
    RESULTAT_DEFAITE,
    RESULTAT_EGALITE,
    RESULTAT_VICTOIRE,
)

PASSWORD = "correct horse battery staple"

#: Un instant fixe : les dates de l'historique se comparent entre elles, jamais à « maintenant ».
T0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


async def _compte_invite(client, db, label: str, *, pseudo: str, acces: bool = True) -> uuid.UUID:
    """Crée un compte vérifié, **connecte** le client dessus, et lui donne (ou non) l'accès au jeu.

    Le dernier compte créé est celui que le client HTTP porte : les tests d'isolation s'appuient
    là-dessus pour écrire l'historique d'un autre joueur **avant** de se connecter en tant que
    victime putative.
    """
    email = _email(label)
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
    jeton = re.search(r"token=(\S+)", sent[-1]["body"])
    assert jeton
    await client.post("/auth/verify-email", json={"token": jeton.group(1)})
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    user_id = uuid.UUID(login.json()["id"])

    user = await db.get(User, user_id)
    user.game_access = acces
    user.pseudo = pseudo
    await db.flush()
    return user_id


async def _deck(db, proprietaire: uuid.UUID, nom: str) -> uuid.UUID:
    """Un deck minimal, juste pour que l'historique ait un nom à afficher."""
    deck = Deck(user_id=proprietaire, name=nom)
    db.add(deck)
    await db.flush()
    return deck.id


async def _partie_persistee(db, game_id: uuid.UUID) -> None:
    """Pose la ligne ``games`` d'une partie close — ce qui rend son replay consultable.

    Les tests qui ne l'appellent pas décrivent une partie **purgée** : sa trace existe, la partie
    non. C'est le cas qui doit laisser la ligne dans l'historique **sans** lien de replay.
    """
    db.add(
        Game(
            id=game_id,
            status="terminee",
            etat_initial={},
            graine="00",
            engagement="00",
            journal_version=1,
            current_numero=1,
            current_empreinte="00",
            last_action_at=T0,
            expires_at=T0 + timedelta(days=1),
        )
    )
    await db.flush()


async def _resultat(
    db,
    joueur: uuid.UUID,
    resultat: str,
    *,
    jours: int = 0,
    deck_id: uuid.UUID | None = None,
    adversaire: uuid.UUID | None = None,
    bot: bool = False,
    entrainement: bool = False,
    comptabilisee: bool | None = None,
    duree_s: int | None = 600,
    raison_fin: str | None = "derniere_recompense",
    persistee: bool = True,
    degats: int = 0,
    coups: int = 0,
) -> uuid.UUID:
    """Pose une partie close dans l'historique (``game_results`` + ``game_result_players``).

    ``comptabilisee`` suit l'entraînement par défaut, comme la clôture réelle le fait : une partie
    d'entraînement entre dans l'historique sans compter. Rend l'identifiant de partie, pour que le
    test puisse vérifier ce que la route en dit.
    """
    compte = (not entrainement) if comptabilisee is None else comptabilisee
    game_id = uuid.uuid4()
    finie_a = T0 + timedelta(days=jours)
    if persistee:
        await _partie_persistee(db, game_id)
    db.add(
        GameResult(
            game_id=game_id,
            statut="terminee",
            raison_fin=raison_fin,
            vainqueur_user_id=joueur if resultat == RESULTAT_VICTOIRE else None,
            entrainement=entrainement,
            comptabilisee=compte,
            coups=coups,
            tours=4,
            duree_s=duree_s,
            journal_numero=coups,
            finie_a=finie_a,
        )
    )
    db.add(
        GameResultPlayer(
            game_id=game_id,
            user_id=joueur,
            seat=0,
            deck_id=deck_id,
            adversaire_user_id=adversaire,
            adversaire_bot=bot,
            resultat=resultat,
            comptabilisee=compte,
            finie_a=finie_a,
            duree_s=duree_s,
            degats_infliges=degats,
            kos_infliges=0,
            recompenses_prises=0,
            cartes_jouees=0,
            energies_attachees=0,
            coups_joues=coups,
        )
    )
    await db.flush()
    return game_id


# --- Le calcul pur : le seuil de significativité ------------------------------


def _pure(resultat: str, *, jours: int = 0, comptabilisee: bool = True) -> PartieJouee:
    """Une partie, pour le module pur — le minimum qui permette de compter."""
    return PartieJouee(
        game_id=uuid.uuid4(),
        finie_a=T0 + timedelta(days=jours),
        resultat=resultat,
        comptabilisee=comptabilisee,
        entrainement=not comptabilisee,
        deck_id=None,
        deck_nom=None,
        adversaire_user_id=None,
        adversaire_pseudo=None,
        adversaire_bot=not comptabilisee,
        duree_s=600,
        degats_infliges=0,
        kos_infliges=0,
        recompenses_prises=0,
        cartes_jouees=0,
        energies_attachees=0,
        coups_joues=0,
    )


@pytest.mark.parametrize("nombre", [0, 1, 2, 3, 4])
def test_sous_le_seuil_un_taux_est_marque_non_significatif(nombre: int) -> None:
    """**Critère 2**, au bord inférieur : jusqu'à quatre parties, le taux ne veut rien dire.

    Le pourcentage est **calculé quand même** (le masquer ressemblerait à un bug), mais marqué, et
    ``parties_manquantes`` dit combien il en faut encore — l'écran peut donc écrire la phrase utile
    plutôt qu'un avertissement générique.
    """
    mesure = taux([RESULTAT_VICTOIRE] * nombre)
    assert mesure.significatif is False
    assert mesure.parties_manquantes == SEUIL_SIGNIFICATIVITE - nombre
    # Trois victoires sur trois, c'est 100 % — et c'est précisément le chiffre flatteur que le
    # risque du lot nomme. Il sort, mais il sort marqué.
    assert mesure.pourcentage == (None if nombre == 0 else 100)


def test_a_cinq_parties_le_taux_devient_significatif() -> None:
    """**Critère 2**, au bord supérieur : le seuil est atteint *à* cinq, pas après.

    Tester les deux bords (4 et 5) est ce qui attrape une inégalité stricte posée au mauvais sens —
    l'erreur la plus facile à écrire et la plus invisible à la lecture.
    """
    mesure = taux([RESULTAT_VICTOIRE] * 3 + [RESULTAT_DEFAITE] * 2)
    assert (mesure.significatif, mesure.parties_manquantes, mesure.pourcentage) == (True, 0, 60)


def test_aucune_partie_ne_donne_pas_zero_pour_cent() -> None:
    """Sans partie, le taux est **absent**, pas nul : 0 % se lirait « il perd toujours » (D9)."""
    assert taux([]).pourcentage is None


def test_un_resultat_inconnu_n_est_pas_compte_comme_une_defaite() -> None:
    """Un résultat hors vocabulaire n'entre dans aucune colonne — jamais transformé en défaite.

    Le compter en défaite inventerait une mauvaise nouvelle. Ici il disparaît des colonnes, et le
    total des trois colonnes (``parties``) le signale en ne collant pas à la liste fournie.
    """
    mesure = taux([RESULTAT_VICTOIRE, "abracadabra"])
    assert (mesure.parties, mesure.victoires, mesure.defaites, mesure.egalites) == (1, 1, 0, 0)


def test_l_egalite_interrompt_la_serie() -> None:
    """Une égalité remet la série à zéro : la prolonger serait flatteur, donc faux.

    Même règle que `j-fin-effets-compte`, et c'est voulu : deux définitions de « série » sur le même
    historique finiraient par s'afficher côte à côte en se contredisant.
    """
    stats = calculer(
        [
            _pure(RESULTAT_VICTOIRE, jours=1),
            _pure(RESULTAT_VICTOIRE, jours=2),
            _pure(RESULTAT_EGALITE, jours=3),
            _pure(RESULTAT_VICTOIRE, jours=4),
        ]
    )
    assert (stats.totaux.serie_en_cours, stats.totaux.meilleure_serie) == (1, 2)


def test_la_serie_ne_depend_pas_de_l_ordre_d_ecriture() -> None:
    """Les mêmes parties, écrites dans deux ordres opposés, donnent la même série.

    C'est ce qui rend le calcul juste quand le balayage de reprise enregistre une partie ancienne
    **après** une récente (`docs/jeu/FIN-COMPTE.md`) : un compteur incrémenté au fil de l'eau
    l'aurait cassé sans bruit.
    """
    parties = [
        _pure(RESULTAT_DEFAITE, jours=1),
        _pure(RESULTAT_VICTOIRE, jours=2),
        _pure(RESULTAT_VICTOIRE, jours=3),
    ]
    endroit = calculer(parties).totaux
    envers = calculer(list(reversed(parties))).totaux
    assert (endroit.serie_en_cours, endroit.meilleure_serie) == (2, 2)
    assert (envers.serie_en_cours, envers.meilleure_serie) == (2, 2)


def test_l_entrainement_ne_touche_aucun_taux() -> None:
    """Quatre victoires contre le bot ne font pas un palmarès — mais le temps joué se voit.

    Les deux moitiés comptent : l'entraînement n'entre pas dans les taux (sinon le palmarès serait
    gonflable à volonté), et il n'est pas perdu non plus (quelqu'un qui s'est entraîné a le droit
    de le voir).
    """
    stats = calculer(
        [_pure(RESULTAT_VICTOIRE, jours=j, comptabilisee=False) for j in range(4)]
        + [_pure(RESULTAT_DEFAITE, jours=5)]
    )
    assert (stats.totaux.taux.parties, stats.totaux.taux.victoires) == (1, 0)
    assert stats.totaux.parties_entrainement == 4
    assert stats.totaux.temps_jeu_entrainement_s == 4 * 600


def test_une_duree_absente_ne_tire_pas_la_moyenne_vers_le_bas() -> None:
    """Une partie sans durée connue est **exclue** de la moyenne, pas comptée pour zéro."""
    avec = _pure(RESULTAT_VICTOIRE, jours=1)
    sans = PartieJouee(**{**avec.__dict__, "duree_s": None, "game_id": uuid.uuid4()})
    stats = calculer([avec, sans])
    assert stats.par_deck[0].duree_moyenne_s == 600


# --- La route : agrégats, isolation, honnêteté --------------------------------


async def test_les_agregats_correspondent_aux_parties_jouees(api_client, db_session):
    """**Critère 1.** Un historique écrit à la main, et la route qui le recompte exactement.

    Six parties comptées sur deux decks et deux adversaires, plus une d'entraînement : chaque
    nombre rendu est confronté à ce que le test a posé, jamais à lui-même.
    """
    rival = await _compte_invite(api_client, db_session, "st-rival", pseudo="aymeric")
    moi = await _compte_invite(api_client, db_session, "st-moi", pseudo="jf")
    feu = await _deck(db_session, moi, "Brasier")
    eau = await _deck(db_session, moi, "Marée")

    # Brasier : 3 victoires et 1 défaite contre aymeric. Marée : 1 défaite, 1 égalité.
    for jour in (1, 2, 3):
        await _resultat(
            db_session, moi, RESULTAT_VICTOIRE, jours=jour, deck_id=feu, adversaire=rival
        )
    await _resultat(db_session, moi, RESULTAT_DEFAITE, jours=4, deck_id=feu, adversaire=rival)
    await _resultat(db_session, moi, RESULTAT_DEFAITE, jours=5, deck_id=eau, adversaire=rival)
    await _resultat(db_session, moi, RESULTAT_EGALITE, jours=6, deck_id=eau, adversaire=rival)
    # Et une partie d'entraînement, qui ne doit toucher aucun taux.
    await _resultat(
        db_session, moi, RESULTAT_VICTOIRE, jours=7, deck_id=feu, bot=True, entrainement=True
    )

    corps = (await api_client.get("/jeu/mes-statistiques")).json()
    totaux = corps["totaux"]["taux"]
    assert (totaux["parties"], totaux["victoires"], totaux["defaites"], totaux["egalites"]) == (
        6,
        3,
        2,
        1,
    )
    assert totaux["pourcentage"] == 50
    assert corps["totaux"]["parties_entrainement"] == 1

    # Par deck, du plus joué au moins joué, avec le bilan de chacun.
    par_deck = {d["deck_nom"]: d for d in corps["par_deck"]}
    assert [d["deck_nom"] for d in corps["par_deck"]] == ["Brasier", "Marée"]
    assert par_deck["Brasier"]["taux"]["victoires"] == 3
    assert par_deck["Brasier"]["taux"]["pourcentage"] == 75
    assert par_deck["Marée"]["taux"]["pourcentage"] == 0
    assert par_deck["Marée"]["taux"]["egalites"] == 1

    # « Ce deck gagne surtout contre… » : le croisement deck × adversaire.
    assert [a["pseudo"] for a in par_deck["Brasier"]["adversaires"]] == ["aymeric"]
    assert par_deck["Brasier"]["adversaires"][0]["taux"]["victoires"] == 3

    # Et par adversaire, toutes decks confondus.
    assert [(a["pseudo"], a["taux"]["parties"]) for a in corps["par_adversaire"]] == [
        ("aymeric", 6)
    ]


async def test_les_colonnes_du_taux_se_recomptent(api_client, db_session):
    """Chaque taux rendu est **recomptable** depuis ses propres colonnes.

    Un pourcentage qu'on ne peut pas refaire à la main n'est pas contestable — et un classement
    qu'on ne peut pas contester, on finit par ne plus le croire (même exigence que le classement
    privé).
    """
    moi = await _compte_invite(api_client, db_session, "st-recompte", pseudo="jf")
    deck = await _deck(db_session, moi, "Brasier")
    for jour in range(5):
        resultat = RESULTAT_VICTOIRE if jour % 2 == 0 else RESULTAT_DEFAITE
        await _resultat(db_session, moi, resultat, jours=jour, deck_id=deck)

    corps = (await api_client.get("/jeu/mes-statistiques")).json()
    for mesure in [corps["totaux"]["taux"], *[d["taux"] for d in corps["par_deck"]]]:
        assert mesure["parties"] == (
            mesure["victoires"] + mesure["defaites"] + mesure["egalites"]
        )
        assert mesure["pourcentage"] == round(mesure["victoires"] * 100 / mesure["parties"])


async def test_la_route_marque_les_taux_non_significatifs(api_client, db_session):
    """**Critère 2** de bout en bout : trois victoires sur trois sortent marquées.

    Le seuil est rendu avec les chiffres (``seuil_significativite``) pour que l'écran écrive la
    règle au lieu de la recoder : la changer un jour ne demandera pas de retoucher le front.
    """
    moi = await _compte_invite(api_client, db_session, "st-seuil", pseudo="jf")
    deck = await _deck(db_session, moi, "Brasier")
    for jour in range(3):
        await _resultat(db_session, moi, RESULTAT_VICTOIRE, jours=jour, deck_id=deck)

    corps = (await api_client.get("/jeu/mes-statistiques")).json()
    assert corps["seuil_significativite"] == SEUIL_SIGNIFICATIVITE
    assert corps["totaux"]["taux"] == {
        "parties": 3,
        "victoires": 3,
        "defaites": 0,
        "egalites": 0,
        "pourcentage": 100,
        "significatif": False,
        "parties_manquantes": 2,
    }
    # La ligne du deck porte la même garde : c'est là qu'un joueur décide quoi jouer.
    assert corps["par_deck"][0]["taux"]["significatif"] is False


async def test_l_historique_liste_mes_parties_de_la_plus_recente(api_client, db_session):
    """La liste, son total, et le lien de replay — dans l'ordre où on la lit."""
    rival = await _compte_invite(api_client, db_session, "st-h-rival", pseudo="aymeric")
    moi = await _compte_invite(api_client, db_session, "st-h-moi", pseudo="jf")
    deck = await _deck(db_session, moi, "Brasier")
    recente = await _resultat(
        db_session, moi, RESULTAT_VICTOIRE, jours=9, deck_id=deck, adversaire=rival
    )
    await _resultat(db_session, moi, RESULTAT_DEFAITE, jours=1, deck_id=deck, adversaire=rival)

    corps = (await api_client.get("/jeu/mes-parties")).json()
    assert corps["total"] == 2
    premiere = corps["parties"][0]
    assert premiere["game_id"] == str(recente)
    assert (premiere["resultat"], premiere["deck_nom"], premiere["adversaire_pseudo"]) == (
        RESULTAT_VICTOIRE,
        "Brasier",
        "aymeric",
    )
    assert premiere["replay_disponible"] is True
    assert premiere["raison_fin"] == "derniere_recompense"


async def test_une_partie_purgee_reste_listee_sans_replay(api_client, db_session):
    """La purge efface la partie, pas sa trace : la ligne reste, le lien de replay disparaît.

    C'est le piège que `j-fin-effets-compte` a payé d'avance en refusant toute clé étrangère vers
    ``games``. L'écran doit donc pouvoir ne **pas** proposer un lien qui répondrait 404 — ce qui
    serait lu comme une panne.
    """
    moi = await _compte_invite(api_client, db_session, "st-purge", pseudo="jf")
    await _resultat(db_session, moi, RESULTAT_VICTOIRE, jours=1, persistee=False)

    ligne = (await api_client.get("/jeu/mes-parties")).json()["parties"][0]
    assert ligne["replay_disponible"] is False
    assert ligne["resultat"] == RESULTAT_VICTOIRE


async def test_un_deck_supprime_garde_ses_parties(api_client, db_session):
    """Supprimer un deck ne doit pas effacer les parties qu'il a jouées.

    Ses lignes se regroupent sous un deck sans identifiant ni nom : l'écran les nomme
    « deck supprimé » plutôt que de les fondre dans un autre deck, ce qui fausserait son taux.
    """
    moi = await _compte_invite(api_client, db_session, "st-deck-mort", pseudo="jf")
    await _resultat(db_session, moi, RESULTAT_VICTOIRE, jours=1, deck_id=None)

    corps = (await api_client.get("/jeu/mes-statistiques")).json()
    assert [(d["deck_id"], d["deck_nom"]) for d in corps["par_deck"]] == [(None, None)]
    assert corps["totaux"]["taux"]["parties"] == 1


async def test_je_ne_vois_pas_les_parties_d_un_autre_compte(api_client, db_session):
    """Isolation : l'historique et les agrégats sont ceux de la session, et de personne d'autre.

    L'autre compte a un historique garni *et* un pseudo : si un filtre ``user_id`` manquait, ses
    parties apparaîtraient ici. Le test d'accès croisé exigé par le dépôt, dans la forme que ce lot
    permet — il n'existe aucune route « les parties de X », donc rien d'autre à tenter.
    """
    autre = await _compte_invite(api_client, db_session, "st-autre", pseudo="autre")
    for jour in range(6):
        await _resultat(db_session, autre, RESULTAT_VICTOIRE, jours=jour)

    moi = await _compte_invite(api_client, db_session, "st-vierge", pseudo="jf")
    await _resultat(db_session, moi, RESULTAT_DEFAITE, jours=1)

    historique = (await api_client.get("/jeu/mes-parties")).json()
    assert historique["total"] == 1
    assert historique["parties"][0]["resultat"] == RESULTAT_DEFAITE

    stats = (await api_client.get("/jeu/mes-statistiques")).json()
    assert (stats["totaux"]["taux"]["parties"], stats["totaux"]["taux"]["victoires"]) == (1, 0)
    assert moi != autre


async def test_un_compte_sans_acces_au_jeu_recoit_404(api_client, db_session):
    """D11 : le jeu est réservé aux comptes invités, et un 404 ne confirme rien (pas un 403)."""
    await _compte_invite(api_client, db_session, "st-dehors", pseudo="dehors", acces=False)
    assert (await api_client.get("/jeu/mes-parties")).status_code == 404
    assert (await api_client.get("/jeu/mes-statistiques")).status_code == 404


async def test_un_filtre_de_resultat_inconnu_est_refuse(api_client, db_session):
    """Un vocabulaire inconnu est **refusé**, pas servi comme une liste vide.

    Une liste vide se lirait « tu n'as jamais gagné » : c'est un repli silencieux, interdit par le
    dépôt. Le 422 nomme le vocabulaire attendu.
    """
    await _compte_invite(api_client, db_session, "st-filtre", pseudo="jf")
    reponse = await api_client.get("/jeu/mes-parties?resultat=gagn%C3%A9")
    assert reponse.status_code == 422, reponse.text
    assert "victoire" in reponse.text


async def test_les_filtres_restreignent_la_liste(api_client, db_session):
    """Les quatre filtres, chacun sur le même historique — dont l'entraînement, visible par défaut.

    Par défaut la liste montre **tout**, entraînement compris : le masquer d'office ferait croire à
    un historique amputé (« où sont mes parties contre le bot ? »).
    """
    rival = await _compte_invite(api_client, db_session, "st-f-rival", pseudo="aymeric")
    moi = await _compte_invite(api_client, db_session, "st-f-moi", pseudo="jf")
    feu = await _deck(db_session, moi, "Brasier")
    eau = await _deck(db_session, moi, "Marée")
    await _resultat(db_session, moi, RESULTAT_VICTOIRE, jours=1, deck_id=feu, adversaire=rival)
    await _resultat(db_session, moi, RESULTAT_DEFAITE, jours=2, deck_id=eau, adversaire=rival)
    await _resultat(
        db_session, moi, RESULTAT_VICTOIRE, jours=3, deck_id=feu, bot=True, entrainement=True
    )

    async def total(requete: str) -> int:
        reponse = await api_client.get(f"/jeu/mes-parties{requete}")
        assert reponse.status_code == 200, reponse.text
        return reponse.json()["total"]

    assert await total("") == 3
    assert await total("?entrainement=false") == 2
    assert await total("?entrainement=true") == 1
    assert await total(f"?deck_id={feu}") == 2
    assert await total(f"?resultat={RESULTAT_DEFAITE}") == 1
    assert await total(f"?adversaire_user_id={rival}") == 2


async def test_la_pagination_dit_ce_qu_elle_n_affiche_pas(api_client, db_session):
    """Une page, son total, et un deuxième appel qui ne redonne pas les mêmes parties."""
    moi = await _compte_invite(api_client, db_session, "st-page", pseudo="jf")
    for jour in range(7):
        await _resultat(db_session, moi, RESULTAT_VICTOIRE, jours=jour)

    page1 = (await api_client.get("/jeu/mes-parties?limite=5")).json()
    page2 = (await api_client.get("/jeu/mes-parties?limite=5&offset=5")).json()
    assert (page1["total"], len(page1["parties"])) == (7, 5)
    assert len(page2["parties"]) == 2
    assert not {p["game_id"] for p in page1["parties"]} & {p["game_id"] for p in page2["parties"]}
    # Un plafond dépassé est refusé, pas tronqué en silence.
    assert (await api_client.get("/jeu/mes-parties?limite=500")).status_code == 422


async def test_les_agregats_ne_sont_pas_pagines(api_client, db_session):
    """Les agrégats portent sur **tout** l'historique, pas sur la page affichée.

    Un taux calculé sur la page changerait en cliquant « suivant » — le joueur verrait son deck
    s'améliorer en tournant les pages.
    """
    moi = await _compte_invite(api_client, db_session, "st-nopage", pseudo="jf")
    for jour in range(30):
        await _resultat(db_session, moi, RESULTAT_VICTOIRE, jours=jour)

    page = (await api_client.get("/jeu/mes-parties?limite=5")).json()
    stats = (await api_client.get("/jeu/mes-statistiques")).json()
    assert len(page["parties"]) == 5
    assert stats["totaux"]["taux"]["parties"] == 30


async def test_le_filtre_par_deck_donne_le_meme_chiffre_que_le_tableau(api_client, db_session):
    """La fiche d'un deck et le tableau général ne peuvent pas se contredire.

    C'est pourquoi la fiche de deck appelle la **même** route avec ``deck_id`` au lieu d'avoir son
    propre calcul : deux calculs du même taux finiraient par divergir, et c'est précisément ce
    qu'on reproche à un chiffre.
    """
    moi = await _compte_invite(api_client, db_session, "st-croise", pseudo="jf")
    feu = await _deck(db_session, moi, "Brasier")
    eau = await _deck(db_session, moi, "Marée")
    for jour in range(5):
        await _resultat(db_session, moi, RESULTAT_VICTOIRE, jours=jour, deck_id=feu)
    await _resultat(db_session, moi, RESULTAT_DEFAITE, jours=6, deck_id=eau)

    general = (await api_client.get("/jeu/mes-statistiques")).json()
    ligne_feu = next(d for d in general["par_deck"] if d["deck_id"] == str(feu))
    cible = (await api_client.get(f"/jeu/mes-statistiques?deck_id={feu}")).json()
    assert cible["totaux"]["taux"] == ligne_feu["taux"]
    assert cible["par_deck"][0]["deck_id"] == str(feu)


async def test_cent_parties_tiennent_la_seconde(api_client, db_session):
    """**Critère 3.** Cent parties, et les deux appels que la page fait vraiment.

    On mesure l'historique paginé **et** les agrégats (non paginés, donc le calcul porte bien sur
    les cent parties) : ne chronométrer que la liste aurait laissé passer un agrégat quadratique.
    Le budget d'une seconde est celui du critère ; la mesure réelle est inscrite au compte rendu.
    """
    rival = await _compte_invite(api_client, db_session, "st-cent-rival", pseudo="aymeric")
    moi = await _compte_invite(api_client, db_session, "st-cent", pseudo="jf")
    decks = [await _deck(db_session, moi, f"Deck {i}") for i in range(4)]
    for tour in range(100):
        await _resultat(
            db_session,
            moi,
            [RESULTAT_VICTOIRE, RESULTAT_DEFAITE, RESULTAT_EGALITE][tour % 3],
            jours=tour,
            deck_id=decks[tour % 4],
            adversaire=rival,
            degats=tour,
            coups=tour % 7,
        )

    debut = time.perf_counter()
    historique = await api_client.get("/jeu/mes-parties?limite=100")
    stats = await api_client.get("/jeu/mes-statistiques")
    ecoule = time.perf_counter() - debut

    assert historique.status_code == 200, historique.text
    assert stats.status_code == 200, stats.text
    assert len(historique.json()["parties"]) == 100
    assert stats.json()["totaux"]["taux"]["parties"] == 100
    assert len(stats.json()["par_deck"]) == 4
    assert ecoule < 1.0, f"cent parties ont demandé {ecoule:.3f} s (budget : 1 s)"
