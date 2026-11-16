"""
API Key & Model Configuration Manager.
Supports transparent encryption/decryption via an active session DEK.
"""
import json
import os
import datetime
import uuid
from cryptography.fernet import Fernet
from core.crypto_utils import encrypt_value, decrypt_value, is_encrypted

API_KEY_FILE    = "api_key.json"
MODEL_CONFIG_FILE = "model_config.json"

DEFAULT_MODELS = {
    "Google API": [
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-pro-preview",
        "gemini-3.1-pro",
        "gemini-3.1-flash-lite",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemma-4-31b-it",
        "gemma-4-26b-a4b-it"
    ],
    "OpenAI":     ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
}

# ── Session DEK singleton (set once when user logs in) ──
_session_dek: bytes | None = None


def set_session_dek(dek_raw: bytes):
    """Called by UI after successful login to activate encryption."""
    global _session_dek
    _session_dek = dek_raw


def clear_session_dek():
    """Clear the session DEK on logout."""
    global _session_dek
    _session_dek = None


def _get_static_fernet() -> Fernet:
    from core.crypto_utils import derive_fernet_key
    return derive_fernet_key("QC_AI_CPC1HN_STATIC_DEK_SECRET_KEY")


def _get_fernet() -> Fernet | None:
    # Luôn sử dụng static key để mã hóa/giải mã API keys trên đĩa.
    # Nhờ vậy hệ thống có thể tự động giải mã khóa để gọi AI mà không cần đăng nhập trước.
    return _get_static_fernet()



# ══════════════════════════════════════════════
#  Model Config
# ══════════════════════════════════════════════

def load_model_config() -> dict:
    if not os.path.exists(MODEL_CONFIG_FILE):
        save_model_config(DEFAULT_MODELS)
        return DEFAULT_MODELS
    with open(MODEL_CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_model_config(data: dict):
    with open(MODEL_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# ══════════════════════════════════════════════
#  API Key I/O  (with transparent encryption)
# ══════════════════════════════════════════════

def _init_api_key_data() -> dict:
    return {
        "last_cleared_month": datetime.date.today().strftime("%Y-%m"),
        "keys": []
    }


def load_api_keys(fernet: Fernet | None = None) -> dict:
    """
    Load API keys from disk.
    If a Fernet key is provided (or a session DEK is active),
    key_string values are decrypted before returning.
    """
    f = fernet or _get_fernet()

    if not os.path.exists(API_KEY_FILE):
        data = _init_api_key_data()
        save_api_keys(data, fernet=f)
        return data

    with open(API_KEY_FILE, 'r', encoding='utf-8') as fp:
        try:
            data = json.load(fp)
        except json.JSONDecodeError:
            data = _init_api_key_data()

    # Ghi lại tháng hiện tại nếu chưa có (không tự động xóa keys)
    current_month = datetime.date.today().strftime("%Y-%m")
    if data.get("last_cleared_month") != current_month:
        data["last_cleared_month"] = current_month
        # Lưu ý: KHÔNG xóa keys khi đổi tháng (đã tắt tính năng auto-clear)

    # Decrypt key_string values in memory (never write back here)
    if f is not None:
        for item in data.get("keys", []):
            if is_encrypted(item.get("key_string", "")):
                decrypted = decrypt_value(f, item["key_string"])
                item["key_string"] = decrypted if decrypted else "[GIẢI MÃ THẤT BẠI]"

    return data


def save_api_keys(data: dict, fernet: Fernet | None = None):
    """
    Save API keys to disk.
    If a Fernet key is provided (or a session DEK is active),
    key_string values are encrypted before writing.
    """
    f = fernet or _get_fernet()

    # Work on a deep copy so we don't mutate in-memory data
    import copy
    data_to_write = copy.deepcopy(data)

    if f is not None:
        for item in data_to_write.get("keys", []):
            ks = item.get("key_string", "")
            if ks and not is_encrypted(ks) and ks != "[GIẢI MÃ THẤT BẠI]":
                item["key_string"] = encrypt_value(f, ks)

    with open(API_KEY_FILE, 'w', encoding='utf-8') as fp:
        json.dump(data_to_write, fp, ensure_ascii=False, indent=4)


def get_active_keys(provider: str, model: str, fernet: Fernet | None = None) -> list[str]:
    """
    Return a list of decrypted, active key strings matching provider + model.
    Works with the session DEK if set; otherwise attempts plaintext fallback.
    """
    f = fernet or _get_fernet()
    data = load_api_keys(fernet=f)

    active = []
    for item in data.get("keys", []):
        if (item.get("provider") == provider
                and item.get("model") == model
                and item.get("is_active") is True):
            ks = item.get("key_string", "")
            if ks and ks != "[GIẢI MÃ THẤT BẠI]" and not is_encrypted(ks):
                active.append(ks)
    return active


def migrate_keys_to_static_dek(user_dek: bytes):
    """
    Di chuyển các API key từ mã hóa bằng user_dek sang static_dek.
    Hàm này được gọi một lần khi người dùng đăng nhập thành công.
    """
    user_fernet = Fernet(user_dek)
    
    if os.path.exists(API_KEY_FILE):
        with open(API_KEY_FILE, 'r', encoding='utf-8') as fp:
            try:
                data = json.load(fp)
            except Exception:
                return
        
        # Giải mã bằng user key cũ
        for item in data.get("keys", []):
            ks = item.get("key_string", "")
            if ks and ks.startswith("enc:"):
                try:
                    dec = decrypt_value(user_fernet, ks)
                    if dec:
                        item["key_string"] = dec
                except Exception:
                    pass
        
        # Lưu lại tự động mã hóa bằng static key mới
        save_api_keys(data)