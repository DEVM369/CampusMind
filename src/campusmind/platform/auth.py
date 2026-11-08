from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from campusmind.config import get_settings
from campusmind.platform.db import (
    AuthSession,
    Role,
    User,
    UserRole,
)


_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SALT_BYTES = 16


class AuthenticationError(RuntimeError):
    """Authentication failed without disclosing which credential was wrong."""


def _b64encode(value: bytes) -> str:
    return (
        base64.urlsafe_b64encode(value)
        .decode("ascii")
        .rstrip("=")
    )


def _b64decode(value: str) -> bytes:
    padding = "=" * (
        (-len(value)) % 4
    )

    return base64.urlsafe_b64decode(
        value + padding
    )


def hash_password(password: str) -> str:
    value = str(password)

    if not value:
        raise ValueError(
            "password must not be empty"
        )

    salt = secrets.token_bytes(
        _SALT_BYTES
    )

    derived = hashlib.scrypt(
        value.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )

    return (
        "scrypt"
        f"$n={_SCRYPT_N}"
        f"$r={_SCRYPT_R}"
        f"$p={_SCRYPT_P}"
        f"${_b64encode(salt)}"
        f"${_b64encode(derived)}"
    )


def verify_password(
    password: str,
    encoded: str | None,
) -> bool:
    if not encoded:
        return False

    try:
        (
            algorithm,
            n_part,
            r_part,
            p_part,
            salt_text,
            digest_text,
        ) = encoded.split(
            "$",
            5,
        )

        if algorithm != "scrypt":
            return False

        n = int(
            n_part.split(
                "=",
                1,
            )[1]
        )

        r = int(
            r_part.split(
                "=",
                1,
            )[1]
        )

        p = int(
            p_part.split(
                "=",
                1,
            )[1]
        )

        # Keep verification cost bounded to the format
        # currently issued by CampusMind.
        if (
            n != _SCRYPT_N
            or r != _SCRYPT_R
            or p != _SCRYPT_P
        ):
            return False

        salt = _b64decode(
            salt_text
        )

        expected = _b64decode(
            digest_text
        )

        actual = hashlib.scrypt(
            str(password).encode(
                "utf-8"
            ),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )

        return hmac.compare_digest(
            actual,
            expected,
        )

    except (
        ValueError,
        TypeError,
        IndexError,
    ):
        return False


def session_token_hash(
    token: str,
) -> str:
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


# Used only to keep missing-user login work comparable
# to a normal password verification.
_DUMMY_PASSWORD_HASH = hash_password(
    "CampusMind-invalid-login-placeholder"
)


class AuthService:
    def __init__(
        self,
        session: Session,
    ) -> None:
        self.session = session

    def authenticate(
        self,
        username: str,
        password: str,
    ) -> User:
        normalized = (
            str(username)
            .strip()
        )

        user = self.session.scalar(
            select(User).where(
                User.username
                == normalized
            )
        )

        if user is None:
            verify_password(
                password,
                _DUMMY_PASSWORD_HASH,
            )

            raise AuthenticationError(
                "invalid username or password"
            )

        if (
            user.status
            != "active"
        ):
            verify_password(
                password,
                user.password_hash
                or _DUMMY_PASSWORD_HASH,
            )

            raise AuthenticationError(
                "invalid username or password"
            )

        if not verify_password(
            password,
            user.password_hash,
        ):
            raise AuthenticationError(
                "invalid username or password"
            )

        return user

    def create_session(
        self,
        user_id: uuid.UUID,
    ) -> tuple[str, AuthSession]:
        settings = get_settings()

        raw_token = secrets.token_urlsafe(
            48
        )

        now = datetime.now(
            timezone.utc
        )

        row = AuthSession(
            user_id=user_id,
            token_hash=session_token_hash(
                raw_token
            ),
            expires_at=(
                now
                + timedelta(
                    hours=settings.auth_session_ttl_hours
                )
            ),
            revoked_at=None,
        )

        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)

        return raw_token, row

    def resolve_session(
        self,
        raw_token: str | None,
    ) -> User | None:
        token = (
            str(raw_token or "")
            .strip()
        )

        if not token:
            return None

        now = datetime.now(
            timezone.utc
        )

        row = self.session.scalar(
            select(AuthSession).where(
                AuthSession.token_hash
                == session_token_hash(
                    token
                ),
                AuthSession.revoked_at
                .is_(
                    None
                ),
                AuthSession.expires_at
                > now,
            )
        )

        if row is None:
            return None

        user = self.session.get(
            User,
            row.user_id,
        )

        if (
            user is None
            or user.status
            != "active"
        ):
            return None

        return user

    def revoke_session(
        self,
        raw_token: str | None,
    ) -> bool:
        token = (
            str(raw_token or "")
            .strip()
        )

        if not token:
            return False

        row = self.session.scalar(
            select(AuthSession).where(
                AuthSession.token_hash
                == session_token_hash(
                    token
                ),
                AuthSession.revoked_at
                .is_(
                    None
                ),
            )
        )

        if row is None:
            return False

        row.revoked_at = datetime.now(
            timezone.utc
        )

        self.session.commit()

        return True

    def role_codes(
        self,
        user_id: uuid.UUID,
    ) -> list[str]:
        rows = self.session.scalars(
            select(Role.code)
            .join(
                UserRole,
                UserRole.role_id
                == Role.id,
            )
            .where(
                UserRole.user_id
                == user_id
            )
            .order_by(
                Role.code.asc()
            )
        ).all()

        return [
            str(value)
            for value in rows
        ]
