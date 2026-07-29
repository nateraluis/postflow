"""Encrypted-at-rest text field for credentials.

Values are encrypted with Fernet using settings.FIELD_ENCRYPTION_KEY and
prefix-tagged so plaintext rows written before the migration are still
readable (and get encrypted on their next save).
"""
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

PREFIX = "enc:v1:"


def _fernet():
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
    if not key:
        return None
    return Fernet(key.encode() if isinstance(key, str) else key)


class EncryptedTextField(models.TextField):
    """TextField that transparently encrypts values when FIELD_ENCRYPTION_KEY is set.

    Without a key configured it behaves as a plain TextField, so local
    development works without extra setup.
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ""):
            return value
        fernet = _fernet()
        if fernet is None or str(value).startswith(PREFIX):
            return value
        token = fernet.encrypt(str(value).encode()).decode()
        return f"{PREFIX}{token}"

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        if not value.startswith(PREFIX):
            return value  # legacy plaintext row
        fernet = _fernet()
        if fernet is None:
            raise RuntimeError(
                "Encrypted value found but FIELD_ENCRYPTION_KEY is not configured"
            )
        try:
            return fernet.decrypt(value[len(PREFIX):].encode()).decode()
        except InvalidToken as e:
            raise RuntimeError("Failed to decrypt field value (wrong key?)") from e

    def to_python(self, value):
        return value
