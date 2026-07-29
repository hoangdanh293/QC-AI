import streamlit as st
import json
import os
import time
import streamlit.components.v1 as components
from core.doc_processor import invalidate_instruction_cache

METHOD_FILE = "method_library.json"

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_component_dir = os.path.join(_parent_dir, "core", "drag_drop_component")
_drag_drop_reorder = components.declare_component("drag_drop_reorder", path=_component_dir)

def load_method_lib():
    if os.path.exists(METHOD_FILE):
        with open(METHOD_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    return {}

def save_method_lib(data):
    with open(METHOD_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=4)
    # [E1] Xóa cache khi method_library thay đổi
    invalidate_instruction_cache()

def update_item_keep_order(old_key, new_key, new_val, lib_data):
    new_dict = {}
    for k, v in lib_data.items():
        if k == old_key:
            new_dict[new_key] = new_val
        else:
            new_dict[k] = v
    return new_dict

def render_thu_vien():
    if "editing_method_id" not in st.session_state:
        st.session_state.editing_method_id = None
    if "method_dnd_key" not in st.session_state:
        st.session_state.method_dnd_key = 0
        
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

    st.markdown("<h2 style='text-align: center; color: #0071e3 !important; font-weight: 600; letter-spacing: -0.02em;'>📚 Quản Lý Thư Viện Phương Pháp Cốt Lõi</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; margin-bottom: 30px;'>Công cụ dành cho QA/QC quản lý và dạy AI các khái niệm kiểm nghiệm mới.</p>", unsafe_allow_html=True)
    
    lib_data = load_method_lib()
    
    # Load criteria tags to auto-suggest
    criteria_file = "criteria_master.json"
    criteria_keys = []
    if os.path.exists(criteria_file):
        try:
            with open(criteria_file, 'r', encoding='utf-8') as f:
                c_data = json.load(f)
                criteria_keys = sorted(list(c_data.keys()))
        except Exception:
            pass
    criteria_options = [""] + criteria_keys

    tab1, tab2 = st.tabs(["🔍 Quản lý, Chỉnh sửa & Sắp xếp", "➕ Thêm Phương pháp Mới"])
 
    # ==========================================
    # TAB 1: TRA CỨU, CHỈNH SỬA, XÓA & SẮP XẾP
    # ==========================================
    with tab1:
        editing_id = st.session_state.get("editing_method_id")
        
        if editing_id and editing_id in lib_data:
            st.markdown(f"#### ⚙️ Chỉnh sửa phương pháp: **{lib_data[editing_id].get('ten_phuong_phap')}**")
            
            if st.button("🔙 Quay lại danh sách", key=f"back_to_list_top_lib_{editing_id}"):
                for skey in [f"edit_tags_val_{editing_id}", f"edit_examples_val_{editing_id}"]:
                    if skey in st.session_state:
                        del st.session_state[skey]
                st.session_state.editing_method_id = None
                st.rerun()
                
            v = lib_data[editing_id]
            st.warning("⚠️ **Đang trong chế độ chỉnh sửa.**")
            
            # Khởi tạo session state hỗ trợ gợi ý AI cho Thuộc tính và Ví dụ Few-Shot
            if f"edit_tags_val_{editing_id}" not in st.session_state:
                current_tags = [{"ma_thuoc_tinh": t_k, "mo_ta": t_v} for t_k, t_v in v.get("cau_truc_dau_ra", {}).items()]
                st.session_state[f"edit_tags_val_{editing_id}"] = current_tags
                
            if f"edit_examples_val_{editing_id}" not in st.session_state:
                current_examples = v.get("vi_du_mau", [])
                if not isinstance(current_examples, list):
                    current_examples = []
                st.session_state[f"edit_examples_val_{editing_id}"] = [
                    {"van_ban_goc": ex.get("van_ban_goc", ""), "ket_qua_mong_muon": ex.get("ket_qua_mong_muon", "")}
                    for ex in current_examples
                ]

            with st.container():
                edit_id = st.text_input("Mã phương pháp (ID)*", value=editing_id)
                edit_name = st.text_input("Tên hiển thị*", value=v.get('ten_phuong_phap', ''))
                
                c_in, c_ex = st.columns(2)
                with c_in: 
                    edit_in = st.text_input("Từ khóa nhận diện", value=", ".join(v.get('tu_khoa_nhan_dien', [])))
                with c_ex: 
                    edit_ex = st.text_input("Từ khóa loại trừ", value=", ".join(v.get('tu_khoa_loai_tru', [])))
                    
                # Thuộc tính (Tag) bóc tách tích hợp AI
                col_tag_title, col_tag_btn = st.columns([3, 1])
                with col_tag_title:
                    st.markdown("**Chỉnh sửa các thuộc tính (Tag) bóc tách:**")
                with col_tag_btn:
                    if st.button("✨ AI Gợi ý Thuộc tính", key=f"ai_tags_edit_{editing_id}"):
                        if edit_name.strip():
                            with st.spinner("AI đang gợi ý thuộc tính..."):
                                from core.ai_handler import call_ai_engine
                                prompt = f"Hãy gợi ý danh sách các mã thuộc tính (Tag) và mô tả nhiệm vụ trích xuất tương ứng cho phương pháp '{edit_name.strip()}' (ID '{editing_id}'). Các mã thuộc tính bắt buộc phải chọn trong các từ khóa sau: {', '.join(criteria_keys)}.\nTrả về dạng JSON array của các object có 2 trường: ma_thuoc_tinh, mo_ta."
                                suggestion = call_ai_engine("Bạn là chuyên gia QA/QC Dược. Trả về DUY NHẤT JSON array.", prompt, "Google API", "gemma-4-31b-it", is_json=True)
                                try:
                                    import json
                                    tags_json = json.loads(suggestion)
                                    if isinstance(tags_json, list):
                                        st.session_state[f"edit_tags_val_{editing_id}"] = [t for t in tags_json if t.get("ma_thuoc_tinh") in criteria_keys]
                                except:
                                    st.error("❌ Lỗi phân tích cú pháp JSON từ AI.")
                                st.rerun()
                        else:
                            st.warning("Vui lòng nhập tên hiển thị trước!")
                
                edited_data = st.data_editor(
                    st.session_state[f"edit_tags_val_{editing_id}"] + [{"ma_thuoc_tinh": "", "mo_ta": ""} for _ in range(3)],
                    num_rows="dynamic",
                    column_config={
                        "ma_thuoc_tinh": st.column_config.SelectboxColumn(
                            "Mã thuộc tính (Tag)*", 
                            options=criteria_options,
                            width="medium",
                            help="Chọn mã tag đã đăng ký trong Quản Lý Chỉ Tiêu Và Thuật Ngữ"
                        ),
                        "mo_ta": st.column_config.TextColumn("Mô tả để AI hiểu*", width="large")
                    },
                    use_container_width=True,
                    key=f"editor_{editing_id}"
                )
                btn_col1, _ = st.columns([1.5, 4.5])
                with btn_col1:
                    save_clicked = st.button("💾 Lưu Cập Nhật", type="primary")
                    
                if save_clicked:
                    new_id = edit_id.strip()
                    if not new_id or not edit_name.strip():
                        st.error("❌ Mã phương pháp và Tên hiển thị không được để trống!")
                    elif new_id != editing_id and new_id in lib_data:
                        st.error(f"❌ Mã ID '{new_id}' đã tồn tại! Vui lòng chọn mã khác.")
                    else:
                        list_nhan_dien = [x.strip() for x in edit_in.split(",") if x.strip()]
                        list_loai_tru = [x.strip() for x in edit_ex.split(",") if x.strip()]
                        cau_truc_dict = {str(row.get("ma_thuoc_tinh", "")).strip(): str(row.get("mo_ta", "")).strip() 
                                         for row in edited_data if str(row.get("ma_thuoc_tinh", "")).strip() and str(row.get("mo_ta", "")).strip()}
                        
                        # Giữ lại vi_du_mau cũ (không xóa dữ liệu đã có từ trước)
                        existing_examples = v.get("vi_du_mau", [])
                        
                        new_obj = {
                            "ten_phuong_phap": edit_name.strip(),
                            "tu_khoa_nhan_dien": list_nhan_dien,
                            "tu_khoa_loai_tru": list_loai_tru,
                            "cau_truc_dau_ra": cau_truc_dict,
                            "vi_du_mau": existing_examples
                        }
                        
                        lib_data = update_item_keep_order(editing_id, new_id, new_obj, lib_data)
                        save_method_lib(lib_data)
                        
                        # Dọn dẹp session state sau khi lưu thành công
                        for skey in [f"edit_tags_val_{editing_id}", f"edit_examples_val_{editing_id}"]:
                            if skey in st.session_state:
                                del st.session_state[skey]
                                
                        st.session_state.editing_method_id = None
                        st.success(f"✅ Đã cập nhật thành công!")
                        time.sleep(1)
                        st.rerun()
        else:
            st.markdown("#### Danh sách các phương pháp trong hệ thống")
            search_term = st.text_input("🔍 Nhập mã, tên phương pháp hoặc thuộc tính để tìm kiếm:", key="search_method_lib")
            is_searching = bool(search_term.strip())
            
            if is_searching:
                st.info("💡 Lưu ý: Chức năng Sắp xếp vị trí bị vô hiệu hóa khi đang tìm kiếm để tránh sai lệch dữ liệu.")

            # Lọc danh sách phương pháp phù hợp với từ khóa
            method_items_for_dnd = []
            for k in lib_data.keys():
                v = lib_data[k]
                search_string = f"{k} {v.get('ten_phuong_phap', '')} {' '.join(v.get('tu_khoa_nhan_dien', []))}".lower()
                if not search_term or search_term.lower() in search_string:
                    method_items_for_dnd.append({
                        "type": "method",
                        "id": k,
                        "ten_phuong_phap": v.get("ten_phuong_phap", ""),
                        "tu_khoa_nhan_dien": v.get("tu_khoa_nhan_dien", []),
                        "tu_khoa_loai_tru": v.get("tu_khoa_loai_tru", []),
                        "cau_truc_dau_ra": v.get("cau_truc_dau_ra", {})
                    })

            if method_items_for_dnd:
                st.markdown("<p style='font-size: 13px; color: #86868b; margin-bottom: 8px;'>💡 Sử dụng tay nắm (⋮⋮) bên trái mỗi thẻ để kéo thả trực tiếp và sắp xếp lại thứ tự.</p>", unsafe_allow_html=True)
                new_order = _drag_drop_reorder(
                    items=method_items_for_dnd,
                    key=f"method_dnd_reorder_{st.session_state.method_dnd_key}",
                    default=method_items_for_dnd,
                    disable_drag=is_searching
                )
                
                # Xử lý các sự kiện phản hồi từ component
                if isinstance(new_order, dict) and "action" in new_order:
                    action = new_order["action"]
                    act_id = new_order["id"]
                    # Reset component key để tránh lặp lại hành động
                    st.session_state.method_dnd_key += 1
                    
                    if action == "edit":
                        st.session_state.editing_method_id = act_id
                        st.rerun()
                    elif action == "delete":
                        if act_id in lib_data:
                            del lib_data[act_id]
                            save_method_lib(lib_data)
                            st.success(f"✅ Đã xóa thành công phương pháp '{act_id}' khỏi Thư viện!")
                            time.sleep(1)
                            st.rerun()
                            
                elif isinstance(new_order, list) and not is_searching:
                    # Kiểm tra xem thứ tự các key có thay đổi thực sự không
                    current_keys = [item["id"] for item in method_items_for_dnd]
                    new_keys = [item["id"] for item in new_order if isinstance(item, dict) and "id" in item]
                    if new_keys and new_keys != current_keys:
                        new_lib_data = {item_id: lib_data[item_id] for item_id in new_keys if item_id in lib_data}
                        # Đảm bảo giữ lại các key không nằm trong danh sách đang lọc (nếu có)
                        for kkey in lib_data.keys():
                            if kkey not in new_lib_data:
                                new_lib_data[kkey] = lib_data[kkey]
                        save_method_lib(new_lib_data)
                        st.rerun()
            else:
                if is_searching:
                    st.error("❌ Không tìm thấy phương pháp nào khớp với từ khóa tìm kiếm!")
                else:
                    st.info("Thư viện đang trống. Hãy chuyển sang Tab 'Thêm mới' để cập nhật dữ liệu.")

    # ==========================================
    # TAB 2: THÊM MỚI PHƯƠNG PHÁP
    # ==========================================
    with tab2:
        st.markdown("#### Khai báo phương pháp mới vào hệ thống")
        
        # Khởi tạo các session state hỗ trợ gợi ý AI cho Thêm mới
        if "add_tags_val" not in st.session_state: st.session_state.add_tags_val = []
        if "add_examples_val" not in st.session_state: st.session_state.add_examples_val = []

        # Nhập mã ID ngoài form để hỗ trợ kiểm tra tồn tại và gợi ý ngay lập tức
        col_chk_1, col_chk_2 = st.columns([2, 3])
        with col_chk_1:
            ma_moi = st.text_input("Mã phương pháp (ID)*", placeholder="VD: quang_pho_aas", key="new_method_id_input")
        with col_chk_2:
            st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True) # Spacer
            if ma_moi.strip():
                ma_moi_clean = ma_moi.strip().lower()
                if ma_moi_clean in lib_data:
                    st.error(f"⚠️ Đã tồn tại phương pháp này: '{lib_data[ma_moi_clean].get('ten_phuong_phap')}'")
                else:
                    st.success("✅ Mã ID phương pháp chưa tồn tại. Hợp lệ!")
                
                # Tìm các ID tương tự đã có
                similar_ids = [k for k in lib_data.keys() if ma_moi_clean in k.lower()]
                if similar_ids:
                    st.caption(f"💡 Mã tương tự đã có: {', '.join(similar_ids[:10])}{'...' if len(similar_ids) > 10 else ''}")
            else:
                st.caption(f"📋 Tổng số: {len(lib_data)} phương pháp. Ví dụ: {', '.join(list(lib_data.keys())[:5])}...")
        
        with st.container():
            ten_moi = st.text_input("Tên hiển thị*", placeholder="VD: Quang phổ hấp thụ nguyên tử (AAS)")
                
            col_in, col_ex = st.columns(2)
            with col_in: tk_nhan_dien = st.text_input("Từ khóa nhận diện (cách nhau bởi dấu phẩy)", placeholder="aas, quang phổ nguyên tử")
            with col_ex: tk_loai_tru = st.text_input("Từ khóa loại trừ (cách nhau bởi dấu phẩy)", placeholder="uv-vis, nm")
                
            # Thuộc tính bóc tách tích hợp AI
            col_tag_title, col_tag_btn = st.columns([3, 1])
            with col_tag_title:
                st.markdown("**Khai báo các thuộc tính (Tag) cần AI bóc tách:**")
            with col_tag_btn:
                if st.button("✨ AI Gợi ý Thuộc tính", key="ai_tags_add"):
                    if ten_moi.strip():
                        with st.spinner("AI đang gợi ý thuộc tính..."):
                            from core.ai_handler import call_ai_engine
                            prompt = f"Hãy gợi ý danh sách các mã thuộc tính (Tag) và mô tả nhiệm vụ trích xuất tương ứng cho phương pháp '{ten_moi.strip()}' (ID '{ma_moi}'). Các mã thuộc tính bắt buộc phải chọn trong các từ khóa sau: {', '.join(criteria_keys)}.\nTrả về dạng JSON array của các object có 2 trường: ma_thuoc_tinh, mo_ta."
                            suggestion = call_ai_engine("Bạn là chuyên gia QA/QC Dược. Trả về DUY NHẤT JSON array.", prompt, "Google API", "gemma-4-31b-it", is_json=True)
                            try:
                                import json
                                tags_json = json.loads(suggestion)
                                if isinstance(tags_json, list):
                                    st.session_state.add_tags_val = [t for t in tags_json if t.get("ma_thuoc_tinh") in criteria_keys]
                            except:
                                st.error("❌ Lỗi phân tích cú pháp JSON từ AI.")
                            st.rerun()
                    else:
                        st.warning("Vui lòng nhập tên hiển thị trước!")

            edited_data = st.data_editor(
                st.session_state.add_tags_val + [{"ma_thuoc_tinh": "", "mo_ta": ""} for _ in range(5)],
                num_rows="dynamic",
                column_config={
                    "ma_thuoc_tinh": st.column_config.SelectboxColumn(
                        "Mã thuộc tính (Tag)*",
                        options=criteria_options,
                        width="medium",
                        help="Chọn mã tag đã đăng ký trong Quản Lý Chỉ Tiêu Và Thuật Ngữ"
                    ),
                    "mo_ta": st.column_config.TextColumn("Mô tả để AI hiểu*", width="large")
                },
                use_container_width=True,
                key="new_method_tags_editor"
            )

            st.info("💡 Ví dụ few-shot thủ công đã được thay thế bởi hệ thống **Hồ Sơ Mẫu** tự động. AI sẽ học từ các hồ sơ mẫu đã upload.")

            submitted = st.button("💾 Lưu vào Thư Viện Phương Pháp", type="primary")

            if submitted:
                if not ma_moi.strip() or not ten_moi.strip():
                    st.error("❌ Vui lòng nhập đầy đủ Mã phương pháp và Tên hiển thị!")
                elif ma_moi.strip() in lib_data:
                    st.error(f"❌ Mã phương pháp '{ma_moi}' đã tồn tại! Vui lòng sang tab bên cạnh để chỉnh sửa.")
                else:
                    list_nhan_dien = [x.strip() for x in tk_nhan_dien.split(",") if x.strip()]
                    list_loai_tru = [x.strip() for x in tk_loai_tru.split(",") if x.strip()]
                    cau_truc_dict = {str(row.get("ma_thuoc_tinh", "")).strip(): str(row.get("mo_ta", "")).strip() for row in edited_data if str(row.get("ma_thuoc_tinh", "")).strip() and str(row.get("mo_ta", "")).strip()}
                    
                    if not cau_truc_dict: st.warning("⚠️ Phương pháp này chưa có thuộc tính nào!")
                    
                    lib_data[ma_moi.strip()] = {
                        "ten_phuong_phap": ten_moi.strip(), 
                        "tu_khoa_nhan_dien": list_nhan_dien,
                        "tu_khoa_loai_tru": list_loai_tru, 
                        "cau_truc_dau_ra": cau_truc_dict,
                        "vi_du_mau": []  # Không dùng few-shot thủ công nữa — AI học từ Hồ sơ Mẫu
                    }
                    save_method_lib(lib_data)
                    
                    # Dọn dẹp session state
                    st.session_state.add_tags_val = []
                    
                    st.success(f"✅ Đã lưu thành công phương pháp '{ten_moi}' vào Thư viện!")
                    st.rerun()