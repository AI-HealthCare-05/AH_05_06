import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet


class PatientSecretCodec:
    def __init__(self, secret_key: str) -> None:
        self._key = secret_key.encode()
        fernet_key = base64.urlsafe_b64encode(hashlib.sha256(self._key).digest())
        self._fernet = Fernet(fernet_key)

    @staticmethod
    def random_token(size: int = 32) -> str:
        return secrets.token_urlsafe(size)

    @staticmethod
    def otp() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    def digest(self, value: str) -> str:
        return hmac.new(self._key, value.encode(), hashlib.sha256).hexdigest()

    def matches(self, value: str, digest: str) -> bool:
        return hmac.compare_digest(self.digest(value), digest)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode()).decode()
