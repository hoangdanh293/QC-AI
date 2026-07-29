import streamlit as st
import json
import os
import time
import traceback
import pandas as pd
import unicodedata
import re
import concurrent.futures

from core.doc_processor import (
    tcnl_scan_criteria_and_limits,
    node_phase_2_deep_extract,
    node_phase_2_deep_extract_v2,
    node_phase_2_extract_other_criteria,
    prepare_file_for_ai,
)
from core.word_exporter import node_4_generate_word
from core.key_manager import load_model_config

# Import fuzzy matching utilities from ui_tcnl
from ui_modules.ui_tcnl import _normalize_name, _fuzzy_match_single, _fuzzy_match, _merge_criteria_union, _find_matched_sop
from ui_modules.ui_sop_library import load_sop_lib
from core.ai_handler import translate_text_to_bilingual, translate_text_to_vietnamese_only

import streamlit.components.v1 as components

# Khai báo component kéo thả (Module level để tránh đăng ký lại nhiều lần)
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_component_dir = os.path.join(_parent_dir, "core", "drag_drop_component")
_drag_drop_reorder = components.declare_component("drag_drop_reorder", path=_component_dir)

# Callbacks for bilingual translations to avoid StreamlitAPIException
def translate_ho_so_name_callback(key):
    p3 = st.session_state.get("ho_so_p3", "Google API")
    m3 = st.session_state.get("ho_so_m3", "gemini-1.5-flash")
    current_name = st.session_state[f"edit_crit_name_{key}"]
    st.session_state[f"edit_crit_name_{key}"] = translate_text_to_bilingual(current_name, p3, m3, "criteria")

def translate_ho_so_sop_callback(key):
    p3 = st.session_state.get("ho_so_p3", "Google API")
    m3 = st.session_state.get("ho_so_m3", "gemini-1.5-flash")
    current_text = st.session_state[f"edit_crit_{key}"]
    st.session_state[f"edit_crit_{key}"] = translate_text_to_bilingual(current_text, p3, m3, "sop")

# Callbacks for SOP templates selection to avoid StreamlitAPIException
def on_sop_change_mapped(k, display_idx):
    sel_key = f"change_sop_select_{k}_{display_idx}"
    val = st.session_state.get(sel_key)
    if val and val != "-- Chọn phương pháp mẫu thay thế (SOP Library) --":
        sop_lib = load_sop_lib()
        if val in sop_lib:
            st.session_state[f"edit_crit_{k}"] = sop_lib[val].get("noi_dung_sop", "")

def on_sop_change_hsnl(hk):
    sel_key = f"hsnl_sop_select_{hk}"
    val = st.session_state.get(sel_key)
    if val and val != "-- Chọn phương pháp mẫu (SOP Library) --":
        sop_lib = load_sop_lib()
        if val in sop_lib:
            st.session_state[f"edit_hsnl_pp_{hk}"] = sop_lib[val].get("noi_dung_sop", "")


def sync_ho_so_comparison_editor_callback():
    editor_state = st.session_state.get("ho_so_comparison_editor", None)
    if not editor_state:
        return
        
    has_adds = len(editor_state.get("added_rows", [])) > 0
    has_deletes = len(editor_state.get("deleted_rows", [])) > 0
    
    if not has_adds and not has_deletes:
        return
        
    df = st.session_state.ho_so_scan_df.copy()
    source_labels = ["Dược điển", "Tiêu chuẩn nguyên liệu", "COA", "MOA"]
    
    # 1. Apply edits
    edited_rows = editor_state.get("edited_rows", {})
    for idx_str, changes in edited_rows.items():
        idx = int(idx_str)
        if idx < len(df):
            for col, val in changes.items():
                df.at[idx, col] = val
                
    # 2. Apply deletes
    deleted_rows = sorted(editor_state.get("deleted_rows", []), reverse=True)
    for idx in deleted_rows:
        if idx < len(df):
            df = df.drop(df.index[idx])
    df = df.reset_index(drop=True)
            
    # 3. Apply adds
    added_rows = editor_state.get("added_rows", [])
    for row in added_rows:
        if not df.empty:
            next_stt = int(df["STT"].max()) + 1
        else:
            next_stt = 1
            
        new_row = {
            "STT": next_stt,
            "Tên Chỉ Tiêu": row.get("Tên Chỉ Tiêu") or "",
            "✅ Chọn": row.get("✅ Chọn") if row.get("✅ Chọn") is not None else True,
            "Giới hạn chốt": row.get("Giới hạn chốt") or ""
        }
        for src in source_labels:
            new_row[src] = row.get(src) or "Nhập thủ công"
            
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        
    # Recalculate STT
    for idx in range(len(df)):
        df.at[idx, "STT"] = idx + 1
        
    st.session_state.ho_so_scan_df = df


DINH_TINH_KEYS = [
    "dinh_tinh",
    "dinh_tinh_a", "dinh_tinh_b", "dinh_tinh_c",
    "dinh_tinh_d", "dinh_tinh_e", "dinh_tinh_f"
]

MASTER_FILE = "criteria_master.json"
METHOD_FILE = "method_library.json"

# =====================================================================
# TIỆN ÍCH
# =====================================================================
def _load_master():
    if not os.path.exists(MASTER_FILE):
        return {}
    with open(MASTER_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

MAX_HSNL_SLOTS = 50  # Số slot tối đa cho chỉ tiêu không có bảng

TEMPLATE_SUPPORTED_CRITERIA = {
    "cam_quan", "do_tan", "dinh_tinh", "dinh_tinh_a", "dinh_tinh_b", 
    "dinh_tinh_c", "dinh_tinh_d", "dinh_tinh_e", "dinh_tinh_f", 
    "cam_quan_dung_dich", "acid_kiem", "mat_khoi_luong_do_say", 
    "tro_sulfat", "can_sau_nung", "ham_luong_nuoc", "ty_trong", 
    "goc_quay_cuc_rieng", "chi_so_acid", "chi_so_iodine", "chi_so_peroxide", 
    "chi_so_hydroxyl", "chi_so_xa_phong_hoa", "chat_khong_xa_phong_hoa", 
    "chat_khong_tan_trong_nuoc", "chat_co_the_chiet_bang_ether", 
    "dinh_luong", "dinh_luong_hplc", "tap_chat_lien_quan"
}

def _criteria_has_table(ma_id, master_data):
    """Kiểm tra chỉ tiêu có bảng thiết kế sẵn (bang_di_kem) trong master không."""
    if ma_id not in master_data:
        return False
    return bool(master_data[ma_id].get("bang_di_kem", ""))

def _match_name_to_master_id(name, master_data):
    """Tìm Mã ID trong criteria_master.json khớp với tên chỉ tiêu AI quét được.
    Trả về (ma_id, ten_hien_thi) hoặc (None, None) nếu không khớp.
    """
    if not name:
        return None, None
    norm_name = _normalize_name(name)
    
    # 1. Khớp chính xác (Normalized hoặc khớp với key)
    for ma_id, config in master_data.items():
        ten_hien_thi = config.get("ten_hien_thi", "")
        if _normalize_name(ten_hien_thi) == norm_name or norm_name == _normalize_name(ma_id):
            return ma_id, ten_hien_thi
            
    # 2. Xử lý đặc biệt cho Định tính
    if "dinh tinh" in norm_name or "identification" in norm_name:
        return "dinh_tinh", master_data.get("dinh_tinh", {}).get("ten_hien_thi", "Định tính (Nhóm I, II / Chung)")

    # 3. Khớp chuỗi con (Substring matching)
    ash_words = {"tro", "ash", "ignition", "nung", "can"}
    has_ash_scanned = any(w in norm_name for w in ash_words)
    for ma_id, config in master_data.items():
        ten_hien_thi = config.get("ten_hien_thi", "")
        norm_master = _normalize_name(ten_hien_thi)
        if norm_master in norm_name or norm_name in norm_master:
            has_ash_master = any(w in norm_master for w in ash_words)
            if has_ash_scanned != has_ash_master:
                continue
            return ma_id, ten_hien_thi
            
    # 4. Khớp mờ (Fuzzy matching)
    for ma_id, config in master_data.items():
        ten_hien_thi = config.get("ten_hien_thi", "")
        if _fuzzy_match(name, ten_hien_thi):
            return ma_id, ten_hien_thi
            
    return None, None

def draw_progress(placeholder, percent, text_status):
    html = f"<div style='font-weight: 600; font-size: 14px; color: var(--apple-text-main); margin-bottom: 5px;'>Tiến trình: {percent}%</div><div style='font-size: 13px; color: var(--apple-text-muted); margin-bottom: 8px;'>{text_status}</div><div class='apple-progress-container'><div class='apple-progress-bar' style='width: {percent}%;'></div></div>"
    placeholder.markdown(html, unsafe_allow_html=True)

def draw_node(placeholder, status, title, desc=""):
    icon = "🔄" if status == "running" else "✅" if status == "success" else "❌" if status == "error" else "⏸️"
    html = f"<div class='node-card {status}'><div class='node-icon'>{icon}</div><div><div class='node-text-title'>{title}</div><div class='node-text-desc'>{desc}</div></div></div>"
    placeholder.markdown(html, unsafe_allow_html=True)

# =====================================================================
# PHASE 1: BẢNG TÍCH CHỌN CHỈ TIÊU (4 CỘT SO SÁNH)
# =====================================================================
def render_ho_so_phase_1():
    """Hiển thị bảng chỉ tiêu AI đã quét để user tích chọn, gán SOP và sắp xếp (Bước 2a, 2ab, 2b)."""
    st.divider()
    
    # Khởi tạo subphase
    if "ho_so_chot_done" not in st.session_state:
        st.session_state.ho_so_chot_done = False
    if "ho_so_sop_done" not in st.session_state:
        st.session_state.ho_so_sop_done = False

    scan_df = st.session_state.ho_so_scan_df
    source_labels = ["Dược điển", "Tiêu chuẩn nguyên liệu", "COA", "MOA"]

    # Load SOP Library
    sop_library = load_sop_lib()

    # --- BƯỚC 2A: CHỐT CHỈ TIÊU & GIỚI HẠN ---
    if not st.session_state.ho_so_chot_done:
        st.markdown("<h3 style='color: #0071e3;'>📊 Bước 2a: Chốt Chỉ Tiêu & Giới Hạn</h3>", unsafe_allow_html=True)
        st.info("Tích chọn các chỉ tiêu cần thiết trong cột **✅ Chọn** và chỉnh sửa giới hạn nếu cần. Nhấn nút dưới bảng để chuyển sang bước chọn phương pháp mẫu. Bạn có thể bấm nút **➕ Add row** ở cuối bảng để thêm chỉ tiêu thủ công mới.")
        
        col_config = {
            "STT": st.column_config.NumberColumn("STT", width="small", min_value=1, format="%d", disabled=True),
            "Tên Chỉ Tiêu": st.column_config.TextColumn("Tên Chỉ Tiêu", width="large"),
            "Dược điển": st.column_config.TextColumn("Dược điển", width="medium"),
            "Tiêu chuẩn nguyên liệu": st.column_config.TextColumn("Tiêu chuẩn nguyên liệu", width="medium"),
            "COA": st.column_config.TextColumn("COA", width="medium"),
            "MOA": st.column_config.TextColumn("MOA", width="medium"),
            "✅ Chọn": st.column_config.CheckboxColumn("✅ Chọn", default=True),
            "Giới hạn chốt": st.column_config.TextColumn("Giới hạn chốt", width="large"),
        }

        edited_df = st.data_editor(
            scan_df,
            column_config=col_config,
            disabled=source_labels,
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="ho_so_comparison_editor",
            on_change=sync_ho_so_comparison_editor_callback
        )
                    
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        
        if st.button("➡️ Xác Nhận Chốt & Chọn Phương Pháp Mẫu", type="primary", use_container_width=True):
            df_to_save = edited_df.copy().reset_index(drop=True)
            for idx in range(len(df_to_save)):
                df_to_save.at[idx, "STT"] = idx + 1
                for src in source_labels:
                    if pd.isna(df_to_save.at[idx, src]) or df_to_save.at[idx, src] is None or df_to_save.at[idx, src] == "":
                        df_to_save.at[idx, src] = "Nhập thủ công"
            
            st.session_state.ho_so_scan_df = df_to_save
            
            # Lọc những chỉ tiêu được chốt
            checked_df = df_to_save[df_to_save["✅ Chọn"] == True].copy().reset_index(drop=True)
            if checked_df.empty:
                st.error("⚠️ Vui lòng tích chọn ít nhất 1 chỉ tiêu!")
                st.stop()
                
            # Đánh lại STT từ 1
            for idx in range(len(checked_df)):
                checked_df.at[idx, "STT"] = idx + 1
                
            # Xác định key cho từng chỉ tiêu
            master_data = _load_master()
            used_master_ids = set()
            other_slot = 1
            hsnl_keys = []
            
            for idx, row in checked_df.iterrows():
                ten = row["Tên Chỉ Tiêu"]
                ma_id, _ = _match_name_to_master_id(ten, master_data)
                if ma_id and ma_id in TEMPLATE_SUPPORTED_CRITERIA and ma_id not in used_master_ids:
                    used_master_ids.add(ma_id)
                    hsnl_keys.append(ma_id)
                else:
                    ukey = f"__unmapped_{other_slot}"
                    hsnl_keys.append(ukey)
                    other_slot += 1
            
            checked_df["_hsnl_key"] = hsnl_keys
            st.session_state.ho_so_sorted_df = checked_df
            st.session_state.ho_so_chot_done = True
            st.session_state.ho_so_sop_done = False
            st.rerun()

    # --- BƯỚC 2AB: CHỌN PHƯƠNG PHÁP MẪU TỪ THƯ VIỆN SOP ---
    elif not st.session_state.ho_so_sop_done:
        st.markdown("<h3 style='color: #0071e3;'>📋 Bước 2ab: Chọn Phương Pháp Mẫu Từ Thư Viện SOP</h3>", unsafe_allow_html=True)
        st.info("Hệ thống sẽ đối chiếu và gợi ý sẵn phương pháp mẫu từ thư viện SOP cho các chỉ tiêu phù hợp. Bạn có thể thay đổi hoặc chọn [AI tự bóc tách phương pháp].")
        
        sorted_df = st.session_state.ho_so_sorted_df
        
        if "ho_so_selected_sops" not in st.session_state:
            st.session_state.ho_so_selected_sops = {}
            
        sop_options = ["(AI tự bóc tách phương pháp)"] + list(sop_library.keys())
        def format_sop_option(op):
            if op == "(AI tự bóc tách phương pháp)":
                return op
            return f"{sop_library[op].get('ten_hien_thi', op)} ({op})"
            
        # Hiển thị từng chỉ tiêu kèm chọn lựa SOP mẫu
        with st.container(border=True):
            for idx, row in sorted_df.iterrows():
                ten_ct = row["Tên Chỉ Tiêu"]
                if ten_ct not in st.session_state.ho_so_selected_sops:
                    auto_matched = _find_matched_sop(ten_ct, sop_library)
                    st.session_state.ho_so_selected_sops[ten_ct] = auto_matched if auto_matched else "(AI tự bóc tách phương pháp)"
                    
                current_sel = st.session_state.ho_so_selected_sops[ten_ct]
                if current_sel not in sop_options:
                    current_sel = "(AI tự bóc tách phương pháp)"
                    
                st.session_state.ho_so_selected_sops[ten_ct] = st.selectbox(
                    f"Chỉ tiêu {idx+1}: {ten_ct}",
                    options=sop_options,
                    index=sop_options.index(current_sel),
                    format_func=format_sop_option,
                    key=f"ho_so_sel_sop_{idx}"
                )
        
        c_back, c_next = st.columns(2)
        with c_back:
            if st.button("⬅️ Quay lại Bước 2a: Chốt lại chỉ tiêu", use_container_width=True):
                st.session_state.ho_so_chot_done = False
                st.rerun()
        with c_next:
            if st.button("➡️ Xác Nhận Phương Pháp & Tiếp Tục Sắp Xếp", type="primary", use_container_width=True):
                for idx, row in sorted_df.iterrows():
                    ten_ct = row["Tên Chỉ Tiêu"]
                    st.session_state.ho_so_selected_sops[ten_ct] = st.session_state[f"ho_so_sel_sop_{idx}"]
                st.session_state.ho_so_sop_done = True
                st.rerun()

    # --- BƯỚC 2B: SẮP XẾP THỨ TỰ CHỈ TIÊU ĐÃ CHỌN ---
    else:
        st.markdown("<h3 style='color: #0071e3;'>🔄 Bước 2b: Sắp Xếp Thứ Tự Chỉ Tiêu Đã Chọn</h3>", unsafe_allow_html=True)
        st.info("Kéo thả danh sách dưới đây để thay đổi thứ tự hiển thị của chỉ tiêu khi xuất file Word.")
        
        sorted_df = st.session_state.ho_so_sorted_df
        criteria_names = sorted_df["Tên Chỉ Tiêu"].tolist()
        
        # Gọi component kéo thả
        new_order = _drag_drop_reorder(items=criteria_names, key="ho_so_dnd_reorder", default=criteria_names)
        
        # Nếu có sự thay đổi thứ tự từ kéo thả
        if new_order and new_order != criteria_names:
            valid_new_order = [name for name in new_order if name in criteria_names]
            for name in criteria_names:
                if name not in valid_new_order:
                    valid_new_order.append(name)
            
            name_to_index = {name: idx for idx, name in enumerate(valid_new_order)}
            sorted_df["_sort_order"] = sorted_df["Tên Chỉ Tiêu"].map(name_to_index)
            sorted_df = sorted_df.sort_values(by="_sort_order").drop(columns=["_sort_order"]).reset_index(drop=True)
            for idx in range(len(sorted_df)):
                sorted_df.at[idx, "STT"] = idx + 1
            st.session_state.ho_so_sorted_df = sorted_df
            st.rerun()
            
        # Hiển thị bảng xem trước thứ tự (read-only)
        st.markdown("##### 👁️ Bảng xem trước thứ tự chỉ tiêu:")
        preview_df = sorted_df[["STT", "Tên Chỉ Tiêu", "Giới hạn chốt"]].copy()
        st.dataframe(preview_df, use_container_width=True, hide_index=True)
        
        c_back, c_next = st.columns(2)
        with c_back:
            if st.button("⬅️ Quay lại Bước 2ab: Chọn lại phương pháp mẫu", use_container_width=True):
                st.session_state.ho_so_sop_done = False
                st.rerun()
                
        with c_next:
            if st.button("🚀 Bước 2: Chốt & Bóc Tách Chi Tiết", type="primary", use_container_width=True):
                # Thu thập chỉ tiêu đã sắp xếp
                selected = []
                for _, row in sorted_df.iterrows():
                    selected.append({
                        "ten": row["Tên Chỉ Tiêu"],
                        "duoc_dien": row.get("Dược điển", ""),
                        "tcnl": row.get("Tiêu chuẩn nguyên liệu", ""),
                        "coa": row.get("COA", ""),
                        "moa": row.get("MOA", ""),
                        "gioi_han_chot": row.get("Giới hạn chốt", "")
                    })
                
                # --- Map tên chỉ tiêu → Mã ID từ criteria_master.json ---
                master_data = _load_master()
                ai_extraction_prompts = {k: v["lenh_ai_trich_xuat"] for k, v in master_data.items()}
                dictionary_rules = "\n".join([f"    - {v['tu_dien_dich']}" for k, v in master_data.items() if v.get("tu_dien_dich", "").strip()])

                # Tất cả chỉ tiêu có trong master_data đều đưa vào mapped_criteria để giữ nguyên tag cũ
                mapped_criteria = {}   # {ma_id: lenh_ai_trich_xuat} — chỉ tiêu có trong master
                hsnl_criteria = {}     
                unmapped = []          # [{ten, ...}] — chỉ tiêu không khớp master (sẽ dùng tag hsnl)
                used_master_ids = set()

                for item in selected:
                    ma_id, _ = _match_name_to_master_id(item["ten"], master_data)
                    if ma_id and ma_id in TEMPLATE_SUPPORTED_CRITERIA and ma_id not in used_master_ids:
                        used_master_ids.add(ma_id)
                        mapped_criteria[ma_id] = ai_extraction_prompts.get(ma_id, "")
                        
                        # Nếu khớp với định tính chung, tự động kích hoạt các chỉ tiêu định tính con A-F
                        if ma_id == "dinh_tinh":
                            for sub_k in ["dinh_tinh_a", "dinh_tinh_b", "dinh_tinh_c", "dinh_tinh_d", "dinh_tinh_e", "dinh_tinh_f"]:
                                if sub_k not in used_master_ids:
                                    used_master_ids.add(sub_k)
                                    mapped_criteria[sub_k] = ai_extraction_prompts.get(sub_k, "")
                    else:
                        unmapped.append(item)

                # Gán unmapped vào hsnl
                hsnl_unmapped = {}  # {"__unmapped_N": prompt}
                other_slot = 1
                for item in unmapped:
                    ukey = f"__unmapped_{other_slot}"
                    limit_val = item.get("gioi_han_chot", "")
                    hsnl_unmapped[ukey] = {
                        "prompt": f"Tìm và bóc tách chỉ tiêu '{item['ten']}' (Giới hạn: {limit_val})",
                        "ten_nguyen_ban": item["ten"]
                    }
                    other_slot += 1

                # Gộp hết vào một dict để gửi AI bóc tách (mapped_criteria + hsnl_criteria)
                all_criteria_for_ai = {**mapped_criteria, **hsnl_criteria}
                # Với unmapped, thêm vào all_criteria_for_ai dưới dạng key thế
                for ukey, uval in hsnl_unmapped.items():
                    all_criteria_for_ai[ukey] = uval["prompt"]

                st.session_state.ho_so_selected_criteria = selected
                st.session_state.ho_so_mapped_criteria = mapped_criteria
                st.session_state.ho_so_hsnl_criteria = hsnl_criteria
                st.session_state.ho_so_hsnl_unmapped = hsnl_unmapped
                st.session_state.ho_so_dictionary_rules = dictionary_rules
                st.session_state.ho_so_master_data = master_data

                # --- Bắt đầu bóc tách ---
                ph_node = st.empty()
                draw_node(ph_node, "running", "Node 2: Bóc tách chuyên sâu (Deep RAG)", f"AI đang bóc tách {len(all_criteria_for_ai)} chỉ tiêu...")        

                try:
                    c_size = st.session_state.get("ho_so_chunk_size", 5)
                    m_workers = st.session_state.get("ho_so_max_workers", 3)

                    uploaded_files = st.session_state.ho_so_uploaded_files
                    extra_docs = st.session_state.ho_so_extra_docs
                    p3 = st.session_state.ho_so_p3
                    m3 = st.session_state.ho_so_m3

                    # Sử dụng kiến trúc v2 (song song theo nguồn) nếu có files đã encode sẵn
                    files_by_source = st.session_state.get("ho_so_files_by_source", {})
                    extra_files_data = st.session_state.get("ho_so_extra_files_data", [])

                    from core.key_manager import get_active_keys
                    active_keys_3 = get_active_keys(p3, m3)
                    g_keys_3 = active_keys_3 if p3 == "Google API" else None
                    o_keys_3 = active_keys_3 if p3 == "OpenAI" else None

                    if files_by_source:
                        # Kiến trúc v2: Song song theo nguồn tài liệu (~3-5x nhanh hơn)
                        draw_node(ph_node, "running", "Node 2: Bóc tách chuyên sâu (Song song theo nguồn)",
                                  f"AI đang bóc tách {len(all_criteria_for_ai)} chỉ tiêu từ {len(files_by_source)} nguồn song song...")
                        raw_deep = node_phase_2_deep_extract_v2(
                            files_by_source,
                            extra_files_data,
                            all_criteria_for_ai,
                            dictionary_rules,
                            p3, m3, g_keys_3, o_keys_3,
                            bilingual=st.session_state.get("ho_so_bilingual", True),
                            chunk_size=c_size,
                            max_workers=m_workers
                        )
                    else:
                        # Fallback kiến trúc cũ nếu không có files đã encode sẵn
                        raw_deep = node_phase_2_deep_extract(
                            uploaded_files,
                            extra_docs if extra_docs else [],
                            all_criteria_for_ai,
                            dictionary_rules,
                            p3, m3, g_keys_3, o_keys_3,
                            chunk_size=c_size,
                            max_workers=m_workers,
                            bilingual=st.session_state.get("ho_so_bilingual", True)
                        )

                    # Phân tách kết quả: chỉ tiêu có bảng (mapped_criteria) vào json_data
                    ho_so_sources = {}
                    json_data = {}
                    hsnl_raw_data = {}  # {ma_id_or_ukey: {ten, yeu_cau, gioi_han, chot, sources...}}

                    from core.doc_processor import extract_sop_text_from_value

                    for k, v in raw_deep.items():
                        if isinstance(v, str):
                            v_stripped = v.strip()
                            if v_stripped.startswith("{") and v_stripped.endswith("}"):
                                try:
                                    import json
                                    v = json.loads(v_stripped)
                                except Exception:
                                    try:
                                        import ast
                                        v = ast.literal_eval(v_stripped)
                                    except Exception:
                                        pass
                        
                        v_dict = v if isinstance(v, dict) else {}
                        
                        # Clean each field
                        ten = v_dict.get("ten", "")
                        if isinstance(ten, dict):
                            ten = extract_sop_text_from_value(ten)
                        ten = str(ten).strip()
                        
                        yeu_cau = v_dict.get("yeu_cau", "")
                        if isinstance(yeu_cau, dict):
                            yeu_cau = extract_sop_text_from_value(yeu_cau)
                        yeu_cau = str(yeu_cau).strip()
                        
                        gioi_han = v_dict.get("gioi_han", "")
                        if isinstance(gioi_han, dict):
                            gioi_han = extract_sop_text_from_value(gioi_han)
                        gioi_han = str(gioi_han).strip()
                        
                        duoc_dien = extract_sop_text_from_value(v_dict.get("duoc_dien", ""))
                        tieu_chuan = extract_sop_text_from_value(v_dict.get("tieu_chuan", ""))
                        coa = extract_sop_text_from_value(v_dict.get("coa", ""))
                        moa = extract_sop_text_from_value(v_dict.get("moa", ""))
                        phu_luc = extract_sop_text_from_value(v_dict.get("phu_luc", ""))
                        
                        chot = v_dict.get("chot", "")
                        if isinstance(chot, (dict, list)) or (isinstance(chot, str) and (chot.strip().startswith("{") or chot.strip().startswith("["))):
                            chot = extract_sop_text_from_value(chot)
                        
                        if not chot:
                            chot = extract_sop_text_from_value(v)
                            
                        # If still empty, use priority order
                        if not chot or chot in ["XOA_HANG", "XOA_DONG"]:
                            for val in [phu_luc, tieu_chuan, duoc_dien, coa, moa]:
                                if val and val.strip():
                                    chot = val.strip()
                                    break
                                    
                        # Default fallback
                        if not chot:
                            chot = "XOA_HANG"

                        if k in mapped_criteria:
                            ho_so_sources[k] = {
                                "duoc_dien": duoc_dien,
                                "tieu_chuan": tieu_chuan,
                                "coa": coa,
                                "moa": moa,
                                "phu_luc": phu_luc
                            }
                            json_data[k] = chot
                        else:
                            hsnl_raw_data[k] = {
                                "ten": master_data[k].get("ten_hien_thi", ten or k) if k in master_data else ten,
                                "yeu_cau": yeu_cau,
                                "gioi_han": gioi_han,
                                "chot": chot,
                                "duoc_dien": duoc_dien,
                                "tieu_chuan": tieu_chuan,
                                "coa": coa,
                                "moa": moa,
                                "phu_luc": phu_luc
                            }
                            if k in hsnl_unmapped:
                                if not ten:
                                    hsnl_raw_data[k]["ten"] = hsnl_unmapped[k]["ten_nguyen_ban"]

                    # Xử lý giá trị rỗng → XOA_HANG cho chỉ tiêu có bảng
                    for k in mapped_criteria.keys():
                        val = str(json_data.get(k, "")).strip().upper()
                        if not val or val in ["NONE", "NULL", "KHÔNG", "KHÔNG CÓ", "{}"]:
                            if k == "dinh_tinh":
                                # Nếu có định tính con hoạt động, đặt thành rỗng để giữ dòng Định tính trong Word
                                sub_keys = ["dinh_tinh_a", "dinh_tinh_b", "dinh_tinh_c", "dinh_tinh_d", "dinh_tinh_e", "dinh_tinh_f"]
                                is_sub_active = any(sk in mapped_criteria for sk in sub_keys)
                                json_data[k] = "" if is_sub_active else "XOA_DONG"
                            else:
                                json_data[k] = "XOA_HANG"

                    # Gán XOA_HANG cho tất cả master ID không được chọn
                    for ma_id in master_data.keys():
                        if ma_id not in mapped_criteria and ma_id not in hsnl_criteria:
                            json_data.setdefault(ma_id, "XOA_HANG")

                    # Xóa các slot chi_tieu_khac_ cũ
                    for i in range(1, 16):
                        tkey = f"ten_chi_tieu_khac_{i}"
                        ckey = f"chi_tieu_khac_{i}"
                        json_data.setdefault(tkey, "XOA_HANG")
                        json_data.setdefault(ckey, "XOA_HANG")

                    # Xóa các slot hsnl chưa dùng (N+1 → MAX_HSNL_SLOTS)
                    used_hsnl_count = len(hsnl_raw_data)
                    for i in range(used_hsnl_count + 1, MAX_HSNL_SLOTS + 1):
                        json_data.setdefault(f"hsnl_ct_{i}", "XOA_HANG")
                        json_data.setdefault(f"hsnl_yc_{i}", "XOA_HANG")
                        json_data.setdefault(f"hsnl_pp_{i}", "XOA_HANG")
                        json_data.setdefault(f"hsnl_gh_{i}", "XOA_HANG")

                    draw_node(ph_node, "success", "Node 2: Bóc tách hoàn tất", f"Đã xử lý {len(all_criteria_for_ai)} chỉ tiêu.")

                    # Đồng bộ hóa ho_so_hsnl_order dựa trên thứ tự người dùng đã kéo thả sắp xếp
                    ordered_hsnl_keys = []
                    for idx, row in sorted_df.iterrows():
                        hk = row["_hsnl_key"]
                        if hk not in mapped_criteria:
                            ordered_hsnl_keys.append(hk)
                    st.session_state.ho_so_hsnl_order = ordered_hsnl_keys

                    st.session_state.ho_so_sources = ho_so_sources
                    st.session_state.ho_so_extracted_json = json_data
                    st.session_state.ho_so_run_ai_criteria = mapped_criteria
                    st.session_state.ho_so_hsnl_raw_data = hsnl_raw_data
                    st.session_state.ho_so_phase = 2
                    time.sleep(1)
                    st.rerun()

                except Exception as e:
                    draw_node(ph_node, "error", "Node 2: Lỗi bóc tách", str(e))
                    st.error(f"❌ Lỗi bóc tách: {traceback.format_exc()}")
                    st.stop()


# =====================================================================
# PHASE 2: BẢN NHÁP + CHỈNH SỬA
# =====================================================================
def render_ho_so_phase_2():
    sop_library = load_sop_lib()
    master_data = st.session_state.ho_so_master_data
    st.divider()
    st.markdown("<h3 style='color: #0071e3;'>📝 Bước 3: Bản Nháp Hồ Sơ Kiểm Nghiệm</h3>", unsafe_allow_html=True)
    st.info("Kiểm tra và chỉnh sửa nội dung bên dưới. Chọn nguồn cách làm bằng cách bấm nút tương ứng để sao chép vào ô chốt, sau đó chỉnh sửa trực tiếp.")

    # Thông tin hành chính tóm tắt (lấy động trực tiếp từ widgets của Bước 1)
    with st.container(border=True):
        st.markdown("##### ℹ️ Thông tin hành chính:")
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"**Đơn vị:** {st.session_state.get('ho_so_don_vi', '')}")
        c2.markdown(f"**Tên nguyên liệu:** {st.session_state.get('ho_so_ten_nl', '')}")
        c3.markdown(f"**Mã hàng (BFO):** {st.session_state.get('ho_so_bfo_input', '')}")
        c4.markdown(f"**Lô sản xuất:** {st.session_state.get('ho_so_lo_sx', '')}")

    extracted_json = st.session_state.ho_so_extracted_json
    run_ai_criteria = st.session_state.ho_so_run_ai_criteria
    
    # Tự động khôi phục và giữ lại định tính lớn nếu có định tính con hoạt động (sửa lỗi cũ)
    sub_dinh_tinh_keys = ["dinh_tinh_a", "dinh_tinh_b", "dinh_tinh_c", "dinh_tinh_d", "dinh_tinh_e", "dinh_tinh_f"]
    is_any_sub_active = any(
        sub_k in extracted_json and extracted_json[sub_k] not in ["XOA_HANG", "XOA_DONG"]
        for sub_k in sub_dinh_tinh_keys
    )
    if is_any_sub_active:
        if "dinh_tinh" not in run_ai_criteria:
            new_run_ai = {}
            inserted = False
            for rk, rv in run_ai_criteria.items():
                if rk in sub_dinh_tinh_keys and not inserted:
                    new_run_ai["dinh_tinh"] = ""
                    inserted = True
                new_run_ai[rk] = rv
            if not inserted:
                new_run_ai["dinh_tinh"] = ""
            st.session_state.ho_so_run_ai_criteria = new_run_ai
            run_ai_criteria = new_run_ai
        
        extracted_json["dinh_tinh"] = ""

    # (Debug log đã được xóa để không phụ thuộc vào đường dẫn cứng)

    sources = st.session_state.get("ho_so_sources", {})
    hsnl_raw_data = st.session_state.get("ho_so_hsnl_raw_data", {})
    hsnl_criteria = st.session_state.get("ho_so_hsnl_criteria", {})
    hsnl_unmapped = st.session_state.get("ho_so_hsnl_unmapped", {})
    
    # Lấy thứ tự chỉ tiêu hsnl đã lưu hoặc khởi tạo từ keys
    all_hsnl_keys = st.session_state.get("ho_so_hsnl_order")
    if not all_hsnl_keys:
        all_hsnl_keys = list(hsnl_raw_data.keys())
        st.session_state.ho_so_hsnl_order = all_hsnl_keys


    # Hiển thị tiêu đề và nút dịch song ngữ toàn bộ
    _bilingual_mode = st.session_state.get("ho_so_bilingual", True)
    _btn_label = "🤖 Dịch song ngữ toàn bộ" if _bilingual_mode else "🤖 Dịch sang Tiếng Việt"
    _btn_help = (
        "Dịch tự động tất cả các tên chỉ tiêu và nội dung phương pháp chưa có song ngữ sang Việt - Anh"
        if _bilingual_mode else
        "Dịch tự động tất cả nội dung sang Tiếng Việt thuần túy (không song ngữ)"
    )

    c_hdr_col, c_trans_col = st.columns([2, 1])
    with c_hdr_col:
        st.markdown("#### 📋 Các chỉ tiêu đã bóc tách:")
    with c_trans_col:
        if st.button(_btn_label, type="secondary", use_container_width=True, help=_btn_help):
            p3 = st.session_state.get("ho_so_p3", "Google API")
            m3 = st.session_state.get("ho_so_m3", "gemini-1.5-flash")
            _do_bilingual = st.session_state.get("ho_so_bilingual", True)

            # Chọn hàm dịch phù hợp
            def _translate(txt, ctx_type):
                if _do_bilingual:
                    return translate_text_to_bilingual(txt, p3, m3, ctx_type)
                else:
                    return translate_text_to_vietnamese_only(txt, p3, m3, ctx_type)

            progress_bar = st.progress(0.0)
            status_text = st.empty()
            translated_count = 0

            def needs_translation(txt):
                if not txt or not txt.strip():
                    return False
                # Nếu bilingual mode: kiểm tra đã có " / " chưa
                # Nếu Vietnamese mode: luôn cần dịch nếu có ký tự Latin nhiều
                if _do_bilingual:
                    temp_txt = txt
                    for unit in ["cfu/g", "mg/kg", "ug/g", "ug/mL", "dm2/g", "ml/g", "m3/g"]:
                        temp_txt = temp_txt.replace(unit, "")
                    return " / " not in temp_txt
                else:
                    # Cần dịch nếu text chứa nhiều từ tiếng Anh (có chứa " / " hoặc nhiều ký tự ASCII)
                    import re as _re
                    latin_words = _re.findall(r'\b[A-Za-z]{3,}\b', txt)
                    return len(latin_words) > 2

            valid_keys = [key_item for key_item in list(run_ai_criteria.keys()) if key_item in extracted_json and extracted_json[key_item] not in ["XOA_HANG", "XOA_DONG"]]
            # Thêm các chỉ tiêu hsnl vào danh sách dịch
            valid_hsnl_keys = [k for k in all_hsnl_keys if hsnl_raw_data.get(k, {}).get("chot", "") not in ["", "XOA_HANG"]]
            total_items = len(valid_keys) + len(valid_hsnl_keys)
            
            for idx, k_item in enumerate(valid_keys):
                label_name = master_data.get(k_item, {}).get("ten_hien_thi", k_item)
                if k_item.startswith("chi_tieu_khac_"):
                    name_key = k_item.replace("chi_tieu_khac_", "ten_chi_tieu_khac_")
                    alt_name = extracted_json.get(name_key, "")
                    if alt_name and alt_name not in ["XOA_HANG", ""]:
                        label_name = alt_name
                
                status_text.markdown(f"⏳ **Đang dịch chỉ tiêu {idx+1}/{total_items}:** `{label_name}`...")
                
                # 1. Dịch tên chỉ tiêu nếu là chi_tieu_khac_N
                if k_item.startswith("chi_tieu_khac_"):
                    name_key = k_item.replace("chi_tieu_khac_", "ten_chi_tieu_khac_")
                    current_name = st.session_state.get(f"edit_crit_name_{k_item}", extracted_json.get(name_key, "")).strip()
                    if needs_translation(current_name):
                        new_name = _translate(current_name, "criteria")
                        st.session_state[f"edit_crit_name_{k_item}"] = new_name
                        extracted_json[name_key] = new_name
                        translated_count += 1

                # 2. Dịch phương pháp (SOP)
                current_pp = st.session_state.get(f"edit_crit_{k_item}", "").strip()
                if needs_translation(current_pp):
                    new_pp = _translate(current_pp, "sop")
                    st.session_state[f"edit_crit_{k_item}"] = new_pp
                    translated_count += 1

                progress_bar.progress((idx + 1) / total_items)

            # Dịch các chỉ tiêu hsnl
            for h_idx, hk in enumerate(valid_hsnl_keys):
                ten_hsnl = st.session_state.get(f"edit_hsnl_ct_{hk}", hsnl_raw_data.get(hk, {}).get("ten", "")).strip()
                status_text.markdown(f"⏳ **Đang dịch chỉ tiêu hsnl {h_idx+1}/{len(valid_hsnl_keys)}:** `{ten_hsnl}`...")

                # Dịch tên chỉ tiêu hsnl
                if needs_translation(ten_hsnl):
                    new_ten = _translate(ten_hsnl, "criteria")
                    st.session_state[f"edit_hsnl_ct_{hk}"] = new_ten
                    translated_count += 1

                # Dịch yêu cầu
                yc_hsnl = st.session_state.get(f"edit_hsnl_yc_{hk}", hsnl_raw_data.get(hk, {}).get("yeu_cau", "")).strip()
                if needs_translation(yc_hsnl):
                    new_yc = _translate(yc_hsnl, "criteria")
                    st.session_state[f"edit_hsnl_yc_{hk}"] = new_yc
                    translated_count += 1

                # Dịch phương pháp hsnl
                pp_hsnl = st.session_state.get(f"edit_hsnl_pp_{hk}", hsnl_raw_data.get(hk, {}).get("chot", "")).strip()
                if needs_translation(pp_hsnl):
                    new_pp = _translate(pp_hsnl, "sop")
                    st.session_state[f"edit_hsnl_pp_{hk}"] = new_pp
                    translated_count += 1

                progress_bar.progress((len(valid_keys) + h_idx + 1) / total_items)

            _success_msg = (
                f"✅ Đã dịch song ngữ thành công! Đã dịch {translated_count} phần."
                if _do_bilingual else
                f"✅ Đã dịch sang Tiếng Việt thành công! Đã dịch {translated_count} phần."
            )
            status_text.success(_success_msg)
            progress_bar.empty()
            time.sleep(1.5)
            st.rerun()

    display_order = list(run_ai_criteria.keys())
    display_idx = 0

    for k in display_order:
        if k in extracted_json and extracted_json[k] not in ["XOA_HANG", "XOA_DONG"]:
            label = master_data.get(k, {}).get("ten_hien_thi", k)
            if k == "dinh_tinh":
                label = "Định tính"

            # Với chi_tieu_khac_N, lấy tên thực tế AI đã phát hiện
            if k.startswith("chi_tieu_khac_"):
                name_key = k.replace("chi_tieu_khac_", "ten_chi_tieu_khac_")
                alt_name = extracted_json.get(name_key, "")
                if alt_name and alt_name not in ["XOA_HANG", ""]:
                    label = alt_name

            val_sources = sources.get(k, {"duoc_dien": "", "tieu_chuan": "", "coa": "", "moa": "", "phu_luc": ""})
            duoc_dien_val = val_sources.get("duoc_dien", "").strip()
            tieu_chuan_val = val_sources.get("tieu_chuan", "").strip()
            coa_val = val_sources.get("coa", "").strip()
            moa_val = val_sources.get("moa", "").strip()
            ph_luc_val = val_sources.get("phu_luc", "").strip()

            # Các chỉ tiêu được lấy từ phụ lục chỉ tiêu chuyển sang màu đỏ và có ghi chú
            is_from_phu_luc = bool(ph_luc_val)
            header_color = "#ff3b30" if is_from_phu_luc else "#0071e3"
            note_suffix = " <span style='font-size: 13px; font-weight: normal; color: #ff3b30;'>(Có tài liệu trong Phụ lục chỉ tiêu)</span>" if is_from_phu_luc else ""

            is_sub_dinh_tinh = k in ["dinh_tinh_a", "dinh_tinh_b", "dinh_tinh_c", "dinh_tinh_d", "dinh_tinh_e", "dinh_tinh_f"]
            
            if is_sub_dinh_tinh:
                item_container = st.container(border=True)
            else:
                item_container = st.container()

            with item_container:
                if not is_sub_dinh_tinh:
                    display_idx += 1
                    st.markdown(f"<div style='margin-top: 25px; margin-bottom: 10px; font-weight: 600; font-size: 16px; color: {header_color};'>🔹 {display_idx}. {label}{note_suffix}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='margin-top: 5px; margin-bottom: 10px; font-weight: 600; font-size: 15px; color: #2c3e50;'>🔸 {label}{note_suffix}</div>", unsafe_allow_html=True)

                if k == "dinh_tinh":
                    # Đặt thành rỗng để giữ dòng Định tính trong Word
                    st.session_state[f"edit_crit_dinh_tinh"] = ""

                if k != "dinh_tinh":
                    # Hiển thị tên cho chỉ tiêu khác
                    if k.startswith("chi_tieu_khac_"):
                        name_key = k.replace("chi_tieu_khac_", "ten_chi_tieu_khac_")
                        st.text_input(
                            label=f"📝 Tên chỉ tiêu ({k})",
                            value=extracted_json.get(name_key, ""),
                            key=f"edit_crit_name_{k}"
                        )

                    # Khởi tạo giá trị trong session state cho trường chốt nếu chưa có
                    if f"edit_crit_{k}" not in st.session_state:
                        criteria_name = master_data.get(k, {}).get("ten_hien_thi", k)
                        if k.startswith("chi_tieu_khac_"):
                            name_key = k.replace("chi_tieu_khac_", "ten_chi_tieu_khac_")
                            alt_name = extracted_json.get(name_key, "")
                            if alt_name and alt_name not in ["XOA_HANG", ""]:
                                criteria_name = alt_name
                        
                        # Sử dụng SOP đã chọn trước ở Bước 2ab nếu có
                        sop_choice = st.session_state.get("ho_so_selected_sops", {}).get(criteria_name, "(AI tự bóc tách phương pháp)")
                        if sop_choice != "(AI tự bóc tách phương pháp)" and sop_choice in sop_library:
                            st.session_state[f"edit_crit_{k}"] = sop_library[sop_choice].get("noi_dung_sop", "")
                        else:
                            st.session_state[f"edit_crit_{k}"] = extracted_json[k]

                    # Hiển thị các nguồn bóc tách có dữ liệu kèm nút chọn
                    source_cols = st.columns(2)
                    col_idx = 0

                    # helper to render source block
                    def render_source_block(title, val, btn_label, col, key_prefix):
                        if val:
                            with col:
                                c_hdr, c_btn = st.columns([2.5, 1.5])
                                c_hdr.markdown(f"**{title}**")
                                if c_btn.button(btn_label, key=f"{key_prefix}_{k}_{display_idx}", use_container_width=True):
                                    st.session_state[f"edit_crit_{k}"] = val
                                    st.rerun()
                                st.text_area(
                                    label=title,
                                    value=val,
                                    height=120,
                                    disabled=True,
                                    label_visibility="collapsed",
                                    key=f"show_area_{key_prefix}_{k}"
                                )

                    # Dược điển
                    if duoc_dien_val:
                        render_source_block("📖 Cách làm ở Dược điển", duoc_dien_val, "📋 Sử dụng", source_cols[col_idx % 2], "dd")
                        col_idx += 1

                    # Tiêu chuẩn nguyên liệu
                    if tieu_chuan_val:
                        render_source_block("📄 Cách làm ở Tiêu chuẩn nguyên liệu", tieu_chuan_val, "📋 Sử dụng", source_cols[col_idx % 2], "tc")
                        col_idx += 1

                    # COA
                    if coa_val:
                        render_source_block("📙 Cách làm ở COA", coa_val, "📋 Sử dụng", source_cols[col_idx % 2], "coa")
                        col_idx += 1

                    # MOA
                    if moa_val:
                        render_source_block("📗 Cách làm ở MOA", moa_val, "📋 Sử dụng", source_cols[col_idx % 2], "moa")
                        col_idx += 1

                    # Phụ lục chỉ tiêu
                    if ph_luc_val:
                        render_source_block("📙 Cách làm ở Phụ lục chỉ tiêu", ph_luc_val, "📋 Sử dụng", source_cols[col_idx % 2], "pl")
                        col_idx += 1

                    # Ô nhập liệu Chốt cuối cùng
                    st.text_area(
                        label="✍️ Cách làm chốt cuối cùng (Có thể chỉnh sửa)",
                        key=f"edit_crit_{k}",
                        height=150
                    )

                    # Chọn phương pháp mẫu thay thế (SOP Library)
                    if sop_library:
                        sop_options = ["-- Chọn phương pháp mẫu thay thế (SOP Library) --"] + list(sop_library.keys())
                        def format_sop_option(op):
                            if op == "-- Chọn phương pháp mẫu thay thế (SOP Library) --":
                                return op
                            return f"{sop_library[op].get('ten_hien_thi', op)} ({op})"
                        
                        selected_sop_id = st.selectbox(
                            label="💡 Thay thế nhanh bằng phương pháp mẫu từ thư viện SOP",
                            options=sop_options,
                            index=0,
                            format_func=format_sop_option,
                            key=f"change_sop_select_{k}_{display_idx}",
                            on_change=on_sop_change_mapped,
                            args=(k, display_idx)
                        )

    if display_idx == 0:
        st.warning("Không có chỉ tiêu nào được bóc tách. Vui lòng quay lại và thử lại.")

    # ========== HIỂN THỊ CHỆ TIÊU HSNL (KHÔNG CÓ BẢNG) ==========
    if all_hsnl_keys:
        st.divider()
        st.markdown("<h4 style='color: #6c3483;'>📄 Các chỉ tiêu không có bảng (sử dụng tag hsnl)</h4>", unsafe_allow_html=True)
        st.info("Đây là các chỉ tiêu không có bảng thiết kế sẵn. Hệ thống sẽ tự động đánh số và điền vào tag hsnl_ct_N, hsnl_yc_N, hsnl_pp_N, hsnl_gh_N theo thứ tự dưới đây.")
        
        for h_idx, hk in enumerate(all_hsnl_keys):
            h_data = hsnl_raw_data.get(hk, {})
            h_chot = h_data.get("chot", "")
            
            if h_chot in ["XOA_HANG", ""]:
                continue
            
            h_slot = h_idx + 1  # số thứ tự N cho tag hsnl
            h_ten = h_data.get("ten", hk)
            h_yeu_cau = h_data.get("yeu_cau", "")
            h_gioi_han = h_data.get("gioi_han", "")
            
            # Label hiển thị
            if hk in hsnl_criteria:
                h_label = master_data.get(hk, {}).get("ten_hien_thi", h_ten or hk)
            else:
                h_label = h_ten or hk
            
            # Nguồn bóc tách
            h_duoc_dien = h_data.get("duoc_dien", "")
            h_tieu_chuan = h_data.get("tieu_chuan", "")
            h_coa = h_data.get("coa", "")
            h_moa = h_data.get("moa", "")
            h_ph_luc = h_data.get("phu_luc", "")
            is_from_phu_luc_h = bool(h_ph_luc)
            h_header_color = "#ff3b30" if is_from_phu_luc_h else "#6c3483"
            
            st.markdown(f"<div style='margin-top: 25px; margin-bottom: 10px; font-weight: 600; font-size: 16px; color: {h_header_color};'>➡️ hsnl_{h_slot}: {h_label}</div>", unsafe_allow_html=True)
            
            # 4 trường nhập liệu
            col_hsnl_1, col_hsnl_2 = st.columns(2)
            with col_hsnl_1:
                if f"edit_hsnl_ct_{hk}" not in st.session_state:
                    st.session_state[f"edit_hsnl_ct_{hk}"] = h_ten
                st.text_input(
                    label=f"🏷️ Tên chỉ tiêu (hsnl_ct_{h_slot})",
                    key=f"edit_hsnl_ct_{hk}"
                )
                
                if f"edit_hsnl_yc_{hk}" not in st.session_state:
                    st.session_state[f"edit_hsnl_yc_{hk}"] = h_yeu_cau
                st.text_area(
                    label=f"📝 Yêu cầu/Giới hạn (hsnl_yc_{h_slot})",
                    key=f"edit_hsnl_yc_{hk}",
                    height=80
                )
                
                if f"edit_hsnl_gh_{hk}" not in st.session_state:
                    st.session_state[f"edit_hsnl_gh_{hk}"] = h_gioi_han
                st.text_input(
                    label=f"🔢 Giới hạn số (hsnl_gh_{h_slot})",
                    key=f"edit_hsnl_gh_{hk}"
                )
            
            with col_hsnl_2:
                # Hiển thị nguồn bóc tách
                h_source_cols = st.columns(2)
                h_col_idx = 0

                def render_hsnl_source(title, val, col, key_prefix_h):
                    if val:
                        with col:
                            c_hdr_h, c_btn_h = st.columns([2, 1.5])
                            c_hdr_h.markdown(f"**{title}**")
                            if c_btn_h.button("📋 Sử dụng", key=f"{key_prefix_h}_{hk}", use_container_width=True):
                                st.session_state[f"edit_hsnl_pp_{hk}"] = val
                                st.rerun()
                            st.text_area(
                                label=title,
                                value=val,
                                height=80,
                                disabled=True,
                                label_visibility="collapsed",
                                key=f"show_h_{key_prefix_h}_{hk}"
                            )

                if h_duoc_dien: render_hsnl_source("📖 Dược điển", h_duoc_dien, h_source_cols[h_col_idx % 2], "hdd"); h_col_idx += 1
                if h_tieu_chuan: render_hsnl_source("📄 Tiêu chuẩn", h_tieu_chuan, h_source_cols[h_col_idx % 2], "htc"); h_col_idx += 1
                if h_coa: render_hsnl_source("📙 COA", h_coa, h_source_cols[h_col_idx % 2], "hcoa"); h_col_idx += 1
                if h_moa: render_hsnl_source("📗 MOA", h_moa, h_source_cols[h_col_idx % 2], "hmoa"); h_col_idx += 1
                if h_ph_luc: render_hsnl_source("📙 Phụ lục", h_ph_luc, h_source_cols[h_col_idx % 2], "hpl"); h_col_idx += 1
            
            # Ô phương pháp chốt
            if f"edit_hsnl_pp_{hk}" not in st.session_state:
                # Sử dụng SOP đã chọn trước ở Bước 2ab nếu có
                sop_choice = st.session_state.get("ho_so_selected_sops", {}).get(h_label, "(AI tự bóc tách phương pháp)")
                if sop_choice != "(AI tự bóc tách phương pháp)" and sop_choice in sop_library:
                    st.session_state[f"edit_hsnl_pp_{hk}"] = sop_library[sop_choice].get("noi_dung_sop", h_chot)
                else:
                    st.session_state[f"edit_hsnl_pp_{hk}"] = h_chot
            st.text_area(
                label=f"✍️ Phương pháp/Cách làm chốt (hsnl_pp_{h_slot})",
                key=f"edit_hsnl_pp_{hk}",
                height=150
            )
            
            # Chọn phương pháp mẫu (SOP Library)
            if sop_library:
                h_sop_opts = ["-- Chọn phương pháp mẫu (SOP Library) --"] + list(sop_library.keys())
                def format_h_sop(op):
                    if op == "-- Chọn phương pháp mẫu (SOP Library) --": return op
                    return f"{sop_library[op].get('ten_hien_thi', op)} ({op})"
                sel_h_sop = st.selectbox(
                    label=f"💡 Thay thế nhanh bằng phương pháp mẫu (hsnl_{h_slot})",
                    options=h_sop_opts, index=0,
                    format_func=format_h_sop,
                    key=f"hsnl_sop_select_{hk}",
                    on_change=on_sop_change_hsnl,
                    args=(hk,)
                )

    st.divider()
    if st.button("🚀 Bước 3: Xác Nhận & Xuất File Word", type="primary", use_container_width=True):
        ph_node = st.empty()
        draw_node(ph_node, "running", "Node 3: Kết xuất Word", "Đang nạp dữ liệu vào template...")

        try:
            # Thu thập thông tin hành chính động từ các widgets của Phase 0
            admin_data = {
                "don_vi": st.session_state.get("ho_so_don_vi", ""),
                "ten_thuong_mai": st.session_state.get("ho_so_ten_nl", ""),
                "lo_sx": st.session_state.get("ho_so_lo_sx", ""),
                "tieu_chuan": st.session_state.get("ho_so_tieu_chuan", ""),
                "ma_hang": st.session_state.get("ho_so_bfo_input", ""),
                "nha_san_xuat": st.session_state.get("ho_so_nha_sx", ""),
                "ngay_sx": st.session_state.get("ho_so_ngay_sx", ""),
                "han_dung": st.session_state.get("ho_so_han_dung", ""),
                "noi_lay_mau": st.session_state.get("ho_so_noi_lay_mau", ""),
                "ngay_lay_mau": st.session_state.get("ho_so_ngay_lay_mau", ""),
                "so_bm": st.session_state.get("ho_so_so_bm", ""),
                "ngay_bh": st.session_state.get("ho_so_ngay_bh", ""),
                "ngay_kt": ""
            }
            st.session_state.ho_so_admin_data = admin_data

            # Thu thập dữ liệu đã chỉnh sửa - chỉ tiêu CÓ bảng
            final_json = extracted_json.copy()
            for k in run_ai_criteria.keys():
                if k in final_json and final_json[k] not in ["XOA_HANG", "XOA_DONG"]:
                    final_json[k] = st.session_state.get(f"edit_crit_{k}", final_json[k])

            # Thu thập dữ liệu hsnl (chỉ tiêu KHÔNG có bảng)
            hsnl_slot = 0
            used_hsnl_slot_max = 0
            for hk in all_hsnl_keys:
                h_data = hsnl_raw_data.get(hk, {})
                h_chot = h_data.get("chot", "")
                if h_chot in ["XOA_HANG", ""]:
                    continue
                hsnl_slot += 1
                used_hsnl_slot_max = hsnl_slot
                final_json[f"hsnl_ct_{hsnl_slot}"] = st.session_state.get(f"edit_hsnl_ct_{hk}", h_data.get("ten", ""))
                final_json[f"hsnl_yc_{hsnl_slot}"] = st.session_state.get(f"edit_hsnl_yc_{hk}", h_data.get("yeu_cau", ""))
                final_json[f"hsnl_pp_{hsnl_slot}"] = st.session_state.get(f"edit_hsnl_pp_{hk}", h_chot)
                final_json[f"hsnl_gh_{hsnl_slot}"] = st.session_state.get(f"edit_hsnl_gh_{hk}", h_data.get("gioi_han", ""))
            
            # Gán XOA_HANG cho các slot hsnl chưa dùng
            for i in range(used_hsnl_slot_max + 1, MAX_HSNL_SLOTS + 1):
                final_json[f"hsnl_ct_{i}"] = "XOA_HANG"
                final_json[f"hsnl_yc_{i}"] = "XOA_HANG"
                final_json[f"hsnl_pp_{i}"] = "XOA_HANG"
                final_json[f"hsnl_gh_{i}"] = "XOA_HANG"

            # --- ÁNH XẠ CÁC KEY SANG PLACEHOLDER THỰC TẾ TRONG WORD TEMPLATE ---
            # Một số chỉ tiêu trong criteria_master.json có key khác với placeholder trong template
            KEY_MAPPINGS = {
                "cam_quan": "tinh_chat",               # Cảm quan → placeholder tinh_chat
                "cam_quan_dung_dich": "do_trong_mau_sac",  # Cảm quan dung dịch → do_trong_mau_sac
                "tap_chat_lien_quan": "tap_chat_hplc",  # Tạp chất HPLC → placeholder tap_chat_hplc
            }
            for src_key, dest_key in KEY_MAPPINGS.items():
                if src_key in final_json:
                    val = final_json[src_key]
                    if val not in ["XOA_HANG", "XOA_DONG", ""]:
                        final_json[dest_key] = val
                    elif dest_key not in final_json:
                        final_json[dest_key] = val

            # --- XỬ LÝ BẢNG LỒNG ĐỊNH TÍNH (nested table trong row 3) ---
            # Dùng "DT_XOA" thay "XOA_HANG" cho dinh_tinh_a..f không có nội dung.
            # Lý do: bảng lồng định tính nằm TRONG ô hàng định tính chính.
            # Nếu dùng "XOA_HANG", khi word_exporter đọc đệ quy (.//w:t) vào bảng lồng,
            # text của hàng cha sẽ chứa "XOA_HANG" → hàng cha bị xóa nhầm.
            # "DT_XOA" được xử lý riêng trong word_exporter (BƯỚC 0b) — xóa cả 2 rows
            # liên tiếp (heading + checkbox "Đúng/Không đúng") khi phương pháp không có.
            _DT_SUBS = ["dinh_tinh_a", "dinh_tinh_b", "dinh_tinh_c",
                        "dinh_tinh_d", "dinh_tinh_e", "dinh_tinh_f"]
            _dt_main_val = str(final_json.get("dinh_tinh", "XOA_HANG")).strip().upper()
            # QUAN TRỌNG: dùng "not in" thuần túy, KHÔNG dùng "_dt_main_val and ..."
            # vì khi dinh_tinh="" (chuỗi rỗng), "" and ... = "" = False (falsy) → sai!
            # dinh_tinh="" = có định tính (chỉ là sub-tests a..f chứa nội dung thực tế)
            # dinh_tinh="XOA_HANG" = KHÔNG có định tính → mới xóa
            _dt_main_active = _dt_main_val not in ["XOA_HANG", "XOA_DONG"]

            # bang_dinh_tinh LUÔN LUÔN là "" (KHÔNG BAO GIỜ "DT_XOA").
            # Lý do: {{ bang_dinh_tinh }} nằm CÙNG CELL với {{ dinh_tinh_a }} trong Row 0
            # của nested table. Nếu gán "DT_XOA" thì cell của Row A sẽ chứa
            # "DT_XOA" + "A. Theo..." → BƯỚC 0b nhận diện DT_XOA và XÓA NHẦM Row A.
            # Khi định tính không có (XOA_HANG): tất cả dinh_tinh_a..f = "DT_XOA"
            # → BƯỚC 0b sẽ tự xóa hết 12 rows của nested table.
            final_json["bang_dinh_tinh"] = ""

            # Từng phương pháp con: dùng DT_XOA nếu không có nội dung;
            # nếu có nội dung → thêm nhãn chữ cái (A., B., C...) để dễ nhận biết trong Word.
            _DT_LABELS = ["A", "B", "C", "D", "E", "F"]
            for _idx, _sub_k in enumerate(_DT_SUBS):
                _sub_raw = final_json.get(_sub_k, "")
                _sub_str = str(_sub_raw).strip()
                _sub_upper = _sub_str.upper()
                if _sub_upper in ["", "XOA_HANG", "XOA_DONG"] or not _sub_str:
                    final_json[_sub_k] = "DT_XOA"
                else:
                    # Thêm nhãn chữ cái nếu chưa có (tránh thêm trùng khi render lại)
                    _lbl = _DT_LABELS[_idx]
                    _prefixes_to_check = [
                        f"{_lbl}.", f"{_lbl} .", f"{_lbl}:",
                        f"Định tính {_lbl}", f"dinh tinh {_lbl.lower()}",
                    ]
                    _already_labeled = any(
                        _sub_str.startswith(p) or _sub_str.startswith(p.lower())
                        for p in _prefixes_to_check
                    )
                    if not _already_labeled:
                        final_json[_sub_k] = f"{_lbl}. {_sub_str}"
                    # Nếu đã có nhãn → giữ nguyên


            # --- XỬ LÝ CÁC THAM SỐ ĐIỀU KIỆN SẮC KÝ HPLC ---
            # Template có các placeholder điều kiện HPLC trong hàng header của bảng Định lượng HPLC
            # Nếu dinh_luong_hplc hoặc tap_chat_lien_quan bị xóa → set các param về XOA_HANG tương ứng
            HPLC_CONDITION_PARAMS = [
                "gioi_han", "cot", "detector", "toc_do_dong",
                "nhiet_do_cot", "nhiet_do_buong_tiem", "the_tich_tiem",
                "thoi_gian_chay", "chuan_doi_chieu",
                "thich_hop_he_thong_1", "thich_hop_he_thong_2",
                "thich_hop_he_thong_3", "thich_hop_he_thong_4"
            ]
            hplc_val = str(final_json.get("dinh_luong_hplc", "XOA_HANG")).strip().upper()
            tc_val = str(final_json.get("tap_chat_lien_quan", "XOA_HANG")).strip().upper()
            is_hplc_val_active = hplc_val and hplc_val not in ["XOA_HANG", "XOA_DONG"]
            is_tc_val_active = tc_val and tc_val not in ["XOA_HANG", "XOA_DONG"]
            is_hplc_active = is_hplc_val_active or is_tc_val_active

            # Tự động bóc tách tham số HPLC từ nội dung đã chốt
            def extract_hplc_param_from_text(text):
                params = {}
                if not text:
                    return params
                import re
                lines = str(text).replace("\\n", "\n").split("\n")
                for line in lines:
                    line_str = line.strip()
                    line_clean = re.sub(r'^[✓\-\*\s]+', '', line_str).strip()
                    if not line_clean:
                        continue
                    if ":" in line_clean:
                        parts = line_clean.split(":", 1)
                        key_part = parts[0].strip().lower()
                        val_part = parts[1].strip()
                        
                        if any(k in key_part for k in ["cột sắc ký", "cột", "column"]):
                            params["cot"] = val_part
                        elif any(k in key_part for k in ["detector", "đầu dò", "spectrophotometer"]):
                            params["detector"] = val_part
                        elif any(k in key_part for k in ["tốc độ dòng", "flow rate"]):
                            params["toc_do_dong"] = val_part
                        elif any(k in key_part for k in ["nhiệt độ buồng tiêm mẫu", "nhiệt độ buồng tiêm", "nhiệt độ buồng bơm mẫu", "nhiệt độ buồng bơm", "nhiệt độ khay tiêm", "sampler temperature"]):
                            params["nhiet_do_buong_tiem"] = val_part
                        elif any(k in key_part for k in ["nhiệt độ cột sắc ký", "nhiệt độ cột", "nhiệt độ", "column temperature", "column temp"]):
                            if "nhiet_do_cot" not in params:
                                params["nhiet_do_cot"] = val_part
                        elif any(k in key_part for k in ["thể tích tiêm", "thể tích bơm", "injection volume"]):
                            params["the_tich_tiem"] = val_part
                        elif any(k in key_part for k in ["thời gian chạy sắc ký", "thời gian chạy", "run time"]):
                            params["thoi_gian_chay"] = val_part
                return params

            extracted_params = {}
            if is_hplc_val_active:
                extracted_params = extract_hplc_param_from_text(final_json.get("dinh_luong_hplc", ""))
            
            if is_tc_val_active:
                tc_extracted = extract_hplc_param_from_text(final_json.get("tap_chat_lien_quan", ""))
                for pk, pv in tc_extracted.items():
                    if not extracted_params.get(pk) and pv:
                        extracted_params[pk] = pv

            for param in HPLC_CONDITION_PARAMS:
                # Riêng gioi_han chỉ hoạt động nếu dinh_luong_hplc hoạt động
                if param == "gioi_han":
                    final_json[param] = "" if is_hplc_val_active else "XOA_HANG"
                else:
                    # Nếu param được bóc tách từ nội dung và có giá trị -> điền vào
                    if param in extracted_params and extracted_params[param]:
                        final_json[param] = extracted_params[param]
                    elif param not in final_json or not str(final_json.get(param, "")).strip():
                        # Nếu không bóc tách được nhưng HPLC vẫn hoạt động -> giữ trống, ngược lại -> XOA_HANG
                        final_json[param] = "" if is_hplc_active else "XOA_HANG"

            # Tự động lược bỏ phần "A. Điều kiện sắc ký" và bảng chương trình chạy Gradient để không lặp lại trong nội dung kết xuất
            def strip_hplc_conditions_section(text):
                if not text or str(text).strip() in ["XOA_HANG", "XOA_DONG", ""]:
                    return text
                import re
                
                def line_clean_for_regex(s):
                    return s.replace("**", "").replace("*", "").replace("__", "").replace("_", "").strip()

                normalized_text = str(text).replace("\\n", "\n")
                lines = normalized_text.split("\n")
                new_lines = []
                in_section_a = False
                
                a_pattern = re.compile(r'^\s*(đại|điều kiện sắc ký|chromatographic conditions)', re.IGNORECASE)
                b_pattern = re.compile(r'^\s*(nội dung|cách tiến hành|chuẩn bị mẫu|procedure|thích hợp hệ thống|system suitability)', re.IGNORECASE)
                
                for line in lines:
                    line_strip = line.strip()
                    cleaned_line = line_clean_for_regex(line_strip)
                    
                    # Lược bỏ các dòng chứa bảng markdown (Gradient) để không in ra ô kết quả thô
                    if line_strip.count("|") >= 2:
                        continue
                    
                    # Loại bỏ tiền tố dạng "A. " hoặc "a. "
                    cleaned_without_prefix = re.sub(r'^[a-zA-Z]\.\s*', '', cleaned_line).strip()
                    
                    # Nếu bắt đầu phần A
                    if a_pattern.match(cleaned_without_prefix):
                        in_section_a = True
                        continue
                        
                    # Nếu bắt đầu phần B
                    if b_pattern.match(cleaned_without_prefix):
                        in_section_a = False
                        
                    if in_section_a:
                        continue
                        
                    new_lines.append(line)
                    
                result_text = "\n".join(new_lines)
                result_text = re.sub(r'\n{3,}', '\n\n', result_text)
                return result_text.strip()

            def extract_gradient_table_from_text(text):
                rows = []
                if not text or str(text).strip() in ["XOA_HANG", "XOA_DONG", ""]:
                    return rows
                
                lines = str(text).replace("\\n", "\n").split("\n")
                for line in lines:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    
                    if "|" in line_str:
                        parts = [p.strip() for p in line_str.split("|")]
                        if line_str.startswith("|"):
                            parts = parts[1:]
                        if line_str.endswith("|"):
                            parts = parts[:-1]
                            
                        # Skip separator line
                        if any(p and all(c in "-: " for c in p) for p in parts):
                            continue
                            
                        # Skip header line
                        parts_joined = " ".join(parts).lower()
                        if any(w in parts_joined for w in ["thời gian", "time", "pha động", "dung dịch", "a (%)", "b (%)"]):
                            continue
                            
                        if len(parts) >= 2:
                            tg = parts[0]
                            pha_a = parts[1]
                            pha_b = parts[2] if len(parts) > 2 else ""
                            rows.append({
                                "thoi_gian": tg,
                                "pha_a": pha_a,
                                "pha_b": pha_b
                            })
                return rows

            def split_tap_chat_at_gradient(text, has_gradient):
                """
                Tách nội dung tap_chat thành 2 phần để đặt bảng Gradient đúng vị trí:
                  - Phần A (tap_chat_hplc_a): nội dung từ đầu đến hết dòng tiêu đề Gradient
                  - Phần B (tap_chat_hplc_b): nội dung tiếp theo sau bảng Gradient
                Nếu không có gradient hoặc không tìm thấy tiêu đề: toàn bộ vào phần A, phần B rỗng.
                """
                if not has_gradient or not text:
                    return text, ""
                
                lines = text.split("\n")
                gradient_heading_idx = None
                # Tìm dòng tiêu đề "Chương trình chạy máy" hoặc "Gradient"
                for idx, line in enumerate(lines):
                    line_clean = line.strip().replace("**", "").lower()
                    if any(kw in line_clean for kw in [
                        "chương trình chạy máy",
                        "chương trình gradient",
                        "gradient program",
                    ]):
                        gradient_heading_idx = idx
                        break
                
                if gradient_heading_idx is None:
                    # Không tìm thấy tiêu đề → toàn bộ vào phần A
                    return text, ""
                
                # Phần A: từ đầu đến hết dòng tiêu đề (bao gồm tiêu đề)
                part_a_lines = lines[:gradient_heading_idx + 1]
                # Phần B: từ sau tiêu đề trở đi
                # Bỏ qua các dòng là hàng của markdown table (| ... |) trong phần B
                remaining = lines[gradient_heading_idx + 1:]
                part_b_lines = []
                for ln in remaining:
                    ln_strip = ln.strip()
                    # Bỏ qua dòng markdown table (| col | col |) — đã được đặt vào bảng Word
                    if ln_strip.startswith("|") or (ln_strip and all(c in "-| " for c in ln_strip)):
                        continue
                    part_b_lines.append(ln)
                
                part_a = "\n".join(part_a_lines).rstrip("\n")
                part_b = "\n".join(part_b_lines).lstrip("\n")
                return part_a, part_b

            # Trích xuất chương trình chạy Gradient từ nội dung HPLC hoặc Tạp chất trước khi strip
            gradient_rows = []
            if is_hplc_val_active:
                gradient_rows = extract_gradient_table_from_text(final_json.get("dinh_luong_hplc", ""))
            if not gradient_rows and is_tc_val_active:
                gradient_rows = extract_gradient_table_from_text(final_json.get("tap_chat_lien_quan", ""))
            
            has_gradient = len(gradient_rows) > 0
            # QUAN TRỌNG: Dùng "GR_XOA" thay vì "XOA_HANG" cho bảng Gradient.
            # Lý do: Bảng Gradient là bảng LỒNG bên trong ô của hàng tap_chat_hplc.
            # Khi word_exporter dùng .//w:t để thu thập cell text, nó đọc đệ quy
            # vào cả bảng lồng. Nếu dùng "XOA_HANG", hàng cha (tap_chat_hplc) sẽ
            # bị đánh dấu xóa nhầm vì cell text của nó chứa "XOA_HANG" từ bảng lồng.
            # "GR_XOA" được xử lý riêng trong word_exporter (Bước 0) trước bước XOA_HANG.
            final_json["bang_gradient"] = "" if has_gradient else "GR_XOA"
            
            for i in range(1, 16):  # Bao phủ tối đa 15 dòng gradient trong template
                tg_key = f"gr_tg_{i}"
                a_key = f"gr_a_{i}"
                b_key = f"gr_b_{i}"
                if has_gradient and (i - 1) < len(gradient_rows):
                    row_data = gradient_rows[i - 1]
                    final_json[tg_key] = row_data["thoi_gian"]
                    final_json[a_key] = row_data["pha_a"]
                    final_json[b_key] = row_data["pha_b"]
                else:
                    # Dùng GR_XOA (không phải XOA_HANG) để tránh nhiễu với hàng cha
                    final_json[tg_key] = "GR_XOA"
                    final_json[a_key] = "GR_XOA"
                    final_json[b_key] = "GR_XOA"

            # Áp dụng strip để lược bỏ A. Điều kiện sắc ký và bảng Gradient
            if is_hplc_val_active:
                stripped_hplc = strip_hplc_conditions_section(final_json.get("dinh_luong_hplc", ""))
                # Tách nội dung thành 2 phần quanh bảng Gradient (tương tự tap_chat_hplc):
                #   dinh_luong_hplc_a → trước bảng (đến hết dòng "Chương trình chạy máy")
                #   dinh_luong_hplc_b → sau bảng (phần còn lại)
                dl_part_a, dl_part_b = split_tap_chat_at_gradient(stripped_hplc, has_gradient)
                final_json["dinh_luong_hplc_a"] = dl_part_a
                final_json["dinh_luong_hplc_b"] = dl_part_b
                final_json["dinh_luong_hplc"] = stripped_hplc  # giữ fallback
            
            if is_tc_val_active:
                stripped_tc = strip_hplc_conditions_section(final_json.get("tap_chat_lien_quan", ""))
                final_json["tap_chat_lien_quan"] = stripped_tc
                # Tách nội dung thành 2 phần để bảng Gradient xuất hiện đúng vị trí trong Word:
                #   tap_chat_hplc_a → trước bảng (đến hết dòng tiêu đề "Chương trình chạy máy")
                #   tap_chat_hplc_b → sau bảng (phần còn lại)
                tc_part_a, tc_part_b = split_tap_chat_at_gradient(stripped_tc, has_gradient)
                final_json["tap_chat_hplc_a"] = tc_part_a
                final_json["tap_chat_hplc_b"] = tc_part_b
                # Giữ lại tap_chat_hplc cho các phiên bản cũ / fallback
                final_json["tap_chat_hplc"] = stripped_tc

            # Đảm bảo tap_chat_hplc_a và tap_chat_hplc_b luôn có giá trị
            # (phòng trường hợp is_tc_val_active = False hoặc không có HPLC tạp chất)
            if "tap_chat_hplc_a" not in final_json:
                final_json["tap_chat_hplc_a"] = final_json.get("tap_chat_hplc", "")
            if "tap_chat_hplc_b" not in final_json:
                final_json["tap_chat_hplc_b"] = ""

            # Đảm bảo dinh_luong_hplc_a và dinh_luong_hplc_b luôn có giá trị
            if "dinh_luong_hplc_a" not in final_json:
                final_json["dinh_luong_hplc_a"] = final_json.get("dinh_luong_hplc", "")
            if "dinh_luong_hplc_b" not in final_json:
                final_json["dinh_luong_hplc_b"] = ""

            # Xử lý bảng đi kèm (hỗ trợ các bảng dùng chung bởi nhiều chỉ tiêu)
            # Gom nhóm các chỉ tiêu (parent) theo từng bảng đi kèm (table_key)
            table_to_parents = {}
            for parent_key, config in master_data.items():
                table_keys = config.get("bang_di_kem", "")
                if not table_keys:
                    continue
                if isinstance(table_keys, list):
                    pass
                else:
                    table_keys = [table_keys]
                for t_key in table_keys:
                    if t_key not in table_to_parents:
                        table_to_parents[t_key] = []
                    table_to_parents[t_key].append(parent_key)

            # Một bảng sẽ bị xóa (nhận giá trị "XOA_HANG") chỉ khi TẤT CẢ các chỉ tiêu dùng chung bảng đó bị xóa hoặc trống
            for t_key, parents in table_to_parents.items():
                all_deleted = True
                for p_key in parents:
                    p_val = str(final_json.get(p_key, "XOA_HANG")).strip().upper()
                    if p_val and p_val not in ["XOA_HANG", "XOA_DONG"]:
                        all_deleted = False
                        break
                
                final_json[t_key] = "XOA_HANG" if all_deleted else ""

            # Lưu JSON debug
            st.session_state.ho_so_json_data = final_json.copy()
            st.session_state.ho_so_json_data.update(admin_data)

            # Tạo file Word
            template_file = st.session_state.ho_so_template_file
            final_io = node_4_generate_word(final_json, template_file, admin_data)

            st.session_state.ho_so_final_io = final_io
            bfo = admin_data.get("ma_hang", "KQ")
            st.session_state.ho_so_file_name = f"HSKNNL_{bfo}.docx"

            draw_node(ph_node, "success", "Node 3: Kết xuất Word", "Hồ sơ đã sẵn sàng tải xuống!")
            st.session_state.ho_so_phase = 3
            st.rerun()

        except Exception as e:
            draw_node(ph_node, "error", "Node 3: Lỗi kết xuất", str(e))
            st.error(f"❌ Lỗi kết xuất Word: {traceback.format_exc()}")
            st.stop()


# =====================================================================
# PHASE 3: TẢI XUỐNG
# =====================================================================
def render_ho_so_phase_3():
    st.divider()
    st.success("🎉 Bước 4: Hồ sơ kiểm nghiệm đã được tạo thành công!")

    tab_dl, tab_json = st.tabs(["📥 TẢI XUỐNG & LÀM MỚI", "👁️ XEM JSON DEBUG"])

    with tab_dl:
        col_dl, col_rs = st.columns(2)
        with col_dl:
            st.download_button(
                label="📥 Tải Hồ Sơ (.docx)",
                data=st.session_state.ho_so_final_io,
                file_name=st.session_state.ho_so_file_name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
                use_container_width=True
            )
        with col_rs:
            if st.button("🔄 Làm mới để tạo hồ sơ khác", use_container_width=True):
                for key in list(st.session_state.keys()):
                    if key.startswith("ho_so_"):
                        del st.session_state[key]
                st.rerun()
        
        # ── Nút Lưu làm Hồ Sơ Mẫu ─────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 💾 Lưu Hồ Sơ Này Làm Mẫu Để AI Học Phong Cách")
        st.caption("Lưu kết quả vừa tạo vào Thư Viện Hồ Sơ Mẫu. AI sẽ học phong cách trình bày từ hồ sơ này.")
        
        with st.expander("📥 Lưu làm Hồ Sơ Mẫu (click để mở)", expanded=False):
            json_data_debug = st.session_state.get("ho_so_json_data", {})
            ten_nl_default = json_data_debug.get("ten_hang", json_data_debug.get("ten_nguyen_lieu", ""))
            
            col_s1, col_s2 = st.columns([2, 1])
            with col_s1:
                ten_nl_save = st.text_input(
                    "Tên nguyên liệu/chế phẩm",
                    value=ten_nl_default,
                    key="save_mau_ten_nl"
                )
                mo_ta_save = st.text_input(
                    "Ghi chú về hồ sơ này",
                    placeholder="VD: Hồ sơ hoàn chỉnh, đã kiểm tra",
                    key="save_mau_mo_ta"
                )
            with col_s2:
                la_mau_vang_save = st.checkbox(
                    "⭐ Đánh dấu là Mẫu Vàng",
                    value=True,
                    key="save_mau_vang_check",
                    help="Mẫu Vàng được AI ưu tiên học nhất"
                )
                loai_tl_save = st.selectbox(
                    "Loại Dược điển",
                    ["Dược điển USP", "Dược điển BP", "Dược điển EP", "Dược điển DĐVN", "Tiêu chuẩn nội bộ", "Khác"],
                    key="save_mau_loai_tl"
                )
            
            if st.button("💾 Lưu vào Thư Viện Hồ Sơ Mẫu", type="primary", key="btn_luu_ho_so_mau"):
                try:
                    import os, json, time as _time
                    from datetime import datetime
                    
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    lib_path = os.path.join(base_dir, "style_examples_library.json")
                    
                    # Load thư viện
                    if os.path.exists(lib_path):
                        with open(lib_path, 'r', encoding='utf-8') as f:
                            lib_data = json.load(f)
                    else:
                        lib_data = {"_meta": {}}
                    
                    # Bóc tách ví dụ chi tiết từ json_data
                    extracted = st.session_state.get("ho_so_extracted_json", {})
                    vi_du_list = []
                    for ct_id, ct_val in extracted.items():
                        if isinstance(ct_val, dict):
                            ten_ct = ct_val.get("ten", ct_id) or ct_id
                            chot = ct_val.get("chot", "").strip()
                            if chot and chot not in ["XOA_HANG", "XOA_DONG", ""] and len(chot) > 20:
                                vi_du_list.append({
                                    "ten_chi_tieu": ten_ct,
                                    "noi_dung_mau": chot[:1200]
                                })
                    
                    # Tạo entry mới
                    import re, unicodedata
                    name = ten_nl_save.lower().strip()
                    name = unicodedata.normalize('NFD', name)
                    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
                    name = re.sub(r'[^a-z0-9 ]', '', name)
                    name = re.sub(r'\s+', '_', name)[:30]
                    ts = str(int(_time.time()))[-6:]
                    entry_id = f"{name}_{ts}"
                    
                    lib_data[entry_id] = {
                        "ten_nguyen_lieu": ten_nl_save.strip() or "Không rõ",
                        "loai_tai_lieu": loai_tl_save,
                        "mo_ta": mo_ta_save.strip(),
                        "la_mau_vang": la_mau_vang_save,
                        "ngay_tao": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "noi_dung_tom_tat": f"Hồ sơ {ten_nl_save} - {loai_tl_save}. {mo_ta_save}",
                        "vi_du_chi_tiet": vi_du_list[:8]  # Tối đa 8 chỉ tiêu
                    }
                    
                    with open(lib_path, 'w', encoding='utf-8') as f:
                        json.dump(lib_data, f, ensure_ascii=False, indent=4)
                    
                    st.success(f"✅ Đã lưu hồ sơ **'{ten_nl_save}'** vào Thư Viện Mẫu! ({len(vi_du_list)} chỉ tiêu mẫu)")
                    st.info("💡 Vào tab **🎨 Training AI** → **Thư Viện Hồ Sơ Mẫu** → **Phân Tích Phong Cách** để cập nhật AI.")
                except Exception as e:
                    st.error(f"❌ Lỗi lưu hồ sơ mẫu: {str(e)}")
        # ────────────────────────────────────────────────────────────────────────



    with tab_json:
        st.write(st.session_state.get("ho_so_json_data", {}))


# =====================================================================
# RENDER CHÍNH
# =====================================================================
def render_ho_so():
    st.markdown("<h2 style='text-align: center; color: #1d1d1f !important; font-weight: 600; letter-spacing: -0.02em; margin-bottom: 0;'>Lập Hồ Sơ Kiểm Nghiệm Nguyên Liệu</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; margin-bottom: 30px;'>Hệ thống AI tự động quét, bóc tách SOP và xuất hồ sơ kiểm nghiệm hoàn chỉnh.</p>", unsafe_allow_html=True)

    # Khởi tạo session state
    if 'ho_so_phase' not in st.session_state:
        st.session_state.ho_so_phase = 0

    # ─── CẤU HÌNH AI ─────────────────────────────────────────────────
    model_config = load_model_config()
    providers = list(model_config.keys())

    # Bước 1 luôn luôn hiển thị đầy đủ thông tin để người dùng xem/chỉnh sửa
    st.markdown("<h3 style='color: #0071e3;'>📋 Bước 1: Thông Tin & Tài Liệu Đầu Vào</h3>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("<h4 style='margin-top: 10px; color: #1d1d1f !important; font-weight: 600;'>Cấu hình AI</h4>", unsafe_allow_html=True)
        c1_2, c2_2, c3_2 = st.columns([1.5, 1, 1])
        c1_2.markdown("🌐 **AI Scanner:** Quét chỉ tiêu (Bước 1)")
        p2 = c2_2.selectbox("Provider Scan", providers, key="ho_so_sel_p2", label_visibility="collapsed")
        m2_options = model_config.get(p2, ["(Chưa có mô hình)"])
        m2 = c3_2.selectbox("Model Scan", m2_options, key="ho_so_sel_m2", label_visibility="collapsed")

        c1_3, c2_3, c3_3 = st.columns([1.5, 1, 1])
        c1_3.markdown("🧩 **AI Extractor:** Bóc tách SOP (Bước 2)")
        p3 = c2_3.selectbox("Provider Extract", providers, key="ho_so_sel_p3", label_visibility="collapsed")
        m3_options = model_config.get(p3, ["(Chưa có mô hình)"])
        m3 = c3_3.selectbox("Model Extract", m3_options, key="ho_so_sel_m3", label_visibility="collapsed")

        c1_4, c2_4, c3_4 = st.columns([1.5, 1, 1])
        c1_4.markdown("⚡ **Tốc độ:** Cấu hình song song")
        chunk_size = c2_4.number_input("Chỉ tiêu/lô", min_value=1, value=5, step=1, key="ho_so_chunk_size_input")
        max_workers = c3_4.number_input("Lô song song", min_value=1, value=3, step=1, key="ho_so_max_workers_input")

        c1_5, c2_5 = st.columns([1.5, 2])
        c1_5.markdown("🌐 **Dịch song ngữ:**")
        bilingual = c2_5.checkbox("Dịch song ngữ Việt - Anh", value=True, key="ho_so_bilingual_toggle_checkbox")

        # ─── THÔNG TIN HÀNH CHÍNH ────────────────────────────────────────────────
        st.markdown("<h4 style='margin-top: 25px; color: #1d1d1f !important; font-weight: 600;'>Hành chính & Lô sản xuất</h4>", unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            ten_nl = st.text_input("Tên nguyên liệu", key="ho_so_ten_nl")
            nha_sx = st.text_input("Nhà sản xuất / cung cấp", key="ho_so_nha_sx")
            noi_lay_mau = st.text_input("Nơi gửi/lấy mẫu", key="ho_so_noi_lay_mau")
        with col2:
            bfo = st.text_input("Mã hàng (BFO)", key="ho_so_bfo_input")
            lo_sx = st.text_input("Lô sản xuất", key="ho_so_lo_sx")
            ngay_lay_mau = st.text_input("Ngày lấy mẫu", key="ho_so_ngay_lay_mau")
        with col3:
            ngay_sx = st.text_input("Ngày sản xuất", key="ho_so_ngay_sx")
            tieu_chuan = st.text_input("Yêu cầu kiểm nghiệm", key="ho_so_tieu_chuan")
            ngay_bh = st.text_input("Ngày ban hành BM", key="ho_so_ngay_bh")
        with col4:
            han_dung = st.text_input("Hạn dùng", key="ho_so_han_dung")
            so_bm = st.text_input("Số BM", value="KN/HS/", key="ho_so_so_bm")
            don_vi = st.text_input("Đơn vị", value="CPC1 HÀ NỘI", key="ho_so_don_vi")

        # ─── TÀI LIỆU ĐẦU VÀO ────────────────────────────────────────────────
        st.markdown("<h4 style='margin-top: 25px; color: #1d1d1f !important; font-weight: 600;'>Tài liệu đầu vào (Tách biệt nguồn)</h4>", unsafe_allow_html=True)
        
        # Hàng 1: 4 nguồn chính
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown("<div style='background: #e8f1fd; padding: 8px; border-radius: 8px; font-size: 13px; text-align: center; font-weight: 500; margin-bottom: 5px;'>📘 Dược điển</div>", unsafe_allow_html=True)
            dd_files = st.file_uploader("DD", type=["pdf", "docx", "png", "jpg"], accept_multiple_files=True, key="ho_so_dd", label_visibility="collapsed")
        with c2:
            st.markdown("<div style='background: #e8f1fd; padding: 8px; border-radius: 8px; font-size: 13px; text-align: center; font-weight: 500; margin-bottom: 5px;'>📄 Tiêu chuẩn nguyên liệu</div>", unsafe_allow_html=True)
            tcnl_files = st.file_uploader("TCNL", type=["pdf", "docx", "png", "jpg"], accept_multiple_files=True, key="ho_so_tcnl", label_visibility="collapsed")
        with c3:
            st.markdown("<div style='background: #fff3cd; padding: 8px; border-radius: 8px; font-size: 13px; text-align: center; font-weight: 500; margin-bottom: 5px;'>📙 COA</div>", unsafe_allow_html=True)
            coa_files = st.file_uploader("COA", type=["pdf", "docx", "png", "jpg"], accept_multiple_files=True, key="ho_so_coa", label_visibility="collapsed")
        with c4:
            st.markdown("<div style='background: #d1e7dd; padding: 8px; border-radius: 8px; font-size: 13px; text-align: center; font-weight: 500; margin-bottom: 5px;'>📗 MOA</div>", unsafe_allow_html=True)
            moa_files = st.file_uploader("MOA", type=["pdf", "docx", "png", "jpg"], accept_multiple_files=True, key="ho_so_moa", label_visibility="collapsed")

        # Hàng 2: Phụ lục & Template
        c5, c6 = st.columns(2)
        with c5:
            st.markdown("<div style='background: #f8d7da; padding: 8px; border-radius: 8px; font-size: 13px; text-align: center; font-weight: 500; margin-bottom: 5px;'>📙 Phụ lục chỉ tiêu (Nếu có)</div>", unsafe_allow_html=True)
            extra_docs = st.file_uploader("Phụ lục", type=["pdf", "docx", "png", "jpg"], accept_multiple_files=True, key="ho_so_pl", label_visibility="collapsed")
        with c6:
            st.markdown("<div style='background: #d1e7dd; padding: 8px; border-radius: 8px; font-size: 13px; text-align: center; font-weight: 500; margin-bottom: 5px;'>📝 Template Word (Mặc định: KNNL)</div>", unsafe_allow_html=True)
            template_file = st.file_uploader("Template", type=["docx"], key="ho_so_template", label_visibility="collapsed")
            st.caption("Mặc định: Template_Form_KNNL.docx (nếu để trống)")

        st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

        if st.button("🚀 Bước 1: Quét Chỉ Tiêu Từ Tài Liệu", type="primary", use_container_width=True):
            has_any = dd_files or tcnl_files or coa_files or moa_files
            if not has_any:
                st.error("Vui lòng tải lên ít nhất 1 tài liệu đầu vào (Dược điển, Tiêu chuẩn nguyên liệu, COA, hoặc MOA)!")
                st.stop()
            # Nếu không tải lên template mới, sử dụng template mặc định KNNL
            if not template_file:
                import io
                default_template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Template_Form_KNNL.docx")
                if not os.path.exists(default_template_path):
                    default_template_path = "Template_Form_KNNL.docx"
                
                if os.path.exists(default_template_path):
                    with open(default_template_path, "rb") as f:
                        template_file = io.BytesIO(f.read())
                else:
                    st.error("Không tìm thấy file Template mặc định 'Template_Form_KNNL.docx'! Vui lòng tải lên file Template Word.")
                    st.stop()

            ph_progress = st.empty()
            ph_node = st.empty()
            draw_progress(ph_progress, 5, "Kiểm tra API key...")

            # Kiểm tra API key trước khi bắt đầu scan
            from core.key_manager import get_active_keys
            test_keys = get_active_keys(p2, m2)
            if not test_keys:
                if st.session_state.get("api_dek") is None:
                    st.error(
                        "🔒 Hệ thống đang khóa API Key.\n\n"
                        "Vui lòng vào tab **🔐 Quản Lý API Keys & Cấu hình** bên thanh trái để đăng nhập và mở khóa trước khi sử dụng!"
                    )
                else:
                    st.error(
                        f"❌ Không có API Key nào đang kích hoạt cho model **{m2}** (Provider: **{p2}**).\n\n"
                        f"Vui lòng vào **🔐 Quản Lý API Keys & Cấu hình** để thêm và kích hoạt API key."
                    )
                st.stop()

            draw_progress(ph_progress, 10, "Bắt đầu quét từng nguồn tài liệu...")            

            try:
                # Quét song song từng rổ
                source_buckets = {}
                if dd_files: source_buckets["Dược điển"] = dd_files
                if tcnl_files: source_buckets["Tiêu chuẩn nguyên liệu"] = tcnl_files
                if coa_files: source_buckets["COA"] = coa_files
                if moa_files: source_buckets["MOA"] = moa_files

                draw_node(ph_node, "running", "Node 1: AI đang quét từng rổ tài liệu...", f"Đang xử lý {len(source_buckets)} nguồn song song.")

                source_results = {}
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(source_buckets)) as executor:
                    future_map = {}
                    for label, files in source_buckets.items():
                        g_keys = test_keys if p2 == "Google API" else None
                        o_keys = test_keys if p2 == "OpenAI" else None
                        future = executor.submit(
                            tcnl_scan_criteria_and_limits,
                            files, label, p2, m2, g_keys, o_keys, bilingual
                        )
                        future_map[future] = label
                    
                    for future in concurrent.futures.as_completed(future_map):
                        label = future_map[future]
                        try:
                            source_results[label] = future.result()
                        except Exception as e:
                            source_results[label] = []
                            st.warning(f"⚠️ Lỗi quét nguồn '{label}': {str(e)}")

                draw_progress(ph_progress, 70, "Đang gộp và so sánh các nguồn...")

                # Gộp thành danh sách hợp nhất
                unified_names, source_map = _merge_criteria_union(source_results)
                
                # Tạo DataFrame so sánh với đầy đủ 4 cột
                rows = []
                for idx, name in enumerate(unified_names, 1):
                    # Mặc định giới hạn chốt lấy theo mức ưu tiên: Tiêu chuẩn nguyên liệu -> Dược điển -> COA -> MOA
                    limit_val = (source_map.get(name, {}).get("Tiêu chuẩn nguyên liệu", "") or
                                 source_map.get(name, {}).get("Dược điển", "") or
                                 source_map.get(name, {}).get("COA", "") or
                                 source_map.get(name, {}).get("MOA", ""))
                    row = {
                        "STT": idx,
                        "Tên Chỉ Tiêu": name,
                        "Dược điển": source_map.get(name, {}).get("Dược điển", ""),
                        "Tiêu chuẩn nguyên liệu": source_map.get(name, {}).get("Tiêu chuẩn nguyên liệu", ""),
                        "COA": source_map.get(name, {}).get("COA", ""),
                        "MOA": source_map.get(name, {}).get("MOA", ""),
                        "✅ Chọn": True,
                        "Giới hạn chốt": limit_val
                    }
                    rows.append(row)

                scan_df = pd.DataFrame(rows)

                draw_node(ph_node, "success", "Node 1: Quét hoàn tất", f"Đã phát hiện {len(rows)} chỉ tiêu từ các nguồn.")
                draw_progress(ph_progress, 100, "Hoàn tất! Đang chuyển sang bảng tích chọn...")

                # Lưu vào session
                st.session_state.ho_so_scan_df = scan_df
                st.session_state.ho_so_p2 = p2
                st.session_state.ho_so_m2 = m2
                st.session_state.ho_so_p3 = p3
                st.session_state.ho_so_m3 = m3
                st.session_state.ho_so_chunk_size = chunk_size
                st.session_state.ho_so_max_workers = max_workers
                st.session_state.ho_so_template_file = template_file
                st.session_state.ho_so_bilingual = bilingual
                
                # Encode file theo từng nguồn và lưu vào session (dùng cho Bước 2 v2, tránh encode lại)
                draw_progress(ph_progress, 85, "Đang chuẩn bị tài liệu cho bóc tách...")
                files_by_source = {}
                with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(source_buckets))) as enc_exec:
                    enc_futures = {
                        enc_exec.submit(prepare_file_for_ai, files): label
                        for label, files in source_buckets.items()
                    }
                    for enc_future in concurrent.futures.as_completed(enc_futures):
                        enc_label = enc_futures[enc_future]
                        try:
                            files_by_source[enc_label] = enc_future.result()
                        except Exception:
                            files_by_source[enc_label] = []

                extra_files_data_enc = prepare_file_for_ai(extra_docs) if extra_docs else []
                st.session_state.ho_so_files_by_source = files_by_source
                st.session_state.ho_so_extra_files_data = extra_files_data_enc

                # Gom tất cả file để dùng cho bóc tách (fallback)
                all_uploaded_files = []
                for files in source_buckets.values():
                    all_uploaded_files.extend(files)
                st.session_state.ho_so_uploaded_files = all_uploaded_files
                st.session_state.ho_so_extra_docs = extra_docs
                
                # Lưu thông tin admin
                st.session_state.ho_so_admin_data = {
                    "don_vi": don_vi, "ten_thuong_mai": ten_nl, "lo_sx": lo_sx,
                    "tieu_chuan": tieu_chuan, "ma_hang": bfo, "nha_san_xuat": nha_sx,
                    "ngay_sx": ngay_sx, "han_dung": han_dung, "noi_lay_mau": noi_lay_mau,
                    "ngay_lay_mau": ngay_lay_mau, "so_bm": so_bm, "ngay_bh": ngay_bh, "ngay_kt": ""
                }

                st.session_state.ho_so_chot_done = False
                st.session_state.ho_so_sop_done = False
                if "ho_so_selected_sops" in st.session_state:
                    del st.session_state.ho_so_selected_sops
                if "ho_so_hsnl_order" in st.session_state:
                    del st.session_state.ho_so_hsnl_order

                st.session_state.ho_so_phase = 1
                time.sleep(1)
                st.rerun()

            except Exception as e:
                draw_node(ph_node, "error", "Node 1: Lỗi quét", str(e))
                st.error(f"❌ Lỗi Bước 1: {traceback.format_exc()}")
                st.stop()

    # RENDER CÁC BƯỚC TIẾP THEO (Nếu đã đạt phase tương ứng, không ẩn bước trước)
    if st.session_state.ho_so_phase >= 1:
        if "ho_so_scan_df" not in st.session_state or st.session_state.ho_so_scan_df is None:
            st.error("❌ Lỗi nội bộ: Không tìm thấy dữ liệu quét. Vui lòng chạy lại Bước 1.")
            st.session_state.ho_so_phase = 0
            st.rerun()
        elif st.session_state.ho_so_scan_df.empty:
            st.warning("⚠️ AI không quét được chỉ tiêu nào từ tài liệu. Hãy kiểm tra lại:\n- API Key đã được kích hoạt chưa?\n- File tài liệu có chứa dữ liệu không?\n- Thử lại Bước 1 với tài liệu khác.")
            if st.button("🔄 Quay lại Bước 1", key="ho_so_back_to_step1_empty"):
                st.session_state.ho_so_phase = 0
                st.rerun()
        else:
            render_ho_so_phase_1()

    if st.session_state.ho_so_phase >= 2:
        render_ho_so_phase_2()

    if st.session_state.ho_so_phase >= 3:
        render_ho_so_phase_3()