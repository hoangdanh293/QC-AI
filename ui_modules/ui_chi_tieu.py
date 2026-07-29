import streamlit as st
import json
import os
import time
import streamlit.components.v1 as components
from core.doc_processor import invalidate_instruction_cache

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_component_dir = os.path.join(_parent_dir, "core", "drag_drop_component")
_drag_drop_reorder = components.declare_component("drag_drop_reorder", path=_component_dir)


CRITERIA_FILE = "criteria_master.json"
METHOD_FILE = "method_library.json"

def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    # [E1] Xóa cache khi file criteria_master hoặc method_library thay đổi
    if "criteria_master" in filepath or "method_library" in filepath:
        invalidate_instruction_cache()

def update_item_keep_order(old_key, new_key, new_val, data_dict):
    new_dict = {}
    for k, v in data_dict.items():
        if k == old_key:
            new_dict[new_key] = new_val
        else:
            new_dict[k] = v
    return new_dict

def display_method_preview(selected_methods, method_lib):
    if selected_methods:
        st.markdown("<span style='font-size: 13px; color: #86868b;'>📌 Chi tiết các phương pháp đang chọn (Lấy từ Thư viện):</span>", unsafe_allow_html=True)
        for m_key in selected_methods:
            m_data = method_lib.get(m_key)
            if m_data:
                with st.expander(f"⚙️ {m_data.get('ten_phuong_phap', m_key)}", expanded=False):
                    st.caption(f"**Tag cấu trúc sẽ xuất ra:** {', '.join(list(m_data.get('cau_truc_dau_ra', {}).keys()))}")
            else:
                st.error(f"⚠️ Phương pháp '{m_key}' không còn tồn tại trong Thư viện!")

# Callback functions for AI suggestions to avoid Streamlit state exceptions
def callback_suggest_dich_edit(editing_id):
    ten_val = st.session_state.get(f"edit_ten_{editing_id}", "").strip()
    if ten_val:
        try:
            from core.ai_handler import call_ai_engine
            prompt = f"Đề xuất một ghi chú dịch thuật / từ điển bắt buộc bằng tiếng Việt cho chỉ tiêu '{ten_val}'. Ví dụ: \"Loss on drying\" BẮT BUỘC dịch là \"Mất khối lượng do làm khô\". Đưa ra câu ngắn gọn, súc tích."
            suggestion = call_ai_engine("Bạn là chuyên gia QA/QC Dược.", prompt, "Google API", "gemma-4-31b-it")
            st.session_state[f"edit_dich_val_{editing_id}"] = suggestion.strip().replace('"', '')
        except Exception as e:
            st.session_state[f"edit_chi_tieu_error_{editing_id}"] = f"Lỗi gọi AI: {str(e)}"
    else:
        st.session_state[f"edit_chi_tieu_error_{editing_id}"] = "Vui lòng điền tên hiển thị trước!"

def callback_suggest_lenh_edit(editing_id):
    ten_val = st.session_state.get(f"edit_ten_{editing_id}", "").strip()
    if ten_val:
        try:
            from core.ai_handler import call_ai_engine
            prompt = f"Viết một prompt lệnh AI bằng tiếng Việt ngắn gọn, xúc tích để yêu cầu mô hình bóc tách chỉ tiêu '{ten_val}' (mã '{editing_id}'). Yêu cầu mô hình copy nguyên văn quy trình chi tiết, thông số và cách thực hiện. Trả về trực tiếp prompt, không chứa lời dẫn."
            suggestion = call_ai_engine("Bạn là chuyên gia QA/QC Dược.", prompt, "Google API", "gemma-4-31b-it")
            st.session_state[f"edit_lenh_val_{editing_id}"] = suggestion.strip()
        except Exception as e:
            st.session_state[f"edit_chi_tieu_error_{editing_id}"] = f"Lỗi gọi AI: {str(e)}"
    else:
        st.session_state[f"edit_chi_tieu_error_{editing_id}"] = "Vui lòng điền tên hiển thị trước!"

def callback_suggest_rules_edit(editing_id):
    ten_val = st.session_state.get(f"edit_ten_{editing_id}", "").strip()
    if ten_val:
        try:
            from core.ai_handler import call_ai_engine
            prompt = f"Hãy đề xuất hướng dẫn Dạy AI (định nghĩa tag là gì, vai trò thế nào) và quy tắc xử lý ngữ cảnh ngắn gọn cho chỉ tiêu/định nghĩa '{ten_val}' khi bóc tách từ các nguồn: COA (nếu có giới hạn số), Dược điển (nếu có sắc ký), MOA (thao tác). Trả về định dạng JSON 4 trường: Training, COA, Duoc_dien, MOA."
            suggestion = call_ai_engine("Bạn là chuyên gia QA/QC Dược. Trả về JSON 4 trường: Training, COA, Duoc_dien, MOA.", prompt, "Google API", "gemma-4-31b-it", is_json=True)
            import json
            rules_json = json.loads(suggestion)
            st.session_state[f"edit_training_val_{editing_id}"] = rules_json.get("Training", "")
            st.session_state[f"edit_coa_val_{editing_id}"] = rules_json.get("COA", "")
            st.session_state[f"edit_dd_val_{editing_id}"] = rules_json.get("Duoc_dien", "")
            st.session_state[f"edit_moa_val_{editing_id}"] = rules_json.get("MOA", "")
        except Exception as e:
            st.session_state[f"edit_chi_tieu_error_{editing_id}"] = f"Lỗi gọi hoặc phân tích AI: {str(e)}"
    else:
        st.session_state[f"edit_chi_tieu_error_{editing_id}"] = "Vui lòng điền tên hiển thị trước!"

def callback_suggest_dich_add():
    ten_val = st.session_state.get("add_ten_moi", "").strip()
    if ten_val:
        try:
            from core.ai_handler import call_ai_engine
            prompt = f"Đề xuất một ghi chú dịch thuật / từ điển bắt buộc bằng tiếng Việt cho chỉ tiêu '{ten_val}'. Ví dụ: \"Loss on drying\" BẮT BUỘC dịch là \"Mất khối lượng do làm khô\". Đưa ra câu ngắn gọn, súc tích."
            suggestion = call_ai_engine("Bạn là chuyên gia QA/QC Dược.", prompt, "Google API", "gemma-4-31b-it")
            st.session_state["add_dich_val"] = suggestion.strip().replace('"', '')
        except Exception as e:
            st.session_state["add_chi_tieu_error"] = f"Lỗi gọi AI: {str(e)}"
    else:
        st.session_state["add_chi_tieu_error"] = "Vui lòng điền tên chỉ tiêu trước!"

def callback_suggest_lenh_add():
    ten_val = st.session_state.get("add_ten_moi", "").strip()
    if ten_val:
        try:
            from core.ai_handler import call_ai_engine
            prompt = f"Viết một prompt lệnh AI bằng tiếng Việt ngắn gọn, xúc tích để yêu cầu mô hình bóc tách chỉ tiêu '{ten_val}'. Yêu cầu mô hình copy nguyên văn quy trình chi tiết, thông số và cách thực hiện. Trả về trực tiếp prompt, không chứa lời dẫn."
            suggestion = call_ai_engine("Bạn là chuyên gia QA/QC Dược.", prompt, "Google API", "gemma-4-31b-it")
            st.session_state["add_lenh_val"] = suggestion.strip()
        except Exception as e:
            st.session_state["add_chi_tieu_error"] = f"Lỗi gọi AI: {str(e)}"
    else:
        st.session_state["add_chi_tieu_error"] = "Vui lòng điền tên chỉ tiêu trước!"

def callback_suggest_rules_add():
    ten_val = st.session_state.get("add_ten_moi", "").strip()
    if ten_val:
        try:
            from core.ai_handler import call_ai_engine
            prompt = f"Hãy đề xuất hướng dẫn Dạy AI (định nghĩa tag là gì, vai trò thế nào) và quy tắc xử lý ngữ cảnh ngắn gọn cho chỉ tiêu/định nghĩa '{ten_val}' khi bóc tách từ các nguồn: COA (nếu có giới hạn số), Dược điển (nếu có sắc ký), MOA (thao tác). Trả về định dạng JSON 4 trường: Training, COA, Duoc_dien, MOA."
            suggestion = call_ai_engine("Bạn là chuyên gia QA/QC Dược. Trả về JSON 4 trường: Training, COA, Duoc_dien, MOA.", prompt, "Google API", "gemma-4-31b-it", is_json=True)
            import json
            rules_json = json.loads(suggestion)
            st.session_state["add_training_val"] = rules_json.get("Training", "")
            st.session_state["add_coa_val"] = rules_json.get("COA", "")
            st.session_state["add_dd_val"] = rules_json.get("Duoc_dien", "")
            st.session_state["add_moa_val"] = rules_json.get("MOA", "")
        except Exception as e:
            st.session_state["add_chi_tieu_error"] = f"Lỗi gọi hoặc phân tích AI: {str(e)}"
    else:
        st.session_state["add_chi_tieu_error"] = "Vui lòng điền tên chỉ tiêu trước!"

def callback_suggest_examples_edit(editing_id):
    ten_val = st.session_state.get(f"edit_ten_{editing_id}", "").strip()
    if ten_val:
        try:
            from core.ai_handler import call_ai_engine
            prompt = f"Đề xuất 3 cặp ví dụ Few-Shot (Văn bản gốc bằng tiếng Anh/Việt & Kết quả mong muốn dạng song ngữ Việt-Anh chốt) để dạy AI cách bóc tách chỉ tiêu/định nghĩa '{ten_val}' (mã '{editing_id}'). Trả về định dạng JSON array chứa các đối tượng có 2 trường: van_ban_goc, ket_qua_mong_muon."
            suggestion = call_ai_engine("Bạn là chuyên gia QA/QC Dược. Trả về DUY NHẤT một JSON array.", prompt, "Google API", "gemma-4-31b-it", is_json=True)
            import json
            examples_json = json.loads(suggestion)
            if isinstance(examples_json, list):
                st.session_state[f"edit_examples_val_{editing_id}"] = examples_json
        except Exception as e:
            st.session_state[f"edit_chi_tieu_error_{editing_id}"] = f"Lỗi gợi ý ví dụ từ AI: {str(e)}"
    else:
        st.session_state[f"edit_chi_tieu_error_{editing_id}"] = "Vui lòng điền tên hiển thị trước!"

def callback_suggest_examples_add():
    ten_val = st.session_state.get("add_ten_moi", "").strip()
    if ten_val:
        try:
            from core.ai_handler import call_ai_engine
            prompt = f"Đề xuất 3 cặp ví dụ Few-Shot (Văn bản gốc bằng tiếng Anh/Việt & Kết quả mong muốn dạng song ngữ Việt-Anh chốt) để dạy AI cách bóc tách chỉ tiêu/định nghĩa '{ten_val}'. Trả về định dạng JSON array chứa các đối tượng có 2 trường: van_ban_goc, ket_qua_mong_muon."
            suggestion = call_ai_engine("Bạn là chuyên gia QA/QC Dược. Trả về DUY NHẤT một JSON array.", prompt, "Google API", "gemma-4-31b-it", is_json=True)
            import json
            examples_json = json.loads(suggestion)
            if isinstance(examples_json, list):
                st.session_state["add_examples_val"] = examples_json
        except Exception as e:
            st.session_state["add_chi_tieu_error"] = f"Lỗi gợi ý ví dụ từ AI: {str(e)}"
    else:
        st.session_state["add_chi_tieu_error"] = "Vui lòng điền tên chỉ tiêu trước!"

def render_chi_tieu():
    if st.session_state.get("just_saved_criteria"):
        for skey in ["new_criteria_id_input", "add_ten_moi", "add_dich_val", "add_lenh_val", "add_training_val", "add_coa_val", "add_dd_val", "add_moa_val", "add_phuong_phap_moi", "add_bang_moi", "add_examples_val"]:
            if skey in st.session_state:
                st.session_state[skey] = "" if isinstance(st.session_state[skey], str) else []
        keys_to_del = [k for k in st.session_state.keys() if k.startswith("edit_")]
        for k in keys_to_del:
            del st.session_state[k]
        st.session_state.editing_criteria_id = None
        del st.session_state["just_saved_criteria"]

    if "editing_criteria_id" not in st.session_state:
        st.session_state.editing_criteria_id = None
    if "criteria_dnd_key" not in st.session_state:
        st.session_state.criteria_dnd_key = 0
        
    st.markdown("""
        <style>
        button[kind="secondary"] {
            background-color: #ffffff !important;
            color: #1d1d1f !important;
            border: 1px solid #d2d2d7 !important;
            border-radius: 980px !important;
            font-weight: 600 !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
        }
        button[kind="secondary"]:hover {
            background-color: #f5f5f7 !important;
            border-color: #86868b !important;
            transform: scale(0.98);
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<h2 style='text-align: center; color: #0071e3 !important; font-weight: 600; letter-spacing: -0.02em;'>📝 Quản Lý Chỉ Tiêu Và Thuật Ngữ</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; margin-bottom: 30px;'>Cấu hình Tiêu chuẩn, Lệnh AI trích xuất và liên kết Phương pháp kiểm nghiệm.</p>", unsafe_allow_html=True)
    
    criteria_data = load_json(CRITERIA_FILE)
    method_lib = load_json(METHOD_FILE)
    
    method_options = list(method_lib.keys())
    def format_method_func(m_key):
        return f"{method_lib[m_key].get('ten_phuong_phap', m_key)} ({m_key})" if m_key in method_lib else m_key

    tab1, tab2 = st.tabs(["🔍 Quản lý, Chỉnh sửa & Sắp xếp", "➕ Thêm Chỉ tiêu Mới"])

    with tab1:
        editing_id = st.session_state.get("editing_criteria_id")
        
        if editing_id and editing_id in criteria_data:
            if "edit_chi_tieu_success" in st.session_state:
                st.success(st.session_state["edit_chi_tieu_success"])
                del st.session_state["edit_chi_tieu_success"]
                time.sleep(1.5)
                st.rerun()

            st.markdown(f"#### ⚙️ Chỉnh sửa chỉ tiêu: **{criteria_data[editing_id].get('ten_hien_thi')}**")
            
            if st.button("🔙 Quay lại danh sách", key=f"back_to_list_top_criteria_{editing_id}"):
                for skey in [f"edit_dich_val_{editing_id}", f"edit_lenh_val_{editing_id}", f"edit_training_val_{editing_id}", f"edit_coa_val_{editing_id}", f"edit_dd_val_{editing_id}", f"edit_moa_val_{editing_id}", f"edit_examples_val_{editing_id}"]:
                    if skey in st.session_state:
                        del st.session_state[skey]
                st.session_state.editing_criteria_id = None
                st.rerun()
                
            v = criteria_data[editing_id]
            st.warning("⚠️ **Đang trong chế độ chỉnh sửa.**")
            
            # Khởi tạo các session state hỗ trợ tự điền từ gợi ý AI
            if f"edit_dich_val_{editing_id}" not in st.session_state:
                st.session_state[f"edit_dich_val_{editing_id}"] = v.get("tu_dien_dich", "")
            if f"edit_lenh_val_{editing_id}" not in st.session_state:
                st.session_state[f"edit_lenh_val_{editing_id}"] = v.get("lenh_ai_trich_xuat", "")
            if f"edit_examples_val_{editing_id}" not in st.session_state:
                current_examples = v.get("vi_du_mau", [])
                if not isinstance(current_examples, list):
                    current_examples = []
                st.session_state[f"edit_examples_val_{editing_id}"] = [
                    {"van_ban_goc": ex.get("van_ban_goc", ""), "ket_qua_mong_muon": ex.get("ket_qua_mong_muon", "")}
                    for ex in current_examples
                ]
                
            current_rules = v.get("quy_tac_ngu_canh", {})
            if not isinstance(current_rules, dict):
                current_rules = {}
            if f"edit_training_val_{editing_id}" not in st.session_state:
                st.session_state[f"edit_training_val_{editing_id}"] = current_rules.get("Dạy AI (Training)", "")
            if f"edit_coa_val_{editing_id}" not in st.session_state:
                st.session_state[f"edit_coa_val_{editing_id}"] = current_rules.get("COA", "")
            if f"edit_dd_val_{editing_id}" not in st.session_state:
                st.session_state[f"edit_dd_val_{editing_id}"] = current_rules.get("Dược điển", "")
            if f"edit_moa_val_{editing_id}" not in st.session_state:
                st.session_state[f"edit_moa_val_{editing_id}"] = current_rules.get("MOA", "")

            if f"edit_chi_tieu_error_{editing_id}" in st.session_state:
                st.warning(st.session_state[f"edit_chi_tieu_error_{editing_id}"])
                del st.session_state[f"edit_chi_tieu_error_{editing_id}"]

            with st.container():
                c1, c2 = st.columns(2)
                with c1:
                    edit_id = st.text_input("Mã chỉ tiêu (ID)*", value=editing_id, key=f"edit_id_{editing_id}")
                with c2:
                    edit_ten = st.text_input("Tên hiển thị*", value=v.get("ten_hien_thi", ""), key=f"edit_ten_{editing_id}")
                
                # Input từ điển dịch thuật tích hợp nút gọi AI
                col_d_1, col_d_2 = st.columns([4, 1])
                with col_d_1:
                    edit_dich = st.text_input("Ghi chú Từ điển / Dịch thuật", key=f"edit_dich_val_{editing_id}")
                with col_d_2:
                    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
                    st.button("✨ AI Gợi ý", key=f"ai_dich_edit_{editing_id}", on_click=callback_suggest_dich_edit, args=(editing_id,))
                
                edit_loai = st.selectbox(
                    "Loại khai báo*",
                    options=["Chỉ tiêu", "Định nghĩa", "Cả hai"],
                    index=["Chỉ tiêu", "Định nghĩa", "Cả hai"].index(v.get("loai_khai_bao", "Chỉ tiêu")),
                    key=f"edit_loai_{editing_id}"
                )

                current_muc = v.get("cap_do_phan_muc", 2)
                try:
                    muc_index = [1, 2, 3, 4].index(int(current_muc))
                except Exception:
                    muc_index = 1
                
                edit_muc = st.selectbox(
                    "Cấp độ phân mức (Phân cấp Dược điển)*",
                    options=[
                        "Mức 1: Nhóm lớn (Characters, Identification...)",
                        "Mức 2: Chỉ tiêu con (Tính chất, Độ tan, Định tính A...)",
                        "Mức 3: Khái niệm trong chỉ tiêu / Thuộc tính (Cột sắc ký, Pha động, Tốc độ dòng...)",
                        "Mức 4: Chi tiết cấu hình con nhỏ hơn (Hệ số K, chiều dài cột...)"
                    ],
                    index=muc_index,
                    help="Cấp độ phân tầng giúp AI hiểu được cấu trúc nhóm lớn/nhóm nhỏ và thuộc tính bóc tách.",
                    key=f"edit_muc_{editing_id}"
                )

                # Input Lệnh AI tích hợp nút gọi AI
                col_l_1, col_l_2 = st.columns([4, 1])
                with col_l_1:
                    lenh_label = "Lệnh AI Trích xuất (Prompt)" + ("*" if edit_loai in ["Chỉ tiêu", "Cả hai"] else "")
                    edit_lenh = st.text_area(lenh_label, key=f"edit_lenh_val_{editing_id}", height=150)
                with col_l_2:
                    st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
                    st.button("✨ AI Gợi ý", key=f"ai_lenh_edit_{editing_id}", on_click=callback_suggest_lenh_edit, args=(editing_id,))
                
                st.markdown("**Liên kết Phương pháp & Biểu mẫu:**")
                current_methods = v.get("phuong_phap_ap_dung", [])
                valid_current_methods = [m for m in current_methods if m in method_options]
                
                edit_methods = st.multiselect(
                    "Chọn các Phương pháp áp dụng (Chỉ bắt buộc đối với Chỉ tiêu)" + ("*" if edit_loai in ["Chỉ tiêu", "Cả hai"] else ""), 
                    options=method_options,
                    default=valid_current_methods,
                    format_func=format_method_func,
                    key=f"edit_methods_{editing_id}"
                )
                
                display_method_preview(edit_methods, method_lib)
                
                edit_bang = st.text_input("Tên bảng điền Form Word (Nếu có)", value=v.get("bang_di_kem", ""), placeholder="VD: bang_dinh_luong", key=f"edit_bang_{editing_id}")
                
                # Cấu hình quy tắc ngữ cảnh tích hợp AI
                with st.expander("🧠 Quy tắc phân biệt ngữ cảnh (Dạy AI)", expanded=False):
                    st.caption("Dạy AI cách xử lý chỉ tiêu này trong các tình huống tài liệu khác nhau.")
                    st.button("✨ AI Đề xuất Hướng dẫn Dạy AI & Quy tắc", key=f"ai_rules_edit_{editing_id}", on_click=callback_suggest_rules_edit, args=(editing_id,))
                    
                    edit_rule_training = st.text_area("Dạy AI (Training) / Định nghĩa tổng quát", key=f"edit_training_val_{editing_id}", placeholder="Mô tả tag này là gì, có ý nghĩa gì, vai trò thế nào để AI hiểu...")
                    edit_rule_coa = st.text_area("Khi gặp trong COA / Phiếu phân tích", key=f"edit_coa_val_{editing_id}", placeholder="Ví dụ: Nếu có kết quả số, lấy số làm giới hạn chốt...")
                    edit_rule_dd = st.text_area("Khi gặp trong Dược điển / Chuyên luận", key=f"edit_dd_val_{editing_id}", placeholder="Ví dụ: Bóc tách chi tiết các bước pha mẫu...")
                    edit_rule_moa = st.text_area("Khi gặp trong MOA / Quy trình phân tích", key=f"edit_moa_val_{editing_id}", placeholder="Ví dụ: Lấy quy trình thao tác...")

                # Ví dụ mẫu Few-Shot tích hợp AI
                col_ex_title, col_ex_btn = st.columns([3, 1])
                with col_ex_title:
                    st.markdown("**Các ví dụ mẫu (Few-Shot Training) để dạy AI cách bóc tách/dịch:**")
                with col_ex_btn:
                    st.button("✨ AI Gợi ý Ví dụ", key=f"ai_exs_edit_{editing_id}", on_click=callback_suggest_examples_edit, args=(editing_id,))
                
                edited_examples = st.data_editor(
                    st.session_state[f"edit_examples_val_{editing_id}"] + [{"van_ban_goc": "", "ket_qua_mong_muon": ""} for _ in range(2)],
                    num_rows="dynamic",
                    column_config={
                        "van_ban_goc": st.column_config.TextColumn("Văn bản gốc (Tiếng Anh / Tiếng Việt)", width="large"),
                        "ket_qua_mong_muon": st.column_config.TextColumn("Nội dung mong muốn xuất ra (Dòng chốt)", width="large")
                    },
                    use_container_width=True,
                    key=f"examples_editor_{editing_id}"
                )

                btn_translate_ex = st.button("✨ AI Tự động Dịch Song ngữ các ví dụ đã nhập", key=f"btn_translate_ex_{editing_id}", help="Tự động dịch các dòng văn bản gốc chưa có nội dung mong muốn hoặc chưa có dạng song ngữ sang song ngữ Việt-Anh")
                if btn_translate_ex:
                    with st.spinner("Đang dịch song ngữ bằng AI..."):
                        from core.ai_handler import translate_text_to_bilingual
                        new_examples = []
                        for row in edited_examples:
                            v_goc = str(row.get("van_ban_goc", "")).strip()
                            k_qua = str(row.get("ket_qua_mong_muon", "")).strip()
                            if v_goc:
                                if not k_qua or '/' not in k_qua:
                                    try:
                                        context_type = "sop" if len(v_goc) > 50 or "\n" in v_goc or "." in v_goc else "limit"
                                        translated = translate_text_to_bilingual(v_goc, "Google API", "gemma-4-31b-it", context_type=context_type)
                                        k_qua = translated
                                    except Exception as e:
                                        st.error(f"Lỗi khi dịch dòng '{v_goc}': {e}")
                                new_examples.append({"van_ban_goc": v_goc, "ket_qua_mong_muon": k_qua})
                        st.session_state[f"edit_examples_val_{editing_id}"] = new_examples
                        widget_key = f"examples_editor_{editing_id}"
                        if widget_key in st.session_state:
                            del st.session_state[widget_key]
                        st.rerun()

                c_btn1, c_btn2 = st.columns([1, 4])
                with c_btn1:
                    btn_save = st.button("💾 Lưu Cập Nhật", type="primary", key=f"save_edit_btn_{editing_id}")
                    
                if btn_save:
                    new_id = edit_id.strip()
                    is_valid = True
                    if not new_id or not edit_ten.strip():
                        st.error("❌ Mã ID và Tên hiển thị không được để trống!")
                        is_valid = False
                    elif edit_loai in ["Chỉ tiêu", "Cả hai"] and not edit_lenh.strip():
                        st.error("❌ Lệnh AI trích xuất không được để trống đối với Chỉ tiêu!")
                        is_valid = False
                    elif edit_loai in ["Chỉ tiêu", "Cả hai"] and not edit_methods:
                        st.error("❌ Vui lòng chọn ít nhất 1 Phương pháp áp dụng cho Chỉ tiêu!")
                        is_valid = False
                    elif new_id != editing_id and new_id in criteria_data:
                        st.error(f"❌ Mã ID '{new_id}' đã tồn tại ở một chỉ tiêu khác!")
                        is_valid = False
                    
                    if is_valid:
                        # Parse dynamic examples
                        examples_list = [
                            {"van_ban_goc": str(row.get("van_ban_goc", "")).strip(), "ket_qua_mong_muon": str(row.get("ket_qua_mong_muon", "")).strip()}
                            for row in edited_examples
                            if str(row.get("van_ban_goc", "")).strip() and str(row.get("ket_qua_mong_muon", "")).strip()
                        ]

                        new_data = {
                            "ten_hien_thi": edit_ten.strip(),
                            "tu_dien_dich": edit_dich.strip(),
                            "loai_khai_bao": edit_loai,
                            "cap_do_phan_muc": int(edit_muc.split(":")[0].replace("Mức ", "").strip()),
                            "lenh_ai_trich_xuat": edit_lenh.strip(),
                            "phuong_phap_ap_dung": edit_methods,
                            "quy_tac_ngu_canh": {
                                "Dạy AI (Training)": edit_rule_training.strip(),
                                "COA": edit_rule_coa.strip(),
                                "Dược điển": edit_rule_dd.strip(),
                                "MOA": edit_rule_moa.strip()
                            },
                            "vi_du_mau": examples_list
                        }
                        if edit_bang.strip():
                            new_data["bang_di_kem"] = edit_bang.strip()
                            
                        criteria_data = update_item_keep_order(editing_id, new_id, new_data, criteria_data)
                        save_json(CRITERIA_FILE, criteria_data)
                        
                        st.session_state["just_saved_criteria"] = True
                        st.session_state["edit_chi_tieu_success"] = f"✅ Đã cập nhật thành công chỉ tiêu '{edit_ten}'!"
                        st.rerun()
        else:
            st.markdown("#### Tìm kiếm và Cập nhật Chỉ tiêu hiện tại")
            search_term = st.text_input("🔍 Nhập mã hoặc tên chỉ tiêu (Ví dụ: dinh_luong, cảm quan...):", key="search_criteria")
            is_searching = bool(search_term.strip())
            
            if is_searching:
                st.info("💡 Lưu ý: Chức năng Sắp xếp vị trí bị vô hiệu hóa khi đang tìm kiếm để tránh sai lệch dữ liệu.")

            # Filter/Format criteria list for DND component
            criteria_items_for_dnd = []
            for k in criteria_data.keys():
                v = criteria_data[k]
                search_string = f"{k} {v.get('ten_hien_thi', '')} {v.get('tu_dien_dich', '')}".lower()
                if not search_term or search_term.lower() in search_string:
                    criteria_items_for_dnd.append({
                        "type": "criteria",
                        "id": k,
                        "ten_hien_thi": v.get("ten_hien_thi", ""),
                        "loai_khai_bao": v.get("loai_khai_bao", "Chỉ tiêu"),
                        "cap_do_phan_muc": v.get("cap_do_phan_muc", 2),
                        "tu_dien_dich": v.get("tu_dien_dich", ""),
                        "bang_di_kem": v.get("bang_di_kem", ""),
                        "lenh_ai_trich_xuat": v.get("lenh_ai_trich_xuat", ""),
                        "methods": [
                            {
                                "id": m_key,
                                "name": method_lib[m_key].get('ten_phuong_phap', m_key)
                            }
                            for m_key in v.get("phuong_phap_ap_dung", [])
                            if m_key in method_lib
                        ]
                    })

            if criteria_items_for_dnd:
                st.markdown("<p style='font-size: 13px; color: #86868b; margin-bottom: 8px;'>💡 Sử dụng tay nắm (⋮⋮) bên trái mỗi thẻ để kéo thả trực tiếp và sắp xếp lại thứ tự.</p>", unsafe_allow_html=True)
                new_order = _drag_drop_reorder(
                    items=criteria_items_for_dnd,
                    key=f"criteria_dnd_reorder_{st.session_state.criteria_dnd_key}",
                    default=criteria_items_for_dnd,
                    disable_drag=is_searching
                )

                if isinstance(new_order, dict) and "action" in new_order:
                    action = new_order["action"]
                    act_id = new_order["id"]
                    st.session_state.criteria_dnd_key += 1
                    
                    if action == "edit":
                        st.session_state.editing_criteria_id = act_id
                        st.rerun()
                    elif action == "delete":
                        if act_id in criteria_data:
                            del criteria_data[act_id]
                            save_json(CRITERIA_FILE, criteria_data)
                            st.success(f"✅ Đã xóa thành công chỉ tiêu '{act_id}'!")
                            time.sleep(1)
                            st.rerun()

                elif isinstance(new_order, list) and not is_searching:
                    current_keys = [item["id"] for item in criteria_items_for_dnd]
                    new_keys = [item["id"] for item in new_order if isinstance(item, dict) and "id" in item]
                    if new_keys and new_keys != current_keys:
                        new_criteria_data = {item_id: criteria_data[item_id] for item_id in new_keys if item_id in criteria_data}
                        # Keep remaining keys that might have been filtered out during search
                        for kkey in criteria_data.keys():
                            if kkey not in new_criteria_data:
                                new_criteria_data[kkey] = criteria_data[kkey]
                        save_json(CRITERIA_FILE, new_criteria_data)
                        st.rerun()
            else:
                if is_searching:
                    st.error("❌ Không tìm thấy chỉ tiêu nào khớp với từ khóa tìm kiếm!")
                else:
                    st.info("Danh mục chỉ tiêu đang trống!")
 
    with tab2:
        if "add_chi_tieu_success" in st.session_state:
            st.success(st.session_state["add_chi_tieu_success"])
            del st.session_state["add_chi_tieu_success"]
            time.sleep(1.5)
            st.rerun()

        st.markdown("#### Khai báo Chỉ tiêu / Định nghĩa mới")
        
        # Khởi tạo các session state cho Form Thêm mới chỉ tiêu
        if "add_dich_val" not in st.session_state: st.session_state.add_dich_val = ""
        if "add_lenh_val" not in st.session_state: st.session_state.add_lenh_val = ""
        if "add_training_val" not in st.session_state: st.session_state.add_training_val = ""
        if "add_coa_val" not in st.session_state: st.session_state.add_coa_val = ""
        if "add_dd_val" not in st.session_state: st.session_state.add_dd_val = ""
        if "add_moa_val" not in st.session_state: st.session_state.add_moa_val = ""
        if "add_examples_val" not in st.session_state: st.session_state.add_examples_val = []

        # Nhập mã ID ngoài form để hỗ trợ kiểm tra tồn tại và gợi ý ngay lập tức
        col_chk_1, col_chk_2 = st.columns([2, 3])
        with col_chk_1:
            ma_moi = st.text_input("Mã ID (Tag)*", placeholder="VD: do_am, cot_sac_ky_hplc (Viết liền không dấu)", key="new_criteria_id_input")
        with col_chk_2:
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True) # Spacer
            if ma_moi.strip():
                ma_moi_clean = ma_moi.strip().lower()
                if ma_moi_clean in criteria_data:
                    st.error(f"⚠️ Đã tồn tại ID này: '{criteria_data[ma_moi_clean].get('ten_hien_thi')}' ({criteria_data[ma_moi_clean].get('loai_khai_bao')})")
                else:
                    st.success("✅ Mã ID chưa tồn tại. Hợp lệ!")
                
                # Tìm các ID tương tự đã có
                similar_ids = [k for k in criteria_data.keys() if ma_moi_clean in k.lower()]
                if similar_ids:
                    st.caption(f"💡 Mã tương tự đã có: {', '.join(similar_ids[:10])}{'...' if len(similar_ids) > 10 else ''}")
            else:
                st.caption(f"📋 Tổng số: {len(criteria_data)} ID. Ví dụ: {', '.join(list(criteria_data.keys())[:5])}...")
        if "add_chi_tieu_error" in st.session_state:
            st.warning(st.session_state["add_chi_tieu_error"])
            del st.session_state["add_chi_tieu_error"]

        with st.container():
            ten_moi = st.text_input("Tên hiển thị*", placeholder="VD: Giới hạn độ ẩm, Cột sắc ký HPLC", key="add_ten_moi")
                
            # Input dịch thuật dịch nghĩa tích hợp AI
            col_d_1, col_d_2 = st.columns([4, 1])
            with col_d_1:
                dich_moi = st.text_input("Ghi chú Từ điển / Dịch thuật", key="add_dich_val", placeholder='VD: "Moisture" BẮT BUỘC dịch là "Độ ẩm"')
            with col_d_2:
                st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
                st.button("✨ AI Gợi ý", key="ai_dich_add", on_click=callback_suggest_dich_add)
            
            loai_moi = st.selectbox(
                "Loại khai báo*",
                options=["Chỉ tiêu", "Định nghĩa", "Cả hai"],
                index=0,
                key="add_loai_moi"
            )
            
            new_muc = st.selectbox(
                "Cấp độ phân mức (Phân cấp Dược điển)*",
                options=[
                    "Mức 1: Nhóm lớn (Characters, Identification...)",
                    "Mức 2: Chỉ tiêu con (Tính chất, Độ tan, Định tính A...)",
                    "Mức 3: Khái niệm trong chỉ tiêu / Thuộc tính (Cột sắc ký, Pha động, Tốc độ dòng...)",
                    "Mức 4: Chi tiết cấu hình con nhỏ hơn (Hệ số K, chiều dài cột...)"
                ],
                index=1, # Default to Mức 2 (Chỉ tiêu con)
                help="Cấp độ phân tầng giúp AI hiểu được cấu trúc nhóm lớn/nhóm nhỏ và thuộc tính bóc tách.",
                key="add_new_muc"
            )
            
            # Input Lệnh Prompt tích hợp AI
            col_l_1, col_l_2 = st.columns([4, 1])
            with col_l_1:
                lenh_moi_label = "Lệnh AI Trích xuất (Prompt)" + ("*" if loai_moi in ["Chỉ tiêu", "Cả hai"] else "")
                lenh_moi = st.text_area(lenh_moi_label, key="add_lenh_val", placeholder="VD: COPY NGUYÊN VĂN 100% mọi nội dung về Độ ẩm.", height=100)
            with col_l_2:
                st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
                st.button("✨ AI Gợi ý", key="ai_lenh_add", on_click=callback_suggest_lenh_add)
            
            st.markdown("**Liên kết Phương pháp & Biểu mẫu:**")
            phuong_phap_moi = st.multiselect(
                "Chọn các Phương pháp áp dụng (Chỉ bắt buộc đối với Chỉ tiêu)" + ("*" if loai_moi in ["Chỉ tiêu", "Cả hai"] else ""), 
                options=method_options,
                format_func=format_method_func,
                key="add_phuong_phap_moi"
            )
            display_method_preview(phuong_phap_moi, method_lib)
            
            bang_moi = st.text_input("Tên bảng điền Form Word (Nếu có)", placeholder="VD: bang_do_am", key="add_bang_moi")
            
            # Quy tắc ngữ cảnh tích hợp AI
            with st.expander("🧠 Quy tắc phân biệt ngữ cảnh (Dạy AI)", expanded=False):
                st.caption("Dạy AI cách xử lý chỉ tiêu này trong các tình huống tài liệu khác nhau.")
                st.button("✨ AI Đề xuất Hướng dẫn Dạy AI & Quy tắc", key="ai_rules_add", on_click=callback_suggest_rules_add)
                        
                moi_rule_training = st.text_area("Dạy AI (Training) / Định nghĩa tổng quát", key="add_training_val", placeholder="Mô tả tag này là gì, có ý nghĩa gì, vai trò thế nào để AI hiểu...")
                moi_rule_coa = st.text_area("Khi gặp trong COA / Phiếu phân tích", key="add_coa_val", placeholder="Ví dụ: Nếu có kết quả số, lấy số làm giới hạn chốt...")
                moi_rule_dd = st.text_area("Khi gặp trong Dược điển / Chuyên luận", key="add_dd_val", placeholder="Ví dụ: Bóc tách chi tiết các bước pha mẫu...")
                moi_rule_moa = st.text_area("Khi gặp trong MOA / Quy trình phân tích", key="add_moa_val", placeholder="Ví dụ: Lấy quy trình thao tác...")
 
            # Ví dụ mẫu Few-Shot tích hợp AI
            col_ex_title, col_ex_btn = st.columns([3, 1])
            with col_ex_title:
                st.markdown("**Các ví dụ mẫu (Few-Shot Training) để dạy AI cách bóc tách/dịch:**")
            with col_ex_btn:
                st.button("✨ AI Gợi ý Ví dụ", key="ai_exs_add", on_click=callback_suggest_examples_add)
            
            edited_add_examples = st.data_editor(
                st.session_state.add_examples_val + [{"van_ban_goc": "", "ket_qua_mong_muon": ""} for _ in range(2)],
                num_rows="dynamic",
                column_config={
                    "van_ban_goc": st.column_config.TextColumn("Văn bản gốc (Tiếng Anh / Tiếng Việt)", width="large"),
                    "ket_qua_mong_muon": st.column_config.TextColumn("Nội dung mong muốn xuất ra (Dòng chốt)", width="large")
                },
                use_container_width=True,
                key="examples_editor_add"
            )

            btn_translate_add_ex = st.button("✨ AI Tự động Dịch Song ngữ các ví dụ đã nhập", key="btn_translate_add_ex", help="Tự động dịch các dòng văn bản gốc chưa có nội dung mong muốn sang song ngữ Việt-Anh")
            if btn_translate_add_ex:
                with st.spinner("Đang dịch song ngữ bằng AI..."):
                    from core.ai_handler import translate_text_to_bilingual
                    new_examples = []
                    for row in edited_add_examples:
                        v_goc = str(row.get("van_ban_goc", "")).strip()
                        k_qua = str(row.get("ket_qua_mong_muon", "")).strip()
                        if v_goc:
                            if not k_qua or '/' not in k_qua:
                                try:
                                    context_type = "sop" if len(v_goc) > 50 or "\n" in v_goc or "." in v_goc else "limit"
                                    translated = translate_text_to_bilingual(v_goc, "Google API", "gemma-4-31b-it", context_type=context_type)
                                    k_qua = translated
                                except Exception as e:
                                    st.error(f"Lỗi khi dịch dòng '{v_goc}': {e}")
                            new_examples.append({"van_ban_goc": v_goc, "ket_qua_mong_muon": k_qua})
                    st.session_state.add_examples_val = new_examples
                    widget_key = "examples_editor_add"
                    if widget_key in st.session_state:
                        del st.session_state[widget_key]
                    st.rerun()

            btn_add = st.button("💾 Thêm Mới Chỉ Tiêu / Định Nghĩa", type="primary", key="add_new_criteria_btn")
            
            if btn_add:
                new_id = ma_moi.strip()
                is_valid = True
                if not new_id or not ten_moi.strip():
                    st.error("❌ Mã ID và Tên hiển thị không được để trống!")
                    is_valid = False
                elif loai_moi in ["Chỉ tiêu", "Cả hai"] and not lenh_moi.strip():
                    st.error("❌ Lệnh AI trích xuất không được để trống đối với Chỉ tiêu!")
                    is_valid = False
                elif loai_moi in ["Chỉ tiêu", "Cả hai"] and not phuong_phap_moi:
                    st.error("❌ Vui lòng chọn ít nhất 1 Phương pháp áp dụng cho Chỉ tiêu!")
                    is_valid = False
                elif new_id in criteria_data:
                    st.error(f"❌ Mã chỉ tiêu '{new_id}' đã tồn tại! Vui lòng chọn mã khác hoặc sang tab Tra cứu để sửa.")
                    is_valid = False
                
                if is_valid:
                    # Parse dynamic examples
                    examples_list = [
                        {"van_ban_goc": str(row.get("van_ban_goc", "")).strip(), "ket_qua_mong_muon": str(row.get("ket_qua_mong_muon", "")).strip()}
                        for row in edited_add_examples
                        if str(row.get("van_ban_goc", "")).strip() and str(row.get("ket_qua_mong_muon", "")).strip()
                    ]

                    new_obj = {
                        "ten_hien_thi": ten_moi.strip(),
                        "tu_dien_dich": dich_moi.strip(),
                        "loai_khai_bao": loai_moi,
                        "cap_do_phan_muc": int(new_muc.split(":")[0].replace("Mức ", "").strip()),
                        "lenh_ai_trich_xuat": lenh_moi.strip(),
                        "phuong_phap_ap_dung": phuong_phap_moi,
                        "quy_tac_ngu_canh": {
                            "Dạy AI (Training)": moi_rule_training.strip(),
                            "COA": moi_rule_coa.strip(),
                            "Dược điển": moi_rule_dd.strip(),
                            "MOA": moi_rule_moa.strip()
                        },
                        "vi_du_mau": examples_list
                    }
                    if bang_moi.strip():
                        new_obj["bang_di_kem"] = bang_moi.strip()
                        
                    criteria_data[new_id] = new_obj
                    save_json(CRITERIA_FILE, criteria_data)
                    
                    st.session_state["just_saved_criteria"] = True
                    st.session_state["add_chi_tieu_success"] = f"✅ Đã thêm chỉ tiêu '{ten_moi}' thành công!"
                    st.rerun()