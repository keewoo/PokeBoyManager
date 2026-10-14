"""Le **câblage** des notifications dans le jeu (lot `j-notifications-jeu`), contre la base réelle.

Les règles sont vérifiées à part (``test_jeu_notifications_regles.py``, sans base). Ici on prouve
que les règles sont **réellement traversées** par les chemins du jeu — une règle juste mais
contournée ne vaut rien :

* l'invitation par pseudo passe par le canal, donc par le silence nocturne et par les réglages
  (``test_invitation_*``). **C'est le critère « le silence nocturne est respecté, y compris pour les
  invitations »** : avant ce lot, l'e-mail partait en dur depuis
  ``pbm_api.games.invitations``, et aucun réglage ne pouvait l'arrêter ;
* une partie entière ne dépasse jamais le plafond, **compteurs lus en base**
  (``test_plafond_dune_partie_tient_en_base``) ;
* une notification ne coûte jamais un coup (``test_une_panne_du_canal_ne_casse_pas_le_coup``).
"""

import uuid
from datetime import UTC, datetime

from test_jeu_notifications_routes import creer_partie_nue

from pbm_api.email import EmailSender
from pbm_api.games import invitations
from pbm_api.models import User
from pbm_api.models.notifications import (
    NOTIF_ADVERSAIRE_TROUVE,
    NOTIF_GENRES,
    NOTIF_INVITATION_RECUE,
    NOTIF_TON_TOUR,
    GameNotification,
)
from pbm_api.notifications import service
from pbm_api.notifications.regles import PLAFOND_PAR_PARTIE


class RecordingEmailSender(EmailSender):
    """Capture les e-mails au lieu de les envoyer : la suite ne dépend d'aucun SMTP.

    Même substitut que celui de ``conftest`` (les tests de ce dépôt s'importent par nom de module,
    sans paquet : le dupliquer coûte six lignes et évite une dépendance entre fichiers de test).
    """

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        """Enregistre le message au lieu de l'expédier."""
        self.sent.append({"to": to, "subject": subject, "body": body})


#: Un mardi 14 h à Paris (hors silence) et le même soir 23 h 30 (en plein silence par défaut).
EN_PLEIN_JOUR = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
EN_PLEINE_NUIT = datetime(2026, 10, 13, 21, 30, tzinfo=UTC)


async def _joueur(db, label: str) -> User:
    """Un compte invité au jeu, avec un pseudo unique — le minimum pour s'inviter."""
    suffixe = uuid.uuid4().hex[:8]
    user = User(
        email=f"{label}-{suffixe}@example.com",
        password_hash="x" * 20,
        last_name="Dresseur",
        birth_date=datetime(2000, 1, 1).date(),
        terms_version="1",
        # `users.terms_accepted_at` est un TIMESTAMP **sans** fuseau : un datetime conscient y est
        # refusé par asyncpg. On y met donc l'instant UTC rendu naïf, comme le reste du dépôt.
        terms_accepted_at=datetime.now(UTC).replace(tzinfo=None),
        pseudo=f"{label}{suffixe}",
        game_access=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _notifications_de(db, user_id: uuid.UUID) -> list[GameNotification]:
    return await service.lister(db, user_id)


# --- L'invitation passe par le canal ----------------------------------------------------------


async def test_invitation_notifie_en_application_et_par_email(db_session):
    """En pleine journée : la notification est enregistrée **et** l'e-mail de rappel part."""
    emetteur = RecordingEmailSender()
    alice = await _joueur(db_session, "alice")
    bob = await _joueur(db_session, "bob")

    await invitations.inviter_par_pseudo(
        db_session,
        emetteur,
        inviter_id=alice.id,
        pseudo=bob.pseudo,
        maintenant=EN_PLEIN_JOUR,
    )

    recues = await _notifications_de(db_session, bob.id)
    assert [n.genre for n in recues] == [NOTIF_INVITATION_RECUE]
    assert recues[0].silencieuse is False
    assert recues[0].donnees["pseudo"] == alice.pseudo
    assert recues[0].game_id is None, "une invitation n'a pas encore de partie"
    assert len(emetteur.sent) == 1
    assert "Invitation" in emetteur.sent[0]["subject"]
    assert emetteur.sent[0]["to"] == bob.email


async def test_invitation_de_nuit_enregistree_mais_sans_email(db_session):
    """**Le critère.** Invitation reçue pendant le silence nocturne : enregistrée, aucun e-mail.

    Rien n'est perdu — la notification existe, marquée ``silencieuse``, et l'invitation reste dans
    la liste des reçues. Ce qui n'arrive pas, c'est le réveil.

    Échoue sans ce lot : l'e-mail partait en dur, quelle que soit l'heure.
    """
    emetteur = RecordingEmailSender()
    alice = await _joueur(db_session, "alice")
    bob = await _joueur(db_session, "bob")

    await invitations.inviter_par_pseudo(
        db_session,
        emetteur,
        inviter_id=alice.id,
        pseudo=bob.pseudo,
        maintenant=EN_PLEINE_NUIT,
    )

    recues = await _notifications_de(db_session, bob.id)
    assert [n.genre for n in recues] == [NOTIF_INVITATION_RECUE]
    assert recues[0].silencieuse is True
    assert emetteur.sent == [], "aucun e-mail ne part pendant le silence nocturne"


async def test_invitation_silence_coupe_par_le_destinataire_reveille_lemail(db_session):
    """Le silence est un **réglage** : coupé, l'e-mail repart la nuit. Sinon il serait imposé."""
    emetteur = RecordingEmailSender()
    alice = await _joueur(db_session, "alice")
    bob = await _joueur(db_session, "bob")
    await service.enregistrer_reglages(db_session, bob.id, silence_actif=False)

    await invitations.inviter_par_pseudo(
        db_session,
        emetteur,
        inviter_id=alice.id,
        pseudo=bob.pseudo,
        maintenant=EN_PLEINE_NUIT,
    )

    assert len(emetteur.sent) == 1
    recues = await _notifications_de(db_session, bob.id)
    assert recues[0].silencieuse is False


async def test_invitation_genre_coupe_nenregistre_rien_et_nenvoie_rien(db_session):
    """Un destinataire qui a coupé « invitation reçue » ne reçoit ni notification ni e-mail.

    L'invitation **existe** malgré tout : elle reste dans sa liste des reçues (``recues``), qui est
    la source de vérité. Couper la notification ne fait pas disparaître l'invitation.
    """
    emetteur = RecordingEmailSender()
    alice = await _joueur(db_session, "alice")
    bob = await _joueur(db_session, "bob")
    await service.enregistrer_reglages(
        db_session, bob.id, genres_desactives=[NOTIF_INVITATION_RECUE]
    )

    invitation = await invitations.inviter_par_pseudo(
        db_session,
        emetteur,
        inviter_id=alice.id,
        pseudo=bob.pseudo,
        maintenant=EN_PLEIN_JOUR,
    )

    assert await _notifications_de(db_session, bob.id) == []
    assert emetteur.sent == []
    recues = await invitations.recues(db_session, user_id=bob.id)
    assert [i.id for i in recues] == [invitation.id], "l'invitation elle-même n'a pas disparu"


async def test_invitation_relais_email_coupe_mais_notification_gardee(db_session):
    """Couper le **relais e-mail** seul laisse la notification dans l'application.

    Deux réglages distincts, deux effets distincts : « ne m'envoie pas d'e-mail » n'est pas « ne me
    prévient pas ».
    """
    emetteur = RecordingEmailSender()
    alice = await _joueur(db_session, "alice")
    bob = await _joueur(db_session, "bob")
    await service.enregistrer_reglages(db_session, bob.id, relais_email_invitation=False)

    await invitations.inviter_par_pseudo(
        db_session,
        emetteur,
        inviter_id=alice.id,
        pseudo=bob.pseudo,
        maintenant=EN_PLEIN_JOUR,
    )

    assert emetteur.sent == []
    assert len(await _notifications_de(db_session, bob.id)) == 1


async def test_deux_invitations_coup_sur_coup_ne_font_quune_notification(db_session):
    """Anti-doublon en base : une seconde invitation non lue ne re-sonne pas."""
    emetteur = RecordingEmailSender()
    alice = await _joueur(db_session, "alice")
    carole = await _joueur(db_session, "carole")
    bob = await _joueur(db_session, "bob")

    await invitations.inviter_par_pseudo(
        db_session, emetteur, inviter_id=alice.id, pseudo=bob.pseudo, maintenant=EN_PLEIN_JOUR
    )
    await invitations.inviter_par_pseudo(
        db_session, emetteur, inviter_id=carole.id, pseudo=bob.pseudo, maintenant=EN_PLEIN_JOUR
    )

    assert len(await _notifications_de(db_session, bob.id)) == 1
    assert len(emetteur.sent) == 1, "pas deux e-mails pour deux invitations non lues"


# --- Le plafond, compteurs lus en base --------------------------------------------------------


async def test_plafond_dune_partie_tient_en_base(db_session):
    """**Le critère** : une partie bavarde ne produit jamais plus que le plafond, compté en base.

    On rejoue le pire cas — tous les genres, cinquante tours, chaque notification aussitôt lue pour
    neutraliser l'anti-doublon — et on compte les lignes de ``game_notifications`` pour cette
    partie. Jamais plus de :data:`PLAFOND_PAR_PARTIE`.
    """
    joueur = await _joueur(db_session, "joueur")
    partie = await creer_partie_nue(db_session, joueurs=[joueur.id])
    genres_de_partie = sorted(NOTIF_GENRES - {NOTIF_INVITATION_RECUE})

    for _ in range(50):
        for genre in genres_de_partie:
            await service.notifier(
                db_session,
                destinataire_id=joueur.id,
                genre=genre,
                game_id=partie.id,
                instant=EN_PLEIN_JOUR,
            )
        await service.marquer_toutes_lues(db_session, joueur.id, instant=EN_PLEIN_JOUR)

    total = len(await service.lister(db_session, joueur.id, limite=service.LIMITE_LECTURE))
    assert total <= PLAFOND_PAR_PARTIE, f"{total} notifications pour une seule partie"
    assert total == PLAFOND_PAR_PARTIE, "le pire cas doit atteindre le plafond, pas moins"


async def test_plafond_dune_partie_ne_bride_pas_une_autre(db_session):
    """Le plafond est **par partie** : une partie saturée n'empêche pas la suivante de notifier."""
    joueur = await _joueur(db_session, "joueur")
    une = await creer_partie_nue(db_session, joueurs=[joueur.id])
    autre = await creer_partie_nue(db_session, joueurs=[joueur.id])

    for _ in range(PLAFOND_PAR_PARTIE + 5):
        await service.notifier(
            db_session,
            destinataire_id=joueur.id,
            genre=NOTIF_TON_TOUR,
            game_id=une.id,
            instant=EN_PLEIN_JOUR,
        )
        await service.marquer_toutes_lues(db_session, joueur.id, instant=EN_PLEIN_JOUR)

    assert await service.notifier(
        db_session,
        destinataire_id=joueur.id,
        genre=NOTIF_ADVERSAIRE_TROUVE,
        game_id=autre.id,
        instant=EN_PLEIN_JOUR,
    ), "la seconde partie doit pouvoir notifier"


# --- Robustesse -------------------------------------------------------------------------------


async def test_une_panne_du_canal_ne_casse_pas_le_coup(db_session, caplog):
    """``notifier_sans_casser`` avale la panne **en la journalisant** — le coup reste appliqué.

    Un genre inconnu simule la panne (il lève :class:`GenreInconnu`). On exige la trace : un canal
    qui tombe sans rien dire serait exactement le repli silencieux que le projet interdit.
    """
    joueur = await _joueur(db_session, "joueur")
    partie = await creer_partie_nue(db_session, joueurs=[joueur.id])

    with caplog.at_level("ERROR"):
        resultat = await service.notifier_sans_casser(
            db_session,
            destinataire_id=joueur.id,
            genre="sonnerie_imaginaire",
            game_id=partie.id,
            instant=EN_PLEIN_JOUR,
        )

    assert resultat is None
    traces = [m for m in caplog.messages if "perdue" in m]
    assert traces, "la panne doit laisser une trace"


async def test_reglages_defauts_du_modele_et_du_code_daccord(db_session):
    """Les défauts du **code** (``Reglages()``) et ceux du **modèle** disent la même chose.

    Deux jeux de défauts qui divergent, c'est un compte réglé différemment selon qu'il a ouvert ses
    réglages ou non — un écart qu'on ne verrait qu'en production.
    """
    joueur = await _joueur(db_session, "joueur")
    avant = await service.charger_reglages(db_session, joueur.id)
    # Un PATCH qui ne change rien crée la ligne : les deux doivent coïncider.
    apres = await service.enregistrer_reglages(db_session, joueur.id)
    assert avant == apres
