import io
import re
import docx
from docxtpl import DocxTemplate, RichText
from docx.oxml.ns import qn

def add_formatted_text(rt, text, italic=False):
    segments = re.split(r'(<sub>.*?</sub>|<sup>.*?</sup>|<b>.*?</b>|<strong>.*?</strong>|<i>.*?</i>|<em>.*?</em>|<u>.*?</u>)', text, flags=re.IGNORECASE)
    for seg in segments:
        if not seg:
            continue
        seg_lower = seg.lower()
        if seg_lower.startswith("<sup>") and seg_lower.endswith("</sup>"):
            val = seg[5:-6]
            rt.add(val, font='Times New Roman', size=26, superscript=True, italic=italic)
        elif seg_lower.startswith("<sub>") and seg_lower.endswith("</sub>"):
            val = seg[5:-6]
            rt.add(val, font='Times New Roman', size=26, subscript=True, italic=italic)
        elif seg_lower.startswith("<b>") and seg_lower.endswith("</b>"):
            val = seg[3:-4]
            rt.add(val, font='Times New Roman', size=26, bold=True, italic=italic)
        elif seg_lower.startswith("<strong>") and seg_lower.endswith("</strong>"):
            val = seg[8:-9]
            rt.add(val, font='Times New Roman', size=26, bold=True, italic=italic)
        elif seg_lower.startswith("<i>") and seg_lower.endswith("</i>"):
            val = seg[3:-4]
            rt.add(val, font='Times New Roman', size=26, italic=True)
        elif seg_lower.startswith("<em>") and seg_lower.endswith("</em>"):
            val = seg[4:-5]
            rt.add(val, font='Times New Roman', size=26, italic=True)
        elif seg_lower.startswith("<u>") and seg_lower.endswith("</u>"):
            val = seg[3:-4]
            rt.add(val, font='Times New Roman', size=26, underline=True, italic=italic)
        else:
            rt.add(seg, font='Times New Roman', size=26, italic=italic)

def convert_to_bilingual_richtext(text):
    rt = RichText()
    normalized_text = str(text).replace("\\n", "\n").replace("\uf0fc", "✓")
    lines = normalized_text.split("\n")
    for i, line in enumerate(lines):
        if i > 0:
            rt.add("\n")
        
        # Split using regex to match a slash with spaces around it
        # This prevents splitting dates (11/06/2026) or units (mg/ml)
        parts = re.split(r'\s+/\s*|\s*/\s+', line, maxsplit=1)
        if len(parts) == 2:
            vi = parts[0].strip()
            en = parts[1].strip()
            add_formatted_text(rt, vi, italic=False)
            rt.add("\n", font='Times New Roman', size=26)
            add_formatted_text(rt, en, italic=True)
        else:
            add_formatted_text(rt, line, italic=False)
    return rt

def node_4_generate_word(json_data, template_file, admin_data, bilingual=False):
    # Cập nhật thông tin hành chính
    json_data.update(admin_data)
    
    # Format lại ngắt dòng và chống lỗi XML
    for k, v in json_data.items():
        if isinstance(v, str):
            if bilingual:
                json_data[k] = convert_to_bilingual_richtext(v)
            else:
                rt = RichText()
                normalized_text = str(v).replace("\\n", "\n").replace("\uf0fc", "✓")
                lines = normalized_text.split("\n")
                for i, line in enumerate(lines):
                    if i > 0:
                        rt.add("\n")
                    add_formatted_text(rt, line, italic=False)
                json_data[k] = rt
            
    # Đổ dữ liệu vào Template
    if hasattr(template_file, 'seek'):
        template_file.seek(0)
    doc = DocxTemplate(template_file)
    doc.render(json_data)
    
    # Lưu vào buffer RAM
    temp_io = io.BytesIO()
    doc.save(temp_io)
    temp_io.seek(0)
    final_doc = docx.Document(temp_io)
    
    namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

    # ----------------------------------------------------
    # BƯỚC 0: Xóa các hàng Gradient chứa marker "GR_XOA"
    # Gradient là bảng LỒNG bên trong ô của hàng tap_chat_hplc.
    # Ta dùng "GR_XOA" (không phải "XOA_HANG") để tránh logic XOA_HANG ở Bước 1
    # vô tình đọc đệ quy (.//w:t) vào bảng lồng và xóa nhầm hàng cha.
    #
    # Cách trích text trực tiếp (không đệ quy vào bảng lồng):
    #   - Với mỗi w:tr, lấy các w:tc là CON TRỰC TIẾP (findall('w:tc'), không dùng .//w:tc)
    #   - Với mỗi w:tc, lấy text từ các phần tử con nhưng BỎ QUA w:tbl (nested table)
    # Bước này phải chạy TRƯỚC Bước 1 để DOM đã sạch khi Bước 1 xây dựng row_cell_texts.
    # ----------------------------------------------------
    try:
        _GR_XOA = "GR_XOA"
        _ns_w = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        _tbl_tag = f'{{{_ns_w}}}tbl'
        _t_tag = f'{{{_ns_w}}}t'
        
        for _tr_el in list(final_doc.element.body.findall('.//w:tr', namespaces)):
            # Lấy ô trực tiếp của hàng (không đệ quy để tránh lấy ô từ bảng lồng khác)
            _tc_els = _tr_el.findall('w:tc', namespaces)
            _row_has_gr_xoa = False
            for _tc in _tc_els:
                # Thu thập text từ các phần tử con của w:tc,
                # nhưng BỎ QUA w:tbl (nested table) để không đọc sâu vào bảng khác
                _cell_texts = []
                for _child in _tc:
                    if _child.tag != _tbl_tag:
                        for _t in _child.iter(_t_tag):
                            if _t.text:
                                _cell_texts.append(_t.text)
                if _GR_XOA in "".join(_cell_texts):
                    _row_has_gr_xoa = True
                    break
            
            if _row_has_gr_xoa:
                # Xóa chữ GR_XOA khỏi các w:t trước khi xóa hàng (phòng hờ)
                for _tc in _tc_els:
                    for _t in _tc.findall(f'.//{_t_tag}'):
                        if _t.text and _GR_XOA in _t.text:
                            _t.text = _t.text.replace(_GR_XOA, "")
                try:
                    _parent = _tr_el.getparent()
                    if _parent is not None:
                        _parent.remove(_tr_el)
                except Exception:
                    pass
    except Exception:
        pass

    # ----------------------------------------------------
    # BƯỚC 0b: Xóa các hàng Định tính chứa marker "DT_XOA"
    # Định tính là bảng LỒNG bên trong ô của hàng định tính chính.
    # Mỗi phương pháp định tính chiếm 2 rows LIÊN TIẾP:
    #   Row A (heading): chứa {{ dinh_tinh_X }} → khi không có → DT_XOA
    #   Row B (checkbox): chứa "Đúng ☐" "Không đúng ☐" — phải xóa CÙNG VỚI row A
    # Khi xóa row A, xác định và xóa luôn row B ngay sau.
    # ----------------------------------------------------
    try:
        _DT_XOA = "DT_XOA"
        _ns_w = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        _tbl_tag = f'{{{_ns_w}}}tbl'
        _t_tag = f'{{{_ns_w}}}t'
        _tr_tag = f'{{{_ns_w}}}tr'

        for _tbl_el in list(final_doc.element.body.findall('.//w:tbl', namespaces)):
            _tbl_rows = list(_tbl_el.findall(_tr_tag))
            _to_delete = []
            for _ri, _tr_el in enumerate(_tbl_rows):
                _tc_els = _tr_el.findall('w:tc', namespaces)
                _has_dt_xoa = False
                for _tc in _tc_els:
                    _cell_texts = []
                    for _child in _tc:
                        if _child.tag != _tbl_tag:
                            for _t in _child.iter(_t_tag):
                                if _t.text:
                                    _cell_texts.append(_t.text)
                    if _DT_XOA in "".join(_cell_texts):
                        _has_dt_xoa = True
                        break

                if _has_dt_xoa:
                    # Xóa text DT_XOA trước khi xóa hàng
                    for _tc in _tc_els:
                        for _t in _tc.findall(f'.//{_t_tag}'):
                            if _t.text and _DT_XOA in _t.text:
                                _t.text = _t.text.replace(_DT_XOA, "")
                    _to_delete.append(_tr_el)
                    # Xóa luôn row NGAY SAU (row checkbox "Đúng/Không đúng")
                    if _ri + 1 < len(_tbl_rows):
                        _next_tr = _tbl_rows[_ri + 1]
                        # Kiểm tra row sau là row checkbox (không phải row heading khác)
                        _next_texts = "".join(
                            _t.text for _tc in _next_tr.findall('w:tc', namespaces)
                            for _t in _tc.findall(f'.//{_t_tag}') if _t.text
                        )
                        # Row checkbox chứa "Đúng" / "Không đúng" và không có DT_XOA
                        _is_checkbox_row = (
                            ("Đúng" in _next_texts or "đúng" in _next_texts)
                            and _DT_XOA not in _next_texts
                            and f'{{{_ns_w}}}tbl' not in [c.tag for c in _next_tr]
                        )
                        if _is_checkbox_row and _next_tr not in _to_delete:
                            _to_delete.append(_next_tr)

            for _tr_del in _to_delete:
                try:
                    _tbl_el.remove(_tr_del)
                except Exception:
                    pass
    except Exception:
        pass


    # ----------------------------------------------------
    # BƯỚC 1: Xóa Row (Hàng của bảng) chứa XOA_HANG trong toàn bộ document
    # Hỗ trợ thêm: xóa "orphan header row" — hàng header có text cứng ở cell 0-1
    # nhưng liền kề ngay trên một hàng content bị xóa (ví dụ: header điều kiện HPLC
    # của Tạp chất liên quan khi Tạp chất bị loại bỏ).
    # ----------------------------------------------------
    try:
        all_tr_els = final_doc.element.body.findall('.//w:tr', namespaces)
        rows_to_delete = set()   # index của các hàng cần xóa

        # Lần 1: Đánh dấu hàng cần xóa (cell 0 hoặc 1 có XOA_HANG)
        row_cell_texts = []
        for ri, tr_el in enumerate(all_tr_els):
            tc_els = tr_el.findall('.//w:tc', namespaces)
            cell_texts = []
            for tc in tc_els:
                t_els = tc.findall('.//w:t', namespaces)
                cell_texts.append("".join(t.text for t in t_els if t.text))
            row_cell_texts.append(cell_texts)

            should_delete = any(
                "XOA_HANG" in text
                for idx, text in enumerate(cell_texts)
                if idx <= 1
            )
            if should_delete:
                rows_to_delete.add(ri)

        # Lần 1.5: Lan truyền trạng thái xóa qua các ô gộp dọc (w:vMerge)
        # Nếu một ô bắt đầu gộp dọc (restart) thuộc hàng bị xóa, các hàng tiếp theo chứa ô gộp dọc đó cũng phải bị xóa.
        active_parent = [None, None]
        for ri, tr_el in enumerate(all_tr_els):
            tc_els = tr_el.findall('.//w:tc', namespaces)
            for ci in range(min(2, len(tc_els))):
                tc = tc_els[ci]
                vMerge = tc.find('.//w:vMerge', namespaces)
                if vMerge is not None:
                    val = vMerge.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val')
                    if val == 'restart':
                        active_parent[ci] = ri
                    else:  # continuation cell
                        parent = active_parent[ci]
                        if parent is not None and parent in rows_to_delete:
                            rows_to_delete.add(ri)
                else:
                    active_parent[ci] = None

        # Lần 2: Phát hiện "orphan header row"
        # Nếu hàng i bị xóa, và hàng i-1 có:
        #   - cell 0 và 1 là text cứng (không có XOA_HANG)
        #   - nhưng ít nhất 1 ô từ cell 2 trở đi cũng chứa XOA_HANG
        #     HOẶC chứa các từ khóa điều kiện HPLC (Cột:, Detector:, Đầu dò:, Tốc độ dòng:, Thể tích tiêm:)
        # → Hàng i-1 là header mồ côi → cũng xóa
        for ri in list(rows_to_delete):
            if ri > 0:
                prev_cells = row_cell_texts[ri - 1]
                has_xoa_in_later_cells = any(
                    "XOA_HANG" in text
                    for idx, text in enumerate(prev_cells)
                    if idx >= 2
                )
                has_hplc_markers = any(
                    any(marker in text for marker in ["Cột:", "Detector:", "Đầu dò:", "Tốc độ dòng:", "Thể tích tiêm:"])
                    for idx, text in enumerate(prev_cells)
                    if idx >= 2
                )
                no_xoa_in_first_cells = all(
                    "XOA_HANG" not in text
                    for idx, text in enumerate(prev_cells)
                    if idx <= 1
                )
                if (has_xoa_in_later_cells or has_hplc_markers) and no_xoa_in_first_cells:
                    rows_to_delete.add(ri - 1)

        # Lần 3: Thực hiện xóa
        for ri, tr_el in enumerate(all_tr_els):
            tc_els = tr_el.findall('.//w:tc', namespaces)
            if ri in rows_to_delete:
                # Xóa chữ XOA_HANG trước khi xóa node
                for tc in tc_els:
                    for t in tc.findall('.//w:t', namespaces):
                        if t.text and "XOA_HANG" in t.text:
                            t.text = t.text.replace("XOA_HANG", "")
                try:
                    parent = tr_el.getparent()
                    if parent is not None:
                        parent.remove(tr_el)
                except Exception:
                    pass
            else:
                # Nếu không xóa hàng, nhưng các ô phía sau (yêu cầu/phương pháp) có XOA_HANG
                cell_texts = row_cell_texts[ri]
                for idx, text in enumerate(cell_texts):
                    if idx >= 2 and "XOA_HANG" in text:
                        tc = tc_els[idx]
                        for t in tc.findall('.//w:t', namespaces):
                            if t.text and "XOA_HANG" in t.text:
                                t.text = t.text.replace("XOA_HANG", "Theo yêu cầu chuyên luận.")
    except Exception:
        pass

    # ----------------------------------------------------
    # BƯỚC 2: Xóa Paragraph (Đoạn văn lẻ) chứa XOA_DONG hoặc XOA_HANG trong toàn bộ document
    # ----------------------------------------------------
    try:
        for p_el in final_doc.element.body.findall('.//w:p', namespaces):
            t_els = p_el.findall('.//w:t', namespaces)
            p_text = "".join(t.text for t in t_els if t.text)
            if "XOA_DONG" in p_text or "XOA_HANG" in p_text: 
                # Xóa chữ trước
                for t in t_els:
                    if t.text:
                        if "XOA_DONG" in t.text:
                            t.text = t.text.replace("XOA_DONG", "")
                        if "XOA_HANG" in t.text:
                            t.text = t.text.replace("XOA_HANG", "")
                # Xóa XML node
                try:
                    parent = p_el.getparent()
                    if parent is not None:
                        parent.remove(p_el)
                except Exception:
                    pass
    except Exception:
        pass
            
    # ----------------------------------------------------
    # BƯỚC 3: Dồn dòng về bên trái (Left Align) cho các bảng
    # ----------------------------------------------------
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    def align_left(tbl):
        for row in tbl.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                for nested_tbl in cell.tables:
                    align_left(nested_tbl)
                    
    for table in final_doc.tables:
        align_left(table)

    # ----------------------------------------------------
    # BƯỚC 4: Dồn dòng về bên trái cho phần Phương pháp kiểm nghiệm (TCNL)
    # ----------------------------------------------------
    try:
        start_align_left = False
        for p in final_doc.paragraphs:
            p_text = p.text.strip()
            if "phương pháp kiểm nghiệm" in p_text.lower():
                start_align_left = True
                continue
            if start_align_left:
                if p.alignment not in [WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.RIGHT]:
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    except Exception:
        pass

    # ----------------------------------------------------
    # BƯỚC 5: Thiết lập phông chữ Times New Roman và giãn chữ (Scale 75%) toàn bộ văn bản
    # Dùng XML XPath trực tiếp để áp dụng hàng loạt — nhanh hơn lặp từng run
    # ----------------------------------------------------
    try:
        body = final_doc.element.body
        
        # Lấy tất cả w:r (run) trong toàn bộ document bằng XPath một lần duy nhất
        all_runs = body.findall('.//w:r', namespaces)
        
        for r_el in all_runs:
            try:
                # Lấy hoặc tạo w:rPr
                rPr = r_el.find(qn('w:rPr'))
                if rPr is None:
                    rPr = docx.oxml.OxmlElement('w:rPr')
                    r_el.insert(0, rPr)
                
                # Thiết lập font Times New Roman
                rFonts = rPr.find(qn('w:rFonts'))
                if rFonts is None:
                    rFonts = docx.oxml.OxmlElement('w:rFonts')
                    rPr.insert(0, rFonts)
                rFonts.set(qn('w:ascii'), 'Times New Roman')
                rFonts.set(qn('w:hAnsi'), 'Times New Roman')
                rFonts.set(qn('w:eastAsia'), 'Times New Roman')
                rFonts.set(qn('w:cs'), 'Times New Roman')
                
                # Thiết lập Scale 75%
                w_el = rPr.find(qn('w:w'))
                if w_el is None:
                    w_el = docx.oxml.OxmlElement('w:w')
                    rPr.append(w_el)
                w_el.set(qn('w:val'), '75')
            except Exception:
                pass
        
        # Áp dụng thêm cho Header/Footer (nằm ngoài body)
        for section in final_doc.sections:
            for h_f in [section.header, section.footer]:
                if h_f is not None:
                    hf_runs = h_f._element.findall('.//w:r', namespaces)
                    for r_el in hf_runs:
                        try:
                            rPr = r_el.find(qn('w:rPr'))
                            if rPr is None:
                                rPr = docx.oxml.OxmlElement('w:rPr')
                                r_el.insert(0, rPr)
                            rFonts = rPr.find(qn('w:rFonts'))
                            if rFonts is None:
                                rFonts = docx.oxml.OxmlElement('w:rFonts')
                                rPr.insert(0, rFonts)
                            rFonts.set(qn('w:ascii'), 'Times New Roman')
                            rFonts.set(qn('w:hAnsi'), 'Times New Roman')
                            rFonts.set(qn('w:eastAsia'), 'Times New Roman')
                            rFonts.set(qn('w:cs'), 'Times New Roman')
                            w_el = rPr.find(qn('w:w'))
                            if w_el is None:
                                w_el = docx.oxml.OxmlElement('w:w')
                                rPr.append(w_el)
                            w_el.set(qn('w:val'), '75')
                        except Exception:
                            pass
    except Exception:
        pass

    # Đóng gói file gửi về Frontend
    final_io = io.BytesIO()
    final_doc.save(final_io)
    final_io.seek(0)
    return final_io