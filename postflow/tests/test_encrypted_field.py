import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from core.fields import PREFIX, EncryptedTextField

KEY = Fernet.generate_key().decode()


class TestEncryptedTextField:
    def test_roundtrip_with_key(self):
        field = EncryptedTextField()
        with override_settings(FIELD_ENCRYPTION_KEY=KEY):
            stored = field.get_prep_value("secret-token")
            assert stored.startswith(PREFIX)
            assert "secret-token" not in stored
            assert field.from_db_value(stored, None, None) == "secret-token"

    def test_plaintext_passthrough_without_key(self):
        field = EncryptedTextField()
        with override_settings(FIELD_ENCRYPTION_KEY=""):
            assert field.get_prep_value("secret-token") == "secret-token"
            assert field.from_db_value("secret-token", None, None) == "secret-token"

    def test_legacy_plaintext_rows_still_readable_with_key(self):
        field = EncryptedTextField()
        with override_settings(FIELD_ENCRYPTION_KEY=KEY):
            assert field.from_db_value("legacy-plaintext", None, None) == "legacy-plaintext"

    def test_already_encrypted_value_not_double_encrypted(self):
        field = EncryptedTextField()
        with override_settings(FIELD_ENCRYPTION_KEY=KEY):
            stored = field.get_prep_value("secret")
            assert field.get_prep_value(stored) == stored

    def test_wrong_key_raises(self):
        field = EncryptedTextField()
        with override_settings(FIELD_ENCRYPTION_KEY=KEY):
            stored = field.get_prep_value("secret")
        with override_settings(FIELD_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            with pytest.raises(RuntimeError):
                field.from_db_value(stored, None, None)

    def test_empty_values(self):
        field = EncryptedTextField()
        with override_settings(FIELD_ENCRYPTION_KEY=KEY):
            assert field.get_prep_value("") == ""
            assert field.from_db_value("", None, None) == ""
