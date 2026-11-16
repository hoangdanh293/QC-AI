import random
import time
from google import genai
from google.genai import types
import openai
from core.key_manager import get_active_keys

GOOGLE_MODEL_ALIASES = {
    "gemini-3.1-pro": "gemini-3.1-pro-preview",
    "gemini-3.5-pro": "gemini-3.1-pro-preview",
    "gemini-1.5-pro": "gemini-2.5-pro",
    "gemini-1.5-flash": "gemini-2.5-flash",
    "gemini-2.0-flash": "gemini-2.5-flash",
}

GOOGLE_FALLBACK_MODELS = [
    "gemini-2.5-pro",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-2.5-flash",
    "gemma-4-26b-a4b-it",
]


def _resolve_google_model(model: str) -> str:
    """Map legacy/short Google model names to live API model IDs."""
    cleaned = (model or "").strip()
    return GOOGLE_MODEL_ALIASES.get(cleaned, cleaned)

def call_ai_engine(system_instruction, user_content, provider, model, google_keys=None, openai_keys=None, is_json=False, temperature=0.0, files=None):
    """
    Hàm gọi LLM đa nền tảng.
    Lưu ý: Tham số google_keys và openai_keys được giữ lại để tương thích ngược với code cũ, 
    hệ thống sẽ tự động sử dụng get_active_keys() để lấy key từ giao diện quản lý.
    """
    # Lấy danh sách key đang ở trạng thái kích hoạt khớp chính xác với Provider và Model
    keys_to_try = get_active_keys(provider, model)
    if not keys_to_try:
        # Tự động tìm key khác cùng Provider để tránh chặn người dùng khi đổi model
        from core.key_manager import load_api_keys
        try:
            key_data = load_api_keys()
            keys_to_try = [
                item["key_string"] for item in key_data.get("keys", [])
                if item["provider"] == provider
                and item.get("is_active") is True
                and item.get("key_string", "")
                and item.get("key_string", "") != "[GIẢI MÃ THẤT BẠI]"
            ]
        except Exception:
            pass
            
    if not keys_to_try:
        raise Exception(f"Không có API Key nào được kích hoạt cho mô hình '{model}' thuộc nhà cung cấp '{provider}'! Vui lòng vào Cấu hình để cấp phát.")
    
    # Xoay tua key ngẫu nhiên để chia đều tải (tránh Rate Limit)
    random.shuffle(keys_to_try)
    last_error = None

    # ==========================================
    # PROVIDER 1: GOOGLE API (Gemini / Gemma)
    # ==========================================
    if provider == "Google API":
        resolved_model = _resolve_google_model(model)
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
        
        for key in keys_to_try:
            for attempt in range(3): 
                try:
                    retry_options = types.HttpRetryOptions(
                        initial_delay=1.0,
                        attempts=2,
                        http_status_codes=[429, 500, 502, 503, 504]
                    )
                    client = genai.Client(
                        api_key=key.strip(),
                        http_options=types.HttpOptions(
                            timeout=120_000,
                            retry_options=retry_options,
                            client_args={"timeout": 120.0}
                        )
                    )
                    
                    is_gemma = "gemma" in model.lower()
                    config_args = {
                        "temperature": temperature,
                        "safety_settings": safety_settings
                    }
                    
                    # Đối với Gemma: Tránh lỗi treo API bằng cách đưa system_instruction vào user_content thay vì config
                    if is_gemma:
                        # Thêm JSON enforcement instruction khi cần JSON output
                        json_enforce_prefix = ""
                        if is_json:
                            # Tu dong phat hien kieu JSON (Array vs Object) tu noi dung system_instruction
                            _si_lower = system_instruction.lower()
                            _expects_array = (
                                "json array" in _si_lower
                                or "mang rong: []" in system_instruction
                                or "mảng rỗng: []" in system_instruction
                                or "tra ve duy nhat mot json array" in _si_lower
                                or "trả về duy nhất một json array" in _si_lower
                            )
                            if _expects_array:
                                json_enforce_prefix = (
                                    "CRITICAL INSTRUCTION: Your response MUST be ONLY a valid JSON array. "
                                    "Start your response IMMEDIATELY with '[' and end with ']'. "
                                    "No preamble, no explanation, no markdown code blocks.\n\n"
                                )
                            else:
                                json_enforce_prefix = (
                                    "CRITICAL INSTRUCTION: Your response MUST be ONLY a valid JSON object. "
                                    "Start your response IMMEDIATELY with '{' and end with '}'. "
                                    "No preamble, no explanation, no markdown code blocks.\n\n"
                                )
                        gemma_prompt = f"{json_enforce_prefix}{system_instruction}\n\nYêu cầu:\n{user_content}"
                        if files:
                            import base64
                            contents = []
                            for f in files:
                                file_bytes = base64.b64decode(f["data"])
                                contents.append(
                                    types.Part.from_bytes(
                                        data=file_bytes,
                                        mime_type=f["mime_type"]
                                    )
                                )
                            contents.append(gemma_prompt)
                        else:
                            contents = gemma_prompt
                    else:
                        config_args["system_instruction"] = system_instruction
                        if "gemini" in model.lower() and is_json:
                            config_args["response_mime_type"] = "application/json"
                            
                        if files:
                            import base64
                            contents = []
                            for f in files:
                                file_bytes = base64.b64decode(f["data"])
                                contents.append(
                                    types.Part.from_bytes(
                                        data=file_bytes,
                                        mime_type=f["mime_type"]
                                    )
                                )
                            contents.append(user_content)
                        else:
                            contents = user_content
                        
                    config = types.GenerateContentConfig(**config_args)
                    response = client.models.generate_content(model=resolved_model, contents=contents, config=config)
                    raw_text = response.text if response.text else "{}"
                    
                    # Post-process cho Gemma: Strip markdown code fences thường xuất hiện trong response
                    if is_gemma and is_json and raw_text:
                        stripped = raw_text.strip()
                        # Xóa ```json ... ``` hoặc ``` ... ```
                        if stripped.startswith("```"):
                            lines_resp = stripped.split("\n")
                            # Bỏ dòng đầu (```json hoặc ```) và dòng cuối (```)
                            if lines_resp[-1].strip() == "```":
                                lines_resp = lines_resp[1:-1]
                            elif lines_resp[0].strip().startswith("```"):
                                lines_resp = lines_resp[1:]
                            raw_text = "\n".join(lines_resp).strip()
                    return raw_text
                except Exception as e:
                    last_error = str(e).lower()
                    # Nếu gặp lỗi rate limit / quota, ngủ exponential backoff + jitter và thử lại
                    if "503" in last_error or "429" in last_error or "quota" in last_error or "resource_exhausted" in last_error:
                        if attempt < 2:
                            sleep_sec = min(30, (2 ** attempt) + random.uniform(0.5, 2.0))
                            time.sleep(sleep_sec) 
                            continue
                    
                    # Tự động kích hoạt chế độ tự phục hồi bằng các mô hình dự phòng cùng nhà cung cấp
                    # Danh sách các mô hình dự phòng của Google API (ưu tiên Gemini trước Gemma)
                    fallbacks = [m for m in GOOGLE_FALLBACK_MODELS if m != resolved_model]
                    
                    for fb_model in fallbacks:
                        try:
                            fb_is_gemma = "gemma" in fb_model.lower()
                            
                            # Xây dựng contents cho model dự phòng (giữ nguyên files nếu có)
                            fb_contents = []
                            if files:
                                import base64
                                for f in files:
                                    file_bytes = base64.b64decode(f["data"])
                                    fb_contents.append(
                                        types.Part.from_bytes(
                                            data=file_bytes,
                                            mime_type=f["mime_type"]
                                        )
                                    )
                            
                            if fb_is_gemma:
                                fb_json_prefix = ""
                                if is_json:
                                    fb_json_prefix = (
                                        "CRITICAL INSTRUCTION: Your response MUST be ONLY a valid JSON object. "
                                        "Start your response IMMEDIATELY with '{' and end with '}'. "
                                        "No preamble, no explanation, no markdown code blocks.\n\n"
                                    )
                                fb_prompt = f"{fb_json_prefix}{system_instruction}\n\nYêu cầu:\n{user_content}"
                                if files:
                                    fb_contents.append(fb_prompt)
                                else:
                                    fb_contents = fb_prompt
                                fb_config = types.GenerateContentConfig(
                                    temperature=temperature,
                                    safety_settings=safety_settings
                                )
                            else:
                                if files:
                                    fb_contents.append(user_content)
                                else:
                                    fb_contents = user_content
                                    
                                fb_config_args = {
                                    "temperature": temperature,
                                    "safety_settings": safety_settings,
                                    "system_instruction": system_instruction
                                }
                                if is_json:
                                    fb_config_args["response_mime_type"] = "application/json"
                                fb_config = types.GenerateContentConfig(**fb_config_args)
                            
                            response = client.models.generate_content(model=fb_model, contents=fb_contents, config=fb_config)
                            if response.text:
                                fb_text = response.text
                                # Post-process cho fallback Gemma: Strip markdown code fences
                                if fb_is_gemma and is_json:
                                    fb_stripped = fb_text.strip()
                                    if fb_stripped.startswith("```"):
                                        fb_lines = fb_stripped.split("\n")
                                        if fb_lines[-1].strip() == "```":
                                            fb_lines = fb_lines[1:-1]
                                        elif fb_lines[0].strip().startswith("```"):
                                            fb_lines = fb_lines[1:]
                                        fb_text = "\n".join(fb_lines).strip()
                                return fb_text
                        except Exception as fb_err:
                            last_error += f" | {fb_model} failed: {str(fb_err)}"
                    break
        raise Exception(f"Google API từ chối toàn bộ truy cập. Lỗi: {last_error}")

    # ==========================================
    # PROVIDER 2: OPENAI (GPT-4o, GPT-3.5...)
    # ==========================================
    elif provider == "OpenAI":
        for key in keys_to_try:
            for attempt in range(2):
                try:
                    client = openai.OpenAI(api_key=key.strip())
                    
                    # Cấu hình gọi API của OpenAI
                    messages_content = []
                    if files:
                        for f in files:
                            if f["mime_type"].startswith("image/"):
                                messages_content.append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{f['mime_type']};base64,{f['data']}"
                                    }
                                })
                            elif f["mime_type"].startswith("text/"):
                                try:
                                    import base64
                                    text_content = base64.b64decode(f["data"]).decode("utf-8")
                                    messages_content.append({
                                        "type": "text",
                                        "text": f"Nội dung file {f['file_name']}:\n{text_content}"
                                    })
                                except:
                                    pass
                    
                    messages_content.append({
                        "type": "text",
                        "text": user_content
                    })

                    response = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": messages_content}
                        ],
                        temperature=temperature,
                        response_format={"type": "json_object"} if is_json else {"type": "text"}
                    )
                    return response.choices[0].message.content or "{}"
                except Exception as e:
                    last_error = str(e).lower()
                    if "rate_limit" in last_error or "429" in last_error or "quota" in last_error:
                        time.sleep(2)
                        continue
                    else: break
        raise Exception(f"OpenAI từ chối toàn bộ truy cập. Lỗi: {last_error}")
    
    else:
        raise Exception(f"Nhà cung cấp {provider} chưa được hỗ trợ!")


def call_ai_engine_stream(system_instruction, user_content, provider, model, google_keys=None, openai_keys=None, temperature=0.0):
    """
    Hàm gọi LLM đa nền tảng có hỗ trợ STREAMING (trả về generator).
    """
    keys_to_try = get_active_keys(provider, model)
    if not keys_to_try:
        from core.key_manager import load_api_keys
        try:
            key_data = load_api_keys()
            keys_to_try = [
                item["key_string"] for item in key_data.get("keys", [])
                if item["provider"] == provider and item.get("is_active") is True
            ]
        except Exception:
            pass
            
    if not keys_to_try:
        raise Exception(f"Không có API Key nào được kích hoạt cho mô hình '{model}' thuộc nhà cung cấp '{provider}'! Vui lòng vào Cấu hình để cấp phát.")
    
    random.shuffle(keys_to_try)
    last_error = None

    if provider == "Google API":
        resolved_model = _resolve_google_model(model)
        safety_settings = [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ]
        
        for key in keys_to_try:
            for attempt in range(3): 
                try:
                    retry_options = types.HttpRetryOptions(
                        initial_delay=1.0,
                        attempts=2,
                        http_status_codes=[429, 500, 502, 503, 504]
                    )
                    client = genai.Client(
                        api_key=key.strip(),
                        http_options=types.HttpOptions(
                            timeout=120_000,
                            retry_options=retry_options,
                            client_args={"timeout": 120.0}
                        )
                    )
                    is_gemma = "gemma" in model.lower()
                    config_args = {
                        "temperature": temperature,
                        "safety_settings": safety_settings
                    }
                    
                    if is_gemma:
                        contents = f"{system_instruction}\n\nYêu cầu:\n{user_content}"
                    else:
                        config_args["system_instruction"] = system_instruction
                        contents = user_content
                        
                    config = types.GenerateContentConfig(**config_args)
                    response_stream = client.models.generate_content_stream(model=resolved_model, contents=contents, config=config)
                    for chunk in response_stream:
                        if chunk.text:
                            yield chunk.text
                    return
                except Exception as e:
                    last_error = str(e).lower()
                    if "503" in last_error or "429" in last_error or "quota" in last_error or "resource_exhausted" in last_error:
                        if attempt < 2:
                            time.sleep(2) 
                            continue
                    
                    # Fallback logic for streaming
                    fallbacks = [m for m in GOOGLE_FALLBACK_MODELS if m != resolved_model]
                    
                    for fb_model in fallbacks:
                        try:
                            fb_is_gemma = "gemma" in fb_model.lower()
                            if fb_is_gemma:
                                fb_contents = f"{system_instruction}\n\nYêu cầu:\n{user_content}"
                                fb_config = types.GenerateContentConfig(
                                    temperature=temperature,
                                    safety_settings=safety_settings
                                )
                            else:
                                fb_contents = user_content
                                fb_config = types.GenerateContentConfig(
                                    temperature=temperature,
                                    safety_settings=safety_settings,
                                    system_instruction=system_instruction
                                )
                            
                            fb_response_stream = client.models.generate_content_stream(model=fb_model, contents=fb_contents, config=fb_config)
                            for chunk in fb_response_stream:
                                if chunk.text:
                                    yield chunk.text
                            return
                        except Exception as fb_err:
                            last_error += f" | {fb_model} failed: {str(fb_err)}"
                    break
        raise Exception(f"Google API từ chối toàn bộ truy cập. Lỗi: {last_error}")

    elif provider == "OpenAI":
        for key in keys_to_try:
            for attempt in range(2):
                try:
                    client = openai.OpenAI(api_key=key.strip())
                    response_stream = client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": user_content}
                        ],
                        temperature=temperature,
                        stream=True
                    )
                    for chunk in response_stream:
                        if chunk.choices and chunk.choices[0].delta.content:
                            yield chunk.choices[0].delta.content
                    return
                except Exception as e:
                    last_error = str(e).lower()
                    if "rate_limit" in last_error or "429" in last_error or "quota" in last_error:
                        time.sleep(2)
                        continue
                    else: break
        raise Exception(f"OpenAI từ chối toàn bộ truy cập. Lỗi: {last_error}")
    
    else:
        raise Exception(f"Nhà cung cấp {provider} chưa được hỗ trợ!")



def clean_translation_prefix(text):
    if not text: return ""
    import re
    text_str = str(text).strip()
    
    # 1. Clean leading colon if present
    text_str = re.sub(r'^:\s*', '', text_str)
    
    # 2. Clean outer quotes if they wrap the entire string
    if (text_str.startswith('"') and text_str.endswith('"')) or (text_str.startswith("'") and text_str.endswith("'")):
        text_str = text_str[1:-1].strip()
        
    # 3. Replace raw literal backslash-escapes with actual control chars safely
    # (Avoid mangling LaTeX commands like \rightarrow, \times, \neq)
    text_str = re.sub(r'\\n(?![a-zA-Z0-9_])', '\n', text_str)
    text_str = re.sub(r'\\r(?![a-zA-Z0-9_])', '\r', text_str)
    text_str = re.sub(r'\\t(?![a-zA-Z0-9_])', '\t', text_str)
    text_str = text_str.replace('\\"', '"').replace("\\'", "'")
    
    lines = text_str.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Case 1: (Dịch: ...) or (Dich: ...)
        if (stripped.startswith("(") or stripped.startswith("(")) and stripped.endswith(")"):
            inner = stripped[1:-1].strip()
            m = re.match(r'^(?:Dịch|dịch|Bản dịch|bản dịch|Translation|translation|Dich|dich)\s*:\s*(.*)$', inner, re.IGNORECASE)
            if m:
                stripped = m.group(1).strip()
        # Case 2: Dịch: ...
        else:
            m = re.match(r'^(?:Dịch|dịch|Bản dịch|bản dịch|Translation|translation|Dich|dich)\s*:\s*(.*)$', stripped, re.IGNORECASE)
            if m:
                stripped = m.group(1).strip()
        
        # Clean any remaining inline "(Dịch: ...)"
        stripped = re.sub(r'\(\s*(?:Dịch|dịch|Bản dịch|bản dịch|Translation|translation|Dich|dich)\s*:\s*(.*?)\s*\)', r'\1', stripped, flags=re.IGNORECASE)
        
        cleaned_lines.append(stripped)
    return "\n".join(cleaned_lines)


def translate_text_to_bilingual(text, provider, model, context_type="sop"):
    """
    Dịch văn bản sang song ngữ Việt - Anh.
    context_type: 'sop' (cho quy trình kiểm nghiệm), 'criteria' (cho tên chỉ tiêu), 'limit' (cho giới hạn)
    """
    if not text or not text.strip():
        return ""
        
    system_instruction = """Bạn là chuyên gia dịch thuật song ngữ Việt - Anh trong ngành Dược phẩm và Kiểm nghiệm chất lượng (QA/QC).
    NHIỆM VỤ: Dịch văn bản đầu vào sang dạng song ngữ Việt - Anh.
    TUYỆT ĐỐI KHÔNG thêm các từ như "Dịch:", "(Dịch: ...)", "Bản dịch:", hoặc bất kỳ chú thích dịch thuật tương tự nào vào kết quả. Chỉ trả về kết quả dịch trực tiếp dưới dạng song ngữ hoặc đơn ngữ theo yêu cầu.
    """
    
    if context_type == "sop":
        system_instruction += """
        QUY TẮC DỊCH SOP:
        - Giữ nguyên cấu trúc phân đoạn và xuống dòng của văn bản gốc.
        - Mọi mô tả, bước tiến hành, chuẩn bị mẫu, chuẩn bị thuốc thử, cách đo và công thức tính toán đều phải được trình bày song ngữ dòng-dòng hoặc câu-câu.
        - Định dạng song ngữ bắt buộc: `[Câu Tiếng Việt] / [Bản dịch Tiếng Anh]`. Cần dịch sát nghĩa chuyên ngành dược điển (ví dụ: USP, EP, BP, DĐVN).
        - Ví dụ: `Chuẩn bị điện cực / Prepare the electrode.`
        - Không thay đổi các giá trị số, đơn vị đo (ví dụ: ml, g, °C), hoặc công thức hóa học.
        - Tuyệt đối không thêm từ "Dịch:", "Bản dịch:" hay ngoặc đơn chú thích dịch thuật tương tự.
        """
        user_content = f"Hãy dịch đoạn SOP sau sang song ngữ Việt - Anh theo định dạng bắt buộc `[Câu Tiếng Việt] / [Bản dịch Tiếng Anh]`:\n\n{text}"
    elif context_type == "criteria":
        system_instruction += """
        QUY TẮC DỊCH TÊN CHỈ TIÊU:
        - Dịch tên chỉ tiêu kiểm nghiệm sang dạng song ngữ: `[Tên Tiếng Việt] / [Tên Tiếng Anh]`.
        - Ví dụ: `Hàm lượng nước / Water content`, `Độ ẩm / Moisture content`, `Tro sulfat / Sulfated ash`.
        - Chỉ trả về chuỗi song ngữ, không giải thích gì thêm.
        - Tuyệt đối không thêm từ "Dịch:", "Bản dịch:" hay ngoặc đơn chú thích dịch thuật tương tự.
        """
        user_content = f"Dịch tên chỉ tiêu này sang song ngữ: {text}"
    else:  # limit
        system_instruction += """
        QUY TẮC DỊCH GIỚI HẠN CHỈ TIÊU:
        - Dịch giới hạn/tiêu chuẩn chấp nhận sang dạng song ngữ: `[Tiếng Việt] / [Tiếng Anh]`.
        - Ví dụ: `Không quá 1,0% / Not more than 1.0%`, `Bột kết tinh màu trắng / White crystalline powder`.
        - Chỉ trả về chuỗi song ngữ, không giải thích gì thêm.
        - Tuyệt đối không thêm từ "Dịch:", "Bản dịch:" hay ngoặc đơn chú thích dịch thuật tương tự.
        """
        user_content = f"Dịch giới hạn chỉ tiêu này sang song ngữ: {text}"
        
    response = call_ai_engine(
        system_instruction=system_instruction,
        user_content=user_content,
        provider=provider,
        model=model,
        temperature=0.0
    )
    return clean_translation_prefix(response.strip())


def translate_text_to_vietnamese_only(text, provider, model, context_type="sop"):
    """
    Dịch văn bản sang tiếng Việt thuần túy (KHÔNG song ngữ).
    Dùng khi người dùng tắt chế độ song ngữ.
    context_type: 'sop' | 'criteria' | 'limit'
    """
    if not text or not text.strip():
        return ""

    system_instruction = """Bạn là chuyên gia dịch thuật chuyên ngành Dược phẩm và Kiểm nghiệm chất lượng (QA/QC).
    NHIỆM VỤ: Dịch văn bản đầu vào sang Tiếng Việt thuần túy (đơn ngữ).
    TUYỆT ĐỐI KHÔNG dịch sang dạng song ngữ "Việt / Anh".
    TUYỆT ĐỐI KHÔNG giữ lại bản dịch tiếng Anh kèm theo.
    TUYỆT ĐỐI KHÔNG thêm "Dịch:", "(Dịch: ...)", "Bản dịch:", hay bất kỳ chú thích nào.
    Ngoại lệ: Giữ nguyên ký hiệu hóa học (NaCl, H₂SO₄...), đơn vị đo (mg/mL, %, rpm...), tên phương pháp viết tắt (HPLC, UV-Vis...).
    Chỉ trả về bản dịch tiếng Việt, không có gì khác.
    """

    if context_type == "sop":
        system_instruction += """
        QUY TẮC DỊCH SOP:
        - Giữ nguyên cấu trúc phân đoạn và xuống dòng của văn bản gốc.
        - Dịch toàn bộ nội dung sang tiếng Việt chuẩn dược lý.
        - Không thay đổi các giá trị số, đơn vị đo, công thức hóa học.
        """
        user_content = f"Hãy dịch đoạn SOP sau sang Tiếng Việt thuần túy (không song ngữ):\n\n{text}"
    elif context_type == "criteria":
        system_instruction += """
        QUY TẮC DỊCH TÊN CHỈ TIÊU:
        - Dịch tên chỉ tiêu kiểm nghiệm sang tiếng Việt.
        - Ví dụ: "Water content" → "Hàm lượng nước", "Sulfated ash" → "Tro sulfat".
        - Chỉ trả về tên tiếng Việt, không kèm tiếng Anh.
        """
        user_content = f"Dịch tên chỉ tiêu này sang Tiếng Việt (không song ngữ): {text}"
    else:  # limit
        system_instruction += """
        QUY TẮC DỊCH GIỚI HẠN:
        - Dịch giới hạn/tiêu chuẩn chấp nhận sang tiếng Việt.
        - Ví dụ: "Not more than 1.0%" → "Không quá 1,0%".
        - Chỉ trả về chuỗi tiếng Việt, không kèm tiếng Anh.
        """
        user_content = f"Dịch giới hạn chỉ tiêu này sang Tiếng Việt (không song ngữ): {text}"

    response = call_ai_engine(
        system_instruction=system_instruction,
        user_content=user_content,
        provider=provider,
        model=model,
        temperature=0.0
    )
    return clean_translation_prefix(response.strip())


def call_ai_engine_parallel(tasks, max_workers=4):
    """
    Gọi AI song song cho nhiều task cùng lúc.
    Mỗi task là một dict:
        {
            "index": int,
            "system_instruction": str,
            "user_content": str,
            "provider": str,
            "model": str,
            "is_json": bool,   # optional, default False
            "temperature": float  # optional, default 0.0
        }
    Trả về list kết quả (str) theo đúng thứ tự index, hoặc None nếu task đó lỗi.
    """
    import concurrent.futures

    def _run_task(task):
        idx = task["index"]
        try:
            result = call_ai_engine(
                system_instruction=task["system_instruction"],
                user_content=task["user_content"],
                provider=task["provider"],
                model=task["model"],
                is_json=task.get("is_json", False),
                temperature=task.get("temperature", 0.0)
            )
            return (idx, result, None)
        except Exception as e:
            return (idx, None, str(e))

    results_map = {}
    errors_map = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run_task, task): task["index"] for task in tasks}
        for future in concurrent.futures.as_completed(futures):
            idx, result, err = future.result()
            results_map[idx] = result
            if err:
                errors_map[idx] = err

    # Sắp xếp kết quả theo thứ tự index
    ordered_results = [results_map.get(i) for i in range(len(tasks))]
    return ordered_results, errors_map