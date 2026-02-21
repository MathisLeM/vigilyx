"""
Fernet-based symmetric encryption helpers for Stripe API keys.

The server holds a single FERNET_KEY in .env.  Every Stripe key is
encrypted before it is written to the database, and decrypted on the
fly when it is needed for API calls.

Usage
-----
    from app.services.crypto import encrypt_key, decrypt_key

    ciphertext = encrypt_key("sk_live_...")   # store this in the DB
    plaintext  = decrypt_key(ciphertext)       # use this for Stripe calls
"""

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet() -> Fernet:
    key = settings.FERNET_KEY
    if not key:
        raise RuntimeError(
            "FERNET_KEY is not set.  "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
            "and add it to your .env file."
        )
    return Fernet(key.encode())


def encrypt_key(plaintext: str) -> str:
    """Encrypt a Stripe API key and return a URL-safe base64 ciphertext string."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_key(ciphertext: str) -> str:
    """
    Decrypt a previously encrypted Stripe API key.

    Raises
    ------
    cryptography.fernet.InvalidToken
        If the ciphertext is corrupted or the FERNET_KEY has changed.
    """
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise InvalidToken(
            "Failed to decrypt Stripe API key — the FERNET_KEY may have changed "
            "or the stored value is corrupted."
        )
