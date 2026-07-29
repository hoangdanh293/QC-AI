"""
Authentication & Recovery Manager
Handles master password, TOTP 2FA setup/verify (multi-account), and recovery flows.

Multi-TOTP schema (v2):
  ui_cache.dat → {
    "v": 2,
    "ph": "<bcrypt hash>",
    "dk": "<DEK enc by password>",
    "ta": [                           ← TOTP Accounts list (encrypted)
        {"label": "QC AI CPC1HN", "ts": "<secret enc by DEK>"},
        {"label": "TK Thu 2",     "ts": "<secret enc by DEK>"},
        ...
    ]
  }

  Legacy v1 files (single "ts" field) are migrated transparently on first load.
"""
import os
import io
import json
import datetime
import pyotp
import qrcode
import bcrypt
from cryptography.fernet import Fernet
from core.crypto_utils import (
    derive_fernet_key, derive_recovery_fernet,
    encrypt_value, decrypt_value
)

# ── File paths (names intentionally non-descriptive) ──
_SECURITY_FILE  = "ui_cache.dat"
_RECOVERY_FILE  = "render_state.dat"
_APP_NAME       = "QC AI CPC1HN"

# ── JSON field keys ──
_F_VER  = "v"
_F_PH   = "ph"    # password bcrypt hash
_F_DK   = "dk"    # DEK encrypted by master password Fernet
_F_TA   = "ta"    # TOTP Accounts: list of {"label": str, "ts": str (enc secret)}
_F_TS   = "ts"    # (legacy v1) single TOTP secret
_F_RD   = "rd"    # DEK encrypted by recovery Fernet


# ══════════════════════════════════════════════
#  Internal I/O helpers
# ══════════════════════════════════════════════

def _load_sec() -> dict:
    with open(_SECURITY_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save_sec(data: dict):
    with open(_SECURITY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)

def _load_rec() -> dict:
    if not os.path.exists(_RECOVERY_FILE):
        return {}
    with open(_RECOVERY_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save_rec(data: dict):
    with open(_RECOVERY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def _migrate_v1_to_v2(sec: dict, dek_fernet: Fernet) -> dict:
    """
    Migrate a v1 security file (single 'ts' field) to v2 (list 'ta').
    Returns the updated dict (caller should _save_sec() it).
    """
    if sec.get(_F_VER, 1) == 1 and _F_TS in sec and _F_TA not in sec:
        sec[_F_VER] = 2
        sec[_F_TA]  = [{"label": _APP_NAME, "ts": sec.pop(_F_TS)}]
    return sec


def _get_totp_accounts(sec: dict, dek_fernet: Fernet) -> list[dict]:
    """
    Return list of {"label": str, "secret": str} decrypted from sec["ta"].
    Handles both v1 (single ts) and v2 (ta list) formats.
    """
    accounts = []
    for acc in sec.get(_F_TA, []):
        secret = decrypt_value(dek_fernet, acc["ts"])
        if secret:
            accounts.append({"label": acc["label"], "secret": secret})
    return accounts


# ══════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════

def is_first_run() -> bool:
    """True if security has not been configured yet."""
    return not os.path.exists(_SECURITY_FILE)


def generate_totp_setup(label: str = "QC AI") -> tuple[str, bytes]:
    """
    Generate a new TOTP secret and QR code image.
    Returns (totp_secret_base32, qr_png_bytes).
    """
    secret = pyotp.random_base32()
    totp   = pyotp.TOTP(secret)
    uri    = totp.provisioning_uri(name=label, issuer_name=_APP_NAME)
    img    = qrcode.make(uri)
    buf    = io.BytesIO()
    img.save(buf, format="PNG")  # type: ignore
    buf.seek(0)
    return secret, buf.getvalue()


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code against a secret."""
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def verify_totp_any(dek_raw: bytes, code: str) -> bool:
    """
    Verify a 6-digit TOTP code against ANY registered TOTP account.
    Returns True if at least one account matches.
    """
    try:
        sec = _load_sec()
        # Auto-migrate v1 if needed
        if sec.get(_F_VER, 1) == 1 and _F_TS in sec:
            dek_fernet = Fernet(dek_raw)
            sec = _migrate_v1_to_v2(sec, dek_fernet)
            _save_sec(sec)

        dek_fernet = Fernet(dek_raw)
        accounts = _get_totp_accounts(sec, dek_fernet)
        return any(verify_totp(acc["secret"], code) for acc in accounts)
    except Exception:
        return False


def get_totp_account_labels(dek_raw: bytes) -> list[str]:
    """Return list of registered TOTP account labels."""
    try:
        sec = _load_sec()
        dek_fernet = Fernet(dek_raw)
        return [acc["label"] for acc in sec.get(_F_TA, [])]
    except Exception:
        return []


def add_totp_account(dek_raw: bytes, label: str, new_secret: str, verify_code: str) -> bool:
    """
    Add a new TOTP account after verifying the TOTP code.
    Returns True on success, False if TOTP code is wrong or label already exists.
    """
    if not verify_totp(new_secret, verify_code):
        return False
    try:
        sec = _load_sec()
        dek_fernet = Fernet(dek_raw)

        # Migrate v1 if needed
        sec = _migrate_v1_to_v2(sec, dek_fernet)

        # Check for duplicate label
        existing_labels = [acc["label"] for acc in sec.get(_F_TA, [])]
        if label.strip() in existing_labels:
            return False  # label already exists

        enc_secret = encrypt_value(dek_fernet, new_secret)
        sec.setdefault(_F_TA, []).append({"label": label.strip(), "ts": enc_secret})
        sec[_F_VER] = 2
        _save_sec(sec)
        return True
    except Exception:
        return False


def remove_totp_account(dek_raw: bytes, label: str) -> bool:
    """
    Remove a TOTP account by label.
    Cannot remove if it's the last account (would lock out).
    Returns True on success.
    """
    try:
        sec = _load_sec()
        dek_fernet = Fernet(dek_raw)
        sec = _migrate_v1_to_v2(sec, dek_fernet)

        accounts = sec.get(_F_TA, [])
        if len(accounts) <= 1:
            return False  # Cannot remove the only account

        new_accounts = [acc for acc in accounts if acc["label"] != label]
        if len(new_accounts) == len(accounts):
            return False  # Label not found

        sec[_F_TA] = new_accounts
        _save_sec(sec)
        return True
    except Exception:
        return False


def rename_totp_account(dek_raw: bytes, old_label: str, new_label: str) -> bool:
    """Rename a TOTP account label."""
    try:
        sec = _load_sec()
        dek_fernet = Fernet(dek_raw)
        sec = _migrate_v1_to_v2(sec, dek_fernet)

        accounts = sec.get(_F_TA, [])
        # Prevent duplicate
        existing = [acc["label"] for acc in accounts]
        if new_label.strip() in existing and new_label.strip() != old_label:
            return False

        changed = False
        for acc in accounts:
            if acc["label"] == old_label:
                acc["label"] = new_label.strip()
                changed = True
                break

        if changed:
            _save_sec(sec)
        return changed
    except Exception:
        return False


def setup_security(
    password: str,
    totp_secret: str,
    totp_code: str,
    recovery_passphrase: str,
    totp_label: str = ""
) -> bool:
    """
    First-time security setup.
    Returns True on success, False if TOTP verification fails.
    """
    if not verify_totp(totp_secret, totp_code):
        return False

    label = totp_label.strip() if totp_label.strip() else _APP_NAME

    # 1. Generate a random Data Encryption Key (DEK)
    dek_raw: bytes = Fernet.generate_key()

    # 2. Hash master password
    pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')

    # 3. Encrypt DEK with password-derived Fernet
    pw_fernet  = derive_fernet_key(password)
    dek_enc_pw = encrypt_value(pw_fernet, dek_raw.decode('utf-8'))

    # 4. Encrypt TOTP secret with DEK Fernet (v2 list format)
    dek_fernet = Fernet(dek_raw)
    totp_enc   = encrypt_value(dek_fernet, totp_secret)

    # 5. Save security file (v2 format)
    _save_sec({
        _F_VER: 2,
        _F_PH:  pw_hash,
        _F_DK:  dek_enc_pw,
        _F_TA:  [{"label": label, "ts": totp_enc}],
    })

    # 6. Encrypt DEK with recovery-passphrase-derived Fernet → save separately
    rec_fernet  = derive_recovery_fernet(recovery_passphrase)
    dek_enc_rec = encrypt_value(rec_fernet, dek_raw.decode('utf-8'))
    _save_rec({_F_VER: 1, _F_RD: dek_enc_rec})

    # 7. Auto-migrate existing plaintext API keys
    _migrate_existing_keys(dek_fernet)

    return True


def verify_login(password: str, totp_code: str) -> bytes | None:
    """
    Verify master password + TOTP (any registered account).
    Returns raw DEK bytes on success, None on failure.
    """
    try:
        sec = _load_sec()

        # Check password
        if not bcrypt.checkpw(password.encode('utf-8'), sec[_F_PH].encode('utf-8')):
            return None

        # Decrypt DEK using password
        pw_fernet = derive_fernet_key(password)
        dek_str   = decrypt_value(pw_fernet, sec[_F_DK])
        if dek_str is None:
            return None

        dek_raw    = dek_str.encode('utf-8')
        dek_fernet = Fernet(dek_raw)

        # Auto-migrate v1 → v2 on first login
        if sec.get(_F_VER, 1) == 1 and _F_TS in sec:
            sec = _migrate_v1_to_v2(sec, dek_fernet)
            _save_sec(sec)

        # Verify code against any registered account
        accounts = _get_totp_accounts(sec, dek_fernet)
        if not any(verify_totp(acc["secret"], totp_code) for acc in accounts):
            return None

        return dek_raw

    except Exception:
        return None


def recover_with_passphrase(recovery_passphrase: str) -> bytes | None:
    """
    Attempt to recover DEK using recovery passphrase.
    Returns raw DEK bytes on success, None on failure.
    """
    try:
        rec        = _load_rec()
        rec_fernet = derive_recovery_fernet(recovery_passphrase)
        dek_str    = decrypt_value(rec_fernet, rec[_F_RD])
        if dek_str is None:
            return None
        return dek_str.encode('utf-8')
    except Exception:
        return None


def reset_password_with_dek(
    dek_raw: bytes,
    new_password: str,
    new_totp_secret: str,
    new_totp_code: str,
    new_recovery_passphrase: str,
    new_totp_label: str = ""
) -> bool:
    """
    Reset master password and TOTP using an already-recovered DEK.
    Replaces ALL TOTP accounts with the new single account.
    Called after successful recover_with_passphrase().
    """
    if not verify_totp(new_totp_secret, new_totp_code):
        return False

    label = new_totp_label.strip() if new_totp_label.strip() else _APP_NAME
    dek_fernet = Fernet(dek_raw)

    new_pw_hash   = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')
    new_pw_fernet = derive_fernet_key(new_password)
    new_dek_enc   = encrypt_value(new_pw_fernet, dek_raw.decode('utf-8'))
    new_totp_enc  = encrypt_value(dek_fernet, new_totp_secret)

    _save_sec({
        _F_VER: 2,
        _F_PH:  new_pw_hash,
        _F_DK:  new_dek_enc,
        _F_TA:  [{"label": label, "ts": new_totp_enc}],
    })

    new_rec_fernet  = derive_recovery_fernet(new_recovery_passphrase)
    new_dek_enc_rec = encrypt_value(new_rec_fernet, dek_raw.decode('utf-8'))
    _save_rec({_F_VER: 1, _F_RD: new_dek_enc_rec})

    return True


def reset_totp_with_password(password: str, new_totp_secret: str, new_totp_code: str,
                              new_label: str = "") -> bool:
    """
    Replace the primary TOTP (user still knows password but lost their phone).
    Replaces ALL existing TOTP accounts with the new one.
    """
    try:
        if not verify_totp(new_totp_secret, new_totp_code):
            return False

        sec = _load_sec()
        if not bcrypt.checkpw(password.encode('utf-8'), sec[_F_PH].encode('utf-8')):
            return False

        pw_fernet = derive_fernet_key(password)
        dek_str   = decrypt_value(pw_fernet, sec[_F_DK])
        if dek_str is None:
            return False

        label      = new_label.strip() if new_label.strip() else _APP_NAME
        dek_fernet = Fernet(dek_str.encode('utf-8'))
        new_totp_enc = encrypt_value(dek_fernet, new_totp_secret)

        sec[_F_VER] = 2
        sec[_F_TA]  = [{"label": label, "ts": new_totp_enc}]
        sec.pop(_F_TS, None)  # remove legacy field if present
        _save_sec(sec)
        return True
    except Exception:
        return False


def export_recovery_pdf(recovery_passphrase: str = "", owner: str = "") -> bytes:
    """
    Generate a PDF recovery card as bytes (for st.download_button).
    Auto-fills recovery_passphrase and creation date.
    Uses Arial font for Vietnamese support.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    # Register Arial for Vietnamese characters
    arial_path = r"C:\Windows\Fonts\arial.ttf"
    if os.path.exists(arial_path):
        pdfmetrics.registerFont(TTFont('Arial', arial_path))
        pdfmetrics.registerFont(TTFont('Arial-Bold', r"C:\Windows\Fonts\arialbd.ttf"))
        font_name = 'Arial'
        font_name_bold = 'Arial-Bold'
    else:
        font_name = 'Helvetica'
        font_name_bold = 'Helvetica-Bold'

    buf     = io.BytesIO()
    doc     = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )
    styles  = getSampleStyleSheet()
    story   = []

    # ── Title ──
    title_style = ParagraphStyle(
        'Title', parent=styles['Title'], fontName=font_name_bold,
        fontSize=20, textColor=colors.HexColor('#0071e3'),
        spaceAfter=6, alignment=TA_CENTER
    )
    story.append(Paragraph("QC AI CPC1HN — The Khoi Phuc Bao Mat", title_style))
    story.append(Paragraph(
        f"Ngay tao: {datetime.date.today().strftime('%d/%m/%Y')}",
        ParagraphStyle('sub', parent=styles['Normal'], fontName=font_name, fontSize=10,
                       textColor=colors.grey, alignment=TA_CENTER)
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#0071e3'), spaceAfter=16))

    # ── Warning ──
    warn_style = ParagraphStyle(
        'Warn', parent=styles['Normal'], fontName=font_name,
        fontSize=10, textColor=colors.HexColor('#ff3b30'),
        backColor=colors.HexColor('#fff5f5'),
        borderPadding=8, leading=16
    )
    story.append(Paragraph(
        "<b>BAO MAT TOI CAO</b> — Luu tai lieu nay o noi an toan. "
        "Khong chup anh, khong gui email. Tot nhat hay in ra va cat vao ngan keo.",
        warn_style
    ))
    story.append(Spacer(1, 0.5*cm))

    # ── Instructions ──
    h2_style = ParagraphStyle('H2', parent=styles['Heading2'], fontName=font_name_bold, fontSize=13,
                               textColor=colors.HexColor('#1d1d1f'), spaceAfter=4)
    body_style = ParagraphStyle('Body', parent=styles['Normal'], fontName=font_name, fontSize=10, leading=16)

    story.append(Paragraph("HUONG DAN KHOI PHUC", h2_style))
    steps = [
        ("Quen Master Password",
         "Mo tab Quan Ly API Keys → chon 'Quen mat khau?' → nhap Recovery Passphrase → dat mat khau moi."),
        ("Mat dien thoai / Google Authenticator",
         "Dang nhap bang Master Password → chon 'Dat lai TOTP' → nhap Recovery Passphrase → quet QR moi."),
        ("Quen ca password lan mat dien thoai",
         "Mo tab Quan Ly API Keys → chon 'Khoi phuc toan bo' → nhap Recovery Passphrase → dat lai moi thu."),
        ("Mat tat ca (ke ca Passphrase)",
         "Xoa file ui_cache.dat va render_state.dat → thiet lap lai tu dau → nhap lai API key."),
    ]
    for i, (title, desc) in enumerate(steps, 1):
        story.append(Paragraph(f"<b>Kich ban {i}: {title}</b>", body_style))
        story.append(Paragraph(f"  -> {desc}", body_style))
        story.append(Spacer(1, 0.25*cm))

    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=8))

    # ── Auto-filled info card ──
    story.append(Paragraph("THONG TIN BAO MAT (Tu dong dien)", h2_style))

    created_str = datetime.date.today().strftime('%d/%m/%Y')
    owner_str   = owner.strip() if owner.strip() else "(chua xac dinh)"

    info_data = [
        ["Ngay thiet lap:",           created_str],
        ["Nguoi so huu / He thong:",  owner_str],
    ]
    info_table = Table(info_data, colWidths=[5.5*cm, 11.5*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME',      (0, 0), (-1, -1), font_name),
        ('FONTSIZE',      (0, 0), (-1, -1), 10),
        ('FONTNAME',      (0, 0), (0, -1),  font_name_bold),
        ('TEXTCOLOR',     (0, 0), (0, -1),  colors.HexColor('#1d1d1f')),
        ('TEXTCOLOR',     (1, 0), (1, -1),  colors.HexColor('#0071e3')),
        ('ROWBACKGROUNDS',(0, 0), (-1, -1), [colors.HexColor('#f0f7ff'), colors.white]),
        ('TOPPADDING',    (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('GRID',          (0, 0), (-1, -1), 0.3, colors.HexColor('#c2d9f5')),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.4*cm))

    # ── Recovery Passphrase box (highlighted) ──
    story.append(Paragraph("RECOVERY PASSPHRASE (Luu giu bi mat)", h2_style))
    passphrase_display = recovery_passphrase if recovery_passphrase else "(khong co thong tin)"
    rec_data = [["Recovery Passphrase:", passphrase_display]]
    rec_table = Table(rec_data, colWidths=[5.5*cm, 11.5*cm])
    rec_table.setStyle(TableStyle([
        ('FONTNAME',      (0, 0), (0, 0),   font_name_bold),
        ('FONTNAME',      (1, 0), (1, 0),   font_name_bold),
        ('FONTSIZE',      (0, 0), (-1, -1), 11),
        ('TEXTCOLOR',     (0, 0), (0, 0),   colors.HexColor('#1d1d1f')),
        ('TEXTCOLOR',     (1, 0), (1, 0),   colors.HexColor('#cc0000')),
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#fff8e6')),
        ('BOX',           (0, 0), (-1, -1), 1.5, colors.HexColor('#ff9500')),
        ('TOPPADDING',    (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
    ]))
    story.append(rec_table)
    story.append(Spacer(1, 0.4*cm))

    # ── Blank fields for extra notes ──
    story.append(Paragraph("GHI CHU THEM (Viet tay)", h2_style))
    field_data = [
        ["Master Password (goi y):",  "_" * 42],
        ["Ten tai khoan Google Auth:", "_" * 42],
        ["Ghi chu khac:",             "_" * 42],
    ]
    field_table = Table(field_data, colWidths=[5.5*cm, 11.5*cm])
    field_table.setStyle(TableStyle([
        ('FONTNAME',      (0, 0), (-1, -1), font_name),
        ('FONTSIZE',      (0, 0), (-1, -1), 10),
        ('FONTNAME',      (0, 0), (0, -1),  font_name_bold),
        ('TEXTCOLOR',     (0, 0), (0, -1),  colors.HexColor('#1d1d1f')),
        ('TEXTCOLOR',     (1, 0), (1, -1),  colors.HexColor('#aeaeb2')),
        ('ROWBACKGROUNDS',(0, 0), (-1, -1), [colors.HexColor('#f9f9fb'), colors.white]),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('GRID',          (0, 0), (-1, -1), 0.3, colors.HexColor('#e5e5ea')),
    ]))
    story.append(field_table)

    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=8))

    # ── Footer ──
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontName=font_name,
                                   fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
    story.append(Paragraph(
        "QC AI CPC1HN | Tai lieu noi bo | Khong phat tan",
        footer_style
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════
#  Internal migration helper
# ══════════════════════════════════════════════

def _migrate_existing_keys(dek_fernet: Fernet):
    """Auto-encrypt any plaintext key_string found in api_key.json."""
    import json as _json
    from core.crypto_utils import is_encrypted, encrypt_value as _enc
    API_FILE = "api_key.json"
    if not os.path.exists(API_FILE):
        return
    try:
        with open(API_FILE, 'r', encoding='utf-8') as f:
            data = _json.load(f)
        changed = False
        for item in data.get("keys", []):
            if "key_string" in item and not is_encrypted(item["key_string"]):
                item["key_string"] = _enc(dek_fernet, item["key_string"])
                changed = True
        if changed:
            with open(API_FILE, 'w', encoding='utf-8') as f:
                _json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception:
        pass
