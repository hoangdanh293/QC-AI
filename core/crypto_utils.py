"""
Encryption utilities — internal module.
Do not import this directly from UI code.
"""
import hashlib
import base64
from cryptography.fernet import Fernet, InvalidToken

# ── Masks for salt reconstruction (stored here, fragments in separate files) ──
_M1 = b'\x3a\x21\xe7\x8f\x4c\x19\x73\xa2\xbd\x96\x5f'
_M2 = b'\x43\x02\x7e\xd8\x3b\x6c\xf4\x90\x17\xa3\x2e'
_M3 = b'\x84\x5d\x09\xc8\xfe\x41\xb6\x73\x0e\x57'

_RM1 = b'\x91\x43\x6e\x5a\xd7\x82\x0c\xbf\x25\x78\x39'
_RM2 = b'\x14\xac\x2f\xd1\x6e\xfb\x07\x94\xc3\x28\xbe'
_RM3 = b'\x51\xe7\x8a\x42\xc5\x30\xab\x17\xf8\x6d'

_PBKDF2_ITERATIONS = 260_000


def _get_salt() -> bytes:
    from core._ui_defaults import _RENDER_PADDING
    from core._fmt_helpers import _DISPLAY_SCALE
    from core._cache_config import _CACHE_VERSION
    p1 = bytes(a ^ b for a, b in zip(_RENDER_PADDING, _M1))
    p2 = bytes(a ^ b for a, b in zip(_DISPLAY_SCALE, _M2))
    p3 = bytes(a ^ b for a, b in zip(_CACHE_VERSION, _M3))
    return p1 + p2 + p3


def _get_recovery_salt() -> bytes:
    from core._ui_defaults import _GRID_OFFSET
    from core._fmt_helpers import _MARGIN_RATIO
    from core._cache_config import _CACHE_POLICY
    r1 = bytes(a ^ b for a, b in zip(_GRID_OFFSET, _RM1))
    r2 = bytes(a ^ b for a, b in zip(_MARGIN_RATIO, _RM2))
    r3 = bytes(a ^ b for a, b in zip(_CACHE_POLICY, _RM3))
    return r1 + r2 + r3


def derive_fernet_key(password: str) -> Fernet:
    """Derive a Fernet key from master password via PBKDF2-HMAC-SHA256."""
    salt = _get_salt()
    raw = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=32
    )
    return Fernet(base64.urlsafe_b64encode(raw))


def derive_recovery_fernet(recovery_passphrase: str) -> Fernet:
    """Derive a Fernet key from recovery passphrase via PBKDF2-HMAC-SHA256."""
    salt = _get_recovery_salt()
    raw = hashlib.pbkdf2_hmac(
        'sha256',
        recovery_passphrase.encode('utf-8'),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=32
    )
    return Fernet(base64.urlsafe_b64encode(raw))


_ENC_PREFIX = "enc:"


def encrypt_value(fernet: Fernet, plaintext: str) -> str:
    """Encrypt a plaintext string. Returns prefixed ciphertext string."""
    token = fernet.encrypt(plaintext.encode('utf-8'))
    return _ENC_PREFIX + token.decode('utf-8')


def decrypt_value(fernet: Fernet, ciphertext: str) -> str | None:
    """Decrypt a ciphertext string. Returns plaintext or None on failure."""
    try:
        if not ciphertext.startswith(_ENC_PREFIX):
            return ciphertext  # already plaintext (migration path)
        token = ciphertext[len(_ENC_PREFIX):].encode('utf-8')
        return fernet.decrypt(token).decode('utf-8')
    except (InvalidToken, Exception):
        return None


def is_encrypted(value: str) -> bool:
    return isinstance(value, str) and value.startswith(_ENC_PREFIX)
