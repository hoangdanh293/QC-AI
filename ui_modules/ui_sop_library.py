import streamlit as st
import json
import os
import time
from core.ai_handler import translate_text_to_bilingual
from core.key_manager import load_model_config
import streamlit.components.v1 as components

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_component_dir = os.path.join(_parent_dir, "core", "drag_drop_component")
_drag_drop_reorder = components.declare_component("drag_drop_reorder", path=_component_dir)


# Callbacks for SOP library translation to avoid StreamlitAPIException
def translate_edit_sop_callback(sop_id):
    p_trans = st.session_state[f"edit_sop_p_{sop_id}"]
    m_trans = st.session_state[f"edit_sop_m_{sop_id}"]
    name = st.session_state[f"edit_sop_name_{sop_id}"]
    content = st.session_state[f"edit_sop_content_{sop_id}"]
    if name or content:
        st.session_state[f"edit_sop_name_{sop_id}"] = translate_text_to_bilingual(name, p_trans, m_trans, "criteria")
        st.session_state[f"edit_sop_content_{sop_id}"] = translate_text_to_bilingual(content, p_trans, m_trans, "sop")

def translate_add_sop_callback():
    p_trans = st.session_state["add_sop_p"]
    m_trans = st.session_state["add_sop_m"]
    name = st.session_state["add_sop_name"]
    content = st.session_state["add_sop_content"]
    if name or content:
        st.session_state["add_sop_name"] = translate_text_to_bilingual(name, p_trans, m_trans, "criteria")
        st.session_state["add_sop_content"] = translate_text_to_bilingual(content, p_trans, m_trans, "sop")

def save_add_sop_callback():
    ma_moi = st.session_state.get("add_sop_id", "").strip()
    ten_moi = st.session_state.get("add_sop_name", "").strip()
    tk_khoi_tao = st.session_state.get("add_sop_kws", "").strip()
    noi_dung_sop_moi = st.session_state.get("add_sop_content", "").strip()
    
    if not ma_moi or not ten_moi or not noi_dung_sop_moi:
        st.session_state["add_sop_error"] = "❌ Vui lòng nhập đầy đủ các trường bắt buộc có dấu (*)!"
        return
        
    lib_data = load_sop_lib()
    is_update = ma_moi in lib_data
    list_kws = [x.strip() for x in tk_khoi_tao.split(",") if x.strip()]
    lib_data[ma_moi] = {
        "ten_hien_thi": ten_moi,
        "tu_khoa_khoi_tao": list_kws,
        "noi_dung_sop": noi_dung_sop_moi
    }
    save_sop_lib(lib_data)
    
    # Safe reset of state keys inside callback
    st.session_state["add_sop_id"] = ""
    st.session_state["add_sop_name"] = ""
    st.session_state["add_sop_kws"] = ""
    st.session_state["add_sop_content"] = ""
    
    if is_update:
        st.session_state["add_sop_success"] = f"✅ Đã cập nhật (ghi đè) thành công SOP '{ten_moi}' (Mã: {ma_moi}) trong Thư viện!"
    else:
        st.session_state["add_sop_success"] = f"✅ Đã lưu mới thành công SOP '{ten_moi}' vào Thư viện!"

SOP_LIB_FILE = "sop_reference_library.json"

def load_sop_lib():
    if os.path.exists(SOP_LIB_FILE):
        with open(SOP_LIB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_sop_lib(data):
    with open(SOP_LIB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def update_item_keep_order(old_key, new_key, new_val, lib_data):
    new_dict = {}
    for k, v in lib_data.items():
        if k == old_key:
            new_dict[new_key] = new_val
        else:
            new_dict[k] = v
    return new_dict

def render_sop_library():
    if "editing_sop_id" not in st.session_state:
        st.session_state.editing_sop_id = None
    if "sop_dnd_key" not in st.session_state:
        st.session_state.sop_dnd_key = 0

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

    st.markdown("<h2 style='text-align: center; color: #0071e3 !important; font-weight: 600; letter-spacing: -0.02em;'>📚 Quản Lý Thư Viện Mẫu</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; margin-bottom: 30px;'>Lưu trữ các phương pháp kiểm nghiệm mẫu (SOP) thay thế hoặc chi tiết hóa chỉ tiêu.</p>", unsafe_allow_html=True)
    
    lib_data = load_sop_lib()

    tab1, tab2 = st.tabs(["🔍 Quản lý, Chỉnh sửa & Sắp xếp", "➕ Thêm Phương pháp Mẫu Mới"])

    # ==========================================
    # TAB 1: TRA CỨU, CHỈNH SỬA, XÓA & SẮP XẾP
    # ==========================================
    with tab1:
        editing_id = st.session_state.get("editing_sop_id")
        
        if editing_id and editing_id in lib_data:
            st.markdown(f"#### ⚙️ Chỉnh sửa SOP mẫu: **{lib_data[editing_id].get('ten_hien_thi')}**")
            
            if st.button("🔙 Quay lại danh sách", key="back_to_list_top"):
                st.session_state.editing_sop_id = None
                st.rerun()
                
            v = lib_data[editing_id]
            st.warning("⚠️ **Đang trong chế độ chỉnh sửa.**")
            with st.form(key=f"edit_sop_form_{editing_id}"):
                edit_id = st.text_input("Mã SOP mẫu (ID)*", key=f"edit_sop_id_{editing_id}", value=editing_id)
                edit_name = st.text_input("Tên hiển thị*", key=f"edit_sop_name_{editing_id}", value=v.get('ten_hien_thi', ''))
                edit_kws = st.text_input("Từ khóa tự động nhận diện (cách nhau bởi dấu phẩy)", key=f"edit_sop_kws_{editing_id}", value=", ".join(v.get('tu_khoa_khoi_tao', [])))
                edit_content = st.text_area("Nội dung phương pháp SOP*", key=f"edit_sop_content_{editing_id}", value=v.get('noi_dung_sop', ''), height=250)
                
                # Cấu hình mô hình dịch
                model_config = load_model_config()
                providers = list(model_config.keys())
                c_sel_1, c_sel_2 = st.columns(2)
                with c_sel_1:
                    p_trans = st.selectbox("Nhà cung cấp dịch", providers, key=f"edit_sop_p_{editing_id}")
                with c_sel_2:
                    m_trans = st.selectbox("Mô hình dịch", model_config.get(p_trans, []), key=f"edit_sop_m_{editing_id}")
                
                c_save, c_trans = st.columns([1, 1])
                with c_save:
                    save_clicked = st.form_submit_button("💾 Lưu Cập Nhật", type="primary")
                with c_trans:
                    st.form_submit_button(
                        "🤖 Dịch song ngữ bằng AI",
                        type="secondary",
                        on_click=translate_edit_sop_callback,
                        args=(editing_id,)
                    )
                    
                if save_clicked:
                    new_id = edit_id.strip()
                    if not new_id or not edit_name.strip() or not edit_content.strip():
                        st.error("❌ Các trường dấu (*) không được để trống!")
                    elif new_id != editing_id and new_id in lib_data:
                        st.error(f"❌ Mã ID '{new_id}' đã tồn tại! Vui lòng chọn mã khác.")
                    else:
                        list_kws = [x.strip() for x in edit_kws.split(",") if x.strip()]
                        new_obj = {
                            "ten_hien_thi": edit_name.strip(),
                            "tu_khoa_khoi_tao": list_kws,
                            "noi_dung_sop": edit_content
                        }
                        lib_data = update_item_keep_order(editing_id, new_id, new_obj, lib_data)
                        save_sop_lib(lib_data)
                        st.session_state.editing_sop_id = None
                        st.success(f"✅ Đã cập nhật thành công!")
                        time.sleep(1)
                        st.rerun()
        else:
            st.markdown("#### Danh sách các SOP mẫu hiện có")
            search_term = st.text_input("🔍 Nhập mã, tên phương pháp hoặc từ khóa nhận diện để tìm kiếm:", key="search_sop_lib")
            is_searching = bool(search_term.strip())
            
            if is_searching:
                st.info("💡 Lưu ý: Chức năng Sắp xếp vị trí bị vô hiệu hóa khi đang tìm kiếm để tránh sai lệch dữ liệu.")

            # Lọc danh sách SOP mẫu phù hợp với từ khóa
            sop_items_for_dnd = []
            for k in lib_data.keys():
                v = lib_data[k]
                search_string = f"{k} {v.get('ten_hien_thi', '')} {' '.join(v.get('tu_khoa_khoi_tao', []))}".lower()
                if not search_term or search_term.lower() in search_string:
                    sop_items_for_dnd.append({
                        "id": k,
                        "ten_hien_thi": v.get("ten_hien_thi", ""),
                        "tu_khoa": v.get("tu_khoa_khoi_tao", []),
                        "noi_dung": v.get("noi_dung_sop", "")
                    })

            if sop_items_for_dnd:
                st.markdown("<p style='font-size: 13px; color: #86868b; margin-bottom: 8px;'>💡 Sử dụng tay nắm (⋮⋮) bên trái mỗi thẻ để kéo thả trực tiếp và sắp xếp lại thứ tự.</p>", unsafe_allow_html=True)
                new_order = _drag_drop_reorder(
                    items=sop_items_for_dnd,
                    key=f"sop_lib_dnd_reorder_{st.session_state.sop_dnd_key}",
                    default=sop_items_for_dnd,
                    disable_drag=is_searching
                )
                
                # Xử lý các sự kiện phản hồi từ component
                if isinstance(new_order, dict) and "action" in new_order:
                    action = new_order["action"]
                    act_id = new_order["id"]
                    # Reset component key để tránh lặp lại hành động
                    st.session_state.sop_dnd_key += 1
                    
                    if action == "edit":
                        st.session_state.editing_sop_id = act_id
                        st.rerun()
                    elif action == "delete":
                        if act_id in lib_data:
                            del lib_data[act_id]
                            save_sop_lib(lib_data)
                            st.success(f"✅ Đã xóa thành công SOP '{act_id}' khỏi Thư viện!")
                            time.sleep(1)
                            st.rerun()
                            
                elif isinstance(new_order, list) and not is_searching:
                    # Kiểm tra xem thứ tự các key có thay đổi thực sự không
                    current_keys = [item["id"] for item in sop_items_for_dnd]
                    new_keys = [item["id"] for item in new_order if isinstance(item, dict) and "id" in item]
                    if new_keys and new_keys != current_keys:
                        new_lib_data = {item_id: lib_data[item_id] for item_id in new_keys if item_id in lib_data}
                        # Đảm bảo giữ lại các key không nằm trong danh sách đang lọc (nếu có)
                        for kkey in lib_data.keys():
                            if kkey not in new_lib_data:
                                new_lib_data[kkey] = lib_data[kkey]
                        save_sop_lib(new_lib_data)
                        st.rerun()
            else:
                if is_searching:
                    st.error("❌ Không tìm thấy SOP mẫu nào khớp với từ khóa tìm kiếm!")
                else:
                    st.info("Thư viện đang trống. Hãy chuyển sang Tab 'Thêm mới' để cập nhật dữ liệu.")

    # ==========================================
    # TAB 2: THÊM MỚI PHƯƠNG PHÁP MẪU
    # ==========================================
    with tab2:
        st.markdown("#### Khai báo SOP mẫu mới vào hệ thống")
        with st.form("add_sop_form"):
            col_id, col_name = st.columns(2)
            with col_id: 
                ma_moi = st.text_input("Mã SOP mẫu (ID)*", placeholder="VD: do_ph_usp", key="add_sop_id")
            with col_name: 
                ten_moi = st.text_input("Tên hiển thị*", placeholder="VD: Đo pH (Theo Dược điển USP <791>)", key="add_sop_name")
                
            tk_khoi_tao = st.text_input("Từ khóa nhận diện tự động (cách nhau bởi dấu phẩy)", placeholder="ph, acidity or alkalinity, giới hạn acid - kiềm", key="add_sop_kws")
            noi_dung_sop_moi = st.text_area("Nội dung phương pháp SOP mẫu*", placeholder="Nhập quy trình chi tiết (Tiếng Việt / English)...", height=250, key="add_sop_content")
            
            # Cấu hình mô hình dịch
            model_config = load_model_config()
            providers = list(model_config.keys())
            c_sel_1, c_sel_2 = st.columns(2)
            with c_sel_1:
                p_trans = st.selectbox("Nhà cung cấp dịch", providers, key="add_sop_p")
            with c_sel_2:
                m_trans = st.selectbox("Mô hình dịch", model_config.get(p_trans, []), key="add_sop_m")
            
            c_save, c_trans = st.columns([1, 1])
            with c_save:
                st.form_submit_button(
                    "💾 Lưu vào Thư Viện SOP Mẫu",
                    type="primary",
                    on_click=save_add_sop_callback
                )
            with c_trans:
                st.form_submit_button(
                    "🤖 Dịch song ngữ bằng AI",
                    type="secondary",
                    on_click=translate_add_sop_callback
                )
            
        # Display feedback outside the form
        if "add_sop_error" in st.session_state and st.session_state["add_sop_error"]:
            st.error(st.session_state["add_sop_error"])
            del st.session_state["add_sop_error"]
            
        if "add_sop_success" in st.session_state and st.session_state["add_sop_success"]:
            st.success(st.session_state["add_sop_success"])
            del st.session_state["add_sop_success"]
            time.sleep(1)
            st.rerun()
