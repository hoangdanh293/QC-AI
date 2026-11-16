import os
import streamlit as st

# NHẬP KHẨU GIAO DIỆN & THEME
from core.ui_theme import inject_theme
from core import updater
from ui_modules import (
    ui_ho_so,
    ui_thu_vien,
    ui_chi_tieu,
    ui_api_key,
    ui_tcnl,
    ui_sop_library,
    ui_tro_ly,
    ui_phong_cach,
    ui_reagent,
    ui_quan_ly_ho_so,
)

# Cấu hình chung cho toàn bộ app
st.set_page_config(page_title="QC AI CPC1HN", layout="wide", page_icon="logo.ico")

# Khởi tạo các biến toàn cục (Session State cơ sở)
if "is_done" not in st.session_state:
    st.session_state.is_done = False
    st.session_state.translated_text = ""
    st.session_state.extra_text_display = ""
    st.session_state.json_data = {}
    st.session_state.final_io = None
    st.session_state.file_name = "KQ.docx"

# Áp dụng Design System & Motion Tokens dùng chung
inject_theme()


# Thanh Điều Hướng Bên Trái
with st.sidebar:
    st.markdown("<h3 style='text-align: center; color: #111827;'>⚙️ TRUNG TÂM ĐIỀU KHIỂN</h3>", unsafe_allow_html=True)
    st.divider()

    app_mode = st.radio(
        "Chọn chức năng làm việc:",
        [
            "📄 Lập Hồ Sơ Kiểm Nghiệm",
            "📚 Tạo Tiêu Chuẩn Nguyên Liệu",
            "📂 Quản Lý & In Hồ Sơ",
            "📝 Quản Lý Chỉ Tiêu Và Thuật Ngữ",
            "🗂️ Quản Lý Thư Viện Phương Pháp",
            "📖 Thư Viện Mẫu",
            "🧪 Thư Viện Dung Dịch & Thuốc Thử",
            "🎨 Training AI",
            "🔑 Quản Lý API Keys & Cấu hình",
        ],
        index=0,
    )

    st.divider()
    st.markdown(
        "<h4 style='color: #111827; font-size: 13px; font-weight: 600; margin-bottom: 8px;'>HỆ THỐNG & CẬP NHẬT</h4>",
        unsafe_allow_html=True,
    )

    if st.button("🔍 Kiểm tra cập nhật GitHub", type="primary", use_container_width=True, key="sb_check_upd"):
        with st.spinner("Đang kiểm tra..."):
            st.session_state["sidebar_upd_info"] = updater.check_for_updates()

    sb_upd = st.session_state.get("sidebar_upd_info")
    if sb_upd:
        if not sb_upd.get("ok"):
            st.error(sb_upd.get("error"))
        elif not sb_upd.get("has_update"):
            st.success(f"Đã là bản mới nhất ({sb_upd.get('remote_short_sha')})")
        else:
            st.info(f"🆕 Bản mới: `{sb_upd.get('remote_short_sha')}` — {sb_upd.get('commit_message')}")
            if st.button("⬇️ Cập nhật ngay", type="primary", use_container_width=True, key="sb_apply_upd"):
                with st.spinner("Đang tải và cập nhật..."):
                    res = updater.apply_update(remote_info=sb_upd)
                if res.get("ok"):
                    st.session_state.pop("sidebar_upd_info", None)
                    st.success("Cập nhật xong! Đang nạp lại...")
                    updater.trigger_restart()
                    st.stop()
                else:
                    st.error(res.get("message"))

    col_restart, col_shutdown = st.columns(2)
    with col_restart:
        if st.button("🔄 Nạp lại", type="secondary", help="Khởi động lại dịch vụ Streamlit", use_container_width=True):
            updater.trigger_restart()
            st.info("Đang nạp lại...")
            st.rerun()

    with col_shutdown:
        if st.button("🔴 Tắt", type="secondary", help="Đóng hoàn toàn dịch vụ chạy ngầm", use_container_width=True):
            shutdown_file = os.path.join(os.path.dirname(__file__), "shutdown.txt")
            with open(shutdown_file, "w") as f:
                f.write("shutdown")
            st.warning("Hệ thống đã tắt.")
            st.stop()

    st.divider()
    _local_ver = updater.get_local_version()
    _short_sha = (_local_ver.get("commit_sha") or "")[:7]
    _ver_suffix = f" • {_short_sha}" if _short_sha else ""
    st.markdown(
        f"<div style='text-align:center;'><span class='qc-version-pill'>QC CPC1HN v3.7{_ver_suffix}</span></div>",
        unsafe_allow_html=True,
    )

# Điều hướng (Routing)
if app_mode == "📄 Lập Hồ Sơ Kiểm Nghiệm":
    ui_ho_so.render_ho_so()
elif app_mode == "📚 Tạo Tiêu Chuẩn Nguyên Liệu":
    ui_tcnl.render_tcnl()
elif app_mode == "📂 Quản Lý & In Hồ Sơ":
    ui_quan_ly_ho_so.render_quan_ly_ho_so()
elif app_mode == "📝 Quản Lý Chỉ Tiêu Và Thuật Ngữ":
    ui_chi_tieu.render_chi_tieu()
elif app_mode == "🗂️ Quản Lý Thư Viện Phương Pháp":
    ui_thu_vien.render_thu_vien()
elif app_mode == "📖 Thư Viện Mẫu":
    ui_sop_library.render_sop_library()
elif app_mode == "🧪 Thư Viện Dung Dịch & Thuốc Thử":
    ui_reagent.render_reagent_library()
elif app_mode == "🎨 Training AI":
    ui_phong_cach.render_phong_cach()
elif app_mode == "🔑 Quản Lý API Keys & Cấu hình":
    ui_api_key.render_api_key_manager()

# Gọi Bong bóng nổi Trợ lý AI ở mọi chức năng của hệ thống
ui_tro_ly.render_floating_assistant()
