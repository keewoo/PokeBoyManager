"""Commandes d'administration — exécutées directement sur le serveur (jamais exposées en HTTP).

Usage :
    uv run python -m pbm_api.admin create-user --email a@b.fr --pseudo aymeric \\
        --last-name Fontaine --birth-date 1990-01-01 --accept-terms \\
        [--first-name Aymeric] [--password-stdin] [--must-change-password]

Le mot de passe est soit lu sur l'entrée standard (`--password-stdin`), soit généré
aléatoirement et affiché une seule fois en sortie : jamais en argument de la ligne de
commande (visible dans l'historique du shell et la liste des processus), jamais journalisé.
"""

import argparse
import asyncio
import secrets
import sys
from datetime import UTC, date, datetime

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select

from pbm_api.auth.service import normalize_email
from pbm_api.db import async_session_factory
from pbm_api.legal import CURRENT_TERMS_VERSION
from pbm_api.models import User
from pbm_api.security.passwords import hash_password, is_password_long_enough

_EMAIL_ADAPTER = TypeAdapter(EmailStr)


class CreateUserError(Exception):
    pass


def _parse_email(value: str) -> str:
    try:
        _EMAIL_ADAPTER.validate_python(value)
    except ValidationError:
        raise CreateUserError(f"Adresse e-mail invalide : {value!r}") from None
    return normalize_email(value)


def _parse_birth_date(value: str) -> date:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise CreateUserError(
            f"Date de naissance invalide (attendu AAAA-MM-JJ) : {value!r}"
        ) from None
    if parsed >= date.today():
        raise CreateUserError("La date de naissance doit être dans le passé.")
    return parsed


def _read_password_from_stdin() -> str:
    password = sys.stdin.readline().rstrip("\n")
    if not password:
        raise CreateUserError("Aucun mot de passe reçu sur l'entrée standard.")
    if not is_password_long_enough(password):
        raise CreateUserError("Le mot de passe doit contenir au moins 10 caractères.")
    return password


async def create_user(
    *,
    email: str,
    pseudo: str,
    last_name: str,
    birth_date_raw: str,
    first_name: str | None,
    password_stdin: bool,
    must_change_password: bool,
) -> tuple[str, str | None]:
    """Crée un compte déjà vérifié. Retourne `(email, mot_de_passe_genere)` — le second
    élément est `None` quand le mot de passe venait de l'entrée standard (déjà connu de
    l'appelant, inutile de le répéter en sortie)."""
    normalized_email = _parse_email(email)
    birth_date = _parse_birth_date(birth_date_raw)

    if password_stdin:
        password = _read_password_from_stdin()
        generated_password = None
    else:
        password = secrets.token_urlsafe(15)
        generated_password = password

    now = datetime.now(UTC).replace(tzinfo=None)

    async with async_session_factory() as db:
        existing_email = await db.execute(select(User).where(User.email == normalized_email))
        if existing_email.scalar_one_or_none() is not None:
            raise CreateUserError(f"Un compte existe déjà pour {normalized_email}.")
        existing_pseudo = await db.execute(select(User).where(User.pseudo == pseudo))
        if existing_pseudo.scalar_one_or_none() is not None:
            raise CreateUserError(f"Le pseudo {pseudo!r} est déjà utilisé.")

        user = User(
            email=normalized_email,
            password_hash=hash_password(password),
            pseudo=pseudo,
            first_name=first_name,
            last_name=last_name,
            birth_date=birth_date,
            terms_version=CURRENT_TERMS_VERSION,
            terms_accepted_at=now,
            must_change_password=must_change_password,
            email_verified_at=now,
        )
        db.add(user)
        await db.commit()

    return normalized_email, generated_password


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pbm_api.admin")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-user", help="Crée un compte déjà vérifié.")
    create.add_argument("--email", required=True)
    create.add_argument("--pseudo", required=True)
    create.add_argument("--first-name", default=None)
    create.add_argument("--last-name", required=True)
    create.add_argument("--birth-date", required=True, help="AAAA-MM-JJ")
    create.add_argument(
        "--accept-terms",
        action="store_true",
        help=(
            "Obligatoire : consentement porté par l'administrateur "
            "(ou le parent, pour un mineur)."
        ),
    )
    create.add_argument(
        "--password-stdin",
        action="store_true",
        help="Lit le mot de passe sur l'entrée standard au lieu d'en générer un.",
    )
    create.add_argument("--must-change-password", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command != "create-user":
        return 1

    if not args.accept_terms:
        print(
            "Erreur : --accept-terms est obligatoire (case des conditions, "
            "consentement porté par l'administrateur ou le parent).",
            file=sys.stderr,
        )
        return 1

    try:
        email, generated_password = asyncio.run(
            create_user(
                email=args.email,
                pseudo=args.pseudo,
                last_name=args.last_name,
                birth_date_raw=args.birth_date,
                first_name=args.first_name,
                password_stdin=args.password_stdin,
                must_change_password=args.must_change_password,
            )
        )
    except CreateUserError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1

    print(f"Compte créé et vérifié : {email}")
    if generated_password is not None:
        print(f"Mot de passe généré (à transmettre, affiché une seule fois) : {generated_password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
