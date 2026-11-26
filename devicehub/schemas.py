"""Corpi JSON dell'API di gestione utenti.

La password viaggia nel body, mai nella query string: gli URL finiscono nei log
del server, nella cronologia dei browser e nei proxy, il body no.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# Unica fonte dei ruoli: il pattern del modello nasce da qui.
ROLES = ("admin", "manager", "soc", "viewer")
ROLE_PATTERN = "^(" + "|".join(ROLES) + ")$"


class UserCreateRequest(BaseModel):
    """Nuovo utente/cliente creato da un amministratore."""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=10, description="almeno 10 caratteri")
    role: str = Field(..., pattern=ROLE_PATTERN, description=", ".join(ROLES))
    tenant: str | None = Field(
        default=None, min_length=1, max_length=80, description="cliente, facoltativo"
    )
    full_name: str | None = Field(default=None, max_length=120)


class PasswordResetRequest(BaseModel):
    """Nuova password scelta dall'amministratore per un altro utente."""

    password: str = Field(..., min_length=10, description="almeno 10 caratteri")
