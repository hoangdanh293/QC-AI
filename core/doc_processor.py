import os
import json
import base64
import concurrent.futures
import re
from difflib import SequenceMatcher
from core.ai_handler import call_ai_engine, clean_translation_prefix

# =====================================================================
# MODULE-LEVEL CACHE — E1: Tránh đọc lại file JSON nặng nhiều lần
# trong mỗi lần xử lý hồ sơ (hàng chục worker thread gọi đồng thời)
# =====================================================================
_DYNAMIC_METHOD_CACHE = None   # Cache cho get_dynamic_method_instructions()
_PERSONAL_STYLE_CACHE = None   # Cache cho get_personal_style_instructions()
_STYLE_EXAMPLES_CACHE = {}     # Cache cho get_relevant_style_examples() — key=frozenset(criteria_ids)

def invalidate_instruction_cache():
    """
    Xóa toàn bộ module-level cache.
    GỌI HÀM NÀY khi người dùng lưu thay đổi vào:
      - criteria_master.json  (tab Chỉ tiêu)
      - personal_style.json   (tab Phong cách)
      - method_library.json   (tab Thư viện)
    Để đảm bảo lần xử lý tiếp theo dùng dữ liệu mới nhất.
    """
    global _DYNAMIC_METHOD_CACHE, _PERSONAL_STYLE_CACHE, _STYLE_EXAMPLES_CACHE
    _DYNAMIC_METHOD_CACHE = None
    _PERSONAL_STYLE_CACHE = None
    _STYLE_EXAMPLES_CACHE = {}
    print("[CACHE] Instruction cache invalidated.")


# =====================================================================
# HỆ THỐNG PHONG CÁCH CÁ NHÂN — AI HỌC TỪ HỒ SƠ MẪU THỰC TẾ
# =====================================================================

def get_personal_style_instructions():
    """
    Đọc personal_style.json để lấy phong cách viết hồ sơ cá nhân.
    Trả về chuỗi instructions để chèn vào System Prompt.
    Nếu chưa có dữ liệu phong cách, trả về chuỗi rỗng.
    [E1] Kết quả được cache module-level: chỉ đọc file 1 lần duy nhất mỗi phiên.
    """
    global _PERSONAL_STYLE_CACHE
    if _PERSONAL_STYLE_CACHE is not None:
        return _PERSONAL_STYLE_CACHE
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    style_path = os.path.join(base_dir, "personal_style.json")
    
    try:
        if not os.path.exists(style_path):
            return ""
        with open(style_path, 'r', encoding='utf-8') as f:
            style_data = json.load(f)
    except Exception:
        return ""
    
    phong_cach = style_data.get("phong_cach_rut_ra", {})
    mo_ta_chung = style_data.get("mo_ta_chung", "").strip()
    so_ho_so = style_data.get("so_ho_so_da_hoc", 0)
    tong_chi_tieu = style_data.get("tong_chi_tieu_hoc", 0)
    
    # Chỉ tạo instructions nếu đã có dữ liệu phong cách
    has_content = (
        mo_ta_chung or
        phong_cach.get("quy_tac_viet_lach") or
        phong_cach.get("cum_tu_uu_dung") or
        phong_cach.get("cau_truc_hplc") or
        phong_cach.get("cach_viet_gioi_han") or
        phong_cach.get("cach_bat_dau_sop")
    )
    
    if not has_content:
        return ""
    
    lines = []
    lines.append("══════════════════════════════════════════════════════")
    lines.append("⭐ PHONG CÁCH CÁ NHÂN BẮT BUỘC TUÂN THEO (PERSONAL STYLE PROFILE)")
    lines.append("══════════════════════════════════════════════════════")
    ho_so_info = f"{so_ho_so} hồ sơ"
    if tong_chi_tieu:
        ho_so_info += f" ({tong_chi_tieu} chỉ tiêu)"
    lines.append(f"Đây là phong cách làm hồ sơ kiểm nghiệm được rút ra từ {ho_so_info} mẫu thực tế.")
    lines.append("BẮT BUỘC áp dụng toàn bộ phong cách này khi tạo nội dung hồ sơ mới.")
    lines.append("")
    
    if mo_ta_chung:
        lines.append(f"📌 Mô tả tổng quát phong cách: {mo_ta_chung}")
        lines.append("")
    
    quy_tac = phong_cach.get("quy_tac_viet_lach", [])
    if quy_tac:
        lines.append("📋 Quy tắc viết lách bắt buộc:")
        for i, rule in enumerate(quy_tac, 1):
            if rule and rule.strip():
                lines.append(f"  {i}. {rule.strip()}")
        lines.append("")
    
    cum_tu = phong_cach.get("cum_tu_uu_dung", {})
    if cum_tu:
        lines.append("💬 Cụm từ ưa dùng (BẮT BUỘC dùng y nguyên):")
        for key, val in cum_tu.items():
            if val and str(val).strip():
                lines.append(f"  • [{key}]: {str(val).strip()}")
        lines.append("")
    
    cau_truc_hplc = phong_cach.get("cau_truc_hplc", "").strip()
    if cau_truc_hplc:
        lines.append("🔬 Cấu trúc trình bày HPLC đặc trưng:")
        lines.append(cau_truc_hplc)
        lines.append("")
    
    cau_truc_tlc = phong_cach.get("cau_truc_tlc", "").strip()
    if cau_truc_tlc:
        lines.append("🔬 Cấu trúc trình bày TLC đặc trưng:")
        lines.append(cau_truc_tlc)
        lines.append("")
    
    cau_truc_chuan_do = phong_cach.get("cau_truc_chuan_do", "").strip()
    if cau_truc_chuan_do:
        lines.append("🔬 Cấu trúc trình bày Chuẩn độ đặc trưng:")
        lines.append(cau_truc_chuan_do)
        lines.append("")
    
    cau_truc_dinh_tinh = phong_cach.get("cau_truc_dinh_tinh", "").strip()
    if cau_truc_dinh_tinh:
        lines.append("🔬 Cấu trúc trình bày Định tính đặc trưng:")
        lines.append(cau_truc_dinh_tinh)
        lines.append("")
    
    cach_viet_gioi_han = phong_cach.get("cach_viet_gioi_han", "").strip()
    if cach_viet_gioi_han:
        lines.append("📏 Cách viết giới hạn/yêu cầu:")
        lines.append(cach_viet_gioi_han)
        lines.append("")
    
    cach_bat_dau_sop = phong_cach.get("cach_bat_dau_sop", "").strip()
    if cach_bat_dau_sop:
        lines.append("✍️ Cách bắt đầu nội dung SOP:")
        lines.append(cach_bat_dau_sop)
        lines.append("")
    
    # === TRUONG MOI v2: quy_tac_boc_tach ===
    quy_tac_boc_tach = phong_cach.get("quy_tac_boc_tach", "").strip()
    if quy_tac_boc_tach:
        lines.append("\U0001f50d Quy tắc nhận diện và phân tách chỉ tiêu:")
        lines.append(quy_tac_boc_tach)
        lines.append("")
    
    # === TRUONG MOI v2: tu_dien_thuat_ngu ===
    tu_dien = phong_cach.get("tu_dien_thuat_ngu", {})
    if tu_dien:
        lines.append("\U0001f4d6 Từ điển thuật ngữ chuẩn (BẮT BUỘC dùng đúng thuật ngữ):")
        for term, definition in tu_dien.items():
            if term and definition and str(definition).strip():
                lines.append(f"  \u2022 \"{term}\": {str(definition).strip()}")
        lines.append("")
    
    # === TRUONG MOI v2: mau_ket_luan_chi_tieu ===
    mau_ket_luan = phong_cach.get("mau_ket_luan_chi_tieu", "").strip()
    if mau_ket_luan:
        lines.append("\U0001f3af Mẫu kết luận chuẩn của chỉ tiêu (Yêu cầu):")
        lines.append(mau_ket_luan)
        lines.append("")
    
    ghi_chu = phong_cach.get("ghi_chu_them", "").strip()
    if ghi_chu:
        lines.append("\U0001f4dd Ghi chú ưu tiên cao nhất (AI phải áp dụng trước):")
        lines.append(ghi_chu)
        lines.append("")
    
    result = "\n".join(lines)
    _PERSONAL_STYLE_CACHE = result  # [E1] Lưu vào cache
    return result


def match_criteria_id_by_name(name, criteria_master):
    if not name:
        return None
    name_clean = name.lower().strip()
    
    # 1. Khớp hoàn toàn với key hoặc ten_hien_thi trong criteria_master
    for k, v in criteria_master.items():
        ten_hien_thi = v.get("ten_hien_thi", "").lower().strip()
        if name_clean == ten_hien_thi or name_clean == k.lower():
            return k
            
    # 2. Khớp hoàn toàn với aliases thông dụng
    aliases_exact = {
        "định tính": "dinh_tinh",
        "identification": "dinh_tinh",
        "qualitative tests": "dinh_tinh",
        "định tính a": "dinh_tinh_a",
        "định tính b": "dinh_tinh_b",
        "định tính c": "dinh_tinh_c",
        "định tính d": "dinh_tinh_d",
        "định tính e": "dinh_tinh_e",
        "định tính f": "dinh_tinh_f",
        "cảm quan": "cam_quan",
        "appearance": "cam_quan",
        "description": "cam_quan",
        "tính chất": "cac_tinh_chat",
        "characters": "cac_tinh_chat",
        "mùi": "mui",
        "odor": "mui",
        "độ tan": "do_tan",
        "solubility": "do_tan",
        "độ trong và màu sắc dung dịch": "cam_quan_dung_dich",
        "độ trong và màu sắc của dung dịch": "cam_quan_dung_dich",
        "cảm quan dung dịch": "cam_quan_dung_dich",
        "appearance of solution": "cam_quan_dung_dich",
        "độ trong và mức độ nhuộm màu": "cam_quan_dung_dich",
        "độ trong": "cam_quan_dung_dich",
        "clarity of solution": "cam_quan_dung_dich",
        "ph": "ph",
        "ph dung dịch": "ph",
        "giới hạn acid - kiềm": "acid_kiem",
        "giới hạn acid-kiềm": "acid_kiem",
        "acid hoặc kiềm": "acid_kiem",
        "acid-kiềm": "acid_kiem",
        "acidity or alkalinity": "acid_kiem",
        "acidity/alkalinity": "acid_kiem",
        "kim loại nặng": "kim_loai_nang",
        "heavy metals": "kim_loai_nang",
        "sắt": "gioi_han_sat",
        "giới hạn sắt": "gioi_han_sat",
        "iron": "gioi_han_sat",
        "limit of iron": "gioi_han_sat",
        "amoni": "gioi_han_amoni",
        "giới hạn amoni": "gioi_han_amoni",
        "ammonium": "gioi_han_amoni",
        "nhôm": "gioi_han_nhom",
        "giới hạn nhôm": "gioi_han_nhom",
        "aluminium": "gioi_han_nhom",
        "arsenic": "gioi_han_arsenic",
        "giới hạn arsenic": "gioi_han_arsenic",
        "natri": "gioi_han_natri",
        "giới hạn natri": "gioi_han_natri",
        "sodium": "gioi_han_natri",
        "barium": "gioi_han_barium",
        "giới hạn barium": "gioi_han_barium",
        "kali": "gioi_han_Potassium",
        "potassium": "gioi_han_Potassium",
        "giới hạn kali": "gioi_han_Potassium",
        "giới hạn potassium": "gioi_han_Potassium",
        "magnesi và các kim loại kiềm thổ": "gioi_han_magnesium_va_kim_loai_kiem_tho",
        "magnesi và kim loại kiềm thổ": "gioi_han_magnesium_va_kim_loai_kiem_tho",
        "magnesium and alkaline-earth metals": "gioi_han_magnesium_va_kim_loai_kiem_tho",
        "clorid": "gioi_han_clorid",
        "clorua": "gioi_han_clorid",
        "chloride": "gioi_han_clorid",
        "chlorides": "gioi_han_clorid",
        "giới hạn clorid": "gioi_han_clorid",
        "giới hạn chloride": "gioi_han_clorid",
        "sulfat": "gioi_han_sulfat",
        "sulfate": "gioi_han_sulfat",
        "sulfates": "gioi_han_sulfat",
        "giới hạn sulfat": "gioi_han_sulfat",
        "giới hạn sulfate": "gioi_han_sulfat",
        "iodid": "gioi_han_iodide",
        "iodide": "gioi_han_iodide",
        "iodides": "gioi_han_iodide",
        "giới hạn iodid": "gioi_han_iodide",
        "giới hạn iodide": "gioi_han_iodide",
        "bromid": "bromide",
        "bromide": "bromide",
        "bromides": "bromide",
        "giới hạn bromid": "bromide",
        "giới hạn bromide": "bromide",
        "phosphate": "gioi_han_phosphate",
        "phosphates": "gioi_han_phosphate",
        "giới hạn phosphate": "gioi_han_phosphate",
        "nitrite": "gioi_han_nitrite",
        "nitrites": "gioi_han_nitrite",
        "giới hạn nitrite": "gioi_han_nitrite",
        "ferrocyanide": "ferrocyanide",
        "ferrocyanides": "ferrocyanide",
        "mất khối lượng do sấy": "mat_khoi_luong_do_say",
        "mất khối lượng do làm khô": "mat_khoi_luong_do_say",
        "loss on drying": "mat_khoi_luong_do_say",
        "lod": "mat_khoi_luong_do_say",
        "mất khối lượng do nung": "mat_khoi_luong_do_nung",
        "loss on ignition": "mat_khoi_luong_do_nung",
        "tro sulfat": "tro_sulfat",
        "tro sulfate": "tro_sulfat",
        "sulfated ash": "tro_sulfat",
        "sulphated ash": "tro_sulfat",
        "cắn sau nung": "can_sau_nung",
        "residue on ignition": "can_sau_nung",
        "nước": "ham_luong_nuoc",
        "hàm lượng nước": "ham_luong_nuoc",
        "water": "ham_luong_nuoc",
        "water content": "ham_luong_nuoc",
        "tạp chất liên quan": "tap_chat_lien_quan",
        "related substances": "tap_chat_lien_quan",
        "tạp chất": "tap_chat_lien_quan",
        "impurities": "tap_chat_lien_quan",
        "định lượng": "dinh_luong",
        "assay": "dinh_luong",
        "định lượng hplc": "dinh_luong_hplc",
        "định lượng bằng hplc": "dinh_luong_hplc",
        "assay by hplc": "dinh_luong_hplc",
        "góc quay cực riêng": "goc_quay_cuc_rieng",
        "specific optical rotation": "goc_quay_cuc_rieng",
        "specific rotation": "goc_quay_cuc_rieng",
        "góc quay cực": "goc_quay_cuc",
        "optical rotation": "goc_quay_cuc",
        "tỷ trọng": "ty_trong",
        "specific gravity": "ty_trong",
        "density": "ty_trong",
        "relative density": "ty_trong",
        "chỉ số acid": "chi_so_acid",
        "acid value": "chi_so_acid",
        "chỉ số iodine": "chi_so_iodine",
        "iodine value": "chi_so_iodine",
        "chỉ số peroxide": "chi_so_peroxide",
        "peroxide value": "chi_so_peroxide",
        "chỉ số hydroxyl": "chi_so_hydroxyl",
        "hydroxyl value": "chi_so_hydroxyl",
        "chỉ số xà phòng hóa": "chi_so_xa_phong_hoa",
        "saponification value": "chi_so_xa_phong_hoa",
        "chất không xà phòng hóa": "chat_khong_xa_phong_hoa",
        "unsaponifiable matter": "chat_khong_xa_phong_hoa",
        "chất không tan trong nước": "chat_khong_tan_trong_nuoc",
        "insoluble matter": "chat_khong_tan_trong_nuoc",
        "chất có thể chiết bằng ether": "chat_co_the_chiet_bang_ether",
        "ether extractable matter": "chat_co_the_chiet_bang_ether",
        "so sánh màu": "so_sanh_mau",
        "comparison of samples": "so_sanh_mau",
        "so màu": "so_mau",
        "dung dịch s": "dung_dich_S",
        "solution s": "dung_dich_S",
        "giới hạn nhiễm khuẩn": "gioi_han_nhiem_khuan",
        "nhiễm khuẩn": "gioi_han_nhiem_khuan",
        "microbial limit": "gioi_han_nhiem_khuan",
        "microbiological examination": "gioi_han_nhiem_khuan",
    }
    
    if name_clean in aliases_exact:
        return aliases_exact[name_clean]
        
    # 3. Thử khớp substring thông minh
    # Quy tắc: Tên ngắn (<= 4 ký tự) KHÔNG được dùng khớp substring để tránh sai lệch (VD: pH khớp sulphated ash)
    if len(name_clean) > 4:
        # Ưu tiên tìm xem có alias nào chứa trong name_clean hoặc ngược lại
        for alias_name, target_id in aliases_exact.items():
            if len(alias_name) > 4:
                # Nếu một trong hai chứa nhau hoàn toàn
                if alias_name in name_clean or name_clean in alias_name:
                    return target_id
                    
        # Khớp với master_data ten_hien_thi
        for k, v in criteria_master.items():
            ten_hien_thi = v.get("ten_hien_thi", "").lower().strip()
            if len(ten_hien_thi) > 4:
                if ten_hien_thi in name_clean or name_clean in ten_hien_thi:
                    return k

    # [A1] Bước 4: Fuzzy Matching — xử lý biến thể ngữ pháp nhỏ
    # (VD: "Tro Sulphate" vs "Tro sulfat", "Loss on Drying" vs "Mất khối lượng do làm khô")
    # Chỉ kích hoạt khi tên đủ dài (> 6 ký tự) để tránh false positive
    if len(name_clean) > 6:
        best_match_id = None
        best_score = 0.78  # Ngưỡng tối thiểu để chấp nhận khớp mờ
        # Kiểm tra với aliases
        for alias_name, target_id in aliases_exact.items():
            if len(alias_name) > 6:
                score = SequenceMatcher(None, name_clean, alias_name).ratio()
                if score > best_score:
                    best_score = score
                    best_match_id = target_id
        # Kiểm tra với ten_hien_thi trong criteria_master
        for k, v in criteria_master.items():
            ten_hien_thi = v.get("ten_hien_thi", "").lower().strip()
            if len(ten_hien_thi) > 6:
                score = SequenceMatcher(None, name_clean, ten_hien_thi).ratio()
                if score > best_score:
                    best_score = score
                    best_match_id = k
        if best_match_id:
            return best_match_id

    return None

def get_relevant_style_examples(target_criteria_ids=None, max_examples=5):
    """
    Lấy các hồ sơ mẫu từ style_examples_library.json để AI học phong cách.
    Ưu tiên các hồ sơ được đánh dấu là 'mau_vang' (Gold Standard).
    Trả về chuỗi instructions để chèn vào System Prompt.
    Giới hạn max_examples hồ sơ để không làm quá tải prompt.
    [E1] Kết quả được cache module-level theo (criteria_ids, max_examples): tránh đọc lại JSON 370KB
    nhiều lần khi hàng chục worker thread gọi đồng thời.
    """
    global _STYLE_EXAMPLES_CACHE
    # Tạo cache key từ criteria_ids và max_examples
    cache_key = (frozenset(target_criteria_ids) if target_criteria_ids else None, max_examples)
    if cache_key in _STYLE_EXAMPLES_CACHE:
        return _STYLE_EXAMPLES_CACHE[cache_key]

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lib_path = os.path.join(base_dir, "style_examples_library.json")
    criteria_path = os.path.join(base_dir, "criteria_master.json")
    
    criteria_master = {}
    try:
        if os.path.exists(criteria_path):
            with open(criteria_path, 'r', encoding='utf-8') as f:
                criteria_master = json.load(f)
    except Exception:
        pass
    
    try:
        if not os.path.exists(lib_path):
            _STYLE_EXAMPLES_CACHE[cache_key] = ""
            return ""
        with open(lib_path, 'r', encoding='utf-8') as f:
            lib_data = json.load(f)
    except Exception:
        _STYLE_EXAMPLES_CACHE[cache_key] = ""
        return ""
    
    # Lọc bỏ key _meta
    entries = {k: v for k, v in lib_data.items() if k != "_meta" and isinstance(v, dict)}
    if not entries:
        return ""
    
    # Sắp xếp: mau_vang trước, sau đó theo ngày tạo mới nhất
    sorted_entries = sorted(
        entries.items(),
        key=lambda x: (
            0 if x[1].get("la_mau_vang", False) else 1,
            x[1].get("ngay_tao", "")
        ),
        reverse=False
    )
    # Chỉ lấy tối đa max_examples hồ sơ để tránh tràn prompt
    selected = sorted_entries[:max_examples]
    
    if not selected:
        return ""
    
    lines = []
    lines.append("══════════════════════════════════════════════════════")
    lines.append("📚 HỒ SƠ MẪU VÀNG — HỌC PHONG CÁCH TỪ HỒ SƠ THỰC TẾ")
    lines.append("══════════════════════════════════════════════════════")
    lines.append("Dưới đây là các ví dụ chỉ tiêu thực tế được phê duyệt.")
    lines.append("BẮT BUỘC học và áp dụng phong cách trình bày y hệt các mẫu này.")
    lines.append("")
    
    for entry_id, entry_data in selected:
        ten_nl = entry_data.get("ten_nguyen_lieu", entry_id)
        loai_tl = entry_data.get("loai_tai_lieu", "")
        mo_ta = entry_data.get("mo_ta", "")
        la_mau_vang = entry_data.get("la_mau_vang", False)
        noi_dung = entry_data.get("noi_dung_tom_tat", "")
        vi_du_chi_tiet = entry_data.get("vi_du_chi_tiet", [])
        
        badge = "⭐ MẪU VÀNG" if la_mau_vang else "📄 Mẫu tham chiếu"
        lines.append(f"--- [{badge}] Hồ sơ: {ten_nl} ({loai_tl}) ---")
        if mo_ta:
            lines.append(f"Mô tả: {mo_ta}")
        
        # Tìm các ví dụ chỉ tiêu phù hợp
        matched_examples = []
        if vi_du_chi_tiet and isinstance(vi_du_chi_tiet, list):
            for vi_du in vi_du_chi_tiet:
                ten_ct = vi_du.get("ten_chi_tieu", "")
                noi_dung_mau = vi_du.get("noi_dung_mau", "")
                if not ten_ct or not noi_dung_mau:
                    continue
                    
                # Xác định ID của chỉ tiêu mẫu này
                ma_ct = vi_du.get("ma_chi_tieu")
                if not ma_ct:
                    ma_ct = match_criteria_id_by_name(ten_ct, criteria_master)
                    
                # Nếu có target_criteria_ids, kiểm tra xem có khớp không
                if target_criteria_ids:
                    is_match = False
                    if ma_ct in target_criteria_ids:
                        is_match = True
                    elif ma_ct and ma_ct.startswith("dinh_tinh") and "dinh_tinh" in target_criteria_ids:
                        is_match = True
                    elif "dinh_tinh" in target_criteria_ids and any(k in ten_ct.lower() for k in ["định tính", "identification"]):
                        is_match = True
                        
                    if is_match:
                        matched_examples.append(vi_du)
                else:
                    matched_examples.append(vi_du)
        
        # Nếu dùng lọc theo target_criteria_ids nhưng không khớp được chỉ tiêu nào từ hồ sơ này,
        # fallback lấy 4 chỉ tiêu đầu tiên để AI có định hướng chung về format
        if target_criteria_ids and not matched_examples:
            matched_examples = vi_du_chi_tiet[:3]  # Fallback: 3 chi tieu dau
            
        if matched_examples:
            lines.append("Các ví dụ chỉ tiêu thực tế liên quan (HỌC PHONG CÁCH):")
            for vi_du in matched_examples:
                ten_ct = vi_du.get("ten_chi_tieu", "")
                noi_dung_mau = vi_du.get("noi_dung_mau", "")
                lines.append(f"  🔸 Chỉ tiêu [{ten_ct}]:")
                # Giới hạn độ dài mỗi ví dụ để tránh quá tải
                # Giới hạn 3000 ký tự, cắt tại điểm xuống dòng hợp lý
                if len(noi_dung_mau) > 3000:
                    cut_pos = noi_dung_mau.rfind('\n', 0, 3000)
                    if cut_pos < 2000:
                        cut_pos = 3000
                    noi_dung_preview = noi_dung_mau[:cut_pos] + '\n    [...Đã cắt bớt...]'
                else:
                    noi_dung_preview = noi_dung_mau
                indented_content = "\n".join(f"    {line}" for line in noi_dung_preview.split("\n"))
                lines.append(indented_content)
                lines.append("")
        
        lines.append("")
    
    result_str = "\n".join(lines)
    _STYLE_EXAMPLES_CACHE[cache_key] = result_str  # [E1] Lưu vào cache
    return result_str


def get_dynamic_method_instructions():
    """
    Nạp dữ liệu từ criteria_master.json và method_library.json
    để huấn luyện AI về cấu trúc và thuộc tính cần bóc tách.
    [E1] Kết quả được cache module-level: chỉ đọc file 1 lần duy nhất mỗi phiên.
    """
    global _DYNAMIC_METHOD_CACHE
    if _DYNAMIC_METHOD_CACHE is not None:
        return _DYNAMIC_METHOD_CACHE
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    criteria_path = os.path.join(base_dir, "criteria_master.json")
    method_path = os.path.join(base_dir, "method_library.json")
    
    criteria_master = {}
    method_library = {}
    
    try:
        if os.path.exists(criteria_path):
            with open(criteria_path, 'r', encoding='utf-8') as f:
                criteria_master = json.load(f)
        if os.path.exists(method_path):
            with open(method_path, 'r', encoding='utf-8') as f:
                method_library = json.load(f)
    except Exception as e:
        print(f"Lỗi nạp criteria_master/method_library: {e}")
        
    dynamic_methods_desc = []
    for m_id, m_info in method_library.items():
        m_name = m_info.get("ten_phuong_phap", m_id)
        nhan_dien = ", ".join(m_info.get("tu_khoa_nhan_dien", []))
        loai_tru = ", ".join(m_info.get("tu_khoa_loai_tru", []))
        cau_truc = m_info.get("cau_truc_dau_ra", {})
        vi_du_mau = m_info.get("vi_du_mau", [])
        
        m_desc = f'🔹 Phương pháp: {m_name} (Mã ID: {m_id})\n'
        if nhan_dien:
            m_desc += f'  - Từ khóa nhận diện: {nhan_dien}\n'
        if loai_tru:
            m_desc += f'  - Từ khóa loại trừ: {loai_tru}\n'
        if cau_truc:
            m_desc += f'  - Cấu trúc/Thuộc tính (Tag) bắt buộc phải trích xuất:\n'
            for tag_k, tag_desc in cau_truc.items():
                m_desc += f'    * `{tag_k}`: {tag_desc}\n'
        if vi_du_mau and isinstance(vi_du_mau, list):
            m_desc += f'  - Các ví dụ mẫu Few-Shot (Học tập):\n'
            for idx, ex in enumerate(vi_du_mau):
                van_ban_goc = ex.get("van_ban_goc", "").strip()
                ket_qua_mong_muon = ex.get("ket_qua_mong_muon", "").strip()
                if van_ban_goc and ket_qua_mong_muon:
                    m_desc += f'    * Ví dụ {idx+1}:\n'
                    m_desc += f'      + Văn bản gốc: "{van_ban_goc}"\n'
                    m_desc += f'      + Kết quả mong muốn: "{ket_qua_mong_muon}"\n'
        dynamic_methods_desc.append(m_desc)
        
    dynamic_methods_str = "\n".join(dynamic_methods_desc)
    
    # Nạp các định nghĩa/khái niệm huấn luyện ngữ cảnh
    dynamic_definitions_desc = []
    
    # Sắp xếp các chỉ tiêu/định nghĩa theo cấp độ phân mức tăng dần
    sorted_criteria = sorted(
        criteria_master.items(),
        key=lambda item: int(item[1].get("cap_do_phan_muc", 2))
    )
    
    for c_id, c_info in sorted_criteria:
        loai = c_info.get("loai_khai_bao", "Chỉ tiêu")
        ten_hien_thi = c_info.get("ten_hien_thi", c_id)
        tu_dien = c_info.get("tu_dien_dich", "")
        quy_tac = c_info.get("quy_tac_ngu_canh", {})
        muc = c_info.get("cap_do_phan_muc", 2)
        vi_du_mau = c_info.get("vi_du_mau", [])
        
        c_desc = f'🔸 Khái niệm/Định nghĩa (Phân cấp Mức {muc} - {loai}): {ten_hien_thi} (Mã ID/Tag: {c_id})\n'
        if tu_dien:
            c_desc += f'  - Hướng dẫn dịch/từ điển: {tu_dien}\n'
        if quy_tac and isinstance(quy_tac, dict):
            c_desc += f'  - Quy tắc phân biệt ngữ cảnh:\n'
            for src_type, rule_text in quy_tac.items():
                if rule_text.strip():
                    c_desc += f'    * Khi bóc tách từ nguồn {src_type}: {rule_text.strip()}\n'
        if vi_du_mau and isinstance(vi_du_mau, list):
            c_desc += f'  - Các ví dụ mẫu Few-Shot (Học tập):\n'
            for idx, ex in enumerate(vi_du_mau):
                van_ban_goc = ex.get("van_ban_goc", "").strip()
                ket_qua_mong_muon = ex.get("ket_qua_mong_muon", "").strip()
                if van_ban_goc and ket_qua_mong_muon:
                    c_desc += f'    * Ví dụ {idx+1}:\n'
                    c_desc += f'      + Văn bản gốc: "{van_ban_goc}"\n'
                    c_desc += f'      + Kết quả mong muốn: "{ket_qua_mong_muon}"\n'
        dynamic_definitions_desc.append(c_desc)
            
    dynamic_definitions_str = "\n".join(dynamic_definitions_desc)
    
    training_instructions = f"""
══════════════════════════════════════════════════════
DỮ LIỆU HUẤN LUYỆN BỔ SUNG: THƯ VIỆN PHƯƠNG PHÁP KIỂM NGHIỆM ĐỘNG (METHOD LIBRARY)
══════════════════════════════════════════════════════
Dưới đây là các phương pháp kiểm nghiệm, thuộc tính (Tag) và ví dụ mẫu đi kèm đã được định cấu hình trong hệ thống.
Khi bóc tách một chỉ tiêu, hãy đối chiếu và BẮT BUỘC trích xuất đầy đủ thông tin của các thuộc tính (Tag) tương ứng để điền vào phần nội dung phương pháp (SOP/Cách làm).
Nếu chỉ tiêu hoặc phương pháp không nằm trong danh sách huấn luyện cụ thể, hãy tự động phân tích và dịch sát nghĩa chuyên ngành dược điển/kiểm nghiệm chất lượng (QA/QC):

{dynamic_methods_str}
"""

    if dynamic_definitions_str.strip():
        training_instructions += f"""
══════════════════════════════════════════════════════
DỮ LIỆU HUẤN LUYỆN BỔ SUNG: CÁC KHÁI NIỆM & ĐỊNH NGHĨA NGỮ CẢNH (CONCEPTUAL DICTIONARY)
══════════════════════════════════════════════════════
Hệ thống sử dụng cấu trúc phân tầng cấp độ (Mức 1 đến Mức 4) để định nghĩa và tổ chức các khái niệm:
- **Mức 1 (Nhóm lớn):** Các tiêu đề cha bao quát (Ví dụ: CHARACTERS, IDENTIFICATION). Nhóm lớn này bao gồm các chỉ tiêu con ở Mức 2.
- **Mức 2 (Chỉ tiêu con):** Các chỉ tiêu thực tế cần bóc tách (Ví dụ: tinh_chat, do_tan, dinh_tinh_a). Mức này nằm trong Mức 1.
- **Mức 3 (Khái niệm trong chỉ tiêu / Thuộc tính):** Các thông số, tag bóc tách của phương pháp (Ví dụ: cot_sac_ky_hplc, pha_dong, toc_do_dong_hplc). Mức này dùng để mô tả chi tiết cách tiến hành của Mức 2.
- **Mức 4 (Chi tiết cấu hình con nhỏ hơn):** Các tham số nhỏ/chi tiết cấu hình con của tag mức 3 (Ví dụ: chieu_dai_cot, kich_thuoc_hat). Mức này thuộc về cấu hình của Mức 3.

Hãy áp dụng nghiêm ngặt các khái niệm, từ khóa đồng nghĩa, cấu trúc phân cấp dưới đây khi phân tích và dịch thuật:

{dynamic_definitions_str}
"""
    _DYNAMIC_METHOD_CACHE = (training_instructions, criteria_master, method_library)  # [E1]
    return _DYNAMIC_METHOD_CACHE

def _normalize_name(name):
    if not name: return ""
    import unicodedata
    name = str(name).lower().strip()
    name = unicodedata.normalize('NFC', name)
    name = re.sub(r'\s+', ' ', name)
    return name

def _match_name_to_master(name, criteria_master):
    norm_name = _normalize_name(name)
    if not norm_name:
        return None
    # 1. Exact or normalized matching with ten_hien_thi or key
    for ma_id, config in criteria_master.items():
        ten_hien_thi = config.get("ten_hien_thi", "")
        if _normalize_name(ten_hien_thi) == norm_name or norm_name == _normalize_name(ma_id):
            return ma_id
        if "/" in ten_hien_thi:
            parts = [p.strip() for p in ten_hien_thi.split("/")]
            for p in parts:
                if _normalize_name(p) == norm_name:
                    return ma_id
    # 2. Substring matching
    ash_words = {"tro", "ash", "ignition", "nung", "can"}
    has_ash_scanned = any(w in norm_name for w in ash_words)
    for ma_id, config in criteria_master.items():
        ten_hien_thi = config.get("ten_hien_thi", "")
        norm_master = _normalize_name(ten_hien_thi)
        if norm_master in norm_name or norm_name in norm_master:
            has_ash_master = any(w in norm_master for w in ash_words)
            if has_ash_scanned != has_ash_master:
                continue
            return ma_id
    return None


def extract_sop_text_from_value(v):
    if not v:
        return ""
    
    # If it is a dictionary, process it
    if isinstance(v, dict):
        # Prefer "chot", then "sop_text", then source fields
        for key in ["chot", "sop_text", "duoc_dien", "tieu_chuan", "coa", "moa", "phu_luc", "noi_dung", "cach_tien_hanh"]:
            val = v.get(key, "")
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        # Fallback: if no priority key matches but there are other string values, find the longest string value
        str_vals = [val for val in v.values() if isinstance(val, str) and val.strip()]
        if str_vals:
            valid_vals = [val for val in str_vals if len(val) > 20]
            if valid_vals:
                return max(valid_vals, key=len).strip()
            return max(str_vals, key=len).strip()
        return str(v)
        
    # If it is a string, check if it is a JSON / Python dict representation
    if isinstance(v, str):
        v_stripped = v.strip()
        if (v_stripped.startswith("{") and v_stripped.endswith("}")) or (v_stripped.startswith("[") and v_stripped.endswith("]")):
            try:
                import json
                parsed = json.loads(v_stripped)
                if isinstance(parsed, dict):
                    return extract_sop_text_from_value(parsed)
            except Exception:
                pass
            
            try:
                import ast
                parsed = ast.literal_eval(v_stripped)
                if isinstance(parsed, dict):
                    return extract_sop_text_from_value(parsed)
            except Exception:
                pass
                
    return str(v).strip()


def safe_json_loads(json_str):
    if not json_str: return {}
    clean_str = json_str.replace("```json", "").replace("```", "").strip()
    
    # 1. Trích xuất ứng viên là Mảng hoặc Đối tượng để loại bỏ lời thoại rác của AI
    array_start = clean_str.find('[')
    array_end = clean_str.rfind(']')
    
    dict_start = clean_str.find('{')
    dict_end = clean_str.rfind('}')
    
    candidates = []
    
    # Ưu tiên Mảng nếu có dấu ngoặc vuông và dấu mở ngoặc vuông xuất hiện trước dấu mở ngoặc nhọn
    if array_start != -1 and array_end != -1 and array_end > array_start:
        if dict_start == -1 or array_start < dict_start:
            candidates.append(clean_str[array_start:array_end+1])
            
    # Ưu tiên Đối tượng nhọn
    if dict_start != -1 and dict_end != -1 and dict_end > dict_start:
        candidates.append(clean_str[dict_start:dict_end+1])
        
    # Thêm Mảng vào sau nếu chưa được thêm
    if array_start != -1 and array_end != -1 and array_end > array_start:
        cand = clean_str[array_start:array_end+1]
        if cand not in candidates:
            candidates.append(cand)
            
    candidates.append(clean_str)

    def try_parse(s):
        # 1. Standard json loads
        try:
            return json.loads(s, strict=False)
        except Exception:
            pass
            
        # 2. Fix unescaped backslashes
        try:
            fixed = re.sub(r'\\(?!["\\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', s)
            return json.loads(fixed, strict=False)
        except Exception:
            pass
            
        # 3. Python ast.literal_eval fallback (very safe and flexible)
        try:
            temp = re.sub(r'\bnull\b', 'None', s)
            temp = re.sub(r'\btrue\b', 'True', temp)
            temp = re.sub(r'\bfalse\b', 'False', temp)
            import ast
            return ast.literal_eval(temp)
        except Exception:
            pass
            
        return None

    # Thử parse các candidate theo thứ tự ưu tiên
    for cand in candidates:
        res = try_parse(cand)
        if res is not None:
            return res
            
    # Fallback cuối cùng: Sửa dấu phẩy bị thiếu giữa các dòng thuộc tính trong candidate nhọn
    target_candidate = clean_str[dict_start:dict_end+1] if (dict_start != -1 and dict_end != -1 and dict_end > dict_start) else clean_str
    fixed_candidate = re.sub(r'("|\d|true|false|null|\]|\})\s*\n\s*"', r'\1,\n"', target_candidate)
    res = try_parse(fixed_candidate)
    if res is not None:
        return res

    # Try simple key-value extraction using regex as a last resort
    try:
        extracted = {}
        candidate = target_candidate
        keys = re.findall(r'"([^"]+)"\s*:', candidate)
        for i, key in enumerate(keys):
            start_pos = candidate.find(f'"{key}"') + len(key) + 2
            next_pos = len(candidate)
            if i + 1 < len(keys):
                next_key = keys[i+1]
                next_pos = candidate.find(f'"{next_key}"', start_pos)
            
            val_segment = candidate[start_pos:next_pos].strip()
            if val_segment.endswith(","):
                val_segment = val_segment[:-1].strip()
            if val_segment.endswith("}"):
                if i == len(keys) - 1:
                    val_segment = val_segment[:-1].strip()
            
            if val_segment.startswith('"') and val_segment.endswith('"'):
                val_segment = val_segment[1:-1]
            elif val_segment.startswith("'") and val_segment.endswith("'"):
                val_segment = val_segment[1:-1]
                
            # Tránh làm hỏng cấu trúc lồng nhau bị cắt cụt bởi regex parser
            if val_segment.startswith("{") and not val_segment.endswith("}"):
                val_segment = ""
            elif val_segment.startswith("[") and not val_segment.endswith("]"):
                val_segment = ""
            elif val_segment in ["{", "[", '{"', "['"]:
                val_segment = ""
                
            extracted[key] = val_segment
        if extracted:
            return extracted
    except Exception:
        pass

    # Finally fallback to raising the error
    fixed_str = re.sub(r'\\(?!["\\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', clean_str)
    return json.loads(fixed_str, strict=False)

# =====================================================================
# HUẤN LUYỆN AI PHÂN BIỆT CÁC THÀNH PHẦN TÀI LIỆU DƯỢC ĐIỂN
# =====================================================================
DOCUMENT_COMPONENT_TRAINING = """
══════════════════════════════════════════════════════════════════
HUẤN LUYỆN: PHÂN BIỆT CÁC THÀNH PHẦN TRONG TÀI LIỆU DƯỢC ĐIỂN/TIÊU CHUẨN
══════════════════════════════════════════════════════════════════

Tài liệu Dược điển và Tiêu chuẩn nguyên liệu gồm 6 loại thành phần. Bạn PHẢI phân biệt chính xác từng loại:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[LOẠI 1] TÊN CHỈ TIÊU KIỂM NGHIỆM (Test Name / Criterion Name)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Đặc điểm nhận biết:
  - Là tiêu đề/đầu mục của từng phép thử, thường in đậm, gạch chân hoặc viết in hoa.
  - Thường đứng đầu đoạn, không có dấu chấm câu ở cuối.
  - Ví dụ ĐÚNG (là tên chỉ tiêu): "Appearance", "Identification", "Assay", "Loss on drying",
    "Heavy metals", "Related substances", "Acidity or alkalinity", "Water", "Sulfated ash",
    "Clarity and colour of solution", "Specific optical rotation", "pH", "Conductivity".
  - Ví dụ SAI (KHÔNG phải tên chỉ tiêu, không được dùng làm tên chỉ tiêu):
      ✗ "Standard solution" → đây là TÊN DUNG DỊCH
      ✗ "Mobile phase" → đây là TÊN DUNG DỊCH PHA ĐỘNG
      ✗ "Column" → đây là TÊN THIẾT BỊ
      ✗ "Procedure" → đây là TIÊU ĐỀ PHỤ của cách tiến hành
      ✗ "System suitability" → đây là TIÊU ĐỀ kiểm tra thích hợp hệ thống
      ✗ "Buffer solution" → đây là TÊN DUNG DỊCH
      ✗ "Limit" → đây là TỪ CHỈ GIỚI HẠN, không phải tên chỉ tiêu
      ✗ "Definition" → đây là MỤC ĐỊNH NGHĨA, không phải tên chỉ tiêu
      ✗ "Calculation" / "Tính toán" → đây là PHẦN TÍNH TOÁN, không phải tên chỉ tiêu

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[LOẠI 2] YÊU CẦU / GIỚI HẠN (Specification / Limit)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Đặc điểm nhận biết:
  - Là con số % hoặc mô tả đánh giá kết quả phải đạt.
  - Thường bắt đầu bằng: "Not more than", "Not less than", "Between X and Y", "Passes test",
    "Complies with", "Không quá", "Không ít hơn", "Trong khoảng", "Đạt yêu cầu".
  - Với Dược điển (USP/BP/EP): Giới hạn "Định lượng/Assay" thường nằm ở mục "Definition" đầu chuyên luận.
  - Phải giữ nguyên điều kiện đi kèm: "on dried basis", "on anhydrous basis", "on dried and solvent-free basis",
    "tính trên chế phẩm khan", "tính trên chế phẩm đã làm khô".
  - Ví dụ: "Not more than 0.5%", "98.0% to 101.0% (on dried basis)", "Passes test", 
    "White or almost white crystalline powder", "pH 5.0 to 7.0".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[LOẠI 3] ĐIỀU KIỆN SẮC KÝ (Chromatographic Conditions) — CHỈ cho HPLC/GC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Đặc điểm nhận biết:
  - Là thông số kỹ thuật của máy sắc ký: Cột (Column), Pha động (Mobile phase),
    Detector, Tốc độ dòng (Flow rate), Nhiệt độ (Temperature), Thể tích tiêm (Injection volume).
  - Thường nằm trong mục "Chromatographic conditions" hoặc "System" hoặc "Chromatography".
  - Ví dụ: "Column: C18, 150 mm × 4.6 mm, 5 µm", "Flow rate: 1.5 mL/min", "Detection: UV at 254 nm".
  - KHÔNG nhầm với "cách pha dung dịch" hay "cách tiến hành".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[LOẠI 4] CÁCH PHA DUNG DỊCH (Solution Preparation)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Đặc điểm nhận biết:
  - Hướng dẫn cân, hòa tan, pha loãng, lọc để tạo ra dung dịch dùng cho phép thử.
  - Thường bắt đầu bằng: "Dissolve", "Weigh", "Dilute", "Transfer", "Prepare", 
    "Hòa tan", "Cân", "Pha loãng", "Chuyển", "Chuẩn bị".
  - Gồm: Test solution (Dung dịch thử), Reference solution (Dung dịch chuẩn/đối chiếu),
    Buffer solution (Dung dịch đệm), Resolution solution (Dung dịch phân giải).
  - PHẢI trích xuất ĐẦY ĐỦ nồng độ, thể tích, dung môi pha của từng dung dịch.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[LOẠI 5] CÁCH TIẾN HÀNH / QUY TRÌNH (Procedure)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Đặc điểm nhận biết:
  - Các bước thao tác thực tế: đo, tiêm mẫu, chuẩn độ, so sánh, tính toán.
  - Thường bắt đầu bằng: "Inject", "Measure", "Titrate", "Observe", "Compare", "Calculate",
    "Tiêm", "Đo", "Chuẩn độ", "So sánh", "Quan sát", "Tính".
  - PHẢI trích xuất TOÀN BỘ nội dung, bao gồm cả mẫu thử và mẫu trắng.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[LOẠI 6] TÍNH THÍCH HỢP HỆ THỐNG (System Suitability) — CHỈ cho HPLC/GC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Đặc điểm nhận biết:
  - Yêu cầu kiểm tra trước khi phân tích: Resolution (Độ phân giải), RSD (Độ lệch chuẩn tương đối),
    Theoretical plates (Số đĩa lý thuyết), Tailing factor (Hệ số kéo đuôi).
  - Thường nằm trong mục "System suitability" hoặc "Tính thích hợp hệ thống".
  - PHẢI nêu đầy đủ dung dịch dùng để kiểm tra và ngưỡng yêu cầu cụ thể.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VÍ DỤ HUẤN LUYỆN THỰC TẾ (FEW-SHOT TRAINING EXAMPLES)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Hãy xem ví dụ mẫu dưới đây để hiểu cách bóc tách một chỉ tiêu từ tài liệu gốc sang cấu trúc JSON kết quả:

[VÍ DỤ 1: CHỈ TIÊU HPLC]
Tài liệu gốc đính kèm:
'''
ASSAY
- Procedure
  Buffer: 1.36 g/L of monobasic potassium phosphate. Adjust with phosphoric acid to a pH of 3.0.
  Mobile phase: Acetonitrile and Buffer (10:90)
  Standard solution: 0.1 mg/mL of USP Acetaminophen RS in Mobile phase
  Assay preparation: 0.1 mg/mL of Acetaminophen in Mobile phase from a portion of reconstituted Oral Suspension
  Chromatographic system
    Mode: LC
    Detector: UV 243 nm
    Column: 4.6-mm x 15-cm; 5-um packing L1
    Flow rate: 1.0 mL/min
    Injection volume: 10 uL
    System suitability
      Sample: Standard solution
      Suitability requirements
        Tailing factor: NMT 2.0
        Relative standard deviation: NMT 2.0%
  Analysis
    Samples: Standard solution and Assay preparation
    Calculate the percentage: Result = (ru / rs) * (Cs / Cu) * 100
  Acceptance criteria: 90.0%-110.0% of the labeled amount of acetaminophen (on dried basis)
'''

Kết quả bóc tách ĐÚNG:
{
  "ten": "Định lượng / Assay",
  "yeu_cau": "90,0% đến 110,0% tính trên chế phẩm khan / 90.0% to 110.0% of the labeled amount of acetaminophen (on dried basis)",
  "gioi_han": "90.0-110.0",
  "duoc_dien": "Theo chuyên luận Acetaminophen - USP\\n✓ Cột: L1 (15 cm x 4.6 mm, 5 µm)\\n✓ Detector: UV 243 nm\\n✓ Tốc độ dòng: 1.0 mL/phút\\n✓ Thể tích tiêm: 10 µL\\n\\nPha đệm: Hòa tan 1.36 g kali phosphat đơn bazơ trong 1 L nước. Điều chỉnh pH đến 3.0 bằng acid phosphoric.\\nPha động: Acetonitrile và Đệm (10:90).\\nDung dịch chuẩn: Pha dung dịch USP Acetaminophen RS nồng độ 0.1 mg/mL trong Pha động.\\nDung dịch thử: Pha dung dịch mẫu thử có nồng độ acetaminophen danh nghĩa khoảng 0.1 mg/mL từ một phần hỗn dịch uống đã hoàn nguyên trong Pha động.\\n\\nTính thích hợp hệ thống:\\n- Mẫu chạy: Dung dịch chuẩn.\\n- Yêu cầu: Hệ số đối xứng không quá 2.0; Độ lệch chuẩn tương đối (RSD) diện tích pic không quá 2.0%.\\n\\nCách tiến hành: Tiêm riêng biệt dung dịch chuẩn và dung dịch thử vào máy sắc ký, ghi lại sắc ký đồ và đo diện tích pic chính.\\n\\nCông thức tính toán:\\nHàm lượng (%) = (ru / rs) * (Cs / Cu) * 100\\nTrong đó:\\nru: diện tích pic của acetaminophen từ dung dịch thử.\\nrs: diện tích pic của acetaminophen từ dung dịch chuẩn.\\nCs: nồng độ chất chuẩn trong dung dịch chuẩn (mg/mL).\\nCu: nồng độ danh nghĩa của acetaminophen trong dung dịch thử (mg/mL)."
}

[VÍ DỤ 2: CHỈ TIÊU SẤY/LÀM KHÔ]
Tài liệu gốc đính kèm:
'''
LOSS ON DRYING <731>
Dry it in vacuum at 60° for 3 hours: it loses not more than 0.5% of its weight.
'''

Kết quả bóc tách ĐÚNG:
{
  "ten": "Mất khối lượng do làm khô / Loss on drying",
  "yeu_cau": "Không quá 0,5% / Not more than 0.5%",
  "gioi_han": "0.5",
  "duoc_dien": "Theo USP - 731\\nSấy chén cân đến khối lượng không đổi. Cân chính xác lượng chế phẩm vào chén cân. Sấy mẫu thử trong chân không ở nhiệt độ 60°C trong 3 giờ. Làm nguội trong bình hút ẩm và cân lại để xác định khối lượng mất đi."
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[QUY TẮC PHÂN TÁCH NHÓM CHỈ TIÊU LỚN] (Ví dụ: CHARACTERS / IDENTIFICATION)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Một số tiêu đề trong tài liệu Dược điển đại diện cho một nhóm lớn chứa nhiều chỉ tiêu con:
  - Tiêu đề "CHARACTERS" (hoặc "Tính chất") thường chứa cả mô tả ngoại quan ("Appearance" - bột màu trắng, v.v.) và độ tan ("Solubility" - tan trong nước, v.v.).
  - Tiêu đề "IDENTIFICATION" (hoặc "Định tính") thường chứa nhiều phép thử độc lập (như phép thử A, B, C, D hoặc IR, TLC, v.v.).

Cách xử lý bóc tách (BẮT BUỘC):
  1. PHÂN TÁCH CHÍNH XÁC: Cho dù các chỉ tiêu con này được viết dưới dạng tiêu đề nhỏ riêng biệt hay viết gộp chung thành một đoạn văn duy nhất không có tiêu đề, bạn PHẢI tự động nhận diện và phân tách chúng:
     + Phần mô tả màu sắc, trạng thái vật lý (bột, tinh thể, v.v.), hình dáng, tính hút ẩm (hygroscopic) phải được bóc tách và đưa vào chỉ tiêu "Tính chất / Cảm quan" (Appearance / Characters).
     + Phần mô tả khả năng hòa tan trong các dung môi (ví dụ: "freely soluble in water, sparingly soluble in ethanol...") phải được bóc tách và đưa vào chỉ tiêu "Độ tan" (Solubility).
  2. KHÔNG CHÉP GỘP: Tuyệt đối không được sao chép nguyên cả đoạn gộp chung vào cả hai chỉ tiêu. Mỗi chỉ tiêu chỉ được chứa đúng phần nội dung chuyên môn tương ứng của nó.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUY TẮC KHÔNG BỎ SÓT NỘI DUNG:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. Đọc TOÀN BỘ nội dung của từng chỉ tiêu từ đầu đến cuối: phần chuẩn bị, tiến hành, tính toán, chú thích.
  2. Nếu chỉ tiêu có nhiều phương pháp (Method 1, Method 2 / Method A, Method B): trích xuất ĐẦY ĐỦ TẤT CẢ.
  3. Nếu có bảng gradient dung môi: sao chép nguyên vẹn TOÀN BỘ bảng.
  4. Nếu có nhiều dung dịch chuẩn: ghi đầy đủ cách pha TẤT CẢ.
  5. KHÔNG tóm tắt, KHÔNG lược bỏ bất kỳ bước nào, KHÔNG bịa thêm nội dung.
  6. Nếu tài liệu không có nội dung cho chỉ tiêu đó: ghi "XOA_HANG", KHÔNG tự bịa ra.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[NGUYÊN TẮC CỐT LÕI: NEO HÀNG (ROW-ANCHORING) — ÁP DỤNG CHO MỌI LOẠI TÀI LIỆU]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Đây là nguyên tắc căn bản nhất, quan trọng hơn mọi quy tắc khác:

  ══ QUY TẮC NEO HÀNG: Tên chỉ tiêu và giới hạn PHẢI cùng thuộc về một chỉ tiêu duy nhất. ══
  KHÔNG ĐƯỢC lấy tên từ chỉ tiêu này rồi ghép với giới hạn từ chỉ tiêu khác.

Cách thực hiện BẮT BUỘC:
  Với MỌI loại tài liệu (bảng, danh sách, đoạn văn):
  - Xác định chỉ tiêu thứ N → đọc TÊN của chỉ tiêu N → đọc GIỚI HẠN của CHÍNH chỉ tiêu N đó.
  - Sau khi ghi xong chỉ tiêu N, mới chuyển sang chỉ tiêu N+1.
  - TUYỆT ĐỐI KHÔNG cắt ngang: lấy tên từ hàng 3 rồi ghép giới hạn từ hàng 5.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[NGUYÊN TẮC 2: PHÂN BIỆT TIÊU CHUẨN CHẤP NHẬN vs KẾT QUẢ KIỂM NGHIỆM]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tài liệu kiểm nghiệm (COA, phiếu kiểm) thường có 2 loại thông tin cần phân biệt:

  TIÊU CHUẨN/GIỚI HẠN CHẤP NHẬN (Specification/Acceptance Criterion):
  → Là điều kiện SẢN PHẨM PHẢI ĐÁP ỨNG. Đây là thông tin cần lấy vào trường "gioi_han".
  → Nhận biết: con số %, mg/kg, mô tả trạng thái vật lý, khoảng giá trị, cụm "not more than", "not less than", "passes", "between X and Y"...
  → Ví dụ: "Not less than 98.0% and not more than 100.5%", "Not more than 1.0%", "White crystalline powder", "Negative"

  KẾT QUẢ PHÂN TÍCH (Result of Analysis):
  → Là kết quả thực tế đo được. KHÔNG đưa vào trường "gioi_han".
  → Nhận biết: từ "Pass", "Fail", "Passes", "Complies", một con số đơn lẻ không có điều kiện (VD: "99.3%"), "Negative"
  → Nếu chỉ có kết quả mà không có tiêu chuẩn → gioi_han = "Đạt / Pass" (hoặc "Không đạt / Fail")

QUY TẮC:
  Luôn ưu tiên lấy TIÊU CHUẨN/GIỚI HẠN CHẤP NHẬN vào "gioi_han",
  không phải kết quả "Pass/Fail".
  Nếu cả hai đều có mặt (ví dụ COA 3 cột): lấy cột SPECIFICATIONS, bỏ qua cột RESULT.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[LỖI NGHIÊM TRỌNG 1 – PHÂN BIỆT "ĐỊNH LƯỢNG" và "HÀM LƯỢNG NƯỚC"]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ví dụ COA có cấu trúc 3 cột (TEST ITEMS | SPECIFICATIONS | RESULT):
  Assay    | Not less than 98.0% and not more than 100.5% | Pass
  Water    | Not more than 1.0%                           | Pass

✗ SAI – AI nhầm lấy giới hạn của Water (1.0%) gán vào Assay:
  → ten_chi_tieu: "Định lượng / Assay"   gioi_han: "Không quá 1,0%"    ← SAI HOÀN TOÀN

✓ ĐÚNG – Áp dụng nguyên tắc NEO HÀNG: lấy đúng giới hạn của từng chỉ tiêu:
  → ten_chi_tieu: "Định lượng / Assay"       gioi_han: "Không ít hơn 98,0% và không quá 100,5% / Not less than 98.0% and not more than 100.5%"
  → ten_chi_tieu: "Hàm lượng nước / Water"   gioi_han: "Không quá 1,0% / Not more than 1.0%"

DẤU HIỆU NHẬN BIẾT SAI:
  Nếu bạn gán giới hạn "Không quá X%" (với X < 50%) cho chỉ tiêu "Định lượng / Assay",
  đó là DẤU HIỆU chắc chắn bạn đang lấy nhầm giới hạn của chỉ tiêu khác (nước, tạp chất, v.v.).
  Giới hạn của Định lượng LUÔN là khoảng cao: 98%-102%, 99%-101%, 90%-110%, v.v.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[LỖI NGHIÊM TRỌNG 2 – TÊN SAI CHO KIM LOẠI NẶNG (Lead, Nickel, Arsenic, v.v.)]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Các chỉ tiêu kim loại nặng (heavy metals / elemental impurities) PHẢI được gọi đúng tên:

  Lead (Plumbum, Pb)     → Tên ĐÚNG: "Chì / Lead"         (KHÔNG phải "Chỉ số acid" hay "Acid value")
  Nickel (Ni)            → Tên ĐÚNG: "Nickel / Nickel"     (KHÔNG phải "Chỉ số acid" hay "Acid value")
  Arsenic (As)           → Tên ĐÚNG: "Asen / Arsenic"
  Mercury (Hg)           → Tên ĐÚNG: "Thủy ngân / Mercury"
  Cadmium (Cd)           → Tên ĐÚNG: "Cadmi / Cadmium"
  Heavy metals (chung)   → Tên ĐÚNG: "Kim loại nặng / Heavy metals"

QUY TẮC:
  Khi giới hạn có đơn vị mg/kg, ppm, ppb → đây là chỉ tiêu KIM LOẠI NẶNG, tên phải là tên nguyên tố đó.
  "Chỉ số acid / Acid value" chỉ tồn tại trong phân tích dầu/mỡ/sáp (đơn vị mg KOH/g), KHÔNG BAO GIỜ mg/kg.

  Ví dụ:
  COA ghi: "Lead: Not more than 1 mg/kg" → ten_chi_tieu: "Chì / Lead", gioi_han: "Không quá 1 mg/kg / Not more than 1 mg/kg"
  COA ghi: "Nickel: Not more than 1 mg/kg" → ten_chi_tieu: "Nickel / Nickel", gioi_han: "Không quá 1 mg/kg / Not more than 1 mg/kg"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[C4] PHÂN BIỆT CÁC CẶP CHỈ TIÊU CÓ TÊN TƯƠNG TỰ — KHÔNG ĐƯỢC NHẦM LẪN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ Cảnh báo: Các cặp chỉ tiêu dưới đây có tên gần giống nhau nhưng phương pháp và giới hạn HOÀN TOÀN KHÁC NHAU.
TUYỆT ĐỐI KHÔNG lấy nội dung / giới hạn của chỉ tiêu này vào trường của chỉ tiêu kia.

CẶP 1: "Mất khối lượng do sấy" vs "Hàm lượng nước"
  ✓ "Mất khối lượng do sấy" (Loss on drying / LOD):
     - Phương pháp: Sấy mẫu ở 100–105°C đến khối lượng không đổi. Đo giảm khối lượng (%).
     - Giới hạn: Thường "Không quá X%" (VD: NMT 0.5%, NMT 1.0%).
     - Đơn vị giới hạn: % (phần trăm).
  ✓ "Hàm lượng nước" (Water content / Karl Fischer):
     - Phương pháp: Chuẩn độ Karl Fischer, đo lượng nước H₂O thực sự. Theo USP <921> hoặc EP 2.5.12.
     - Giới hạn: Thường "Không quá X%" (VD: NMT 0.1%, NMT 5.0%).
     - Đơn vị giới hạn: % (phần trăm) — NHƯNG phương pháp hoàn toàn khác LOD.

CẶP 2: "Tro sulfat" vs "Cắn sau nung"
  ✓ "Tro sulfat" (Sulfated ash / Sulphated ash):
     - Phương pháp: Nung mẫu + thêm H₂SO4 loãng → nung tiếp đến khối lượng không đổi. Đo cắn vô cơ.
     - Nhận biết trong tài liệu: "Sulfated ash", "Sulphated ash", "add sulphuric acid"
  ✓ "Cắn sau nung" (Residue on ignition / Ash):
     - Phương pháp: Nung trực tiếp ở 600°C KHÔNG thêm acid. Đo cắn còn lại.
     - Nhận biết trong tài liệu: "Residue on ignition", "ignite to constant weight", "600°C"

CẶP 3: "Định lượng" (Assay) vs "Tạp chất liên quan" (Related substances)
  ✓ "Định lượng" (Assay): Giới hạn LUÔN cao, khoảng 90–102% (VD: 98.0%–102.0%).
  ✓ "Tạp chất liên quan" (Related substances / Impurities): Giới hạn LUÔN nhỏ, dạng "không quá X%" (VD: NMT 0.1%, NMT 0.5%).
  ⚠️ Nếu thấy giới hạn "không quá X%" với X < 10 → ĐÓ LÀ TẠP CHẤT, không phải Định lượng.

CẶP 4: "pH" vs "Giới hạn acid - kiềm"
  ✓ "pH": Giới hạn là một con số hoặc khoảng số (VD: pH 5.0–7.0, pH 6.0–8.0). Phương pháp dùng pH kế.
  ✓ "Giới hạn acid - kiềm" (Acidity or alkalinity): Phương pháp so màu chỉ thị, không dùng pH kế trực tiếp.

CẶP 5: "Tính chất / Cảm quan" vs "Độ trong và màu sắc dung dịch"
  ✓ "Tính chất / Cảm quan" (Appearance/Characters): Mô tả dạng rắn — màu sắc, dạng bột/tinh thể.
  ✓ "Độ trong và màu sắc" (Appearance of solution): Mô tả dung dịch SAU KHI hòa tan mẫu vào dung môi.
"""

SOP_FORMATTING_GUIDELINES = """
PHONG CÁCH TRÌNH BÀY & DIỄN ĐẠT PHƯƠNG PHÁP (SOP) BẮT BUỘC CHO MỌI CHỈ TIÊU:

════════════════════════════════════════════════════════
PHẦN 1: QUY TẮC CHUNG BẮT BUỘC
════════════════════════════════════════════════════════

1. ĐỊNH DẠNG CHUNG:
   - Dịch chi tiết 100% sang Tiếng Việt, sử dụng thuật ngữ chuyên ngành Dược. Dùng dấu xuống dòng (\\n) để phân tách rõ các mục.
   - Bắt đầu phương pháp bằng nguồn tham chiếu cụ thể. Ví dụ: "Theo chuyên luận [Tên nguyên liệu] - [Dược điển]" (ví dụ: "Theo chuyên luận Dexamethasone sodium phosphate - USP") hoặc "Theo [Dược điển] - [Chuyên luận chung]" (ví dụ: "Theo USP - 791").
   - Tập trung HOÀN TOÀN vào nội dung cách làm, các bước chuẩn bị (hòa tan, pha loãng, đo đạc, chuẩn độ...) và điều kiện thiết bị.
   - TUYỆT ĐỐI KHÔNG vẽ bảng ghi nhận kết quả trống, không chèn các dòng check-box hay phần chừa trống "Kết quả" vì các phần này đã được định nghĩa sẵn trong file template mẫu.
   - VỀ CÔNG THỨC TÍNH TOÁN: Chỉ nêu công thức và giải thích ký hiệu nếu tài liệu nguồn có đề cập cụ thể. Tuyệt đối không tự ý chèn/bịa ra công thức.

2. QUY ĐỊNH VỀ DANH PHÁP HÓA CHẤT (BẮT BUỘC):
   - BẮT BUỘC GIỮ NGUYÊN TÊN GỐC (không dịch ra tiếng Việt) đối với các dung dịch thuốc thử, hóa chất và dung dịch chuẩn độ. Ví dụ:
     + ĐÚNG: "Acetonitrile", "Methanol", "Phosphoric acid", "Sodium hydroxide 0.1 N", "USP Acetaminophen RS"
     + SAI: "Acetonitril", "Methanol" (được dùng), "Acid phosphoric" → Dùng tên IUPAC/USP gốc
   - Tên dung dịch pha chế có thể dịch: "Dung dịch đệm", "Pha động", "Dung dịch thử", "Dung dịch chuẩn", "Dung dịch phân giải".
   - Các tên công cụ/thiết bị dùng tên Việt hoá chuẩn: "Cột sắc ký C18", "Đầu dò UV", "Máy đo pH", "Bình định mức".

3. QUY ĐỊNH VỀ PHA CHẾ THUỐC THỬ / DUNG DỊCH:
   - Chỉ dịch chi tiết hướng dẫn pha chế các dung dịch hoặc thuốc thử nếu phần nội dung này được đề cập trong tài liệu gốc (Dược điển, TCNL, COA, MOA).
   - TUYỆT ĐỐI KHÔNG tự ý sáng tạo hay tra cứu tài liệu ngoài để thêm vào phương pháp pha chế nếu tài liệu gốc không đề cập.

4. KẾT LUẬN CHỈ TIÊU (BẮT BUỘC):
   - Ở cuối mỗi chỉ tiêu, luôn phải trình bày rõ ràng giới hạn và yêu cầu chấp nhận của chuyên luận bằng câu hoàn chỉnh.
   - Ví dụ: "Yêu cầu: Không quá 0,5% / Requirement: Not more than 0.5%."
   - Ví dụ: "Yêu cầu: Hàm lượng từ 98,0% đến 102,0% tính trên chế phẩm khan."

5. TUYỆT ĐỐI NGHIÊM CẤM TỰ BỊA ĐẶT CÁCH LÀM (BIỆN PHÁP CHỐNG HALLUCINATION):
   - Nếu tài liệu đính kèm chỉ liệt kê tên chỉ tiêu và giới hạn/yêu cầu mà KHÔNG CÓ bất kỳ quy trình thử nghiệm hay cách làm chi tiết nào (ví dụ: các chỉ tiêu lấy từ COA hoặc các phép thử phụ chỉ ghi giới hạn), bạn TUYỆT ĐỐI KHÔNG ĐƯỢC tự ý suy diễn, giả lập hay viết ra quy trình thực hiện, không được tự chèn các thông số thiết bị (bước sóng, nhiệt độ, chương trình dung môi, cột, đầu dò, buồng tiêm...), cách cân mẫu hay cách pha chế dung dịch. Trong trường hợp này, phần cách tiến hành chỉ được viết ngắn gọn: "Cách tiến hành: Thực hiện theo chuyên luận của Dược điển hiện hành hoặc theo tiêu chuẩn của nhà sản xuất (hoặc Theo chuyên luận của nhà sản xuất)."
   - Bất kỳ hành vi viết chi tiết các thông số kỹ thuật (HPLC, GC, chuẩn độ...) không có trong tài liệu nguồn cho các chỉ tiêu này đều bị coi là lỗi nghiêm trọng (bịa đặt thông tin).
   - NGOẠI LỆ: Nếu tài liệu gốc có câu mô tả ngắn gọn hoặc câu tham chiếu phương pháp chung (ví dụ: "B. Infrared absorption spectrophotometry (2.2.24). Comparison: folic acid CRS." hoặc "C. Thin-layer chromatography (2.2.27)..."), bạn PHẢI trích xuất và dịch trung thực câu ngắn gọn này (ví dụ: "Phương pháp: Quang phổ hấp thụ hồng ngoại (2.2.24). So sánh với phổ của folic acid CRS."). TUYỆT ĐỐI không dùng câu boilerplate chung chung cho các phép thử có mô tả/tham chiếu ngắn này, để tránh làm mất từ khóa phương pháp quan trọng.
   - CẢNH BÁO ĐẶC BIỆT CHỐNG BỊA ĐẶT (ĐỐI VỚI CHẤT FOLIC ACID):
     + Chỉ tiêu "Acid D-folic / D-folic acid" và "Acetone" trong COA chỉ có giới hạn mà hoàn toàn KHÔNG CÓ quy trình thử chi tiết nào trong tài liệu Dược điển EP/COA. Bạn TUYỆT ĐỐI KHÔNG được tự bịa ra quy trình HPLC hay GC hay bất kỳ thông số thiết bị nào cho Acid D-folic hay Acetone. Tuyệt đối không nhầm lẫn "Acid D-folic" với "Tạp chất D (Impurity D / pteroic acid)" trong EP để lấy quy trình HPLC của Tạp chất D gán cho Acid D-folic. Phần cách tiến hành chỉ được viết: "Cách tiến hành: Theo tiêu chuẩn của nhà sản xuất." hoặc "Procedure: According to the manufacturer's specifications."

════════════════════════════════════════════════════════
PHẦN 2: CẤU TRÚC THEO TỪNG LOẠI PHƯƠNG PHÁP
════════════════════════════════════════════════════════

5. PHƯƠNG PHÁP SẮC KÝ LỎNG HIỆU NĂNG CAO (HPLC):
   Cấu trúc bắt buộc chia thành 2 phần A và B rõ ràng:

   **A. Điều kiện sắc ký** — Liệt kê dạng danh sách dùng dấu `✓`:
      ✓ Cột sắc ký: [Tên cột, kích thước, hạt nhồi. Ví dụ: C18 (150 mm × 4,6 mm; 5 µm)]
      ✓ Đầu dò (Detector): [Tên và bước sóng. Ví dụ: UV 254 nm]
      ✓ Tốc độ dòng: [Ví dụ: 1,5 ml/phút]
      ✓ Nhiệt độ cột: [Ví dụ: 30°C] (nếu có quy định)
      ✓ Nhiệt độ buồng tiêm mẫu: [Ví dụ: 25°C] (nếu có quy định)
      ✓ Thể tích tiêm: [Ví dụ: 10 µL hoặc 20 µL]
      ✓ Thời gian chạy sắc ký: [Ví dụ: 30 phút] (nếu tài liệu có quy định)

   **B. Nội dung chi tiết phương pháp** — Trình bày tuần tự theo thứ tự sau:
      * **Thành phần pha động**: Trình bày cụ thể cách pha chế các dung dịch cấu thành nên pha động, bao gồm: Dung dịch đệm, Dung môi pha động, Dung dịch A, và Dung dịch B (nếu chạy gradient).
      * **Chương trình chạy máy (Gradient)** (nếu sử dụng chế độ Gradient): BẮT BUỘC trình bày dưới dạng bảng theo định dạng sau để đảm bảo tính trực quan:
        | Thời gian (phút) | % Dung dịch A | % Dung dịch B |
        | 0 | XX | XX |
        | ... | ... | ... |
      * **Chuẩn bị mẫu**: Dịch chi tiết quy trình pha chế các loại dung dịch: Dung dịch chuẩn, Dung dịch thử, Dung dịch đối chiếu, Dung dịch phân giải (nếu có). Bao gồm đầy đủ: khối lượng cân (mg/g), thể tích định mức (ml), nồng độ, dung môi pha.
      * **Thông số đánh giá chuyên môn (System Suitability)**: Trình bày các yêu cầu về Thời gian lưu tương đối, Độ phân giải (Resolution ≥ X), Hệ số đối xứng (Tailing factor ≤ X), và Độ lệch chuẩn tương đối (RSD ≤ X%) của diện tích pic tiêm lặp lại.
      * **Tiêu chuẩn chấp nhận**: Trình bày đầy đủ giới hạn và yêu cầu đánh giá kết quả của phương pháp HPLC.

6. PHƯƠNG PHÁP SẮC KÝ LỚP MỎNG (SKLM / TLC):
   Cấu trúc bắt buộc chia thành 2 phần A và B rõ ràng:

   **A. Điều kiện sắc ký** — Liệt kê đầy đủ các thông số kỹ thuật:
      ✓ Bản mỏng: [Loại bản mỏng sử dụng, ví dụ: Silica gel GF254]
      ✓ Pha động: [Hệ dung môi khai triển, ví dụ: Ethyl acetate : Methanol : Ammonia (7:2:1)]
      ✓ Chiều dài triển khai: [Khoảng cách dung môi di chuyển trên bản mỏng, ví dụ: 10 cm]
      ✓ Thể tích chấm: [Lượng mẫu cần chấm lên bản mỏng, ví dụ: 5 µL]
      ✓ Dung dịch hiện màu: [Thuốc thử hiện màu (nếu có yêu cầu) kết hợp với các thao tác ở bước sấy và soi bản mỏng, ví dụ: Dung dịch vanilin - acid sulfuric]
      ✓ Điều kiện sấy khô bản mỏng: [Nhiệt độ và thời gian sấy] (nếu có quy định)

   **B. Nội dung chi tiết phương pháp**:
      * **Chuẩn bị mẫu**: Nêu rõ quy trình pha chế các loại dung dịch: Dung dịch thử, Dung dịch chuẩn, và Dung dịch đối chiếu. Bao gồm đầy đủ: khối lượng cân, thể tích pha, nồng độ, dung môi pha.
      * **Thông số đánh giá chuyên môn**: Trình bày các tiêu chí về Tính thích hợp hệ thống (nếu chuyên luận có yêu cầu).
      * **Tiêu chuẩn chấp nhận**: Ghi rõ Yêu cầu của chỉ tiêu để đánh giá kết quả (ví dụ: so sánh vết, vị trí, màu sắc, kích thước vết...).

7. PHƯƠNG PHÁP CHUẨN ĐỘ THỂ TÍCH (VOLUMETRIC TITRATION):
   * **Thuốc thử & Chỉ thị**: Nêu rõ dung dịch chuẩn độ (ví dụ: Dung dịch natri hydroxyd 0,1 N) và chỉ thị màu.
   * **Chuẩn bị mẫu**: Cân chính xác khoảng ... g chế phẩm, hòa tan trong ... ml dung môi thích hợp.
   * **Cách tiến hành**: Mô tả chi tiết quá trình chuẩn độ đến khi đổi màu chỉ thị.
   * **Hệ số đương lượng**: "1 ml dung dịch [Tên dung dịch chuẩn độ] [Nồng độ] tương đương với ... mg [Tên hoạt chất]".
   * **Tính toán**: Chỉ nêu công thức nếu tài liệu nguồn có đề cập cụ thể.

8. PHƯƠNG PHÁP QUANG PHỔ HẤP THỤ (UV-VIS / IR):
   * **Thiết bị & Điều kiện**: Loại máy, bước sóng (nm) hoặc dải sóng (cm⁻¹), loại cuvet (ví dụ: cuvet thạch anh 1 cm).
   * **Cách pha mẫu**: Cách chuẩn bị dung dịch thử, dung dịch chuẩn.
   * **Cách tiến hành**: Đo Absorbance hoặc quét phổ, đo mẫu trắng.
   * **Tính toán / Đánh giá**: Chỉ nêu công thức nếu tài liệu có đề cập. So sánh phổ của mẫu thử phải phù hợp với phổ chất chuẩn.

9. PHƯƠNG PHÁP MẤT KHỐI LƯỢNG DO LÀM KHÔ / TRO SULFAT / CẮN SAU NUNG:
   * **Dụng cụ & Điều kiện**: Loại chén cân/chén nung, nhiệt độ sấy/nung (°C), thời gian.
   * **Cách tiến hành**: Sấy/nung chén đến khối lượng không đổi trước khi cân mẫu. Cân khoảng ... g mẫu. Sấy/nung ở nhiệt độ quy định đến khối lượng không đổi. Làm nguội trong bình hút ẩm và cân lại.
   * **ĐỐI VỚI TRO SULFAT (SULFATED ASH)**: Khi tài liệu đính kèm chỉ ghi ngắn gọn (ví dụ: tham chiếu 2.4.14 hoặc chỉ ghi khối lượng mẫu), bạn PHẢI bổ sung mô tả quy trình nung chuẩn của Dược điển: nung chén nung trước, cân lượng mẫu quy định, làm ẩm bằng sulfuric acid (acid sulfuric), đun nóng nhẹ cho đến khi bay hết khói trắng, sau đó nung (ignite) ở nhiệt độ khoảng 600°C ± 50°C đến khối lượng không đổi.
   * **Tính toán**: Chỉ nêu công thức nếu tài liệu có đề cập.

10. PHƯƠNG PHÁP GIỚI HẠN TẠP CHẤT HÓA HỌC (Clorid, Sulfat, Kim loại nặng, Amoni, Sắt, Bari...):
    * **Cách pha**: Ống thử (hòa tan mẫu thử) và Ống chuẩn (dung dịch chuẩn chứa ion giới hạn).
    * **Cách tiến hành**: Thêm thuốc thử tạo đục/tạo màu. Để yên thời gian quy định.
    * **Đánh giá**: So sánh độ đục/màu sắc. Ống thử không được đậm hơn ống chuẩn.

11. PHƯƠNG PHÁP XÁC ĐỊNH NƯỚC (Karl Fischer):
    * Theo [Dược điển] - [Chuyên luận chung] (Ví dụ: Theo USP - 921, phương pháp 1)
    * Dùng khoảng [Khối lượng] mẫu thử.
    * Hệ số T của thuốc thử Karl Fischer T = [Hướng dẫn xác định]
    * Công thức tính toán: Chỉ nêu nếu tài liệu có đề cập.

12. PHƯƠNG PHÁP ĐO PH / GÓC QUAY CỰC RIÊNG / NHIỆT ĐỘ NÓNG CHẢY:
    * Trình bày các bước chuẩn bị thiết bị, nhiệt độ đo, nồng độ dung dịch thử và thao tác đo đạc chi tiết. KHÔNG để khoảng chấm chấm trống điền kết quả đo.

13. CÁC PHƯƠNG PHÁP ĐƠN GIẢN (Cảm quan, Tính chất, Độ tan, Thử giới hạn cơ bản):
    * Trình bày các bước kiểm tra bằng mắt thường hoặc mô tả tính chất vật lý/độ tan tìm được từ tài liệu. KHÔNG ghi chữ "Kết quả" ở cuối.

14. PHƯƠNG PHÁP ĐỊNH TÍNH (IDENTIFICATION):
    * Bắt buộc trình bày chi tiết và bóc tách cách tiến hành cho TỪNG phép thử định tính riêng lẻ (ví dụ: Định tính A, Định tính B, Định tính C, Định tính D...) dưới dạng danh sách dùng dấu gạch đầu dòng `-`.
    * TUYỆT ĐỐI KHÔNG được copy-paste hoặc gán quy trình cảm quan của "Tính chất" (như quan sát bột màu gì...) cho các phép Định tính A, B, C, D, trừ khi đó là định tính cảm quan thật sự.
    * ĐỐI VỚI PHÉP ĐỊNH TÍNH THAM CHIẾU CHÉO (Ví dụ: "Specific optical rotation (see Tests)" hoặc "Water (see Tests)"): Bạn PHẢI đi tìm phép thử tương ứng trong phần TESTS của tài liệu đính kèm (ví dụ: tìm phép thử "Specific optical rotation" hoặc "Water" trong phần TESTS) để lấy đúng quy trình chuẩn bị mẫu và đo đạc chi tiết (ví dụ: hòa tan trong dung dịch NaOH, đo góc quay cực, hoặc đo Karl Fischer) để đưa vào cách tiến hành của phép định tính tương ứng đó.
    * ĐỐI VỚI CÁC PHÉP ĐỊNH TÍNH KHÁC: Nếu chỉ có mô tả ngắn như đo phổ hồng ngoại so với CRS hoặc chạy TLC, hãy viết ngắn gọn và trung thực theo mô tả đó (ví dụ: "So sánh phổ hấp thụ hồng ngoại của mẫu thử với phổ hấp thụ hồng ngoại của folic acid CRS"), TUYỆT ĐỐI KHÔNG tự bịa quy trình chi tiết (như HPLC hay cân đong hóa chất phức tạp) nếu tài liệu không có.
    * TUYỆT ĐỐI KHÔNG ghi chung chung "Theo yêu cầu chuyên luận" trừ khi tài liệu hoàn toàn không mô tả cách làm.
"""

# ─── ANTI-BILINGUAL OVERRIDE (dùng khi bilingual=False) ────────────────────
_ANTI_BILINGUAL_HEADER = """
╔══════════════════════════════════════════════════════════════════════════════╗
║  ⚠️  CHỈ THỊ NGÔN NGỮ ĐẦU RA – ƯU TIÊN TỐI CAO – KHÔNG ĐƯỢC BỎ QUA      ║
║                                                                              ║
║  TUYỆT ĐỐI CHỈ DỊCH VÀ VIẾT BẰNG TIẾNG VIỆT THUẦN TÚY.                   ║
║  KHÔNG sử dụng bất kỳ hình thức song ngữ "Việt / Anh" nào.                 ║
║  KHÔNG viết thêm bản dịch tiếng Anh kèm theo.                               ║
║  BỎ QUA mọi lệnh "dịch song ngữ", "Việt-Anh", "[English]" ở bên dưới.     ║
║                                                                              ║
║  Ngoại lệ duy nhất được phép giữ nguyên tiếng Anh:                          ║
║    • Ký hiệu hóa học (NaCl, H2SO4, C6H12O6...)                              ║
║    • Công thức toán học và đơn vị đo (mg/mL, %, rpm...)                     ║
║    • Tên riêng thiết bị / phương pháp viết tắt (HPLC, UV-Vis, ATR...)       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

def prepare_file_for_ai(uploaded_files):
    """
    Chuyển đổi file tải lên từ Streamlit sang định dạng Base64.
    Định dạng này giúp gửi trực tiếp nguyên bản file (PDF/Word/Ảnh) qua API của AI (Gemini 1.5 / GPT-4o)
    mà không cần dùng bất kỳ thư viện đọc chữ nào.
    """
    if not uploaded_files: return []
    if not isinstance(uploaded_files, list): uploaded_files = [uploaded_files]
    
    file_list = []
    for file in uploaded_files:
        try:
            file.seek(0)
            file_bytes = file.read()
            if not file_bytes: continue
            
            # Xác định Mime Type để AI biết đường xử lý
            fname = file.name.lower()
            if fname.endswith('.pdf'): mime_type = "application/pdf"
            elif fname.endswith('.docx'):
                import docx
                import io
                try:
                    doc = docx.Document(io.BytesIO(file_bytes))
                    
                    # Khai báo bộ đếm số đầu mục (numbering)
                    num_counters = {}
                    
                    def get_p_numbering_pref(p):
                        p_pr = p._p.pPr
                        if p_pr is None or p_pr.numPr is None:
                            return ""
                        num_pr = p_pr.numPr
                        num_id = num_pr.numId.val if num_pr.numId is not None else None
                        ilvl = num_pr.ilvl.val if num_pr.ilvl is not None else 0
                        if num_id is None:
                            return ""
                        
                        style_lower = p.style.name.lower() if p.style else ""
                        if "bullet" in style_lower:
                            return "• "
                            
                        if num_id not in num_counters:
                            num_counters[num_id] = [0] * 9
                        num_counters[num_id][ilvl] += 1
                        for i in range(ilvl + 1, 9):
                            num_counters[num_id][i] = 0
                            
                        if ilvl == 0:
                            return f"{num_counters[num_id][0]}. "
                        elif ilvl == 1:
                            return f"{num_counters[num_id][0]}.{num_counters[num_id][1]}. "
                        else:
                            return f"{num_counters[num_id][ilvl]}. "

                    def escape_katex(text):
                        if not text:
                            return ""
                        s = text
                        # Escape special LaTeX characters
                        s = s.replace('\\', '\\backslash ')
                        s = s.replace('%', '\\%')
                        s = s.replace('_', '\\_')
                        s = s.replace('{', '\\{')
                        s = s.replace('}', '\\}')
                        s = s.replace('&', '\\&')
                        s = s.replace('#', '\\#')
                        s = s.replace('$', '\\$')
                        
                        has_alpha = any(c.isalpha() for c in s)
                        has_non_ascii = any(ord(c) > 127 for c in s)
                        
                        if has_alpha:
                            # If it's a single ASCII alphabetical character (e.g. 'M', 'x'), keep it as-is (math italic)
                            is_single_ascii_alpha = len(s) == 1 and s.isalpha() and ord(s) <= 127
                            if not is_single_ascii_alpha or has_non_ascii:
                                return f"\\text{{{s}}}"
                        return s

                    def parse_omml_to_latex(elem):
                        """Đổi cấu trúc Office Math XML sang định dạng LaTeX math."""
                        tag = elem.tag.split('}')[-1]
                        if tag == 'oMath' or tag == 'oMathPara':
                            return "".join(parse_omml_to_latex(child) for child in elem)
                        elif tag == 'r':
                            t_elems = elem.findall('.//{http://schemas.openxmlformats.org/officeDocument/2006/math}t')
                            run_text = "".join(t.text for t in t_elems if t.text)
                            return escape_katex(run_text)
                        elif tag == 'f':
                            num_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}num')
                            den_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}den')
                            num_str = parse_omml_to_latex(num_elem) if num_elem is not None else ""
                            den_str = parse_omml_to_latex(den_elem) if den_elem is not None else ""
                            return f"\\frac{{{num_str}}}{{{den_str}}}"
                        elif tag in ['num', 'den', 'e', 'sub', 'sup']:
                            return "".join(parse_omml_to_latex(child) for child in elem)
                        elif tag == 'sSub':
                            e_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}e')
                            sub_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}sub')
                            e_str = parse_omml_to_latex(e_elem) if e_elem is not None else ""
                            sub_str = parse_omml_to_latex(sub_elem) if sub_elem is not None else ""
                            return f"{e_str}_{{{sub_str}}}"
                        elif tag == 'sSup':
                            e_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}e')
                            sup_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}sup')
                            e_str = parse_omml_to_latex(e_elem) if e_elem is not None else ""
                            sup_str = parse_omml_to_latex(sup_elem) if sup_elem is not None else ""
                            return f"{e_str}^{{{sup_str}}}"
                        elif tag == 'sSubSup':
                            e_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}e')
                            sub_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}sub')
                            sup_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}sup')
                            e_str = parse_omml_to_latex(e_elem) if e_elem is not None else ""
                            sub_str = parse_omml_to_latex(sub_elem) if sub_elem is not None else ""
                            sup_str = parse_omml_to_latex(sup_elem) if sup_elem is not None else ""
                            return f"{e_str}_{{{sub_str}}}^{{{sup_str}}}"
                        elif tag == 'd':
                            d_pr = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}dPr')
                            beg = "("
                            end = ")"
                            if d_pr is not None:
                                beg_el = d_pr.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}begChr')
                                if beg_el is not None:
                                    for k, v in beg_el.attrib.items():
                                        if k.endswith('val') or k == 'val':
                                            beg = v
                                            break
                                end_el = d_pr.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}endChr')
                                if end_el is not None:
                                    for k, v in end_el.attrib.items():
                                        if k.endswith('val') or k == 'val':
                                            end = v
                                            break
                            e_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}e')
                            e_str = parse_omml_to_latex(e_elem) if e_elem is not None else ""
                            beg_escaped = beg
                            if beg in ['{', '}']:
                                beg_escaped = '\\' + beg
                            end_escaped = end
                            if end in ['{', '}']:
                                end_escaped = '\\' + end
                            return f"{beg_escaped}{e_str}{end_escaped}"
                        elif tag == 'limLow':
                            e_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}e')
                            lim_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}lim')
                            e_str = parse_omml_to_latex(e_elem) if e_elem is not None else ""
                            lim_str = parse_omml_to_latex(lim_elem) if lim_elem is not None else ""
                            return f"{{{e_str}}}_{{{lim_str}}}"
                        elif tag == 'limUpp':
                            e_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}e')
                            lim_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}lim')
                            e_str = parse_omml_to_latex(e_elem) if e_elem is not None else ""
                            lim_str = parse_omml_to_latex(lim_elem) if lim_elem is not None else ""
                            return f"{{{e_str}}}^{{{lim_str}}}"
                        elif tag == 'rad':
                            deg_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}deg')
                            e_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}e')
                            deg_str = parse_omml_to_latex(deg_elem) if deg_elem is not None else ""
                            e_str = parse_omml_to_latex(e_elem) if e_elem is not None else ""
                            if deg_str:
                                return f"\\sqrt[{deg_str}]{{{e_str}}}"
                            else:
                                return f"\\sqrt{{{e_str}}}"
                        elif tag == 'nary':
                            nary_pr = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}naryPr')
                            sub_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}sub')
                            sup_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}sup')
                            e_elem = elem.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}e')
                            op = "\\sum"
                            if nary_pr is not None:
                                chr_el = nary_pr.find('{http://schemas.openxmlformats.org/officeDocument/2006/math}chr')
                                if chr_el is not None:
                                    val = ""
                                    for k, v in chr_el.attrib.items():
                                        if k.endswith('val') or k == 'val':
                                            val = v
                                            break
                                    if val == '∫' or 'int' in val:
                                        op = "\\int"
                                    elif val == '∏':
                                        op = "\\prod"
                                    elif val == '∑':
                                        op = "\\sum"
                            sub_str = parse_omml_to_latex(sub_elem) if sub_elem is not None else ""
                            sup_str = parse_omml_to_latex(sup_elem) if sup_elem is not None else ""
                            e_str = parse_omml_to_latex(e_elem) if e_elem is not None else ""
                            limits = ""
                            if sub_str:
                                limits += f"_{{{sub_str}}}"
                            if sup_str:
                                limits += f"^{{{sup_str}}}"
                            return f"{op}{limits} {{{e_str}}}"
                        else:
                            return "".join(parse_omml_to_latex(child) for child in elem)

                    def get_element_rich_text(element, p_obj=None):
                        parts = []
                        if p_obj is not None:
                            pref = get_p_numbering_pref(p_obj)
                            if pref:
                                parts.append(pref)
                        def recurse(node):
                            tag = node.tag.split('}')[-1]
                            if tag == 'r':
                                for child in node:
                                    child_tag = child.tag.split('}')[-1]
                                    if child_tag == 't':
                                        if child.text:
                                            parts.append(child.text)
                            elif tag in ['oMath', 'oMathPara']:
                                latex = parse_omml_to_latex(node)
                                if latex:
                                    parts.append(f" $\\displaystyle {latex}$ ")
                            elif tag == 'br':
                                parts.append("\n")
                            elif tag == 'p' and node != element:
                                if parts and parts[-1] != "\n":
                                    parts.append("\n")
                                for child in node:
                                    recurse(child)
                            else:
                                for child in node:
                                    recurse(child)
                        recurse(element)
                        return "".join(parts).strip()

                    full_text = []
                    # Đọc đoạn văn bản thường (ngoài bảng)
                    for para in doc.paragraphs:
                        p_txt = get_element_rich_text(para._p, para)
                        if p_txt:
                            full_text.append(p_txt)
                    
                    seen_cells = set()
                    for table in doc.tables:
                        for row in table.rows:
                            row_text = []
                            for cell in row.cells:
                                tc_el = cell._tc
                                if tc_el in seen_cells:
                                    continue
                                seen_cells.add(tc_el)
                                
                                cell_paras_text = []
                                for p in cell.paragraphs:
                                    p_txt = get_element_rich_text(p._p, p)
                                    if p_txt:
                                        cell_paras_text.append(p_txt)
                                if cell_paras_text:
                                    row_text.append(" ".join(cell_paras_text))
                            if row_text:
                                full_text.append(" | ".join(row_text))
                    
                    docx_text = "\n".join(full_text)
                    file_bytes = docx_text.encode('utf-8')

                    mime_type = "text/plain"
                except Exception as docx_err:
                    print(f"Lỗi đọc nội dung file Word {file.name}: {str(docx_err)}")
                    mime_type = "text/plain"
            elif fname.endswith(('.png', '.jpg', '.jpeg')): mime_type = f"image/{fname.split('.')[-1]}"
            else: mime_type = "text/plain"
            
            file_list.append({
                "file_name": file.name,
                "mime_type": mime_type,
                "data": base64.b64encode(file_bytes).decode('utf-8')
            })
        except Exception as e:
            print(f"Lỗi chuẩn bị file {file.name}: {str(e)}")
            
    return file_list

# =====================================================================
# THÌ 1: QUÉT SIÊU DỮ LIỆU & NHẬN DIỆN CHỈ TIÊU (FAST METADATA SCAN)
# =====================================================================
def node_phase_1_scan_metadata(uploaded_files, provider, model, google_keys, openai_keys):
    """
    Giai đoạn 1: Ép AI "Nhìn" file và tự động nhận diện ngôn ngữ, dịch ngầm trong đầu,
    sau đó trả về JSON chứa Metadata và Tên các chỉ tiêu (Phục vụ cho Bảng Ma Trận).
    """
    if not uploaded_files: return {"Danh_sach_TEN_cac_chi_tieu": []}
    
    files_data = prepare_file_for_ai(uploaded_files)
    
    # Tối ưu: Phase 1 chỉ cần tên chỉ tiêu, không cần đọc toàn bộ file.
    # Giới hạn data gửi AI: text=4000 ký tự, PDF giữ nguyên (binary).
    # Prompt rút gọn tiếng Anh để giảm thời gian sinh text của model.
    system_prompt = """You are a pharmaceutical QA/QC document analyst.
Read the attached document(s) (Pharmacopoeia, Standard, COA, or MOA).
Auto-translate any foreign language to Vietnamese during analysis.

TASK: Return ONLY a single JSON object:
{"Ten_chuyen_luan":"<substance name>","Nguon_tai_lieu":"<Dược điển/Tiêu chuẩn/COA/MOA>","Phien_ban_nam":"<year/version>","Danh_sach_TEN_cac_chi_tieu":["<criterion 1>","<criterion 2>",...]}

RULES:
- "Danh_sach_TEN_cac_chi_tieu": list ONLY criterion names in Vietnamese pharmaceutical terminology (e.g. "Appearance"→"Tính chất", "Assay"→"Định lượng"). Do NOT include methods or limits.
- Output ONLY valid JSON, no markdown, no explanation."""
    
    try:
        # Truyền tham số files=files_data thẳng vào API
        ai_text = call_ai_engine(system_prompt, "Scan document metadata and list all test criteria names.", provider, model, google_keys, openai_keys, is_json=True, temperature=0.0, files=files_data)
        if not ai_text: return {"Danh_sach_TEN_cac_chi_tieu": []}
        return safe_json_loads(ai_text)
    except Exception as e:
        print(f"Lỗi Node 1 (Scan Metadata): {str(e)}")
        return {"Danh_sach_TEN_cac_chi_tieu": []}



# =====================================================================
# THÌ 2: BÓC TÁCH CHI TIẾT (DEEP RAG EXTRACTION) DỰA TRÊN DANH SÁCH ĐÃ CHỐT
# =====================================================================
def worker_task_deep_extract(files_data_main, files_data_extra, criteria_subset, dictionary_rules, provider, model, google_keys, openai_keys, bilingual=True):
    """Task chạy ngầm cho Giai đoạn 2: Bóc tách SOP chi tiết.
    Nhận files_data đã chuẩn bị sẵn (đã encode base64) để tránh re-encode nhiều lần."""
    all_files = files_data_main + files_data_extra
    
    training_instructions, criteria_master, method_library = get_dynamic_method_instructions()
    personal_style_str = get_personal_style_instructions()
    # Gemma: giới hạn 1 ví dụ để tránh prompt quá dài gây lost-in-the-middle
    style_examples_str = get_relevant_style_examples(
        target_criteria_ids=list(criteria_subset.keys()),
        max_examples=1 if "gemma" in model.lower() else 2
    )

    criteria_desc_lines = []
    for k, v in criteria_subset.items():
        if k in criteria_master:
            c_info = criteria_master[k]
            ten_ct = c_info.get("ten_hien_thi", k)
            lenh_ai = c_info.get("lenh_ai_trich_xuat", v)
            tu_dien = c_info.get("tu_dien_dich", "")
            methods = c_info.get("phuong_phap_ap_dung", [])
            quy_tac = c_info.get("quy_tac_ngu_canh", {})
            
            desc = f'  - Mã chỉ tiêu: "{k}"\n'
            desc += f'    + Tên chỉ tiêu: {ten_ct}\n'
            desc += f'    + Lệnh trích xuất: {lenh_ai}\n'
            if tu_dien:
                desc += f'    + Hướng dẫn dịch/từ điển: {tu_dien}\n'
            if quy_tac and isinstance(quy_tac, dict):
                desc += f'    + Quy tắc phân biệt ngữ cảnh (Dạy AI):\n'
                for src_type, rule_text in quy_tac.items():
                    if rule_text.strip():
                        desc += f'      * Khi bóc tách từ nguồn {src_type}: {rule_text.strip()}\n'
            if methods:
                desc += f'    + Phương pháp áp dụng liên quan:\n'
                for m_id in methods:
                    if m_id in method_library:
                        m_info = method_library[m_id]
                        desc += f'      * Phương pháp: {m_info.get("ten_phuong_phap", m_id)} (Mã: {m_id})\n'
                        cau_truc = m_info.get("cau_truc_dau_ra", {})
                        if cau_truc:
                            desc += f'      * Các thuộc tính (Tag) bắt buộc phải có trong nội dung SOP/Cách làm:\n'
                            for tag_k, tag_desc in cau_truc.items():
                                desc += f'        - `{tag_k}`: {tag_desc}\n'
            criteria_desc_lines.append(desc)
        else:
            criteria_desc_lines.append(f'  - Mã chỉ tiêu: "{k}"\n    + Lệnh trích xuất/Tên chỉ tiêu: {v}')
            
    criteria_desc = "\n".join(criteria_desc_lines)
    
    guidelines = SOP_FORMATTING_GUIDELINES
    if bilingual:
        guidelines = guidelines.replace(
            "- Dịch chi tiết 100% sang Tiếng Việt, sử dụng thuật ngữ chuyên ngành Dược. Dùng dấu xuống dòng (\\n) để phân tách rõ các mục.",
            "- Trình bày song ngữ Việt - Anh, từng bước tiến hành, điều kiện thiết bị, công thức tính toán đều phải có dòng Tiếng Việt kèm bản dịch Tiếng Anh phân cách bởi dấu gạch chéo `/` (Ví dụ: `[Câu tiếng Việt] / [English Translation]`). Sử dụng thuật ngữ chuyên ngành Dược. Dùng dấu xuống dòng (\\n) để phân tách rõ các mục."
        )
        rule_sources = (
            "3. BẮT BUỘC ĐỊNH DẠNG SONG NGỮ VIỆT - ANH CHO TẤT CẢ CÁC TRƯỜNG NGUỒN VÀ TRƯỜNG CHỐT:\n"
            "Tất cả các trường chứa phương pháp kiểm nghiệm bao gồm 'duoc_dien', 'tieu_chuan', 'coa', 'moa', 'phu_luc' và 'chot' "
            "BẮT BUỘC phải viết ở dạng song ngữ Việt - Anh [Tiếng Việt] / [English] cho từng câu hoặc từng đầu mục. "
            "Nếu tài liệu gốc là tiếng Anh, hãy dịch từng câu sang tiếng Việt rồi viết theo cấu trúc: `[Câu tiếng Việt] / [Original English]`. "
            "Tuyệt đối không được giữ nguyên tiếng Anh không dịch, cũng không được chỉ viết tiếng Việt."
        )
        rule_detail = (
            "4. YÊU CẦU ĐỘ CHI TIẾT CỰC KỲ CAO VÀ RÕ RÀNG:\n"
            "Đối với từng nguồn ('duoc_dien', 'tieu_chuan', 'coa', 'moa', 'phu_luc'), bạn PHẢI trích xuất toàn bộ "
            "quy trình chi tiết từng bước (step-by-step instructions), thông số thiết bị (cột sắc ký, detector, tốc độ dòng, thể tích tiêm...), "
            "cách cân và pha tất cả các dung dịch thử/chuẩn/đệm, và toàn bộ công thức/hệ số tính toán nếu có trong tài liệu. "
            "Tuyệt đối không tóm tắt, không lược bỏ bất kỳ thông tin kỹ thuật nào, không viết chung chung, và không ghi 'Theo yêu cầu chuyên luận'."
        )
        rule_lang = "- \"yeu_cau\": Yêu cầu/giới hạn dạng chữ đầy đủ (song ngữ Việt/Anh). Phải giữ nguyên điều kiện đi kèm: \"tính trên chế phẩm khan\", \"on dried basis\", \"on anhydrous basis\"..."
        rule_ten = "- \"ten\": Tên chỉ tiêu bằng Tiếng Việt (song ngữ Việt/Anh nếu có). Đặc biệt nếu ID chỉ tiêu bắt đầu bằng \"__unmapped_\", hãy xác định và điền tên chỉ tiêu thực tế tìm được trong tài liệu (ví dụ: \"Nhôm / Aluminium\", \"Sắt / Iron\", \"Độ rã / Disintegration\"...)."
    else:
        rule_sources = (
            "3. BẮT BUỘC DỊCH 100% SANG TIẾNG VIỆT CHO TẤT CẢ CÁC TRƯỜNG NGUỒN VÀ TRƯỜNG CHỐT:\n"
            "Tất cả các trường chứa phương pháp kiểm nghiệm bao gồm 'duoc_dien', 'tieu_chuan', 'coa', 'moa', 'phu_luc' và 'chot' "
            "PHẢI được dịch và trình bày hoàn toàn 100% bằng Tiếng Việt (không chứa bất kỳ từ/câu Tiếng Anh nào ngoại trừ ký hiệu hóa học, công thức toán học và đơn vị đo). "
            "Hãy dịch toàn bộ nội dung tiếng Anh từ tài liệu gốc sang tiếng Việt một cách tự nhiên và chính xác."
        )
        rule_detail = (
            "4. YÊU CẦU ĐỘ CHI TIẾT CỰC KỲ CAO VÀ RÕ RÀNG:\n"
            "Đối với từng nguồn ('duoc_dien', 'tieu_chuan', 'coa', 'moa', 'phu_luc'), bạn PHẢI trích xuất toàn bộ "
            "quy trình chi tiết từng bước (step-by-step instructions), thông số thiết bị (cột sắc ký, detector, tốc độ dòng, thể tích tiêm...), "
            "cách cân và pha tất cả các dung dịch thử/chuẩn/đệm, và toàn bộ công thức/hệ số tính toán nếu có trong tài liệu. "
            "Tuyệt đối không tóm tắt, không lược bỏ bất kỳ thông tin kỹ thuật nào, không viết chung chung, và không ghi 'Theo yêu cầu chuyên luận'."
        )
        rule_lang = "- \"yeu_cau\": Yêu cầu/giới hạn dạng chữ đầy đủ bằng Tiếng Việt duy nhất (không dùng Tiếng Anh)."
        rule_ten = "- \"ten\": Tên chỉ tiêu bằng Tiếng Việt duy nhất (không dùng Tiếng Anh)."

    system_prompt = f"""{_ANTI_BILINGUAL_HEADER if not bilingual else ""}Bạn là Chuyên gia QA/QC Dược phẩm. Hãy "nhìn" trực tiếp vào các tài liệu đính kèm (Bao gồm Dược điển, Tiêu chuẩn nguyên liệu, COA, MOA và Phụ lục bổ sung nếu có).
    
    NHIỆM VỤ: Lập hồ sơ kiểm nghiệm, nhưng BẠN CHỈ ĐƯỢC PHÉP TÌM VÀ BÓC TÁCH CHI TIẾT CÁC CHỈ TIÊU TRONG DANH SÁCH SAU:
{criteria_desc}
    
    ══════════════════════════════════════════════════════
    BƯỚC 1: ĐỌC VÀ PHÂN BIỆT THÀNH PHẦN TÀI LIỆU (BẮT BUỘC)
    ══════════════════════════════════════════════════════
    Trước khi bóc tách, hãy đọc toàn bộ tài liệu và phân biệt chính xác:
    
    {DOCUMENT_COMPONENT_TRAINING}
    
    ══════════════════════════════════════════════════════
    BƯỚC 2: ĐỐI CHIẾU SONG NGỮ VIỆT - ANH
    ══════════════════════════════════════════════════════
    Tài liệu đính kèm có thể viết bằng Tiếng Anh hoặc Tiếng Việt. Phải tự động đối chiếu chính xác:
      + "Cảm quan" / "Tính chất" ↔ "Appearance" hoặc "Characters" hoặc "Description"
      + "Định tính" ↔ "Identification"
      + "Định lượng" ↔ "Assay"
      + "Mất khối lượng do làm khô" ↔ "Loss on drying"
      + "Tro sulfat" ↔ "Sulfated ash" hoặc "Sulphated ash"
      + "Cắn sau nung" ↔ "Residue on ignition" hoặc "Ash"
      + "Kim loại nặng" ↔ "Heavy metals"
      + "Tạp chất liên quan" ↔ "Related substances" hoặc "Related impurities" hoặc "Impurities"
      + "Hàm lượng nước" ↔ "Water" hoặc "Water content" hoặc "Moisture"
      + "Giới hạn acid - kiềm" ↔ "Acidity or alkalinity" hoặc "Acid/alkalinity"
      + "Độ tan" ↔ "Solubility"
      + "Độ trong và màu sắc" ↔ "Clarity and colour of solution" hoặc "Appearance of solution"
      + "Độ dẫn điện" ↔ "Conductivity"
      + "Đường khử" ↔ "Reducing sugars" hoặc "Reducing substances"
      + "Góc quay cực riêng" ↔ "Specific optical rotation"
      + "pH" ↔ "pH" hoặc "Acidity/Alkalinity"
      + "Tỷ trọng" ↔ "Relative density" hoặc "Density"
      + "So màu" ↔ "Colour" hoặc "Degree of coloration"
      + "Giới hạn Clorid" ↔ "Chlorides"
      + "Giới hạn Sulfat" ↔ "Sulfates" hoặc "Sulphates"
      + "Giới hạn Sắt" ↔ "Iron"
      + "Giới hạn Nhôm" ↔ "Aluminium"
      + "Giới hạn Barium" ↔ "Barium"
      + "Giới hạn Arsenic" ↔ "Arsenic"
      + "Giới hạn Phosphate" ↔ "Phosphates"
      + "Giới hạn Amoni" ↔ "Ammonium"
      + "Giới hạn Iodide" ↔ "Iodides"
      + "Giới hạn Nitrite" ↔ "Nitrites"
      + "Giới hạn Potassium" ↔ "Potassium"
      + "Giới hạn Magnesium" ↔ "Magnesium and alkaline-earth metals"

    ══════════════════════════════════════════════════════
    BƯỚC 3: QUY TẮC BÓC TÁCH TỪNG NGUỒN TÀI LIỆU
    ══════════════════════════════════════════════════════
    - Nhận diện nguồn từng tài liệu: Dược điển (USP/BP/EP/DĐVN), Tiêu chuẩn nguyên liệu/TCCS, COA, MOA, Phụ lục.
    - Với mỗi chỉ tiêu, bóc tách cách tiến hành (SOP) từ TỪNG nguồn tài liệu trên nếu có nhắc đến.
    - BẮT BUỘC TRÍCH XUẤT NỘI DUNG PHƯƠNG PHÁP: Nếu trong tài liệu có mô tả cách tiến hành/chuẩn bị dung dịch/đo đạc, PHẢI bóc tách chi tiết toàn bộ. Tuyệt đối không ghi "Theo yêu cầu chuyên luận" nếu tài liệu có nội dung hướng dẫn cụ thể.
    - Định dạng SOP bóc tách BẮT BUỘC biên tập đầy đủ theo đúng hướng dẫn:
    
    {guidelines}
    
    {rule_sources}
    
    {rule_detail}
    
    ══════════════════════════════════════════════════════
    BƯỚC 4: TRÍCH XUẤT YÊU CẦU VÀ GIỚI HẠN
    ══════════════════════════════════════════════════════
    {rule_lang}
    - "gioi_han": Chỉ lấy phần số. Ví dụ "Không quá 0.5%" → gioi_han = "0.5"; "98.0-102.0%" → gioi_han = "98.0-102.0". Nếu là định tính (đạt/không đạt) thì gioi_han = "".
    - KHÔNG BỎ SÓT: PHẢI TRẢ VỀ ĐẦY ĐỦ TẤT CẢ CÁC MÃ CHỈ TIÊU ĐƯỢC GIAO.
    - ĐỐI VỚI CHỈ TIÊU VI SINH / GIỚI HẠN NHIỄM KHUẨN (Microbial Limits / Microbiological purity): Đây là 1 chỉ tiêu duy nhất. TUYỆT ĐỐI KHÔNG ĐƯỢC tách thành nhiều chỉ tiêu nhỏ (như không được tách riêng 'Tổng số vi khuẩn hiếu khí', 'Tổng số nấm men nấm mốc', hay 'Vi khuẩn sinh bào tử' thành các chỉ tiêu riêng). Phải gộp chung tất cả các yêu cầu giới hạn vi sinh đó vào làm một chỉ tiêu duy nhất tên là 'Giới hạn nhiễm khuẩn / Microbial limits' (hoặc 'Giới hạn vi sinh / Microbiological purity'), với cột giới hạn chứa toàn bộ các yêu cầu vi sinh đó dưới dạng danh sách xuống dòng.
    - TUYỆT ĐỐI KHÔNG thêm từ "Dịch:", "(Dịch: ...)" hay bất kỳ chú thích dịch thuật nào khác vào nội dung kết quả. Hãy dịch tự nhiên và trả về trực tiếp.
    
    TỪ ĐIỂN BẮT BUỘC (Không được dịch sai các từ sau):
    {dictionary_rules}
    
    {training_instructions}

    {personal_style_str}

    {style_examples_str}

    KẾT QUẢ ĐẦU RA: Trả về DUY NHẤT một đối tượng JSON.
    Mỗi key là Mã ID của chỉ tiêu (từ danh sách trên). Value tương ứng là một đối tượng JSON chứa chính xác các trường sau:
    - {rule_ten}
    - "yeu_cau": Yêu cầu hoặc giới hạn của chỉ tiêu dưới dạng chuỗi chữ đầy đủ. Ví dụ: "Không quá 1 ppm / Not more than 1 ppm". Nếu không tìm thấy, ghi rỗng "".
    - "gioi_han": Giá trị giới hạn dưới dạng số (chỉ lấy phần số). Ví dụ: "0.5", "98.0-102.0". Nếu chỉ tiêu chỉ đánh giá định tính, ghi rỗng "".
    - "duoc_dien": Đoạn văn SOP bóc tách được từ Dược điển. Nếu không tìm thấy, ghi rỗng "".
    - "tieu_chuan": Đoạn văn SOP bóc tách được từ Tiêu chuẩn nguyên liệu / TCCS. Nếu không tìm thấy, ghi rỗng "".
    - "coa": Đoạn văn SOP bóc tách được từ COA. Nếu không tìm thấy, ghi rỗng "".
    - "moa": Đoạn văn SOP bóc tách được từ MOA. Nếu không tìm thấy, ghi rỗng "".
    - "phu_luc": Đoạn văn SOP bóc tách được từ Phụ lục bổ sung. Nếu không tìm thấy, ghi rỗng "".
    - "chot": Đoạn văn SOP chốt cuối cùng ghép từ các nguồn theo quy tắc ưu tiên (Phụ lục > Tiêu chuẩn nguyên liệu > Dược điển > COA > MOA). (Ghi lệnh "XOA_HANG" nếu không tài liệu nào nhắc đến chỉ tiêu này).
    """

    
    try:
        ai_text = call_ai_engine(system_prompt, "Bóc tách chi tiết các chỉ tiêu được yêu cầu.", provider, model, google_keys, openai_keys, is_json=True, temperature=0.0, files=all_files)
        if not ai_text: return {}
        parsed_res = safe_json_loads(ai_text)
        if not isinstance(parsed_res, dict):
            parsed_dict = {}
            if isinstance(parsed_res, list):
                for item in parsed_res:
                    if isinstance(item, dict):
                        for key_field in ["id", "ma_chi_tieu", "key", "ma_id"]:
                            if key_field in item and item[key_field] in criteria_subset:
                                parsed_dict[item[key_field]] = item
                                break
                        else:
                            for ik, iv in item.items():
                                if ik in criteria_subset:
                                    parsed_dict[ik] = iv
            parsed_res = parsed_dict
        
        normalized_res = {}
        for k in criteria_subset.keys():
            v = parsed_res.get(k, {})
            if isinstance(v, dict):
                normalized_res[k] = {
                    "ten": clean_translation_prefix(v.get("ten", "").strip()),
                    "yeu_cau": clean_translation_prefix(v.get("yeu_cau", "").strip()),
                    "gioi_han": clean_translation_prefix(v.get("gioi_han", "").strip()),
                    "duoc_dien": clean_translation_prefix(v.get("duoc_dien", "").strip()),
                    "tieu_chuan": clean_translation_prefix(v.get("tieu_chuan", "").strip()),
                    "coa": clean_translation_prefix(v.get("coa", "").strip()),
                    "moa": clean_translation_prefix(v.get("moa", "").strip()),
                    "phu_luc": clean_translation_prefix(v.get("phu_luc", "").strip()),
                    "chot": clean_translation_prefix(v.get("chot", "").strip())
                }
            else:
                # Fallback nếu AI trả về dạng chuỗi đơn giản
                val_text = extract_sop_text_from_value(v)
                normalized_res[k] = {
                    "ten": "",
                    "yeu_cau": "",
                    "gioi_han": "",
                    "duoc_dien": "",
                    "tieu_chuan": "",
                    "coa": "",
                    "moa": "",
                    "phu_luc": "",
                    "chot": clean_translation_prefix(val_text).strip()
                }
            # Nếu chot rỗng hoặc chứa từ khóa xóa hàng, đánh dấu XOA_HANG
            chot_upper = normalized_res[k]["chot"].upper()
            if not normalized_res[k]["chot"] or chot_upper in ["NONE", "NULL", "KHÔNG", "KHÔNG CÓ", "{}"]:
                if k == "dinh_tinh":
                    normalized_res[k]["chot"] = "XOA_DONG"
                else:
                    normalized_res[k]["chot"] = "XOA_HANG"
                
        return normalized_res
    except Exception as e:
        return {
            k: {
                "ten": "",
                "yeu_cau": "",
                "gioi_han": "",
                "duoc_dien": "",
                "phu_luc": "",
                "chot": f"LỖI_HỆ_THỐNG: {str(e)}"
            } for k in criteria_subset.keys()
        }

def node_phase_2_deep_extract(uploaded_files_main, uploaded_files_extra, criteria_config, dictionary_rules, provider, model, google_keys, openai_keys, chunk_size=None, max_workers=None, bilingual=True):
    """Điều phối bóc tách đa luồng siêu tốc cho Thì 2.
    
    TĂNG TỐC: Files được encode base64 DUY NHẤT MỘT LẦN ở đây,
    sau đó chia sẻ trực tiếp cho tất cả worker threads - không re-encode.
    """
    if not criteria_config: return {}
    
    # ── ENCODE FILE MỘT LẦN DUY NHẤT ──────────────────────────────────────
    files_data_main = prepare_file_for_ai(uploaded_files_main)
    files_data_extra = prepare_file_for_ai(uploaded_files_extra)
    # ───────────────────────────────────────────────────────────────────────
    
    keys = list(criteria_config.keys())
    if chunk_size is None or chunk_size <= 0:
        chunk_size = max(1, (len(keys) + 1) // 2)
        
    batches = [{k: criteria_config[k] for k in keys[i:i + chunk_size]} for i in range(0, len(keys), chunk_size)]
    
    merged_json = {}
    if max_workers is None or max_workers <= 0:
        safe_workers = min(3, len(batches))
    else:
        safe_workers = min(max_workers, len(batches))
        safe_workers = max(1, safe_workers)

    # Mỗi worker nhận files_data đã chuẩn bị sẵn (danh sách dict bất biến, an toàn đa luồng)
    with concurrent.futures.ThreadPoolExecutor(max_workers=safe_workers) as executor:
        futures = [
            executor.submit(
                worker_task_deep_extract,
                files_data_main, files_data_extra, batch,
                dictionary_rules, provider, model, google_keys, openai_keys,
                bilingual
            )
            for batch in batches
        ]
        for future in concurrent.futures.as_completed(futures):
            try:
                merged_json.update(future.result())
            except Exception as e:
                print(f"Lỗi batch extraction: {str(e)}")
            
    return merged_json


# =====================================================================
# THÌ 2 TỐI ƯU: BÓC TÁCH SONG SONG THEO TỪNG NGUỒN TÀI LIỆU (v2)
# =====================================================================
def worker_task_extract_from_source(source_label, files_data, criteria_subset, dictionary_rules, provider, model, google_keys, openai_keys, bilingual=True):
    """
    Bóc tách SOP từ MỘT nguồn tài liệu duy nhất cho TẤT CẢ các chỉ tiêu.
    Kiến trúc tối ưu: AI chỉ tập trung vào 1 loại tài liệu → nhanh và chính xác hơn.
    Trả về: {criteria_id: {"ten", "yeu_cau", "gioi_han", "sop_text"}}
    """
    if not files_data or not criteria_subset:
        return {k: {"ten": "", "yeu_cau": "", "gioi_han": "", "sop_text": ""} for k in criteria_subset.keys()}

    training_instructions, criteria_master, method_library = get_dynamic_method_instructions()
    personal_style_str = get_personal_style_instructions()
    # Gemma: giới hạn 1 ví dụ để tránh prompt quá dài gây lost-in-the-middle
    _is_gemma_worker = "gemma" in model.lower()
    style_examples_str = get_relevant_style_examples(
        target_criteria_ids=list(criteria_subset.keys()),
        max_examples=1 if _is_gemma_worker else 2
    )

    criteria_desc_lines = []
    for k, v in criteria_subset.items():
        if k in criteria_master:
            c_info = criteria_master[k]
            ten_ct = c_info.get("ten_hien_thi", k)
            lenh_ai = c_info.get("lenh_ai_trich_xuat", v)
            tu_dien = c_info.get("tu_dien_dich", "")
            methods = c_info.get("phuong_phap_ap_dung", [])
            quy_tac = c_info.get("quy_tac_ngu_canh", {})
            
            desc = f'  - Mã chỉ tiêu: "{k}"\n'
            desc += f'    + Tên chỉ tiêu: {ten_ct}\n'
            desc += f'    + Lệnh trích xuất: {lenh_ai}\n'
            if tu_dien:
                desc += f'    + Hướng dẫn dịch/từ điển: {tu_dien}\n'
            if quy_tac and isinstance(quy_tac, dict):
                desc += f'    + Quy tắc phân biệt ngữ cảnh (Dạy AI):\n'
                for src_type, rule_text in quy_tac.items():
                    if rule_text.strip():
                        is_current = " (BẮT BUỘC ÁP DỤNG cho nguồn hiện tại)" if src_type.lower() == source_label.lower() else ""
                        desc += f'      * Đối với {src_type}{is_current}: {rule_text.strip()}\n'
            if methods:
                desc += f'    + Phương pháp áp dụng liên quan:\n'
                for m_id in methods:
                    if m_id in method_library:
                        m_info = method_library[m_id]
                        desc += f'      * Phương pháp: {m_info.get("ten_phuong_phap", m_id)} (Mã: {m_id})\n'
                        cau_truc = m_info.get("cau_truc_dau_ra", {})
                        if cau_truc:
                            desc += f'      * Các thuộc tính (Tag) bắt buộc phải có trong nội dung SOP/Cách làm:\n'
                            for tag_k, tag_desc in cau_truc.items():
                                desc += f'        - `{tag_k}`: {tag_desc}\n'
            criteria_desc_lines.append(desc)
        else:
            criteria_desc_lines.append(f'  - Mã chỉ tiêu: "{k}"\n    + Lệnh trích xuất/Tên chỉ tiêu: {v}')
            
    criteria_desc = "\n".join(criteria_desc_lines)

    guidelines = SOP_FORMATTING_GUIDELINES
    if bilingual:
        guidelines = guidelines.replace(
            "- Dịch chi tiết 100% sang Tiếng Việt, sử dụng thuật ngữ chuyên ngành Dược. Dùng dấu xuống dòng (\\n) để phân tách rõ các mục.",
            "- Trình bày song ngữ Việt - Anh, từng bước tiến hành, điều kiện thiết bị, công thức tính toán đều phải có dòng Tiếng Việt kèm bản dịch Tiếng Anh phân cách bởi dấu gạch chéo `/` (Ví dụ: `[Câu tiếng Việt] / [English Translation]`). Sử dụng thuật ngữ chuyên ngành Dược. Dùng dấu xuống dòng (\\n) để phân tách rõ các mục."
        )
        rule_sop_lang = (
            "ĐỊNH DẠNG SONG NGỮ VIỆT - ANH BẮT BUỘC CHO \"sop_text\": "
            "Mọi nội dung phương pháp PHẢI ở dạng [Tiếng Việt] / [English] cho từng câu/đầu mục. "
            "Nếu tài liệu gốc là tiếng Anh, dịch từng câu sang tiếng Việt rồi viết: `[Câu tiếng Việt] / [Original English]`. "
            "Tuyệt đối không giữ nguyên tiếng Anh không dịch, cũng không được chỉ viết tiếng Việt. Giữ nguyên công thức hóa học và hệ số K."
        )
        rule_lang = "- \"yeu_cau\": Yêu cầu/giới hạn dạng chữ đầy đủ (song ngữ Việt/Anh). Giữ nguyên điều kiện: \"tính trên chế phẩm khan\", \"on dried basis\", \"on anhydrous basis\"..."
        rule_ten = "- \"ten\": Tên chỉ tiêu bằng Tiếng Việt (song ngữ Việt/Anh nếu có). Nếu ID bắt đầu bằng \"__unmapped_\", hãy xác định và điền tên chỉ tiêu thực tế."
    else:
        rule_sop_lang = (
            "DỊCH 100% SANG TIẾNG VIỆT BẮT BUỘC CHO \"sop_text\": "
            "Toàn bộ nội dung phương pháp PHẢI dịch và trình bày hoàn toàn bằng Tiếng Việt "
            "(ngoại trừ ký hiệu hóa học, công thức toán học và đơn vị đo). Giữ nguyên công thức hóa học và hệ số K."
        )
        rule_lang = "- \"yeu_cau\": Yêu cầu/giới hạn dạng chữ đầy đủ hoàn toàn bằng Tiếng Việt (không dùng Tiếng Anh)."
        rule_ten = "- \"ten\": Tên chỉ tiêu bằng Tiếng Việt (không dùng Tiếng Anh). Nếu ID bắt đầu bằng \"__unmapped_\", hãy xác định và điền tên thực tế."

    # ── Tạo JSON output hint cho Gemma TRƯỚC khi build f-string ──────────────
    # (Gemma không hỗ trợ response_mime_type=json, phải dùng text instruction)
    _gemma_json_hint = ""
    if "gemma" in model.lower():
        crit_keys = list(criteria_subset.keys())
        example_key = crit_keys[0] if crit_keys else "ma_chi_tieu"
        _gemma_json_hint = f"""
QUAN TRỌNG - CHỈ DÀNH CHO OUTPUT FORMAT:
Bắt đầu output NGAY BẰNG dấu `{{` (không có bất kỳ chú thích, giải thích hay markdown nào trước đó).
Ví dụ cấu trúc JSON cần trả về:
{{
  "{example_key}": {{
    "ten": "Tên chỉ tiêu tiếng Việt",
    "yeu_cau": "Yêu cầu/giới hạn đầy đủ",
    "gioi_han": "99.0-100.5",
    "sop_text": "Mô tả chi tiết phương pháp..."
  }}
}}
Chỉ xuất JSON thuần túy. Không dùng ```json``` hay bất kỳ markdown nào."""

    system_prompt = f"""{_ANTI_BILINGUAL_HEADER if not bilingual else ""}Bạn là Chuyên gia QA/QC Dược phẩm. Tài liệu đính kèm là loại: **{source_label}**.

NHIỆM VỤ: Bóc tách PHƯƠNG PHÁP KIỂM NGHIỆM từ tài liệu {source_label} này cho TẤT CẢ các chỉ tiêu sau:
{criteria_desc}

══════════════════════════════════════════════════════
BƯỚC 1: PHÂN BIỆT THÀNH PHẦN TÀI LIỆU (BẮT BUỘC)
══════════════════════════════════════════════════════
{DOCUMENT_COMPONENT_TRAINING}

══════════════════════════════════════════════════════
BƯỚC 2: ĐỐI CHIẾU SONG NGỮ VIỆT - ANH
══════════════════════════════════════════════════════
Tài liệu có thể viết bằng Tiếng Anh hoặc Tiếng Việt. Tự động đối chiếu:
  + "Cảm quan" / "Tính chất" ↔ "Appearance" / "Characters" / "Description"
  + "Định tính" ↔ "Identification"
  + "Định lượng" ↔ "Assay"
  + "Mất khối lượng do làm khô" ↔ "Loss on drying"
  + "Tro sulfat" ↔ "Sulfated ash" / "Sulphated ash"
  + "Cắn sau nung" ↔ "Residue on ignition" / "Ash"
  + "Kim loại nặng" ↔ "Heavy metals"
  + "Tạp chất liên quan" ↔ "Related substances" / "Related impurities" / "Impurities"
  + "Hàm lượng nước" ↔ "Water" / "Water content" / "Moisture"
  + "Giới hạn acid - kiềm" ↔ "Acidity or alkalinity"
  + "pH" ↔ "pH" / "Acidity/Alkalinity"
  + "Độ dẫn điện" ↔ "Conductivity"
  + "Góc quay cực riêng" ↔ "Specific optical rotation"
  + "Tỷ trọng" ↔ "Relative density" / "Density"
  + "Giới hạn Clorid" ↔ "Chlorides"
  + "Giới hạn Sulfat" ↔ "Sulfates"
  + "Giới hạn Sắt" ↔ "Iron"
  + "Giới hạn Nhôm" ↔ "Aluminium"

══════════════════════════════════════════════════════
BƯỚC 3: QUY TẮC BÓC TÁCH PHƯƠNG PHÁP
══════════════════════════════════════════════════════
- Tập trung đọc tài liệu **{source_label}** và bóc tách cách làm cho từng chỉ tiêu được giao.
- BẮT BUỘC TRÍCH XUẤT TOÀN BỘ: Nếu tài liệu có mô tả cách tiến hành, chuẩn bị dung dịch, đo đạc → PHẢI bóc tách chi tiết toàn bộ. Tuyệt đối không ghi "Theo yêu cầu chuyên luận" khi tài liệu có nội dung cụ thể.
- Nếu chỉ tiêu KHÔNG được đề cập trong tài liệu {source_label} này → trường "sop_text" để rỗng "".
- Định dạng SOP BẮT BUỘC theo hướng dẫn phong cách dưới đây:

{guidelines}

{rule_sop_lang}

YÊU CẦU ĐỘ CHI TIẾT CỰC KỲ CAO:
Bạn PHẢI trích xuất toàn bộ quy trình chi tiết từng bước (step-by-step), thông số thiết bị (cột sắc ký, detector, tốc độ dòng, thể tích tiêm...), cách cân và pha tất cả các dung dịch thử/chuẩn/đệm, và toàn bộ công thức/hệ số tính toán nếu có trong tài liệu. Tuyệt đối không tóm tắt hay lược bỏ thông tin kỹ thuật.

══════════════════════════════════════════════════════
BƯỚC 4: TRÍCH XUẤT YÊU CẦU VÀ GIỚI HẠN
══════════════════════════════════════════════════════
{rule_lang}
- "gioi_han": Chỉ lấy phần số. "Không quá 0.5%" → "0.5"; "98.0-102.0%" → "98.0-102.0". Định tính thì để rỗng "".
- ĐỐI VỚI CHỈ TIÊU VI SINH / GIỚI HẠN NHIỄM KHUẨN: Đây là 1 chỉ tiêu duy nhất. Gộp tất cả yêu cầu vi sinh vào "sop_text" dưới dạng danh sách.
- TUYỆT ĐỐI KHÔNG thêm "Dịch:", "(Dịch: ...)" vào kết quả.

TỪ ĐIỂN BẮT BUỘC (Không được dịch sai):
{dictionary_rules}

{training_instructions}

{personal_style_str}

{style_examples_str}

KẾT QUẢ ĐẦU RA: Trả về DUY NHẤT một JSON object.
Mỗi key là Mã ID chỉ tiêu (từ danh sách trên). Value là object chứa CHÍNH XÁC:
- {rule_ten}
- "yeu_cau": Yêu cầu/giới hạn đầy đủ. Nếu không tìm thấy trong tài liệu này, ghi "".
- "gioi_han": Giá trị số giới hạn. Nếu định tính hoặc không có, ghi "".
- "sop_text": Đoạn văn SOP chi tiết từ tài liệu {source_label}. Nếu chỉ tiêu không có trong tài liệu này, ghi "".
{_gemma_json_hint}
"""


    try:
        ai_text = call_ai_engine(
            system_prompt,
            f"Bóc tách chi tiết phương pháp từ {source_label}.",
            provider, model, google_keys, openai_keys,
            is_json=True, temperature=0.0, files=files_data
        )
        if not ai_text:
            return {k: {"ten": "", "yeu_cau": "", "gioi_han": "", "sop_text": ""} for k in criteria_subset.keys()}

        parsed = safe_json_loads(ai_text)
        
        # Ghi debug log nếu kết quả bị lỗi/hỏng cấu trúc
        is_corrupted = False
        if isinstance(parsed, dict):
            for pk, pv in parsed.items():
                if isinstance(pv, str) and pv.strip() in ["{", "}", "[", "]"]:
                    is_corrupted = True
                    break
                elif isinstance(pv, dict):
                    for sub_pk, sub_pv in pv.items():
                        if isinstance(sub_pv, str) and sub_pv.strip() in ["{", "}", "[", "]"]:
                            is_corrupted = True
                            break
        else:
            is_corrupted = True
            
        if is_corrupted:
            try:
                with open("d:\\Phieu_KNNL_AI\\ai_error_debug.txt", "a", encoding="utf-8") as f_debug:
                    f_debug.write(f"\n=== CORRUPTED OR INVALID JSON ({source_label}) ===\n")
                    f_debug.write(f"Keys requested: {list(criteria_subset.keys())}\n")
                    f_debug.write(f"Parsed result: {parsed}\n")
                    f_debug.write(f"AI Text:\n{ai_text}\n")
            except Exception:
                pass

        if not isinstance(parsed, dict):
            parsed_dict = {}
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        for key_field in ["id", "ma_chi_tieu", "key", "ma_id"]:
                            if key_field in item and item[key_field] in criteria_subset:
                                parsed_dict[item[key_field]] = item
                                break
                        else:
                            for ik, iv in item.items():
                                if ik in criteria_subset:
                                    parsed_dict[ik] = iv
            parsed = parsed_dict

        result = {}
        for k in criteria_subset.keys():
            v = parsed.get(k, {})
            if isinstance(v, dict):
                result[k] = {
                    "ten": clean_translation_prefix(v.get("ten", "").strip()),
                    "yeu_cau": clean_translation_prefix(v.get("yeu_cau", "").strip()),
                    "gioi_han": clean_translation_prefix(v.get("gioi_han", "").strip()),
                    "sop_text": clean_translation_prefix(v.get("sop_text", "").strip()),
                }
            else:
                val_text = extract_sop_text_from_value(v)
                result[k] = {
                    "ten": "",
                    "yeu_cau": "",
                    "gioi_han": "",
                    "sop_text": clean_translation_prefix(val_text).strip() if v else ""
                }

        # ── Gemma Retry Logic: Nếu thiếu > 50% chỉ tiêu, thử lại với prompt rút gọn ──
        if "gemma" in model.lower():
            missing_keys = [k for k in criteria_subset.keys() if not result.get(k, {}).get("sop_text", "").strip()
                            and not result.get(k, {}).get("yeu_cau", "").strip()]
            missing_ratio = len(missing_keys) / max(len(criteria_subset), 1)
            if missing_ratio > 0.5 and missing_keys:
                print(f"[Gemma Retry] {source_label}: {len(missing_keys)}/{len(criteria_subset)} chỉ tiêu trống → retry với prompt rút gọn...")
                # Tạo danh sách chỉ tiêu cần retry
                retry_subset = {k: criteria_subset[k] for k in missing_keys}
                retry_keys_desc = "\n".join([
                    f'  - "{k}": {v}' for k, v in retry_subset.items()
                ])
                retry_example_key = missing_keys[0] if missing_keys else "chi_tieu"
                retry_prompt = f"""CRITICAL INSTRUCTION: Your response MUST be ONLY a valid JSON object starting with '{{'.

You are a pharmaceutical QA/QC expert. Read the attached {source_label} document carefully.

Extract the following test criteria information:
{retry_keys_desc}

For each criterion ID, return a JSON object with:
- "ten": criterion name in Vietnamese
- "yeu_cau": requirement/limit as full text
- "gioi_han": numeric limit only (e.g., "0.5", "99.0-100.5", or "")
- "sop_text": detailed SOP method text extracted from {source_label}. If not found, return "".

OUTPUT: Start immediately with '{{', no markdown, no explanation.
Example:
{{
  "{retry_example_key}": {{
    "ten": "Tên chỉ tiêu",
    "yeu_cau": "Yêu cầu đầy đủ",
    "gioi_han": "",
    "sop_text": "Chi tiết phương pháp..."
  }}
}}"""
                try:
                    retry_text = call_ai_engine(
                        retry_prompt,
                        f"Extract criteria from {source_label} document.",
                        provider, model, google_keys, openai_keys,
                        is_json=True, temperature=0.0, files=files_data
                    )
                    if retry_text:
                        retry_parsed = safe_json_loads(retry_text)
                        if isinstance(retry_parsed, dict):
                            for k in missing_keys:
                                rv = retry_parsed.get(k, {})
                                if isinstance(rv, dict) and (rv.get("sop_text", "").strip() or rv.get("yeu_cau", "").strip()):
                                    result[k] = {
                                        "ten": clean_translation_prefix(rv.get("ten", "").strip()),
                                        "yeu_cau": clean_translation_prefix(rv.get("yeu_cau", "").strip()),
                                        "gioi_han": clean_translation_prefix(rv.get("gioi_han", "").strip()),
                                        "sop_text": clean_translation_prefix(rv.get("sop_text", "").strip()),
                                    }
                                    print(f"[Gemma Retry] Phục hồi thành công: {k}")
                except Exception as retry_err:
                    print(f"[Gemma Retry] Lỗi retry: {str(retry_err)}")

        return result
    except Exception as e:
        print(f"Lỗi worker_task_extract_from_source ({source_label}): {str(e)}")
        return {k: {"ten": "", "yeu_cau": "", "gioi_han": "", "sop_text": ""} for k in criteria_subset.keys()}


def node_phase_2_deep_extract_v2(source_files_dict, extra_files_data, criteria_config, dictionary_rules, provider, model, google_keys, openai_keys, bilingual=True, chunk_size=5, max_workers=None):
    """
    Kiến trúc tối ưu tốc độ v2: Bóc tách song song theo từng nguồn tài liệu riêng biệt kết hợp chia nhỏ (chunk) chỉ tiêu.

    Thay vì gửi tất cả chỉ tiêu trong 1 cuộc gọi AI cho mỗi nguồn tài liệu (kiến trúc v2 cũ),
    hàm này chia nhỏ danh sách chỉ tiêu thành các batch (mặc định 5 chỉ tiêu) và gửi song song,
    giúp giảm thời gian sinh text tuần tự của LLM và tránh lỗi mất/cụt thông tin -> nhanh hơn ~3-5x.
    """
    if not criteria_config:
        return {}

    # Map tên nguồn UI → key trường kết quả JSON
    SOURCE_KEY_MAP = {
        "Dược điển": "duoc_dien",
        "Tiêu chuẩn nguyên liệu": "tieu_chuan",
        "COA": "coa",
        "MOA": "moa",
        "Phụ lục": "phu_luc",
    }

    # Thứ tự ưu tiên chọn chot: Phụ lục > TCNL > DD > COA > MOA
    PRIORITY_ORDER = ["phu_luc", "tieu_chuan", "duoc_dien", "coa", "moa"]

    # Chia criteria_config thành các batch nhỏ theo chunk_size
    keys = list(criteria_config.keys())
    is_gemma = "gemma" in model.lower()
    if not chunk_size or chunk_size <= 0:
        # Gemma: tối đa 3 chỉ tiêu/batch để tránh mất thông tin do context window hạn chế
        chunk_size = 3 if is_gemma else 5

    criteria_batches = []
    for i in range(0, len(keys), chunk_size):
        batch_keys = keys[i:i + chunk_size]
        batch_dict = {k: criteria_config[k] for k in batch_keys}
        criteria_batches.append(batch_dict)

    # Xây dựng danh sách task song song
    tasks = []  # [(source_label, files_data, criteria_batch)]
    for label, files_data in source_files_dict.items():
        if files_data:
            for batch_dict in criteria_batches:
                tasks.append((label, files_data, batch_dict))
    if extra_files_data:
        for batch_dict in criteria_batches:
            tasks.append(("Phụ lục", extra_files_data, batch_dict))

    if not tasks:
        empty_entry = {
            "ten": "", "yeu_cau": "", "gioi_han": "",
            "duoc_dien": "", "tieu_chuan": "", "coa": "", "moa": "", "phu_luc": "",
            "chot": "XOA_HANG"
        }
        return {k: empty_entry.copy() for k in criteria_config.keys()}

    # Chạy song song: mỗi nguồn + mỗi batch là 1 cuộc gọi AI riêng biệt
    source_results = {}  # {src_key: {criteria_id: {sop_text, yeu_cau, gioi_han, ten}}}
    
    if max_workers is None or max_workers <= 0:
        # Giới hạn worker dựa trên số API key để tránh bão hòa rate limit
        # Mỗi key xử lý tối đa 2 requests song song
        n_keys = len(google_keys) if google_keys else 1
        safe_workers = min(n_keys * 2, len(tasks), 8)  # Tối đa 8 dù nhiều key
    else:
        safe_workers = min(max_workers, len(tasks))
    safe_workers = max(1, safe_workers)

    with concurrent.futures.ThreadPoolExecutor(max_workers=safe_workers) as executor:
        future_to_task = {
            executor.submit(
                worker_task_extract_from_source,
                label, files_data, batch_dict,
                dictionary_rules, provider, model, google_keys, openai_keys,
                bilingual
            ): (label, batch_dict)
            for label, files_data, batch_dict in tasks
        }
        for future in concurrent.futures.as_completed(future_to_task):
            label, batch_dict = future_to_task[future]
            src_key = SOURCE_KEY_MAP.get(label, label.lower().replace(" ", "_"))
            if src_key not in source_results:
                source_results[src_key] = {}
            try:
                res_dict = future.result()
                source_results[src_key].update(res_dict)
            except Exception as e:
                print(f"Lỗi bóc tách nguồn '{label}' cho batch {list(batch_dict.keys())}: {str(e)}")
                for k in batch_dict.keys():
                    source_results[src_key][k] = {"ten": "", "yeu_cau": "", "gioi_han": "", "sop_text": ""}

    # Merge kết quả: ghép tất cả nguồn lại cho từng chỉ tiêu
    merged = {}
    for k in criteria_config.keys():
        entry = {
            "ten": "", "yeu_cau": "", "gioi_han": "",
            "duoc_dien": "", "tieu_chuan": "", "coa": "", "moa": "", "phu_luc": "",
            "chot": ""
        }

        # Thu thập sop_text từ mỗi nguồn
        for src_key in PRIORITY_ORDER:
            if src_key not in source_results:
                continue
            sop_text = source_results[src_key].get(k, {}).get("sop_text", "").strip()
            entry[src_key] = sop_text

        # Chọn ten, yeu_cau, gioi_han từ nguồn ưu tiên cao nhất có SOP
        for src_key in PRIORITY_ORDER:
            src_data = source_results.get(src_key, {}).get(k, {})
            if src_data.get("sop_text", "").strip():
                if not entry["ten"]:
                    entry["ten"] = src_data.get("ten", "").strip()
                if not entry["yeu_cau"]:
                    entry["yeu_cau"] = src_data.get("yeu_cau", "").strip()
                if not entry["gioi_han"]:
                    entry["gioi_han"] = src_data.get("gioi_han", "").strip()

        # Fallback: nếu không nguồn nào có SOP, vẫn lấy ten/yeu_cau/gioi_han từ bất kỳ nguồn nào
        if not entry["ten"]:
            for src_key in PRIORITY_ORDER:
                t = source_results.get(src_key, {}).get(k, {}).get("ten", "").strip()
                if t:
                    entry["ten"] = t
                    break
        if not entry["yeu_cau"]:
            for src_key in PRIORITY_ORDER:
                yc = source_results.get(src_key, {}).get(k, {}).get("yeu_cau", "").strip()
                if yc:
                    entry["yeu_cau"] = yc
                    break
        if not entry["gioi_han"]:
            for src_key in PRIORITY_ORDER:
                gh = source_results.get(src_key, {}).get(k, {}).get("gioi_han", "").strip()
                if gh:
                    entry["gioi_han"] = gh
                    break

        # Chọn chot theo thứ tự ưu tiên: Phụ lục > TCNL > DD > COA > MOA
        # Bỏ qua các sentinel value ("XOA_HANG", "XOA_DONG"...) để fallback đúng nguồn tiếp theo
        _CHOT_SENTINELS = {"XOA_HANG", "XOA_DONG", "NONE", "NULL", "N/A", "KHÔNG CÓ"}
        chot = ""
        for src_key in PRIORITY_ORDER:
            val = entry.get(src_key, "").strip()
            if val and val.upper() not in _CHOT_SENTINELS:
                chot = val
                break

        # Fallback nâng cao: nếu sop_text rỗng nhưng yeu_cau có giá trị,
        # dùng yeu_cau làm chot để tránh mất dữ liệu quan trọng
        if not chot and entry.get("yeu_cau", "").strip():
            chot = f"[Chỉ có giới hạn, không có SOP chi tiết] {entry['yeu_cau']}"

        # Xử lý trường hợp không tìm thấy
        if not chot:
            chot = "XOA_HANG"
        chot_upper = chot.upper()
        if chot_upper in ["NONE", "NULL", "KHÔNG", "KHÔNG CÓ", "{}"]:
            chot = "XOA_DONG" if k == "dinh_tinh" else "XOA_HANG"

        entry["chot"] = chot
        merged[k] = entry

    return merged


# =====================================================================
def node_phase_2_extract_other_criteria(uploaded_files_main, uploaded_files_extra, existing_names, provider, model, google_keys, openai_keys):
    """Mắt thần quét lại file một lần nữa để nhặt những chỉ tiêu bị bỏ quên"""
    files_data_main = prepare_file_for_ai(uploaded_files_main)
    files_data_extra = prepare_file_for_ai(uploaded_files_extra)
    all_files = files_data_main + files_data_extra
    
    training_instructions, _, _ = get_dynamic_method_instructions()
    
    system_prompt = f"""Bạn là Chuyên gia QA/QC Dược phẩm. 
    Nhiệm vụ: Hãy "nhìn" vào các tài liệu đính kèm và trích xuất TẤT CẢ các chỉ tiêu kiểm nghiệm CÒN LẠI mà KHÔNG NẰM TRONG danh sách sau:
    DANH SÁCH ĐÃ BÓC TÁCH (TUYỆT ĐỐI BỎ QUA MỤC NÀY): {', '.join(existing_names)}
    
    {DOCUMENT_COMPONENT_TRAINING}
    
    QUY TẮC:
    - Nếu tài liệu là tiếng nước ngoài, phải dịch chi tiết 100% sang tiếng Việt.
    - Định dạng trường "noi_dung" BẮT BUỘC biên tập đầy đủ theo đúng hướng dẫn phong cách và định dạng dưới đây (dùng \\n để xuống dòng):
    
    {SOP_FORMATTING_GUIDELINES}
    
    {training_instructions}

    - Kết quả trả về là JSON Array chứa tối đa 15 object: [ {{"ten_chi_tieu": "...", "noi_dung": "..."}} ]
    - Nếu không còn chỉ tiêu nào khác, trả về mảng rỗng: []
    """
    
    try:
        ai_text = call_ai_engine(system_prompt, "Quét tìm các chỉ tiêu ngoại lệ.", provider, model, google_keys, openai_keys, is_json=True, temperature=0.0, files=all_files)
        if not ai_text: return []
        res = safe_json_loads(ai_text)
        
        if isinstance(res, list): return res
        if isinstance(res, dict):
            for k, v in res.items():
                if isinstance(v, list): return v
        return []
    except Exception:
        return []

# =====================================================================
# TCNL MỚI: VALIDATION NGỮ NGHĨA SAU KHI QUÉT
# =====================================================================
def _validate_scanned_criteria(items):
    """Tầng validation ngữ nghĩa sau khi AI trả kết quả quét.
    Phát hiện và tự sửa các lỗi logic phổ biến:
      - Lỗi 1: Định lượng (Assay) bị gán giới hạn nhỏ (< 50%) — thực ra là giới hạn nước/tạp chất.
      - Lỗi 2: Kim loại nặng (Lead, Nickel, Arsenic...) bị đặt tên sai là "Chỉ số acid".
    """
    import re
    import unicodedata

    def _norm(s):
        """Normalize về lowercase không dấu."""
        if not s: return ""
        s = str(s).replace('đ', 'd').replace('Đ', 'd')
        nfkd = unicodedata.normalize('NFKD', s.lower())
        cleaned = "".join(c for c in nfkd if not unicodedata.combining(c))
        return re.sub(r'[^a-z0-9 /\-\.]', ' ', cleaned).strip()

    # ── Bảng ánh xạ từ khóa → tên chuẩn của kim loại nặng ──
    HEAVY_METAL_KEYWORDS = {
        "lead":    ("Chì / Lead",        ["lead", "plumbum", " pb "]),
        "nickel":  ("Nickel / Nickel",   ["nickel", " ni "]),
        "arsenic": ("Asen / Arsenic",    ["arsenic", "arsen", " as "]),
        "mercury": ("Thủy ngân / Mercury", ["mercury", "mercurium", " hg "]),
        "cadmium": ("Cadmi / Cadmium",   ["cadmium", "cadmi", " cd "]),
    }

    ASSAY_NAMES  = {"dinh luong", "assay", "ham luong"}
    WATER_NAMES  = {"ham luong nuoc", "water", "nuoc", "ham am"}

    validated = []
    for item in items:
        if not isinstance(item, dict):
            validated.append(item)
            continue

        name     = item.get("ten_chi_tieu", "").strip()
        limit    = item.get("gioi_han",     "").strip()
        norm_name  = _norm(name)
        norm_limit = _norm(limit)

        # ──────────────────────────────────────────────────────────────
        # [B1] QUY TẮC 3: LOD / Hàm lượng nước không được có đơn vị mg/kg
        # ──────────────────────────────────────────────────────────────
        LOD_NAMES = {"mat khoi luong", "loss on drying", "ham luong nuoc", "water content",
                     "ham am", "moisture", "lod", "water"}
        is_lod_name = any(kw in norm_name for kw in LOD_NAMES)
        if is_lod_name and limit:
            has_metal_unit_lod = bool(re.search(r'\b(mg/kg|ppm|ppb|µg/kg|ug/kg)\b', limit, re.IGNORECASE))
            if has_metal_unit_lod:
                print(f"[VALIDATION-B1-R3] LOD/Water has wrong unit mg/kg: '{name}' → '{limit}'. Cleared.")
                item = dict(item)
                item["gioi_han"] = ""
                item["_validation_warning"] = (
                    f"Gioi han '{limit}' co don vi mg/kg khong hop le cho chi tieu LOD/Water. "
                    "Vui long kiem tra lai tai lieu goc."
                )

        # ──────────────────────────────────────────────────────────────
        # [B1] QUY TẮC 4: Chỉ tiêu định tính / cảm quan không được gán giá trị số %
        # ──────────────────────────────────────────────────────────────
        QUALITATIVE_NAMES = {"dinh tinh", "identification", "cam quan", "tinh chat",
                             "appearance", "characters", "do tan", "solubility"}
        is_qualitative = any(kw in norm_name for kw in QUALITATIVE_NAMES)
        # Tránh nhầm với "Định tính A: ..., Định tính B: ..." — chỉ xử lý khi tên không có chữ số theo sau
        if is_qualitative and limit:
            # Kiểm tra nếu giới hạn chỉ toàn là số %  và không có chữ mô tả nào
            pct_only_match = re.fullmatch(r'\s*\d+[\.,]?\d*\s*%\s*', limit.strip())
            if pct_only_match:
                print(f"[VALIDATION-B1-R4] Qualitative criteria has numeric % limit: '{name}' → '{limit}'. Cleared.")
                item = dict(item)
                item["gioi_han"] = ""
                item["_validation_warning"] = (
                    f"Chi tieu dinh tinh/cam quan '{name}' khong nen co gioi han so '{limit}'. "
                    "Hay de trong hoac viet 'Dat / Passes test'."
                )

        # ──────────────────────────────────────────────────────────────
        # [B1] QUY TẮC 5: pH phải là số thực trong khoảng hợp lý 0–14
        # ──────────────────────────────────────────────────────────────
        is_ph_name = norm_name.strip() in {"ph", "ph dung dich", "ph solution"} or norm_name.startswith("ph ")
        if is_ph_name and limit:
            ph_numbers = re.findall(r'(\d+(?:[.,]\d+)?)', limit)
            if ph_numbers:
                ph_vals = [float(p.replace(',', '.')) for p in ph_numbers]
                if any(v > 14.0 for v in ph_vals):
                    print(f"[VALIDATION-B1-R5] pH limit out of range 0-14: '{name}' → '{limit}'. Flagged.")
                    item = dict(item)
                    item["_validation_warning"] = (
                        f"Gia tri pH '{limit}' vuot ngoai khoang 0-14. Co the bi nham gioi han cua chi tieu khac."
                    )

        # ──────────────────────────────────────────────────────────────
        # QUY TẮC 1: Định lượng không được mang giới hạn nhỏ < 50%
        # ──────────────────────────────────────────────────────────────
        # Phân biệt chính xác Assay vs Water:
        # - Assay: norm_name chứa "assay" hoặc "dinh luong" nhưng KHÔNG chứa từ khóa nước
        WATER_EXCLUSION = {"nuoc", "water", "moisture", "ham am", "am"}
        is_assay_name = (
            "assay" in norm_name.split()
            or "dinh luong" in norm_name
        ) and not any(w in norm_name.split() for w in WATER_EXCLUSION)
        if is_assay_name and limit:
            # Tìm số % trong giới hạn
            pct_numbers = re.findall(r'(\d+(?:[.,]\d+)?)\s*%', limit)
            if pct_numbers:
                all_values = []
                for pn in pct_numbers:
                    try:
                        all_values.append(float(pn.replace(',', '.')))
                    except ValueError:
                        pass
                # Nếu tất cả các số % đều nhỏ hơn 50 → chắc chắn sai (là giới hạn tạp chất/nước)
                if all_values and max(all_values) < 50.0:
                    print(f"[VALIDATION] Assay limit error: '{name}' assigned wrong limit '{limit}' (max={max(all_values)}% < 50%). Cleared.")
                    item = dict(item)  # copy để không mutate gốc
                    item["gioi_han"] = ""  # xóa giới hạn sai, để trống cho người dùng tự điền
                    item["_validation_warning"] = (
                        f"Gioi han '{limit}' phat hien sai logic (< 50% khong phai gioi han Dinh luong). "
                        "Vui long kiem tra lai tu tai lieu goc."
                    )

        # ──────────────────────────────────────────────────────────────
        # QUY TẮC 2: Kim loại nặng bị đặt tên sai
        # Nhận biết: giới hạn có đơn vị mg/kg, ppm, ppb
        # ──────────────────────────────────────────────────────────────
        has_metal_unit = bool(re.search(r'\b(mg/kg|ppm|ppb|µg/kg|ug/kg)\b', limit, re.IGNORECASE))
        if has_metal_unit:
            norm_limit_lower = limit.lower()
            correct_name = None
            for _key, (display_name, keywords) in HEAVY_METAL_KEYWORDS.items():
                if any(kw in norm_limit_lower for kw in keywords):
                    correct_name = display_name
                    break
            if not correct_name:
                # Nếu không nhận diện được nguyên tố cụ thể → dùng tên chung
                correct_name = "Kim loại nặng / Heavy metals"

            # Kiểm tra xem tên hiện tại có SAI không
            BAD_NAMES_FOR_METALS = {"chi so acid", "acid value", "chi so a xit", "acidity"}
            if any(bad in norm_name for bad in BAD_NAMES_FOR_METALS):
                print(f"[VALIDATION] Heavy metal name error: '{name}' has mg/kg unit. Fixed to '{correct_name}'.")
                item = dict(item)
                item["ten_chi_tieu"] = correct_name
                item["_validation_warning"] = (
                    f"Ten '{name}' sua thanh '{correct_name}' "
                    "vi gioi han co don vi mg/kg (kim loai nang, khong phai chi so acid)."
                )

        # ──────────────────────────────────────────────────────────────
        # QUY TẮC 6: Chuẩn hóa Định tính D (Hàm lượng nước) của Dược điển
        # ──────────────────────────────────────────────────────────────
        if "dinh tinh d" in norm_name or "identification d" in norm_name:
            if not limit or any(kw in norm_limit for kw in ["water", "test", "xem", "tests", "nuoc"]):
                item = dict(item)
                item["gioi_han"] = "Đáp ứng phép thử Hàm lượng nước (xem mục nước) / Complies with the test for water"

        validated.append(item)

    return validated


# =====================================================================
# TCNL MỚI: QUÉT CHỈ TIÊU + GIỚI HẠN TỪ TỪNG NGUỒN TÀI LIỆU
# =====================================================================
def tcnl_scan_criteria_and_limits(uploaded_files, source_label, provider, model, google_keys, openai_keys, bilingual=True, files_data=None, monograph_name=None):
    """Quét 1 rổ tài liệu (VD: Dược điển, COA, MOA, TCCS),
    trả về danh sách [{ten_chi_tieu, gioi_han}].
    
    Tối ưu: Nếu files_data đã được chuẩn bị sẵn (đã encode base64), truyền vào trực tiếp
    để tránh encode lại. Nếu không, sẽ tự encode từ uploaded_files.
    """
    if files_data is None:
        if not uploaded_files: return []
        files_data = prepare_file_for_ai(uploaded_files)
    if not files_data: return []
    
    if bilingual:
        rule_1 = """1. ĐỊNH DẠNG SONG NGỮ VIỆT - ANH BẮT BUỘC: 
       - TÊN CHỈ TIÊU (ten_chi_tieu): Phải trình bày dưới dạng song ngữ "Tiếng Việt / Tiếng Anh" (Ví dụ: "Định lượng / Assay", "Tính chất / Appearance", "Tro sulfat / Sulfated ash", "Kim loại nặng / Heavy metals", "Mất khối lượng do làm khô / Loss on drying", "Giới hạn acid - kiềm / Acidity or alkalinity").
       - GIỚI HẠN/YÊU CẦU (gioi_han): Phải trình bày dưới dạng song ngữ "Tiếng Việt / Tiếng Anh" (Ví dụ: "Không quá 0,1% / Not more than 0.1%", "Đạt yêu cầu / Passes test", "Bột kết tinh trắng hoặc tinh thể không màu / White crystalline powder or colorless crystals")."""
    else:
        rule_1 = """1. DỊCH CHUẨN XÁC SANG TIẾNG VIỆT: 
       - Dịch 100% sang Tiếng Việt chuẩn dược lý (ví dụ: "Appearance" -> "Tính chất", "Assay" -> "Định lượng", "Loss on drying" -> "Mất khối lượng do làm khô", "Sulfated ash" -> "Tro sulfat", "Acidity or alkalinity" -> "Giới hạn acid - kiềm")."""
       
    if bilingual:
        json_example_bilingual = (
            '    [\n'
            '      {"ten_chi_tieu": "Tính chất / Appearance", "gioi_han": "Bột kết tinh trắng / White crystalline powder"},\n'
            '      {"ten_chi_tieu": "Định tính A / Identification A", "gioi_han": "Đạt / Passes test"},\n'
            '      {"ten_chi_tieu": "Định lượng / Assay", "gioi_han": "99,0% đến 100,5% (khan) / 99.0-100.5% (dried)"},\n'
            '      ...\n'
            '    ]'
        )
    else:
        json_example_bilingual = (
            '    [\n'
            '      {"ten_chi_tieu": "Tính chất", "gioi_han": "Bột kết tinh trắng hoặc tinh thể không màu"},\n'
            '      {"ten_chi_tieu": "Định tính A", "gioi_han": "Đạt yêu cầu phản ứng"},\n'
            '      {"ten_chi_tieu": "Định lượng", "gioi_han": "99,0% đến 100,5% (tính trên chế phẩm khan)"},\n'
            '      ...\n'
            '    ]'
        )
    # ── [A2] Ví dụ âm tính: Những gì KHÔNG phải chỉ tiêu ──
    NEGATIVE_EXAMPLES = """
    ══════════════════════════════════════════════════════
    CẢNH BÁO: NHỮNG GÌ TUYỆT ĐỐI KHÔNG PHẢI CHỈ TIÊU
    ══════════════════════════════════════════════════════
    TUYỆT ĐỐI KHÔNG đưa vào danh sách kết quả các thông tin sau:
      ✗ Tên thuốc/hoạt chất (VD: "Paracetamol", "Amoxicillin", "Dexamethasone")
      ✗ Tên nhà sản xuất, số lô, ngày sản xuất, ngày hết hạn (Exp. Date, Mfg. Date)
      ✗ Tiêu đề cột bảng (VD: "Test Items", "Specifications", "Results", "Parameters")
      ✗ Mã dược điển / số chuyên luận chung (VD: "2.2.1", "USP <921>", "EP 2.9.1")
      ✗ "System Suitability" (Tính thích hợp hệ thống) — đây chỉ là điều kiện kỹ thuật, không phải chỉ tiêu độc lập
      ✗ Phần "Definition" hoặc "Content" đầu chuyên luận BP/EP — Đây là giới hạn của "Định lượng", không phải chỉ tiêu riêng
      ✗ Tên dung môi, thuốc thử (VD: "Acetonitrile", "Methanol", "HCl 0.1N")
      ✗ Thông tin bao bì, lưu trữ (VD: "Store below 25°C", "Keep in dry place")
    """

    # ── Quy tắc bổ sung đặc thù theo loại tài liệu ──
    is_coa = source_label.upper() in ("COA", "COA/MOA", "MOA")
    is_pharmacopoeia = any(kw in source_label for kw in ("Dược điển", "Pharmacopoeia", "BP", "EP", "USP", "JP", "CP", "DĐVN"))

    if is_coa:
        source_specific_rules = """
    ══════════════════════════════════════════════════════
    QUY TẮC ĐẶC THÙ CHO TÀI LIỆU COA / MOA
    ══════════════════════════════════════════════════════
    COA thường có 3 cột: TEST ITEMS | SPECIFICATIONS | RESULT OF ANALYSIS
    (Hoặc 2 cột: TEST ITEMS | SPECIFICATIONS nếu không có cột kết quả)

    BƯỚC BẮT BUỘC — NHẬN DIỆN CỘT TRƯỚC KHI ĐỌC:
    1. Xác định đâu là cột TÊN CHỈ TIÊU (Test items): liệt kê tên các phép thử.
    2. Xác định đâu là cột TIÊU CHUẨN CHẤP NHẬN (Specifications): chứa giới hạn số/mô tả.
    3. Xác định đâu là cột KẾT QUẢ (Result): chứa "Pass", "Fail", con số đo được.

    QUY TẮC LẤY DỮ LIỆU:
    - "ten_chi_tieu" → lấy từ cột TÊN CHỈ TIÊU, dịch sang tên dược lý chuẩn.
    - "gioi_han" → lấy từ cột TIÊU CHUẨN CHẤP NHẬN (SPECIFICATIONS), không phải cột RESULT.
    - Nếu cột SPECIFICATIONS có nội dung → đó là giới hạn cần lấy, dù cột RESULT chỉ ghi "Pass".
    - Nếu COA không có cột SPECIFICATIONS riêng và chỉ ghi kết quả → gioi_han = "Đạt / Pass".

    VÍ DỤ CHUẨN (COA 3 cột):
    TEST ITEMS | SPECIFICATIONS                               | RESULT
    Assay      | Not less than 98.0% and not more than 100.5% | Pass
    Water      | Not more than 1.0%                           | Pass
    Lead       | Not more than 1 mg/kg                        | Pass

    → {"ten_chi_tieu": "Định lượng / Assay",       "gioi_han": "Không ít hơn 98,0% và không quá 100,5% / Not less than 98.0% and not more than 100.5%"}
    → {"ten_chi_tieu": "Hàm lượng nước / Water",   "gioi_han": "Không quá 1,0% / Not more than 1.0%"}
    → {"ten_chi_tieu": "Chì / Lead",               "gioi_han": "Không quá 1 mg/kg / Not more than 1 mg/kg"}
    """
    elif is_pharmacopoeia:
        source_specific_rules = """
    ══════════════════════════════════════════════════════
    QUY TẮC ĐẶC THÙ CHO DƯỢC ĐIỂN (BP / EP / USP / DĐVN)
    ══════════════════════════════════════════════════════
    Dược điển có cấu trúc: [Tên chuyên luận] → [Content/Definition] → [Characters] → [Identification] → [Tests] → [Assay]

    QUY TẮC BẮT BUỘC ĐỌC ĐỊNH LƯỢNG:
    - Giới hạn ĐỊNH LƯỢNG (Assay) trong BP/EP KHÔNG nằm ở mục "ASSAY" cuối bài mà nằm ở mục "Content" hoặc "Definition" ĐẦU CHUYÊN LUẬN.
    - Ví dụ BP ghi: "Content: 98.0 per cent to 102.0 per cent (anhydrous substance)"
      → gioi_han của Định lượng = "98,0% đến 102,0% (tính trên chế phẩm khan) / 98.0% to 102.0% (anhydrous substance)"
    - Mục "ASSAY" cuối chuyên luận chỉ mô tả phương pháp, không chứa giới hạn. Đừng bỏ sót phần "Content" đầu bài.

    QUY TẮC BẮT BUỘC CHO ĐỊNH TÍNH (IDENTIFICATION):
    - Dược điển thường ghi Nhóm định tính ngay đầu phần IDENTIFICATION, ví dụ: "First identification: A, B, D", "Second identification: A, C". Bạn PHẢI trích xuất thông tin phân nhóm này thành chỉ tiêu "Định tính nhóm / Identification group" với giới hạn là toàn bộ dòng phân nhóm đó (Ví dụ: "Nhóm I: Phép thử A, B, D. Nhóm II: Phép thử A, C").
    - Tách riêng biệt từng phép thử Định tính (A, B, C, D...) thành các dòng độc lập.
    - BẮT BUỘC trích xuất phép thử định tính dạng tham chiếu như "D. Water (see Tests)" hoặc "D. Loss on drying (see Tests)" thành chỉ tiêu độc lập (Ví dụ: "Định tính D (Hàm lượng nước) / Identification D (Water)" với giới hạn là "Đáp ứng phép thử Hàm lượng nước (xem mục nước) / Complies with the test for water").

    ══════════════════════════════════════════════════════
    QUY TẮC ĐẶC BIỆT QUAN TRỌNG: GIỚI HẠN CHO TỪNG PHÉP THỬ ĐỊNH TÍNH (A, B, C, D...)
    ══════════════════════════════════════════════════════
    Mỗi phép thử Định tính (A, B, C, D...) có PHƯƠNG PHÁP riêng. gioi_han của từng phép thử PHẢI mô tả cụ thể nội dung phương pháp/kết quả, KHÔNG được ghi chung chung "Đạt" hay copy từ nhóm định tính.
    VÍ DỤ CHUẨN:
    - Định tính A (Quay cực đặc trưng / Specific optical rotation): gioi_han = "Quay cực đặc trưng: +18 đến +22 (tính trên chế phẩm khan) / Specific optical rotation: +18 to +22 (anhydrous substance)"
    - Định tính B (Phổ hấp thụ hồng ngoại / Infrared absorption spectrophotometry): gioi_han = "Phổ hấp thụ hồng ngoại phù hợp với chất chuẩn CRS / Infrared absorption spectrum matches CRS reference"
    - Định tính C (Sắc ký lớp mỏng / Thin-layer chromatography): gioi_han = "Vết chính tương tự về vị trí và kích thước với vết đối chiếu (TLC) / Principal spot similar in position and size to reference spot (TLC)"
    - Định tính D (Hàm lượng nước / Water) khi dạng "see Tests": gioi_han = "Đáp ứng phép thử Hàm lượng nước (xem mục nước) / Complies with the test for water (see Tests)"
    TUYỆT ĐỐI KHÔNG được ghi gioi_han của Định tính A chỉ là "Đạt / Passes test" hay chép nội dung từ chỉ tiêu Định tính nhóm.

    CẤU TRÚC TRÍCH XUẤT TỪNG MỤC:
    - "CHARACTERS" hoặc "Appearance" → chỉ tiêu "Tính chất / Appearance"
    - "Solubility" → chỉ tiêu "Độ tan / Solubility"
    - Mỗi tiểu mục trong "IDENTIFICATION" (A, B, C...) → một chỉ tiêu riêng, gioi_han mô tả phương pháp/kết quả cụ thể
    - Mỗi tiểu mục trong "TESTS" → một chỉ tiêu riêng, lấy giới hạn ("Maximum X", "Not more than X"...)
    - Giới hạn nằm ngay đầu mục (dòng đầu tiên sau tên test), dạng: "Maximum 20 µS·cm⁻¹", "Not more than 0.2 per cent"
    """
    else:
        source_specific_rules = """
    ══════════════════════════════════════════════════════
    QUY TẮC CHUNG CHO TCCS VÀ TÀI LIỆU KHÁC
    ══════════════════════════════════════════════════════
    - Đọc từng dòng/hàng trong bảng chỉ tiêu theo nguyên tắc NEO HÀNG.
    - "ten_chi_tieu" và "gioi_han" phải cùng thuộc một chỉ tiêu, không được trộn lẫn giữa các hàng.
    - "gioi_han" là tiêu chuẩn chấp nhận (con số, mô tả), không phải kết quả "Pass/Fail".
    """

    # Dinh nghia JSON Array hint cho Gemma TRUOC khi build f-string
    _gemma_scan_hint = ""
    if "gemma" in model.lower():
        _gemma_scan_hint = """
QUAN TRONG - OUTPUT FORMAT CHO GEMMA:
Bat dau output NGAY BANG dau '[' (khong co giai thich hay markdown truoc do).
Chi xuat JSON Array thuan tuy. Khong dung ```json``` hay bat ky markdown nao.
Vi du output:
[
  {"ten_chi_tieu": "Tinh chat / Appearance", "gioi_han": "Bot trang / White powder"},
  {"ten_chi_tieu": "Dinh luong / Assay", "gioi_han": "99.0-101.0%"}
]"""

    monograph_filter = ""
    if monograph_name:
        monograph_filter = f"""
    ══════════════════════════════════════════════════════
    CHỈ QUÉT CHUYÊN LUẬN ĐÍCH: {monograph_name}
    ══════════════════════════════════════════════════════
    - Tài liệu có thể chứa nhiều chuyên luận liên tiếp hoặc ghép chung (ví dụ: chuyên luận "Folic acid hydrate" và chuyên luận "Follitropin" trong cùng một file).
    - Bạn TUYỆT ĐỐI CHỈ ĐƯỢC quét và trích xuất các chỉ tiêu thuộc về chuyên luận đích: **{monograph_name}** (hoặc chuyên luận có tên tương đương).
    - Hãy BỎ QUA HOÀN TOÀN tất cả các chỉ tiêu thuộc chuyên luận khác. Tuyệt đối không được gộp, trộn hay trích xuất bất kỳ chỉ tiêu nào của các chuyên luận không liên quan.
    """

    system_prompt = f"""{_ANTI_BILINGUAL_HEADER if not bilingual else ""}Ban la Chuyen gia phan tich tai lieu Duoc pham (QA/QC) hang dau.
    Hãy "nhìn" và đọc trực tiếp tài liệu đính kèm. Đây là tài liệu thuộc loại: **{source_label}**.
    
    NHIỆM VỤ: Liệt kê TẤT CẢ các chỉ tiêu kiểm nghiệm có trong tài liệu, kèm theo giới hạn/yêu cầu tương ứng.
    {monograph_filter}
    
    ══════════════════════════════════════════════════════
    BƯỚC 1: HIỂU CẤU TRÚC TÀI LIỆU VÀ PHÂN BIỆT ĐÚNG TÊN CHỈ TIÊU
    ══════════════════════════════════════════════════════
    {DOCUMENT_COMPONENT_TRAINING}
    {NEGATIVE_EXAMPLES}
    {source_specific_rules}
    ══════════════════════════════════════════════════════
    BƯỚC 2: QUY TẮC TRÍCH XUẤT BẮT BUỘC
    ══════════════════════════════════════════════════════
    {rule_1}
    2. GHI ĐẦY ĐỦ YÊU CẦU/GIỚI HẠN: Mỗi chỉ tiêu phải ghi rõ giới hạn/yêu cầu cụ thể (con số, mô tả trạng thái, khoảng giới hạn). PHẢI giữ nguyên các điều kiện đi kèm cực kỳ quan trọng (ví dụ: "tính trên chế phẩm khan", "tính trên chế phẩm đã làm khô", "tính trên chế phẩm khan và không chứa dung môi", "theo chế phẩm đã làm khô"). TUYỆT ĐỐI không được lược bỏ những cụm từ điều kiện này.
    3. KHÔNG bóc tách phương pháp/cách làm ở bước này — chỉ lấy TÊN CHỈ TIÊU + GIỚI HẠN/YÊU CẦU.
    4. TUYỆT ĐỐI KHÔNG BỎ SÓT: Quét toàn bộ tài liệu từ đầu đến cuối để nhặt hết tất cả các chỉ tiêu kiểm nghiệm.
       - Đặc biệt lưu ý các chỉ tiêu dưới mục "Tests" (hoặc "Phép thử") như: Barium (Bari), Iron (Sắt), Aluminium (Nhôm), Zinc (Kẽm), Lead (Chì), Arsenic (Asen), Heavy metals (Kim loại nặng), Ammonium (Amoni), Chlorides (Clorid), Sulfates (Sulfat), Nitrites, Phosphates, Fluorides...
       - Tách riêng biệt từng phép Định tính thành các dòng độc lập (ví dụ: "Định tính A", "Định tính B", "Định tính C"...).
       - Tách riêng biệt từng ion nếu chúng là các phép thử khác nhau (ví dụ: tách riêng "Giới hạn Bromide" và "Giới hạn Iodide").
       - ĐỐI VỚI CHỈ TIÊU VI SINH / GIỚI HẠN NHIỄM KHUẨN (Microbial Limits / Microbiological purity): Đây là 1 chỉ tiêu duy nhất. TUYỆT ĐỐI KHÔNG ĐƯỢC tách thành nhiều chỉ tiêu nhỏ (như không được tách riêng 'Tổng số vi khuẩn hiếu khí', 'Tổng số nấm men nấm mốc', hay 'Vi khuẩn sinh bào tử' thành các chỉ tiêu riêng). Phải gộp chung tất cả các yêu cầu giới hạn vi sinh đó vào làm một chỉ tiêu duy nhất tên là 'Giới hạn nhiễm khuẩn / Microbial limits' (hoặc 'Giới hạn vi sinh / Microbiological purity'), với cột giới hạn chứa toàn bộ các yêu cầu vi sinh đó dưới dạng danh sách xuống dòng.
    5. TUYỆT ĐỐI KHÔNG thêm từ "Dịch:", "(Dịch: ...)" hay bất kỳ chú thích dịch thuật nào khác vào nội dung kết quả. Hãy dịch tự nhiên và trả về trực tiếp.

    
    KET QUA: Tra ve DUY NHAT mot JSON Array:
    {json_example_bilingual}
    Neu tai lieu khong co chi tieu nao, tra ve mang rong: []
    {_gemma_scan_hint}
    """

    
    try:
        ai_text = call_ai_engine(
            system_prompt,
            f"Quét tất cả chỉ tiêu và giới hạn từ tài liệu {source_label}.",
            provider, model, google_keys, openai_keys,
            is_json=True, temperature=0.0, files=files_data
        )
        if not ai_text:
            return []
        # Post-process Gemma: strip markdown fences
        if "gemma" in model.lower():
            stripped = ai_text.strip()
            if stripped.startswith("```"):
                lines_r = stripped.split("\n")
                if lines_r[-1].strip() == "```":
                    lines_r = lines_r[1:-1]
                elif lines_r[0].strip().startswith("```"):
                    lines_r = lines_r[1:]
                ai_text = "\n".join(lines_r).strip()
        res = safe_json_loads(ai_text)
        
        scanned_list = []
        if isinstance(res, list):
            scanned_list = res
        elif isinstance(res, dict):
            for k, v in res.items():
                if isinstance(v, list):
                    scanned_list = v
                    break
        
        for item in scanned_list:
            if isinstance(item, dict):
                item["ten_chi_tieu"] = clean_translation_prefix(item.get("ten_chi_tieu", "")).strip()
                item["gioi_han"] = clean_translation_prefix(item.get("gioi_han", "")).strip()
        
        # ── Tầng validation ngữ nghĩa: phát hiện và sửa lỗi logic ──
        scanned_list = _validate_scanned_criteria(scanned_list)

        return scanned_list
    except Exception as e:
        import traceback
        err_msg = f"Lỗi tcnl_scan ({source_label}): {str(e)}\n{traceback.format_exc()}"
        print(err_msg)
        raise Exception(err_msg)


# =====================================================================
# TCNL MỚI: SINH PHƯƠNG PHÁP KIỂM NGHIỆM CHI TIẾT
# =====================================================================
def tcnl_generate_methods(uploaded_files_all, criteria_list, provider, model, google_keys, openai_keys, chunk_size=None, max_workers=None, bilingual=True, files_data=None):
    """Nhận danh sách chỉ tiêu đã chốt (tên + giới hạn),
    gọi AI sinh phương pháp kiểm nghiệm SOP chi tiết cho từng chỉ tiêu.
    
    criteria_list: [{"ten": "Tính chất", "gioi_han": "Bột trắng..."}, ...]
    Trả về: {"Tính chất": "Yêu cầu/Giới hạn: ...\\nCách tiến hành: ...", ...}
    
    Tối ưu: Nếu files_data đã encode sẵn, truyền vào để tránh encode lại.
    """
    if not criteria_list: return {}
    
    if files_data is None:
        files_data = prepare_file_for_ai(uploaded_files_all)
    
    # Chia batch
    is_gemma_gen = "gemma" in model.lower()
    batches = []
    if is_gemma_gen:
        # Nhóm chỉ tiêu nhạy cảm cần chạy riêng lẻ (chunk_size = 1) để tránh bị drift thông tin chéo
        sensitive_keywords = ["định tính", "identification", "tính chất", "characters", "appearance", "độ tan", "solubility", "hàm lượng nước", "water"]
        normal_criteria = []
        for c in criteria_list:
            name_lower = c["ten"].lower()
            is_sensitive = any(kw in name_lower for kw in sensitive_keywords)
            if is_sensitive:
                batches.append([c]) # Mỗi chỉ tiêu nhạy cảm chạy riêng lẻ
            else:
                normal_criteria.append(c)
        
        # Các chỉ tiêu bình thường khác chia thành các batch tối đa 3 chỉ tiêu
        c_size = 3
        for i in range(0, len(normal_criteria), c_size):
            batches.append(normal_criteria[i:i + c_size])
    else:
        if chunk_size is None or chunk_size <= 0:
            chunk_size = max(1, (len(criteria_list) + 1) // 2)
        batches = [criteria_list[i:i + chunk_size] for i in range(0, len(criteria_list), chunk_size)]
    
    if max_workers is None or max_workers <= 0:
        # Giới hạn worker dựa trên số API key thực tế (mỗi key xử lý tối đa 2 req song song)
        # Tránh bão hòa rate limit khi nhiều batch chạy đồng thời
        n_keys = len(google_keys) if google_keys else 1
        max_concurrent = min(n_keys * 2, 8)  # Tối đa 8 dù nhiều key
        safe_workers = min(max_concurrent, len(batches))
    else:
        safe_workers = min(max_workers, len(batches))
        safe_workers = max(1, safe_workers)
    
    def worker_generate(batch_criteria):
        training_instructions, criteria_master, method_library = get_dynamic_method_instructions()
        
        criteria_desc_lines = []
        for c in batch_criteria:
            c_name = c["ten"]
            c_limit = c["gioi_han"]
            
            ma_id = _match_name_to_master(c_name, criteria_master)
            if ma_id:
                c_info = criteria_master[ma_id]
                lenh_ai = c_info.get("lenh_ai_trich_xuat", "")
                tu_dien = c_info.get("tu_dien_dich", "")
                methods = c_info.get("phuong_phap_ap_dung", [])
                quy_tac = c_info.get("quy_tac_ngu_canh", {})
                
                desc = f'  - Chỉ tiêu: "{c_name}"\n'
                desc += f'    + Giới hạn chốt: {c_limit}\n'
                if lenh_ai:
                    desc += f'    + Lệnh trích xuất: {lenh_ai}\n'
                if tu_dien:
                    desc += f'    + Hướng dẫn dịch/từ điển: {tu_dien}\n'
                if quy_tac and isinstance(quy_tac, dict):
                    desc += f'    + Quy tắc phân biệt ngữ cảnh (Dạy AI):\n'
                    for src_type, rule_text in quy_tac.items():
                        if rule_text.strip():
                            desc += f'      * Khi bóc tách từ nguồn {src_type}: {rule_text.strip()}\n'
                
                if methods:
                    desc += f'    + Các phương pháp áp dụng tương ứng:\n'
                    for m_id in methods:
                        if m_id in method_library:
                            m_info = method_library[m_id]
                            desc += f'      * Phương pháp: {m_info.get("ten_phuong_phap", m_id)} (Mã: {m_id})\n'
                            cau_truc = m_info.get("cau_truc_dau_ra", {})
                            if cau_truc:
                                desc += f'      * Các thuộc tính (Tag) bắt buộc phải có:\n'
                                for tag_k, tag_desc in cau_truc.items():
                                    desc += f'        - `{tag_k}`: {tag_desc}\n'
                criteria_desc_lines.append(desc)
            else:
                criteria_desc_lines.append(f'  - Chỉ tiêu: "{c_name}"\n    + Giới hạn chốt: {c_limit}')
                
        criteria_desc = "\n".join(criteria_desc_lines)
        
        guidelines = SOP_FORMATTING_GUIDELINES
        if bilingual:
            guidelines = guidelines.replace(
                "- Dịch chi tiết 100% sang Tiếng Việt, sử dụng thuật ngữ chuyên ngành Dược. Dùng dấu xuống dòng (\\n) để phân tách rõ các mục.",
                "- Trình bày song ngữ Việt - Anh, từng bước tiến hành, điều kiện thiết bị, công thức tính toán đều phải có dòng Tiếng Việt kèm bản dịch Tiếng Anh phân cách bởi dấu gạch chéo `/` (Ví dụ: `[Câu tiếng Việt] / [English Translation]`). Sử dụng thuật ngữ chuyên ngành Dược. Dùng dấu xuống dòng (\\n) để phân tách rõ các mục."
            )
            rule_sources = (
                "2. ĐỊNH DẠNG SONG NGỮ VIỆT - ANH BẮT BUỘC CHO PHƯƠNG PHÁP: Mọi mô tả, điều kiện thiết bị, cách làm, cách pha dung dịch, và công thức tính toán... "
                "PHẢI được trình bày dưới dạng song ngữ Việt - Anh theo định dạng `[Tiếng Việt] / [English]` "
                "(Ví dụ: `Cột: C18 / Column: C18...`, `Tốc độ dòng: 1,5 ml/phút / Flow rate: 1.5 mL/min`, `Hòa tan trong 50 ml methanol / Dissolve in 50 mL of methanol`). "
                "Nếu tài liệu gốc là tiếng Anh, hãy dịch từng câu sang tiếng Việt rồi viết theo cấu trúc `[Câu tiếng Việt] / [Original English]`. "
                "Tuyệt đối không được giữ nguyên tiếng Anh không dịch, cũng không được chỉ viết tiếng Việt. Giữ nguyên công thức hóa học và hệ số K."
            )
            rule_detail = (
                "3. YÊU CẦU ĐỘ CHI TIẾT CỰC KỲ CAO VÀ RÕ RÀNG:\n"
                "Bạn PHẢI trích xuất toàn bộ quy trình chi tiết từng bước (step-by-step instructions), thông số thiết bị (cột sắc ký, detector, tốc độ dòng, thể tích tiêm...), "
                "cách cân và pha tất cả các dung dịch thử/chuẩn/đệm, và toàn bộ công thức/hệ số tính toán nếu có trong tài liệu. "
                "Tuyệt đối không tóm tắt, không lược bỏ bất kỳ thông tin kỹ thuật nào, không viết chung chung, và không ghi 'Theo yêu cầu chuyên luận'."
            )
        else:
            rule_sources = (
                "2. DỊCH VÀ TRÌNH BÀY 100% TIẾNG VIỆT BẮT BUỘC CHO PHƯƠNG PHÁP: Mọi mô tả, điều kiện thiết bị, cách làm, cách pha dung dịch, và công thức tính toán... "
                "PHẢI được dịch và trình bày hoàn toàn 100% bằng Tiếng Việt (không chứa bất kỳ từ/câu Tiếng Anh nào ngoại trừ ký hiệu hóa học, công thức toán học và đơn vị đo). "
                "Hãy dịch toàn bộ nội dung tiếng Anh từ tài liệu gốc sang tiếng Việt một cách tự nhiên và chính xác. Giữ nguyên công thức hóa học và hệ số K."
            )
            rule_detail = (
                "3. YÊU CẦU ĐỘ CHI TIẾT CỰC KỲ CAO VÀ RÕ RÀNG:\n"
                "Bạn PHẢI trích xuất toàn bộ quy trình chi tiết từng bước (step-by-step instructions), thông số thiết bị (cột sắc ký, detector, tốc độ dòng, thể tích tiêm...), "
                "cách cân và pha tất cả các dung dịch thử/chuẩn/đệm, và toàn bộ công thức/hệ số tính toán nếu có trong tài liệu. "
                "Tuyệt đối không tóm tắt, không lược bỏ bất kỳ thông tin kỹ thuật nào, không viết chung chung, và không ghi 'Theo yêu cầu chuyên luận'."
            )
        
        # Them JSON hint cho Gemma TRUOC khi build f-string
        _gemma_methods_hint = ""
        if "gemma" in model.lower():
            ex_key = batch_criteria[0]["ten"] if batch_criteria else "chi_tieu"
            _gemma_methods_hint = f"""
QUAN TRONG - OUTPUT FORMAT:
Bat dau NGAY BANG dau '{{' (khong markdown, khong giai thich).
Vi du:
{{
  "{ex_key}": "Yeu cau/Gioi han: ...\\nCach tien hanh: ..."
}}
Chi xuat JSON object thuan tuy."""

        system_prompt = f"""Ban la Chuyen gia QA/QC Duoc pham. Hay \"nhin\" truc tiep cac tai lieu dinh kem.
        
        NHIEM VU: Sinh PHUONG PHAP KIEM NGHIEM chi tiet cho DUNG cac chi tieu sau:
{criteria_desc}
        
        {DOCUMENT_COMPONENT_TRAINING}
        
        LUU Y BAT BUOC VE DICH THUAT VA DOI CHIEU SONG NGU:
        - Tai lieu dinh kem co the viet bang Tieng Anh hoac Tieng Viet. Ban phai tu dong doi chieu cac chi tieu Tieng Viet sang Tieng Anh tuong ung trong tai lieu de boc tach cach tien hanh chinh xac. Vi du:
          + "Do dan dien" tuong ung voi "Conductivity"
          + "Duong khu" tuong ung voi "Reducing sugars" hoac "Reducing substances"
          + "Tap chat lien quan" tuong ung voi "Related substances" hoac "Related substance" hoac "Impurity"
          + "Tro sulfat" tuong ung voi "Sulfated ash"
          + "Kim loai nang" tuong ung voi "Heavy metals"
          + "Mat khoi luong do say/lam kho" tuong ung voi "Loss on drying"
          + "Do trong va mau sac" tuong ung voi "Appearance of solution" hoac "Clarity and color of solution"
          + "Tinh chat" / "Cam quan" tuong ung voi "Appearance" hoac "Characters"
          + "Dinh luong" tuong ung voi "Assay"
          + "Ham luong nuoc" tuong ung voi "Water" hoac "Water content"
          + "Gioi han acid - kiem" tuong ung voi "Acidity or alkalinity"
          + "Do tan" tuong ung voi "Solubility"
          + "Dinh tinh" tuong ung voi "Identification"

        QUY TAC:
        1. Voi moi chi tieu, tim cach lam/phuong phap thu trong tai lieu dinh kem va bien tap thanh 1 doan van SOP (dung \\n de xuong dong) theo dung phong cach va dinh dang quy dinh duoi day:
        
        {guidelines}
        
        {rule_sources}
        
        {rule_detail}
        
        4. BAT BUOC TRICH XUAT NOI DUNG PHUONG PHAP: Neu trong tai lieu co mo ta cach tien hanh/chuan bi dung dich/do dac cho chi tieu, ban PHAI boc tach chi tiet toan bo cach lam. Tuyet doi khong luoi bieng ghi "Theo yeu cau chuyen luan" neu thuc su tai lieu co noi dung huong dan cach lam. Chi ghi "Theo yeu cau chuyen luan" khi va chi khi tai lieu hoan toan khong co huong dan nao cho chi tieu do.
        
        5. QUY TAC BAN DAU PHUONG PHAP (QUAN TRONG CHO DO CHINH XAC):
        Dong dau tien cua moi phuong phap PHAI neu ro TEN PHUONG PHAP / TEN CHI TIEU bang tieng Anh:
          - Chi tieu "Dinh luong / Assay": dong dau = "Phuong phap: Dinh luong bang sac ky long (HPLC) / Method: Assay by Liquid Chromatography (HPLC)" (hoac phuong phap tuong duong)
          - Chi tieu "Dinh tinh B" (pho IR): dong dau = "Phuong phap: Pho hap thu hong ngoai / Method: Infrared absorption spectrophotometry"
          - Chi tieu "Dinh tinh C" (TLC): dong dau = "Phuong phap: Sac ky lop mong / Method: Thin-layer chromatography (TLC)"
          - Chi tieu "Tap chat lien quan / Related substances": dong dau = "Phuong phap: Sac ky long (HPLC) / Method: Liquid chromatography (HPLC)"
          - Chi tieu "Ham luong nuoc / Water": dong dau = "Phuong phap: Chuan do Karl Fischer (2.5.12) / Method: Karl Fischer titration"
          - Chi tieu "Tro sulfat / Sulfated ash": dong dau = "Phuong phap: Tro sulfat (2.4.14) / Method: Sulfated ash (2.4.14)"
        Viec neu ten phuong phap NGAY TU DAU giup nguoi dung nhan biet ngay phuong phap ap dung.
        
        {training_instructions}

        KET QUA: Tra ve DUY NHAT mot JSON object.
        Moi key la TEN chi tieu (chinh xac nhu danh sach tren), value la doan van SOP.
        {_gemma_methods_hint}
        """
        
        try:
            ai_text = call_ai_engine(
                system_prompt,
                "Sinh phuong phap kiem nghiem chi tiet.",
                provider, model, google_keys, openai_keys,
                is_json=True, temperature=0.0, files=files_data
            )
            if not ai_text: return {}
            # Post-process Gemma: strip markdown fences
            if "gemma" in model.lower():
                stripped_m = ai_text.strip()
                if stripped_m.startswith("```"):
                    lines_m = stripped_m.split("\n")
                    if lines_m[-1].strip() == "```":
                        lines_m = lines_m[1:-1]
                    elif lines_m[0].strip().startswith("```"):
                        lines_m = lines_m[1:]
                    ai_text = "\n".join(lines_m).strip()
            raw_res = safe_json_loads(ai_text)
            if not isinstance(raw_res, dict):
                raw_res = {}
            cleaned_res = {}
            _SENTINEL_VALUES = {"XOA_HANG", "XOA_DONG", "N/A", "n/a", "null", "NULL", "none", "NONE", "undefined"}
            for k, v in raw_res.items():
                val_text = extract_sop_text_from_value(v)
                val_clean = clean_translation_prefix(val_text).strip()
                # Loc bo cac gia tri sentinel / garbage
                if val_clean.strip().upper() in _SENTINEL_VALUES or val_clean.strip() in ("", "{}"):
                    val_clean = ""
                cleaned_res[clean_translation_prefix(k).strip()] = val_clean

            # Gemma Retry: nếu bất kỳ chi tiêu nào thiếu hoặc quá ngắn (<100 ký tự) -&gt; retry
            if "gemma" in model.lower():
                missing = [c["ten"] for c in batch_criteria
                           if not cleaned_res.get(c["ten"], "").strip() or
                           len(cleaned_res.get(c["ten"], "")) < 100]
                if len(missing) > 0 and len(missing) > len(batch_criteria) * 0.3:
                    print(f"[TCNL Retry] {len(missing)}/{len(batch_criteria)} methods trong -> retry...")
                    retry_crit_desc = "\n".join(
                        [f'  - "{c["ten"]}": limit={c["gioi_han"]}'
                         for c in batch_criteria if c["ten"] in missing]
                    )
                    ex_k = batch_criteria[0]["ten"] if batch_criteria else "chi_tieu"
                    lang_instruction = ""
                    if bilingual:
                        lang_instruction = (
                            "BẮT BUỘC TRÌNH BÀY SONG NGỮ VIỆT - ANH: Mọi mô tả, câu viết, cách tiến hành, cách chuẩn bị dung dịch phải ở dạng "
                            "`[Tiếng Việt] / [Tiếng Anh]` phân cách bởi dấu gạch chéo `/`. Ví dụ: `Cân 1,0 g mẫu / Weigh 1.0 g of sample.`"
                        )
                    else:
                        lang_instruction = (
                            "BẮT BUỘC DỊCH VÀ TRÌNH BÀY 100% TIẾNG VIỆT: Mọi mô tả, cách tiến hành, cách pha dung dịch phải dịch hoàn toàn "
                            "sang Tiếng Việt thuần túy, không chứa câu tiếng Anh (trừ ký hiệu hóa học, công thức toán học và đơn vị đo)."
                        )

                    retry_prompt = f"""CRITICAL: Respond with ONLY a valid JSON object starting with '{{'.

Bạn là Chuyên gia QA/QC Dược phẩm. Hãy đọc kỹ tài liệu đính kèm để trích xuất quy trình kiểm nghiệm.

Sinh quy trình SOP chi tiết cho các chỉ tiêu sau:
{retry_crit_desc}

Với mỗi chỉ tiêu (dùng đúng tên làm key), cung cấp toàn bộ quy trình kiểm nghiệm chi tiết.
Yêu cầu bao gồm: cách chuẩn bị dung dịch thử/dung dịch chuẩn/đệm, thông số thiết bị, các bước tiến hành chi tiết từng bước, và công thức/hệ số tính toán nếu có.

QUY TẮC NGÔN NGỮ QUAN TRỌNG:
{lang_instruction}

OUTPUT MUST start immediately with '{{', no markdown, no explanation:
{{
  "{ex_k}": "Quy trinh..."
}}"""
                    try:
                        retry_text = call_ai_engine(
                            retry_prompt,
                            "Generate test methods.",
                            provider, model, google_keys, openai_keys,
                            is_json=True, temperature=0.0, files=files_data
                        )
                        if retry_text:
                            # Strip markdown from retry too
                            rt_stripped = retry_text.strip()
                            if rt_stripped.startswith("```"):
                                rt_lines = rt_stripped.split("\n")
                                if rt_lines[-1].strip() == "```":
                                    rt_lines = rt_lines[1:-1]
                                elif rt_lines[0].strip().startswith("```"):
                                    rt_lines = rt_lines[1:]
                                retry_text = "\n".join(rt_lines).strip()
                            retry_res = safe_json_loads(retry_text)
                            if isinstance(retry_res, dict):
                                for rk, rv in retry_res.items():
                                    rv_text = extract_sop_text_from_value(rv)
                                    rv_clean = clean_translation_prefix(rv_text).strip()
                                    # Loc bo gia tri sentinel / garbage trong retry
                                    if rv_clean.strip().upper() in _SENTINEL_VALUES or rv_clean.strip() in ("", "{}"):
                                        rv_clean = ""
                                    if rv_clean and len(rv_clean) > 30:
                                        clean_k = clean_translation_prefix(rk).strip()
                                        cleaned_res[clean_k] = rv_clean
                                        print(f"[TCNL Retry] Phuc hoi: {clean_k[:40]}")
                    except Exception as re_err:
                        print(f"[TCNL Retry] Loi: {re_err}")

            return cleaned_res
        except Exception as e:
            return {c["ten"]: f"LOI: {str(e)}" for c in batch_criteria}
    
    merged = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=safe_workers) as executor:
        futures = [executor.submit(worker_generate, batch) for batch in batches]
        for future in concurrent.futures.as_completed(futures):
            try:
                merged.update(future.result())
            except Exception as e:
                print(f"Lỗi batch method generation: {str(e)}")
    
    return merged

def tcnl_extract_monograph_name(uploaded_files, provider, model, google_keys, openai_keys, files_data=None):
    """
    Quét tài liệu Dược điển đính kèm để trích xuất tên chuyên luận gốc tiếng Anh/Việt
    (ví dụ: 'Maltitol', 'Crystalline Maltitol - F', 'Pyridoxine Hydrochloride').
    
    Tối ưu: Nếu files_data đã encode sẵn, truyền vào để tránh encode lại.
    Giới hạn dữ liệu gửi đi khoảng 4000 ký tự đầu tiên để tối ưu thời gian xử lý của AI.
    """
    if files_data is None:
        if not uploaded_files: return ""
        files_data = prepare_file_for_ai(uploaded_files)
    if not files_data: return ""
    
    # Tối ưu hóa: Trích xuất tên chuyên luận chỉ cần xem phần đầu tài liệu.
    # Text: giới hạn 4000 ký tự. PDF: giới hạn ~15KB đầu để giảm thời gian xử lý AI.
    truncated_files_data = []
    for f in files_data:
        mime = f.get("mime_type", "")
        if mime == "text/plain":
            try:
                import base64
                raw_text = base64.b64decode(f["data"]).decode("utf-8", errors="ignore")
                truncated_text = raw_text[:4000]
                truncated_files_data.append({
                    "file_name": f["file_name"],
                    "mime_type": mime,
                    "data": base64.b64encode(truncated_text.encode("utf-8")).decode("utf-8")
                })
            except Exception as tr_err:
                print(f"Lỗi rút gọn text: {tr_err}")
                truncated_files_data.append(f)
        elif mime == "application/pdf":
            # PDF: giu nguyen (khong cat bytes vi PDF la nhi phan, cat se hong file)
            # Toc do duoc cai thien bang cach dung prompt ngan gon hon
            truncated_files_data.append(f)
        else:
            truncated_files_data.append(f)
            
    system_prompt = """Read the attached pharmacopoeia document. What is the monograph title (the active ingredient/substance name at the top)?
    Reply with ONLY the monograph name, nothing else. Examples: "Maltitol", "Folic acid hydrate", "Pyridoxine Hydrochloride".
    If not found, reply with empty string.
    """
    
    try:
        res = call_ai_engine(
            system_prompt,
            "Trích xuất tên chuyên luận từ Dược điển.",
            provider, model, google_keys, openai_keys,
            is_json=False, temperature=0.0, files=truncated_files_data
        )
        if res:
            val = res.strip().replace('"', '').replace("'", "")
            return val if val != '""' else ""
        return ""
    except Exception as e:
        print(f"Lỗi trích xuất tên chuyên luận: {str(e)}")
        return ""