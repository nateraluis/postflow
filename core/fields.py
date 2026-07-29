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


class EncryptedJSONField(models.TextField):
    """JSON stored as (optionally encrypted) text.

    Used for credential/config blobs. Behaves like a JSONField to Python code
    (dict/list in, dict/list out) but stores an encrypted string when
    FIELD_ENCRYPTION_KEY is set. Not queryable with JSON lookups.
    """

    def get_prep_value(self, value):
        import json

        if value is None:
            return None
        text = value if isinstance(value, str) and value.startswith(PREFIX) else json.dumps(value)
        fernet = _fernet()
        if fernet is None or text.startswith(PREFIX):
            return text
        return f"{PREFIX}{fernet.encrypt(text.encode()).decode()}"

    def from_db_value(self, value, expression, connection):
        import json

        if value in (None, ""):
            return {}
        if value.startswith(PREFIX):
            fernet = _fernet()
            if fernet is None:
                raise RuntimeError(
                    "Encrypted value found but FIELD_ENCRYPTION_KEY is not configured"
                )
            try:
                value = fernet.decrypt(value[len(PREFIX):].encode()).decode()
            except InvalidToken as e:
                raise RuntimeError("Failed to decrypt field value (wrong key?)") from e
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return {}

    def to_python(self, value):
        import json

        if value is None or isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return {}
