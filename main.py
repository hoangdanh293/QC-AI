import streamlit as st

# NHẬP KHẨU GIAO DIỆN (Bổ sung ui_reagent)
from ui_modules import ui_ho_so, ui_thu_vien, ui_chi_tieu, ui_api_key, ui_tcnl, ui_sop_library, ui_tro_ly, ui_phong_cach, ui_reagent, ui_quan_ly_ho_so

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

# CSS Dùng chung (Apple Human Interface Guidelines)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    :root {
        --font-apple: "Inter", -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;
        --apple-bg: #f2f2f7;
        --apple-surface: #ffffff;
        --apple-surface-2: #f9f9fb;
        --apple-text-main: #1d1d1f;
        --apple-text-secondary: #3a3a3c;
        --apple-text-muted: #86868b;
        --apple-text-placeholder: #aeaeb2;
        --apple-blue: #0071e3;
        --apple-blue-hover: #0077ed;
        --apple-blue-light: #e8f1fd;
        --apple-green: #34c759;
        --apple-red: #ff3b30;
        --apple-orange: #ff9500;
        --apple-separator: rgba(60, 60, 67, 0.12);
        --apple-radius-xs: 6px;
        --apple-radius-sm: 10px;
        --apple-radius-md: 13px;
        --apple-radius-lg: 18px;
        --apple-radius-xl: 24px;
        --shadow-xs: 0 1px 2px rgba(0,0,0,0.04);
        --shadow-sm: 0 2px 8px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
        --shadow-md: 0 4px 16px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.04);
        --shadow-lg: 0 8px 32px rgba(0,0,0,0.10), 0 2px 8px rgba(0,0,0,0.06);
    }

    /* ─── Base ─── */
    .stApp, html, body, [class*="css"] {
        background-color: var(--apple-bg) !important;
        color: var(--apple-text-main) !important;
        font-family: var(--font-apple) !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }
    .block-container {
        padding-top: 3.5rem !important;
        padding-bottom: 3rem !important;
        max-width: 94% !important;
    }
    header[data-testid="stHeader"] {
        background-color: rgba(0, 0, 0, 0) !important;
    }
    div[data-testid="stVerticalBlock"] { gap: 0.4rem !important; }

    /* ─── Cards & Containers ─── */
    div[data-testid="stContainer"] {
        background-color: var(--apple-surface) !important;
        border-radius: var(--apple-radius-md) !important;
        border: 1px solid var(--apple-separator) !important;
        box-shadow: var(--shadow-sm) !important;
        padding: 16px !important;
    }
    div[data-testid="stExpander"] {
        background-color: var(--apple-surface) !important;
        border-radius: var(--apple-radius-md) !important;
        border: 1px solid var(--apple-separator) !important;
        box-shadow: var(--shadow-xs) !important;
        overflow: hidden;
    }
    div[data-testid="stExpander"] summary {
        font-weight: 600 !important;
        font-size: 14px !important;
        color: var(--apple-text-main) !important;
        padding: 14px 16px !important;
    }

    /* ─── Inputs ─── */
    .stTextInput input {
        background-color: var(--apple-surface) !important;
        border: 1px solid var(--apple-separator) !important;
        border-radius: var(--apple-radius-sm) !important;
        color: var(--apple-text-main) !important;
        font-size: 15px !important;
        font-weight: 400 !important;
        height: 40px !important;
        padding: 0 12px !important;
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    .stTextInput input:focus {
        border-color: var(--apple-blue) !important;
        box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.15) !important;
        outline: none !important;
    }
    .stTextInput input::placeholder { color: var(--apple-text-placeholder) !important; }

    .stTextArea textarea {
        background-color: var(--apple-surface) !important;
        border: 1px solid var(--apple-separator) !important;
        border-radius: var(--apple-radius-sm) !important;
        color: var(--apple-text-main) !important;
        font-size: 14px !important;
        font-weight: 400 !important;
        line-height: 1.6 !important;
        padding: 10px 12px !important;
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    .stTextArea textarea:focus {
        border-color: var(--apple-blue) !important;
        box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.15) !important;
    }
    div[data-baseweb="textarea"][disabled] textarea,
    .stTextArea textarea:disabled {
        background-color: var(--apple-surface-2) !important;
        color: var(--apple-text-secondary) !important;
        cursor: default !important;
    }

    /* ─── Selectbox ─── */
    .stSelectbox div[data-baseweb="select"] {
        background-color: var(--apple-surface) !important;
        border: 1px solid var(--apple-separator) !important;
        border-radius: var(--apple-radius-sm) !important;
        font-size: 15px !important;
    }
    .stSelectbox div[data-baseweb="select"]:focus-within {
        border-color: var(--apple-blue) !important;
        box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.15) !important;
    }

    /* ─── Labels ─── */
    .stTextInput label, .stSelectbox label, .stFileUploader label,
    .stTextArea label, .stNumberInput label, .stSlider label {
        font-size: 13px !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em !important;
        color: var(--apple-text-secondary) !important;
        margin-bottom: 4px !important;
        text-transform: uppercase;
    }
    .stMarkdown p strong { color: var(--apple-text-main) !important; font-size: 15px !important; }
    .stMarkdown p { color: var(--apple-text-muted); font-size: 14px !important; line-height: 1.5; }
    h1, h2, h3, h4 { letter-spacing: -0.025em !important; }

    /* ─── Checkboxes ─── */
    div[data-testid="stCheckbox"] label span,
    div[data-testid="stCheckbox"] label div,
    div[data-testid="stCheckbox"] label p {
        color: var(--apple-text-main) !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }

    /* ─── File Uploader ─── */
    div[data-testid="stFileUploadDropzone"] {
        background-color: var(--apple-surface) !important;
        border: 2px dashed var(--apple-separator) !important;
        border-radius: var(--apple-radius-md) !important;
        transition: border-color 0.15s ease;
    }
    div[data-testid="stFileUploadDropzone"]:hover { border-color: var(--apple-blue) !important; }

    /* ─── Buttons ─── */
    .stButton > button {
        height: 44px !important;
        font-weight: 600 !important;
        font-size: 15px !important;
        font-family: var(--font-apple) !important;
        border: none !important;
        border-radius: 980px !important;
        cursor: pointer;
        transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1) !important;
        letter-spacing: -0.01em !important;
    }
    /* Primary buttons */
    .stButton > button[kind="primary"],
    .stButton > button:first-child {
        background-color: var(--apple-blue) !important;
        color: #ffffff !important;
        box-shadow: 0 1px 3px rgba(0, 113, 227, 0.3), 0 1px 2px rgba(0,0,0,0.08) !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stButton > button:first-child:hover {
        background-color: var(--apple-blue-hover) !important;
        transform: scale(0.98);
        box-shadow: 0 2px 8px rgba(0, 113, 227, 0.35) !important;
    }
    /* Secondary buttons */
    .stButton > button[kind="secondary"] {
        background-color: #e5e5ea !important;
        color: var(--apple-text-main) !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background-color: #d1d1d6 !important;
        transform: scale(0.98);
    }
    /* Sidebar buttons */
    section[data-testid="stSidebar"] .stButton > button {
        height: 36px !important;
        font-size: 13px !important;
        border-radius: var(--apple-radius-sm) !important;
    }

    /* ─── Progress Bar ─── */
    .apple-progress-container {
        background-color: #e5e5ea;
        border-radius: 980px;
        height: 6px;
        width: 100%;
        overflow: hidden;
        margin-top: 8px;
        margin-bottom: 20px;
    }
    .apple-progress-bar {
        background: linear-gradient(90deg, var(--apple-blue), #34aadc);
        height: 100%;
        border-radius: 980px;
        transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
    }

    /* ─── Node Cards ─── */
    .node-card {
        background-color: var(--apple-surface);
        border: 1px solid var(--apple-separator);
        border-radius: var(--apple-radius-md);
        padding: 14px 18px;
        margin-bottom: 10px;
        box-shadow: var(--shadow-xs);
        display: flex;
        align-items: center;
        gap: 14px;
        transition: all 0.25s ease;
    }
    .node-card.pending { opacity: 0.45; filter: grayscale(80%); }
    .node-card.running {
        border-left: 4px solid var(--apple-blue);
        background: linear-gradient(135deg, #f0f7ff 0%, #ffffff 100%);
        transform: scale(1.005);
        box-shadow: var(--shadow-sm) !important;
    }
    .node-card.success { border-left: 4px solid var(--apple-green); }
    .node-card.error { border-left: 4px solid var(--apple-red); background-color: #fff5f5; }
    .node-icon { font-size: 22px; flex-shrink: 0; }
    .node-text-title { font-weight: 600; font-size: 14px; color: var(--apple-text-main); margin-bottom: 2px; letter-spacing: -0.01em; }
    .node-text-desc { font-size: 12px; color: var(--apple-text-muted); line-height: 1.4; }

    /* ─── Translated Box ─── */
    .translated-box {
        background-color: var(--apple-surface);
        padding: 20px;
        border-radius: var(--apple-radius-lg);
        border: 1px solid var(--apple-separator);
        box-shadow: var(--shadow-sm);
        font-size: 14px;
        max-height: 400px;
        overflow-y: auto;
        white-space: pre-wrap;
        margin-bottom: 20px;
        color: var(--apple-text-main);
        line-height: 1.65;
    }

    /* ─── Scrollbar ─── */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #c7c7cc; border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: #8e8e93; }

    /* ─── Sidebar ─── */
    section[data-testid="stSidebar"] {
        background-color: rgba(242, 242, 247, 0.95) !important;
        border-right: 1px solid var(--apple-separator) !important;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] label {
        font-size: 14px !important;
        font-weight: 500 !important;
        color: var(--apple-text-main) !important;
        padding: 8px 0 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {
        gap: 4px !important;
    }

    /* ─── Alerts / Info boxes ─── */
    div[data-testid="stAlert"] {
        border-radius: var(--apple-radius-sm) !important;
        border: none !important;
        font-size: 14px !important;
    }

    /* ─── Data Editor / Table ─── */
    div[data-testid="stDataEditor"] {
        border-radius: var(--apple-radius-sm) !important;
        overflow: hidden;
        border: 1px solid var(--apple-separator) !important;
    }

    /* ─── Divider ─── */
    hr { border-color: var(--apple-separator) !important; margin: 16px 0 !important; }

    /* ─── Number input ─── */
    div[data-testid="stNumberInput"] input {
        border-radius: var(--apple-radius-sm) !important;
        border: 1px solid var(--apple-separator) !important;
        height: 38px !important;
    }

    /* ─── Tabs ─── */
    div[data-testid="stTabs"] button {
        font-size: 14px !important;
        font-weight: 600 !important;
        letter-spacing: -0.01em !important;
    }

    /* ─── Card Action Column Fix ─── */
    /* Đảm bảo cột nút hành động trong card không bị đẩy xuống */
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        display: flex !important;
        flex-direction: column !important;
        justify-content: flex-start !important;
    }
    /* Bỏ khoảng trắng thừa giữa các element trong vertical block */
    div[data-testid="stVerticalBlock"] {
        gap: 0.3rem !important;
    }
    /* Container lồng nhau: không thêm padding ngoài */
    div[data-testid="stContainer"] div[data-testid="stContainer"] {
        padding: 10px !important;
        margin: 0 !important;
    }
    /* Căn chỉnh các nút nhỏ (icon button) không bị kéo dài */
    div[data-testid="column"]:last-child .stButton > button {
        min-height: 38px !important;
        height: auto !important;
        padding: 6px 10px !important;
    }
    </style>
""", unsafe_allow_html=True)


# Thanh Điều Hướng Bên Trái
with st.sidebar:
    st.markdown("<h3 style='text-align: center; color: #1d1d1f;'>⚙️ TRUNG TÂM ĐIỀU KHIỂN</h3>", unsafe_allow_html=True)
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
            "🔐 Quản Lý API Keys & Cấu hình"
        ],
        index=0
    )
    
    st.divider()
    st.markdown("<h4 style='color: #1d1d1f; font-size: 14px; font-weight: 600; margin-bottom: 8px;'>HỆ THỐNG TRẠNG THÁI</h4>", unsafe_allow_html=True)
    
    col_restart, col_shutdown = st.columns(2)
    with col_restart:
        if st.button("🔄 Cập nhật", help="Cập nhật code mới và tự động nạp lại hệ thống", use_container_width=True):
            import os
            restart_file = os.path.join(os.path.dirname(__file__), "restart.txt")
            with open(restart_file, "w") as f:
                f.write("restart")
            st.info("Đang nạp lại...")
            st.rerun()
            
    with col_shutdown:
        if st.button("🔴 Tắt", help="Đóng hoàn toàn dịch vụ chạy ngầm", use_container_width=True):
            import os
            shutdown_file = os.path.join(os.path.dirname(__file__), "shutdown.txt")
            with open(shutdown_file, "w") as f:
                f.write("shutdown")
            st.warning("Hệ thống đã tắt.")
            st.stop()
            
    st.divider()
    st.caption("Phiên bản nội bộ QC CPC1HN v3.6 (Modular)")

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
elif app_mode == "🔐 Quản Lý API Keys & Cấu hình":
    ui_api_key.render_api_key_manager()

# Gọi Bong bóng nổi Trợ lý AI ở mọi chức năng của hệ thống
ui_tro_ly.render_floating_assistant()