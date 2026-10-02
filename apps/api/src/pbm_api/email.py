"""Envoi d'e-mails transactionnels (vérification, mot de passe oublié) via SMTP.

D5 (provisoire) : SMTP configurable — Mailpit en développement (`pbm_api.config.settings`).
Abstraction `EmailSender` injectable : les tests unitaires/API substituent un émetteur qui
enregistre les messages plutôt que de dépendre d'un serveur SMTP.
"""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from pbm_api.config import settings

logger = logging.getLogger(__name__)


class EmailSender:
    """Interface d'envoi — permet de substituer un émetteur de test aux implémentations réelles."""

    async def send(self, to: str, subject: str, body: str) -> None:
        """Envoie un e-mail texte. À implémenter par chaque sous-classe."""
        raise NotImplementedError


class DisabledEmailSender(EmailSender):
    """SMTP non configuré (`SMTP_HOST` vide, cible PROD/MVP sans serveur de mail) : envois
    désactivés PROPREMENT (lot `pbm-deploy`). On journalise en WARNING et on n'émet rien, plutôt
    que d'ouvrir une connexion SMTP vers un hôte vide — ce qui ferait échouer l'inscription ou la
    réinitialisation de mot de passe par une exception de connexion. Ce n'est pas un repli
    silencieux : le mode « e-mail désactivé » est un choix de configuration explicite, tracé."""

    async def send(self, to: str, subject: str, body: str) -> None:
        """N'envoie rien : journalise en WARNING pour que l'absence d'envoi reste visible."""
        logger.warning(
            "E-mail non envoyé (SMTP désactivé : SMTP_HOST vide) — to=%s subject=%r", to, subject
        )


class SmtpEmailSender(EmailSender):
    """Envoi réel par SMTP (D5 provisoire) — Mailpit en développement, serveur SMTP en ligne."""

    async def send(self, to: str, subject: str, body: str) -> None:
        """Envoie via SMTP, hors boucle asyncio (`smtplib` est bloquant)."""
        await asyncio.to_thread(self._send_sync, to, subject, body)

    def _send_sync(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=5) as smtp:
            if settings.smtp_user:
                smtp.starttls()
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)


_default_sender = SmtpEmailSender()
_disabled_sender = DisabledEmailSender()


def get_email_sender() -> EmailSender:
    """Choisit l'émetteur selon la configuration : désactivé si `SMTP_HOST` est vide, SMTP sinon."""
    # `SMTP_HOST` vide = envois désactivés proprement (lot `pbm-deploy`) : aucune connexion SMTP,
    # aucun échec d'inscription/reset sur un hôte vide.
    if not settings.smtp_host:
        return _disabled_sender
    return _default_sender
