import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # Argon2id with library defaults (OWASP-aligned)

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        # Still spend the time so response timing doesn't reveal unknown users.
        _hasher.hash(password)
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"at least {MIN_PASSWORD_LENGTH} characters")
    if password.lower() == password or password.upper() == password:
        problems.append("mix of upper and lower case")
    if not any(c.isdigit() for c in password):
        problems.append("at least one digit")
    return problems
