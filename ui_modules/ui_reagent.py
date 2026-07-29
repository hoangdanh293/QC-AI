import streamlit as st
import streamlit.components.v1 as components
import json
import os
import time
import re
import io
import csv
from datetime import datetime
from core.ai_handler import call_ai_engine
from core.key_manager import load_model_config
from core.doc_processor import prepare_file_for_ai

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_paste_component_dir = os.path.join(_parent_dir, "core", "paste_image_component")
paste_image = components.declare_component("paste_image_v4", path=_paste_component_dir)

REAGENT_FILE = "reagent_library.json"
PAGE_SIZE = 10

LOAI_OPTIONS = [
    "Thuốc thử",
    "Dung dịch chuẩn",
    "Chỉ thị",
    "Buffer / Dung dịch đệm",
    "Khác",
]

LOAI_STYLE = {
    "Thuốc thử":              {"color": "#0071e3", "bg": "#e8f1fd", "icon": "🔵"},
    "Dung dịch chuẩn":        {"color": "#1a7f37", "bg": "#dcfce7", "icon": "🟢"},
    "Chỉ thị":                {"color": "#9a6700", "bg": "#fef9c3", "icon": "🟡"},
    "Buffer / Dung dịch đệm": {"color": "#7e22ce", "bg": "#f3e8ff", "icon": "🟠"},
    "Khác":                   {"color": "#86868b", "bg": "#f5f5f7", "icon": "⚪"},
}

DEFAULT_REAGENTS = {
    "lead_standard_solution_1_ppm_pb": {
        "ten_tieng_anh": "Lead Standard Solution (1 ppm Pb)",
        "ten_tieng_viet": "Dung dịch Chì chuẩn (1 ppm Pb)",
        "duoc_dien": "BP 2025 / USP 43",
        "loai": "Dung dịch chuẩn",
        "cach_pha": (
            "- Hòa tan 1,60 g Chì nitrat [Pb(NO\u2083)\u2082] trong nước, thêm 1 mL acid nitric khan và pha loãng "
            "thành 1000 mL bằng nước để được dung dịch chì gốc.\n"
            "- Trước khi dùng, hút chính xác 1,0 mL dung dịch chì gốc trên và pha loãng thành 1000,0 mL bằng nước.\n"
            "- Dung dịch chứa lượng chì tương đương với 1 microgam Pb trong 1 mL. Chuẩn bị ngay trước khi dùng."
        ),
        "nguon_goc": "BP Appendix I C / USP Reagents",
        "ngay_cap_nhat": "",
    },
    "barium_sulfate_reagent": {
        "ten_tieng_anh": "Barium Sulfate Reagent",
        "ten_tieng_viet": "Thuốc thử Bari sulfat",
        "duoc_dien": "BP 2025 / DĐVN V",
        "loai": "Thuốc thử",
        "cach_pha": (
            "- Lấy 15 mL dung dịch bari clorid 25% (TT) và 4,5 mL dung dịch chuẩn sulfat 10 ppm trong ethanol 30%.\n"
            "- Lắc đều và để yên trong 1 phút.\n"
            "- Dung dịch này phải được chuẩn bị ngay trước khi dùng."
        ),
        "nguon_goc": "BP Appendix I C",
        "ngay_cap_nhat": "",
    },
    "starch_indicator_solution": {
        "ten_tieng_anh": "Starch Indicator Solution",
        "ten_tieng_viet": "Dung dịch chỉ thị hồ tinh bột",
        "duoc_dien": "USP 43 / DĐVN V",
        "loai": "Chỉ thị",
        "cach_pha": (
            "- Trộn 1 g hồ tinh bột tan với 10 mg thủy ngân (II) iodid (làm chất bảo quản) và một lượng nhỏ nước lạnh "
            "để tạo thành bột nhão mịn.\n"
            "- Thêm từ từ bột nhão này vào 200 mL nước đang sôi, khuấy liên tục.\n"
            "- Đun sôi nhẹ trong vài phút cho đến khi dung dịch trở nên trong suốt.\n"
            "- Để nguội trước khi sử dụng. Bảo quản trong chai thủy tinh kín ánh sáng."
        ),
        "nguon_goc": "USP Reagents / DĐVN V",
        "ngay_cap_nhat": "",
    },
    "phenolphthalein_indicator_solution": {
        "ten_tieng_anh": "Phenolphthalein Indicator Solution",
        "ten_tieng_viet": "Dung dịch chỉ thị Phenolphthalein",
        "duoc_dien": "USP 43 / DĐVN V",
        "loai": "Chỉ thị",
        "cach_pha": (
            "- Hòa tan 1 g phenolphthalein trong 100 mL ethanol 96% (TT).\n"
            "- Lọc nếu cần thiết để thu được dung dịch trong suốt không màu."
        ),
        "nguon_goc": "USP Reagents / DĐVN V Phụ lục 2",
        "ngay_cap_nhat": "",
    },
    "0_1_m_sodium_hydroxide_vs": {
        "ten_tieng_anh": "0.1 M Sodium Hydroxide VS",
        "ten_tieng_viet": "Dung dịch chuẩn Natri hydroxyd 0,1 M",
        "duoc_dien": "BP 2025 / DĐVN V",
        "loai": "Dung dịch chuẩn",
        "cach_pha": (
            "- Hòa tan khoảng 4,2 g natri hydroxyd (TT) trong nước không có carbon dioxyd (TT) để vừa đủ 1000 mL.\n"
            "- Chuẩn hóa: Cân chính xác khoảng 0,5 g kali hydro phtalat [C\u2088H\u2085KO\u2084] (đã sấy khô ở 120°C trong 2 giờ).\n"
            "- Hòa tan trong 75 mL nước không có carbon dioxyd, thêm 0,1 mL dung dịch phenolphthalein (chỉ thị).\n"
            "- Chuẩn độ bằng dung dịch natri hydroxyd vừa pha cho đến khi xuất hiện màu hồng nhạt bền vững trong ít nhất 30 giây.\n"
            "- Tính hệ số hiệu chỉnh F (hoặc nồng độ đương lượng thực tế)."
        ),
        "nguon_goc": "BP Appendix I D / DĐVN V Phụ lục 3",
        "ngay_cap_nhat": "",
    },
}


# ─────────────────────────────────────────────────
# HELPERS: DATA
# ─────────────────────────────────────────────────

def _migrate_record(r: dict) -> dict:
    """Backward-compatible migration: add missing new fields."""
    r.setdefault("loai", "Thuốc thử")
    r.setdefault("ngay_cap_nhat", "")
    return r


def load_reagent_lib() -> dict:
    if os.path.exists(REAGENT_FILE):
        try:
            with open(REAGENT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = {}
            for k, v in data.items():
                v = _migrate_record(v)
                # Auto-correct loai for known default entries that got wrong default
                if k in DEFAULT_REAGENTS and v.get("loai") == "Thuốc thử":
                    correct = DEFAULT_REAGENTS[k].get("loai", "Thuốc thử")
                    if correct != "Thuốc thử":
                        v["loai"] = correct
                result[k] = v
            return result
        except Exception:
            pass
    save_reagent_lib(DEFAULT_REAGENTS)
    return dict(DEFAULT_REAGENTS)


def save_reagent_lib(data: dict):
    with open(REAGENT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def clean_json_string(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
        text = text.strip()
    return text


_VALID_ESCAPES = set('"\\/ bfnrtu')

def _repair_json_escapes(text: str) -> str:
    """Thay thế các escape sequence không hợp lệ trong JSON string bằng ký tự thật."""
    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '\\' and i + 1 < len(text):
            next_ch = text[i + 1]
            if next_ch in _VALID_ESCAPES:
                result.append(ch)
                result.append(next_ch)
                i += 2
            else:
                # Invalid escape: bỏ backslash, giữ ký tự gốc
                result.append(next_ch)
                i += 2
        else:
            result.append(ch)
            i += 1
    return ''.join(result)


def safe_json_loads(text: str):
    """Parse JSON với fallback tự động sửa invalid escape sequences."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        repaired = _repair_json_escapes(text)
        return json.loads(repaired)


def _export_csv(lib_data: dict) -> bytes:
    """Export library to UTF-8-BOM CSV (Excel-friendly)."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Tên Tiếng Anh", "Tên Tiếng Việt", "Loại", "Dược điển", "Nguồn", "Cách pha", "Ngày cập nhật"])
    for r in lib_data.values():
        writer.writerow([
            r.get("ten_tieng_anh", ""),
            r.get("ten_tieng_viet", ""),
            r.get("loai", ""),
            r.get("duoc_dien", ""),
            r.get("nguon_goc", ""),
            r.get("cach_pha", "").replace("\n", " | "),
            r.get("ngay_cap_nhat", ""),
        ])
    return output.getvalue().encode("utf-8-sig")


# ─────────────────────────────────────────────────
# HELPERS: UI RENDERING
# ─────────────────────────────────────────────────

def _loai_badge(loai: str) -> str:
    s = LOAI_STYLE.get(loai, LOAI_STYLE["Khác"])
    return (
        f"<span style='display:inline-block;padding:2px 10px;border-radius:20px;"
        f"background:{s['bg']};color:{s['color']};font-size:12px;font-weight:600;"
        f"border:1px solid {s['color']}44;white-space:nowrap;'>{s['icon']} {loai}</span>"
    )


def _dd_badges(duoc_dien_str: str) -> str:
    parts = [p.strip() for p in re.split(r"[/,]", duoc_dien_str or "") if p.strip()]
    return "".join(
        f"<span style='display:inline-block;padding:2px 8px;border-radius:6px;"
        f"background:#f5f5f7;color:#1d1d1f;font-size:11px;font-weight:500;"
        f"margin-right:4px;border:1px solid #d2d2d7;'>{p}</span>"
        for p in parts
    ) or "<span style='color:#86868b;font-size:12px;'>—</span>"


def _stat_card(value, label: str, color: str = "#0071e3") -> str:
    return (
        f"<div style='background:linear-gradient(135deg,#f5f5f7 0%,#ffffff 100%);"
        f"border:1px solid rgba(60,60,67,0.10);border-radius:14px;padding:14px 18px;text-align:center;'>"
        f"<div style='font-size:32px;font-weight:700;color:{color};line-height:1.1;'>{value}</div>"
        f"<div style='font-size:12px;color:#86868b;font-weight:500;margin-top:2px;'>{label}</div></div>"
    )


# ─────────────────────────────────────────────────
# MAIN RENDER
# ─────────────────────────────────────────────────

def render_reagent_library():
    # Session state init
    for key, default in [
        ("editing_reagent_id", None),
        ("reagent_scan_key", 0),
        ("reagent_page", 0),
        ("reagent_scanned_selected", {}),
        ("reagent_search_query", ""),
        ("reagent_filter_dd", "— Tất cả Dược điển —"),
        ("reagent_filter_loai", "— Tất cả loại —"),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # Global CSS
    st.markdown("""
        <style>
        .rg-container { margin-bottom: 12px; }
        div[data-testid="stButton"] button[kind="secondary"] {
            border-radius: 980px !important;
            border: 1px solid #d2d2d7 !important;
            font-weight: 600 !important;
            transition: all 0.15s !important;
        }
        div[data-testid="stButton"] button[kind="secondary"]:hover {
            background-color: #f5f5f7 !important;
            border-color: #86868b !important;
        }
        div[data-testid="stExpander"] summary {
            font-size: 13px !important;
            font-weight: 500 !important;
        }
        /* Căn chỉnh cột nút hành động thẳng đứng */
        .rg-action-col {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            padding-top: 4px;
            gap: 6px;
        }
        /* Không để container lồng nhau tạo padding thừa */
        div[data-testid="stVerticalBlock"] > div[data-testid="element-container"] {
            margin-bottom: 0 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # Page header
    st.markdown(
        "<h2 style='text-align:center;color:#0071e3;font-weight:700;"
        "letter-spacing:-0.02em;margin-bottom:4px;'>🧪 Thư Viện Dung Dịch & Thuốc Thử</h2>"
        "<p style='text-align:center;color:#86868b;margin-bottom:28px;font-size:15px;'>"
        "Tra cứu · Lưu trữ · Dịch thuật quy trình pha chế từ Dược điển quốc tế</p>",
        unsafe_allow_html=True,
    )

    lib_data = load_reagent_lib()

    tab1, tab2, tab3 = st.tabs([
        "🔍 Tra Cứu & Quản Lý",
        "➕ Thêm Mới Thủ Công",
        "🤖 AI Dịch & Quét Cách Pha",
    ])

    # ══════════════════════════════════════════
    # TAB 1 — TRA CỨU & QUẢN LÝ
    # ══════════════════════════════════════════
    with tab1:
        editing_id = st.session_state.editing_reagent_id

        # ── EDIT MODE ──────────────────────────
        if editing_id and editing_id in lib_data:
            v = lib_data[editing_id]
            st.markdown(f"#### ⚙️ Chỉnh sửa: **{v.get('ten_tieng_anh')}**")
            if st.button("🔙 Quay lại danh sách", key="reagent_back_to_list"):
                st.session_state.editing_reagent_id = None
                st.rerun()

            st.warning("⚠️ **Đang trong chế độ chỉnh sửa.** Nhấn Lưu để cập nhật hoặc quay lại để hủy.")
            with st.form(key=f"edit_reagent_form_{editing_id}"):
                edit_en = st.text_input("Tên Tiếng Anh *", value=v.get("ten_tieng_anh", ""))
                edit_vi = st.text_input("Tên Tiếng Việt *", value=v.get("ten_tieng_viet", ""))
                c1, c2 = st.columns(2)
                with c1:
                    edit_dd = st.text_input("Dược điển *", value=v.get("duoc_dien", ""), placeholder="VD: USP 43 / BP 2025")
                with c2:
                    cur = v.get("loai", "Thuốc thử")
                    edit_loai = st.selectbox("Loại *", LOAI_OPTIONS, index=LOAI_OPTIONS.index(cur) if cur in LOAI_OPTIONS else 0)
                edit_nguon = st.text_input("Nguồn / Chuyên luận", value=v.get("nguon_goc", ""))
                edit_pha = st.text_area("Quy trình pha chế *", value=v.get("cach_pha", ""), height=260)
                if st.form_submit_button("💾 Lưu Cập Nhật", type="primary"):
                    if not edit_en.strip() or not edit_vi.strip() or not edit_pha.strip():
                        st.error("❌ Vui lòng nhập đầy đủ các trường bắt buộc (*)")
                    else:
                        lib_data[editing_id] = {
                            "ten_tieng_anh": edit_en.strip(),
                            "ten_tieng_viet": edit_vi.strip(),
                            "duoc_dien": edit_dd.strip(),
                            "loai": edit_loai,
                            "cach_pha": edit_pha.strip(),
                            "nguon_goc": edit_nguon.strip(),
                            "ngay_cap_nhat": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        }
                        save_reagent_lib(lib_data)
                        st.session_state.editing_reagent_id = None
                        st.success("✅ Đã cập nhật thành công!")
                        time.sleep(0.8)
                        st.rerun()

        # ── LIST MODE ──────────────────────────
        else:
            # --- Dashboard stats ---
            total = len(lib_data)
            dd_set = set()
            for r in lib_data.values():
                for part in re.split(r"[/,]", r.get("duoc_dien", "")):
                    first = part.strip().split()[0] if part.strip() else ""
                    if first:
                        dd_set.add(first)
            loai_set = set(r.get("loai", "Khác") for r in lib_data.values())

            sc1, sc2, sc3 = st.columns(3)
            sc1.markdown(_stat_card(total, "Tổng số mục"), unsafe_allow_html=True)
            sc2.markdown(_stat_card(len(dd_set), "Dược điển", "#34c759"), unsafe_allow_html=True)
            sc3.markdown(_stat_card(len(loai_set), "Phân loại", "#af52de"), unsafe_allow_html=True)

            st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)

            # --- Search & filter row ---
            c_s, c_dd, c_loai = st.columns([3, 2, 2])
            with c_s:
                search_query = st.text_input(
                    "search", label_visibility="collapsed",
                    placeholder="🔍 Tìm theo tên tiếng Anh, tiếng Việt hoặc cách pha...",
                    value=st.session_state.reagent_search_query,
                    key="search_reagent_input",
                )
            # Collect all pharmacopoeia entries from data
            all_dd_raw = set()
            for r in lib_data.values():
                for p in re.split(r"[/,]", r.get("duoc_dien", "")):
                    if p.strip():
                        all_dd_raw.add(p.strip())
            dd_options = ["— Tất cả Dược điển —"] + sorted(all_dd_raw)
            with c_dd:
                dd_index = dd_options.index(st.session_state.reagent_filter_dd) if st.session_state.reagent_filter_dd in dd_options else 0
                filter_dd = st.selectbox(
                    "dd", dd_options, 
                    index=dd_index,
                    key="filter_reagent_dd", 
                    label_visibility="collapsed"
                )
            with c_loai:
                loai_options_all = ["— Tất cả loại —"] + LOAI_OPTIONS
                loai_index = loai_options_all.index(st.session_state.reagent_filter_loai) if st.session_state.reagent_filter_loai in loai_options_all else 0
                filter_loai = st.selectbox(
                    "loai", loai_options_all,
                    index=loai_index,
                    key="filter_reagent_loai", 
                    label_visibility="collapsed",
                )

            # Save to persistent session state variables
            st.session_state.reagent_search_query = search_query
            st.session_state.reagent_filter_dd = filter_dd
            st.session_state.reagent_filter_loai = filter_loai

            # --- Apply filters ---
            filtered_items = []
            for r_id, r_info in lib_data.items():
                haystack = (
                    f"{r_info.get('ten_tieng_anh', '')} "
                    f"{r_info.get('ten_tieng_viet', '')} "
                    f"{r_info.get('duoc_dien', '')} "
                    f"{r_info.get('cach_pha', '')}"
                ).lower()
                if search_query and search_query.lower() not in haystack:
                    continue
                if filter_dd != "— Tất cả Dược điển —" and filter_dd.lower() not in r_info.get("duoc_dien", "").lower():
                    continue
                if filter_loai != "— Tất cả loại —" and r_info.get("loai", "Khác") != filter_loai:
                    continue
                filtered_items.append((r_id, r_info))

            # --- Pagination ---
            page_count = max(1, (len(filtered_items) + PAGE_SIZE - 1) // PAGE_SIZE)
            if st.session_state.reagent_page >= page_count:
                st.session_state.reagent_page = 0
                st.session_state.reagent_page_input = 1

            start = st.session_state.reagent_page * PAGE_SIZE
            page_items = filtered_items[start: start + PAGE_SIZE]

            if not filtered_items:
                st.info("Không tìm thấy thuốc thử/dung dịch nào khớp với bộ lọc.")
            else:
                page_label = (
                    f"  •  Trang **{st.session_state.reagent_page + 1}/{page_count}**"
                    if page_count > 1 else ""
                )
                st.markdown(
                    f"<p style='color:#86868b;font-size:13px;margin-bottom:14px;'>"
                    f"Tìm thấy <strong>{len(filtered_items)}</strong> mục{page_label}</p>",
                    unsafe_allow_html=True,
                )

                for r_id, r_info in page_items:
                    loai = r_info.get("loai", "Khác")
                    nguon = r_info.get("nguon_goc") or "Chưa rõ"
                    ngay = r_info.get("ngay_cap_nhat", "")
                    with st.container(border=True):
                        # Header: info bên trái, 2 nút bên phải thẳng hàng
                        col_info, col_actions = st.columns([9, 1])
                        with col_info:
                            st.markdown(
                                f"<div style='margin-bottom:4px;'>"
                                f"<span style='font-size:17px;font-weight:700;color:#0071e3;'>"
                                f"{r_info.get('ten_tieng_anh','—')}</span>"
                                f"&nbsp;&nbsp;{_loai_badge(loai)}</div>"
                                f"<div style='font-size:15px;font-weight:500;color:#1d1d1f;margin-bottom:4px;'>"
                                f"🇻🇳 {r_info.get('ten_tieng_viet','—')}</div>"
                                f"<div style='font-size:12px;color:#86868b;margin-bottom:2px;'>"
                                f"📚 {_dd_badges(r_info.get('duoc_dien',''))}</div>"
                                f"<div style='font-size:11px;color:#aeaeb2;'>"
                                f"Nguồn: {nguon}"
                                + (f"&emsp;·&emsp;🕒 {ngay}" if ngay else "") +
                                "</div>",
                                unsafe_allow_html=True,
                            )
                        with col_actions:
                            if st.button("✏️", key=f"btn_edit_{r_id}", help="Chỉnh sửa",
                                         use_container_width=True):
                                st.session_state.editing_reagent_id = r_id
                                st.rerun()
                            if st.button("🗑️", key=f"btn_del_{r_id}", help="Xóa",
                                         use_container_width=True):
                                del lib_data[r_id]
                                save_reagent_lib(lib_data)
                                st.success("Đã xóa thành công!")
                                st.rerun()

                        with st.expander("📋 Xem toàn bộ nội dung", expanded=False):
                            st.markdown(r_info.get("cach_pha", "—"))

                # Pagination controls
                if page_count > 1:
                    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
                    
                    # Callbacks to update page state before widgets are rendered
                    def prev_page():
                        st.session_state.reagent_page -= 1
                        st.session_state.reagent_page_input = st.session_state.reagent_page + 1

                    def next_page():
                        st.session_state.reagent_page += 1
                        st.session_state.reagent_page_input = st.session_state.reagent_page + 1
                        
                    pc_prev, pc_text1, pc_input, pc_text2, pc_next = st.columns([2, 1, 1, 1, 2])
                    with pc_prev:
                        st.button(
                            "⬅️ Trang trước", 
                            use_container_width=True,
                            disabled=(st.session_state.reagent_page == 0),
                            on_click=prev_page
                        )
                    with pc_text1:
                        st.markdown(
                            "<div style='text-align:right; padding-top:8px; font-size:14px; color:#86868b; font-weight:500;'>"
                            "Trang</div>",
                            unsafe_allow_html=True
                        )
                    with pc_input:
                        page_val = st.number_input(
                            "Trang",
                            min_value=1,
                            max_value=page_count,
                            value=st.session_state.reagent_page + 1,
                            step=1,
                            label_visibility="collapsed",
                            key="reagent_page_input"
                        )
                    with pc_text2:
                        st.markdown(
                            f"<div style='text-align:left; padding-top:8px; font-size:14px; color:#86868b; font-weight:500;'>"
                            f"/ {page_count}</div>",
                            unsafe_allow_html=True
                        )
                    with pc_next:
                        st.button(
                            "Trang sau ➡️", 
                            use_container_width=True,
                            disabled=(st.session_state.reagent_page >= page_count - 1),
                            on_click=next_page
                        )
                    
                    if page_val - 1 != st.session_state.reagent_page:
                        st.session_state.reagent_page = page_val - 1
                        st.rerun()

            # CSV export
            st.markdown("---")
            col_csv, _ = st.columns([1, 2])
            with col_csv:
                st.download_button(
                    label="📥 Xuất toàn bộ thư viện ra CSV",
                    data=_export_csv(lib_data),
                    file_name=f"thu_vien_thuoc_thu_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

    # ══════════════════════════════════════════
    # TAB 2 — THÊM MỚI THỦ CÔNG
    # ══════════════════════════════════════════
    with tab2:
        st.markdown("#### ➕ Nhập thông tin thuốc thử / dung dịch mới")

        # AI quick-translate helper (outside form so button click won't submit)
        with st.expander("🤖 Gợi ý tên Tiếng Việt bằng AI", expanded=False):
            st.caption("Nhập tên tiếng Anh rồi nhấn **Dịch ngay** để AI gợi ý tên tiếng Việt chuẩn ngành Dược.")
            c_ai_inp, c_ai_btn = st.columns([4, 1])
            with c_ai_inp:
                ai_en_input = st.text_input(
                    "Tên tiếng Anh:", key="ai_suggest_en_input",
                    placeholder="VD: 0.1 M Hydrochloric Acid VS",
                    label_visibility="collapsed",
                )
            with c_ai_btn:
                if st.button("✨ Dịch ngay", key="btn_ai_suggest_vi", use_container_width=True):
                    if ai_en_input.strip():
                        _mc = load_model_config()
                        _providers = list(_mc.keys())
                        if _providers:
                            _p = _providers[0]
                            _models = _mc.get(_p, [])
                            if _models:
                                with st.spinner("Đang dịch..."):
                                    try:
                                        vi_sug = call_ai_engine(
                                            system_instruction=(
                                                "Bạn là chuyên gia dược điển. Dịch tên thuốc thử/dung dịch "
                                                "từ tiếng Anh sang tiếng Việt theo chuẩn ngành Dược Việt Nam. "
                                                "Chỉ trả về tên đã dịch, không giải thích thêm."
                                            ),
                                            user_content=f'Dịch sang tiếng Việt: "{ai_en_input.strip()}"',
                                            provider=_p,
                                            model=_models[0],
                                        )
                                        st.session_state["ai_suggested_vi"] = vi_sug.strip()
                                        st.success(f"✅ Gợi ý: **{vi_sug.strip()}**")
                                    except Exception as ex:
                                        st.error(f"Lỗi AI: {ex}")

        with st.form("add_reagent_manual_form"):
            add_en = st.text_input("Tên Tiếng Anh *", placeholder="VD: Silver Nitrate Reagent")
            suggested_vi = st.session_state.get("ai_suggested_vi", "")
            add_vi = st.text_input("Tên Tiếng Việt *", value=suggested_vi, placeholder="VD: Thuốc thử Bạc nitrat")
            cf1, cf2 = st.columns(2)
            with cf1:
                add_dd = st.text_input("Dược điển áp dụng *", placeholder="VD: DĐVN V / BP 2025")
            with cf2:
                add_loai = st.selectbox("Loại *", LOAI_OPTIONS)
            add_nguon = st.text_input("Nguồn tài liệu / Chuyên luận", placeholder="VD: BP Appendix I C")
            add_pha = st.text_area(
                "Quy trình pha chế (Tiếng Việt) *",
                placeholder="VD:\n- Hòa tan 1,7 g bạc nitrat trong nước để vừa đủ 100 mL.\n- Bảo quản tránh ánh sáng.",
                height=220,
            )
            if st.form_submit_button("💾 Lưu Vào Thư Viện", type="primary"):
                if not add_en.strip() or not add_vi.strip() or not add_pha.strip():
                    st.error("❌ Vui lòng điền đầy đủ các thông tin bắt buộc (*)")
                else:
                    slug = re.sub(r"[^a-z0-9_]", "", add_en.strip().lower().replace(" ", "_"))
                    if not slug:
                        slug = f"reagent_{int(time.time())}"
                    elif slug in lib_data:
                        slug = f"{slug}_{int(time.time())}"
                    lib_data[slug] = {
                        "ten_tieng_anh": add_en.strip(),
                        "ten_tieng_viet": add_vi.strip(),
                        "duoc_dien": add_dd.strip(),
                        "loai": add_loai,
                        "cach_pha": add_pha.strip(),
                        "nguon_goc": add_nguon.strip(),
                        "ngay_cap_nhat": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    }
                    save_reagent_lib(lib_data)
                    if "ai_suggested_vi" in st.session_state:
                        del st.session_state["ai_suggested_vi"]
                    st.success(f"✅ Đã lưu thành công: **{add_en.strip()}**!")
                    st.rerun()

    # ══════════════════════════════════════════
    # TAB 3 — AI DỊCH & QUÉT CÁCH PHA
    # ══════════════════════════════════════════
    with tab3:
        st.markdown("#### 🤖 Tải tài liệu hoặc dán ảnh/văn bản để AI trích xuất & dịch cách pha")
        st.info(
            "💡 Tải lên file tài liệu (PDF, Word, Ảnh), dán ảnh chụp màn hình **(Ctrl + V)**, "
            "hoặc dán trực tiếp đoạn văn bản."
        )

        # Input row
        c_up, c_pst = st.columns([1, 1])
        with c_up:
            st.markdown("##### 1. Tải file tài liệu:")
            uploaded_files = st.file_uploader(
                "upload",
                type=["pdf", "docx", "png", "jpg", "jpeg"],
                accept_multiple_files=True,
                key=f"reagent_uploader_{st.session_state.reagent_scan_key}",
                label_visibility="collapsed",
            )
        with c_pst:
            st.markdown("##### 2. Dán ảnh chụp màn hình (Ctrl + V):")
            comp_val = paste_image(key=f"reagent_paste_image_{st.session_state.reagent_scan_key}")
            if comp_val is not None:
                if isinstance(comp_val, dict) and comp_val.get("cleared"):
                    st.session_state.reagent_pasted_image_data = None
                else:
                    st.session_state.reagent_pasted_image_data = comp_val
            pasted_img = st.session_state.get("reagent_pasted_image_data")

        st.markdown("##### 3. Dán trực tiếp đoạn văn bản tại đây:")
        pasted_text = st.text_area(
            "text",
            placeholder="Dán nội dung hướng dẫn pha chế thuốc thử/dung dịch từ Dược điển vào đây...",
            height=150,
            key=f"reagent_pasted_text_{st.session_state.reagent_scan_key}",
            label_visibility="collapsed",
        )

        # AI provider/model config
        model_config = load_model_config()
        providers = list(model_config.keys())
        cp, cm = st.columns(2)
        with cp:
            p_ai = st.selectbox("Provider", providers, key="reagent_ai_provider")
        with cm:
            m_ai = st.selectbox("Model", model_config.get(p_ai, []), key="reagent_ai_model")

        # Scan button
        if st.button("🚀 Quét & Dịch Bằng AI", type="primary", use_container_width=True):
            if not uploaded_files and not pasted_text.strip() and not pasted_img:
                st.error("⚠️ Vui lòng tải lên file, dán văn bản hoặc dán ảnh cần quét!")
            else:
                progress_placeholder = st.empty()
                result_placeholder = st.empty()
                try:
                    # ── Bước 1: Chuẩn bị dữ liệu đầu vào ──────────────────
                    progress_placeholder.info("⏳ **Bước 1/3** — Đang đọc và chuẩn bị tài liệu...")
                    files_data = prepare_file_for_ai(uploaded_files) if uploaded_files else []
                    if pasted_img:
                        imgs = pasted_img if isinstance(pasted_img, list) else [pasted_img]
                        for img in imgs:
                            if img and isinstance(img, dict) and not img.get("cleared"):
                                files_data.append({
                                    "name": img.get("name", "pasted_image.png"),
                                    "mime_type": img.get("type", "image/png"),
                                    "data": img.get("data", ""),
                                })

                    # ── Bước 2: Gọi AI (prompt tối giản, chuẩn xác) ────────
                    progress_placeholder.info("🤖 **Bước 2/3** — AI đang trích xuất và dịch thuật. Vui lòng đợi...")

                    system_instruction = (
                        "Bạn là chuyên gia Dược điển (BP, USP, EP, DĐVN, JP, ChP).\n"
                        "Nhiệm vụ: Đọc tài liệu đính kèm, trích xuất TẤT CẢ thuốc thử, dung dịch, "
                        "dung dịch chuẩn, chỉ thị, dung dịch đệm.\n"
                        "Với mỗi mục trả về JSON object đúng 6 trường (không thêm trường khác):\n"
                        '  "ten_tieng_anh": tên chuẩn tiếng Anh (kèm nồng độ nếu có);\n'
                        '  "ten_tieng_viet": tên tiếng Việt chuẩn ngành Dược;\n'
                        '  "duoc_dien": tên Dược điển nguồn (VD: "BP 2025");\n'
                        '  "loai": một trong: "Thuốc thử"|"Dung dịch chuẩn"|"Chỉ thị"|"Buffer / Dung dịch đệm"|"Khác";\n'
                        '  "cach_pha": toàn bộ nội dung mục đó dịch sang tiếng Việt chuẩn, '
                        "dùng **bold header** (🔬 Thông số kỹ thuật / 📋 Yêu cầu hàm lượng / "
                        "⚗️ Cách pha / 🏷️ Bảo quản) và gạch đầu dòng; bỏ phần không có dữ liệu;\n"
                        '  "nguon_goc": số appendix/section trong Dược điển.\n'
                        "Trả về DUY NHẤT JSON ARRAY hợp lệ, KHÔNG có markdown hay text khác."
                    )
                    user_prompt = (
                        "Trích xuất TẤT CẢ thuốc thử và dung dịch từ tài liệu. "
                        "Lấy đầy đủ: thông số kỹ thuật, hàm lượng, quy trình pha, bảo quản. "
                        "Dịch hoàn chỉnh sang tiếng Việt. Trả về JSON array."
                    )
                    if pasted_text.strip():
                        user_prompt += f'\n\nVăn bản dán vào:\n"""\n{pasted_text.strip()}\n"""'

                    response_text = call_ai_engine(
                        system_instruction=system_instruction,
                        user_content=user_prompt,
                        provider=p_ai,
                        model=m_ai,
                        is_json=True,
                        files=files_data,
                    )

                    # ── Bước 3: Phân tích JSON và hiển thị kết quả ─────────
                    progress_placeholder.info("✅ **Bước 3/3** — Đang phân tích kết quả...")
                    cleaned = clean_json_string(response_text)
                    extracted = safe_json_loads(cleaned)

                    if not isinstance(extracted, list):
                        progress_placeholder.error("⚠️ AI không trả về JSON array hợp lệ. Thử lại hoặc đổi mô hình.")
                    else:
                        st.session_state.reagents_scanned = extracted
                        st.session_state.reagent_scanned_selected = {
                            i: True for i in range(len(extracted))
                        }
                        progress_placeholder.success(
                            f"🎉 Trích xuất thành công! Tìm thấy **{len(extracted)}** thuốc thử/dung dịch."
                        )
                except Exception as exc:
                    progress_placeholder.error(f"❌ Lỗi quét dịch tài liệu: {exc}")

        # ── Review results ──
        if st.session_state.get("reagents_scanned"):
            scanned_list = st.session_state.reagents_scanned
            selected = st.session_state.get(
                "reagent_scanned_selected", {i: True for i in range(len(scanned_list))}
            )

            st.markdown("---")
            st.markdown(
                f"### 📋 Kết quả quét từ AI — {len(scanned_list)} mục  \n"
                "_Chọn các mục bạn muốn lưu vào thư viện, sau đó nhấn nút Lưu._"
            )

            # Bulk select controls
            bs1, bs2, bs3 = st.columns([1, 1, 3])
            with bs1:
                if st.button("☑️ Chọn tất cả", key="btn_sel_all"):
                    st.session_state.reagent_scanned_selected = {i: True for i in range(len(scanned_list))}
                    st.rerun()
            with bs2:
                if st.button("⬜ Bỏ chọn tất", key="btn_desel_all"):
                    st.session_state.reagent_scanned_selected = {i: False for i in range(len(scanned_list))}
                    st.rerun()

            st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)

            for i, item in enumerate(scanned_list):
                is_checked = selected.get(i, True)
                loai = item.get("loai", "Khác")
                with st.container(border=True):
                    c_hdr, c_chk = st.columns([5, 1])
                    with c_hdr:
                        st.markdown(
                            f"<div style='margin-bottom:4px;'>"
                            f"<span style='font-size:16px;font-weight:700;color:#0071e3;'>"
                            f"{item.get('ten_tieng_anh','—')}</span>"
                            f"&nbsp;&nbsp;{_loai_badge(loai)}</div>"
                            f"<div style='font-size:14px;color:#1d1d1f;margin-bottom:4px;'>"
                            f"🇻🇳 {item.get('ten_tieng_viet','—')}</div>"
                            f"<div style='font-size:12px;color:#86868b;'>"
                            f"{_dd_badges(item.get('duoc_dien',''))}</div>",
                            unsafe_allow_html=True,
                        )
                    with c_chk:
                        new_val = st.checkbox(
                            "Chọn", value=is_checked,
                            key=f"scanned_chk_{st.session_state.reagent_scan_key}_{i}",
                            label_visibility="collapsed",
                        )
                        if new_val != is_checked:
                            st.session_state.reagent_scanned_selected[i] = new_val

                    with st.expander("📋 Xem toàn bộ nội dung", expanded=True):
                        st.markdown(item.get("cach_pha", "—"))
                        if item.get("nguon_goc"):
                            st.caption(f"📌 Nguồn: {item.get('nguon_goc')}")

            st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
            num_selected = sum(1 for v in st.session_state.reagent_scanned_selected.values() if v)

            btn_save, btn_clear = st.columns(2)
            with btn_save:
                if st.button(
                    f"💾 Lưu {num_selected} mục đã chọn vào Thư Viện",
                    type="primary", use_container_width=True,
                    disabled=(num_selected == 0),
                ):
                    added = 0
                    for i, item in enumerate(scanned_list):
                        if not st.session_state.reagent_scanned_selected.get(i, True):
                            continue
                        en = item.get("ten_tieng_anh", "").strip()
                        if not en:
                            continue
                        slug = re.sub(r"[^a-z0-9_]", "", en.lower().replace(" ", "_")) or f"reagent_{int(time.time())}_{i}"
                        if slug in lib_data:
                            slug = f"{slug}_{int(time.time())}_{i}"
                        lib_data[slug] = {
                            "ten_tieng_anh": en,
                            "ten_tieng_viet": item.get("ten_tieng_viet", "").strip(),
                            "duoc_dien": item.get("duoc_dien", "").strip(),
                            "loai": item.get("loai", "Thuốc thử"),
                            "cach_pha": item.get("cach_pha", "").strip(),
                            "nguon_goc": item.get("nguon_goc", "").strip(),
                            "ngay_cap_nhat": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        }
                        added += 1
                    save_reagent_lib(lib_data)
                    st.success(f"✅ Đã thêm thành công **{added}** mục vào Thư viện!")
                    del st.session_state.reagents_scanned
                    st.session_state.reagent_scanned_selected = {}
                    st.session_state.reagent_scan_key += 1
                    st.session_state.reagent_pasted_image_data = None
                    st.rerun()

            with btn_clear:
                if st.button("❌ Hủy bỏ kết quả quét", use_container_width=True):
                    del st.session_state.reagents_scanned
                    st.session_state.reagent_scanned_selected = {}
                    st.session_state.reagent_scan_key += 1
                    st.session_state.reagent_pasted_image_data = None
                    st.rerun()
