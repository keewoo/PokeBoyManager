"""Classement privé entre comptes invités — lot ``j-classement-prive`` (jalon J4, DJ6).

Les trois critères d'acceptation du lot, chacun mesuré :

1. **« Le classement se recalcule intégralement depuis l'historique et retrouve le même état »** —
   :func:`test_recalcul_complet_identique_au_calcul_incremental`. Les deux chemins de calcul du
   module pur (compter-puis-multiplier contre accumuler-partie-par-partie) sont confrontés sur le
   même historique, joueur par joueur et champ par champ. C'est le test que la mission demande, et
   il n'est informatif que parce que les deux implémentations sont réellement distinctes — un pli
   comparé à lui-même ne prouverait rien.
2. **« La désactivation est un réglage, pas un déploiement »** —
   :func:`test_eteindre_le_classement_sans_redemarrer_le_serveur`. Le classement est allumé puis
   éteint **pendant la vie du même processus**, sur le même client HTTP, sans rien recharger : si
   l'activation avait été lue dans la configuration au démarrage (variable d'environnement), ce
   test ne pourrait pas s'écrire.
3. **« Les parties d'entraînement n'y figurent jamais »** — deux fois, aux deux bouts :
   :func:`test_entrainement_jamais_au_classement` sur le calcul pur, et
   :func:`test_la_route_ignore_l_entrainement` de bout en bout par la route.

Plus ce que le lot promet au-delà des critères : l'ordre de lecture des parties ne change rien (une
somme s'en moque, et c'est ce qui rend le recalcul reproductible), **aucun barème ne peut retirer de
points** (DJ6, garde structurelle sur tous les barèmes déclarés plutôt que sur ceux du jour), les
ex æquo partagent leur rang, la fenêtre « récent » inclut sa borne, un réglage inconnu ou une valeur
hors vocabulaire sont **refusés** au lieu d'être écrits sans effet, un compte sans accès au jeu
reçoit 404, et l'historique d'un compte **non invité** n'apparaît pas au tableau.

Les lignes d'historique sont écrites directement dans ``game_result_players`` plutôt que par des
parties réellement jouées, et c'est volontaire : le contrat de ce lot porte sur **cette table**, et
c'est ``test_games_fin_compte`` qui prouve déjà qu'une partie close l'écrit juste. Rejouer des
parties ici mesurerait une deuxième fois le lot précédent, et masquerait les cas limites qu'une
partie réelle ne produit pas à la demande (un mois d'écart entre deux parties, une égalité, un
compte sans pseudo).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from pbm_api.jeu.classement import (
    BAREME_POINTS,
    BAREME_VICTOIRES,
    BAREMES,
    Cumul,
    PartieClassante,
    appliquer,
    bareme,
    calculer,
)
from pbm_api.jeu.reglages import (
    CLE_CLASSEMENT_ACTIF,
    CLE_CLASSEMENT_BAREME,
    NON,
    OUI,
    REGLAGES,
    ReglageInconnu,
    ValeurInvalide,
    interpreter,
    valider,
)
from pbm_api.jeu.reglages_service import ecrire, etat_complet, lire
from pbm_api.models import GameResultPlayer, User
from pbm_api.models.fin_compte import (
    RESULTAT_DEFAITE,
    RESULTAT_EGALITE,
    RESULTAT_VICTOIRE,
)

PASSWORD = "correct horse battery staple"

_IDENTITE = {
    "last_name": "Dresseur",
    "birth_date": date(2000, 1, 1),
    "terms_version": "test",
    "terms_accepted_at": datetime(2000, 1, 1),
}

#: Un instant fixe : les dates du classement se comparent entre elles, jamais à « maintenant »
#: (sauf la fenêtre récente, dont les tests passent l'instant de référence en paramètre).
T0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@example.com"


def _partie(
    joueur: uuid.UUID,
    resultat: str,
    *,
    jours: int = 0,
    comptabilisee: bool = True,
) -> PartieClassante:
    """Une partie close du point de vue du classement, datée par rapport à :data:`T0`."""
    return PartieClassante(
        user_id=joueur,
        resultat=resultat,
        comptabilisee=comptabilisee,
        finie_a=T0 + timedelta(days=jours),
    )


# --- Le calcul pur : le critère d'acceptation central -------------------------


#: Un historique volontairement tordu : trois joueurs, les trois issues, des parties
#: d'entraînement intercalées, un joueur qui n'a QUE de l'entraînement, et des dates en désordre.
#: Chacun de ces traits a déjà cassé une implémentation naïve pendant l'écriture du lot.
def _historique_tordu() -> tuple[list[PartieClassante], dict[str, uuid.UUID]]:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    parties = [
        _partie(a, RESULTAT_VICTOIRE, jours=0),
        _partie(b, RESULTAT_DEFAITE, jours=0),
        _partie(a, RESULTAT_EGALITE, jours=10),
        _partie(b, RESULTAT_EGALITE, jours=10),
        # Entraînement contre le bot : ne doit toucher aucun compteur.
        _partie(a, RESULTAT_VICTOIRE, jours=11, comptabilisee=False),
        _partie(b, RESULTAT_VICTOIRE, jours=20),
        _partie(a, RESULTAT_DEFAITE, jours=20),
        # Une partie plus ANCIENNE que la précédente, arrivée après : c'est le cas que le balayage
        # de `j-fin-effets-compte` produit réellement.
        _partie(b, RESULTAT_VICTOIRE, jours=5),
        _partie(a, RESULTAT_VICTOIRE, jours=5),
        # Un joueur qui ne s'est QUE entraîné : il ne doit pas exister au tableau.
        _partie(c, RESULTAT_VICTOIRE, jours=1, comptabilisee=False),
        _partie(c, RESULTAT_VICTOIRE, jours=2, comptabilisee=False),
    ]
    return parties, {"a": a, "b": b, "c": c}


@pytest.mark.parametrize("formule", [BAREME_POINTS, BAREME_VICTOIRES])
def test_recalcul_complet_identique_au_calcul_incremental(formule):
    """**Critère 1.** Les deux chemins de calcul rendent le même état, pour chaque barème.

    `calculer` compte les issues puis multiplie une fois ; `appliquer` ajoute les points partie par
    partie. Ils ne partagent aucune ligne d'arithmétique : si l'un se trompe de barème, d'issue ou
    de fenêtre, l'autre le dit. C'est le test que la mission exige, et la raison pour laquelle le
    pas incrémental est conservé dans le code alors que la production ne l'appelle pas.
    """
    parties, ids = _historique_tordu()
    recent_depuis = T0 + timedelta(days=15)

    # Chemin incrémental : on plie l'historique, partie par partie, comme le ferait un cache.
    cumuls: dict[uuid.UUID, Cumul] = {}
    for partie in parties:
        cumuls = appliquer(cumuls, partie, bareme=formule, recent_depuis=recent_depuis)

    # Chemin complet : ce que le serveur appelle réellement.
    complet = calculer(parties, bareme=formule, recent_depuis=recent_depuis)
    par_joueur = {ligne.user_id: ligne for ligne in complet.lignes}

    assert set(par_joueur) == set(cumuls), "les deux chemins ne retiennent pas les mêmes joueurs"
    for joueur, cumul in cumuls.items():
        ligne = par_joueur[joueur]
        assert (ligne.points, ligne.parties) == (cumul.points, cumul.parties)
        assert (ligne.victoires, ligne.defaites, ligne.egalites) == (
            cumul.victoires,
            cumul.defaites,
            cumul.egalites,
        )
        assert ligne.points_recents == cumul.points_recents
        assert ligne.derniere_partie_a == cumul.derniere_partie_a

    # Et le joueur qui ne s'est qu'entraîné n'existe dans ni l'un ni l'autre.
    assert ids["c"] not in par_joueur


def test_l_ordre_de_lecture_ne_change_pas_le_classement():
    """Lu à l'endroit ou à l'envers, le tableau est le même — c'est ce qui le rend reproductible.

    Contraste voulu avec les **séries** de `j-fin-effets-compte`, qui exigent l'ordre
    chronologique : une série dépend de l'ordre, une somme non. C'est pourquoi le service ne
    demande aucun tri à la base.
    """
    parties, _ = _historique_tordu()
    endroit = calculer(parties, bareme=BAREME_POINTS)
    envers = calculer(list(reversed(parties)), bareme=BAREME_POINTS)
    assert endroit.lignes == envers.lignes


def test_entrainement_jamais_au_classement():
    """**Critère 3**, côté calcul : l'entraînement ne crée ni ligne ni point.

    Vérifié sur les deux chemins, parce que c'est le genre de condition qu'on oublie dans celui
    qu'on n'appelle pas.
    """
    joueur = uuid.uuid4()
    entrainements = [
        _partie(joueur, RESULTAT_VICTOIRE, jours=i, comptabilisee=False) for i in range(5)
    ]

    assert calculer(entrainements, bareme=BAREME_POINTS).lignes == ()

    cumuls: dict[uuid.UUID, Cumul] = {}
    for partie in entrainements:
        cumuls = appliquer(cumuls, partie, bareme=BAREME_POINTS)
    assert cumuls == {}


def test_aucun_bareme_ne_peut_retirer_de_points():
    """DJ6 : « sans saison ni **perte de points** » — garde **structurelle** sur tous les barèmes.

    Porte sur :data:`BAREMES` en entier, pas sur les deux barèmes du jour : un barème ajouté plus
    tard avec une défaite négative fait rougir ce test sans que personne n'ait eu à y penser. C'est
    la même façon de faire que la garde du langage de scripts (`j-securite-jeu`), et pour la même
    raison : une liste figée dans un test finit toujours par retarder sur le code.
    """
    for nom, formule in BAREMES.items():
        for issue, points in (
            ("victoire", formule.victoire),
            ("égalité", formule.egalite),
            ("défaite", formule.defaite),
        ):
            assert points >= 0, f"le barème {nom!r} retire des points sur une {issue}"
        # Et une victoire vaut toujours au moins une égalité : un barème qui punirait la victoire
        # serait un barème qu'on applique à l'envers.
        assert formule.victoire >= formule.egalite >= formule.defaite, nom


def test_les_ex_aequo_partagent_leur_rang():
    """Deux joueurs à égalité de points portent le même rang, et le suivant saute (1, 1, 3).

    Départager un ex æquo serait inventer une hiérarchie que le barème n'a pas produite — et c'est
    exactement le détail qui transforme un tableau amical en dispute.
    """
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    parties = [
        _partie(a, RESULTAT_VICTOIRE),
        _partie(b, RESULTAT_VICTOIRE),
        _partie(c, RESULTAT_DEFAITE),
    ]
    rangs = [ligne.rang for ligne in calculer(parties, bareme=BAREME_POINTS).lignes]
    assert rangs == [1, 1, 3]


def test_la_fenetre_recente_inclut_sa_borne():
    """Une partie jouée exactement à la borne est « récente » : on ne la perd pas d'une seconde."""
    joueur = uuid.uuid4()
    borne = T0 + timedelta(days=10)
    parties = [
        _partie(joueur, RESULTAT_VICTOIRE, jours=10),  # pile sur la borne → compte
        _partie(joueur, RESULTAT_VICTOIRE, jours=9),  # avant la borne → hors fenêtre
    ]
    ligne = calculer(parties, bareme=BAREME_POINTS, recent_depuis=borne).lignes[0]
    assert ligne.points == 6
    assert ligne.points_recents == 3


def test_le_demandeur_figure_au_tableau_meme_sans_partie():
    """Un joueur qui n'a rien joué se voit à zéro, plutôt qu'absent de son propre tableau."""
    joueur, autre = uuid.uuid4(), uuid.uuid4()
    classement = calculer(
        [_partie(autre, RESULTAT_VICTOIRE)], bareme=BAREME_POINTS, inclure=(joueur,)
    )
    moi = next(ligne for ligne in classement.lignes if ligne.user_id == joueur)
    assert (moi.points, moi.parties, moi.rang) == (0, 0, 2)


def test_un_bareme_inconnu_rend_le_defaut_sans_lever():
    """Un nom de barème caduc (barème retiré du code) n'a jamais pour effet une erreur 500.

    Le classement s'affiche sur la formule par défaut, et la sortie **nomme** le barème appliqué :
    l'écart reste visible à qui le cherche, ce qui n'est pas un repli silencieux.
    """
    assert bareme("barème-qui-n-existe-pas").nom == BAREME_POINTS.nom
    assert bareme(None).nom == BAREME_POINTS.nom
    assert bareme(BAREME_VICTOIRES.nom) is BAREME_VICTOIRES


def test_les_points_se_recomptent_a_la_main():
    """Le total affiché doit être recomptable de tête : 2 victoires + 1 égalité = 7 points."""
    joueur = uuid.uuid4()
    parties = [
        _partie(joueur, RESULTAT_VICTOIRE),
        _partie(joueur, RESULTAT_VICTOIRE, jours=1),
        _partie(joueur, RESULTAT_EGALITE, jours=2),
        _partie(joueur, RESULTAT_DEFAITE, jours=3),
    ]
    ligne = calculer(parties, bareme=BAREME_POINTS).lignes[0]
    assert (ligne.points, ligne.victoires, ligne.egalites, ligne.defaites) == (7, 2, 1, 1)
    assert ligne.parties == 4
    victoires_seules = calculer(parties, bareme=BAREME_VICTOIRES).lignes[0]
    assert victoires_seules.points == 2


# --- Le registre de réglages : rien ne s'écrit en silence ---------------------


def test_une_cle_inconnue_est_refusee_pas_ecrite():
    """Une faute de frappe (« classement_active ») lève, et le message nomme les clés existantes.

    Sans ce refus, la commande d'administration rendrait un succès et JF croirait avoir activé le
    classement : la panne muette que ce dépôt refuse par principe.
    """
    with pytest.raises(ReglageInconnu) as leve:
        valider("classement_active", OUI)
    assert CLE_CLASSEMENT_ACTIF in str(leve.value)


def test_une_valeur_hors_vocabulaire_est_refusee():
    """« true », « 1 », « ok » ne sont pas « oui » : accepter dix orthographes, c'est accepter une
    faute de frappe qui ressemble à un succès."""
    for valeur in ("true", "1", "ok", "yes"):
        with pytest.raises(ValeurInvalide):
            valider(CLE_CLASSEMENT_ACTIF, valeur)
    # La casse et les espaces, en revanche, sont normalisés : la valeur est tapée à la main.
    assert valider(CLE_CLASSEMENT_ACTIF, "  OUI ") == OUI


def test_le_defaut_declare_est_eteint():
    """DJ6 dit « en option, activable par JF » : un lot ne s'auto-active pas."""
    assert REGLAGES[CLE_CLASSEMENT_ACTIF].defaut == NON
    assert interpreter(CLE_CLASSEMENT_ACTIF, None) == NON


def test_les_baremes_choisissables_sont_derives_du_code():
    """Les valeurs acceptées du réglage viennent de :data:`BAREMES` — pas d'une liste recopiée."""
    assert set(REGLAGES[CLE_CLASSEMENT_BAREME].valeurs) == set(BAREMES)


async def test_ecrire_puis_lire_un_reglage(db_session):
    """Un réglage posé est relu ; jamais touché, il rend son défaut (aucune ligne à semer)."""
    assert await lire(db_session, CLE_CLASSEMENT_ACTIF) == NON
    await ecrire(db_session, CLE_CLASSEMENT_ACTIF, OUI)
    assert await lire(db_session, CLE_CLASSEMENT_ACTIF) == OUI
    # Idempotent : reposer la même valeur ne casse rien (ON CONFLICT DO UPDATE).
    await ecrire(db_session, CLE_CLASSEMENT_ACTIF, OUI)
    assert await lire(db_session, CLE_CLASSEMENT_ACTIF) == OUI

    etat = {
        cle: (stockee, effective) for cle, stockee, effective in await etat_complet(db_session)
    }
    assert etat[CLE_CLASSEMENT_ACTIF] == (OUI, OUI)
    # Le barème n'a jamais été posé : stocké à None, effectif au défaut. C'est cet écart que la
    # commande d'administration doit montrer.
    assert etat[CLE_CLASSEMENT_BAREME] == (None, BAREME_POINTS.nom)


async def test_lire_une_cle_inconnue_leve_avant_de_toucher_la_base(db_session):
    with pytest.raises(ReglageInconnu):
        await lire(db_session, "reglage_imaginaire")


# --- La route ----------------------------------------------------------------


async def _compte_invite(
    client: httpx.AsyncClient, db, label: str, *, pseudo: str | None, acces: bool = True
) -> uuid.UUID:
    """Inscrit, vérifie et connecte un compte ; lui donne (ou non) l'accès au jeu et un pseudo.

    ⚠️ Le client ne garde qu'une session à la fois : le **dernier** compte créé est celui qui
    interroge. Les comptes « adversaires » sont donc créés avant.
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


async def _resultat(
    db,
    joueur: uuid.UUID,
    resultat: str,
    *,
    comptabilisee: bool = True,
    jours: int = 0,
    finie_a: datetime | None = None,
) -> None:
    """Pose une ligne d'historique (``game_result_players``) — la seule table que le lot lit.

    ``game_id`` est un identifiant libre : il n'y a **aucune** clé étrangère vers ``games``, parce
    qu'un résultat survit à la purge de sa partie (`docs/jeu/FIN-COMPTE.md`). C'est ce qui permet
    d'écrire un historique de test sans fabriquer de parties.
    """
    db.add(
        GameResultPlayer(
            game_id=uuid.uuid4(),
            user_id=joueur,
            seat=0,
            deck_id=None,
            adversaire_user_id=None,
            adversaire_bot=not comptabilisee,
            resultat=resultat,
            comptabilisee=comptabilisee,
            finie_a=finie_a or (datetime.now(UTC) - timedelta(days=jours)),
            duree_s=600,
            degats_infliges=0,
            kos_infliges=0,
            recompenses_prises=0,
            cartes_jouees=0,
            energies_attachees=0,
            coups_joues=0,
        )
    )
    await db.flush()


async def test_le_classement_est_eteint_par_defaut(api_client, db_session):
    """Sans décision de JF, la route répond 200 avec zéro ligne — même avec un historique garni.

    200 et pas 404 : l'écran doit distinguer « JF n'a pas activé le classement » d'une route
    cassée. Et quand il est éteint, l'historique n'est pas lu du tout.
    """
    joueur = await _compte_invite(api_client, db_session, "cl-defaut", pseudo="solo")
    await _resultat(db_session, joueur, RESULTAT_VICTOIRE)

    reponse = await api_client.get("/jeu/classement")
    assert reponse.status_code == 200, reponse.text
    corps = reponse.json()
    assert corps["actif"] is False
    assert corps["lignes"] == []
    # Le barème est quand même nommé : l'écran peut annoncer la formule qui s'appliquerait.
    assert corps["bareme"]["nom"] == BAREME_POINTS.nom


async def test_eteindre_le_classement_sans_redemarrer_le_serveur(api_client, db_session):
    """**Critère 2.** Allumé puis éteint dans la vie du même processus, sans rien recharger.

    C'est la preuve que la désactivation est un réglage et non un déploiement : aucune variable
    d'environnement n'est relue, aucun conteneur ne redémarre, et une partie en cours ne serait pas
    interrompue. Si l'activation vivait dans la configuration, ce test serait inécrivable.
    """
    joueur = await _compte_invite(api_client, db_session, "cl-bascule", pseudo="bascule")
    await _resultat(db_session, joueur, RESULTAT_VICTOIRE)

    await ecrire(db_session, CLE_CLASSEMENT_ACTIF, OUI)
    allume = (await api_client.get("/jeu/classement")).json()
    assert allume["actif"] is True
    assert [ligne["pseudo"] for ligne in allume["lignes"]] == ["bascule"]

    await ecrire(db_session, CLE_CLASSEMENT_ACTIF, NON)
    eteint = (await api_client.get("/jeu/classement")).json()
    assert eteint["actif"] is False
    assert eteint["lignes"] == []


async def test_le_tableau_classe_les_comptes_invites(api_client, db_session):
    """Le tableau ordonné, surligné sur ma ligne, et recomptable depuis les compteurs rendus."""
    adversaire = await _compte_invite(api_client, db_session, "cl-adv", pseudo="aymeric")
    moi = await _compte_invite(api_client, db_session, "cl-moi", pseudo="jf")
    await ecrire(db_session, CLE_CLASSEMENT_ACTIF, OUI)

    # L'adversaire mène : deux victoires (6 points) contre une victoire et une égalité (4).
    await _resultat(db_session, adversaire, RESULTAT_VICTOIRE, jours=1)
    await _resultat(db_session, adversaire, RESULTAT_VICTOIRE, jours=2)
    await _resultat(db_session, moi, RESULTAT_VICTOIRE, jours=1)
    await _resultat(db_session, moi, RESULTAT_EGALITE, jours=2)

    corps = (await api_client.get("/jeu/classement")).json()
    assert corps["actif"] is True
    lignes = corps["lignes"]
    assert [(ligne["rang"], ligne["pseudo"], ligne["points"]) for ligne in lignes] == [
        (1, "aymeric", 6),
        (2, "jf", 4),
    ]
    # Ma ligne est signalée, et aucune ligne ne publie d'identifiant de compte.
    assert [ligne["moi"] for ligne in lignes] == [False, True]
    assert all("user_id" not in ligne for ligne in lignes)
    # Les points se recomptent avec le barème rendu à côté.
    formule = corps["bareme"]
    mienne = lignes[1]
    assert mienne["points"] == (
        mienne["victoires"] * formule["points_victoire"]
        + mienne["egalites"] * formule["points_egalite"]
        + mienne["defaites"] * formule["points_defaite"]
    )


async def test_la_route_ignore_l_entrainement(api_client, db_session):
    """**Critère 3**, de bout en bout : s'entraîner contre le bot ne rapporte aucun point."""
    moi = await _compte_invite(api_client, db_session, "cl-entrain", pseudo="entraine")
    await ecrire(db_session, CLE_CLASSEMENT_ACTIF, OUI)
    for jour in range(4):
        await _resultat(db_session, moi, RESULTAT_VICTOIRE, comptabilisee=False, jours=jour)
    await _resultat(db_session, moi, RESULTAT_DEFAITE, jours=5)

    ligne = (await api_client.get("/jeu/classement")).json()["lignes"][0]
    assert (ligne["points"], ligne["victoires"], ligne["parties"]) == (0, 0, 1)


async def test_un_compte_sans_acces_au_jeu_recoit_404(api_client, db_session):
    """D11 : le jeu est réservé aux comptes invités, et un 404 ne confirme rien (pas un 403)."""
    await _compte_invite(api_client, db_session, "cl-dehors", pseudo="dehors", acces=False)
    reponse = await api_client.get("/jeu/classement")
    assert reponse.status_code == 404, reponse.text


async def test_l_historique_d_un_compte_non_invite_n_apparait_pas(api_client, db_session):
    """Un compte qui n'a pas (ou plus) l'accès au jeu ne figure pas au classement des invités.

    C'est ce qui exclut aussi le compte du bot d'entraînement du tableau **sans avoir à le
    nommer** : une condition de moins à maintenir quand un autre compte technique apparaîtra.
    """
    exclu = await _compte_invite(api_client, db_session, "cl-exclu", pseudo="exclu", acces=False)
    moi = await _compte_invite(api_client, db_session, "cl-dedans", pseudo="dedans")
    await ecrire(db_session, CLE_CLASSEMENT_ACTIF, OUI)
    # L'exclu a un historique flatteur : il ne doit pas pour autant apparaître.
    for jour in range(3):
        await _resultat(db_session, exclu, RESULTAT_VICTOIRE, jours=jour)
    await _resultat(db_session, moi, RESULTAT_DEFAITE, jours=1)

    lignes = (await api_client.get("/jeu/classement")).json()["lignes"]
    assert [ligne["pseudo"] for ligne in lignes] == ["dedans"]


async def test_je_me_vois_a_zero_sans_avoir_joue(api_client, db_session):
    """Un nouveau joueur se trouve dans son propre tableau, à zéro — pas absent."""
    await _compte_invite(api_client, db_session, "cl-neuf", pseudo="nouveau")
    await ecrire(db_session, CLE_CLASSEMENT_ACTIF, OUI)

    lignes = (await api_client.get("/jeu/classement")).json()["lignes"]
    assert [(ligne["pseudo"], ligne["points"], ligne["moi"]) for ligne in lignes] == [
        ("nouveau", 0, True)
    ]


async def test_le_bareme_choisi_par_jf_change_les_points(api_client, db_session):
    """Changer de barème est une commande, pas un déploiement — et la sortie nomme la formule."""
    moi = await _compte_invite(api_client, db_session, "cl-bareme", pseudo="barème")
    await ecrire(db_session, CLE_CLASSEMENT_ACTIF, OUI)
    await _resultat(db_session, moi, RESULTAT_VICTOIRE, jours=1)
    await _resultat(db_session, moi, RESULTAT_EGALITE, jours=2)

    en_points = (await api_client.get("/jeu/classement")).json()
    assert en_points["bareme"]["nom"] == BAREME_POINTS.nom
    assert en_points["lignes"][0]["points"] == 4

    await ecrire(db_session, CLE_CLASSEMENT_BAREME, BAREME_VICTOIRES.nom)
    en_victoires = (await api_client.get("/jeu/classement")).json()
    assert en_victoires["bareme"]["nom"] == BAREME_VICTOIRES.nom
    assert en_victoires["lignes"][0]["points"] == 1


async def test_la_fenetre_recente_est_bornee(api_client, db_session):
    """Une fenêtre hors bornes est refusée en 422 : on ne calcule pas sur dix ans par surprise."""
    await _compte_invite(api_client, db_session, "cl-fenetre", pseudo="fenêtre")
    await ecrire(db_session, CLE_CLASSEMENT_ACTIF, OUI)
    assert (await api_client.get("/jeu/classement?fenetre_jours=0")).status_code == 422
    assert (await api_client.get("/jeu/classement?fenetre_jours=5000")).status_code == 422
    ok = await api_client.get("/jeu/classement?fenetre_jours=7")
    assert ok.status_code == 200
    assert ok.json()["fenetre_jours"] == 7


async def test_les_points_recents_suivent_la_fenetre(api_client, db_session):
    """« Évolution dans le temps » : seuls les points gagnés dans la fenêtre y figurent."""
    moi = await _compte_invite(api_client, db_session, "cl-recent", pseudo="récent")
    await ecrire(db_session, CLE_CLASSEMENT_ACTIF, OUI)
    await _resultat(db_session, moi, RESULTAT_VICTOIRE, jours=1)  # dans les 7 jours
    await _resultat(db_session, moi, RESULTAT_VICTOIRE, jours=40)  # bien avant

    ligne = (await api_client.get("/jeu/classement?fenetre_jours=7")).json()["lignes"][0]
    assert ligne["points"] == 6
    assert ligne["points_recents"] == 3
