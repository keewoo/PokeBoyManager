"""Observabilité du jeu (lot ``j-observabilite-jeu``) — les trois critères d'acceptation.

* **une erreur de moteur déclenche une alerte**, prouvé par *injection* : on force le moteur à
  lever une exception dans une vraie partie, et on vérifie que l'incident est consigné ET que la
  règle d'alerte le classe critique (``test_injection_erreur_moteur_*``) ;
* **les métriques sont visibles sans SSH** : ``GET /jeu/metriques`` les sert à un compte ayant
  l'accès au jeu, et répond 404 à tout autre (``test_metriques_*``) ;
* **le récapitulatif hebdomadaire arrive, et son absence est un signal** : le texte est produit
  depuis le relevé, et l'absence d'envoi devient une alerte (``test_recap_hebdo_*``).

Les seuils et les motifs sont **purs** : ils se testent sans base, sans serveur de mail et sans
horloge — c'est tout l'intérêt de les avoir séparés de leur lecture.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# `tests/` n'est pas un paquet : on importe à plat, comme `test_catalog_completeness.py`.
from test_games_service import _deux_joueurs, _make_card, _make_deck, _make_user

from pbm_api.config import settings
from pbm_api.games import service as game_service
from pbm_api.games.errors import ActionRefusee, CartesNonJouables
from pbm_api.games.service import appliquer_action, creer_partie, demarrer_partie, purger
from pbm_api.models import (
    INCIDENT_ACTION_REFUSEE,
    INCIDENT_ERREUR_MOTEUR,
    INCIDENT_PARTIE_REFUSEE,
    Game,
    JeuIncident,
    User,
)
from pbm_api.observabilite.consignation import consigner_incident, definir_fabrique
from pbm_api.observabilite.metriques import relever
from pbm_api.observabilite.motifs import (
    DETAIL_MAX,
    MOTIF_SANS_REGLE,
    detail_borne,
    motif_d_erreur,
    motif_de_refus,
)
from pbm_api.observabilite.rapport import (
    sujet_alerte,
    sujet_recap_hebdo,
    texte_alerte,
    texte_recap_hebdo,
)
from pbm_api.observabilite.regles import (
    DELAI_RECAP_HEBDO_J,
    GRAVITE_CRITIQUE,
    SEUIL_REFUS_VOLUME,
    alerte_recap_manquant,
    evaluer,
    verdict,
)
from pbm_api.observabilite.releve import RAISON_DESERTION, RAISON_TEMPS_ECOULE, Releve

PASSWORD = "Mdp-observabilite-2026!"


# --- Fixtures ----------------------------------------------------------------


@pytest_asyncio.fixture
async def incidents_en_test(db_session):
    """Branche l'écriture des incidents sur la connexion du test.

    En production, :func:`consigner_incident` écrit dans une session **autonome** : c'est ce qui
    fait survivre la trace au rollback du coup refusé. Dans la suite, cette autonomie écrirait
    pour de vrai dans la base de test et s'accumulerait d'un test à l'autre. On l'oriente donc
    vers la connexion du test (même mécanique de savepoint que ``conftest.db_session``), si bien
    que les lignes disparaissent avec le rollback de fin de test — sans jamais changer le code
    de production.
    """
    connexion = await db_session.connection()

    def fabrique() -> AsyncSession:
        return AsyncSession(
            bind=connexion, join_transaction_mode="create_savepoint", expire_on_commit=False
        )

    definir_fabrique(fabrique)
    yield
    definir_fabrique(None)


async def _incidents(db, genre: str | None = None) -> list[JeuIncident]:
    """Les incidents consignés, filtrés par genre si demandé, du plus ancien au plus récent."""
    requete = select(JeuIncident).order_by(JeuIncident.created_at)
    if genre is not None:
        requete = requete.where(JeuIncident.genre == genre)
    return list((await db.execute(requete)).scalars().all())


def _releve(**kwargs) -> Releve:
    """Un relevé de test : tout à zéro sauf ce qu'on veut éprouver (fenêtre de 24 h par défaut)."""
    kwargs.setdefault("fenetre_heures", 24)
    return Releve(**kwargs)


# --- Motifs : purs, bornés, sans donnée d'utilisateur ------------------------


def test_motif_de_refus_prend_la_regle_citee():
    """Un refus du moteur cite sa règle : c'est elle qui devient le motif agrégeable (R-3.5)."""
    assert motif_de_refus("Un seul Stade en jeu à la fois (R-3.5)") == "R-3.5"
    assert motif_de_refus("Ce Pokémon ne peut pas battre en retraite (R-13.1)") == "R-13.1"


def test_motif_de_refus_sans_regle_est_nomme_pas_devine():
    """Un refus qui ne cite aucune règle n'est pas rangé au hasard : il porte son propre motif.

    Tout refus DOIT citer sa règle (``pbm_game.actions.modele.refus``) : un compteur non nul sur
    ce motif désigne donc un chemin de refus à corriger, pas un cas normal.
    """
    assert motif_de_refus("action inconnue : sortilege") == MOTIF_SANS_REGLE
    assert motif_de_refus(None) == MOTIF_SANS_REGLE
    assert motif_de_refus("") == MOTIF_SANS_REGLE


def test_motif_d_erreur_est_la_classe_jamais_le_message():
    """Le motif d'une erreur ne transporte JAMAIS le message : il porterait des données."""
    exc = KeyError("carte-secrete-xy-123")
    motif = motif_d_erreur(exc)
    assert motif == "KeyError"
    assert "carte-secrete" not in motif


def test_detail_borne_tronque_et_ne_depasse_jamais_la_colonne():
    """Un détail trop long est tronqué : une trace ne doit pas échouer sur sa propre longueur."""
    assert detail_borne(None) is None
    assert detail_borne("   ") is None
    assert detail_borne("court") == "court"
    long = "x" * (DETAIL_MAX + 200)
    borne = detail_borne(long)
    assert len(borne) == DETAIL_MAX
    assert borne.endswith("…")


# --- Règles d'alerte : pures ------------------------------------------------


def test_une_erreur_de_moteur_est_une_alerte_critique():
    """Critère du lot : une erreur de moteur est une ALERTE, sans seuil, jamais un journal."""
    alertes = evaluer(_releve(erreurs_moteur=1, coups_joues=200))
    assert [a.code for a in alertes] == ["erreur_moteur"]
    assert alertes[0].gravite == GRAVITE_CRITIQUE
    assert verdict(alertes) == "PANNE"


def test_aucune_alerte_quand_tout_va_bien():
    """Une activité normale ne réveille personne : la liste d'alertes est vide, le verdict OK."""
    releve = _releve(
        parties_en_cours=2,
        parties_creees=5,
        parties_terminees=4,
        coups_joues=400,
        refus=6,
        refus_par_motif={"R-3.5": 4, "R-13.1": 2},
        fins_par_raison={"derniere_recompense": 4},
    )
    assert evaluer(releve) == []
    assert verdict([]) == "OK"


def test_quelques_refus_sous_le_seuil_de_volume_ne_declenchent_rien():
    """À trois joueurs, deux refus sur trois coups c'est quelqu'un qui apprend, pas une panne."""
    releve = _releve(coups_joues=1, refus=2, refus_par_motif={"R-3.5": 2})
    assert releve.taux_refus > 0.5  # le taux est bien mauvais…
    assert evaluer(releve) == []  # … mais le volume ne permet rien d'en conclure


def test_rafale_de_refus_alerte_quand_volume_ET_taux_sont_depasses():
    """Le signal « bug d'interface ou client modifié » : beaucoup de refus, et en proportion."""
    releve = _releve(
        coups_joues=20,
        refus=SEUIL_REFUS_VOLUME + 10,
        refus_par_motif={f"R-{i}.1": 1 for i in range(SEUIL_REFUS_VOLUME + 10)},
    )
    codes = [a.code for a in evaluer(releve)]
    assert "rafale_refus" in codes
    assert verdict(evaluer(releve)) == "A_SURVEILLER"


def test_motif_dominant_nomme_la_regle_en_cause():
    """Quand un seul R-x.y concentre les refus, l'alerte le nomme : on sait où lire REGLES.md."""
    releve = _releve(coups_joues=500, refus=20, refus_par_motif={"R-6.2": 18, "R-3.5": 2})
    alertes = [a for a in evaluer(releve) if a.code == "motif_dominant"]
    assert len(alertes) == 1
    assert "R-6.2" in alertes[0].message


def test_parties_qui_n_aboutissent_pas_alertent():
    """« Des parties qui n'aboutissent pas » est un signal nommé du jalon J5."""
    codes = [a.code for a in evaluer(_releve(parties_en_cours=3, parties_bloquees=2))]
    assert codes == ["parties_bloquees"]


def test_releve_expose_horloges_desertions_et_motif_dominant():
    """Les dérivées du relevé : le lecteur d'une métrique ne refait aucun calcul."""
    releve = _releve(
        fins_par_raison={RAISON_TEMPS_ECOULE: 3, RAISON_DESERTION: 1},
        coups_joues=90,
        refus=10,
        refus_par_motif={"R-3.5": 7, "R-6.2": 3},
    )
    assert releve.expirations_horloge == 3
    assert releve.desertions == 1
    assert releve.motif_dominant == ("R-3.5", 7)
    assert releve.taux_refus == pytest.approx(10 / 100)
    assert releve.en_json()["expirations_horloge"] == 3


def test_releve_sans_activite_ne_divise_pas_par_zero():
    """Aucun coup soumis : le taux vaut 0, et aucune moyenne n'est inventée."""
    vide = _releve()
    assert vide.taux_refus == 0.0
    assert vide.motif_dominant is None
    assert vide.en_json()["duree_moyenne_minutes"] is None


# --- Le récapitulatif hebdomadaire et son absence ---------------------------


def test_recap_hebdo_manquant_est_une_alerte():
    """L'homme mort du dispositif : plus de récapitulatif = la sonde ne tourne plus."""
    aujourdhui = date(2026, 10, 14)
    a_jour = aujourdhui - timedelta(days=DELAI_RECAP_HEBDO_J - 1)
    en_retard = aujourdhui - timedelta(days=DELAI_RECAP_HEBDO_J)

    assert alerte_recap_manquant(a_jour, aujourdhui) is None
    alerte = alerte_recap_manquant(en_retard, aujourdhui)
    assert alerte is not None
    assert alerte.code == "recap_hebdo_manquant"
    assert en_retard.isoformat() in alerte.message


def test_recap_hebdo_jamais_envoye_est_deja_un_retard():
    """Une sonde qui n'a jamais envoyé n'est pas une sonde qui va bien."""
    alerte = alerte_recap_manquant(None, date(2026, 10, 14))
    assert alerte is not None
    assert alerte.code == "recap_hebdo_jamais_envoye"


def test_texte_recap_hebdo_porte_les_parties_et_dit_que_son_absence_est_une_panne():
    """Le récapitulatif se lit seul : les parties jouées, et pourquoi son silence compte."""
    releve = _releve(
        fenetre_heures=168,
        parties_creees=12,
        parties_terminees=11,
        fins_par_raison={"derniere_recompense": 9, RAISON_TEMPS_ECOULE: 2},
        duree_moyenne_minutes=27.5,
        coups_moyens=64.0,
        coups_joues=704,
        parties_refusees=3,
    )
    corps = texte_recap_hebdo(releve, [], instant="2026-10-14 06:00 UTC")
    assert "Parties créées              : 12" in corps
    assert "derniere_recompense : 9" in corps
    assert "Parties refusées (D9)       : 3" in corps
    assert "ABSENCE est une panne" in corps
    assert "12 partie(s) créée(s)" in sujet_recap_hebdo(releve)


def test_texte_alerte_met_ce_qui_cloche_en_tete():
    """Un e-mail d'alerte se lit sur un téléphone : la cause d'abord, le relevé ensuite."""
    releve = _releve(erreurs_moteur=2, coups_joues=30)
    alertes = evaluer(releve)
    corps = texte_alerte(releve, alertes, instant="2026-10-14 09:00 UTC")
    assert corps.index("CE QUI CLOCHE") < corps.index("RELEVÉ")
    assert "[CRITIQUE] erreur_moteur" in corps
    assert "PANNE" in sujet_alerte(alertes)


# --- Consignation et métriques, contre la vraie base ------------------------


async def test_refus_dun_coup_est_consigne_avec_son_motif(db_session, incidents_en_test):
    """Un coup refusé laisse une trace EN BASE : sans elle, le refus meurt avec la requête."""
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )

    with pytest.raises(ActionRefusee):
        await appliquer_action(
            db_session, game_id=game.id, user_id=user_a.id, type="sortilege", numero_attendu=0
        )

    incidents = await _incidents(db_session, INCIDENT_ACTION_REFUSEE)
    assert len(incidents) == 1
    assert incidents[0].game_id == game.id
    assert incidents[0].user_id == user_a.id
    assert incidents[0].type_action == "sortilege"
    assert incidents[0].detail  # la cause du moteur est gardée pour le diagnostic


async def test_refus_dun_coup_illegal_en_partie_jouable_cite_sa_regle(
    db_session, incidents_en_test
):
    """Sur une partie en mise en place, le refus vient de ``valider`` et cite son ``R-x.y``.

    C'est le cas qui rend la métrique « refus par motif » utile : le motif EST la règle, donc une
    hausse nomme la règle qui casse (R-4 — mise en place).
    """
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session, taille_deck=20)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    await demarrer_partie(db_session, game)

    with pytest.raises(ActionRefusee):
        await appliquer_action(
            db_session,
            game_id=game.id,
            user_id=user_a.id,
            type="declarer_attaque",
            params={"indice": 0},
            numero_attendu=game.current_numero,
        )

    incidents = await _incidents(db_session, INCIDENT_ACTION_REFUSEE)
    assert len(incidents) == 1
    assert incidents[0].motif.startswith("R-"), incidents[0].motif
    assert len(incidents[0].motif) <= 64


async def test_injection_erreur_moteur_consigne_un_incident_et_alerte(
    db_session, incidents_en_test, monkeypatch
):
    """**Test d'injection** : le moteur plante, et ça devient une alerte critique (critère 1).

    On force ``pbm_game.journal.appliquer`` — vu par le service — à lever une exception qui n'est
    PAS un refus de règle (``ValueError`` est déjà traitée comme un coup illégal) : c'est le profil
    d'un vrai bug de moteur. On vérifie les trois maillons de la chaîne : l'incident est écrit, le
    relevé le compte, et la règle d'alerte le classe critique.
    """
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )

    # Le décor est validé AVANT le coup : en production la partie est déjà en base quand on
    # lui applique un coup, et le `rollback` du garde n'abandonne que le coup à moitié écrit.
    # Sans ce commit, il emporterait aussi la partie créée par le test — et on mesurerait un
    # artefact de la suite, pas le comportement réel.
    await db_session.commit()

    def moteur_casse(etat, action, rng):
        raise KeyError("zone-inconnue-42")

    monkeypatch.setattr(game_service, "appliquer", moteur_casse)

    with pytest.raises(KeyError):
        await appliquer_action(
            db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=0
        )

    # 1. l'incident est écrit, et son motif ne trahit aucune donnée de la partie
    incidents = await _incidents(db_session, INCIDENT_ERREUR_MOTEUR)
    assert len(incidents) == 1
    assert incidents[0].motif == "KeyError"
    assert incidents[0].type_action == "piocher"

    # 2. le relevé le compte
    releve = await relever(db_session)
    assert releve.erreurs_moteur == 1

    # 3. et la règle d'alerte en fait une PANNE — pas une ligne de journal
    alertes = evaluer(releve)
    assert "erreur_moteur" in [a.code for a in alertes]
    assert verdict(alertes) == "PANNE"


async def test_erreur_moteur_sans_le_garde_ne_laisserait_aucune_trace(
    db_session, incidents_en_test, monkeypatch
):
    """La preuve que le garde sert : le coup n'est pas appliqué, et la partie n'avance pas.

    Avant ce lot, la même exception remontait en 500 sans trace exploitable ; ici l'état de la
    partie est intact (le serveur fait autorité) ET l'incident existe.
    """
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )

    await db_session.commit()  # cf. test précédent : le décor existe déjà en production
    # On retient l'identifiant AVANT de détacher l'instance plus bas : `expunge_all()` la coupe
    # de sa session, et lire `game.id` ensuite lèverait `DetachedInstanceError`.
    game_id = game.id

    def moteur_casse(etat, action, rng):
        raise TypeError("bug")

    monkeypatch.setattr(game_service, "appliquer", moteur_casse)
    with pytest.raises(TypeError):
        await appliquer_action(
            db_session, game_id=game_id, user_id=user_a.id, type="piocher", numero_attendu=0
        )

    # On vide la carte d'identité de la session avant de relire : après le `rollback` du garde,
    # l'instance en mémoire est périmée, et la recharger paresseusement hors du pont async de
    # SQLAlchemy lève `MissingGreenlet`. On relit donc depuis la base, pas depuis le cache.
    db_session.expunge_all()
    partie = (
        await db_session.execute(select(Game).where(Game.id == game_id))
    ).scalar_one()
    assert partie.current_numero == 0  # rien n'a été appliqué
    assert [i.motif for i in await _incidents(db_session, INCIDENT_ERREUR_MOTEUR)] == ["TypeError"]


async def test_partie_refusee_en_d9_est_comptee(db_session, incidents_en_test):
    """Une partie refusée faute de carte scriptée est le signal « couverture insuffisante ».

    Ce n'est PAS une alerte (le refus est le comportement voulu), mais c'est compté : sans ça, le
    fait qu'un joueur n'a pas pu lancer sa partie n'existe que dans son écran.
    """
    user_a = await _make_user(db_session)
    user_b = await _make_user(db_session)
    bonne = await _make_card(db_session, name="Salamèche")
    mauvaise = await _make_card(db_session, name="Carte Mystère", jouable=False)
    deck_a = await _make_deck(db_session, user_a, [(bonne, 4), (mauvaise, 2)])
    deck_b = await _make_deck(db_session, user_b, [(bonne, 6)])

    with pytest.raises(CartesNonJouables):
        await creer_partie(
            db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
        )

    incidents = await _incidents(db_session, INCIDENT_PARTIE_REFUSEE)
    assert len(incidents) == 1
    assert "Carte Mystère" in incidents[0].detail
    releve = await relever(db_session)
    assert releve.parties_refusees == 1
    # … et le jeu n'alerte pas pour autant : refuser est le comportement voulu (D9).
    assert [a.code for a in evaluer(releve)] == []


async def test_relever_compte_les_parties_leurs_fins_et_leurs_coups(db_session):
    """Le relevé lit les parties là où elles vivent déjà : statut, raison de fin, coups, durée."""
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    for n in range(2):
        await appliquer_action(
            db_session, game_id=game.id, user_id=user_a.id, type="piocher", numero_attendu=n
        )

    en_cours = await relever(db_session)
    assert en_cours.parties_en_cours == 1
    assert en_cours.parties_creees == 1
    assert en_cours.parties_terminees == 0
    assert en_cours.coups_joues >= 2
    assert en_cours.parties_bloquees == 0

    # Une partie terminée au temps doit apparaître dans `fins_par_raison` et compter comme une
    # expiration d'horloge — c'est la métrique demandée par le lot.
    game.status = "terminee"
    game.raison_fin = RAISON_TEMPS_ECOULE
    await db_session.flush()

    apres = await relever(db_session)
    assert apres.parties_en_cours == 0
    assert apres.parties_terminees == 1
    assert apres.fins_par_raison == {RAISON_TEMPS_ECOULE: 1}
    assert apres.expirations_horloge == 1
    assert apres.coups_moyens is not None


async def test_relever_voit_une_partie_qui_n_aboutit_pas(db_session):
    """Une partie en cours sans coup depuis trop longtemps est comptée comme bloquée."""
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    game.last_action_at = datetime.now(UTC) - timedelta(days=5)
    await db_session.flush()

    releve = await relever(db_session)
    assert releve.parties_bloquees == 1
    assert "parties_bloquees" in [a.code for a in evaluer(releve)]


async def test_releve_est_borne_a_sa_fenetre(db_session, incidents_en_test):
    """Un incident hors fenêtre ne compte pas : 24 h ne traînent pas le mois dernier."""
    await consigner_incident(
        genre=INCIDENT_ERREUR_MOTEUR,
        motif="KeyError",
        horodatage=datetime.now(UTC) - timedelta(days=3),
    )
    assert (await relever(db_session, fenetre_heures=24)).erreurs_moteur == 0
    assert (await relever(db_session, fenetre_heures=24 * 7)).erreurs_moteur == 1


async def test_incident_survit_a_la_purge_des_parties(db_session, incidents_en_test):
    """La purge des parties mortes efface la partie, jamais la trace de supervision (SET NULL)."""
    user_a, deck_a, user_b, deck_b = await _deux_joueurs(db_session)
    game = await creer_partie(
        db_session, joueur_a=(user_a.id, deck_a.id), joueur_b=(user_b.id, deck_b.id)
    )
    game_id = game.id  # retenu avant tout détachement (cf. `expunge_all` plus bas)
    await consigner_incident(
        genre=INCIDENT_ERREUR_MOTEUR, motif="KeyError", game_id=game_id, user_id=user_a.id
    )
    game.status = "terminee"
    await db_session.flush()

    # `games.updated_at` porte un `onupdate=now()` : le vieillir à la main est sans effet (le
    # flush le réécrit). On se place donc un an plus tard, ce que `purger` accepte par paramètre.
    await purger(
        db_session, maintenant=datetime.now(UTC) + timedelta(days=365), anciennete=timedelta(days=1)
    )

    db_session.expunge_all()  # cf. ci-dessus : on relit la base, pas la carte d'identité
    restantes = (
        await db_session.execute(
            select(func.count()).select_from(Game).where(Game.id == game_id)
        )
    ).scalar_one()
    assert restantes == 0  # la partie a bien été purgée

    incidents = await _incidents(db_session, INCIDENT_ERREUR_MOTEUR)
    assert len(incidents) == 1
    assert incidents[0].game_id is None  # le lien est perdu, le fait demeure
    assert incidents[0].motif == "KeyError"


async def test_genre_inconnu_n_ecrit_rien(db_session, incidents_en_test):
    """Un genre hors vocabulaire est un bug : rien n'est écrit, et rien n'est tu."""
    await consigner_incident(genre="pas_un_genre", motif="R-1.1")
    assert await _incidents(db_session) == []


# --- La route : visible sans SSH, invisible pour qui n'a pas le jeu ---------


async def _compte(client, db, email: str, *, acces_jeu: bool) -> uuid.UUID:
    """Crée, vérifie et connecte un compte, avec ou sans l'accès au jeu (D11)."""
    import re

    reponse = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "last_name": "Dresseur",
            "birth_date": "2000-01-01",
            "accept_terms": True,
        },
    )
    assert reponse.status_code == 202, reponse.text
    jeton = re.search(r"token=(\S+)", client.email_sender.sent[-1]["body"]).group(1)
    await client.post("/auth/verify-email", json={"token": jeton})
    connexion = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert connexion.status_code == 200, connexion.text
    user_id = uuid.UUID(connexion.json()["id"])
    utilisateur = await db.get(User, user_id)
    utilisateur.game_access = acces_jeu
    await db.flush()
    return user_id


async def test_metriques_404_pour_un_compte_sans_acces_au_jeu(api_client, db_session):
    """Compte non invité : le jeu n'existe pas, donc sa supervision non plus (404, pas 403)."""
    await _compte(api_client, db_session, "obs-sansacces@example.com", acces_jeu=False)
    reponse = await api_client.get("/jeu/metriques")
    assert reponse.status_code == 404, reponse.text


async def test_metriques_401_sans_session(api_client):
    """Sans session, aucune métrique : la supervision n'est pas publique."""
    assert (await api_client.get("/jeu/metriques")).status_code == 401


async def test_metriques_visibles_sans_ssh_avec_le_meme_verdict_que_la_sonde(
    api_client, db_session, incidents_en_test
):
    """Critère du lot : les métriques se lisent dans le navigateur, et disent la même chose.

    La route et la sonde appellent tous deux ``evaluer`` : un relevé consulté à l'écran ne peut
    pas contredire l'e-mail du matin.
    """
    await _compte(api_client, db_session, "obs-avecacces@example.com", acces_jeu=True)
    await consigner_incident(genre=INCIDENT_ERREUR_MOTEUR, motif="KeyError")

    reponse = await api_client.get("/jeu/metriques?fenetre_heures=24")
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["fenetre_heures"] == 24
    assert corps["verdict"] == "PANNE"
    assert corps["releve"]["erreurs_moteur"] == 1
    assert "erreur_moteur" in [a["code"] for a in corps["alertes"]]
    # Aucune ventilation par compte : ce serait une fuite entre joueurs.
    assert "user_id" not in reponse.text
    assert "utilisateurs" not in corps["releve"]


async def test_metriques_refuse_une_fenetre_hors_bornes(api_client, db_session):
    """Une fenêtre non bornée rendrait l'agrégat illisible et la requête non bornée : 422."""
    await _compte(api_client, db_session, "obs-fenetre@example.com", acces_jeu=True)
    assert (await api_client.get("/jeu/metriques?fenetre_heures=0")).status_code == 422
    assert (await api_client.get("/jeu/metriques?fenetre_heures=100000")).status_code == 422


def test_destinataire_de_supervision_configure():
    """La sonde a une boîte par défaut, et c'est une adresse de service — jamais un secret."""
    assert "@" in settings.supervision_email
