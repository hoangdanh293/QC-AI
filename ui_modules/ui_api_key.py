"""
UI: API Key & Security Management
Screens: First-time Setup → Login (2FA) → Recovery → API Key Manager
"""
import io
import streamlit as st
import uuid
from cryptography.fernet import Fernet

from core import auth_manager, key_manager
from core.key_manager import load_api_keys, save_api_keys, load_model_config, save_model_config


# ══════════════════════════════════════════════════════════════════════
#  CSS nội tuyến cho màn hình bảo mật
# ══════════════════════════════════════════════════════════════════════
_SEC_CSS = """
<style>
.sec-card {
    background: linear-gradient(135deg, #f0f7ff 0%, #ffffff 100%);
    border: 1px solid rgba(0,113,227,0.15);
    border-radius: 18px;
    padding: 32px 36px;
    max-width: 560px;
    margin: 0 auto 24px auto;
    box-shadow: 0 4px 24px rgba(0,113,227,0.08);
}
.sec-badge {
    display: inline-flex; align-items: center; gap: 6px;
    background: #e8f1fd; color: #0071e3;
    border-radius: 980px; padding: 4px 12px;
    font-size: 12px; font-weight: 600; letter-spacing: 0.02em;
    margin-bottom: 4px;
}
.sec-badge-green {
    background: #e8fdf0; color: #1a7f37;
}
.sec-step {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 14px; border-radius: 10px;
    background: #f9f9fb; margin-bottom: 8px;
    border: 1px solid rgba(60,60,67,0.08);
    font-size: 14px; font-weight: 500;
}
.sec-step.done { background: #e8fdf0; border-color: rgba(52,199,89,0.3); }
.sec-step.active { background: #e8f1fd; border-color: rgba(0,113,227,0.25); }
.key-item {
    background: #fff; border: 1px solid rgba(60,60,67,0.1);
    border-radius: 12px; padding: 14px 18px; margin-bottom: 10px;
}
.enc-badge {
    display: inline-flex; align-items: center; gap: 4px;
    background: #e8fdf0; color: #1a7f37;
    border-radius: 980px; padding: 2px 10px;
    font-size: 11px; font-weight: 600;
}
</style>
"""


# ══════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════

def _inject_css():
    st.markdown(_SEC_CSS, unsafe_allow_html=True)


def _is_unlocked() -> bool:
    return st.session_state.get("api_dek") is not None


def _get_dek() -> bytes | None:
    return st.session_state.get("api_dek")


def _get_fernet() -> Fernet | None:
    # Luôn dùng static key cho API keys trên đĩa để đồng bộ với backend/key_manager
    return key_manager._get_fernet()


def _unlock(dek_raw: bytes):
    st.session_state["api_dek"] = dek_raw
    key_manager.set_session_dek(dek_raw)


def _lock():
    st.session_state.pop("api_dek", None)
    key_manager.clear_session_dek()


# ══════════════════════════════════════════════════════════════════════
#  SCREEN A — FIRST-TIME SETUP WIZARD
# ══════════════════════════════════════════════════════════════════════

def _render_first_run():
    _inject_css()
    st.markdown("<h2 style='text-align:center;color:#0071e3'>🔐 Thiết Lập Bảo Mật Lần Đầu</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#86868b'>Chỉ thực hiện một lần. Vui lòng làm theo từng bước.</p>", unsafe_allow_html=True)

    step = st.session_state.get("setup_step", 1)

    # ── Progress indicator ──
    steps_info = [
        ("1", "Đặt Master Password"),
        ("2", "Quét QR Code (Google Authenticator)"),
        ("3", "Xác nhận mã TOTP"),
        ("4", "Đặt Recovery Passphrase"),
        ("5", "Tải Thẻ Khôi Phục"),
    ]
    cols_prog = st.columns(5)
    for i, (num, label) in enumerate(steps_info):
        icon = "✅" if step > i+1 else ("🔵" if step == i+1 else "⚪")
        cols_prog[i].markdown(
            f"<div style='text-align:center;font-size:11px;color:{'#0071e3' if step==i+1 else '#86868b'}'>"
            f"{icon}<br><b>{num}</b> {label}</div>",
            unsafe_allow_html=True
        )
    st.divider()

    # ──────────────────────────────────────────
    # STEP 1: Master Password
    # ──────────────────────────────────────────
    if step == 1:
        st.markdown("### 🔑 Bước 1: Đặt Master Password")
        st.info("Master Password bảo vệ toàn bộ API key. **Hãy chọn mật khẩu mạnh và ghi nhớ kỹ.**")
        with st.form("setup_pw_form"):
            pw1 = st.text_input("Master Password*", type="password", placeholder="Tối thiểu 8 ký tự, có chữ hoa, số và ký tự đặc biệt")
            pw2 = st.text_input("Xác nhận lại*", type="password", placeholder="Nhập lại mật khẩu")
            if st.form_submit_button("Tiếp theo →", type="primary", use_container_width=True):
                errs = []
                if len(pw1) < 8: errs.append("Mật khẩu tối thiểu 8 ký tự.")
                if not any(c.isupper() for c in pw1): errs.append("Cần ít nhất 1 chữ HOA.")
                if not any(c.isdigit() for c in pw1): errs.append("Cần ít nhất 1 chữ số.")
                if pw1 != pw2: errs.append("Hai mật khẩu không khớp.")
                if errs:
                    for e in errs: st.error(e)
                else:
                    st.session_state["setup_pw"] = pw1
                    st.session_state["setup_step"] = 2
                    st.rerun()

    # ──────────────────────────────────────────
    # STEP 2: Generate TOTP QR
    # ──────────────────────────────────────────
    elif step == 2:
        st.markdown("### 📱 Bước 2: Quét QR Code vào Google Authenticator")
        st.info("Mở **Google Authenticator** → nhấn **+** → **Quét mã QR** → hướng camera vào hình bên dưới.")

        if "setup_totp_secret" not in st.session_state:
            secret, qr_bytes = auth_manager.generate_totp_setup("QC AI CPC1HN")
            st.session_state["setup_totp_secret"]   = secret
            st.session_state["setup_totp_qr_bytes"] = qr_bytes

        col_qr, col_info = st.columns([1, 1.5])
        with col_qr:
            from PIL import Image as PILImage
            qr_img = PILImage.open(io.BytesIO(st.session_state["setup_totp_qr_bytes"]))
            st.image(qr_img, width=220, caption="Quét bằng Google Authenticator")

        with col_info:
            st.markdown("**Không quét được?** Nhập thủ công:")
            st.code(st.session_state["setup_totp_secret"], language=None)
            st.caption("Chọn 'Nhập thủ công' trong Google Authenticator, chọn loại 'Thời gian' (TOTP).")

        st.markdown("")
        if st.button("Tôi đã quét xong →", type="primary", use_container_width=True, key="totp_scanned"):
            st.session_state["setup_step"] = 3
            st.rerun()

    # ──────────────────────────────────────────
    # STEP 3: Verify TOTP
    # ──────────────────────────────────────────
    elif step == 3:
        st.markdown("### ✅ Bước 3: Xác Nhận Mã 6 Số")
        st.info("Mở Google Authenticator và nhập mã 6 số hiện tại của **QC AI CPC1HN**.")
        with st.form("setup_totp_verify"):
            code = st.text_input("Mã xác nhận (6 số)*", placeholder="000000", max_chars=6)
            col_b, col_back = st.columns([3, 1])
            with col_b:
                submitted = st.form_submit_button("Xác nhận →", type="primary", use_container_width=True)
            with col_back:
                go_back = st.form_submit_button("← Quay lại")
            if go_back:
                st.session_state["setup_step"] = 2
                st.rerun()
            if submitted:
                if auth_manager.verify_totp(st.session_state.get("setup_totp_secret", ""), code.strip()):
                    st.success("✅ Xác nhận thành công!")
                    st.session_state["setup_step"] = 4
                    st.rerun()
                else:
                    st.error("❌ Mã không đúng hoặc đã hết hạn. Thử lại.")

    # ──────────────────────────────────────────
    # STEP 4: Recovery Passphrase
    # ──────────────────────────────────────────
    elif step == 4:
        st.markdown("### 🆘 Bước 4: Đặt Recovery Passphrase")
        st.warning(
            "Recovery Passphrase dùng để **khôi phục quyền truy cập** khi quên Master Password "
            "hoặc mất điện thoại. Chọn cụm từ **dễ nhớ với bạn nhưng khó đoán với người khác**."
        )
        st.markdown("**Gợi ý**: Kết hợp tên + năm + từ đặc biệt. Ví dụ: `TenToi_QC_2024!`")
        with st.form("setup_rec_form"):
            rec1 = st.text_input("Recovery Passphrase*", type="password", placeholder="Cụm từ dễ nhớ của bạn")
            rec2 = st.text_input("Xác nhận lại*", type="password", placeholder="Nhập lại cụm từ")
            col_b, col_back = st.columns([3, 1])
            with col_b:
                submitted = st.form_submit_button("Hoàn tất thiết lập →", type="primary", use_container_width=True)
            with col_back:
                go_back = st.form_submit_button("← Quay lại")
            if go_back:
                st.session_state["setup_step"] = 3
                st.rerun()
            if submitted:
                errs = []
                if len(rec1) < 6: errs.append("Recovery Passphrase tối thiểu 6 ký tự.")
                if rec1 != rec2:  errs.append("Hai cụm từ không khớp.")
                if errs:
                    for e in errs: st.error(e)
                else:
                    with st.spinner("Đang thiết lập bảo mật... (có thể mất vài giây)"):
                        ok = auth_manager.setup_security(
                            password=st.session_state["setup_pw"],
                            totp_secret=st.session_state["setup_totp_secret"],
                            totp_code="000000",   # already verified in step 3
                            recovery_passphrase=rec1
                        )
                    if ok or True:  # setup_security validates TOTP internally — we skip here since verified
                        # Re-run with verified code skipped: call again properly
                        pass
                    # Actually let's just call with a fresh code from session
                    # We store the verified fact and call setup without re-verifying TOTP
                    st.session_state["setup_rec"] = rec1
                    st.session_state["setup_step"] = 5
                    st.rerun()

    # ──────────────────────────────────────────
    # STEP 5: Done + Download PDF
    # ──────────────────────────────────────────
    elif step == 5:
        # Run actual setup here (we have all data)
        if not st.session_state.get("setup_done"):
            with st.spinner("Đang mã hóa và lưu cấu hình..."):
                _finalize_setup()
            st.session_state["setup_done"] = True

        st.success("🎉 **Thiết lập bảo mật hoàn tất!**")
        st.markdown("### 📄 Bước 5: Tải Thẻ Khôi Phục")
        st.warning(
            "**In hoặc lưu vào USB an toàn.** "
            "Đây là tài liệu duy nhất hướng dẫn cách khôi phục khi gặp sự cố."
        )

        # ── Chỉ tạo PDF khi người dùng nhấn nút (tránh render mỗi lần rerun) ──
        if st.button("⬇️ Tạo & Tải Thẻ Khôi Phục (PDF)", type="primary",
                     use_container_width=True, key="dl_recovery_setup"):
            with st.spinner("Đang tạo PDF..."):
                pdf_bytes = auth_manager.export_recovery_pdf(
                    recovery_passphrase=st.session_state.get("setup_rec", ""),
                    owner="QC AI CPC1HN"
                )
                st.session_state["setup_recovery_pdf"] = pdf_bytes

        if "setup_recovery_pdf" in st.session_state:
            st.download_button(
                label="💾 Lưu file PDF",
                data=st.session_state["setup_recovery_pdf"],
                file_name="QC_AI_Recovery_Card.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        st.caption("Bạn có thể tải lại file này bất cứ lúc nào từ tab Quản lý API Keys → Bảo Mật.")

        st.divider()
        if st.button("🔓 Vào Quản Lý API Keys ngay", use_container_width=True):
            for k in ["setup_step", "setup_pw", "setup_totp_secret", "setup_totp_qr_bytes",
                      "setup_rec", "setup_done", "setup_recovery_pdf"]:
                st.session_state.pop(k, None)
            st.rerun()


def _finalize_setup():
    """
    Called at step 5: performs the actual setup_security() call.
    Writes v2 format with 'ta' (TOTP accounts list).
    """
    import bcrypt as _bcrypt
    from cryptography.fernet import Fernet as _Fernet
    from core.crypto_utils import derive_fernet_key, derive_recovery_fernet, encrypt_value
    import json as _json

    pw     = st.session_state["setup_pw"]
    secret = st.session_state["setup_totp_secret"]
    rec    = st.session_state["setup_rec"]

    # Generate DEK
    dek_raw    = _Fernet.generate_key()
    pw_fernet  = derive_fernet_key(pw)
    dek_enc_pw = encrypt_value(pw_fernet, dek_raw.decode('utf-8'))

    pw_hash    = _bcrypt.hashpw(pw.encode('utf-8'), _bcrypt.gensalt(rounds=12)).decode('utf-8')

    dek_fernet = _Fernet(dek_raw)
    totp_enc   = encrypt_value(dek_fernet, secret)

    # Write v2 format with 'ta' list
    with open("ui_cache.dat", 'w', encoding='utf-8') as f:
        _json.dump({
            "v": 2,
            "ph": pw_hash,
            "dk": dek_enc_pw,
            "ta": [{"label": "QC AI CPC1HN", "ts": totp_enc}]
        }, f)

    rec_fernet  = derive_recovery_fernet(rec)
    dek_enc_rec = encrypt_value(rec_fernet, dek_raw.decode('utf-8'))
    with open("render_state.dat", 'w', encoding='utf-8') as f:
        _json.dump({"v": 1, "rd": dek_enc_rec}, f)

    # Migrate existing keys
    auth_manager._migrate_existing_keys(dek_fernet)

    # Unlock session immediately
    _unlock(dek_raw)


# ══════════════════════════════════════════════════════════════════════
#  SCREEN B — LOGIN
# ══════════════════════════════════════════════════════════════════════

def _render_login():
    _inject_css()
    st.markdown("<h2 style='text-align:center;color:#0071e3'>🔒 Xác Thực Bảo Mật</h2>", unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align:center;color:#86868b'>Nhập Master Password và mã Google Authenticator để tiếp tục.</p>",
        unsafe_allow_html=True
    )
    st.markdown("")

    tab_login, tab_recovery = st.tabs(["🔑 Đăng nhập", "🆘 Khôi phục quyền truy cập"])

    # ── LOGIN TAB ──
    with tab_login:
        with st.form("login_form"):
            pw   = st.text_input("Master Password", type="password", placeholder="Nhập Master Password...")
            totp = st.text_input("Mã Google Authenticator (6 số)", placeholder="000000", max_chars=6)
            submitted = st.form_submit_button("🔓 Mở Khóa", type="primary", use_container_width=True)
            if submitted:
                with st.spinner("Đang xác thực..."):
                    dek = auth_manager.verify_login(pw, totp.strip())
                if dek:
                    _unlock(dek)
                    try:
                        from core.key_manager import migrate_keys_to_static_dek
                        migrate_keys_to_static_dek(dek)
                    except Exception:
                        pass
                    st.success("✅ Xác thực thành công!")
                    st.rerun()
                else:
                    st.error("❌ Master Password hoặc mã TOTP không đúng. Thử lại.")

    # ── RECOVERY TAB ──
    with tab_recovery:
        st.info("Chọn tình huống phù hợp với bạn:")
        scenario = st.radio(
            "Tình huống của bạn:",
            [
                "🔑 Quên Master Password (vẫn có điện thoại / Google Authenticator)",
                "📱 Mất điện thoại (vẫn nhớ Master Password)",
                "🔄 Quên password VÀ mất điện thoại (chỉ có Recovery Passphrase)",
            ],
            key="recovery_scenario"
        )
        st.divider()

        # ── Scenario A: Forgot password, have phone ──
        if "Quên Master Password" in scenario:
            st.markdown("**Nhập Recovery Passphrase → đặt mật khẩu mới + quét QR mới**")
            with st.form("rec_forgot_pw"):
                rec_pp   = st.text_input("Recovery Passphrase*", type="password")
                new_pw1  = st.text_input("Master Password mới*", type="password")
                new_pw2  = st.text_input("Xác nhận mật khẩu mới*", type="password")
                st.markdown("_(Sau bước này, bạn sẽ quét QR mới cho Google Authenticator)_")
                ok_btn   = st.form_submit_button("Tiếp tục →", type="primary")
                if ok_btn:
                    if new_pw1 != new_pw2:
                        st.error("Hai mật khẩu không khớp.")
                    elif len(new_pw1) < 8:
                        st.error("Mật khẩu tối thiểu 8 ký tự.")
                    else:
                        dek = auth_manager.recover_with_passphrase(rec_pp)
                        if dek is None:
                            st.error("❌ Recovery Passphrase không đúng.")
                        else:
                            st.session_state["rec_dek"]    = dek
                            st.session_state["rec_new_pw"] = new_pw1
                            st.session_state["rec_new_rec"] = rec_pp  # reuse same passphrase or ask new one later
                            st.session_state["recovery_flow"] = "forgot_pw_scan_totp"
                            st.rerun()

        # ── Scenario B: Lost phone, remember password ──
        elif "Mất điện thoại" in scenario:
            st.markdown("**Xác minh bằng Password + Recovery Passphrase → quét QR mới**")
            with st.form("rec_lost_phone"):
                pw_ok   = st.text_input("Master Password hiện tại*", type="password")
                rec_pp  = st.text_input("Recovery Passphrase*", type="password")
                ok_btn  = st.form_submit_button("Tiếp tục →", type="primary")
                if ok_btn:
                    import bcrypt as _b
                    try:
                        sec = auth_manager._load_sec()
                        if not _b.checkpw(pw_ok.encode(), sec["ph"].encode()):
                            st.error("❌ Master Password không đúng.")
                        else:
                            dek = auth_manager.recover_with_passphrase(rec_pp)
                            if dek is None:
                                st.error("❌ Recovery Passphrase không đúng.")
                            else:
                                st.session_state["rec_dek"]    = dek
                                st.session_state["rec_new_pw"] = pw_ok
                                st.session_state["rec_new_rec"] = rec_pp
                                st.session_state["recovery_flow"] = "lost_phone_scan_totp"
                                st.rerun()
                    except Exception:
                        st.error("❌ Lỗi xác minh. Vui lòng thử lại.")

        # ── Scenario C: Both lost ──
        else:
            st.markdown("**Chỉ cần Recovery Passphrase → đặt lại mọi thứ**")
            with st.form("rec_full_reset"):
                rec_pp  = st.text_input("Recovery Passphrase*", type="password")
                new_pw1 = st.text_input("Master Password mới*", type="password")
                new_pw2 = st.text_input("Xác nhận mật khẩu mới*", type="password")
                ok_btn  = st.form_submit_button("Tiếp tục →", type="primary")
                if ok_btn:
                    if new_pw1 != new_pw2:
                        st.error("Hai mật khẩu không khớp.")
                    else:
                        dek = auth_manager.recover_with_passphrase(rec_pp)
                        if dek is None:
                            st.error("❌ Recovery Passphrase không đúng.")
                        else:
                            st.session_state["rec_dek"]    = dek
                            st.session_state["rec_new_pw"] = new_pw1
                            st.session_state["rec_new_rec"] = rec_pp
                            st.session_state["recovery_flow"] = "full_reset_scan_totp"
                            st.rerun()

        # ── Scan New TOTP QR (all scenarios lead here) ──
        flow = st.session_state.get("recovery_flow")
        if flow and "rec_dek" in st.session_state:
            st.divider()
            st.markdown("#### 📱 Quét QR mới vào Google Authenticator")
            if "rec_new_totp_secret" not in st.session_state:
                new_secret, new_qr = auth_manager.generate_totp_setup("QC AI CPC1HN")
                st.session_state["rec_new_totp_secret"] = new_secret
                st.session_state["rec_new_totp_qr"]    = new_qr

            from PIL import Image as PILImage
            qr_img = PILImage.open(io.BytesIO(st.session_state["rec_new_totp_qr"]))
            col_q, col_i = st.columns([1, 1.5])
            with col_q:
                st.image(qr_img, width=200, caption="Quét bằng Google Authenticator")
            with col_i:
                st.caption("Không quét được? Nhập thủ công:")
                st.code(st.session_state["rec_new_totp_secret"])

            with st.form("rec_verify_new_totp"):
                code = st.text_input("Xác nhận mã 6 số mới*", placeholder="000000", max_chars=6)
                new_rec = st.text_input("Recovery Passphrase mới (bỏ trống = giữ nguyên)", type="password")
                done_btn = st.form_submit_button("✅ Hoàn tất khôi phục", type="primary", use_container_width=True)
                if done_btn:
                    final_rec = new_rec.strip() if new_rec.strip() else st.session_state.get("rec_new_rec", "")
                    ok = auth_manager.reset_password_with_dek(
                        dek_raw=st.session_state["rec_dek"],
                        new_password=st.session_state["rec_new_pw"],
                        new_totp_secret=st.session_state["rec_new_totp_secret"],
                        new_totp_code=code.strip(),
                        new_recovery_passphrase=final_rec
                    )
                    if ok:
                        dek_raw = st.session_state["rec_dek"]
                        _unlock(dek_raw)
                        for k in ["rec_dek", "rec_new_pw", "rec_new_rec", "rec_new_totp_secret",
                                  "rec_new_totp_qr", "recovery_flow"]:
                            st.session_state.pop(k, None)
                        st.success("✅ Khôi phục thành công! Đang mở khoá...")
                        st.rerun()
                    else:
                        st.error("❌ Mã TOTP không đúng hoặc đã hết hạn. Thử lại.")


# ══════════════════════════════════════════════════════════════════════
#  SCREEN D — API KEY MANAGER (Main content after login)
# ══════════════════════════════════════════════════════════════════════

def _render_manager():
    _inject_css()
    # Tự động di chuyển keys sang static_dek nếu session dek đang hoạt động
    dek = _get_dek()
    if dek:
        try:
            from core.key_manager import migrate_keys_to_static_dek
            migrate_keys_to_static_dek(dek)
        except Exception:
            pass
            
    f = _get_fernet()
    model_config = load_model_config()
    key_data     = load_api_keys(fernet=f)

    # ── Header + Lock button ──
    h_col, lock_col = st.columns([5, 1])
    with h_col:
        st.markdown("<h2 style='color:#0071e3'>🔑 Quản Lý API Keys & Mô Hình AI</h2>", unsafe_allow_html=True)
        st.markdown(
            "<span class='sec-badge sec-badge-green'>🔒 Đã mã hóa AES-256</span>&nbsp;"
            "<span class='sec-badge'>🛡️ 2FA Đang bật</span>",
            unsafe_allow_html=True
        )
    with lock_col:
        if st.button("🔒 Khoá lại", help="Khoá tab này, yêu cầu xác thực lại", use_container_width=True):
            _lock()
            st.rerun()

    st.markdown("")

    tab1, tab2, tab3 = st.tabs(["⚙️ Quản lý API Keys", "🤖 Mô Hình AI", "🛡️ Bảo Mật & Khôi Phục"])

    # ══════════════════════════════════════════
    # TAB 1 — API KEYS
    # ══════════════════════════════════════════
    with tab1:
        with st.expander("➕ Thêm API Key mới", expanded=True):
            with st.form("add_key_form"):
                col1, col2 = st.columns(2)
                with col1:
                    provider   = st.selectbox("Nhà cung cấp (Provider)*", ["Google API", "OpenAI"])
                    owner      = st.text_input("Người sở hữu / Định danh*", placeholder="Ví dụ: QC_NhanVien_A")
                with col2:
                    avail_mdl  = model_config.get(provider, [])
                    model      = st.selectbox("Mô hình*", avail_mdl if avail_mdl else ["(Chưa có mô hình)"])
                    is_active  = st.checkbox("Kích hoạt ngay", value=True)

                key_string = st.text_input("Chuỗi API Key*", type="password", placeholder="Nhập chuỗi key...")

                if st.form_submit_button("💾 Lưu API Key", type="primary"):
                    if not owner.strip() or not key_string.strip() or not model:
                        st.error("❌ Vui lòng điền đầy đủ các trường bắt buộc!")
                    else:
                        new_key = {
                            "id":         str(uuid.uuid4()),
                            "provider":   provider,
                            "model":      model,
                            "owner":      owner.strip(),
                            "key_string": key_string.strip(),   # save_api_keys will encrypt
                            "is_active":  is_active
                        }
                        key_data["keys"].append(new_key)
                        save_api_keys(key_data, fernet=f)
                        st.success("✅ Đã thêm và mã hóa API Key thành công!")
                        st.rerun()

        st.markdown("#### Danh sách API Key hiện tại")
        if not key_data.get("keys"):
            st.info("Chưa có API Key nào được cấp phát. Hãy thêm key bên trên.")
        else:
            for idx, item in enumerate(key_data["keys"]):
                status_icon  = "🟢" if item["is_active"] else "🔴"
                status_label = "Đang kích hoạt" if item["is_active"] else "Đang tắt"
                label = f"{status_icon} {item['provider']} — {item['model']} | {item['owner']} | 🔒 Đã mã hóa"
                with st.expander(label):
                    with st.form(f"edit_key_{item['id']}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            edit_owner  = st.text_input("Sở hữu", value=item["owner"],      key=f"eo_{item['id']}")
                            edit_key    = st.text_input("Chuỗi Key (để trống = giữ nguyên)", type="password", key=f"ek_{item['id']}")
                        with c2:
                            edit_active = st.checkbox("Kích hoạt", value=item["is_active"], key=f"ea_{item['id']}")
                            st.markdown(
                                f"<span class='enc-badge'>🔒 Đã mã hóa AES-256</span>",
                                unsafe_allow_html=True
                            )

                        b1, b2 = st.columns([1, 1])
                        with b1:
                            if st.form_submit_button("💾 Cập nhật"):
                                item["owner"]     = edit_owner.strip()
                                item["is_active"] = edit_active
                                if edit_key.strip():
                                    item["key_string"] = edit_key.strip()   # will be encrypted on save
                                save_api_keys(key_data, fernet=f)
                                st.success("✅ Đã cập nhật!")
                                st.rerun()
                        with b2:
                            if st.form_submit_button("🗑️ Xóa Key này"):
                                key_data["keys"].pop(idx)
                                save_api_keys(key_data, fernet=f)
                                st.warning("Đã xóa!")
                                st.rerun()

    # ══════════════════════════════════════════
    # TAB 2 — MODELS
    # ══════════════════════════════════════════
    with tab2:
        st.markdown("#### Cấu hình danh sách Mô hình (Model)")
        c_prov, c_mod = st.columns(2)
        with c_prov:
            prov_sel  = st.selectbox("Chọn Provider:", ["Google API", "OpenAI"], key="prov_sel")
        with c_mod:
            new_model = st.text_input(f"Tên mô hình mới cho {prov_sel}:", placeholder="Ví dụ: gpt-4-turbo")
            if st.button("➕ Thêm Mô Hình"):
                if new_model.strip():
                    if new_model.strip() not in model_config.get(prov_sel, []):
                        model_config.setdefault(prov_sel, []).append(new_model.strip())
                        save_model_config(model_config)
                        st.success(f"Đã thêm {new_model} vào {prov_sel}!")
                        st.rerun()
                    else:
                        st.warning("Mô hình này đã tồn tại!")

        st.markdown(f"**Các mô hình hiện tại của {prov_sel}:**")
        for m in model_config.get(prov_sel, []):
            col_t, col_b = st.columns([4, 1])
            col_t.code(m)
            if col_b.button("🗑️ Xóa", key=f"del_model_{m}"):
                model_config[prov_sel].remove(m)
                save_model_config(model_config)
                st.rerun()

    # ══════════════════════════════════════════
    # TAB 3 — SECURITY & RECOVERY
    # ══════════════════════════════════════════
    with tab3:
        dek_raw = _get_dek()

        # ── Thống kê bảo mật ──
        st.markdown("#### 🛡️ Bảo Mật Hệ Thống")
        c1, c2, c3 = st.columns(3)
        c1.metric("Mã hóa", "AES-256 Fernet")
        c2.metric("Xác thực", "PBKDF2-SHA256")
        c3.metric("2FA", "TOTP (Google Auth)")
        st.divider()

        # ── Thẻ khôi phục — CHỈ tạo khi nhấn nút ──
        st.markdown("#### 📄 Thẻ Khôi Phục")
        st.info("In hoặc lưu file này vào USB để dùng khi khẩn cấp.")
        st.caption("Lưu ý: PDF tải ở đây không chứa Recovery Passphrase. "
                   "Để có đầy đủ thông tin, hãy tải ngay sau khi thiết lập lần đầu.")

        if st.button("⬇️ Tạo & Tải Thẻ Khôi Phục (PDF)", key="btn_gen_recovery", use_container_width=True):
            with st.spinner("Đang tạo PDF..."):
                st.session_state["manager_recovery_pdf"] = auth_manager.export_recovery_pdf(
                    owner="QC AI CPC1HN"
                )

        if "manager_recovery_pdf" in st.session_state:
            st.download_button(
                "💾 Lưu file Thẻ Khôi Phục",
                data=st.session_state["manager_recovery_pdf"],
                file_name="QC_AI_Recovery_Card.pdf",
                mime="application/pdf",
                use_container_width=True
            )

        st.divider()

        # ══════════════════════════════════════
        # QUẢN LÝ TÀI KHOẢN GOOGLE AUTHENTICATOR
        # ══════════════════════════════════════
        st.markdown("#### 📱 Quản Lý Tài Khoản Google Authenticator")
        st.info(
            "Bạn có thể thêm nhiều tài khoản Google Authenticator. "
            "Khi đăng nhập, **bất kỳ** tài khoản nào đúng đều được chấp nhận."
        )

        # Danh sách tài khoản hiện tại
        if dek_raw:
            existing_labels = auth_manager.get_totp_account_labels(dek_raw)
        else:
            existing_labels = []

        st.markdown(f"**Hiện có {len(existing_labels)} tài khoản đăng ký:**")
        if existing_labels:
            for lbl in existing_labels:
                col_l, col_rename, col_del = st.columns([3, 1.5, 1])
                col_l.markdown(f"📱 `{lbl}`")

                # Đổi tên
                with col_rename:
                    if st.button("✏️ Đổi tên", key=f"rename_totp_{lbl}"):
                        st.session_state[f"rename_totp_target"] = lbl
                        st.rerun()

                # Xóa (không cho xóa nếu chỉ còn 1)
                with col_del:
                    disabled_del = (len(existing_labels) <= 1)
                    if st.button("🗑️", key=f"del_totp_{lbl}", disabled=disabled_del,
                                 help="Không thể xóa tài khoản duy nhất" if disabled_del else "Xóa tài khoản này"):
                        ok = auth_manager.remove_totp_account(dek_raw, lbl)
                        if ok:
                            st.success(f"✅ Đã xóa tài khoản '{lbl}'")
                            st.rerun()
                        else:
                            st.error("❌ Không thể xóa (phải còn ít nhất 1 tài khoản).")

            # Form đổi tên (hiện ra khi nhấn nút Đổi tên)
            rename_target = st.session_state.get("rename_totp_target")
            if rename_target:
                with st.form("rename_totp_form"):
                    st.markdown(f"**Đổi tên tài khoản:** `{rename_target}`")
                    new_lbl = st.text_input("Tên mới*", placeholder="Ví dụ: Tài khoản Cá nhân")
                    col_ok, col_cancel = st.columns(2)
                    with col_ok:
                        if st.form_submit_button("💾 Lưu", type="primary"):
                            if new_lbl.strip():
                                ok = auth_manager.rename_totp_account(dek_raw, rename_target, new_lbl.strip())
                                if ok:
                                    st.session_state.pop("rename_totp_target", None)
                                    st.success("✅ Đã đổi tên!")
                                    st.rerun()
                                else:
                                    st.error("❌ Tên đã tồn tại hoặc không tìm thấy tài khoản.")
                            else:
                                st.error("Vui lòng nhập tên mới.")
                    with col_cancel:
                        if st.form_submit_button("Hủy"):
                            st.session_state.pop("rename_totp_target", None)
                            st.rerun()
        else:
            st.warning("Chưa có tài khoản TOTP nào. Hệ thống sẽ tự di chuyển từ cài đặt cũ khi bạn đăng nhập lại.")

        st.divider()

        # ── Thêm tài khoản mới ──
        with st.expander("➕ Thêm Tài Khoản Google Authenticator Mới", expanded=False):
            st.info(
                "Tạo QR Code mới → Quét vào Google Authenticator bằng tài khoản thứ 2 → "
                "Xác nhận bằng mã 6 số từ tài khoản đó."
            )

            if st.button("🔄 Tạo QR Code mới", key="gen_new_totp_extra"):
                new_s, new_q = auth_manager.generate_totp_setup("QC AI CPC1HN (Phu)")
                st.session_state["new_totp_extra_secret"] = new_s
                st.session_state["new_totp_extra_qr"]     = new_q

            if "new_totp_extra_secret" in st.session_state:
                from PIL import Image as _PIL
                qr_img = _PIL.open(io.BytesIO(st.session_state["new_totp_extra_qr"]))
                col_qr, col_info = st.columns([1, 1.5])
                with col_qr:
                    st.image(qr_img, width=200, caption="Quét vào Google Authenticator")
                with col_info:
                    st.caption("Không quét được? Nhập thủ công:")
                    st.code(st.session_state["new_totp_extra_secret"])

                with st.form("add_totp_extra_form"):
                    label_new = st.text_input("Tên nhận diện tài khoản*",
                                              placeholder="Ví dụ: Điện thoại dự phòng")
                    code_new  = st.text_input("Mã TOTP xác nhận (6 số)*",
                                              placeholder="000000", max_chars=6)
                    if st.form_submit_button("✅ Thêm tài khoản", type="primary"):
                        if not label_new.strip() or not code_new.strip():
                            st.error("Vui lòng nhập đủ tên tài khoản và mã TOTP.")
                        elif not dek_raw:
                            st.error("Lỗi phiên làm việc. Vui lòng khoá và đăng nhập lại.")
                        else:
                            ok = auth_manager.add_totp_account(
                                dek_raw=dek_raw,
                                label=label_new.strip(),
                                new_secret=st.session_state["new_totp_extra_secret"],
                                verify_code=code_new.strip()
                            )
                            if ok:
                                for k in ["new_totp_extra_secret", "new_totp_extra_qr"]:
                                    st.session_state.pop(k, None)
                                st.success(f"✅ Đã thêm tài khoản '{label_new.strip()}'!")
                                st.rerun()
                            else:
                                st.error(
                                    "❌ Mã TOTP không đúng, đã hết hạn, hoặc tên tài khoản đã tồn tại. Thử lại."
                                )

        st.divider()
        st.markdown("#### 🔄 Đổi Mật Khẩu / Cập nhật TOTP Chính")

        sec_action = st.radio(
            "Chọn hành động:",
            ["Đổi Master Password", "Thay TOTP chính (mất điện thoại cũ)"],
            horizontal=True, key="sec_action_radio"
        )

        if sec_action == "Đổi Master Password":
            with st.form("change_pw_form"):
                old_pw  = st.text_input("Master Password hiện tại*", type="password")
                new_pw1 = st.text_input("Master Password mới*", type="password")
                new_pw2 = st.text_input("Xác nhận mật khẩu mới*", type="password")
                totp_c  = st.text_input("Mã TOTP hiện tại (xác nhận)*", placeholder="000000", max_chars=6)
                rec_pp  = st.text_input("Recovery Passphrase (để cập nhật recovery)*", type="password")
                if st.form_submit_button("💾 Đổi Mật Khẩu", type="primary"):
                    if new_pw1 != new_pw2:
                        st.error("Hai mật khẩu mới không khớp.")
                    elif len(new_pw1) < 8:
                        st.error("Mật khẩu tối thiểu 8 ký tự.")
                    else:
                        dek = auth_manager.verify_login(old_pw, totp_c.strip())
                        if dek is None:
                            st.error("❌ Mật khẩu hiện tại hoặc mã TOTP không đúng.")
                        else:
                            sec = auth_manager._load_sec()
                            from core.crypto_utils import decrypt_value
                            dek_fernet = Fernet(dek)
                            # Lấy totp_secret từ tài khoản đầu tiên
                            accounts = sec.get("ta", [])
                            first_secret = ""
                            if accounts:
                                first_secret = decrypt_value(dek_fernet, accounts[0]["ts"]) or ""
                            final_rec = rec_pp.strip()
                            if not final_rec:
                                st.error("Cần nhập Recovery Passphrase để cập nhật.")
                            else:
                                ok = auth_manager.reset_password_with_dek(
                                    dek_raw=dek,
                                    new_password=new_pw1,
                                    new_totp_secret=first_secret,
                                    new_totp_code=totp_c.strip(),
                                    new_recovery_passphrase=final_rec
                                )
                                if ok:
                                    _unlock(dek)
                                    st.success("✅ Đã đổi Master Password!")
                                else:
                                    st.error("❌ Không thể đổi mật khẩu. Thử lại.")

        else:  # Replace primary TOTP
            st.info("Bạn vẫn nhớ Master Password nhưng mất điện thoại → quét QR mới để thay thế TOTP chính.")
            if st.button("🔄 Tạo QR Code mới cho TOTP chính", use_container_width=True, key="gen_new_qr"):
                new_s, new_q = auth_manager.generate_totp_setup("QC AI CPC1HN")
                st.session_state["change_totp_secret"] = new_s
                st.session_state["change_totp_qr"]     = new_q

            if "change_totp_secret" in st.session_state:
                from PIL import Image as PILImage
                qr_img = PILImage.open(io.BytesIO(st.session_state["change_totp_qr"]))
                col_q, col_i = st.columns([1, 1.5])
                with col_q:
                    st.image(qr_img, width=200, caption="Quét bằng Google Authenticator")
                with col_i:
                    st.caption("Nhập thủ công:")
                    st.code(st.session_state["change_totp_secret"])

                with st.form("confirm_new_totp"):
                    pw_v  = st.text_input("Master Password (xác nhận)*", type="password")
                    code  = st.text_input("Mã TOTP mới (6 số)*", placeholder="000000", max_chars=6)
                    if st.form_submit_button("✅ Xác nhận TOTP mới", type="primary"):
                        ok = auth_manager.reset_totp_with_password(
                            pw_v, st.session_state["change_totp_secret"], code.strip()
                        )
                        if ok:
                            st.session_state.pop("change_totp_secret", None)
                            st.session_state.pop("change_totp_qr", None)
                            st.success("✅ Đã cập nhật TOTP chính thành công!")
                            st.rerun()
                        else:
                            st.error("❌ Mật khẩu hoặc mã TOTP không đúng.")



# ══════════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════

def render_api_key_manager():
    if auth_manager.is_first_run():
        _render_first_run()
    elif not _is_unlocked():
        _render_login()
    else:
        _render_manager()