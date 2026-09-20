"""SMTP désactivé proprement (lot `pbm-deploy`) : `SMTP_HOST` vide → `DisabledEmailSender`, qui
n'ouvre aucune connexion SMTP et ne lève pas — l'inscription/la réinitialisation ne plantent pas
en PROD lancée sans serveur de mail."""

import asyncio

from pbm_api import email as email_mod
from pbm_api.email import DisabledEmailSender, SmtpEmailSender, get_email_sender


def test_disabled_sender_when_smtp_host_empty(monkeypatch):
    monkeypatch.setattr(email_mod.settings, "smtp_host", "")
    assert isinstance(get_email_sender(), DisabledEmailSender)


def test_smtp_sender_when_smtp_host_present(monkeypatch):
    monkeypatch.setattr(email_mod.settings, "smtp_host", "localhost")
    assert isinstance(get_email_sender(), SmtpEmailSender)


def test_disabled_sender_send_does_not_raise(monkeypatch):
    monkeypatch.setattr(email_mod.settings, "smtp_host", "")
    asyncio.run(get_email_sender().send("a@b.fr", "sujet", "corps"))
