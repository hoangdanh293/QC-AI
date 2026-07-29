import pandas as pd

def python_extract_criteria_matrix(translated_text, master_data):
    """
    Phase 2: Dùng Python quét bản dịch để nhận diện nhanh các chỉ tiêu.
    Trả về DataFrame cấu trúc ma trận.
    """
    found_criteria = []
    text_lower = translated_text.lower()
    
    for key, config in master_data.items():
        name = config.get("ten_hien_thi", "").strip()
        # Dùng Python quét xem tên chỉ tiêu có xuất hiện trong text không
        if name and name.lower() in text_lower:
            found_criteria.append({
                "Mã ID": key,
                "Chọn": True,  # Mặc định tick chọn để đi tiếp
                "Tên Chỉ Tiêu": name,
                "TCNL": False,
                "Dược Điển": False,
                "COA": False,
                "MOA": False
            })
            
    # Trả về dạng DataFrame để Streamlit dễ dàng vẽ bảng tương tác
    return pd.DataFrame(found_criteria)

def filter_appendix_by_decision(parsed_extra_dict, selected_criteria_names):
    """
    Phase 4: Cắt gọt Phụ lục - CHỈ giữ lại các chỉ tiêu đã được tick chọn ở Phase 3.
    """
    filtered_dict = {}
    
    # Chuyển tập hợp tên đã chọn về chữ thường để so sánh an toàn
    selected_lower = [name.lower().strip() for name in selected_criteria_names]
    
    for parsed_name, content in parsed_extra_dict.items():
        parsed_name_lower = parsed_name.lower().strip()
        
        # So khớp chéo: Tên trong phụ lục có nằm trong tên đã chọn, hoặc ngược lại
        for sel_name in selected_lower:
            if sel_name in parsed_name_lower or parsed_name_lower in sel_name:
                filtered_dict[parsed_name] = content
                break # Tìm thấy thì lưu lại và thoát vòng lặp nhỏ
                
    return filtered_dict