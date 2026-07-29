"""
ui_quan_ly_ho_so.py
====================
Giao diện Quản Lý & In Hồ Sơ (Google Drive) cho QC AI CPC1HN.

Chức năng:
  • Cài Đặt Drive  – Cấu hình xác thực OAuth / Service Account
  • Duyệt Hồ Sơ   – Duyệt folder/file theo cấu trúc cây
  • Tìm Kiếm      – Tìm theo Tên hoặc BFO (trong tên file)
  • Tải Lên        – Tạo folder mới, upload file
  • In             – In file qua webViewLink (Google Docs viewer) trên browser
"""

import os
import io
import json
import traceback
import streamlit as st
import streamlit.components.v1 as components

from core.drive_manager import (
    load_drive_config, save_drive_config,
    authenticate_drive,
    list_folders, list_files, search_files_global,
    create_folder, upload_file, download_file,
    get_folder_path, get_file_metadata,
    format_file_size, format_datetime,
    get_file_icon, is_printable
)

# ─────────────────────────────────────────────────────────────────────────────
#  CSS
# ─────────────────────────────────────────────────────────────────────────────
_CSS = """
<style>
/* ─ Drive Cards ─ */
.drive-card {
    background: #fff;
    border: 1px solid rgba(60,60,67,0.12);
    border-radius: 13px;
    padding: 14px 18px;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 14px;
    transition: all 0.18s ease;
    cursor: pointer;
}
.drive-card:hover {
    border-color: rgba(0,113,227,0.35);
    box-shadow: 0 4px 16px rgba(0,113,227,0.08);
    transform: translateY(-1px);
}
.drive-folder-card {
    background: linear-gradient(135deg,#fffbf0 0%,#fff 100%);
    border-left: 4px solid #ff9500;
}
.drive-file-card {
    border-left: 4px solid #0071e3;
}
.drive-icon { font-size: 26px; flex-shrink: 0; }
.drive-title {
    font-weight: 600;
    font-size: 14px;
    color: #1d1d1f;
    letter-spacing: -0.01em;
    margin-bottom: 2px;
}
.drive-meta {
    font-size: 12px;
    color: #86868b;
    line-height: 1.4;
}
.drive-badge {
    display: inline-flex; align-items: center;
    background: #e8f1fd; color: #0071e3;
    border-radius: 980px; padding: 2px 10px;
    font-size: 11px; font-weight: 600;
    margin-left: 6px;
}
.drive-badge-green { background: #e8fdf0; color: #1a7f37; }
.drive-badge-orange { background: #fff3e0; color: #e65100; }

/* ─ Breadcrumb ─ */
.breadcrumb {
    display: flex; align-items: center; flex-wrap: wrap;
    gap: 4px; padding: 10px 14px;
    background: #f9f9fb; border-radius: 10px;
    border: 1px solid rgba(60,60,67,0.08);
    margin-bottom: 12px; font-size: 13px;
}
.breadcrumb-sep { color: #aeaeb2; }
.breadcrumb-item { color: #0071e3; font-weight: 500; }
.breadcrumb-current { color: #1d1d1f; font-weight: 600; }

/* ─ Auth Card ─ */
.auth-card {
    background: linear-gradient(135deg,#f0f7ff 0%,#fff 100%);
    border: 1px solid rgba(0,113,227,0.15);
    border-radius: 18px;
    padding: 28px 32px;
    margin-bottom: 20px;
    box-shadow: 0 4px 20px rgba(0,113,227,0.07);
}
.auth-step {
    display: flex; align-items: flex-start; gap: 12px;
    padding: 12px 16px; border-radius: 10px;
    background: #f9f9fb; margin-bottom: 8px;
    border: 1px solid rgba(60,60,67,0.08);
    font-size: 13px; line-height: 1.5;
}
.auth-step-num {
    background: #0071e3; color: #fff;
    border-radius: 50%; width: 22px; height: 22px;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 700; flex-shrink: 0;
}

/* ─ Print Panel ─ */
.print-panel {
    background: linear-gradient(135deg,#f0fff8 0%,#fff 100%);
    border: 1px solid rgba(52,199,89,0.25);
    border-radius: 13px;
    padding: 16px 20px;
    margin-top: 12px;
}

/* ─ Search result highlight ─ */
.search-result-name { font-weight: 600; color: #0071e3; }
.search-highlight { background: #fff3cd; border-radius: 3px; padding: 0 2px; }
</style>
"""

# ─────────────────────────────────────────────────────────────────────────────
#  Session state helpers
# ─────────────────────────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "drive_service":        None,
        "drive_connected":      False,
        "drive_current_folder": None,   # {id, name}
        "drive_folder_path":    [],     # [{id, name}, ...]
        "drive_selected_file":  None,   # {id, name, mimeType, ...}
        "drive_tab":            "browser",  # browser | search | upload | settings
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _get_service():
    """Lấy service đã lưu hoặc None."""
    return st.session_state.get("drive_service")


def _require_connected():
    """Trả về True nếu đã kết nối, hiển thị cảnh báo nếu chưa."""
    if not st.session_state.drive_connected or _get_service() is None:
        st.warning("⚠️ Chưa kết nối Google Drive. Hãy vào tab **⚙️ Cài Đặt** để kết nối.")
        return False
    return True

def _verify_drive_password(password_input: str) -> bool:
    """Kiểm tra mật khẩu nhập vào có trùng khớp với mật khẩu Master của hệ thống hoặc mật khẩu riêng của Drive không."""
    import bcrypt
    import json
    import os
    
    password_input = password_input.strip()
    if not password_input:
        return False
        
    # 1. Kiểm tra Mật khẩu Master của hệ thống (trong ui_cache.dat)
    if os.path.exists("ui_cache.dat"):
        try:
            with open("ui_cache.dat", "r", encoding="utf-8") as f:
                sec = json.load(f)
            ph = sec.get("ph")
            if ph and bcrypt.checkpw(password_input.encode('utf-8'), ph.encode('utf-8')):
                return True
        except Exception:
            pass
            
    # 2. Kiểm tra Mật khẩu riêng cho Drive (trong drive_config.json)
    cfg = load_drive_config()
    drive_hash = cfg.get("drive_password_hash")
    if drive_hash:
        try:
            if bcrypt.checkpw(password_input.encode('utf-8'), drive_hash.encode('utf-8')):
                return True
        except Exception:
            pass
            
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  Tab: Cài Đặt Drive
# ─────────────────────────────────────────────────────────────────────────────
def _render_settings_tab():
    st.markdown(_CSS, unsafe_allow_html=True)
    
    # ── Kiểm tra bảo mật truy cập ──────────────────────────────────────────
    is_system_unlocked = st.session_state.get("api_dek") is not None
    if is_system_unlocked:
        st.session_state.drive_authorized = True
        
    if not st.session_state.get("drive_authorized", False):
        st.markdown("<div style='max-width:560px;margin:40px auto;'>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center;'>🔐 Khóa Cấu Hình Google Drive</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #86868b;'>Vui lòng nhập mật khẩu Master hoặc mật khẩu riêng của Drive để tiếp tục.</p>", unsafe_allow_html=True)
        
        with st.form("drive_unlock_form"):
            password_input = st.text_input("Mật khẩu truy cập", type="password", placeholder="Nhập mật khẩu của bạn...")
            submit = st.form_submit_button("🔓 Mở Khóa", use_container_width=True, type="primary")
            
            if submit:
                if _verify_drive_password(password_input):
                    st.session_state.drive_authorized = True
                    st.success("🔓 Mở khóa thành công!")
                    import time
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ Mật khẩu không chính xác.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    cfg = load_drive_config()

    st.markdown("### ⚙️ Cài Đặt Kết Nối Google Drive")

    # ── Hướng dẫn ──────────────────────────────────────────────────────────
    with st.expander("📘 Hướng dẫn lấy Credentials (nhấn để mở)", expanded=False):
        st.markdown("""
<div class='auth-card'>
<b>Bước 1 — Tạo dự án Google Cloud</b>
<div class='auth-step'><div class='auth-step-num'>1</div>
Truy cập <a href='https://console.cloud.google.com' target='_blank'>console.cloud.google.com</a>
→ Tạo dự án mới (hoặc chọn dự án có sẵn).
</div>
<div class='auth-step'><div class='auth-step-num'>2</div>
Vào <b>APIs & Services → Library</b> → Tìm <b>Google Drive API</b> → Bật (Enable).
</div>

<b>Cách A — OAuth 2.0 (tài khoản Google cá nhân)</b>
<div class='auth-step'><div class='auth-step-num'>3A</div>
Vào <b>APIs & Services → Credentials</b> → <b>Create Credentials → OAuth client ID</b>
→ Loại: <b>Desktop app</b> → Tải về file <code>credentials.json</code>.
</div>
<div class='auth-step'><div class='auth-step-num'>4A</div>
Nếu app ở trạng thái <i>Testing</i>, vào <b>OAuth consent screen → Test users</b>
→ Thêm email Google của bạn.
</div>

<b>Cách B — Service Account (không cần đăng nhập mỗi lần)</b>
<div class='auth-step'><div class='auth-step-num'>3B</div>
Vào <b>APIs & Services → Credentials → Create Credentials → Service Account</b>
→ Tạo → Vào service account → Tab <b>Keys → Add Key → JSON</b> → Tải về.
</div>
<div class='auth-step'><div class='auth-step-num'>4B</div>
<b>Quan trọng:</b> Chia sẻ Folder Drive với email của Service Account
(dạng <code>xxx@project.iam.gserviceaccount.com</code>) với quyền <b>Editor</b>.
</div>
</div>
        """, unsafe_allow_html=True)

    st.divider()

    # ── Cấu hình xác thực ───────────────────────────────────────────────────
    col1, col2 = st.columns([1, 1])

    with col1:
        auth_type = st.radio(
            "Phương thức xác thực",
            ["OAuth 2.0 (tài khoản cá nhân)", "Service Account (nội bộ)"],
            index=0 if cfg.get("auth_type", "oauth") == "oauth" else 1,
            key="drive_auth_type_radio"
        )
        cfg["auth_type"] = "oauth" if "OAuth" in auth_type else "service_account"

    with col2:
        creds_label = "credentials.json (OAuth)" if cfg["auth_type"] == "oauth" else "service_account.json"
        creds_file_input = st.text_input(
            f"Đường dẫn file {creds_label}",
            value=cfg.get("credentials_file", ""),
            placeholder="VD: D:/QC_AI_Win/credentials.json",
            key="drive_creds_path"
        )
        cfg["credentials_file"] = creds_file_input.strip()

        # Upload file credentials thay thế nhập tay
        uploaded_creds = st.file_uploader(
            f"Hoặc tải lên file {creds_label}",
            type=["json"],
            key="drive_creds_upload"
        )
        if uploaded_creds is not None:
            save_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                uploaded_creds.name
            )
            with open(save_path, "wb") as f:
                f.write(uploaded_creds.getvalue())
            cfg["credentials_file"] = save_path
            st.success(f"✅ Đã lưu: {save_path}")

    st.divider()

    # ── Folder gốc ──────────────────────────────────────────────────────────
    col_r1, col_r2 = st.columns([2, 1])
    with col_r1:
        root_id = st.text_input(
            "ID Folder gốc trên Google Drive",
            value=cfg.get("root_folder_id", ""),
            placeholder="VD: 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms",
            help="Copy ID từ URL Google Drive: drive.google.com/drive/folders/[ID_Ở_ĐÂY]",
            key="drive_root_id"
        )
        raw_root_id = root_id.strip()
        if "drive.google.com" in raw_root_id:
            parts = raw_root_id.split("/folders/")
            if len(parts) > 1:
                raw_root_id = parts[1]
        if "?" in raw_root_id:
            raw_root_id = raw_root_id.split("?")[0]
        if "&" in raw_root_id:
            raw_root_id = raw_root_id.split("&")[0]
        cfg["root_folder_id"] = raw_root_id.strip()

    with col_r2:
        root_name = st.text_input(
            "Tên hiển thị folder gốc",
            value=cfg.get("root_folder_name", "QC Hồ Sơ Kiểm Nghiệm"),
            key="drive_root_name"
        )
        cfg["root_folder_name"] = root_name.strip()

    # ── Nút lưu + kết nối ───────────────────────────────────────────────────
    col_s1, col_s2, col_s3 = st.columns([1, 1, 2])

    with col_s1:
        if st.button("💾 Lưu Cấu Hình", use_container_width=True, key="drive_save_cfg"):
            save_drive_config(cfg)
            st.success("✅ Đã lưu cấu hình!")

    with col_s2:
        if st.button("🔗 Kết Nối Drive", use_container_width=True, key="drive_connect_btn", type="primary"):
            save_drive_config(cfg)
            with st.spinner("Đang kết nối Google Drive…"):
                try:
                    svc = authenticate_drive(cfg)
                    st.session_state.drive_service   = svc
                    st.session_state.drive_connected = True
                    # Reset về folder gốc
                    root_id_clean = cfg.get("root_folder_id", "").strip()
                    if root_id_clean:
                        st.session_state.drive_current_folder = {
                            "id": root_id_clean,
                            "name": cfg.get("root_folder_name", "Folder Gốc")
                        }
                        st.session_state.drive_folder_path = [
                            {"id": root_id_clean, "name": cfg.get("root_folder_name", "Folder Gốc")}
                        ]
                    st.success("✅ Kết nối Google Drive thành công!")
                    st.rerun()
                except ImportError as e:
                    st.error(f"❌ Thiếu thư viện: {e}\n\nChạy **CaiDat_ThuVien.bat** để cài đặt.")
                except FileNotFoundError as e:
                    st.error(f"❌ {e}")
                except Exception as e:
                    st.error(f"❌ Lỗi kết nối: {e}")
                    st.code(traceback.format_exc(), language="text")

    with col_s3:
        if st.session_state.drive_connected:
            st.markdown(
                "<div style='padding:10px 0'>"
                "<span class='drive-badge drive-badge-green'>🟢 Đã kết nối Drive</span>"
                "</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                "<div style='padding:10px 0'>"
                "<span class='drive-badge drive-badge-orange'>🔴 Chưa kết nối</span>"
                "</div>",
                unsafe_allow_html=True
            )

    # Ngắt kết nối
    if st.session_state.drive_connected:
        st.divider()
        if st.button("🔌 Ngắt Kết Nối", key="drive_disconnect"):
            st.session_state.drive_service   = None
            st.session_state.drive_connected = False
            st.session_state.drive_current_folder = None
            st.session_state.drive_folder_path    = []
            st.session_state.drive_selected_file  = None
            st.rerun()

    # ── Đổi mật khẩu riêng của Drive ──────────────────────────────────────────
    st.divider()
    st.markdown("### 🔐 Quản Lý Mật Khẩu Riêng Cho Drive")
    st.caption("Thiết lập mật khẩu riêng để truy cập cấu hình Drive mà không cần mở khóa API Keys của hệ thống.")
    
    with st.expander("🔑 Thay đổi / Thiết lập mật khẩu riêng"):
        with st.form("set_drive_password_form"):
            new_pw = st.text_input("Mật khẩu riêng mới", type="password", placeholder="Tối thiểu 6 ký tự")
            confirm_pw = st.text_input("Xác nhận mật khẩu riêng mới", type="password", placeholder="Nhập lại mật khẩu")
            btn_set = st.form_submit_button("💾 Lưu Mật Khẩu Riêng", type="primary")
            
            if btn_set:
                if len(new_pw) < 6:
                    st.error("❌ Mật khẩu phải có độ dài tối thiểu 6 ký tự.")
                elif new_pw != confirm_pw:
                    st.error("❌ Hai mật khẩu không khớp.")
                else:
                    import bcrypt
                    pw_hash = bcrypt.hashpw(new_pw.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')
                    cfg["drive_password_hash"] = pw_hash
                    save_drive_config(cfg)
                    st.success("✅ Đã cập nhật mật khẩu riêng cho Drive thành công!")


# ─────────────────────────────────────────────────────────────────────────────
#  Component: Breadcrumb
# ─────────────────────────────────────────────────────────────────────────────
def _render_breadcrumb():
    """Render breadcrumb dạng nút bấm để điều hướng lên."""
    path = st.session_state.drive_folder_path
    cfg  = load_drive_config()
    root_id = cfg.get("root_folder_id", "")

    if not path:
        return

    crumbs = [{"id": root_id or "root", "name": "🏠 Gốc"}] + path
    # Loại trùng
    seen = []
    unique_crumbs = []
    for c in crumbs:
        if c["id"] not in seen:
            seen.append(c["id"])
            unique_crumbs.append(c)

    cols = st.columns(min(len(unique_crumbs) * 2, 12))
    for i, crumb in enumerate(unique_crumbs):
        col_idx = i * 2
        if col_idx < len(cols):
            with cols[col_idx]:
                is_current = (i == len(unique_crumbs) - 1)
                label = f"📁 {crumb['name']}" if not crumb["name"].startswith("🏠") else crumb["name"]
                if is_current:
                    st.markdown(
                        f"<span style='font-weight:700;color:#1d1d1f;font-size:13px'>{label}</span>",
                        unsafe_allow_html=True
                    )
                else:
                    if st.button(label, key=f"bc_{crumb['id']}_{i}", use_container_width=False):
                        # Cắt path về crumb này
                        idx = next(
                            (j for j, p in enumerate(st.session_state.drive_folder_path)
                             if p["id"] == crumb["id"]), -1
                        )
                        if idx >= 0:
                            st.session_state.drive_folder_path = st.session_state.drive_folder_path[:idx + 1]
                            st.session_state.drive_current_folder = crumb
                        elif crumb["name"].startswith("🏠") or crumb["id"] in ("root", root_id):
                            st.session_state.drive_folder_path = [
                                {"id": root_id or "root",
                                 "name": cfg.get("root_folder_name", "Folder Gốc")}
                            ]
                            st.session_state.drive_current_folder = st.session_state.drive_folder_path[0]
                        st.session_state.drive_selected_file = None
                        st.rerun()

        if col_idx + 1 < len(cols) and i < len(unique_crumbs) - 1:
            with cols[col_idx + 1]:
                st.markdown("<span style='color:#aeaeb2;font-size:16px;line-height:32px'> › </span>",
                            unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Component: Print Panel
# ─────────────────────────────────────────────────────────────────────────────
def clean_print_cache(max_files: int = 30):
    """Giới hạn số lượng file trong cache ở mức max_files, xóa những file cũ nhất (không bị khóa)."""
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_dir = os.path.join(base_dir, "cache_print")
    if not os.path.exists(cache_dir):
        return

    try:
        files = []
        for item in os.listdir(cache_dir):
            path = os.path.join(cache_dir, item)
            if os.path.isfile(path):
                files.append((path, os.path.getmtime(path)))
        
        # Sắp xếp theo thời gian sửa đổi tăng dần (cũ nhất trước)
        files.sort(key=lambda x: x[1])
        
        # Nếu vượt quá hoặc bằng số lượng cho phép, xóa bớt các file cũ nhất để tạo chỗ cho file mới
        if len(files) >= max_files:
            to_delete_count = len(files) - (max_files - 1)
            deleted_count = 0
            for path, _ in files:
                if deleted_count >= to_delete_count:
                    break
                try:
                    os.remove(path)
                    deleted_count += 1
                except Exception:
                    # File đang bị khóa bởi Word/PDF reader, bỏ qua
                    pass
    except Exception:
        pass


def get_safe_cache_path(cache_dir: str, file_name: str) -> str:
    """Tạo đường dẫn file an toàn trong cache. Nếu file bị khóa, tự động thêm hậu tố (1), (2)..."""
    import os
    base, ext = os.path.splitext(file_name)
    temp_path = os.path.join(cache_dir, file_name)
    
    counter = 1
    while True:
        if not os.path.exists(temp_path):
            return temp_path
        try:
            # Thử mở file ở chế độ đọc/ghi để kiểm tra xem có bị khóa không
            with open(temp_path, "r+b"):
                pass
            return temp_path
        except IOError:
            # File bị khóa, đổi tên với hậu tố (counter)
            temp_path = os.path.join(cache_dir, f"{base} ({counter}){ext}")
            counter += 1


def _render_print_panel(file_meta: dict, prefix: str = "browser"):
    """Panel in ấn qua browser và máy in cục bộ."""
    file_name = file_meta.get("name", "")
    mime      = file_meta.get("mimeType", "")
    view_link = file_meta.get("webViewLink", "")
    dl_link   = file_meta.get("webContentLink", "")

    st.markdown("---")
    st.markdown(
        "<div class='print-panel'>",
        unsafe_allow_html=True
    )
    st.markdown(f"**🖨️ In file:** `{file_name}`")

    col_p1, col_p2, col_p3 = st.columns([1.5, 1.5, 1])

    with col_p1:
        if view_link:
            # Mở Google Docs viewer → Ctrl+P trong browser
            st.markdown(
                f"""
                <a href="{view_link}" target="_blank"
                   style="display:inline-flex;align-items:center;gap:8px;
                          background:#0071e3;color:#fff;border-radius:980px;
                          padding:10px 22px;font-size:14px;font-weight:600;
                          text-decoration:none;transition:all 0.18s ease;width:100%;justify-content:center;">
                    🌐 Mở Để In (Web Drive)
                </a>
                """,
                unsafe_allow_html=True
            )
            st.caption("💡 File sẽ mở trong Google Drive — nhấn **Ctrl+P** để in.")
        else:
            st.warning("⚠️ Không lấy được link xem file này.")

    with col_p2:
        # Tải về & mở trực tiếp bằng Word/PDF trên Windows
        svc = _get_service()
        if svc and st.button("⚡ Tải & Mở In Ngay (Cache)", key=f"{prefix}_local_open_{file_meta.get('id', 'f')}", use_container_width=True):
            try:
                with st.spinner("Đang tải & mở file…"):
                    # Dọn dẹp cache cũ trước, giới hạn tối đa 30 file
                    clean_print_cache(max_files=30)
                    
                    # Tạo thư mục cache
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    cache_dir = os.path.join(base_dir, "cache_print")
                    os.makedirs(cache_dir, exist_ok=True)
                    
                    # Tìm đường dẫn lưu file tạm an toàn (tránh đè lên file đang bị khóa)
                    temp_path = get_safe_cache_path(cache_dir, file_name)
                    actual_file_name = os.path.basename(temp_path)
                    
                    # Lưu file tạm
                    file_bytes = download_file(svc, file_meta["id"])
                    with open(temp_path, "wb") as f:
                        f.write(file_bytes)
                    
                    # Mở file trên Windows
                    if os.name == 'nt':
                        os.startfile(temp_path)
                        st.toast(f"⚡ Đã mở file `{actual_file_name}` bằng Word/PDF Reader!")
                        st.success(f"✅ Đã mở file cục bộ. Hãy bấm **Ctrl+P** trong phần mềm để in. File tạm sẽ tự động được dọn dẹp sau khi bạn tắt file.")
                    else:
                        st.warning("⚠️ Tính năng mở file trực tiếp chỉ khả dụng trên hệ điều hành Windows.")
            except Exception as e:
                st.error(f"❌ Lỗi mở file: {e}")

    with col_p3:
        if dl_link:
            # Tải về thủ công để lưu trữ lâu dài
            if svc and st.button("⬇️ Tải Về Máy", key=f"{prefix}_dl_{file_meta.get('id', 'f')}", use_container_width=True):
                try:
                    file_bytes = download_file(svc, file_meta["id"])
                    st.download_button(
                        label="💾 Lưu file",
                        data=file_bytes,
                        file_name=file_name,
                        mime=mime,
                        key=f"{prefix}_save_{file_meta.get('id', 'f')}"
                    )
                except Exception as e:
                    st.error(f"Lỗi tải file: {e}")

    st.markdown("</div>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Tab: Duyệt Hồ Sơ
# ─────────────────────────────────────────────────────────────────────────────
def _render_browser_tab():
    if not _require_connected():
        return

    svc = _get_service()
    cfg = load_drive_config()
    root_id = cfg.get("root_folder_id", "root")

    # Khởi tạo folder hiện tại nếu chưa có
    if st.session_state.drive_current_folder is None:
        st.session_state.drive_current_folder = {
            "id": root_id,
            "name": cfg.get("root_folder_name", "Folder Gốc")
        }
        st.session_state.drive_folder_path = [st.session_state.drive_current_folder]

    current = st.session_state.drive_current_folder

    # Reset ô lọc nhanh nếu người dùng chuyển sang thư mục khác
    current_id = current["id"] if current else None
    if current_id and st.session_state.get("_prev_browser_folder_id") != current_id:
        st.session_state["_prev_browser_folder_id"] = current_id
        st.session_state["browser_local_filter"] = ""

    # Header
    st.markdown(f"### 📁 {current['name']}")

    # Breadcrumb
    _render_breadcrumb()

    # Nút làm mới & Ô lọc nhanh trong thư mục
    col_rf, col_search = st.columns([1.5, 4.5])
    with col_rf:
        if st.button("🔄 Làm mới", key="browser_refresh", use_container_width=True):
            # Clear cache key để force reload
            for k in list(st.session_state.keys()):
                if k.startswith("_drive_cache_"):
                    del st.session_state[k]
            st.rerun()
    with col_search:
        local_filter = st.text_input(
            "Tìm nhanh trong thư mục...",
            placeholder="🔍 Nhập từ khóa để lọc nhanh folder hoặc file hiện tại…",
            key="browser_local_filter",
            label_visibility="collapsed"
        )

    st.divider()

    # ── Tải danh sách folder + file ─────────────────────────────────────────
    cache_key = f"_drive_cache_{current['id']}"
    if cache_key not in st.session_state:
        with st.spinner("Đang tải danh sách…"):
            try:
                folders = list_folders(svc, current["id"])
                files   = list_files(svc, current["id"])
                st.session_state[cache_key] = {"folders": folders, "files": files}
            except Exception as e:
                st.error(f"❌ Lỗi tải dữ liệu: {e}")
                return

    data    = st.session_state[cache_key]
    folders = data["folders"]
    files   = data["files"]

    # Áp dụng bộ lọc nhanh trong thư mục
    orig_folders_len = len(folders)
    orig_files_len = len(files)
    filter_q = local_filter.strip().lower() if local_filter else ""

    if filter_q:
        folders = [f for f in folders if filter_q in f.get("name", "").lower()]
        files   = [f for f in files if filter_q in f.get("name", "").lower()]

    # ── Hiển thị Folders ────────────────────────────────────────────────────
    if folders:
        st.markdown(f"**📁 Folders ({len(folders)})**")
        for folder in folders:
            col_icon, col_info, col_btn = st.columns([0.5, 6, 1.5])
            with col_icon:
                st.markdown("📁", unsafe_allow_html=True)
            with col_info:
                # Tô sáng từ khóa tìm kiếm trong tên folder
                fname = folder.get("name", "")
                if filter_q and filter_q in fname.lower():
                    idx = fname.lower().index(filter_q)
                    fname_hl = (
                        fname[:idx]
                        + f"<mark style='background:#fff3cd;border-radius:3px;padding:0 2px'>"
                        + fname[idx:idx + len(filter_q)]
                        + "</mark>"
                        + fname[idx + len(filter_q):]
                    )
                else:
                    fname_hl = fname
                st.markdown(
                    f"<div class='drive-title'>{fname_hl}</div>"
                    f"<div class='drive-meta'>Sửa lần cuối: {format_datetime(folder.get('modifiedTime', ''))}</div>",
                    unsafe_allow_html=True
                )
            with col_btn:
                if st.button("Mở →", key=f"open_folder_{folder['id']}", use_container_width=True):
                    st.session_state.drive_current_folder = {"id": folder["id"], "name": folder["name"]}
                    st.session_state.drive_folder_path.append({"id": folder["id"], "name": folder["name"]})
                    st.session_state.drive_selected_file = None
                    # Clear cache folder con
                    cache_sub = f"_drive_cache_{folder['id']}"
                    if cache_sub in st.session_state:
                        del st.session_state[cache_sub]
                    st.rerun()
            st.markdown("<hr style='margin:4px 0;border-color:rgba(60,60,67,0.08)'>", unsafe_allow_html=True)

    else:
        if orig_folders_len > 0:
            st.markdown("*Không có folder con nào khớp từ khóa*")
        elif not files and orig_files_len == 0:
            st.info("📂 Folder này chưa có nội dung.")
        else:
            st.markdown("*Không có folder con*")

    # ── Hiển thị Files ──────────────────────────────────────────────────────
    if files:
        st.markdown(f"**📄 Files ({len(files)})**")
        for f in files:
            col_icon, col_info, col_actions = st.columns([0.5, 5, 2.5])
            icon = get_file_icon(f.get("mimeType", ""))
            size = format_file_size(f.get("size"))
            mtime = format_datetime(f.get("modifiedTime", ""))
            is_selected = (
                st.session_state.drive_selected_file is not None
                and st.session_state.drive_selected_file.get("id") == f["id"]
            )

            with col_icon:
                st.markdown(icon)
            with col_info:
                # Tô sáng từ khóa tìm kiếm trong tên file
                fname = f.get("name", "")
                if filter_q and filter_q in fname.lower():
                    idx = fname.lower().index(filter_q)
                    fname_hl = (
                        fname[:idx]
                        + f"<mark style='background:#fff3cd;border-radius:3px;padding:0 2px'>"
                        + fname[idx:idx + len(filter_q)]
                        + "</mark>"
                        + fname[idx + len(filter_q):]
                    )
                else:
                    fname_hl = fname
                selected_style = "color:#0071e3;" if is_selected else ""
                st.markdown(
                    f"<div class='drive-title' style='{selected_style}'>{fname_hl}</div>"
                    f"<div class='drive-meta'>{size} &nbsp;|&nbsp; {mtime}</div>",
                    unsafe_allow_html=True
                )
            with col_actions:
                ac1, ac2 = st.columns(2)
                with ac1:
                    if is_printable(f.get("mimeType", "")):
                        select_label = "✅ Đã chọn" if is_selected else "🖨️ In"
                        if st.button(select_label, key=f"sel_file_{f['id']}", use_container_width=True):
                            if is_selected:
                                st.session_state.drive_selected_file = None
                            else:
                                st.session_state.drive_selected_file = f
                            st.rerun()
                with ac2:
                    if f.get("webViewLink"):
                        st.markdown(
                            f"<a href='{f['webViewLink']}' target='_blank' "
                            f"style='display:block;text-align:center;padding:8px 4px;"
                            f"font-size:12px;color:#0071e3;font-weight:600;"
                            f"text-decoration:none;'>🔗 Xem</a>",
                            unsafe_allow_html=True
                        )
            st.markdown("<hr style='margin:4px 0;border-color:rgba(60,60,67,0.08)'>", unsafe_allow_html=True)
    else:
        if orig_files_len > 0:
            st.markdown("*Không có file nào khớp từ khóa*")

    # ── Print Panel ──────────────────────────────────────────────────────────
    if st.session_state.drive_selected_file:
        _render_print_panel(st.session_state.drive_selected_file, prefix="browser")


# ─────────────────────────────────────────────────────────────────────────────
#  Tab: Tìm Kiếm
# ─────────────────────────────────────────────────────────────────────────────
def _render_search_tab():
    if not _require_connected():
        return

    svc = _get_service()
    cfg = load_drive_config()
    root_id = cfg.get("root_folder_id", "")

    st.markdown("### 🔍 Tìm Kiếm Hồ Sơ")

    col_q, col_btn = st.columns([5.5, 1.5])
    with col_q:
        query = st.text_input(
            "Từ khóa tìm kiếm",
            placeholder="Nhập tên file hoặc mã BFO cần tìm…",
            key="search_query_input",
            label_visibility="collapsed"
        )
    with col_btn:
        st.markdown("<div style='margin-top:4px'>", unsafe_allow_html=True)
        do_search = st.button("🔍 Tìm Kiếm", key="do_search_btn",
                              use_container_width=True, type="primary")
        st.markdown("</div>", unsafe_allow_html=True)

    current_query = query.strip()
    last_query = st.session_state.get("_last_search_query", "")

    # Nếu ô tìm kiếm trống, xóa sạch kết quả cũ
    if not current_query:
        st.session_state["_last_search_query"] = ""
        st.session_state["_last_search_results"] = None

    # Kích hoạt tìm kiếm nếu nhấn nút Tìm Kiếm, hoặc gõ từ khóa mới (Enter)
    trigger_search = do_search or (
        current_query and current_query != last_query
    )

    if trigger_search:
        st.session_state["_last_search_query"] = current_query

        with st.spinner(f"Đang tìm kiếm '{current_query}'…"):
            try:
                results = search_files_global(svc, root_id, name_query=current_query)
                st.session_state["_last_search_results"] = results
            except Exception as e:
                st.error(f"❌ Lỗi tìm kiếm: {e}")
                return

    # Lấy dữ liệu từ session state để hiển thị kết quả
    results = st.session_state.get("_last_search_results")
    searched_query = st.session_state.get("_last_search_query")

    if searched_query:
        if not results:
            st.info(f"🔍 Không tìm thấy kết quả nào cho: **{searched_query}**")
            return

        st.success(f"✅ Tìm thấy **{len(results)}** kết quả")
        st.divider()

        for f in results:
            icon  = get_file_icon(f.get("mimeType", ""))
            size  = format_file_size(f.get("size"))
            mtime = format_datetime(f.get("modifiedTime", ""))

            # Tô sáng từ khóa trong tên file
            fname  = f.get("name", "")
            q_low  = searched_query.lower()
            f_low  = fname.lower()
            if q_low in f_low:
                idx    = f_low.index(q_low)
                fname_hl = (
                    fname[:idx]
                    + f"<mark style='background:#fff3cd;border-radius:3px;padding:0 2px'>"
                    + fname[idx:idx + len(searched_query)]
                    + "</mark>"
                    + fname[idx + len(searched_query):]
                )
            else:
                fname_hl = fname

            col_i, col_info, col_act = st.columns([0.5, 5.5, 2])
            with col_i:
                st.markdown(icon)
            with col_info:
                st.markdown(
                    f"<div class='drive-title'>{fname_hl}</div>"
                    f"<div class='drive-meta'>{size} &nbsp;|&nbsp; {mtime}</div>",
                    unsafe_allow_html=True
                )
            with col_act:
                ac1, ac2 = st.columns(2)
                with ac1:
                    if is_printable(f.get("mimeType", "")):
                        is_sel = (
                            st.session_state.drive_selected_file is not None
                            and st.session_state.drive_selected_file.get("id") == f["id"]
                        )
                        lbl = "✅ Đã chọn" if is_sel else "🖨️ In"
                        if st.button(lbl, key=f"sr_sel_{f['id']}", use_container_width=True):
                            st.session_state.drive_selected_file = None if is_sel else f
                            st.rerun()
                with ac2:
                    if f.get("webViewLink"):
                        st.markdown(
                            f"<a href='{f['webViewLink']}' target='_blank' "
                            f"style='display:block;text-align:center;padding:8px 4px;"
                            f"font-size:12px;color:#0071e3;font-weight:600;"
                            f"text-decoration:none;'>🔗 Xem</a>",
                            unsafe_allow_html=True
                        )

            st.markdown("<hr style='margin:4px 0;border-color:rgba(60,60,67,0.08)'>", unsafe_allow_html=True)

        # Print panel
        if st.session_state.drive_selected_file:
            _render_print_panel(st.session_state.drive_selected_file, prefix="search")


# ─────────────────────────────────────────────────────────────────────────────
#  Tab: Tải Lên & Tạo Folder
# ─────────────────────────────────────────────────────────────────────────────
def _render_upload_tab():
    if not _require_connected():
        return

    svc = _get_service()
    cfg = load_drive_config()
    root_id = cfg.get("root_folder_id", "root")

    st.markdown("### ➕ Tải Lên & Tạo Folder")

    # ── Chọn folder đích ────────────────────────────────────────────────────
    st.markdown("**📂 Folder đích**")

    col_fd1, col_fd2 = st.columns([3, 1])
    with col_fd1:
        # Lấy breadcrumb hiện tại
        current = st.session_state.drive_current_folder
        if current:
            path_str = " › ".join([p["name"] for p in st.session_state.drive_folder_path])
            st.markdown(
                f"<div style='background:#f9f9fb;border:1px solid rgba(60,60,67,0.1);"
                f"border-radius:10px;padding:10px 14px;font-size:13px;color:#1d1d1f'>"
                f"📁 {path_str}</div>",
                unsafe_allow_html=True
            )
        else:
            st.info("Chưa chọn folder. Hãy duyệt đến folder trong tab **Duyệt Hồ Sơ** trước.")

    with col_fd2:
        target_folder_id_input = st.text_input(
            "Hoặc nhập ID folder",
            placeholder="ID folder Drive",
            key="upload_target_id",
            label_visibility="collapsed"
        )

    # Xác định folder đích thực tế
    if target_folder_id_input.strip():
        target_id   = target_folder_id_input.strip()
        target_name = f"Folder [{target_id[:12]}…]"
    elif current:
        target_id   = current["id"]
        target_name = current["name"]
    else:
        target_id   = root_id
        target_name = cfg.get("root_folder_name", "Folder Gốc")

    st.caption(f"🎯 Folder đích: **{target_name}**")

    st.divider()

    # ── Tạo Folder Mới ──────────────────────────────────────────────────────
    st.markdown("**📁 Tạo Folder Mới**")
    col_nf1, col_nf2 = st.columns([4, 1])
    with col_nf1:
        new_folder_name = st.text_input(
            "Tên folder mới",
            placeholder="VD: Hồ Sơ Tháng 6/2025",
            key="new_folder_name_input",
            label_visibility="collapsed"
        )
    with col_nf2:
        if st.button("➕ Tạo", key="create_folder_btn", use_container_width=True, type="primary"):
            if not new_folder_name.strip():
                st.warning("⚠️ Nhập tên folder.")
            else:
                try:
                    with st.spinner("Đang tạo folder…"):
                        result = create_folder(svc, new_folder_name.strip(), target_id)
                    st.success(f"✅ Đã tạo folder: **{result['name']}**")
                    # Xóa cache để refresh
                    cache_key = f"_drive_cache_{target_id}"
                    if cache_key in st.session_state:
                        del st.session_state[cache_key]
                except Exception as e:
                    st.error(f"❌ Lỗi tạo folder: {e}")

    st.divider()

    # ── Tải File Lên ────────────────────────────────────────────────────────
    st.markdown("**📤 Tải File Lên Folder**")
    uploaded_files = st.file_uploader(
        "Chọn file (hỗ trợ nhiều file cùng lúc)",
        accept_multiple_files=True,
        type=["docx", "doc", "pdf", "xlsx", "xls", "jpg", "jpeg", "png", "txt"],
        key="upload_files_input"
    )

    if uploaded_files:
        st.markdown(f"📋 Đã chọn **{len(uploaded_files)}** file:")
        for uf in uploaded_files:
            st.caption(f"• {uf.name} ({format_file_size(uf.size)})")

        if st.button(
            f"⬆️ Tải Lên {len(uploaded_files)} File → {target_name}",
            key="do_upload_btn",
            type="primary"
        ):
            progress = st.progress(0)
            success_count = 0
            errors = []

            for i, uf in enumerate(uploaded_files):
                try:
                    progress.progress((i) / len(uploaded_files), text=f"Đang tải: {uf.name}…")
                    file_bytes = uf.getvalue()
                    result = upload_file(svc, file_bytes, uf.name, target_id)
                    success_count += 1
                    st.success(f"✅ {uf.name}")
                except Exception as e:
                    errors.append(f"{uf.name}: {e}")
                    st.error(f"❌ {uf.name}: {e}")

            progress.progress(1.0, text="Hoàn tất!")

            if success_count > 0:
                # Xóa cache để refresh
                cache_key = f"_drive_cache_{target_id}"
                if cache_key in st.session_state:
                    del st.session_state[cache_key]

            if errors:
                st.warning(f"⚠️ {success_count}/{len(uploaded_files)} file thành công. {len(errors)} lỗi.")
            else:
                st.success(f"✅ Đã tải lên {success_count}/{len(uploaded_files)} file thành công!")


# ─────────────────────────────────────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────────────────────────────────────
def render_quan_ly_ho_so():
    """Hàm render chính, được gọi từ main.py."""
    st.markdown(_CSS, unsafe_allow_html=True)
    _init_state()

    # ── Header ──────────────────────────────────────────────────────────────
    col_h1, col_h2 = st.columns([5, 1])
    with col_h1:
        st.markdown(
            "<h2 style='margin:0;letter-spacing:-0.03em;color:#1d1d1f'>"
            "📂 Quản Lý & In Hồ Sơ"
            "</h2>"
            "<p style='color:#86868b;font-size:14px;margin:4px 0 0 0'>"
            "Duyệt, tìm kiếm, tải lên và in hồ sơ từ Google Drive"
            "</p>",
            unsafe_allow_html=True
        )
    with col_h2:
        status_html = (
            "<span class='drive-badge drive-badge-green'>🟢 Drive</span>"
            if st.session_state.drive_connected
            else "<span class='drive-badge drive-badge-orange'>🔴 Chưa kết nối</span>"
        )
        st.markdown(f"<div style='text-align:right;padding-top:8px'>{status_html}</div>",
                    unsafe_allow_html=True)

    st.divider()

    # ── Tabs ────────────────────────────────────────────────────────────────
    tab_browser, tab_search, tab_upload, tab_settings = st.tabs([
        "📁 Duyệt Hồ Sơ",
        "🔍 Tìm Kiếm",
        "⬆️ Tải Lên & Tạo Folder",
        "⚙️ Cài Đặt Drive"
    ])

    with tab_browser:
        _render_browser_tab()

    with tab_search:
        _render_search_tab()

    with tab_upload:
        _render_upload_tab()

    with tab_settings:
        _render_settings_tab()
