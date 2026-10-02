"""Schémas Pydantic des routes d'authentification — entrées et réponses."""

from datetime import date

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Corps de l'inscription libre : identité, mot de passe et acceptation des CGU."""

    email: EmailStr
    password: str
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    birth_date: date
    accept_terms: bool


class LoginRequest(BaseModel):
    """Corps de la connexion : e-mail et mot de passe en clair (jamais journalisés)."""

    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    """Corps de la validation d'adresse : le jeton opaque reçu par e-mail."""

    token: str


class ForgotPasswordRequest(BaseModel):
    """Corps de la demande de réinitialisation : l'e-mail du compte, sans confirmer qu'il existe."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Corps de la réinitialisation : le jeton reçu par e-mail et le nouveau mot de passe."""

    token: str
    password: str


class MessageResponse(BaseModel):
    """Réponse générique à message unique, utilisée quand l'issue ne doit rien révéler."""

    message: str


class UserResponse(BaseModel):
    """Vue publique de l'utilisateur connecté — jamais de mot de passe ni de clé IA."""

    id: str
    email: str
    email_verified: bool
    must_change_password: bool
