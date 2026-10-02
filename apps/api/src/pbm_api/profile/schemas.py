"""Schémas Pydantic des requêtes/réponses de la page profil (validation d'entrée, forme de
sortie).
"""
import re
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

PSEUDO_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class UpdateProfileRequest(BaseModel):
    """Requête de mise à jour d'identité : pseudo, nom, prénom, date de naissance."""

    pseudo: str = Field(min_length=3, max_length=32)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    birth_date: date

    @field_validator("pseudo")
    @classmethod
    def _validate_pseudo(cls, value: str) -> str:
        if not PSEUDO_PATTERN.match(value):
            raise ValueError("Le pseudo n'accepte que lettres, chiffres, tirets et underscores.")
        return value


class ProfileResponse(BaseModel):
    """Profil complet renvoyé au front : identité, état de l'e-mail, accès au jeu."""

    id: str
    email: str
    email_verified: bool
    pending_email: str | None
    pseudo: str | None
    has_avatar: bool
    first_name: str | None
    last_name: str
    birth_date: date
    # Droit d'accès au jeu (D11, lot `j-file-attente`) : posé hors ligne par l'administration.
    # Exposé ici — et nulle part ailleurs — pour que le front décide s'il montre l'entrée « Jouer »
    # (navigation, salon). Le serveur reste l'autorité : chaque route du jeu répond déjà 404 à un
    # compte sans ce droit (`require_game_access`). Ce booléen n'ouvre aucun accès, il évite
    # seulement d'afficher une porte qui mène à un 404 (lot `j-salon-partie`, critère 5).
    game_access: bool


class ChangeEmailRequest(BaseModel):
    """Requête de changement d'adresse e-mail (déclenche un e-mail de confirmation)."""

    email: EmailStr


class ConfirmEmailChangeRequest(BaseModel):
    """Jeton reçu par e-mail pour confirmer le changement d'adresse."""

    token: str


class ChangePasswordRequest(BaseModel):
    """Requête de changement de mot de passe : exige l'ancien pour vérification."""

    current_password: str
    new_password: str


class DeleteAccountRequest(BaseModel):
    """Requête de suppression de compte : le mot de passe reconfirme l'intention."""

    password: str


class MessageResponse(BaseModel):
    """Réponse générique à message unique (confirmation sans autre donnée)."""

    message: str


class SessionResponse(BaseModel):
    """Session active exposée au front, pour que l'utilisateur révoque les autres."""

    id: str
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    current: bool
