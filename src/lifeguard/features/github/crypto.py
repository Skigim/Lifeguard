from cryptography.fernet import Fernet, InvalidToken

from lifeguard.config import ConfigError

__all__ = ["TokenCipher", "InvalidToken"]


class TokenCipher:
    def __init__(self, key):
        try:
            self.fernet = Fernet(key.encode())
        except (ValueError, TypeError) as exc:
            raise ConfigError("TOKEN_ENCRYPTION_KEY must be a Fernet key") from exc

    def encrypt(self, value):
        return self.fernet.encrypt(value.encode()).decode() if value else None

    def decrypt(self, value):
        return self.fernet.decrypt(value.encode()).decode() if value else None
