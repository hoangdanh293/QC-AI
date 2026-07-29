import streamlit as st
import json
import os
import time
from datetime import datetime
from core.doc_processor import invalidate_instruction_cache

STYLE_LIB_FILE = "style_examples_library.json"
PERSONAL_STYLE_FILE = "personal_style.json"


def load_json_safe(filepath, default=None):
    if default is None:
        default = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_json_safe(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    # [E1] Xóa cache khi file phong cách hoặc style examples thay đổi
    if "personal_style" in filepath or "style_examples" in filepath:
        invalidate_instruction_cache()


def _gen_entry_id(ten_nguyen_lieu):
    import re, unicodedata, time as _time
    name = ten_nguyen_lieu.lower().strip()
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    name = re.sub(r'[^a-z0-9 ]', '', name)
    name = re.sub(r'\s+', '_', name)[:30]
    ts = str(int(_time.time()))[-6:]
    return f"{name}_{ts}"


def _parse_ai_json(result, expected_type="dict"):
    """
    Phân tích JSON từ kết quả AI một cách an toàn.
    Tự động tìm và cắt phần JSON trong kết quả kể cả khi có text thừa.
    expected_type: 'dict' hoặc 'array'
    """
    if not result or not result.strip():
        return None

    result_clean = result.strip()

    if expected_type == "array":
        start = result_clean.find('[')
        end = result_clean.rfind(']')
    else:
        start = result_clean.find('{')
        end = result_clean.rfind('}')

    if start != -1 and end != -1 and end > start:
        result_clean = result_clean[start:end + 1]

    try:
        return json.loads(result_clean)
    except json.JSONDecodeError:
        return None


# =============================
# TAB 1: PHONG CÁCH CÁ NHÂN
# =============================

def render_tab_phong_cach():
    style_data = load_json_safe(PERSONAL_STYLE_FILE, {
        "tieu_de": "Phong Cách QA/QC Cá Nhân",
        "mo_ta_chung": "",
        "trang_thai_phan_tich": "chua_phan_tich",
        "ngay_cap_nhat": "",
        "so_ho_so_da_hoc": 0,
        "phong_cach_rut_ra": {
            "quy_tac_viet_lach": [],
            "cum_tu_uu_dung": {},
            "cau_truc_hplc": "",
            "cau_truc_tlc": "",
            "cau_truc_chuan_do": "",
            "cau_truc_dinh_tinh": "",
            "cach_viet_gioi_han": "",
            "cach_bat_dau_sop": "",
            "ghi_chu_them": ""
        }
    })

    phong_cach = style_data.get("phong_cach_rut_ra", {})
    so_ho_so = style_data.get("so_ho_so_da_hoc", 0)
    ngay_cap_nhat = style_data.get("ngay_cap_nhat", "")

    if so_ho_so > 0:
        st.success(f"✅ **Đã học từ {so_ho_so} hồ sơ mẫu** | Cập nhật lần cuối: {ngay_cap_nhat}")
    else:
        st.info("💡 **Chưa có dữ liệu phong cách.** Hãy sang tab **'Thư Viện Hồ Sơ Mẫu'** để upload hồ sơ mẫu và bấm 'Phân tích phong cách'.")

    st.markdown("---")

    col_title, col_btn = st.columns([3, 1])
    with col_title:
        st.markdown("#### 🧠 Phong Cách Cá Nhân (AI Đã Rút Ra)")
        st.caption("AI tự động phân tích các hồ sơ mẫu và rút ra phong cách. Bạn có thể chỉnh sửa thêm bên dưới.")
    with col_btn:
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        if st.button("🔄 Phân tích lại", key="btn_analyze_style", help="AI phân tích lại toàn bộ hồ sơ mẫu để cập nhật phong cách"):
            _ai_analyze_style()

    with st.form("form_edit_style"):
        mo_ta_chung = st.text_area(
            "📌 Mô tả tổng quát phong cách (AI sẽ dùng để định hướng)",
            value=style_data.get("mo_ta_chung", ""),
            height=100,
            placeholder="Ví dụ: Phong cách QA/QC chuyên nghiệp, trình bày rõ ràng, chi tiết, dùng ký hiệu ✓ cho điều kiện sắc ký..."
        )

        st.markdown("**📋 Quy tắc viết lách bắt buộc (mỗi dòng 1 quy tắc)**")
        quy_tac_list = phong_cach.get("quy_tac_viet_lach", [])
        quy_tac_str = "\n".join(quy_tac_list) if quy_tac_list else ""
        quy_tac_input = st.text_area(
            "Quy tắc viết lách",
            value=quy_tac_str,
            height=140,
            label_visibility="collapsed",
            placeholder="Ví dụ:\nLuôn bắt đầu SOP bằng 'Theo chuyên luận X - Dược điển'\nDùng dấu ✓ cho điều kiện sắc ký HPLC\nViết giới hạn dạng: 'Không quá X% / Not more than X%'"
        )

        st.markdown("**✍️ Cách bắt đầu nội dung SOP**")
        cach_bat_dau = st.text_area(
            "Cách bắt đầu SOP",
            value=phong_cach.get("cach_bat_dau_sop", ""),
            height=80,
            label_visibility="collapsed",
            placeholder="Ví dụ: Theo chuyên luận {ten_nguyen_lieu} - {duoc_dien}"
        )

        st.markdown("**📏 Cách viết yêu cầu/giới hạn**")
        cach_gioi_han = st.text_area(
            "Cách viết giới hạn",
            value=phong_cach.get("cach_viet_gioi_han", ""),
            height=80,
            label_visibility="collapsed",
            placeholder="Ví dụ: Yêu cầu: Không quá X% / Requirement: Not more than X%."
        )

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**🔬 Cấu trúc trình bày HPLC**")
            cau_truc_hplc = st.text_area(
                "HPLC",
                value=phong_cach.get("cau_truc_hplc", ""),
                height=160,
                label_visibility="collapsed",
                placeholder="A. Điều kiện sắc ký:\n✓ Cột: ...\n✓ Đầu dò: ...\n✓ Tốc độ dòng: ..."
            )

            st.markdown("**🔬 Cấu trúc trình bày TLC**")
            cau_truc_tlc = st.text_area(
                "TLC",
                value=phong_cach.get("cau_truc_tlc", ""),
                height=120,
                label_visibility="collapsed",
                placeholder="A. Điều kiện:\n✓ Bản mỏng: ...\n✓ Pha động: ..."
            )
        with col_b:
            st.markdown("**🔬 Cấu trúc trình bày Chuẩn độ**")
            cau_truc_chuan_do = st.text_area(
                "Chuẩn độ",
                value=phong_cach.get("cau_truc_chuan_do", ""),
                height=140,
                label_visibility="collapsed",
                placeholder="Cân chính xác khoảng... mẫu...\nHòa tan trong...\nChuẩn độ bằng..."
            )

            st.markdown("**🔬 Cấu trúc trình bày Định tính**")
            cau_truc_dinh_tinh = st.text_area(
                "Định tính",
                value=phong_cach.get("cau_truc_dinh_tinh", ""),
                height=140,
                label_visibility="collapsed",
                placeholder="A. Phổ hấp thụ IR:...\nB. Phổ hấp thụ UV:..."
            )

        st.markdown("**📝 Ghi chú bổ sung cho AI**")
        ghi_chu = st.text_area(
            "Ghi chú",
            value=phong_cach.get("ghi_chu_them", ""),
            height=80,
            label_visibility="collapsed",
            placeholder="Các lưu ý đặc biệt, ngoại lệ, hay yêu cầu riêng..."
        )

        saved = st.form_submit_button("💾 Lưu Phong Cách", type="primary")

        if saved:
            quy_tac_list_new = [line.strip() for line in quy_tac_input.split("\n") if line.strip()]
            new_style = {
                "tieu_de": "Phong Cách QA/QC Cá Nhân",
                "mo_ta_chung": mo_ta_chung.strip(),
                "trang_thai_phan_tich": style_data.get("trang_thai_phan_tich", "thu_cong"),
                "ngay_cap_nhat": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "so_ho_so_da_hoc": so_ho_so,
                "phong_cach_rut_ra": {
                    "quy_tac_viet_lach": quy_tac_list_new,
                    "cum_tu_uu_dung": phong_cach.get("cum_tu_uu_dung", {}),
                    "cau_truc_hplc": cau_truc_hplc.strip(),
                    "cau_truc_tlc": cau_truc_tlc.strip(),
                    "cau_truc_chuan_do": cau_truc_chuan_do.strip(),
                    "cau_truc_dinh_tinh": cau_truc_dinh_tinh.strip(),
                    "cach_viet_gioi_han": cach_gioi_han.strip(),
                    "cach_bat_dau_sop": cach_bat_dau.strip(),
                    "ghi_chu_them": ghi_chu.strip()
                }
            }
            save_json_safe(PERSONAL_STYLE_FILE, new_style)
            st.success("✅ Đã lưu phong cách thành công! AI sẽ áp dụng ngay trong lần tạo hồ sơ tiếp theo.")
            time.sleep(1)
            st.rerun()


def _ai_analyze_style():
    """
    AI phân tích SÂU toàn bộ hồ sơ mẫu để rút ra phong cách chuẩn.
    - Phân tích TẤT CẢ hồ sơ (không giới hạn cứng).
    - Lấy TẤT CẢ vi_du_chi_tiet (không giới hạn số chỉ tiêu).
    - Mỗi chỉ tiêu lấy tối đa 2000 ký tự.
    - Rút ra các trường mới: quy_tac_boc_tach, tu_dien_thuat_ngu, mau_ket_luan_chi_tieu.
    """
    lib_data = load_json_safe(STYLE_LIB_FILE, {})
    entries = {k: v for k, v in lib_data.items() if k != "_meta" and isinstance(v, dict)}

    if not entries:
        st.error("❌ Chưa có hồ sơ mẫu nào trong thư viện! Hãy upload hồ sơ mẫu trước.")
        return

    # Ưu tiên mẫu vàng trước, sau đó lấy tất cả
    sorted_entries = sorted(
        entries.items(),
        key=lambda x: (0 if x[1].get("la_mau_vang", False) else 1, x[1].get("ngay_tao", ""))
    )

    with st.spinner(f"🧠 AI đang phân tích SÂU {len(entries)} hồ sơ mẫu..."):
        try:
            from core.ai_handler import call_ai_engine

            # Thu thập nội dung mẫu: TOÀN BỘ hồ sơ, TOÀN BỘ chỉ tiêu
            sample_content = []
            tong_chi_tieu = 0
            for entry_id, entry_data in sorted_entries:
                ten_nl = entry_data.get("ten_nguyen_lieu", entry_id)
                loai_tl = entry_data.get("loai_tai_lieu", "")
                la_vang = "⭐ MẪU VÀNG" if entry_data.get("la_mau_vang") else "📄 Tham chiếu"
                vi_du = entry_data.get("vi_du_chi_tiet", [])

                if vi_du:
                    sample_content.append(f"\n{'='*60}")
                    sample_content.append(f"[{la_vang}] HỒ SƠ: {ten_nl} ({loai_tl})")
                    sample_content.append('='*60)
                    for vd in vi_du:  # TOÀN BỘ chỉ tiêu
                        ct = vd.get("ten_chi_tieu", "")
                        nd = vd.get("noi_dung_mau", "")
                        if ct and nd:
                            tong_chi_tieu += 1
                            # Lấy 2000 ký tự/chỉ tiêu thay vì 800
                            nd_crop = nd[:2000] + ("..." if len(nd) > 2000 else "")
                            sample_content.append(f"\n--- Chỉ tiêu: {ct} ---\n{nd_crop}")
                else:
                    # Fallback: nội dung đầy đủ
                    noi_dung = entry_data.get("noi_dung_day_du", entry_data.get("noi_dung_tom_tat", ""))
                    if noi_dung:
                        sample_content.append(f"\n{'='*60}")
                        sample_content.append(f"[{la_vang}] HỒ SƠ: {ten_nl} ({loai_tl})")
                        sample_content.append(noi_dung[:4000])

            if not sample_content:
                st.warning("⚠️ Hồ sơ mẫu chưa có nội dung. Hãy upload hồ sơ từ tab 'Thư Viện Hồ Sơ Mẫu'.")
                return

            st.info(f"📊 Thu thập được **{tong_chi_tieu} chỉ tiêu** từ **{len(entries)} hồ sơ** để phân tích.")

            samples_str = "\n".join(sample_content)
            # Giới hạn tổng độ dài để tránh quá tải API
            if len(samples_str) > 60000:
                samples_str = samples_str[:60000] + "\n[...Đã cắt bớt để phù hợp với giới hạn API...]"

            prompt = f"""Dưới đây là nội dung THỰC TẾ từ {len(entries)} hồ sơ kiểm nghiệm mẫu đã được phê duyệt ({tong_chi_tieu} chỉ tiêu tổng cộng):

{samples_str}

Hãy phân tích KỸ LƯỠNG và rút ra phong cách trình bày chuyên nghiệp theo cấu trúc JSON sau:
{{
    "mo_ta_chung": "Mô tả tổng quát phong cách viết hồ sơ trong 3-5 câu, nêu rõ đặc trưng nổi bật",
    "quy_tac_viet_lach": [
        "Quy tắc 1: Bắt buộc bắt đầu mỗi chỉ tiêu bằng 'Theo chuyên luận X - Dược điển'",
        "Quy tắc 2: ...",
        "Ít nhất 10 quy tắc cụ thể"
    ],
    "cum_tu_uu_dung": {{
        "bat_dau_chi_tieu": "Theo chuyên luận [TÊN NL] - [DƯỢC ĐIỂN]",
        "ket_luan_khong_qua": "Yêu cầu: Không quá X% / Not more than X%.",
        "ket_luan_khoang": "Yêu cầu: Từ X đến Y / From X to Y.",
        "ten_cum_tu_khac": "nội dung cụm từ tương ứng"
    }},
    "cau_truc_hplc": "Mô tả cấu trúc HPLC chi tiết: A. Điều kiện... B. Nội dung...",
    "cau_truc_tlc": "Mô tả cấu trúc TLC nếu có",
    "cau_truc_chuan_do": "Mô tả cấu trúc chuẩn độ nếu có",
    "cau_truc_dinh_tinh": "Mô tả cấu trúc định tính (gộp A, B, C... vào 1 chỉ tiêu)",
    "cach_viet_gioi_han": "Mô tả CHÍNH XÁC cách viết yêu cầu/giới hạn đặc trưng từ hồ sơ mẫu",
    "cach_bat_dau_sop": "Cách bắt đầu nội dung SOP đặc trưng",
    "quy_tac_boc_tach": "Các quy tắc nhận diện và phân tách chỉ tiêu (ví dụ: Định tính là 1 chỉ tiêu dù có A,B,C; Giới hạn nhiễm khuẩn là 1 chỉ tiêu)",
    "tu_dien_thuat_ngu": {{
        "Tiến hành": "Cách tiến hành / Procedure",
        "Yêu cầu": "Tiêu chuẩn chấp nhận / Acceptance criteria",
        "Dung dịch thử": "Test solution",
        "Dung dịch chuẩn": "Reference/Standard solution"
    }},
    "mau_ket_luan_chi_tieu": "Yêu cầu: {{limit_vn}} / {{limit_en}}.",
    "ghi_chu_them": "Ghi chú bổ sung, lưu ý đặc biệt, ngoại lệ"
}}

Trả về DUY NHẤT JSON object trên, không giải thích."""

            result = call_ai_engine(
                "Bạn là chuyên gia QA/QC Dược phẩm với 10 năm kinh nghiệm viết và phê duyệt hồ sơ kiểm nghiệm. "
                "Hãy phân tích chính xác và chi tiết phong cách từ các ví dụ thực tế được cung cấp.",
                prompt,
                "Google API",
                "gemma-4-31b-it",
                is_json=True,
                temperature=0.0
            )

            analyzed = _parse_ai_json(result, "dict")
            if not analyzed or not isinstance(analyzed, dict):
                st.error("❌ AI không trả về kết quả hợp lệ. Vui lòng thử lại.")
                return

            new_style = {
                "tieu_de": "Phong Cách QA/QC Cá Nhân",
                "mo_ta_chung": analyzed.get("mo_ta_chung", ""),
                "trang_thai_phan_tich": "da_phan_tich",
                "ngay_cap_nhat": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "so_ho_so_da_hoc": len(entries),
                "tong_chi_tieu_hoc": tong_chi_tieu,
                "phong_cach_rut_ra": {
                    "quy_tac_viet_lach": analyzed.get("quy_tac_viet_lach", []),
                    "cum_tu_uu_dung": analyzed.get("cum_tu_uu_dung", {}),
                    "cau_truc_hplc": analyzed.get("cau_truc_hplc", ""),
                    "cau_truc_tlc": analyzed.get("cau_truc_tlc", ""),
                    "cau_truc_chuan_do": analyzed.get("cau_truc_chuan_do", ""),
                    "cau_truc_dinh_tinh": analyzed.get("cau_truc_dinh_tinh", ""),
                    "cach_viet_gioi_han": analyzed.get("cach_viet_gioi_han", ""),
                    "cach_bat_dau_sop": analyzed.get("cach_bat_dau_sop", ""),
                    "quy_tac_boc_tach": analyzed.get("quy_tac_boc_tach", ""),
                    "tu_dien_thuat_ngu": analyzed.get("tu_dien_thuat_ngu", {}),
                    "mau_ket_luan_chi_tieu": analyzed.get("mau_ket_luan_chi_tieu", ""),
                    "ghi_chu_them": analyzed.get("ghi_chu_them", "")
                }
            }
            save_json_safe(PERSONAL_STYLE_FILE, new_style)
            st.success(
                f"✅ AI đã phân tích xong **{len(entries)} hồ sơ** ({tong_chi_tieu} chỉ tiêu) và cập nhật phong cách!\n"
                f"Gồm {len(analyzed.get('quy_tac_viet_lach', []))} quy tắc viết lách."
            )
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"❌ Lỗi phân tích: {str(e)}")


# =============================
# HÀM BÓC TÁCH TOÀN BỘ CHỈ TIÊU
# =============================

# ── Nhúng toàn bộ quy tắc SOP vào System Prompt bóc tách ──
_SOP_RULES_FOR_EXTRACT = """
QUY TẮC TRÌNH BÀY NỘI DUNG BẮT BUỘC (áp dụng cho trường noi_dung_mau):
1. Mỗi chỉ tiêu PHẢI bắt đầu bằng nguồn tham chiếu: "Theo chuyên luận [Tên NL] - [Dược điển]" hoặc "Theo [Dược điển] - [Mã chuyên luận]"
2. Kết thúc mỗi chỉ tiêu bằng: "Yêu cầu: [Giới hạn tiếng Việt] / [Giới hạn tiếng Anh]."
3. Dùng dấu gạch đầu dòng `-` cho từng bước thao tác.
4. Dùng dấu `+` cho từng loại dung dịch cần pha.
5. Với HPLC: chia 2 phần A (Điều kiện sắc ký, dùng ✓) và B (Nội dung chi tiết).
6. KHÔNG ghi "Kết quả:" hay "Kết quả" vào noi_dung_mau — các ô này đã có trong template.
7. KHÔNG bỏ sót: công thức tính, số liệu, điều kiện nhiệt độ, thể tích, nồng độ.
8. Giữ nguyên tên hoá chất IUPAC/USP: Acetonitrile, Methanol, Phosphoric acid... (không dịch thành tiếng Việt).
9. Công thức tính: ghi sau "- Công thức tính:" và giải thích từng ký hiệu dưới dạng danh sách.
10. Nếu nội dung chunk không đủ để biết giới hạn → ghi "Yêu cầu: Theo chuyên luận."
"""

SYSTEM_PROMPT_EXTRACT = """Bạn là chuyên gia QA/QC Dược có kinh nghiệm phân tích và viết hồ sơ kiểm nghiệm.
Nhiệm vụ: Bóc tách nội dung SOP đầy đủ của TỪNG VÀ TẤT CẢ chỉ tiêu kiểm nghiệm có trong hồ sơ thực tế.
Trả về DUY NHẤT JSON array. Không giải thích, không thêm text ngoài JSON.
""" + _SOP_RULES_FOR_EXTRACT

PROMPT_EXTRACT_TEMPLATE = """Dưới đây là nội dung hồ sơ kiểm nghiệm của {ten_nl} (đoạn {chunk_so}/{tong_chunk}):

{noi_dung}

═══════════ YÊU CẦU BẮT BUỘC ═══════════

1. ĐỊNH TÍNH (IDENTIFICATION / QUALITATIVE TESTS):
   ⚠️ QUAN TRỌNG: "Định tính" hoặc "Identification" là MỘT chỉ tiêu DUY NHẤT.
   - Các phần A, B, C, D, E, F... là CÁC PHẦN CON THUỘC chỉ tiêu Định tính — KHÔNG phải chỉ tiêu riêng lẻ.
   - Phải gộp TOÀN BỘ nội dung A + B + C + D... vào ÔNG NỘI DUNG DUY NHẤT của chỉ tiêu "Định tính".
   - Ví dụ đúng: ten_chi_tieu = "Định tính", noi_dung_mau = "A. Phổ IR...\\nB. Phổ UV...\\nC. Phản ứng sulfat..."
   - Ví dụ SAI: tạo 3 entry riêng "Định tính A", "Định tính B", "Định tính C" → KHÔNG được làm vậy.

2. GIỚI HẠN NHIỄM KHUẨN (MICROBIAL LIMITS / MICROBIOLOGICAL PURITY):
   ⚠️ QUAN TRỌNG: "Giới hạn nhiễm khuẩn" (hoặc "Giới hạn vi sinh") là MỘT chỉ tiêu DUY NHẤT.
   - Các yêu cầu con như 'Tổng số vi sinh vật hiếu khí/VSV đếm được', 'Tổng số nấm men và nấm mốc', 'E. coli', 'Salmonella', v.v. là CÁC PHẦN CON của chỉ tiêu Giới hạn nhiễm khuẩn — KHÔNG phải các chỉ tiêu riêng lẻ.
   - Phải gộp TOÀN BỘ các yêu cầu vi sinh đó vào làm một chỉ tiêu duy nhất tên là "Giới hạn nhiễm khuẩn".
   - Ví dụ đúng: ten_chi_tieu = "Giới hạn nhiễm khuẩn", noi_dung_mau = "Theo DĐVN – 13.6\\nYêu cầu:\\n1. Tổng số VSV...\\n2. Tổng số nấm men...\\n3. Không có vi khuẩn..."
   - Ví dụ SAI: tạo các entry riêng "Tổng số VSV", "Tổng số nấm men", "E. coli" → KHÔNG được làm vậy.

3. TẤT CẢ CÁC CHỈ TIÊU KHÁC (BẮT BUỘC KHÔNG BỎ SÓT):
   - Phải trích xuất đầy đủ TẤT CẢ các chỉ tiêu xuất hiện trong hồ sơ (bao gồm cả Cảm quan, Tính chất, Độ tan, pH, Giới hạn nhiễm khuẩn, Hàm lượng nước, Kim loại nặng, Giới hạn tạp chất, Clorid, Sulfat, Sắt, Định lượng...).
   - Trích xuất TOÀN BỘ nội dung: phương pháp thử, cách chuẩn bị hóa chất/thiết bị, cách pha dung dịch, bước tiến hành thực nghiệm, yêu cầu kỹ thuật và công thức tính toán.
   - Không bỏ sót bất kỳ chỉ tiêu nào có trong bảng hoặc nội dung tài liệu mẫu.

4. FORMAT TRẢ VỀ (DUY NHẤT JSON array, không text thừa):
[
  {{"ten_chi_tieu": "Định tính", "noi_dung_mau": "A. Phổ hấp thụ IR...\\nB. Thêm vào..."}},
  {{"ten_chi_tieu": "Cảm quan", "noi_dung_mau": "Kiểm tra bằng mắt thường...\\nBột trắng..."}},
  {{"ten_chi_tieu": "Giới hạn nhiễm khuẩn", "noi_dung_mau": "Theo DĐVN – 13.6\\nYêu cầu:\\n1. Tổng số VSV đếm được < 100 CFU/g\\n2. Tổng số nấm men...\\n3. Không có vi khuẩn..."}},
  {{"ten_chi_tieu": "Định lượng", "noi_dung_mau": "Theo chuyên luận...\\n$\\\\displaystyle ...$"}}
]

Nếu đoạn này không có chỉ tiêu nào phù hợp, trả về: []"""


def _merge_results(all_results, seen_names, parsed_items, criteria_master):
    """Gộp kết quả từ 1 chunk vào all_results (dùng chung cho tuần tự và song song)."""
    from core.doc_processor import match_criteria_id_by_name
    for item in parsed_items:
        ten = str(item.get("ten_chi_tieu", "")).strip()
        nd = str(item.get("noi_dung_mau", "")).strip()
        if not ten or not nd:
            continue
        ten_lower = ten.lower()
        is_dinh_tinh = any(k in ten_lower for k in ["định tính", "identification", "qualitative"])
        is_nhiem_khuan = any(k in ten_lower for k in ["nhiễm khuẩn", "vi sinh", "microbial", "microbiol", "vsv"])
        ma_ct = match_criteria_id_by_name(ten, criteria_master)
        if is_nhiem_khuan:
            ma_ct = "gioi_han_nhiem_khuan"

        merged = False
        if is_dinh_tinh:
            for existing in all_results:
                if any(k in existing["ten_chi_tieu"].lower() for k in ["định tính", "identification", "qualitative"]):
                    if nd not in existing["noi_dung_mau"]:
                        existing["noi_dung_mau"] += "\n" + nd
                    existing["ma_chi_tieu"] = "dinh_tinh"
                    merged = True
                    break
        elif is_nhiem_khuan:
            for existing in all_results:
                if any(k in existing["ten_chi_tieu"].lower() for k in ["nhiễm khuẩn", "vi sinh", "microbial", "microbiol", "vsv"]):
                    if nd not in existing["noi_dung_mau"]:
                        existing["noi_dung_mau"] += "\n" + nd
                    existing["ma_chi_tieu"] = "gioi_han_nhiem_khuan"
                    merged = True
                    break

        if not merged:
            if is_nhiem_khuan and "nhiễm khuẩn" not in ten_lower:
                ten = "Giới hạn nhiễm khuẩn"
                ten_lower = ten.lower()
            if ten_lower not in seen_names:
                seen_names.add(ten_lower)
                all_results.append({"ten_chi_tieu": ten, "noi_dung_mau": nd, "ma_chi_tieu": ma_ct})
            else:
                for existing in all_results:
                    if existing["ten_chi_tieu"].lower() == ten_lower:
                        if len(nd) > len(existing["noi_dung_mau"]):
                            existing["noi_dung_mau"] = nd
                            existing["ma_chi_tieu"] = ma_ct
                        break


def _ai_extract_all_criteria(noi_dung_text: str, ten_nl: str):
    """
    Bóc tách toàn bộ chỉ tiêu từ hồ sơ mẫu.
    ⚡ Xử lý SONG SONG các chunk bằng ThreadPoolExecutor để tăng tốc tối đa.
    - Retry 1 lần nếu chunk lỗi, nếu vẫn lỗi thì cảnh báo và bỏ qua.
    - Gộp và loại trùng kết quả từ nhiều đoạn sau khi hoàn tất.
    """
    from core.ai_handler import call_ai_engine_parallel
    import concurrent.futures as cf

    CHUNK_SIZE = 12000
    OVERLAP = 1000
    MAX_TOTAL = 48000  # Tăng lên để bao phủ hồ sơ dài hơn

    noi_dung_crop = noi_dung_text[:MAX_TOTAL]
    total_len = len(noi_dung_crop)

    # Tạo các đoạn có overlap
    chunks = []
    pos = 0
    while pos < total_len:
        end = min(pos + CHUNK_SIZE, total_len)
        chunks.append(noi_dung_crop[pos:end])
        if end >= total_len:
            break
        pos = end - OVERLAP

    tong_chunk = len(chunks)
    st.info(f"📄 Tài liệu dài **{total_len:,} ký tự** → chia thành **{tong_chunk} đoạn**, xử lý ⚡ **song song** để tăng tốc.")

    # Load criteria_master một lần duy nhất
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    criteria_path = os.path.join(base_dir, "criteria_master.json")
    criteria_master = {}
    try:
        if os.path.exists(criteria_path):
            with open(criteria_path, 'r', encoding='utf-8') as f:
                criteria_master = json.load(f)
    except Exception:
        pass

    # Chuẩn bị tasks song song
    tasks = [
        {
            "index": i,
            "system_instruction": SYSTEM_PROMPT_EXTRACT,
            "user_content": PROMPT_EXTRACT_TEMPLATE.format(
                ten_nl=ten_nl,
                chunk_so=i + 1,
                tong_chunk=tong_chunk,
                noi_dung=chunk
            ),
            "provider": "Google API",
            "model": "gemma-4-31b-it",
            "is_json": True,
            "temperature": 0.0
        }
        for i, chunk in enumerate(chunks)
    ]

    progress_placeholder = st.empty()
    progress_placeholder.info(f"⚡ Đang gửi {tong_chunk} đoạn đến AI song song...")

    results_list, errors_map = call_ai_engine_parallel(tasks, max_workers=min(tong_chunk, 4))

    # Thông báo nếu có lỗi một số chunk → retry tuần tự chunk đó
    if errors_map:
        from core.ai_handler import call_ai_engine
        for err_idx, err_msg in errors_map.items():
            progress_placeholder.warning(f"⚠️ Đoạn {err_idx+1} lỗi lần 1 ({err_msg[:80]}...), đang retry...")
            try:
                retry_result = call_ai_engine(
                    SYSTEM_PROMPT_EXTRACT,
                    tasks[err_idx]["user_content"],
                    "Google API",
                    "gemma-4-31b-it",
                    is_json=True,
                    temperature=0.0
                )
                results_list[err_idx] = retry_result
            except Exception as e2:
                st.warning(f"⚠️ Đoạn {err_idx+1} retry vẫn lỗi: {e2}. Bỏ qua đoạn này.")

    progress_placeholder.empty()

    # Gộp kết quả theo đúng thứ tự chunk
    all_results = []
    seen_names = set()
    failed_chunks = []

    for i, raw_result in enumerate(results_list):
        if raw_result is None:
            failed_chunks.append(i + 1)
            continue
        parsed = _parse_ai_json(raw_result, "array")
        if not parsed or not isinstance(parsed, list):
            failed_chunks.append(i + 1)
            continue
        _merge_results(all_results, seen_names, parsed, criteria_master)

    if failed_chunks:
        st.warning(f"⚠️ Không thể xử lý các đoạn: {failed_chunks}. Kết quả có thể thiếu nội dung từ các đoạn này.")

    if all_results:
        st.session_state.vi_du_upload_rows = all_results
        st.success(
            f"✅ AI đã bóc tách được **{len(all_results)} chỉ tiêu** từ {tong_chunk} đoạn (song song)!\n"
            f"Kiểm tra lại danh sách bên dưới trước khi lưu."
        )
        with st.expander(f"📋 Danh sách {len(all_results)} chỉ tiêu đã bóc tách"):
            for r in all_results:
                nd_prev = r['noi_dung_mau'][:80].replace('\n', ' ')
                ma_prev = f" ({r.get('ma_chi_tieu')})" if r.get('ma_chi_tieu') else " (Chưa liên kết)"
                st.markdown(f"- **{r['ten_chi_tieu']}**{ma_prev}: {nd_prev}...")
        st.rerun()
    else:
        st.warning(
            "⚠️ AI không tìm thấy chỉ tiêu nào có SOP đầy đủ trong toàn bộ hồ sơ.\n"
            "Hãy kiểm tra lại nội dung hồ sơ hoặc nhập tay."
        )


def _ai_quality_check(vi_du_rows: list, ten_nl: str):
    """
    AI tự đánh giá chất lượng các chỉ tiêu vừa bóc tách.
    Trả về điểm (1-10) và danh sách chỉ tiêu cần cải thiện.
    """
    from core.ai_handler import call_ai_engine

    if not vi_du_rows:
        st.warning("Chưa có chỉ tiêu nào để kiểm tra.")
        return

    # Tóm tắt nội dung để kiểm tra
    summary_lines = []
    for r in vi_du_rows:
        nd = r.get('noi_dung_mau', '')
        summary_lines.append(f"- {r['ten_chi_tieu']}: {nd[:300]}")
    summary_text = "\n".join(summary_lines)

    prompt = f"""Dưới đây là danh sách các chỉ tiêu kiểm nghiệm đã bóc tách từ hồ sơ '{ten_nl}':

{summary_text}

Hãy đánh giá chất lượng bóc tách và trả về JSON:
{{
    "diem_tong_the": <1-10>,
    "nhan_xet_chung": "Nhận xét ngắn gọn về chất lượng tổng thể",
    "chi_tieu_tot": ["Tên chỉ tiêu có nội dung đầy đủ, chuẩn xác"],
    "chi_tieu_can_cai_thien": [
        {{"ten": "Tên chỉ tiêu", "ly_do": "Lý do cần cải thiện", "goi_y": "Gợi ý cụ thể"}}
    ],
    "chi_tieu_co_the_thieu": ["Tên các chỉ tiêu có thể thiếu trong hồ sơ này"]
}}

Tiêu chí đánh giá:
- Có "Theo chuyên luận..." ở đầu không?
- Có "Yêu cầu: ..." ở cuối không?
- Nội dung có đủ chi tiết (>100 ký tự) không?
- Có công thức tính nếu cần không?
- Không có "Kết quả:" thừa không?"""

    with st.spinner("🔍 AI đang đánh giá chất lượng bóc tách..."):
        try:
            result = call_ai_engine(
                "Bạn là chuyên gia QA/QC kiểm tra chất lượng hồ sơ kiểm nghiệm. Trả về DUY NHẤT JSON object.",
                prompt,
                "Google API",
                "gemma-4-31b-it",
                is_json=True,
                temperature=0.0
            )
            qa_data = _parse_ai_json(result, "dict")
            if not qa_data:
                st.error("❌ AI không trả về kết quả hợp lệ.")
                return

            diem = qa_data.get("diem_tong_the", 0)
            nhan_xet = qa_data.get("nhan_xet_chung", "")
            tot = qa_data.get("chi_tieu_tot", [])
            can_sua = qa_data.get("chi_tieu_can_cai_thien", [])
            co_the_thieu = qa_data.get("chi_tieu_co_the_thieu", [])

            # Hiển thị kết quả
            color = "#22c55e" if diem >= 8 else ("#f59e0b" if diem >= 6 else "#ef4444")
            st.markdown(
                f"<div style='background:{color}22;border-left:4px solid {color};padding:12px;border-radius:8px;'>"
                f"<b>⭐ Điểm chất lượng: {diem}/10</b><br>{nhan_xet}</div>",
                unsafe_allow_html=True
            )

            if tot:
                with st.expander(f"✅ {len(tot)} chỉ tiêu chất lượng tốt"):
                    for t in tot:
                        st.markdown(f"- {t}")

            if can_sua:
                with st.expander(f"⚠️ {len(can_sua)} chỉ tiêu cần cải thiện", expanded=True):
                    for item in can_sua:
                        st.markdown(
                            f"**🔸 {item.get('ten', '')}**: {item.get('ly_do', '')}\n"
                            f"→ *{item.get('goi_y', '')}*"
                        )

            if co_the_thieu:
                with st.expander(f"❓ {len(co_the_thieu)} chỉ tiêu có thể bị thiếu"):
                    for t in co_the_thieu:
                        st.markdown(f"- {t}")

        except Exception as e:
            st.error(f"❌ Lỗi kiểm tra chất lượng: {e}")


# =============================
# TAB 2: THƯ VIỆN HỒ SƠ MẪU
# =============================

def render_tab_ho_so_mau():
    lib_data = load_json_safe(STYLE_LIB_FILE, {"_meta": {}})
    entries = {k: v for k, v in lib_data.items() if k != "_meta" and isinstance(v, dict)}

    st.markdown(f"#### 📦 Thư Viện Hồ Sơ Mẫu ({len(entries)} hồ sơ)")
    st.caption("Upload hồ sơ Word đã hoàn chỉnh HOẶC lưu trực tiếp từ kết quả hệ thống. AI học phong cách từ các hồ sơ này.")

    sub_a, sub_b = st.tabs(["📤 Upload Hồ Sơ Mới", "📋 Danh Sách Hồ Sơ Mẫu"])

    with sub_a:
        st.markdown("##### Upload hồ sơ kiểm nghiệm đã hoàn chỉnh")
        st.info("💡 Hỗ trợ file Word (.docx) đã điền đầy đủ hoặc dán nội dung trực tiếp vào ô bên dưới.")

        col1, col2 = st.columns([1, 1])
        with col1:
            ten_nl_input = st.text_input("Tên nguyên liệu / chế phẩm*", placeholder="Ví dụ: Amoxicillin Trihydrate", key="upload_ten_nl")
            loai_tl_input = st.selectbox("Loại tài liệu*", ["Dược điển BP", "Dược điển USP", "Dược điển EP", "Dược điển DĐVN", "Tiêu chuẩn nội bộ", "Khác"], key="upload_loai_tl")
        with col2:
            mo_ta_input = st.text_input("Mô tả / Ghi chú", placeholder="Ví dụ: Hồ sơ mẫu tốt, có đầy đủ HPLC và định tính", key="upload_mo_ta")
            la_mau_vang = st.checkbox("⭐ Đánh dấu là Mẫu Vàng (Gold Standard)", value=True, key="upload_mau_vang", help="Mẫu Vàng được ưu tiên cao nhất khi AI học phong cách")

        up_method = st.radio("Cách nhập hồ sơ:", ["📁 Upload file Word (.docx)", "📝 Dán nội dung trực tiếp (text)"], horizontal=True, key="upload_method")

        noi_dung_text = ""
        if up_method == "📁 Upload file Word (.docx)":
            uploaded_word = st.file_uploader("Chọn file Word hồ sơ mẫu", type=["docx"], key="upload_word_file")
            if uploaded_word:
                try:
                    import docx, io
                    doc = docx.Document(io.BytesIO(uploaded_word.read()))

                    # Bộ đếm số đầu mục (cho danh sách decimal/lowerLetter)
                    num_counters = {}
                    # Cache numbering.xml đã parse
                    _abs_num_cache = {}

                    def _build_abs_num_cache():
                        """Đọc numbering.xml một lần và cache kết quả."""
                        if _abs_num_cache:
                            return
                        try:
                            numbering_part = doc.part.numbering_part
                        except Exception:
                            return
                        if numbering_part is None:
                            return
                        ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
                        root = numbering_part._element
                        # Map abstractNumId -> {ilvl -> {numFmt, lvlText}}
                        for abs_num in root.findall(f'{{{ns}}}abstractNum'):
                            abs_id_el = abs_num.get(f'{{{ns}}}abstractNumId')
                            if abs_id_el is None:
                                continue
                            abs_id = int(abs_id_el)
                            _abs_num_cache[abs_id] = {}
                            for lvl in abs_num.findall(f'{{{ns}}}lvl'):
                                ilvl_val = int(lvl.get(f'{{{ns}}}ilvl', 0))
                                fmt_el = lvl.find(f'{{{ns}}}numFmt')
                                txt_el = lvl.find(f'{{{ns}}}lvlText')
                                fmt = fmt_el.get(f'{{{ns}}}val', '') if fmt_el is not None else ''
                                txt = txt_el.get(f'{{{ns}}}val', '') if txt_el is not None else ''
                                _abs_num_cache[abs_id][ilvl_val] = {'numFmt': fmt, 'lvlText': txt}
                        # Map numId -> abstractNumId
                        _abs_num_cache['__numid_map__'] = {}
                        for num_el in root.findall(f'{{{ns}}}num'):
                            num_id_val = num_el.get(f'{{{ns}}}numId')
                            abs_ref = num_el.find(f'{{{ns}}}abstractNumId')
                            if num_id_val and abs_ref is not None:
                                abs_ref_val = abs_ref.get(f'{{{ns}}}val')
                                if abs_ref_val is not None:
                                    _abs_num_cache['__numid_map__'][int(num_id_val)] = int(abs_ref_val)

                    def _resolve_bullet_char(num_id, ilvl):
                        """Tra cứu ký tự bullet thực tế (✓, •...) từ numbering.xml."""
                        _build_abs_num_cache()
                        numid_map = _abs_num_cache.get('__numid_map__', {})
                        abs_id = numid_map.get(num_id)
                        if abs_id is None:
                            return None
                        lvl_data = _abs_num_cache.get(abs_id, {}).get(ilvl, {})
                        fmt = lvl_data.get('numFmt', '')
                        txt = lvl_data.get('lvlText', '')
                        if fmt == 'bullet':
                            # Map Wingdings → Unicode
                            char_map = {
                                '': '✓',  # Wingdings checkmark ✓
                                '': '✓',  # Wingdings checkmark alt
                                '': '•',  # Wingdings bullet •
                                '': '▪',  # Wingdings ▪ small square
                                'o':      '◦',  # Wingdings o → ◦ white circle
                                '✓': '✓',  # ✓ Unicode
                                '✔': '✔',  # ✔ bold checkmark
                                '•': '•',  # • bullet
                                '●': '●',  # ● filled circle
                                '■': '■',  # ■ square
                                '–': '–',  # – dash
                            }
                            resolved = char_map.get(txt, None)
                            if resolved:
                                return resolved + ' '
                            if txt and len(txt) <= 2:
                                return txt + ' '
                            return '• '  # fallback •
                        return None  # không phải bullet

                    def get_p_numbering_pref(p):
                        """Xác định prefix đầu dòng từ numPr XML.
                        Ưu tiên đọc ký tự bullet thực tế (✓, •) từ numbering.xml.
                        Chỉ tạo số thứ tự (1., 2.) khi numFmt là decimal/lowerLetter/...
                        """
                        p_pr = p._p.pPr
                        if p_pr is None or p_pr.numPr is None:
                            return ""
                        num_pr = p_pr.numPr
                        num_id = num_pr.numId.val if num_pr.numId is not None else None
                        ilvl = num_pr.ilvl.val if num_pr.ilvl is not None else 0
                        if num_id is None or num_id == 0:
                            return ""

                        # Ưu tiên: đọc ký tự bullet thực tế
                        bullet_char = _resolve_bullet_char(num_id, ilvl)
                        if bullet_char is not None:
                            return bullet_char

                        # Fallback: kiểm tra tên style
                        style_lower = p.style.name.lower() if p.style else ""
                        if "bullet" in style_lower:
                            return "• "

                        # Danh sách có thứ tự — đọc numFmt để định dạng đúng
                        def _get_num_fmt_local(nid, ilv):
                            """Lấy numFmt từ cache cho numId/ilvl."""
                            _build_abs_num_cache()
                            nmap = _abs_num_cache.get("__numid_map__", {})
                            aid = nmap.get(nid)
                            if aid is None:
                                return "decimal"
                            return _abs_num_cache.get(aid, {}).get(ilv, {}).get("numFmt", "decimal")

                        def _to_roman(n):
                            """Chuyển số nguyên sang chữ số La Mã."""
                            vals = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),
                                    (90,"XC"),(50,"L"),(40,"XL"),(10,"X"),(9,"IX"),
                                    (5,"V"),(4,"IV"),(1,"I")]
                            res = ""
                            for v, s in vals:
                                while n >= v:
                                    res += s; n -= v
                            return res

                        def _format_by_fmt(count, fmt):
                            """Định dạng số đếm theo numFmt."""
                            if fmt == "upperLetter":
                                return chr(ord("A") + (count - 1) % 26)
                            elif fmt == "lowerLetter":
                                return chr(ord("a") + (count - 1) % 26)
                            elif fmt == "upperRoman":
                                return _to_roman(count)
                            elif fmt == "lowerRoman":
                                return _to_roman(count).lower()
                            else:
                                return str(count)

                        num_fmt_cur = _get_num_fmt_local(num_id, ilvl)
                        if num_id not in num_counters:
                            num_counters[num_id] = [0] * 9
                        num_counters[num_id][ilvl] += 1
                        for i in range(ilvl + 1, 9):
                            num_counters[num_id][i] = 0
                        cnt = num_counters[num_id][ilvl]
                        label = _format_by_fmt(cnt, num_fmt_cur)
                        if ilvl == 0:
                            return f"{label}. "
                        elif ilvl == 1:
                            parent_fmt = _get_num_fmt_local(num_id, 0)
                            parent_label = _format_by_fmt(num_counters[num_id][0], parent_fmt)
                            return f"{parent_label}.{label}. "
                        else:
                            return f"{label}. "

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
                        """
                        Đọc văn bản chi tiết từ XML element (hỗ trợ các công thức toán học <m:oMath>,
                        dòng trống <w:br> và số đầu mục của paragraph).
                        """
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


                    # ── Hàm đọc bảng dưới dạng HTML giữ nguyên colspan và rowspan ──
                    def read_table_as_html(table):
                        """Chuyển đổi bảng Word thành bảng HTML giữ nguyên rowspan và colspan."""
                        n_rows = len(table.rows)
                        if n_rows == 0:
                            return []
                        
                        # Xác định số lượng cột tối đa trong bảng
                        n_cols = max(len(row.cells) for row in table.rows) if table.rows else 0
                        if n_cols == 0:
                            return []
                            
                        # Khởi tạo grid 2D ánh xạ toạ độ cột-hàng
                        grid = [[None for _ in range(n_cols)] for _ in range(n_rows)]
                        for r_idx, row in enumerate(table.rows):
                            for c_idx, cell in enumerate(row.cells):
                                if c_idx < n_cols:
                                    grid[r_idx][c_idx] = cell
                                    
                        visited = set()
                        html_rows = []
                        
                        for r_idx in range(n_rows):
                            row_cells_html = []
                            for c_idx in range(n_cols):
                                cell = grid[r_idx][c_idx]
                                if cell is None:
                                    continue
                                tc_el = cell._tc
                                if tc_el in visited:
                                    continue
                                visited.add(tc_el)
                                
                                # Tính toán colspan (trộn cột ngang)
                                colspan = 1
                                while c_idx + colspan < n_cols and grid[r_idx][c_idx + colspan] is not None and grid[r_idx][c_idx + colspan]._tc == tc_el:
                                    colspan += 1
                                    
                                # Tính toán rowspan (trộn hàng dọc)
                                rowspan = 1
                                while r_idx + rowspan < n_rows and grid[r_idx + rowspan][c_idx] is not None and grid[r_idx + rowspan][c_idx]._tc == tc_el:
                                    rowspan += 1
                                    
                                # Đánh dấu các vị trí ô trộn trong grid là đã xử lý
                                for dr in range(rowspan):
                                    for dc in range(colspan):
                                        if r_idx + dr < n_rows and c_idx + dc < n_cols and grid[r_idx + dr][c_idx + dc] is not None:
                                            visited.add(grid[r_idx + dr][c_idx + dc]._tc)
                                            
                                # Lấy văn bản trong ô dưới dạng rich-text (có cả số đầu mục + công thức toán học)
                                cell_paras_text = []
                                for p in cell.paragraphs:
                                    p_txt = get_element_rich_text(p._p, p)
                                    if p_txt:
                                        cell_paras_text.append(p_txt)
                                cell_text = "<br>".join(cell_paras_text)
                                
                                td_attrs = []
                                if colspan > 1:
                                    td_attrs.append(f'colspan="{colspan}"')
                                if rowspan > 1:
                                    td_attrs.append(f'rowspan="{rowspan}"')
                                    
                                attrs_str = " " + " ".join(td_attrs) if td_attrs else ""
                                row_cells_html.append(f'<td{attrs_str} style="border: 1px solid #ccc; padding: 8px; vertical-align: top;">{cell_text}</td>')
                                
                            if row_cells_html:
                                html_rows.append("  <tr>\n    " + "\n    ".join(row_cells_html) + "\n  </tr>")
                                
                        html_table = [
                            '<table style="border-collapse: collapse; width: 100%; border: 1px solid #ccc; font-family: sans-serif; font-size: 14px; margin-bottom: 15px;">',
                            *html_rows,
                            '</table>'
                        ]
                        return html_table

                    full_text = []

                    # Đọc đoạn văn bản thường (ngoài bảng)
                    for p in doc.paragraphs:
                        p_text = get_element_rich_text(p._p, p)
                        if p_text:
                            full_text.append(p_text)

                    # Đọc tất cả bảng (dưới dạng HTML)
                    for table in doc.tables:
                        html_lines = read_table_as_html(table)
                        if html_lines:
                            full_text.extend(html_lines)
                            full_text.append("")  # Dòng trống phân cách bảng

                    noi_dung_text = "\n".join(full_text)

                    # Thống kê
                    st.success(
                        f"✅ Đọc được **{len(noi_dung_text):,} ký tự** | "
                        f"**{len(full_text)} dòng** từ file Word."
                    )

                    # Hiển thị TOÀN BỘ nội dung dưới dạng bảng và văn bản đẹp mắt
                    with st.expander(f"👁 Xem toàn bộ nội dung ({len(noi_dung_text):,} ký tự)"):
                        with st.container(height=500):
                            st.markdown(noi_dung_text, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"❌ Lỗi đọc file Word: {e}")

        else:
            noi_dung_text = st.text_area(
                "Dán toàn bộ nội dung hồ sơ vào đây:",
                height=300,
                placeholder="Dán nội dung hồ sơ kiểm nghiệm đã hoàn chỉnh vào đây...",
                key="upload_text_direct"
            )

        # ─── Phần nhập ví dụ chi tiết từng chỉ tiêu ──────────────────────────
        st.markdown("---")
        st.markdown("**✏️ Ví dụ chi tiết từng chỉ tiêu**")
        st.caption("AI sẽ bóc tách tự động hoặc bạn có thể nhập tay. Nên có 3-5 chỉ tiêu quan trọng.")

        if "vi_du_upload_rows" not in st.session_state:
            st.session_state.vi_du_upload_rows = [{"ten_chi_tieu": "", "noi_dung_mau": ""}]

        # Load criteria_master to get standard IDs for selection
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        criteria_path = os.path.join(base_dir, "criteria_master.json")
        criteria_master = {}
        try:
            if os.path.exists(criteria_path):
                with open(criteria_path, 'r', encoding='utf-8') as f:
                    criteria_master = json.load(f)
        except Exception:
            pass

        # Options list: [("Friendly name", "id")]
        std_options = [("Không liên kết / Khác (None)", "None")]
        for key_std, val_std in sorted(criteria_master.items(), key=lambda x: x[1].get("ten_hien_thi", x[0])):
            std_options.append((f"{val_std.get('ten_hien_thi')} ({key_std})", key_std))

        new_rows = []
        for i, row in enumerate(st.session_state.vi_du_upload_rows):
            c1, c2, c3 = st.columns([1.5, 3, 0.3])
            
            curr_ma = row.get("ma_chi_tieu")
            if not curr_ma and row.get("ten_chi_tieu"):
                from core.doc_processor import match_criteria_id_by_name
                curr_ma = match_criteria_id_by_name(row.get("ten_chi_tieu"), criteria_master)
            
            # Find index
            sel_idx = 0
            for idx_std, (lbl, val_id) in enumerate(std_options):
                if val_id == curr_ma:
                    sel_idx = idx_std
                    break

            with c1:
                ten_ct = st.text_input(f"Tên chỉ tiêu {i+1}", value=row.get("ten_chi_tieu", ""), key=f"vd_ten_{i}", placeholder="VD: Định lượng HPLC")
                sel_ma = st.selectbox(
                    f"Liên kết chỉ tiêu hệ thống {i+1}",
                    options=[o[0] for o in std_options],
                    index=sel_idx,
                    key=f"vd_ma_{i}"
                )
                ma_ct = std_options[[o[0] for o in std_options].index(sel_ma)][1]
                if ma_ct == "None":
                    ma_ct = None

            with c2:
                nd_ct = st.text_area(f"Nội dung mẫu {i+1}", value=row.get("noi_dung_mau", ""), key=f"vd_nd_{i}", height=120, placeholder="Dán nội dung SOP của chỉ tiêu này từ hồ sơ mẫu...")
            with c3:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("🗑", key=f"del_vd_{i}", help="Xóa dòng này"):
                    st.session_state.vi_du_upload_rows.pop(i)
                    st.rerun()
            new_rows.append({"ten_chi_tieu": ten_ct, "noi_dung_mau": nd_ct, "ma_chi_tieu": ma_ct})
        st.session_state.vi_du_upload_rows = new_rows

        if st.button("➕ Thêm chỉ tiêu ví dụ", key="btn_add_vd_row"):
            st.session_state.vi_du_upload_rows.append({"ten_chi_tieu": "", "noi_dung_mau": ""})
            st.rerun()

        # ─── Nút AI tự động bóc tách ─────────────────────────────────────────
        if noi_dung_text.strip() and ten_nl_input.strip():
            st.markdown("---")
            st.markdown("**🤖 Bóc Tách Tự Động Bằng AI**")
            st.info(
                "💡 AI sẽ đọc TOÀN BỘ hồ sơ và trích xuất tất cả chỉ tiêu có SOP đầy đủ. "
                "⚡ Xử lý **song song** để tăng tốc tối đa.\n"
                "**Lưu ý:** Chỉ tiêu **Định tính** sẽ được gộp thành 1 chỉ tiêu duy nhất chứa toàn bộ A, B, C, D..."
            )

            col_extract, col_qc = st.columns([1, 1])
            with col_extract:
                if st.button("✨ AI Bóc Tách Toàn Bộ Chỉ Tiêu", key="btn_ai_extract_vi_du", type="secondary", use_container_width=True):
                    _ai_extract_all_criteria(noi_dung_text, ten_nl_input)
            with col_qc:
                if st.button("🔍 Kiểm Tra Chất Lượng Bóc Tách", key="btn_ai_qc_check", use_container_width=True):
                    current_rows = st.session_state.get("vi_du_upload_rows", [])
                    filled_rows = [r for r in current_rows if r.get("ten_chi_tieu") and r.get("noi_dung_mau")]
                    if filled_rows:
                        _ai_quality_check(filled_rows, ten_nl_input)
                    else:
                        st.warning("Chưa có chỉ tiêu nào. Hãy bóc tách trước!")



        st.markdown("---")

        # ─── Nút lưu ─────────────────────────────────────────────────────────
        col_btn1, _ = st.columns([1, 3])
        with col_btn1:
            if st.button("💾 Lưu Hồ Sơ Mẫu", type="primary", key="btn_save_ho_so_mau"):
                if not ten_nl_input.strip():
                    st.error("❌ Vui lòng nhập tên nguyên liệu!")
                else:
                    vi_du_filtered = [
                        r for r in st.session_state.vi_du_upload_rows
                        if r.get("ten_chi_tieu") and r.get("noi_dung_mau")
                    ]
                    _save_new_ho_so_mau(
                        ten_nl=ten_nl_input.strip(),
                        loai_tl=loai_tl_input,
                        mo_ta=mo_ta_input.strip(),
                        la_mau_vang=la_mau_vang,
                        noi_dung=noi_dung_text.strip(),
                        vi_du_chi_tiet=vi_du_filtered,
                        lib_data=lib_data
                    )

    with sub_b:
        if not entries:
            st.info("📭 Thư viện chưa có hồ sơ mẫu nào. Hãy upload hồ sơ ở tab bên cạnh.")
        else:
            n_vang = sum(1 for v in entries.values() if v.get("la_mau_vang"))
            st.markdown(f"**Tổng cộng: {len(entries)} hồ sơ** — ⭐ {n_vang} Mẫu Vàng")
            
            # Load criteria_master once for options matching/editing
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            criteria_path = os.path.join(base_dir, "criteria_master.json")
            criteria_master = {}
            try:
                if os.path.exists(criteria_path):
                    with open(criteria_path, 'r', encoding='utf-8') as f:
                        criteria_master = json.load(f)
            except Exception:
                pass
            std_options = [("Không liên kết / Khác (None)", "None")]
            for key_std, val_std in sorted(criteria_master.items(), key=lambda x: x[1].get("ten_hien_thi", x[0])):
                std_options.append((f"{val_std.get('ten_hien_thi')} ({key_std})", key_std))

            if st.button("🧠 Phân Tích Phong Cách Từ Toàn Bộ Thư Viện", type="primary", key="btn_analyze_all"):
                _ai_analyze_style()

            st.markdown("---")

            for entry_id, entry_data in sorted(entries.items(), key=lambda x: (0 if x[1].get("la_mau_vang") else 1, x[1].get("ngay_tao", "")), reverse=False):
                ten_nl = entry_data.get("ten_nguyen_lieu", entry_id)
                loai_tl = entry_data.get("loai_tai_lieu", "")
                mo_ta = entry_data.get("mo_ta", "")
                la_vang = entry_data.get("la_mau_vang", False)
                ngay = entry_data.get("ngay_tao", "")
                vi_du_chi_tiet = entry_data.get("vi_du_chi_tiet", [])
                noi_dung_day_du = entry_data.get("noi_dung_day_du", "")
                ky_tu = len(noi_dung_day_du) if noi_dung_day_du else 0

                badge_icon = "⭐" if la_vang else "📄"

                with st.expander(f"{badge_icon} **{ten_nl}** — {loai_tl} | {ngay} | {len(vi_du_chi_tiet)} chỉ tiêu mẫu | {ky_tu:,} ký tự"):
                    if mo_ta:
                        st.caption(f"📝 {mo_ta}")

                    # Checkbox to toggle Edit Mode
                    is_editing = st.checkbox("✏️ Sửa nội dung & ID chỉ tiêu", key=f"is_editing_{entry_id}")

                    if is_editing:
                        st.markdown("**✏️ Chế độ chỉnh sửa chỉ tiêu:**")
                        updated_vi_du = []
                        
                        # Loop through and render editable fields
                        for idx, vd in enumerate(vi_du_chi_tiet):
                            st.markdown("---")
                            c1_ed, c2_ed = st.columns([1.5, 3])
                            with c1_ed:
                                t_val = st.text_input(
                                    f"Tên chỉ tiêu {idx+1}", 
                                    value=vd.get("ten_chi_tieu", ""), 
                                    key=f"edit_ten_{entry_id}_{idx}"
                                )
                                
                                # Selectbox standard ID mapping
                                curr_ma = vd.get("ma_chi_tieu")
                                if not curr_ma and t_val:
                                    from core.doc_processor import match_criteria_id_by_name
                                    curr_ma = match_criteria_id_by_name(t_val, criteria_master)
                                    
                                sel_idx = 0
                                for idx_std, (lbl, val_id) in enumerate(std_options):
                                    if val_id == curr_ma:
                                        sel_idx = idx_std
                                        break
                                        
                                s_val_lbl = st.selectbox(
                                    f"Liên kết chỉ tiêu hệ thống {idx+1}",
                                    options=[o[0] for o in std_options],
                                    index=sel_idx,
                                    key=f"edit_ma_{entry_id}_{idx}"
                                )
                                ma_ct = std_options[[o[0] for o in std_options].index(s_val_lbl)][1]
                                if ma_ct == "None":
                                    ma_ct = None
                                    
                            with c2_ed:
                                n_val = st.text_area(
                                    f"Nội dung mẫu {idx+1}", 
                                    value=vd.get("noi_dung_mau", ""), 
                                    key=f"edit_nd_{entry_id}_{idx}",
                                    height=120
                                )
                            
                            updated_vi_du.append({
                                "ma_chi_tieu": ma_ct,
                                "ten_chi_tieu": t_val,
                                "noi_dung_mau": n_val
                            })
                            
                        # Save Button
                        if st.button("💾 Lưu thay đổi chỉ tiêu", key=f"save_edit_{entry_id}", type="primary"):
                            # Filter empty rows
                            filtered_vi_du = [r for r in updated_vi_du if r.get("ten_chi_tieu").strip() and r.get("noi_dung_mau").strip()]
                            lib_data[entry_id]["vi_du_chi_tiet"] = filtered_vi_du
                            save_json_safe(STYLE_LIB_FILE, lib_data)
                            st.success(f"✅ Đã cập nhật thành công {len(filtered_vi_du)} chỉ tiêu của '{ten_nl}'!")
                            time.sleep(0.5)
                            st.rerun()

                    else:
                        # View Mode (with sequence numbering)
                        if vi_du_chi_tiet:
                            st.markdown("**Các chỉ tiêu ví dụ:**")
                            for idx, vd in enumerate(vi_du_chi_tiet):
                                nd_preview = vd.get('noi_dung_mau', '')
                                ma_val = vd.get('ma_chi_tieu')
                                ma_display = f" (`{ma_val}`)" if ma_val else " (Chưa liên kết)"
                                st.markdown(f"{idx+1}. **{vd.get('ten_chi_tieu', '')}**{ma_display}:")
                                nd_text = nd_preview[:150].strip()
                                if len(nd_preview) > 150:
                                    nd_text += "..."
                                st.caption(nd_text)

                    if noi_dung_day_du:
                        with st.expander("📄 Xem nội dung đầy đủ đã lưu"):
                            with st.container(height=400):
                                st.markdown(noi_dung_day_du, unsafe_allow_html=True)

                    c_toggle, c_delete = st.columns([1, 1])
                    with c_toggle:
                        new_vang_state = not la_vang
                        toggle_label = "❌ Bỏ Mẫu Vàng" if la_vang else "⭐ Đặt làm Mẫu Vàng"
                        if st.button(toggle_label, key=f"toggle_vang_{entry_id}"):
                            lib_data[entry_id]["la_mau_vang"] = new_vang_state
                            save_json_safe(STYLE_LIB_FILE, lib_data)
                            st.rerun()
                    with c_delete:
                        if st.button("🗑 Xóa khỏi thư viện", key=f"del_ho_so_{entry_id}"):
                            del lib_data[entry_id]
                            save_json_safe(STYLE_LIB_FILE, lib_data)
                            st.success(f"✅ Đã xóa hồ sơ '{ten_nl}'")
                            time.sleep(0.5)
                            st.rerun()


def _save_new_ho_so_mau(ten_nl, loai_tl, mo_ta, la_mau_vang, noi_dung, vi_du_chi_tiet, lib_data):
    """Lưu hồ sơ mẫu mới vào thư viện - Lưu TOÀN BỘ nội dung (không cắt xén)."""
    entry_id = _gen_entry_id(ten_nl)
    
    # Tự động gán ma_chi_tieu bằng cách khớp tên chỉ tiêu
    from core.doc_processor import match_criteria_id_by_name
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    criteria_path = os.path.join(base_dir, "criteria_master.json")
    criteria_master = {}
    try:
        if os.path.exists(criteria_path):
            with open(criteria_path, 'r', encoding='utf-8') as f:
                criteria_master = json.load(f)
    except Exception:
        pass

    vi_du_mapped = []
    for vd in vi_du_chi_tiet:
        ten_ct = vd.get("ten_chi_tieu", "")
        noi_dung_mau = vd.get("noi_dung_mau", "")
        ma_ct = vd.get("ma_chi_tieu")
        if not ma_ct:
            ma_ct = match_criteria_id_by_name(ten_ct, criteria_master)
        vi_du_mapped.append({
            "ma_chi_tieu": ma_ct,
            "ten_chi_tieu": ten_ct,
            "noi_dung_mau": noi_dung_mau
        })

    lib_data[entry_id] = {
        "ten_nguyen_lieu": ten_nl,
        "loai_tai_lieu": loai_tl,
        "mo_ta": mo_ta,
        "la_mau_vang": la_mau_vang,
        "ngay_tao": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "noi_dung_tom_tat": noi_dung[:2000] if noi_dung else "",  # Rút gọn cho hiển thị nhanh
        "noi_dung_day_du": noi_dung,                               # Toàn bộ để AI học
        "vi_du_chi_tiet": vi_du_mapped
    }
    save_json_safe(STYLE_LIB_FILE, lib_data)

    if "vi_du_upload_rows" in st.session_state:
        st.session_state.vi_du_upload_rows = [{"ten_chi_tieu": "", "noi_dung_mau": ""}]

    st.success(f"✅ Đã lưu hồ sơ mẫu **'{ten_nl}'** vào thư viện! ({len(noi_dung):,} ký tự, {len(vi_du_chi_tiet)} chỉ tiêu mẫu)")
    time.sleep(1)
    st.rerun()


# =============================
# TAB 3: SOP FORMATTING GUIDELINES
# =============================

def render_tab_sop_guidelines():
    st.markdown("#### 📐 Quy Tắc Định Dạng SOP")
    st.info("💡 Các quy tắc định dạng cốt lõi được tích hợp sẵn trong hệ thống. Bạn có thể thêm ghi chú đặc biệt bên dưới để AI ưu tiên áp dụng.")

    style_data = load_json_safe(PERSONAL_STYLE_FILE, {})
    phong_cach = style_data.get("phong_cach_rut_ra", {})
    ghi_chu_sop = phong_cach.get("ghi_chu_them", "")

    st.markdown("**Các quy tắc hiện tại của hệ thống (hardcoded):**")
    with st.expander("Xem danh sách quy tắc định dạng mặc định"):
        st.markdown("""
- **HPLC**: Chia 2 phần A (Điều kiện sắc ký dùng ✓) và B (Nội dung chi tiết)
- **TLC**: Chia 2 phần A (Điều kiện dùng ✓) và B (Nội dung)
- **Chuẩn độ**: Thuốc thử → Chuẩn bị mẫu → Tiến hành → Hệ số đương lượng
- **UV-Vis**: Thiết bị → Pha mẫu → Tiến hành → Tính toán
- **Karl Fischer**: Theo [Dược điển] - [Chuyên luận]
- **Định tính**: Trình bày riêng lẻ từng phép thử A, B, C...
- **Tất cả**: Bắt đầu bằng "Theo chuyên luận X - Dược điển"
        """)

    st.markdown("**Ghi chú ưu tiên đặc biệt của bạn (AI sẽ áp dụng với ưu tiên cao nhất):**")
    ghi_chu_moi = st.text_area(
        "Ghi chú đặc biệt",
        value=ghi_chu_sop,
        height=200,
        label_visibility="collapsed",
        placeholder="Ví dụ:\n- Khi viết gradient HPLC, phải dùng bảng\n- Với định tính IR, luôn ghi rõ 'Phổ hấp thụ IR của mẫu thử phải phù hợp với phổ của chất chuẩn'\n- Không dùng dấu ngoặc đơn cho đơn vị"
    )

    if st.button("💾 Lưu Ghi Chú", key="btn_save_sop_note"):
        if "phong_cach_rut_ra" not in style_data:
            style_data["phong_cach_rut_ra"] = {}
        style_data["phong_cach_rut_ra"]["ghi_chu_them"] = ghi_chu_moi.strip()
        style_data["ngay_cap_nhat"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        save_json_safe(PERSONAL_STYLE_FILE, style_data)
        st.success("✅ Đã lưu ghi chú! AI sẽ áp dụng ngay.")


# =============================
# MAIN RENDER FUNCTION
# =============================

def render_phong_cach():
    st.markdown(
        "<h2 style='text-align: center; color: #0071e3 !important; font-weight: 600; letter-spacing: -0.02em;'>"
        "🎨 Training AI</h2>",
        unsafe_allow_html=True
    )
    st.markdown(
        "<p style='text-align: center; margin-bottom: 30px;'>"
        "Dạy AI học phong cách làm hồ sơ kiểm nghiệm của bạn từ các hồ sơ mẫu thực tế.</p>",
        unsafe_allow_html=True
    )

    tab1, tab2, tab3 = st.tabs([
        "🎨 Phong Cách Cá Nhân",
        "📚 Thư Viện Hồ Sơ Mẫu",
        "📐 Quy Tắc Định Dạng"
    ])

    with tab1:
        render_tab_phong_cach()

    with tab2:
        render_tab_ho_so_mau()

    with tab3:
        render_tab_sop_guidelines()
