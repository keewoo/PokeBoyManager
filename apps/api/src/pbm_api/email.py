"""Envoi d'e-mails transactionnels (vérification, mot de passe oublié) via SMTP.

D5 (provisoire) : SMTP configurable — Mailpit en développement (`pbm_api.config.settings`).
Abstraction `EmailSender` injectable : les tests unitaires/API substituent un émetteur qui
enregistre les messages plutôt que de dépendre d'un serveur SMTP.
"""

import asyncio
import smtplib
from email.message import EmailMessage

from pbm_api.config import settings


class EmailSender:
    async def send(self, to: str, subject: str, body: str) -> None:
        raise NotImplementedError


class SmtpEmailSender(EmailSender):
    async def send(self, to: str, subject: str, body: str) -> None:
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


def get_email_sender() -> EmailSender:
    return _default_sender
