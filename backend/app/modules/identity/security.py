import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
# Same expensive verification for unknown usernames, without a usable default credential.
_dummy_hash = password_hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str | None) -> bool:
    try:
        return password_hasher.verify(encoded or _dummy_hash, password) and encoded is not None
    except (VerificationError, InvalidHashError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token: str) -> str:
    return hmac.new(token.encode(), b"element29:csrf:v1", hashlib.sha256).hexdigest()
