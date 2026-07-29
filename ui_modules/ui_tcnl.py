import streamlit as st
import streamlit.components.v1 as components
import json
import os
import time
import traceback
import pandas as pd
import unicodedata
import concurrent.futures

from core.doc_processor import (
    tcnl_scan_criteria_and_limits,
    tcnl_generate_methods,
    tcnl_extract_monograph_name,
)
from core.word_exporter import node_4_generate_word
from core.key_manager import load_model_config
from core.ai_handler import translate_text_to_bilingual, translate_text_to_vietnamese_only

# Callbacks for bilingual translations to avoid StreamlitAPIException
def translate_new_crit_callback():
    name = st.session_state.get("tcnl_new_crit_name", "")
    limit = st.session_state.get("tcnl_new_crit_limit", "")
    if name:
        p3 = st.session_state.get("tcnl_p3", "Google API")
        m3 = st.session_state.get("tcnl_m3", "gemini-1.5-flash")
        st.session_state["tcnl_new_crit_name"] = translate_text_to_bilingual(name, p3, m3, "criteria")
        st.session_state["tcnl_new_crit_limit"] = translate_text_to_bilingual(limit, p3, m3, "limit")

def translate_tcnl_crit_callback(idx):
    p3 = st.session_state.get("tcnl_p3", "Google API")
    m3 = st.session_state.get("tcnl_m3", "gemini-1.5-flash")
    current_ten = st.session_state[f"tcnl_draft_ten_{idx}"]
    current_yc = st.session_state[f"tcnl_draft_yc_{idx}"]
    st.session_state[f"tcnl_draft_ten_{idx}"] = translate_text_to_bilingual(current_ten, p3, m3, "criteria")
    st.session_state[f"tcnl_draft_yc_{idx}"] = translate_text_to_bilingual(current_yc, p3, m3, "limit")

def translate_tcnl_pp_callback(idx):
    p3 = st.session_state.get("tcnl_p3", "Google API")
    m3 = st.session_state.get("tcnl_m3", "gemini-1.5-flash")
    current_pp = st.session_state[f"tcnl_draft_pp_{idx}"]
    st.session_state[f"tcnl_draft_pp_{idx}"] = translate_text_to_bilingual(current_pp, p3, m3, "sop")

# Callbacks for SOP templates selection to avoid StreamlitAPIException
def on_sop_change_tcnl(idx):
    sel_key = f"tcnl_override_sop_{idx}"
    val = st.session_state.get(sel_key)
    if val and val != "-- Chọn phương pháp mẫu để ghi đè --":
        from ui_modules.ui_sop_library import load_sop_lib
        sop_library = load_sop_lib()
        if val in sop_library:
            st.session_state[f"tcnl_draft_pp_{idx}"] = sop_library[val].get("noi_dung_sop", "")
            # Reset selectbox to default
            st.session_state[sel_key] = "-- Chọn phương pháp mẫu để ghi đè --"

# Khai báo component kéo thả (Module level để tránh đăng ký lại nhiều lần gây lỗi load asset)
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_component_dir = os.path.join(_parent_dir, "core", "drag_drop_component")
_drag_drop_reorder = components.declare_component("drag_drop_reorder", path=_component_dir)

# =====================================================================
# TIỆN ÍCH: Chuẩn hóa tên chỉ tiêu để so sánh fuzzy
# =====================================================================
def _normalize_name(s):
    """Chuẩn hóa tên chỉ tiêu: lowercase, bỏ dấu, bỏ ký tự đặc biệt."""
    if not s: return ""
    import re
    import unicodedata
    
    # Thay thế chữ đ/Đ thành d/D để tránh bị xóa khi loại bỏ ký tự không thuộc a-z
    s = str(s).replace('đ', 'd').replace('Đ', 'd')
    
    nfkd = unicodedata.normalize('NFKD', s.lower().strip())
    s_clean = "".join([c for c in nfkd if not unicodedata.combining(c)])
    s_clean = re.sub(r'[^a-z0-9 ]', '', s_clean)
    s_clean = re.sub(r'\s+', ' ', s_clean).strip()
    
    # Từ điển đồng nghĩa rộng rãi cho Dược điển và COA/MOA
    synonyms = {
        "ham luong": "dinh luong",
        "assay": "dinh luong",
        "mat khoi luong do lam kho": "mat khoi luong do say",
        "mat khoi luong do say": "mat khoi luong do say",
        "loss on drying": "mat khoi luong do say",
        "drying": "mat khoi luong do say",
        "loss on ignition": "mat khoi luong do nung",
        "residue on ignition": "can sau nung",
        "sulfated ash": "tro sulfat",
        "heavy metals": "kim loai nang",
        "related substances": "tap chat lien quan",
        "related substance": "tap chat lien quan",
        "tap chat": "tap chat lien quan",
        "magnesi mg": "magnesium va kim loai kiem tho",
        "magnesi": "magnesium va kim loai kiem tho",
        "magnesium": "magnesium va kim loai kiem tho",
        "ferocyanid": "ferrocyanide",
        "ferocyanides": "ferrocyanide",
        "bromides": "bromide",
        "iodides": "iodide",
        "iode": "iodide",
        "iod": "iodide",
        "acidity or alkalinity": "gioi han acid kiem",
        "acid kiem": "gioi han acid kiem",
        "iron": "sat",
        "aluminium": "nhom",
        "appearance": "tinh chat",
        "characters": "tinh chat",
        "cam quan": "tinh chat",
        "ngoai quan": "tinh chat",
        "mo ta": "tinh chat",
        "description": "tinh chat",
        "do trong va mau sac": "do trong va mau sac",
        "do trong": "do trong va mau sac",
        "mau sac": "do trong va mau sac",
        "solubility": "do tan",
        "identification": "dinh tinh",
        "barium": "bari",
        "ammonium": "amoni",
        "sulfate": "sulfat",
        "sulfates": "sulfat",
        "sulphat": "sulfat",
        "sulphate": "sulfat",
        "sulphates": "sulfat",
        "chloride": "clorid",
        "arsenic": "asen",
        "lead": "chi",
        "zinc": "kem",
        "phosphate": "phosphat",
        "nitrite": "nitrit",
        # ---- Vi sinh / Nhiễm khuẩn --- tất cả variant map về cùng chuỗi chuẩn ----
        "microbial limits": "gioi han nhiem khuan vi sinh",
        "microbial limit": "gioi han nhiem khuan vi sinh",
        "microbiological purity": "gioi han nhiem khuan vi sinh",
        "microbiological examination": "gioi han nhiem khuan vi sinh",
        "microbial contamination": "gioi han nhiem khuan vi sinh",
        "gioi han nhiem khuan": "gioi han nhiem khuan vi sinh",
        "gioi han vi sinh": "gioi han nhiem khuan vi sinh",
        "kiem tra vi sinh": "gioi han nhiem khuan vi sinh",
        "nhiem khuan": "nhiem khuan vi sinh",
        "vi sinh vat": "nhiem khuan vi sinh",
    }
    
    for syn_key, syn_val in sorted(synonyms.items(), key=lambda x: len(x[0]), reverse=True):
        if syn_key in s_clean:
            s_clean = s_clean.replace(syn_key, syn_val)
            
    return s_clean.strip()

def _split_combined(name):
    """Tách chỉ tiêu gộp thành danh sách các chỉ tiêu đơn lẻ để đối chiếu."""
    if not name: return [name]
    import re
    # Chuyển về chữ thường để dễ bóc tách
    s = name.lower()
    # Tách theo các liên từ: " và ", " and ", " hoặc ", " or ", "/", "+", " va "
    parts = re.split(r'\bva\b|\band\b|\bhoac\b|\bor\b|/|\+', s)
    return [p.strip() for p in parts if p.strip()]

def _fuzzy_match_single(name1, name2):
    norm1 = _normalize_name(name1)
    norm2 = _normalize_name(name2)
    
    if not norm1 or not norm2:
        return False
        
    if norm1 == norm2:
        return True
        
    # Phân biệt rõ giữa chỉ tiêu chất rắn (tính chất/appearance) và chỉ tiêu dung dịch (appearance of solution / dung dịch)
    is_sol_1 = "solution" in norm1 or "dung dich" in norm1 or "do trong" in norm1 or "clarity" in norm1
    is_sol_2 = "solution" in norm2 or "dung dich" in norm2 or "do trong" in norm2 or "clarity" in norm2
    if is_sol_1 != is_sol_2:
        return False
        
    # Phân biệt rõ định tính và các chỉ tiêu giới hạn khác
    is_id_1 = "dinh tinh" in norm1 or "identification" in norm1
    is_id_2 = "dinh tinh" in norm2 or "identification" in norm2
    if is_id_1 != is_id_2:
        return False
        
    # Định lượng chung không được khớp fuzzy với Định lượng bằng HPLC
    if (norm1 == "dinh luong" and "hplc" in norm2) or (norm2 == "dinh luong" and "hplc" in norm1):
        return False
        
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    
    # 1. Kiểm tra xung đột hậu tố chỉ định (a, b, c vs 1, 2, 3...)
    sub_tests = {"a", "b", "c", "d", "e", "f", "g", "1", "2", "3", "4", "5", "i", "ii", "iii", "iv", "v"}
    sub_tests_1 = words1 & sub_tests
    sub_tests_2 = words2 & sub_tests
    if sub_tests_1 != sub_tests_2:
        return False
        
    # 2. Kiểm tra xung đột chất/ion (ví dụ: sắt vs nhôm, bromide vs iodide)
    substances = {
        "sat", "nhom", "barium", "calci", "magnesium", "kem", "chi", "asen", 
        "bromide", "iodide", "chloride", "sulfate", "ammonium", "ferrocyanide",
        "phosphate", "nitrite", "bari", "clorid", "sulfat", "amoni", "phat", "zinc",
        "magnesi", "ferocyanid", "bromides", "iodides", "iron", "aluminium"
    }
    subs_1 = words1 & substances
    subs_2 = words2 & substances
    if subs_1 and subs_2 and subs_1 != subs_2:
        return False
        
    # 2.5. Kiểm tra xung đột giữa chỉ tiêu tro/nung và chỉ tiêu giới hạn thông thường
    ash_words = {"tro", "ash", "ignition", "nung", "can"}
    has_ash_1 = any(w in norm1 for w in ash_words)
    has_ash_2 = any(w in norm2 for w in ash_words)
    if has_ash_1 != has_ash_2:
        return False
        
    # 3. Loại bỏ từ nhiễu để so sánh cốt lõi
    def clean_noise(w_set):
        noise = {"gioi", "han", "chi", "tieu", "phep", "thu", "do", "ve", "cua"}
        return {w for w in w_set if w not in noise}
        
    core1 = clean_noise(words1)
    core2 = clean_noise(words2)
    
    if not core1 or not core2:
        return False
        
    if core1 == core2:
        return True
        
    if core1.issubset(core2) or core2.issubset(core1):
        return True
        
    overlap = len(core1 & core2)
    max_len = max(len(core1), len(core2))
    
    return (overlap / max_len) >= 0.75

def _fuzzy_match(name1, name2):
    """
    So sánh chính xác 2 tên chỉ tiêu để quyết định xem có gộp chúng làm một hay không.
    Hỗ trợ cả trường hợp một bên là chỉ tiêu gộp (ví dụ: "Bromides và Iodides").
    """
    parts1 = _split_combined(name1)
    parts2 = _split_combined(name2)
    
    if len(parts1) > 1 or len(parts2) > 1:
        if len(parts1) > 1:
            for p1 in parts1:
                if _fuzzy_match_single(p1, name2):
                    return True
        if len(parts2) > 1:
            for p2 in parts2:
                if _fuzzy_match_single(name1, p2):
                    return True
        return False
        
    return _fuzzy_match_single(name1, name2)

def _merge_related_substances_in_source(items):
    """
    Gộp các chỉ tiêu liên quan đến Tạp chất liên quan / Related substances 
    trong cùng một nguồn dữ liệu thành một chỉ tiêu duy nhất.
    """
    if not items:
        return []
    new_items = []
    related_items = []
    for item in items:
        ten = item.get("ten_chi_tieu", "").strip()
        norm = _normalize_name(ten)
        # Check if "tap chat lien quan" is in the normalized name
        if "tap chat lien quan" in norm:
            related_items.append(item)
        else:
            new_items.append(item)
            
    if related_items:
        # Find a suitable unified name
        unified_name = "Tạp chất liên quan"
        # If any of the items is exactly "Tạp chất liên quan" or "Related substances", use that exact casing
        for ri in related_items:
            t_orig = ri.get("ten_chi_tieu", "").strip()
            if t_orig.lower() in ["tạp chất liên quan", "related substances", "related substance", "tạp chất"]:
                unified_name = t_orig
                break
        
        if len(related_items) == 1:
            # If there's only 1 related substances item, rename its field to the unified name
            new_items.append({
                "ten_chi_tieu": unified_name,
                "gioi_han": related_items[0].get("gioi_han", "").strip()
            })
        else:
            limit_lines = []
            for ri in related_items:
                t_orig = ri.get("ten_chi_tieu", "").strip()
                lim_val = ri.get("gioi_han", "").strip()
                
                # Try to extract the sub-title (e.g. "Bất kỳ tạp chất đơn lẻ nào" from "Tạp chất liên quan - Bất kỳ tạp chất đơn lẻ nào")
                sub_title = ""
                for sep in [" - ", " -", "- ", "-", " : ", " :", ": ", ":"]:
                    if sep in t_orig:
                        parts = t_orig.split(sep, 1)
                        if "tap chat" in _normalize_name(parts[0]) or "related" in _normalize_name(parts[0]):
                            sub_title = parts[1].strip()
                            break
                if not sub_title:
                    sub_title = t_orig
                
                if sub_title:
                    sub_title = sub_title[0].upper() + sub_title[1:]
                
                limit_lines.append(f"- {sub_title}: {lim_val}")
            
            merged_limit = "\n".join(limit_lines)
            new_items.append({
                "ten_chi_tieu": unified_name,
                "gioi_han": merged_limit
            })
            
    return new_items

def _merge_identifications_in_source(items):
    """
    Gộp các chỉ tiêu liên quan đến Định tính / Identification
    trong cùng một nguồn dữ liệu thành một chỉ tiêu duy nhất.
    """
    if not items:
        return []
    new_items = []
    id_items = []
    for item in items:
        ten = item.get("ten_chi_tieu", "").strip()
        norm = _normalize_name(ten)
        if "dinh tinh" in norm:
            id_items.append(item)
        else:
            new_items.append(item)
            
    if id_items:
        unified_name = "Định tính / Identification"
        
        if len(id_items) == 1:
            new_items.append({
                "ten_chi_tieu": unified_name,
                "gioi_han": id_items[0].get("gioi_han", "").strip()
            })
        else:
            def get_suffix(name):
                import re
                m = re.search(r'(?i)(?:định tính|identification)\s+([a-g1-9])', name)
                if m:
                    return m.group(1).upper()
                return name
            
            id_items_sorted = sorted(id_items, key=lambda x: get_suffix(x.get("ten_chi_tieu", "")))
            
            limit_lines = []
            for item in id_items_sorted:
                t_orig = item.get("ten_chi_tieu", "").strip()
                lim_val = item.get("gioi_han", "").strip()
                suffix = get_suffix(t_orig)
                if len(suffix) == 1:
                    limit_lines.append(f"- {suffix}: {lim_val}")
                else:
                    limit_lines.append(f"- {t_orig}: {lim_val}")
            
            merged_limit = "\n".join(limit_lines)
            new_items.append({
                "ten_chi_tieu": unified_name,
                "gioi_han": merged_limit
            })
            
    return new_items


def _merge_microbial_limits_in_source(items):
    """
    Gộp các chỉ tiêu liên quan đến Giới hạn nhiễm khuẩn / Vi sinh / Microbial limits
    trong cùng một nguồn dữ liệu thành một chỉ tiêu duy nhất.
    """
    if not items:
        return []
    new_items = []
    microbial_items = []
    for item in items:
        ten = item.get("ten_chi_tieu", "").strip()
        norm = _normalize_name(ten)
        # Check if any microbial keywords are in the normalized name
        if "nhiem khuan" in norm or "vi sinh" in norm or "microbial" in norm or "microbiological" in norm:
            microbial_items.append(item)
        else:
            new_items.append(item)
            
    if microbial_items:
        # Luôn dùng tên chuẩn nhất quán để cross-source merge hoạt động
        # Kiểm tra ngôn ngữ: nếu có song ngữ thì giữ song ngữ, không thì dùng tiếng Việt
        has_bilingual = any("/" in mi.get("ten_chi_tieu", "") for mi in microbial_items)
        if has_bilingual:
            unified_name = "Giới hạn nhiễm khuẩn / Microbial limits"
        else:
            unified_name = "Giới hạn nhiễm khuẩn"
        
        if len(microbial_items) == 1:
            new_items.append({
                "ten_chi_tieu": unified_name,
                "gioi_han": microbial_items[0].get("gioi_han", "").strip()
            })
        else:
            limit_lines = []
            for mi in microbial_items:
                t_orig = mi.get("ten_chi_tieu", "").strip()
                lim_val = mi.get("gioi_han", "").strip()
                
                # Try to extract the sub-title (e.g. "Tổng số vi khuẩn hiếu khí" from "Giới hạn nhiễm khuẩn - Tổng số vi khuẩn hiếu khí")
                sub_title = ""
                for sep in [" - ", " -", "- ", "-", " : ", " :", ": ", ":"]:
                    if sep in t_orig:
                        parts = t_orig.split(sep, 1)
                        norm_part = _normalize_name(parts[0])
                        if any(k in norm_part for k in ["nhiem khuan", "vi sinh", "microbial", "microbiological"]):
                            sub_title = parts[1].strip()
                            break
                if not sub_title:
                    sub_title = t_orig
                
                if sub_title:
                    sub_title = sub_title[0].upper() + sub_title[1:]
                
                limit_lines.append(f"- {sub_title}: {lim_val}")
            
            merged_limit = "\n".join(limit_lines)
            new_items.append({
                "ten_chi_tieu": unified_name,
                "gioi_han": merged_limit
            })
            
    return new_items


def _match_name_to_master_tcnl(name, master_data):
    if not name: return None
    norm_name = _normalize_name(name)
    # 1. Exact/Normalize match
    for ma_id, config in master_data.items():
        ten_hien_thi = config.get("ten_hien_thi", "")
        if _normalize_name(ten_hien_thi) == norm_name or norm_name == _normalize_name(ma_id):
            return config.get("ten_hien_thi", "")
        if "/" in ten_hien_thi:
            parts = [p.strip() for p in ten_hien_thi.split("/")]
            for p in parts:
                if _normalize_name(p) == norm_name:
                    return config.get("ten_hien_thi", "")
    # 2. Substring matching
    ash_words = {"tro", "ash", "ignition", "nung", "can"}
    has_ash_scanned = any(w in norm_name for w in ash_words)
    
    # Danh sách các chất hóa học/ion đặc thù
    substances = {
        "sat", "nhom", "barium", "calci", "magnesium", "kem", "chi", "asen", 
        "bromide", "iodide", "chloride", "sulfate", "ammonium", "ferrocyanide",
        "phosphate", "nitrite", "bari", "clorid", "sulfat", "amoni", "phat", "zinc",
        "magnesi", "ferocyanid", "bromides", "iodides", "iron", "aluminium"
    }
    words_scanned = set(norm_name.split())
    subs_scanned = words_scanned & substances

    for ma_id, config in master_data.items():
        ten_hien_thi = config.get("ten_hien_thi", "")
        norm_master = _normalize_name(ten_hien_thi)
        
        # Tránh trùng lặp từ đồng âm khác nghĩa sau khi bỏ dấu (ví dụ: "nhôm" vs "nhóm", "chì" vs "chỉ")
        # Nếu master là định tính mà scanned không phải định tính -> không cho khớp substring
        is_id_scanned = "dinh tinh" in norm_name or "identification" in norm_name
        is_id_master = "dinh tinh" in norm_master or "identification" in norm_master
        if is_id_scanned != is_id_master:
            continue
            
        # Định lượng chung không được khớp substring với Định lượng bằng HPLC
        if norm_name == "dinh luong" and "hplc" in norm_master:
            continue
            
        if norm_master in norm_name or norm_name in norm_master:
            # Kiểm tra xung đột chất hóa học
            words_master = set(norm_master.split())
            subs_master = words_master & substances
            # Nếu một bên chứa chất/ion đặc thù mà bên kia không chứa chất/ion đó -> không khớp
            if subs_scanned != subs_master:
                continue
                
            has_ash_master = any(w in norm_master for w in ash_words)
            if has_ash_scanned != has_ash_master:
                continue
            return config.get("ten_hien_thi", "")
            
    # 3. Fuzzy matching using _fuzzy_match
    for ma_id, config in master_data.items():
        ten_hien_thi = config.get("ten_hien_thi", "")
        if _fuzzy_match(name, ten_hien_thi):
            return config.get("ten_hien_thi", "")
    return None


def _merge_criteria_union(source_data_dict):
    """Gộp tất cả tên chỉ tiêu từ nhiều nguồn thành danh sách hợp nhất.
    source_data_dict: {"Dược điển": [...], "COA": [...], ...}
    
    Trả về:
    - unified_names: ["Tính chất", "Định tính", ...]
    - source_map: {"Tính chất": {"Dược điển": "Bột trắng...", "COA": "White powder..."}}
    """
    unified_names = []
    source_map = {}  # {unified_name: {source_label: gioi_han}}
    
    # Ưu tiên duyệt "Dược điển" trước để làm chuẩn
    def sort_key(k):
        kl = k.lower()
        if "dược điển" in kl: return 0
        if "tiêu chuẩn" in kl: return 1
        if "coa" in kl: return 2
        return 3
        
    sorted_sources = sorted(source_data_dict.keys(), key=sort_key)
    
    for source_label in sorted_sources:
        criteria_list = _merge_related_substances_in_source(source_data_dict[source_label])
        criteria_list = _merge_identifications_in_source(criteria_list)
        criteria_list = _merge_microbial_limits_in_source(criteria_list)
        for item in criteria_list:
            ten = item.get("ten_chi_tieu", "").strip()
            gioi_han = item.get("gioi_han", "").strip()
            if not ten: continue
            
            # Tìm xem tên này đã có trong danh sách hợp nhất chưa (fuzzy match)
            matched_names = []
            for existing_name in unified_names:
                if _fuzzy_match(ten, existing_name):
                    matched_names.append(existing_name)
            
            if matched_names:
                for matched_name in matched_names:
                    # Ghi chú nếu tài liệu phụ gộp chỉ tiêu (ví dụ: Bromides và Iodides)
                    is_gop = ("và" in ten.lower() or "and" in ten.lower() or "hoac" in ten.lower() or "or" in ten.lower() or "/" in ten or "+" in ten)
                    if is_gop and len(matched_names) >= 1 and ten.lower() != matched_name.lower() and "dược điển" not in source_label.lower():
                        source_map[matched_name][source_label] = f"{gioi_han} (Ghi chú {source_label} gộp: {ten})"
                    else:
                        source_map[matched_name][source_label] = gioi_han
            else:
                unified_names.append(ten)
                source_map[ten] = {source_label: gioi_han}
    
    return unified_names, source_map

# =====================================================================
# UI HELPERS
# =====================================================================
def draw_progress(placeholder, percent, text_status):
    html = f"<div style='font-weight: 600; font-size: 14px; color: var(--apple-text-main); margin-bottom: 5px;'>Tiến trình: {percent}%</div><div style='font-size: 13px; color: var(--apple-text-muted); margin-bottom: 8px;'>{text_status}</div><div class='apple-progress-container'><div class='apple-progress-bar' style='width: {percent}%;'></div></div>"
    placeholder.markdown(html, unsafe_allow_html=True)

def draw_node(placeholder, status, title, desc=""):
    icon = "🔄" if status == "running" else "✅" if status == "success" else "❌" if status == "error" else "⏸️"
    html = f"<div class='node-card {status}'><div class='node-icon'>{icon}</div><div><div class='node-text-title'>{title}</div><div class='node-text-desc'>{desc}</div></div></div>"
    placeholder.markdown(html, unsafe_allow_html=True)

# =====================================================================
# PHASE 2: BẢNG SO SÁNH ĐA NGUỒN
# =====================================================================
def _find_matched_sop(criteria_name, sop_library):
    if not criteria_name or not sop_library:
        return None
    norm_name = _normalize_name(criteria_name)
    for sop_id, sop_data in sop_library.items():
        keywords = sop_data.get("tu_khoa_khoi_tao", [])
        for kw in keywords:
            norm_kw = _normalize_name(kw)
            if norm_kw and norm_kw in norm_name:
                return sop_id
    return None

def sync_comparison_editor_callback():
    editor_state = st.session_state.get("tcnl_comparison_editor", None)
    if not editor_state:
        return
        
    has_adds = len(editor_state.get("added_rows", [])) > 0
    has_deletes = len(editor_state.get("deleted_rows", [])) > 0
    
    if not has_adds and not has_deletes:
        # Only cell edits occurred, let st.data_editor handle it without resetting the source dataframe
        return
        
    df = st.session_state.tcnl_comparison_df.copy()
    source_labels = st.session_state.tcnl_source_labels
    
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
            "✅ Chốt": row.get("✅ Chốt") if row.get("✅ Chốt") is not None else True,
            "Giới hạn chốt": row.get("Giới hạn chốt") or ""
        }
        for src in source_labels:
            new_row[src] = row.get(src) or "Nhập thủ công"
            
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        
    # Recalculate STT column to keep sequence clean and contiguous
    for idx in range(len(df)):
        df.at[idx, "STT"] = idx + 1
        
    st.session_state.tcnl_comparison_df = df

def render_tcnl_phase_comparison():
    """Hiển thị bảng so sánh đa nguồn cho user tích chọn."""
    st.divider()
    
    # Khởi tạo subphase
    if "tcnl_chot_done" not in st.session_state:
        st.session_state.tcnl_chot_done = False
    if "tcnl_sop_done" not in st.session_state:
        st.session_state.tcnl_sop_done = False
        
    comparison_df = st.session_state.tcnl_comparison_df
    source_labels = st.session_state.tcnl_source_labels

    # Load SOP Library
    from ui_modules.ui_sop_library import load_sop_lib
    sop_library = load_sop_lib()

    if not st.session_state.tcnl_chot_done:
        st.markdown("<h3 style='color: #0071e3;'>📊 Bước 2a: Chốt Chỉ Tiêu & Giới Hạn</h3>", unsafe_allow_html=True)
        st.info("Tích chọn các chỉ tiêu cần thiết trong cột **✅ Chốt** và chỉnh sửa giới hạn nếu cần. Nhấn nút dưới bảng để chuyển sang bước chọn phương pháp mẫu. Bạn có thể bấm nút **➕ Add row** ở cuối bảng để thêm chỉ tiêu thủ công mới.")
        
        # Hiển thị bảng so sánh dạng editable (KHÔNG hiển thị drag-drop component ở đây)
        col_config = {}
        col_config["STT"] = st.column_config.NumberColumn("STT", width="small", min_value=1, format="%d", disabled=True)
        col_config["Tên Chỉ Tiêu"] = st.column_config.TextColumn("Tên Chỉ Tiêu", width="large")
        for src in source_labels:
            col_config[src] = st.column_config.TextColumn(src, width="medium")
        col_config["✅ Chốt"] = st.column_config.CheckboxColumn("✅ Chốt", default=True)
        col_config["Giới hạn chốt"] = st.column_config.TextColumn("Giới hạn chốt", width="large")
        
        edited_df = st.data_editor(
            comparison_df,
            column_config=col_config,
            disabled=source_labels,
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="tcnl_comparison_editor",
            on_change=sync_comparison_editor_callback
        )
                    
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        # Nút chuyển sang bước gán SOP mẫu
        if st.button("➡️ Xác Nhận Chốt & Chọn Phương Pháp Mẫu", type="primary", use_container_width=True):
            # Đồng bộ lại bảng gốc để lưu các chỉnh sửa của người dùng và làm sạch các ô trống
            df_to_save = edited_df.copy().reset_index(drop=True)
            for idx in range(len(df_to_save)):
                df_to_save.at[idx, "STT"] = idx + 1
                for src in source_labels:
                    if pd.isna(df_to_save.at[idx, src]) or df_to_save.at[idx, src] is None or df_to_save.at[idx, src] == "":
                        df_to_save.at[idx, src] = "Nhập thủ công"
            
            st.session_state.tcnl_comparison_df = df_to_save
            
            # Lọc những chỉ tiêu được chốt để chuyển sang sắp xếp
            checked_df = df_to_save[df_to_save["✅ Chốt"] == True].copy().reset_index(drop=True)
            if checked_df.empty:
                st.error("⚠️ Vui lòng tích chọn ít nhất 1 chỉ tiêu!")
                st.stop()
                
            # Đánh lại STT từ 1
            for idx in range(len(checked_df)):
                checked_df.at[idx, "STT"] = idx + 1
                
            st.session_state.tcnl_sorted_df = checked_df
            st.session_state.tcnl_chot_done = True
            st.session_state.tcnl_sop_done = False
            st.rerun()
            
    elif not st.session_state.tcnl_sop_done:
        st.markdown("<h3 style='color: #0071e3;'>📋 Bước 2ab: Chọn Phương Pháp Mẫu Từ Thư Viện SOP</h3>", unsafe_allow_html=True)
        st.info("Hệ thống sẽ đối chiếu và gợi ý sẵn phương pháp mẫu từ thư viện SOP cho các chỉ tiêu phù hợp. Bạn có thể thay đổi hoặc chọn [Tự động/Sinh bởi AI].")
        
        sorted_df = st.session_state.tcnl_sorted_df
        
        if "tcnl_selected_sops" not in st.session_state:
            st.session_state.tcnl_selected_sops = {}
            
        sop_options = ["(AI tự sinh phương pháp)"] + list(sop_library.keys())
        def format_sop_option(op):
            if op == "(AI tự sinh phương pháp)":
                return op
            return f"{sop_library[op].get('ten_hien_thi', op)} ({op})"
            
        # Hiển thị từng chỉ tiêu kèm chọn lựa SOP mẫu
        with st.container(border=True):
            for idx, row in sorted_df.iterrows():
                ten_ct = row["Tên Chỉ Tiêu"]
                # Gợi ý tự động nếu chưa có cấu hình trong session
                if ten_ct not in st.session_state.tcnl_selected_sops:
                    auto_matched = _find_matched_sop(ten_ct, sop_library)
                    st.session_state.tcnl_selected_sops[ten_ct] = auto_matched if auto_matched else "(AI tự sinh phương pháp)"
                    
                current_sel = st.session_state.tcnl_selected_sops[ten_ct]
                if current_sel not in sop_options:
                    current_sel = "(AI tự sinh phương pháp)"
                    
                st.session_state.tcnl_selected_sops[ten_ct] = st.selectbox(
                    f"Chỉ tiêu {idx+1}: {ten_ct}",
                    options=sop_options,
                    index=sop_options.index(current_sel),
                    format_func=format_sop_option,
                    key=f"tcnl_sel_sop_{idx}"
                )
        
        c_back, c_next = st.columns(2)
        with c_back:
            if st.button("⬅️ Quay lại Bước 2a: Chốt lại chỉ tiêu", use_container_width=True):
                st.session_state.tcnl_chot_done = False
                st.rerun()
        with c_next:
            if st.button("➡️ Xác Nhận Phương Pháp & Tiếp Tục Sắp Xếp", type="primary", use_container_width=True):
                # Đồng bộ widgets giá trị về session state chính thức
                for idx, row in sorted_df.iterrows():
                    ten_ct = row["Tên Chỉ Tiêu"]
                    st.session_state.tcnl_selected_sops[ten_ct] = st.session_state[f"tcnl_sel_sop_{idx}"]
                st.session_state.tcnl_sop_done = True
                st.rerun()
                
    else:
        st.markdown("<h3 style='color: #0071e3;'>🔄 Bước 2b: Sắp Xếp Thứ Tự Chỉ Tiêu Đã Chọn</h3>", unsafe_allow_html=True)
        st.info("Kéo thả danh sách dưới đây để thay đổi thứ tự hiển thị của chỉ tiêu khi xuất file Word.")
        
        sorted_df = st.session_state.tcnl_sorted_df
        criteria_names = sorted_df["Tên Chỉ Tiêu"].tolist()
        
        # Gọi component kéo thả
        new_order = _drag_drop_reorder(items=criteria_names, key="tcnl_dnd_reorder", default=criteria_names)
        
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
            st.session_state.tcnl_sorted_df = sorted_df
            st.rerun()
            
        # Hiển thị bảng xem trước thứ tự (read-only)
        st.markdown("##### 👁️ Bảng xem trước thứ tự chỉ tiêu:")
        preview_df = sorted_df[["STT", "Tên Chỉ Tiêu", "Giới hạn chốt"]].copy()
        st.dataframe(preview_df, use_container_width=True, hide_index=True)
        
        c_back, c_next = st.columns(2)
        with c_back:
            if st.button("⬅️ Quay lại Bước 2ab: Chọn lại phương pháp mẫu", use_container_width=True):
                st.session_state.tcnl_sop_done = False
                st.rerun()
                
        with c_next:
            if st.button("🚀 Bước 3: Chốt & Sinh Phương Phương Pháp Kiểm Nghiệm", type="primary", use_container_width=True):
                # Thu thập chỉ tiêu đã sắp xếp
                selected_criteria = []
                for _, row in sorted_df.iterrows():
                    selected_criteria.append({
                        "ten": row["Tên Chỉ Tiêu"],
                        "gioi_han": row["Giới hạn chốt"]
                    })
                
                st.session_state.tcnl_selected_criteria = selected_criteria
                
                # Gọi AI sinh phương pháp hoặc lấy trực tiếp mẫu từ thư viện
                ph_node = st.empty()
                
                # Tách riêng các chỉ tiêu dùng SOP mẫu và các chỉ tiêu cần AI sinh
                ai_criteria = []
                methods_result = {}
                
                for crit in selected_criteria:
                    ten_ct = crit["ten"]
                    sop_choice = st.session_state.get("tcnl_selected_sops", {}).get(ten_ct, "(AI tự sinh phương pháp)")
                    if sop_choice != "(AI tự sinh phương pháp)" and sop_choice in sop_library:
                        # Gán luôn nội dung từ thư viện
                        methods_result[ten_ct] = sop_library[sop_choice].get("noi_dung_sop", "")
                    else:
                        ai_criteria.append(crit)
                
                # Nếu có chỉ tiêu cần AI viết, tiến hành gọi AI sinh phương pháp
                if ai_criteria:
                    draw_node(ph_node, "running", "Node 3: Sinh Phương Pháp KN", f"AI đang viết SOP cho {len(ai_criteria)} chỉ tiêu...")
                    
                    try:
                        p3 = st.session_state.tcnl_p3
                        m3 = st.session_state.tcnl_m3
                        c_size = st.session_state.get("tcnl_chunk_size", 5)
                        m_workers = st.session_state.get("tcnl_max_workers", 3)
                        all_files = st.session_state.tcnl_all_files

                        from core.key_manager import get_active_keys
                        active_keys_3 = get_active_keys(p3, m3)
                        g_keys_3 = active_keys_3 if p3 == "Google API" else None
                        o_keys_3 = active_keys_3 if p3 == "OpenAI" else None

                        ai_methods = tcnl_generate_methods(
                            all_files, ai_criteria,
                            p3, m3, g_keys_3, o_keys_3,
                            chunk_size=c_size,
                            max_workers=m_workers,
                            bilingual=st.session_state.tcnl_bilingual_toggle,
                            files_data=st.session_state.get("tcnl_all_files_data")  # Tái dùng files đã encode
                        )
                        methods_result.update(ai_methods)
                        draw_node(ph_node, "success", "Node 3: Hoàn tất sinh phương pháp", f"Đã sinh xong phương pháp cho tất cả chỉ tiêu.")
                    except Exception as e:
                        draw_node(ph_node, "error", "Node 3: Lỗi", str(e))
                        st.error(f"❌ Lỗi sinh phương pháp: {traceback.format_exc()}")
                        st.stop()
                else:
                    draw_node(ph_node, "success", "Node 3: Hoàn tất", "Tất cả chỉ tiêu sử dụng SOP sẵn có từ thư viện.")
                
                st.session_state.tcnl_methods = methods_result
                st.session_state.tcnl_phase = 3
                time.sleep(1)
                st.rerun()

# =====================================================================
# PHASE 3: BẢN NHÁP + CHỈNH SỬA
# =====================================================================
def render_tcnl_phase_draft():
    """Hiển thị bản nháp để chỉnh sửa trước khi xuất Word."""
    st.divider()
    st.markdown("<h3 style='color: #0071e3;'>📝 Bản Nháp Tiêu Chuẩn Nguyên Liệu</h3>", unsafe_allow_html=True)
    st.info("Kiểm tra và chỉnh sửa nội dung bên dưới. Sau khi hoàn tất, nhấn nút cuối trang để xuất file Word.")
    
    # Thông tin hành chính tóm tắt (lấy động từ widgets)
    with st.container(border=True):
        st.markdown("##### ℹ️ Thông tin hành chính:")
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**Nguyên liệu:** {st.session_state.get('tcnl_ten_nl', '')}")
        c2.markdown(f"**NSX:** {st.session_state.get('tcnl_nha_sx', '')}")
        c3.markdown(f"**Tiêu chuẩn:** {st.session_state.get('tcnl_tieu_chuan', '')}")
    
    selected_criteria = st.session_state.tcnl_selected_criteria
    methods = st.session_state.tcnl_methods
    num_criteria = min(len(selected_criteria), 50)
    
    # Hiển thị tiêu đề và nút dịch song ngữ toàn bộ
    _bilingual_mode = st.session_state.get("tcnl_bilingual_toggle", True)
    _tcnl_btn_label = "🤖 Dịch song ngữ toàn bộ" if _bilingual_mode else "🤖 Dịch sang Tiếng Việt"
    _tcnl_btn_help = (
        "Dịch tự động tất cả các chỉ tiêu và SOP chưa có song ngữ sang tiếng Anh"
        if _bilingual_mode else
        "Dịch tự động tất cả nội dung sang Tiếng Việt thuần túy (không song ngữ)"
    )
    c_hdr_col, c_trans_col = st.columns([2, 1])
    with c_hdr_col:
        st.markdown("#### 📋 Danh sách chỉ tiêu (tối đa 50):")
    with c_trans_col:
        if st.button(_tcnl_btn_label, type="secondary", use_container_width=True, help=_tcnl_btn_help):
            p3 = st.session_state.get("tcnl_p3", "Google API")
            m3 = st.session_state.get("tcnl_m3", "gemini-1.5-flash")
            _do_bilingual = st.session_state.get("tcnl_bilingual_toggle", True)

            # Chọn hàm dịch phù hợp
            def _tcnl_translate(txt, ctx_type):
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
                if _do_bilingual:
                    temp_txt = txt
                    for unit in ["cfu/g", "mg/kg", "ug/g", "ug/mL", "dm2/g", "ml/g", "m3/g"]:
                        temp_txt = temp_txt.replace(unit, "")
                    return " / " not in temp_txt
                else:
                    import re as _re
                    latin_words = _re.findall(r'\b[A-Za-z]{3,}\b', txt)
                    return len(latin_words) > 2

            for idx in range(num_criteria):
                crit_item = selected_criteria[idx]
                crit_orig_name = crit_item["ten"]

                status_text.markdown(f"⏳ **Đang dịch chỉ tiêu {idx+1}/{num_criteria}:** `{crit_orig_name}`...")

                current_ten = st.session_state.get(f"tcnl_draft_ten_{idx}", "").strip()
                current_yc = st.session_state.get(f"tcnl_draft_yc_{idx}", "").strip()
                current_pp = st.session_state.get(f"tcnl_draft_pp_{idx}", "").strip()

                # 1. Dịch tên chỉ tiêu
                if needs_translation(current_ten):
                    new_ten = _tcnl_translate(current_ten, "criteria")
                    st.session_state[f"tcnl_draft_ten_{idx}"] = new_ten
                    crit_item["ten"] = new_ten
                    translated_count += 1

                # 2. Dịch yêu cầu / giới hạn
                if needs_translation(current_yc):
                    new_yc = _tcnl_translate(current_yc, "limit")
                    st.session_state[f"tcnl_draft_yc_{idx}"] = new_yc
                    crit_item["gioi_han"] = new_yc
                    translated_count += 1

                # 3. Dịch phương pháp kiểm nghiệm (SOP)
                if needs_translation(current_pp):
                    new_pp = _tcnl_translate(current_pp, "sop")
                    st.session_state[f"tcnl_draft_pp_{idx}"] = new_pp
                    methods[crit_orig_name] = new_pp
                    if current_ten != crit_orig_name:
                        methods[current_ten] = new_pp
                    translated_count += 1

                progress_bar.progress((idx + 1) / num_criteria)

            _success_msg = (
                f"✅ Đã dịch song ngữ thành công! Đã dịch {translated_count} phần."
                if _do_bilingual else
                f"✅ Đã dịch sang Tiếng Việt thành công! Đã dịch {translated_count} phần."
            )
            status_text.success(_success_msg)
            progress_bar.empty()
            time.sleep(1.5)
            st.rerun()
            
    for i in range(num_criteria):
        crit = selected_criteria[i]
        ten = crit["ten"]
        gioi_han = crit["gioi_han"]
        method_text = methods.get(ten, "Theo yêu cầu chuyên luận.")
        
        st.markdown(f"<div style='margin-top: 20px; margin-bottom: 5px; font-weight: 600; color: #1d1d1f;'>🔹 Chỉ tiêu {i+1}: {ten}</div>", unsafe_allow_html=True)
        
        col_a, col_b = st.columns([1, 2])
        with col_a:
            st.text_input(
                label=f"Tên chỉ tiêu {i+1}",
                value=ten,
                key=f"tcnl_draft_ten_{i}"
            )
            st.text_input(
                label=f"Yêu cầu / Giới hạn {i+1}",
                value=gioi_han,
                key=f"tcnl_draft_yc_{i}"
            )
        with col_b:
            st.text_area(
                label=f"Phương pháp kiểm nghiệm {i+1}",
                value=method_text,
                key=f"tcnl_draft_pp_{i}",
                height=150
            )
            # Thêm chọn lựa ghi đè nhanh bằng SOP mẫu ngay tại bản nháp
            from ui_modules.ui_sop_library import load_sop_lib
            sop_library = load_sop_lib()
            
            sop_options_edit = ["-- Chọn phương pháp mẫu để ghi đè --"] + list(sop_library.keys())
            def format_sop_option_edit(op):
                if op == "-- Chọn phương pháp mẫu để ghi đè --":
                    return op
                return f"{sop_library[op].get('ten_hien_thi', op)}"
                
            selected_override = st.selectbox(
                f"Ghi đè chỉ tiêu {i+1} bằng phương pháp mẫu",
                options=sop_options_edit,
                format_func=format_sop_option_edit,
                key=f"tcnl_override_sop_{i}",
                on_change=on_sop_change_tcnl,
                args=(i,)
            )
    
    st.divider()
    
    if st.button("🚀 Bước 4: Xác Nhận & Xuất File Word", type="primary", use_container_width=True):
        ph_node = st.empty()
        draw_node(ph_node, "running", "Node 4: Kết xuất Word", "Đang nạp dữ liệu vào template...")
        
        try:
            # Thu thập dữ liệu chỉnh sửa
            final_json = {}
            
            for i in range(50):
                idx = i + 1
                if i < num_criteria:
                    final_json[f"tcnl_ct_{idx}"] = st.session_state.get(f"tcnl_draft_ten_{i}", "")
                    final_json[f"tcnl_yc_{idx}"] = st.session_state.get(f"tcnl_draft_yc_{i}", "")
                    final_json[f"tcnl_pp_{idx}"] = st.session_state.get(f"tcnl_draft_pp_{i}", "")
                else:
                    final_json[f"tcnl_ct_{idx}"] = "XOA_HANG"
                    final_json[f"tcnl_yc_{idx}"] = "XOA_HANG"
                    final_json[f"tcnl_pp_{idx}"] = "XOA_HANG"
            
            # Thêm thông tin hành chính động từ widgets
            admin_data = {
                "ten_thuong_mai": st.session_state.get("tcnl_ten_nl", ""),
                "ten_nguyen_lieu": st.session_state.get("tcnl_monograph_name", st.session_state.get("tcnl_ten_nl", "")),
                "nha_san_xuat": st.session_state.get("tcnl_nha_sx", ""),
                "ma_hang": st.session_state.get("tcnl_ma_hang", ""),
                "tieu_chuan": st.session_state.get("tcnl_tieu_chuan", ""),
                "soan_thao": st.session_state.get("tcnl_soan_thao", ""),
                "kiem_tra": st.session_state.get("tcnl_kiem_tra", ""),
                "phe_duyet": st.session_state.get("tcnl_phe_duyet", ""),
                "ngay_soan_thao": st.session_state.get("tcnl_ngay_soan_thao", ""),
                "ngay_hieu_luc": st.session_state.get("tcnl_ngay_hieu_luc", ""),
                "han_ra_soat": st.session_state.get("tcnl_han_ra_soat", ""),
                "ngay_sua": st.session_state.get("tcnl_ngay_sua", ""),
                "noi_dung_sua_doi": st.session_state.get("tcnl_noi_dung_sua_doi", ""),
                "ly_do_sua_doi": st.session_state.get("tcnl_ly_do", ""),
                "lan_bh": st.session_state.get("tcnl_lan_bh", ""),
                "bao_quan": st.session_state.get("tcnl_bao_quan", ""),
            }
            st.session_state.tcnl_admin_data = admin_data
            final_json.update(admin_data)
            
            # Lưu JSON để debug
            st.session_state.tcnl_json_data = final_json.copy()
            
            # Tạo file Word
            template_file = st.session_state.tcnl_template_file
            final_io = node_4_generate_word(final_json, template_file, {}, bilingual=st.session_state.tcnl_bilingual_toggle)
            
            st.session_state.tcnl_final_io = final_io
            bfo = st.session_state.tcnl_admin_data.get("ma_hang", "TCNL")
            st.session_state.tcnl_file_name = f"TCNL_{bfo}.docx"
            
            draw_node(ph_node, "success", "Node 4: Hoàn tất kết xuất", "File TCNL đã sẵn sàng tải xuống!")
            st.session_state.tcnl_phase = 4
            st.rerun()
            
        except Exception as e:
            draw_node(ph_node, "error", "Node 4: Lỗi kết xuất", str(e))
            st.error(f"❌ Lỗi kết xuất Word: {traceback.format_exc()}")
            st.stop()

# =====================================================================
# PHASE 4: TẢI XUỐNG
# =====================================================================
def render_tcnl_phase_download():
    """Hiển thị nút tải xuống và khảo sát JSON."""
    st.divider()
    st.success("🎉 Tiêu Chuẩn Nguyên Liệu đã được tạo thành công!")
    
    tab_dl, tab_json = st.tabs(["📥 TẢI XUỐNG & LÀM MỚI", "👁️ XEM JSON DEBUG"])
    
    with tab_dl:
        col_dl, col_rs = st.columns(2)
        with col_dl:
            st.download_button(
                label="📥 Tải File TCNL (.docx)",
                data=st.session_state.tcnl_final_io,
                file_name=st.session_state.tcnl_file_name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
                use_container_width=True
            )
        with col_rs:
            if st.button("🔄 Làm mới để tạo TCNL khác", use_container_width=True):
                for key in list(st.session_state.keys()):
                    if key.startswith("tcnl_"):
                        del st.session_state[key]
                st.rerun()
    
    with tab_json:
        st.write(st.session_state.get("tcnl_json_data", {}))

# =====================================================================
# RENDER CHÍNH
# =====================================================================
def render_tcnl():
    st.markdown("<h2 style='text-align: center; color: #1d1d1f !important; font-weight: 600; letter-spacing: -0.02em; margin-bottom: 0;'>Tạo Tiêu Chuẩn Nguyên Liệu</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; margin-bottom: 30px;'>Hệ thống AI tự động quét, so sánh đa nguồn và sinh file TCNL hoàn chỉnh.</p>", unsafe_allow_html=True)

    # Khởi tạo session state
    if 'tcnl_phase' not in st.session_state:
        st.session_state.tcnl_phase = 0
    if 'tcnl_bilingual_toggle' not in st.session_state:
        st.session_state.tcnl_bilingual_toggle = True

    # ─── CẤU HÌNH AI ─────────────────────────────────────────────────
    model_config = load_model_config()
    providers = list(model_config.keys())

    # Bước 1 luôn hiển thị đầy đủ
    st.markdown("<h3 style='color: #0071e3;'>📋 Bước 1: Thông Tin & Tài Liệu Đầu Vào</h3>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("<h4 style='margin-top: 10px; color: #1d1d1f !important; font-weight: 600;'>Cấu hình AI</h4>", unsafe_allow_html=True)
        c1_2, c2_2, c3_2 = st.columns([1.5, 1, 1])
        c1_2.markdown("🌐 **AI Scanner:** Quét chỉ tiêu + giới hạn")
        p2 = c2_2.selectbox("Provider Scan", providers, key="tcnl_sel_p2", label_visibility="collapsed")
        m2_options = model_config.get(p2, ["(Chưa có mô hình)"])
        m2 = c3_2.selectbox("Model Scan", m2_options, key="tcnl_sel_m2", label_visibility="collapsed")

        c1_3, c2_3, c3_3 = st.columns([1.5, 1, 1])
        c1_3.markdown("🧩 **AI Method:** Sinh phương pháp KN")
        p3 = c2_3.selectbox("Provider Method", providers, key="tcnl_sel_p3", label_visibility="collapsed")
        m3_options = model_config.get(p3, ["(Chưa có mô hình)"])
        m3 = c3_3.selectbox("Model Method", m3_options, key="tcnl_sel_m3", label_visibility="collapsed")

        c1_4, c2_4, c3_4 = st.columns([1.5, 1, 1])
        c1_4.markdown("⚡ **Tốc độ:** Cấu hình song song")
        chunk_size = c2_4.number_input("Chỉ tiêu/lô", min_value=1, value=2, step=1, key="tcnl_chunk_size_input")
        max_workers = c3_4.number_input("Lô song song", min_value=1, value=5, step=1, key="tcnl_max_workers_input")

        c1_5, c2_5, c3_5 = st.columns([1.5, 1, 1])
        c1_5.markdown("🌐 **Hệ song ngữ:** Việt - Anh")
        bilingual = c2_5.toggle("Bật song ngữ", value=st.session_state.tcnl_bilingual_toggle, key="tcnl_bilingual_toggle", help="Mặc định bật hệ song ngữ Việt - Anh. Tắt đi sẽ chỉ xuất tiếng Việt.")

        # ─── THÔNG TIN HÀNH CHÍNH ────────────────────────────────────────
        st.markdown("<h4 style='margin-top: 25px; color: #1d1d1f !important; font-weight: 600;'>Thông tin Hành chính TCNL</h4>", unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            ten_nl = st.text_input("Tên nguyên liệu", placeholder="VD: Pyridoxin hydrochlorid", key="tcnl_ten_nl")
            nha_sx = st.text_input("Nhà sản xuất", placeholder="VD: Fisher Scientific", key="tcnl_nha_sx")
            ma_hang = st.text_input("Mã hàng", placeholder="VD: S01131", key="tcnl_ma_hang")
        with col2:
            tieu_chuan = st.text_input("Tiêu chuẩn áp dụng", placeholder="VD: BP 2025", key="tcnl_tieu_chuan")
            soan_thao = st.text_input("Người soạn thảo", key="tcnl_soan_thao")
            kiem_tra = st.text_input("Người kiểm tra", key="tcnl_kiem_tra")
        with col3:
            phe_duyet = st.text_input("Người phê duyệt", key="tcnl_phe_duyet")
            ngay_soan_thao = st.text_input("Ngày soạn thảo", key="tcnl_ngay_soan_thao")
            ngay_hieu_luc = st.text_input("Ngày hiệu lực", key="tcnl_ngay_hieu_luc")
        with col4:
            han_ra_soat = st.text_input("Hạn rà soát", key="tcnl_han_ra_soat")
            ngay_sua = st.text_input("Ngày sửa đổi", key="tcnl_ngay_sua")
            noi_dung_sua_doi = st.text_input("Nội dung sửa đổi", placeholder="Ban hành lần đầu", key="tcnl_noi_dung_sua_doi")
        
        c_ld, c_bh, c_bq = st.columns([2, 1, 2])
        with c_ld:
            ly_do_sua_doi = st.text_input("Lý do sửa đổi", placeholder="Ban hành lần đầu", key="tcnl_ly_do")
        with c_bh:
            lan_bh = st.text_input("Lần ban hành", placeholder="VD: 01", key="tcnl_lan_bh")
        with c_bq:
            bao_quan = st.text_input("Điều kiện bảo quản", placeholder="VD: Bảo quản trong bao bì kín, tránh ánh sáng.", key="tcnl_bao_quan")

        # ─── TÀI LIỆU ĐẦU VÀO ──────────────────────────────────────────
        st.markdown("<h4 style='margin-top: 25px; color: #1d1d1f !important; font-weight: 600;'>Tài liệu đầu vào (Tách biệt nguồn)</h4>", unsafe_allow_html=True)
        f1, f2, f3, f4, f5 = st.columns(5)
        with f1:
            st.info("📘 Dược điển")
            dd_files = st.file_uploader("DD", type=["pdf", "docx", "png", "jpg"], accept_multiple_files=True, key="tcnl_dd", label_visibility="collapsed")
        with f2:
            st.warning("📙 COA")
            coa_files = st.file_uploader("COA", type=["pdf", "docx", "png", "jpg"], accept_multiple_files=True, key="tcnl_coa", label_visibility="collapsed")
        with f3:
            st.success("📗 MOA")
            moa_files = st.file_uploader("MOA", type=["pdf", "docx", "png", "jpg"], accept_multiple_files=True, key="tcnl_moa", label_visibility="collapsed")
        with f4:
            st.markdown("<div style='background: #e8f1fd; padding: 10px; border-radius: 8px; font-size: 14px; text-align: center; font-weight: 500;'>📄 TCCS</div>", unsafe_allow_html=True)
            tccs_files = st.file_uploader("TCCS", type=["pdf", "docx", "png", "jpg"], accept_multiple_files=True, key="tcnl_tccs", label_visibility="collapsed")
        with f5:
            st.markdown("<div style='background: #e5ffe8; padding: 10px; border-radius: 8px; font-size: 14px; text-align: center; font-weight: 500;'>📝 Template Word</div>", unsafe_allow_html=True)
            template_file = st.file_uploader("Template", type=["docx"], key="tcnl_template", label_visibility="collapsed")

        st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)

        if st.button("🚀 Bước 1: Quét Chỉ Tiêu & Giới Hạn Từ Tất Cả Nguồn", type="primary", use_container_width=True):
            has_any = dd_files or coa_files or moa_files or tccs_files
            if not has_any:
                st.error("Vui lòng tải lên ít nhất 1 tài liệu!")
                st.stop()
            # Nếu không tải lên template mới, sử dụng template mặc định
            if not template_file:
                import io
                default_template_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Template_Form_TCNL.docx")
                if not os.path.exists(default_template_path):
                    default_template_path = "Template_Form_TCNL.docx"
                
                if os.path.exists(default_template_path):
                    with open(default_template_path, "rb") as f:
                        template_file = io.BytesIO(f.read())
                else:
                    st.error("Không tìm thấy file Template mặc định 'Template_Form_TCNL.docx'! Vui lòng tải lên file Template Word.")
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

            draw_progress(ph_progress, 10, "Đang chuẩn bị và mã hóa tài liệu...")
            

            try:
                # Quét song song từng rổ
                source_buckets = {}
                if dd_files: source_buckets["Dược điển"] = dd_files
                if coa_files: source_buckets["COA"] = coa_files
                if moa_files: source_buckets["MOA"] = moa_files
                if tccs_files: source_buckets["TCCS"] = tccs_files
                
                # ── ENCODE FILE MỘT LẦN DUY NHẤT ──────────────────────────────────
                from core.doc_processor import prepare_file_for_ai
                bucket_files_data = {}
                all_files_data = []
                for label, files in source_buckets.items():
                    fd = prepare_file_for_ai(files)
                    bucket_files_data[label] = fd
                    all_files_data.extend(fd)
                
                # Trích xuất tên chuyên luận từ Dược điển
                draw_progress(ph_progress, 10, "Đang trích xuất tên chuyên luận...")
                monograph_name = ""
                if dd_files and "Dược điển" in bucket_files_data:
                    draw_node(ph_node, "running", "Node 0: Trích xuất tên chuyên luận", "AI đang đọc tên nguyên liệu...")
                    try:
                        monograph_name = tcnl_extract_monograph_name(
                            None, p2, m2, None, None,
                            files_data=bucket_files_data["Dược điển"]
                        )
                    except Exception as e:
                        st.warning(f"⚠️ Lỗi trích xuất tên chuyên luận: {str(e)}")
                
                if not monograph_name:
                    monograph_name = ten_nl
                st.session_state.tcnl_monograph_name = monograph_name
                
                draw_progress(ph_progress, 20, "Đang quét chỉ tiêu từ các tài liệu...")
                draw_node(ph_node, "running", "Node 1: AI đang quét từng rổ tài liệu...", f"Đang xử lý {len(source_buckets)} nguồn song song.")
                
                source_results = {}
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(source_buckets)) as executor:
                    future_map = {}
                    for label in source_buckets.keys():
                        g_keys = test_keys if p2 == "Google API" else None
                        o_keys = test_keys if p2 == "OpenAI" else None
                        future = executor.submit(
                            tcnl_scan_criteria_and_limits,
                            None, label, p2, m2, g_keys, o_keys,
                            st.session_state.tcnl_bilingual_toggle,
                            bucket_files_data[label],
                            monograph_name=st.session_state.get("tcnl_monograph_name", ten_nl)
                        )
                        future_map[future] = label
                    
                    for future in concurrent.futures.as_completed(future_map):
                        label = future_map[future]
                        try:
                            source_results[label] = future.result()
                        except Exception as e:
                            source_results[label] = []
                            st.warning(f"⚠️ Lỗi quét nguồn '{label}': {str(e)}")
                
                draw_progress(ph_progress, 70, "Đang gộp và so sánh...")
                draw_node(ph_node, "success", "Node 1: Quét hoàn tất", f"Đã quét {sum(len(v) for v in source_results.values())} chỉ tiêu từ {len(source_results)} nguồn.")
                
                # Load master data to map names
                from ui_modules.ui_ho_so import _load_master
                master_data = _load_master()
                
                # Ánh xạ tên chỉ tiêu về master_data trước khi gộp dòng để tránh trùng lặp
                mapped_source_results = {}
                for label, items in source_results.items():
                    mapped_items = []
                    for item in items:
                        ten_raw = item.get("ten_chi_tieu", "").strip()
                        if ten_raw:
                            mapped_name = _match_name_to_master_tcnl(ten_raw, master_data)
                            new_name = mapped_name if mapped_name else ten_raw
                            mapped_items.append({
                                "ten_chi_tieu": new_name,
                                "gioi_han": item.get("gioi_han", "").strip()
                            })
                    mapped_source_results[label] = mapped_items

                # Gộp thành danh sách hợp nhất
                unified_names, source_map = _merge_criteria_union(mapped_source_results)
                source_labels = list(source_buckets.keys())
                
                # Tạo DataFrame so sánh
                rows = []
                for idx, name in enumerate(unified_names, 1):
                    row = {"STT": idx, "Tên Chỉ Tiêu": name}
                    for src in source_labels:
                        row[src] = source_map.get(name, {}).get(src, "")
                    # Mặc định giới hạn chốt lấy từ Dược điển
                    dd_val = source_map.get(name, {}).get("Dược điển", "")
                    if not dd_val:
                        # Fallback: lấy từ nguồn đầu tiên có dữ liệu
                        for src in source_labels:
                            v = source_map.get(name, {}).get(src, "")
                            if v:
                                dd_val = v
                                break
                    row["✅ Chốt"] = True
                    row["Giới hạn chốt"] = dd_val
                    rows.append(row)
                
                comparison_df = pd.DataFrame(rows)
                
                # Lưu vào session
                st.session_state.tcnl_comparison_df = comparison_df
                st.session_state.tcnl_source_labels = source_labels
                st.session_state.tcnl_p3 = p3
                st.session_state.tcnl_m3 = m3
                st.session_state.tcnl_chunk_size = chunk_size
                st.session_state.tcnl_max_workers = max_workers
                st.session_state.tcnl_template_file = template_file
                
                # Lưu files_data đã encode để tái dùng ở Node 3 (tránh encode lại)
                st.session_state.tcnl_all_files_data = all_files_data
                
                # Gom tất cả file gốc (giữ lại cho tương thích ngược nếu cần)
                all_files = []
                for files in source_buckets.values():
                    all_files.extend(files)
                st.session_state.tcnl_all_files = all_files
                
                st.session_state.tcnl_admin_data = {
                    "ten_thuong_mai": ten_nl,
                    "ten_nguyen_lieu": st.session_state.get("tcnl_monograph_name", ten_nl),
                    "nha_san_xuat": nha_sx,
                    "ma_hang": ma_hang,
                    "tieu_chuan": tieu_chuan,
                    "soan_thao": soan_thao,
                    "kiem_tra": kiem_tra,
                    "phe_duyet": phe_duyet,
                    "ngay_soan_thao": ngay_soan_thao,
                    "ngay_hieu_luc": ngay_hieu_luc,
                    "han_ra_soat": han_ra_soat,
                    "ngay_sua": ngay_sua,
                    "noi_dung_sua_doi": noi_dung_sua_doi,
                    "ly_do_sua_doi": ly_do_sua_doi,
                    "lan_bh": lan_bh,
                    "bao_quan": st.session_state.get("tcnl_bao_quan", ""),
                }
                
                st.session_state.tcnl_phase = 2
                st.session_state.tcnl_chot_done = False
                draw_progress(ph_progress, 100, "Hoàn tất! Chuyển sang bảng so sánh...")
                time.sleep(1)
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Lỗi Bước 1: {str(e)}\n\n{traceback.format_exc()}")
                st.stop()

    # RENDER CÁC BƯỚC TIẾP THEO (Nếu đã đạt phase tương ứng, không ẩn bước trước)
    if st.session_state.tcnl_phase >= 2:
        if "tcnl_comparison_df" not in st.session_state or st.session_state.tcnl_comparison_df is None:
            st.error("❌ Lỗi nội bộ: Không tìm thấy dữ liệu quét. Vui lòng chạy lại Bước 1.")
            st.session_state.tcnl_phase = 1
            st.rerun()
        elif st.session_state.tcnl_comparison_df.empty:
            st.warning("⚠️ AI không quét được chỉ tiêu nào từ tài liệu. Hãy kiểm tra lại:\n- API Key đã được kích hoạt chưa?\n- File tài liệu có chứa dữ liệu không?\n- Thử lại Bước 1 với tài liệu khác.")
            if st.button("🔄 Quay lại Bước 1", key="tcnl_back_to_step1_empty"):
                st.session_state.tcnl_phase = 1
                st.rerun()
        else:
            render_tcnl_phase_comparison()

    if st.session_state.tcnl_phase >= 3:
        render_tcnl_phase_draft()

    if st.session_state.tcnl_phase >= 4:
        render_tcnl_phase_download()