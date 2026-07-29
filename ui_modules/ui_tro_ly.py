import json
import os
import re
import streamlit as st
import streamlit.components.v1 as components
from core.ai_handler import call_ai_engine_stream, clean_translation_prefix

# ─── Đường dẫn thư viện ───────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REAGENT_LIB_PATH = os.path.join(_BASE_DIR, "reagent_library.json")
_SOP_LIB_PATH     = os.path.join(_BASE_DIR, "sop_reference_library.json")
_METHOD_LIB_PATH  = os.path.join(_BASE_DIR, "method_library.json")

# ─── Cache thư viện ───────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _load_reagent_library():
    try:
        with open(_REAGENT_LIB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

@st.cache_resource(show_spinner=False)
def _load_sop_library():
    try:
        with open(_SOP_LIB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

# ─── Hàm tìm kiếm ─────────────────────────────────────────────────────────────
def _search_reagent(query: str, top_k: int = 3) -> list[dict]:
    """Tìm kiếm thuốc thử / dung dịch trong thư viện theo tên hoặc từ khóa."""
    lib = _load_reagent_library()
    if not lib:
        return []
    
    # Chuẩn hóa truy vấn: loại bỏ dấu câu
    q_clean = re.sub(r'[?.,!:]', ' ', query.lower()).strip()
    
    # Danh sách từ dừng (stopwords) để tránh so khớp các từ quá phổ biến
    stopwords = {
        "dung", "dịch", "thuốc", "thử", "hóa", "chất", 
        "của", "trong", "cho", "bằng", "hoặc", "với", "nước", 
        "các", "làm", "cách", "pha", "tác", "dụng", 
        "là", "gì", "như", "thế", "nào", "để", "ở", "tại", "sử", "dụng"
    }
    
    words = [w for w in q_clean.split() if w not in stopwords and len(w) >= 2]
    if not words:
        words = [w for w in q_clean.split() if len(w) >= 3]
        
    if not words:
        return []
        
    scored = []
    for key, item in lib.items():
        name_en  = item.get("ten_tieng_anh", "").lower()
        name_vi  = item.get("ten_tieng_viet", "").lower()
        cach_pha = item.get("cach_pha", "").lower()
        score = 0
        
        # Nếu khớp hoàn toàn cụm từ khóa (không tính stopwords)
        q_keywords_str = " ".join(words)
        if q_keywords_str in name_en or q_keywords_str in name_vi:
            score += 15
            
        for w in words:
            if w in name_en:  score += 4
            if w in name_vi:  score += 4
            if w in cach_pha: score += 1
            
        # Ngưỡng điểm chất lượng: phải đạt tối thiểu 8 điểm mới coi là trùng khớp hợp lệ
        if score >= 8:
            scored.append((score, key, item))
            
    scored.sort(key=lambda x: -x[0])
    return [
        {
            "key": k,
            "ten_tieng_anh": v.get("ten_tieng_anh", ""),
            "ten_tieng_viet": v.get("ten_tieng_viet", ""),
            "loai": v.get("loai", ""),
            "duoc_dien": v.get("duoc_dien", ""),
            "cach_pha": v.get("cach_pha", ""),
        }
        for _, k, v in scored[:top_k]
    ]

def _search_sop(query: str, top_k: int = 2) -> list[dict]:
    lib = _load_sop_library()
    if not lib:
        return []
        
    q_clean = re.sub(r'[?.,!:]', ' ', query.lower()).strip()
    
    stopwords = {
        "sop", "phương", "pháp", "quy", "trình", "của", "trong", "cho", 
        "bằng", "hoặc", "với", "nước", "làm", "cách", "tác", "dụng", 
        "là", "gì", "như", "thế", "nào", "để", "ở", "tại", "sử", "dụng"
    }
    
    words = [w for w in q_clean.split() if w not in stopwords and len(w) >= 2]
    if not words:
        words = [w for w in q_clean.split() if len(w) >= 3]
        
    if not words:
        return []
        
    scored = []
    items_list = lib if isinstance(lib, list) else lib.get("sops", [])
    for item in items_list:
        name    = str(item.get("ten", item.get("name", ""))).lower()
        content = str(item.get("noi_dung", item.get("content", ""))).lower()
        score = 0
        
        q_keywords_str = " ".join(words)
        if q_keywords_str in name:
            score += 15
            
        for w in words:
            if w in name:    score += 5
            if w in content: score += 1
            
        # Ngưỡng điểm chất lượng: phải đạt tối thiểu 8 điểm
        if score >= 8:
            scored.append((score, item))
            
    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:top_k]]

def _detect_intent(query: str) -> str:
    """Phân loại ý định: 'reagent' | 'sop' | 'system' | 'general'"""
    q = query.lower()
    
    # 0. Ưu tiên nhận dạng câu hỏi lý thuyết/tổng quát (General Q&A)
    general_indicators = [
        "tác dụng của", "tác dụng là gì", "vai trò của", "vai trò là gì",
        "là gì", "là như thế nào", "tại sao", "cơ chế", "nguyên lý",
        "nguyên nhân", "hiện tượng", "ưu điểm", "nhược điểm", "khác nhau",
        "so sánh", "định nghĩa", "khái niệm", "ý nghĩa"
    ]
    for ind in general_indicators:
        if ind in q:
            return "general"
            
    reagent_kw = [
        "thuốc thử", "dung dịch", "hóa chất", "reagent", "solution", "acid",
        "pha chế", "pha loãng", "cách pha", "nồng độ", "mol", "buffer",
        "indicator", "chỉ thị", "acetic", "acetone", "ethanol", "methanol",
        "sulfuric", "hydrochloric", "sodium", "potassium", "ammonia",
    ]
    sop_kw = [
        "sop", "phương pháp", "quy trình", "hplc", "uv-vis", "uvvis",
        "titrimetric", "karl fischer", "lod", "loi", "tro sulfat",
        "kim loại nặng", "giới hạn",
    ]
    system_kw = [
        "hệ thống", "bước", "chức năng", "tab", "lập hồ sơ", "training ai",
        "api key", "cấu hình", "sidebar", "workflow", "bước nào",
        "làm thế nào", "how to", "giải thích", "hồ sơ kiểm nghiệm",
        "tiêu chuẩn nguyên liệu", "thư viện phương pháp", "training",
    ]
    for kw in reagent_kw:
        if kw in q:
            return "reagent"
    for kw in sop_kw:
        if kw in q:
            return "sop"
    for kw in system_kw:
        if kw in q:
            return "system"
    return "general"

def _build_context_from_db(query: str, intent: str) -> str:
    parts = []
    if intent == "reagent":
        results = _search_reagent(query)
        if results:
            parts.append("=== DỮ LIỆU TỪ THƯ VIỆN THUỐC THỬ & DUNG DỊCH ===")
            for r in results:
                parts.append(
                    f"\n📦 **{r['ten_tieng_anh']}** ({r['ten_tieng_viet']})\n"
                    f"- Loại: {r['loai']} | Dược điển: {r['duoc_dien']}\n"
                    f"- Chi tiết:\n{r['cach_pha']}"
                )
    elif intent == "sop":
        results = _search_sop(query)
        if results:
            parts.append("=== DỮ LIỆU TỪ THƯ VIỆN SOP ===")
            for r in results:
                name    = r.get("ten", r.get("name", ""))
                content = r.get("noi_dung", r.get("content", ""))[:500]
                parts.append(f"\n📋 **{name}**\n{content}...")
    return "\n".join(parts)

# ─── System Prompts ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT_WITH_DB = """Bạn là Trợ lý QA/QC Co-pilot chuyên nghiệp tích hợp trong hệ thống Quản lý Hồ Sơ Kiểm Nghiệm AI của nhà máy Dược phẩm CPC1HN.

## NGUYÊN TẮC (QUAN TRỌNG NHẤT):
- **TUYỆT ĐỐI TRUNG THỰC**: Chỉ trả lời những gì bạn BIẾT CHẮC CHẮN.
- **KHÔNG BỊA ĐẶT**: Không suy đoán hay bịa thông số kỹ thuật, công thức, nồng độ. Chỉ trích dẫn từ dữ liệu được cung cấp.
- **NGUỒN GỐC RÕ RÀNG**: Khi trả lời từ dữ liệu thư viện, ghi rõ nguồn (tên Dược điển, số chương...).
- **NGẮN GỌN, CÓ CẤU TRÚC**: Dùng Markdown, bullet points, in đậm thuật ngữ quan trọng.

## HƯỚNG DẪN TRẢ LỜI KHI CÓ DỮ LIỆU HỆ THỐNG:
Dựa HOÀN TOÀN vào phần "DỮ LIỆU TÌM ĐƯỢC" bên dưới để trả lời. Trích dẫn rõ Dược điển, phương pháp nguồn gốc. Không thêm thông tin ngoài dữ liệu đã cung cấp."""

_SYSTEM_PROMPT_AI_FALLBACK = """Bạn là Trợ lý QA/QC Co-pilot chuyên nghiệp của nhà máy Dược phẩm CPC1HN. Câu hỏi này KHÔNG có trong cơ sở dữ liệu nội bộ, bạn sẽ trả lời dựa trên kiến thức chuyên môn QA/QC Dược phẩm.

## NGUYÊN TẮC TRẢ LỜI (NGHIÊM NGẶT):
- **CHÍNH XÁC TUYỆT ĐỐI**: Chỉ trả lời những gì bạn chắc chắn về mặt khoa học/pháp lý.
- **TRÍCH DẪN NGUỒN**: Với mỗi thông tin, phải ghi rõ nguồn (ví dụ: "EP 11.0, Chapter 2.2.46", "USP <1231>", "ICH Q6A", "DĐVN V, Phụ lục 9.6"...).
- **CẤU TRÚC RÕ RÀNG**: Dùng Markdown với header, bullet, bold cho thuật ngữ kỹ thuật.
- **PHÂN BIỆT RÕ**: Thông tin từ Dược điển vs. Kiến thức chuyên môn chung.
- **TUYỆT ĐỐI KHÔNG BỊA ĐẶT**: Nếu không chắc chắn, ghi rõ "Cần tra cứu thêm tại [nguồn]" thay vì đoán.

## ĐỊNH DẠNG TRẢ LỜI:
Trả lời trực tiếp, có cấu trúc rõ ràng. Kết thúc bằng phần:
> 📚 **Nguồn tham khảo**: [liệt kê nguồn cụ thể: tên Dược điển, phiên bản, chương/mục]"""

# ─── Robot SVG & JS Template ──────────────────────────────────────────────────
_ROBOT_SVG_BUBBLE = """<svg class="cpc-robot-svg" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%;">
  <defs>
    <linearGradient id="redGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ff4b5c"/>
      <stop offset="100%" stop-color="#cc0022"/>
    </linearGradient>
  </defs>
  <circle cx="50" cy="50" r="46" fill="#ffffff"/>
  <circle cx="50" cy="50" r="46" fill="none" stroke="url(#redGrad)" stroke-width="4"/>
  <rect x="25" y="32" width="50" height="42" rx="16" fill="#ffffff" stroke="#eef0f3" stroke-width="1.5"/>
  <path d="M25 48 C25 35, 75 35, 75 48 L75 40 C75 30, 25 30, 25 40 Z" fill="url(#redGrad)"/>
  <path d="M21 42 C35 37, 65 37, 79 42 L79 45 C65 40, 35 40, 21 45 Z" fill="#ffffff"/>
  <rect x="32" y="47" width="36" height="22" rx="6" fill="#ffffff" stroke="url(#redGrad)" stroke-width="1.5"/>
  <path d="M38 56 L44 52 L38 48" fill="none" stroke="#1d1d1f" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M56 50 A4 4 0 0 1 64 50" fill="none" stroke="#1d1d1f" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="36" cy="61" r="2.5" fill="#ffbaba"/>
  <circle cx="64" cy="61" r="2.5" fill="#ffbaba"/>
  <path d="M47 58 Q50 61 53 58" stroke="url(#redGrad)" stroke-width="2" stroke-linecap="round" fill="none"/>
  <path d="M28 34 A26 26 0 0 1 72 34" fill="none" stroke="url(#redGrad)" stroke-width="3"/>
  <rect x="19" y="44" width="7" height="18" rx="3" fill="url(#redGrad)"/>
  <rect x="74" y="44" width="7" height="18" rx="3" fill="url(#redGrad)"/>
  <path d="M23 57 L33 62" fill="none" stroke="#555555" stroke-width="1.5" stroke-linecap="round"/>
  <circle cx="33" cy="62" r="1.5" fill="url(#redGrad)"/>
</svg>"""

_ROBOT_SVG_AVATAR = """<svg class="cpc-robot-svg" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%;">
  <defs>
    <linearGradient id="redGrad2" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ff4b5c"/>
      <stop offset="100%" stop-color="#cc0022"/>
    </linearGradient>
  </defs>
  <rect x="25" y="32" width="50" height="42" rx="16" fill="#ffffff" stroke="#eef0f3" stroke-width="1.5"/>
  <path d="M25 48 C25 35, 75 35, 75 48 L75 40 C75 30, 25 30, 25 40 Z" fill="url(#redGrad2)"/>
  <path d="M21 42 C35 37, 65 37, 79 42 L79 45 C65 40, 35 40, 21 45 Z" fill="#ffffff"/>
  <rect x="32" y="47" width="36" height="22" rx="6" fill="#ffffff" stroke="url(#redGrad2)" stroke-width="1.5"/>
  <path d="M38 56 L44 52 L38 48" fill="none" stroke="#1d1d1f" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M56 50 A4 4 0 0 1 64 50" fill="none" stroke="#1d1d1f" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="36" cy="61" r="2.5" fill="#ffbaba"/>
  <circle cx="64" cy="61" r="2.5" fill="#ffbaba"/>
  <path d="M47 58 Q50 61 53 58" stroke="url(#redGrad2)" stroke-width="2" stroke-linecap="round" fill="none"/>
  <path d="M28 34 A26 26 0 0 1 72 34" fill="none" stroke="url(#redGrad2)" stroke-width="3"/>
  <rect x="19" y="44" width="7" height="18" rx="3" fill="url(#redGrad2)"/>
  <rect x="74" y="44" width="7" height="18" rx="3" fill="url(#redGrad2)"/>
  <path d="M23 57 L33 62" fill="none" stroke="#555555" stroke-width="1.5" stroke-linecap="round"/>
  <circle cx="33" cy="62" r="1.5" fill="url(#redGrad2)"/>
</svg>"""

_JS_TEMPLATE = """
(function () {
    'use strict';
    var P = window.parent;
    var D = P.document;

    var robotSvgBubble = '{robot_svg_bubble}';
    var robotSvgAvatar = '{robot_svg_avatar}';
    var popWidth = {popWidth};
    var popHeight = {popHeight};

    /* ===== 1. Inject CSS vào <head> parent ===== */
    var s = D.getElementById('cpc-copilot-style');
    if (!s) {
        s = D.createElement('style');
        s.id = 'cpc-copilot-style';
        D.head.appendChild(s);
    }
    s.textContent = [
        '@keyframes cpc-blink {',
        '  0%,100% { opacity: 0.35; } 50% { opacity: 1; }',
        '}',
        '@keyframes cpc-pulse {',
        '  0% { box-shadow: 0 0 0 0 rgba(255,59,48,0.55), 0 4px 16px rgba(255,59,48,0.18); }',
        '  70% { box-shadow: 0 0 0 10px rgba(255,59,48,0), 0 4px 16px rgba(255,59,48,0.18); }',
        '  100% { box-shadow: 0 0 0 0 rgba(255,59,48,0), 0 4px 16px rgba(255,59,48,0.18); }',
        '}',
        '.cpc-online-dot {',
        '  width:7px; height:7px; background:#34c759; border-radius:50%;',
        '  display:inline-block; animation:cpc-blink 1.6s infinite;',
        '  box-shadow:0 0 0 2px rgba(52,199,89,0.2);',
        '}',
        /* ── Bong bóng nổi ── */
        'div[data-testid="stPopover"] {',
        '  position:fixed !important; bottom:24px !important; right:24px !important;',
        '  left:auto !important; top:auto !important;',
        '  z-index:2147483646 !important; touch-action:none !important;',
        '}',
        'div[data-testid="stPopover"] > button {',
        '  border-radius:50% !important;',
        '  width:60px !important; height:60px !important;',
        '  min-width:60px !important; max-width:60px !important;',
        '  min-height:60px !important; max-height:60px !important;',
        '  padding:0 !important; overflow:hidden !important;',
        '  background:#fff !important; border:2px solid #ff3b30 !important;',
        '  cursor:grab !important;',
        '  transition:transform .18s cubic-bezier(.34,1.56,.64,1) !important;',
        '  display:flex !important; align-items:center !important; justify-content:center !important;',
        '}',
        'div[data-testid="stPopover"] > button:hover { transform:scale(1.09) !important; }',
        'div[data-testid="stPopover"] > button:active { cursor:grabbing !important; transform:scale(0.94) !important; }',
        'div[data-testid="stPopover"] > button svg { display:none !important; }',
        'div[data-testid="stPopover"] > button > div {',
        '  width:100% !important; height:100% !important;',
        '  display:flex !important; align-items:center !important; justify-content:center !important;',
        '}',
        /* ── Khung popover ── */
        'div[data-testid="stPopoverBody"] {',
        '  width:' + popWidth + 'px !important;',
        '  max-height:' + popHeight + 'px !important;',
        '  border-radius:16px !important;',
        '  box-shadow:0 16px 48px rgba(0,0,0,0.13),0 4px 14px rgba(0,0,0,0.07) !important;',
        '  border:1px solid rgba(0,0,0,0.07) !important;',
        '  padding:0 !important; overflow:hidden !important;',
        '  background:#f4f5f7 !important;',
        /* clip để popover không tràn ra ngoài màn hình */
        '  contain:layout !important;',
        '}',
        'div[data-testid="stPopoverBody"] footer { display:none !important; }',
        /* ── Scrollbar ── */
        'div[data-testid="stPopoverBody"] ::-webkit-scrollbar { width:5px !important; }',
        'div[data-testid="stPopoverBody"] ::-webkit-scrollbar-thumb { background:rgba(0,0,0,0.14) !important; border-radius:10px !important; }',
        /* ── Chat feed area ── */
        'div[data-testid="stPopoverBody"] div[data-testid="stChatMessageContainer"] { background:#f4f5f7 !important; padding:10px 12px !important; }',
        'div[data-testid="stPopoverBody"] div[data-testid="stChatMessage"] { background:transparent !important; padding:0 !important; margin-bottom:10px !important; border:none !important; }',
        /* ── Tin nhắn người dùng ── */
        '.cpc-user-msg { flex-direction:row-reverse !important; }',
        '.cpc-user-msg div[data-testid="stChatMessageContent"] {',
        '  background:#0055c4 !important; color:#fff !important;',
        '  border-radius:16px 16px 4px 16px !important;',
        '  padding:9px 13px !important; box-shadow:0 2px 8px rgba(0,85,196,.18) !important;',
        '}',
        '.cpc-user-msg div[data-testid="stChatMessageContent"] p,',
        '.cpc-user-msg div[data-testid="stChatMessageContent"] li { color:#fff !important; }',
        '.cpc-user-msg [data-testid="stChatMessageAvatar"] { display:none !important; }',
        /* ── Tin nhắn trợ lý ── */
        '.cpc-assistant-msg div[data-testid="stChatMessageContent"] {',
        '  background:#fff !important; color:#1d1d1f !important;',
        '  border-radius:16px 16px 16px 4px !important;',
        '  padding:9px 13px !important;',
        '  box-shadow:0 1px 6px rgba(0,0,0,0.05) !important;',
        '  border:1px solid #eef0f3 !important;',
        '}',
        '.cpc-assistant-msg div[data-testid="stChatMessageContent"] p,',
        '.cpc-assistant-msg div[data-testid="stChatMessageContent"] li { color:#1d1d1f !important; }',
        '.cpc-assistant-msg [data-testid="stChatMessageAvatar"] {',
        '  background:transparent !important; border:none !important;',
        '  width:30px !important; height:30px !important; margin-right:6px !important;',
        '}',
        /* ── Input area - FULL WIDTH ── */
        'div[data-testid="stPopoverBody"] div[data-testid="stChatInput"] {',
        '  background:#fff !important;',
        '  border-top:1px solid rgba(0,0,0,0.06) !important;',
        '  padding:8px 10px !important;',
        '  width:100% !important; box-sizing:border-box !important;',
        '}',
        'div[data-testid="stPopoverBody"] div[data-testid="stChatInput"] > div {',
        '  width:100% !important; box-sizing:border-box !important;',
        '  background:#f4f5f7 !important; border:1px solid #e5e5ea !important;',
        '  border-radius:20px !important; padding:0 !important; overflow:hidden !important;',
        '}',
        'div[data-testid="stPopoverBody"] div[data-testid="stChatInput"] textarea {',
        '  width:100% !important; box-sizing:border-box !important;',
        '  background:transparent !important; border:none !important;',
        '  box-shadow:none !important; color:#1d1d1f !important;',
        '  font-size:14px !important; padding:10px 45px 10px 14px !important;',
        '  line-height:1.45 !important; resize:none !important;',
        '}',
        'div[data-testid="stPopoverBody"] div[data-testid="stChatInput"] textarea:focus {',
        '  outline:none !important;',
        '}',
        'div[data-testid="stPopoverBody"] div[data-testid="stChatInput"] > div:focus-within {',
        '  border-color:#0055c4 !important;',
        '  box-shadow:0 0 0 3px rgba(0,85,196,0.12) !important;',
        '}',
        'div[data-testid="stPopoverBody"] div[data-testid="stChatInput"] button {',
        '  background:#0055c4 !important; color:#fff !important;',
        '  border:none !important; border-radius:50% !important;',
        '  width:32px !important; height:32px !important;',
        '  min-width:32px !important; min-height:32px !important;',
        '  padding:0 !important; cursor:pointer !important;',
        '  transition:background .15s !important;',
        '}',
        'div[data-testid="stPopoverBody"] div[data-testid="stChatInput"] button:hover {',
        '  background:#003fa3 !important;',
        '}',
        /* ── Header action buttons ── */
        'div[data-testid="stPopoverBody"] div[data-testid="stHorizontalBlock"] div[data-testid="column"] button {',
        '  background:transparent !important; border:none !important;',
        '  color:#86868b !important; font-size:17px !important;',
        '  padding:0 !important; min-height:auto !important;',
        '  height:30px !important; width:30px !important;',
        '  border-radius:6px !important;',
        '  display:flex !important; align-items:center !important; justify-content:center !important;',
        '  transition:background .15s, color .15s !important;',
        '}',
        'div[data-testid="stPopoverBody"] div[data-testid="stHorizontalBlock"] div[data-testid="column"] button:hover {',
        '  background:#ebebf0 !important; color:#1d1d1f !important;',
        '}'
    ].join('\\n');

    /* ===== 2. Hàm ép style và nội dung nút ===== */
    function fixPopover() {
        var pop = D.querySelector('div[data-testid="stPopover"]');
        if (!pop) return false;

        if (P.__fcp_left === undefined) {
            pop.style.cssText = 'position:fixed !important; bottom:24px !important; right:24px !important; left:auto !important; top:auto !important; z-index:2147483646 !important;';
        } else {
            var maxL = P.innerWidth - popWidth - 16;
            var cl = Math.min(P.__fcp_left, maxL);
            cl = Math.max(8, cl);
            pop.style.cssText = 'position:fixed !important; bottom:auto !important; right:auto !important; left:' + cl + 'px !important; top:' + P.__fcp_top + 'px !important; z-index:2147483646 !important;';
        }

        var btn = pop.querySelector('button');
        if (btn) {
            btn.style.cssText = 'border-radius:50%;width:60px;height:60px;min-width:60px;max-width:60px;min-height:60px;max-height:60px;padding:0;display:flex;align-items:center;justify-content:center;overflow:hidden;background:#fff;border:2px solid #ff3b30;cursor:grab;';
            var svgs = btn.querySelectorAll('svg:not(.cpc-robot-svg)');
            for (var i = 0; i < svgs.length; i++) svgs[i].style.display = 'none';
            var inner = btn.querySelector('div');
            if (inner && !inner.classList.contains('cpc-robot-injected')) {
                inner.innerHTML = robotSvgBubble;
                inner.classList.add('cpc-robot-injected');
                inner.style.width = '100%';
                inner.style.height = '100%';
            }
        }

        styleMessages();
        return true;
    }

    function styleMessages() {
        var messages = D.querySelectorAll('div[data-testid="stChatMessage"]');
        for (var i = 0; i < messages.length; i++) {
            var msg = messages[i];
            var avt = msg.querySelector('[data-testid="stChatMessageAvatar"]');
            if (!avt) continue;
            var txt = avt.textContent || '';
            if (txt.indexOf('\\uD83E\\uDDD1\\u200D\\uD83D\\uDCBB') !== -1 || txt.indexOf('👤') !== -1 || txt.indexOf('\\uD83E\\uDDD1') !== -1) {
                msg.classList.add('cpc-user-msg');
            } else if (txt.indexOf('\\uD83E\\uDD16') !== -1) {
                msg.classList.add('cpc-assistant-msg');
                var inner2 = avt.querySelector('div,span,p');
                if (inner2 && !inner2.classList.contains('cpc-avatar-replaced')) {
                    inner2.innerHTML = robotSvgAvatar;
                    inner2.classList.add('cpc-avatar-replaced');
                    avt.style.background = 'transparent';
                }
            }
        }
    }

    var tries = 0;
    function retry() {
        if (!fixPopover() && tries++ < 30) P.setTimeout(retry, 200);
    }
    retry();

    var obs = new MutationObserver(function() { fixPopover(); });
    obs.observe(D.body, { childList: true, subtree: true });

    /* ===== 3. Drag & Drop ===== */
    if (P.__fcp_drag_ok) return;
    P.__fcp_drag_ok = true;

    var drag = false, dragEl = null;
    var sx = 0, sy = 0, il = 0, it = 0, moved = false;

    function getPop()  { return D.querySelector('div[data-testid="stPopover"]'); }
    function getBtn2() { var p = getPop(); return p ? p.querySelector('button') : null; }

    D.addEventListener('mousedown', function(e) {
        var btn = getBtn2();
        if (!btn || !btn.contains(e.target)) return;
        var pop = getPop(); if (!pop) return;
        drag = true; moved = false; dragEl = pop;
        var r = pop.getBoundingClientRect();
        il = r.left; it = r.top; sx = e.clientX; sy = e.clientY;
        pop.style.transition = 'none';
        pop.style.bottom = 'auto'; pop.style.right = 'auto';
        pop.style.left = il + 'px'; pop.style.top = it + 'px';
    }, true);

    D.addEventListener('mousemove', function(e) {
        if (!drag || !dragEl) return;
        var dx = e.clientX - sx, dy = e.clientY - sy;
        if (Math.abs(dx) > 5 || Math.abs(dy) > 5) moved = true;
        var nL = Math.max(8, Math.min(il + dx, P.innerWidth - popWidth - 10));
        var nT = Math.max(8, Math.min(it + dy, P.innerHeight - 80));
        dragEl.style.left = nL + 'px'; dragEl.style.top = nT + 'px';
        P.__fcp_left = nL; P.__fcp_top = nT;
    });

    D.addEventListener('mouseup', function() {
        drag = false;
        if (dragEl) dragEl.style.transition = '';
        dragEl = null;
    });

    D.addEventListener('touchstart', function(e) {
        var btn = getBtn2();
        if (!btn || !btn.contains(e.target)) return;
        var pop = getPop(); if (!pop) return;
        drag = true; moved = false; dragEl = pop;
        var t = e.touches[0], r = pop.getBoundingClientRect();
        il = r.left; it = r.top; sx = t.clientX; sy = t.clientY;
        pop.style.transition = 'none';
        pop.style.bottom = 'auto'; pop.style.right = 'auto';
        pop.style.left = il + 'px'; pop.style.top = it + 'px';
    }, { passive: true });

    D.addEventListener('touchmove', function(e) {
        if (!drag || !dragEl) return;
        var t = e.touches[0];
        var dx = t.clientX - sx, dy = t.clientY - sy;
        if (Math.abs(dx) > 5 || Math.abs(dy) > 5) moved = true;
        var nL = Math.max(8, Math.min(il + dx, P.innerWidth - popWidth - 10));
        var nT = Math.max(8, Math.min(it + dy, P.innerHeight - 80));
        dragEl.style.left = nL + 'px'; dragEl.style.top = nT + 'px';
        P.__fcp_left = nL; P.__fcp_top = nT;
        e.preventDefault();
    }, { passive: false });

    D.addEventListener('touchend', function() {
        drag = false;
        if (dragEl) dragEl.style.transition = '';
        dragEl = null;
    });

    D.addEventListener('click', function(e) {
        var btn = getBtn2();
        if (btn && btn.contains(e.target) && moved) {
            e.stopPropagation(); e.preventDefault(); moved = false;
        }
    }, true);

})();
"""


def render_floating_assistant():
    """
    Bong bóng Trợ lý AI QA/QC Co-pilot — nổi tự do, kéo thả được.
    v5: AI fallback với trích dẫn nguồn, chat input full-width, popover không tràn.
    """
    # ── Session state ──────────────────────────────────────────────────────────
    if "copilot_messages" not in st.session_state:
        st.session_state.copilot_messages = [
            {
                "role": "assistant",
                "content": (
                    "👋 Xin chào! Tôi là **Trợ lý AI QC** của CPC1HN.\n\n"
                    "Tôi có thể giúp:\n"
                    "- 🔍 **Tra cứu thuốc thử & dung dịch** từ thư viện hệ thống (EP, USP, BP, DĐVN...)\n"
                    "- 📋 **Hỏi đáp chuyên môn** QA/QC Dược phẩm — có trích dẫn nguồn cụ thể\n"
                    "- 🗂️ **Hướng dẫn** quy trình SOP & vận hành hệ thống\n\n"
                    "Hãy gửi câu hỏi cho tôi nhé!"
                ),
            }
        ]
    if "copilot_expanded" not in st.session_state:
        st.session_state.copilot_expanded = False
    if "copilot_popover_open" not in st.session_state:
        st.session_state.copilot_popover_open = False

    def close_copilot_popover():
        st.session_state.copilot_popover_open = False

    # ── Kích thước động ───────────────────────────────────────────────────────
    popWidth  = 720 if st.session_state.copilot_expanded else 420
    popHeight = 690 if st.session_state.copilot_expanded else 590
    chat_height = 490 if st.session_state.copilot_expanded else 400

    # ── Inject CSS + JS vào parent document ────────────────────────────────────
    js_code = _JS_TEMPLATE
    js_code = js_code.replace("{robot_svg_bubble}", _ROBOT_SVG_BUBBLE.replace("\n", " "))
    js_code = js_code.replace("{robot_svg_avatar}", _ROBOT_SVG_AVATAR.replace("\n", " "))
    js_code = js_code.replace("{popWidth}", str(popWidth))
    js_code = js_code.replace("{popHeight}", str(popHeight))

    components.html(f"<script>{js_code}</script>", height=0, width=0)

    # ── Popover chính ─────────────────────────────────────────────────────────
    with st.popover("🤖", key="copilot_popover_open", on_change="rerun"):

        # ── Header ────────────────────────────────────────────────────────────
        hcol_left, hcol_clear, hcol_expand, hcol_close = st.columns([7.5, 1.5, 1.5, 1.5])

        with hcol_left:
            st.markdown(
                f"""
                <div style="display:flex;align-items:center;gap:8px;padding:2px 0;">
                     <div style="width:32px;height:32px;border-radius:50%;overflow:hidden;border:1.5px solid #ff3b30;background:#fff;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                        {_ROBOT_SVG_AVATAR}
                    </div>
                    <div style="display:flex;flex-direction:column;justify-content:center;min-width:0;">
                        <span style="font-size:13px;font-weight:700;color:#1d1d1f;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">Trợ lý AI QC</span>
                        <span style="font-size:10px;color:#34c759;font-weight:600;display:flex;align-items:center;gap:4px;line-height:1.3;">
                            <span class="cpc-online-dot"></span> Online · Tra cứu + AI
                        </span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with hcol_clear:
            if st.button("🧹", key="copilot_clear_btn", help="Xóa lịch sử chat"):
                st.session_state.copilot_messages = [
                    {"role": "assistant", "content": "🗑️ Lịch sử đã dọn dẹp. Tôi sẵn sàng hỗ trợ!"}
                ]
                st.rerun()

        with hcol_expand:
            icon_expand = "🗗" if st.session_state.copilot_expanded else "🗖"
            if st.button(icon_expand, key="copilot_toggle_size", help="Phóng to / Thu nhỏ"):
                st.session_state.copilot_expanded = not st.session_state.copilot_expanded
                st.rerun()

        with hcol_close:
            st.button("➖", key="copilot_close_btn", help="Ẩn trợ lý", on_click=close_copilot_popover)

        # Divider
        st.markdown(
            "<div style='border-bottom:1px solid rgba(0,0,0,0.05);margin:6px 0 8px;'></div>",
            unsafe_allow_html=True
        )

        # ── Vùng chat ─────────────────────────────────────────────────────────
        chat_container = st.container(height=chat_height)
        with chat_container:
            for msg in st.session_state.copilot_messages:
                avatar = "🧑" if msg["role"] == "user" else "🤖"
                with st.chat_message(msg["role"], avatar=avatar):
                    st.markdown(msg["content"])
                    # Nguồn DB
                    if msg.get("source"):
                        st.markdown(
                            f'<p style="font-size:10.5px;color:#0055c4;margin-top:2px;font-weight:600;">'
                            f'📚 Nguồn: {msg["source"]}</p>',
                            unsafe_allow_html=True,
                        )

        # ── Chat Input (full-width) ────────────────────────────────────────────
        user_query = st.chat_input("Nhập câu hỏi...", key="copilot_chat_input_val")

        if user_query:
            st.session_state.copilot_messages.append({"role": "user", "content": user_query})

            # Phân loại intent & tìm dữ liệu DB
            intent     = _detect_intent(user_query)
            db_context = _build_context_from_db(user_query, intent)

            # Xây dựng lịch sử (10 tin nhắn gần nhất)
            context_lines = []
            for m in st.session_state.copilot_messages[-10:-1]:
                prefix = "Người dùng" if m["role"] == "user" else "Trợ lý"
                context_lines.append(f"{prefix}: {m['content'][:400]}")
            history_str = "\n".join(context_lines)

            # ── Quyết định strategy ─────────────────────────────────────────
            if db_context:
                # Có dữ liệu trong hệ thống → dùng dữ liệu DB + AI diễn giải
                system_prompt = _SYSTEM_PROMPT_WITH_DB
                user_content = (
                    f"{history_str}\n\n"
                    f"--- DỮ LIỆU TÌM ĐƯỢC TRONG HỆ THỐNG ---\n"
                    f"{db_context}\n"
                    f"--- KẾT THÚC DỮ LIỆU ---\n\n"
                    f"Người dùng: {user_query}\n"
                    f"Trợ lý:"
                )
                source_label = "📖 Thư viện hệ thống CPC1HN"
            else:
                # Không có trong DB → AI fallback với trích dẫn nguồn chuẩn
                system_prompt = _SYSTEM_PROMPT_AI_FALLBACK
                user_content = (
                    f"{history_str}\n\n"
                    f"Câu hỏi của người dùng: {user_query}\n\n"
                    f"Hãy trả lời chính xác, có cấu trúc, trích dẫn nguồn cụ thể (tên Dược điển, phiên bản, chương/mục). "
                    f"Kết thúc bằng phần 📚 Nguồn tham khảo.\n"
                    f"Trợ lý:"
                )
                source_label = None  # AI sẽ tự liệt kê nguồn trong phần trả lời

            with chat_container:
                with st.chat_message("user", avatar="🧑"):
                    st.markdown(user_query)

                with st.chat_message("assistant", avatar="🤖"):
                    # Hiển thị badge trước khi stream
                    if not db_context:
                        st.caption("🔍 Không tìm thấy trong thư viện nội bộ · Đang tìm kiếm từ kiến thức chuyên môn...")

                    cleaned_response = "❌ Lỗi không xác định."
                    try:
                        resp_placeholder = st.empty()
                        stream_gen = call_ai_engine_stream(
                            system_instruction=system_prompt,
                            user_content=user_content,
                            provider="Google API",
                            model="gemma-4-31b-it",
                            temperature=0.1,
                        )
                        full_response = resp_placeholder.write_stream(stream_gen)
                        cleaned_response = clean_translation_prefix(str(full_response).strip())
                        if cleaned_response != full_response:
                            resp_placeholder.markdown(cleaned_response)

                        # Nguồn DB (nếu có)
                        if source_label:
                            st.markdown(
                                f'<p style="font-size:10.5px;color:#0055c4;margin-top:2px;font-weight:600;">'
                                f'{source_label}</p>',
                                unsafe_allow_html=True,
                            )

                    except Exception as e:
                        cleaned_response = (
                            f"❌ **Lỗi kết nối AI**: `{str(e)}`\n\n"
                            f"Vui lòng kiểm tra API Key trong mục **🔐 Quản Lý API Keys & Cấu hình**."
                        )
                        st.markdown(cleaned_response)

            # Lưu phản hồi
            st.session_state.copilot_messages.append({
                "role": "assistant",
                "content": cleaned_response,
                "source": source_label if db_context else None,
            })
            st.rerun()
