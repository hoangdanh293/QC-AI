# -*- coding: utf-8 -*-
"""
Comprehensive 10-Criteria Evaluation Suite for QC AI CPC1HN.
Compares models (gemini-3.1-pro vs gemini-3.8-flash) on:
  - Test/Potassium Sorbate.pdf (USP-NF Monograph)
  - Test/COA Potassium Sorbate.pdf (Manufacturer COA)
Outputs:
  - Test/eval_output/TCNL_Potassium_Sorbate_<model>.docx
  - Test/eval_output/eval_results.json
  - Test/eval_output/BAO_CAO_DANH_GIA_DICH_THUAT.md
  - Test/eval_output/BAO_CAO_DANH_GIA_DICH_THUAT.html
"""
import concurrent.futures
import datetime
import html as html_lib
import io
import json
import os
import re
import sys
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import docx
import fitz

from core.ai_handler import call_ai_engine
from core.doc_processor import (
    node_phase_1_scan_metadata,
    prepare_file_for_ai,
    safe_json_loads,
    tcnl_ai_semantic_reconciliation,
    tcnl_extract_monograph_name,
    tcnl_generate_methods,
    tcnl_scan_criteria_and_limits,
)
from core.key_manager import load_api_keys
from core.word_exporter import node_4_generate_word
from ui_modules.ui_tcnl import _normalize_name

MODELS_TO_TEST = ["gemini-3.1-pro", "gemini-3.8-flash"]
JUDGE_MODEL = "gemini-3.1-pro"

USP_PATH = os.path.join(ROOT, "Test", "Potassium Sorbate.pdf")
COA_PATH = os.path.join(ROOT, "Test", "COA Potassium Sorbate.pdf")
TEMPLATE_TCNL = os.path.join(ROOT, "Template_Form_TCNL.docx")
OUTPUT_DIR = os.path.join(ROOT, "Test", "eval_output")

# Ground truth for Potassium Sorbate (USP-NF + COA)
GROUND_TRUTH = {
    "tinh_chat": {
        "label": "Tính chất / Cảm quan (Description / Appearance)",
        "name_kws": ["tinh chat", "cam quan", "appearance", "description", "ngoai quan"],
        "limit_kws": ["white", "trang", "powder", "bot", "granular", "hat", "crystalline", "ket tinh"],
        "required": True,
    },
    "dinh_tinh": {
        "label": "Định tính (Identification)",
        "name_kws": ["dinh tinh", "identification"],
        "limit_kws": ["a", "b", "ir", "uv", "potassium", "kali", "sorbate", "passes", "dat", "dung"],
        "required": True,
    },
    "do_kiem": {
        "label": "Độ kiềm (Alkalinity as K2CO3)",
        "name_kws": ["kiem", "alkalinity", "k2co3", "acidity"],
        "limit_kws": ["1.0", "1,0", "1%", "nmt", "not more than", "khong qua"],
        "required": True,
    },
    "mat_khoi_luong_do_say": {
        "label": "Mất khối lượng do làm khô (Loss on drying)",
        "name_kws": ["say", "drying", "loss on drying", "mat khoi luong"],
        "limit_kws": ["1.0", "1,0", "1%", "105", "3", "nmt", "not more than", "khong qua"],
        "required": True,
    },
    "dinh_luong": {
        "label": "Định lượng (Assay)",
        "name_kws": ["dinh luong", "assay", "content", "ham luong"],
        "limit_kws": ["98.0", "101.0", "98,0", "101,0", "%"],
        "required": True,
    },
    "aldehyd": {
        "label": "Giới hạn Aldehyd (Aldehydes)",
        "name_kws": ["aldehyd", "aldehyde"],
        "limit_kws": ["0.15", "0,15", "0.1", "nmt", "not more than", "khong qua", "%"],
        "required": False,
    },
    "kim_loai_nang_chi": {
        "label": "Kim loại nặng / Chì (Heavy metals / Lead)",
        "name_kws": ["kim loai", "heavy metals", "lead", "chi", "pb"],
        "limit_kws": ["10", "5", "2", "ppm", "ug/g", "nmt", "not more than", "khong qua"],
        "required": False,
    },
}

EXPECTED_RECON_PAIRS = [
    ("tinh_chat", ["tinh chat", "cam quan", "appearance", "description"]),
    ("dinh_tinh", ["dinh tinh", "identification"]),
    ("do_kiem", ["kiem", "alkalinity"]),
    ("mat_khoi_luong_do_say", ["say", "drying", "mat khoi luong"]),
    ("dinh_luong", ["dinh luong", "assay"]),
]


class MockFile:
    def __init__(self, filepath: str):
        self.name = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            self._bytes = f.read()
        self._pos = 0

    def seek(self, pos: int) -> None:
        self._pos = pos

    def read(self, n: int = -1) -> bytes:
        if n == -1:
            d = self._bytes[self._pos :]
            self._pos = len(self._bytes)
            return d
        d = self._bytes[self._pos : self._pos + n]
        self._pos += len(d)
        return d

    def getvalue(self) -> bytes:
        return self._bytes


def extract_pdf_text(path: str) -> str:
    doc = fitz.open(path)
    return "\n".join(page.get_text("text") for page in doc)


def inspect_docx_output(docx_path: str, expected_criteria_count: int, monograph_name: str) -> dict:
    doc = docx.Document(docx_path)
    all_texts = [p.text for p in doc.paragraphs]
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                all_texts.append(cell.text)
    joined = "\n".join(all_texts)

    leftover_tags = re.findall(r"\{\{.*?\}\}", joined)
    has_xoa_hang = "XOA_HANG" in joined
    has_monograph = any(
        kw in joined.lower() for kw in ["potassium sorbate", "kali sorbat", monograph_name.lower()[:10]]
    )

    # Find the main criteria table (table with >= expected_criteria_count rows and >= 3 cols)
    best_table_rows = 0
    non_empty_method_cells = 0
    for tbl in doc.tables:
        if len(tbl.rows) >= expected_criteria_count and len(tbl.columns) >= 3:
            if len(tbl.rows) > best_table_rows:
                best_table_rows = len(tbl.rows)
                non_empty_method_cells = sum(
                    1 for r in tbl.rows if len(r.cells) >= 3 and len(r.cells[2].text.strip()) > 15
                )

    score = 10.0
    if leftover_tags:
        score -= min(4.0, len(leftover_tags) * 1.0)
    if has_xoa_hang:
        score -= 2.0
    if not has_monograph:
        score -= 2.0
    if best_table_rows < expected_criteria_count:
        score -= 2.0
    if non_empty_method_cells < max(1, expected_criteria_count - 1):
        score -= 1.5

    return {
        "score": round(max(0.0, score), 2),
        "leftover_tags": leftover_tags,
        "has_xoa_hang": has_xoa_hang,
        "has_monograph": has_monograph,
        "best_table_rows": best_table_rows,
        "non_empty_method_cells": non_empty_method_cells,
    }


def deterministic_score(
    usp_criteria: list,
    coa_criteria: list,
    recon_result: list | dict,
    methods_result: dict,
    docx_check: dict,
    meta_scan: dict,
) -> dict:
    # Criterion 2: Criteria recognition (Recall & Precision on required items)
    all_scanned = usp_criteria + coa_criteria
    matched_gt = 0
    required_total = 0
    required_matched = 0
    limit_matched = 0
    detail_rows = []

    for gt_key, gt in GROUND_TRUTH.items():
        if gt["required"]:
            required_total += 1
        found_item = None
        for item in all_scanned:
            nm = _normalize_name(item.get("ten_chi_tieu", ""))
            if any(kw in nm for kw in gt["name_kws"]):
                found_item = item
                break
        if found_item:
            matched_gt += 1
            if gt["required"]:
                required_matched += 1
            lim = (found_item.get("gioi_han") or "").lower()
            lim_ok = any(kw in lim for kw in gt["limit_kws"])
            if lim_ok:
                limit_matched += 1
            detail_rows.append(
                {
                    "gt": gt["label"],
                    "found": True,
                    "scanned_name": found_item.get("ten_chi_tieu", ""),
                    "scanned_limit": found_item.get("gioi_han", ""),
                    "limit_ok": lim_ok,
                }
            )
        else:
            detail_rows.append(
                {
                    "gt": gt["label"],
                    "found": False,
                    "scanned_name": "",
                    "scanned_limit": "",
                    "limit_ok": False,
                }
            )

    c2_score = round((required_matched / max(1, required_total)) * 8.0 + (matched_gt / len(GROUND_TRUTH)) * 2.0, 2)
    c4_score = round((limit_matched / max(1, matched_gt)) * 10.0, 2)

    # Criterion 3: Semantic reconciliation (same criteria grouped across USP & COA)
    if isinstance(recon_result, list):
        merged_list = recon_result
    elif isinstance(recon_result, dict):
        merged_list = recon_result.get("merged_criteria") or recon_result.get("criteria") or []
    else:
        merged_list = []

    grouped_both = 0
    for _, kws in EXPECTED_RECON_PAIRS:
        for row in merged_list:
            if not isinstance(row, dict):
                continue
            nm = _normalize_name(
                row.get("ten_chi_tieu", "")
                or row.get("ten_chuan", "")
                or row.get("name", "")
            )
            if any(kw in nm for kw in kws):
                sources = row.get("sources") or row.get("nguon") or row.get("chi_tiet_nguon") or {}
                has_two = (isinstance(sources, (dict, list)) and len(sources) >= 2) or (
                    bool(row.get("gioi_han_usp") or row.get("gioi_han")) and bool(row.get("gioi_han_coa") or row.get("so_sanh"))
                )
                if has_two or len(merged_list) <= (len(usp_criteria) + len(coa_criteria) - 3):
                    grouped_both += 1
                break
    c3_score = round((grouped_both / len(EXPECTED_RECON_PAIRS)) * 10.0, 2) if merged_list else 5.0

    # Criterion 1: Content extraction completeness (methods non-empty + metadata scan)
    non_empty_methods = sum(1 for v in methods_result.values() if isinstance(v, str) and len(v.strip()) > 30)
    method_ratio = non_empty_methods / max(1, len(usp_criteria))
    meta_ok = 1.0 if (isinstance(meta_scan, dict) and len(meta_scan) >= 2) else 0.5
    c1_score = round(min(10.0, method_ratio * 8.5 + meta_ok * 1.5), 2)

    return {
        "c1_extract": c1_score,
        "c2_identify": c2_score,
        "c3_similarity": c3_score,
        "c4_limits": c4_score,
        "c9_template": docx_check["score"],
        "gt_details": detail_rows,
        "non_empty_methods": non_empty_methods,
        "total_usp_criteria": len(usp_criteria),
        "total_coa_criteria": len(coa_criteria),
        "merged_count": len(merged_list),
    }


def llm_judge_model(
    model_name: str,
    usp_text: str,
    coa_text: str,
    usp_criteria: list,
    coa_criteria: list,
    recon_result: dict,
    methods_result: dict,
    google_keys: list[str],
) -> dict:
    """Use AI-as-a-Judge to score all 10 criteria with concrete evidence and improvement notes."""
    sample_methods = {}
    for k, v in list(methods_result.items())[:8]:
        sample_methods[k] = v[:1500] if isinstance(v, str) else str(v)[:1500]

    prompt = f"""Bạn là Chuyên gia Đảm bảo Chất lượng Dược phẩm (QA/QC) và Kỹ sư AI.
Hãy đánh giá kết quả đầu ra của mô hình `{model_name}` trên cặp tài liệu gốc Potassium Sorbate (USP-NF & COA) theo đúng 10 tiêu chí bên dưới.

=== TEXT GỐC USP-NF (trích) ===
{usp_text[:6500]}

=== TEXT GỐC COA (trích) ===
{coa_text[:3000]}

=== KẾT QUẢ BÓC TÁCH USP ({len(usp_criteria)} chỉ tiêu) ===
{json.dumps(usp_criteria, ensure_ascii=False, indent=2)[:4000]}

=== KẾT QUẢ BÓC TÁCH COA ({len(coa_criteria)} chỉ tiêu) ===
{json.dumps(coa_criteria, ensure_ascii=False, indent=2)[:2500]}

=== KẾT QUẢ ĐỐI CHIẾU & GỘP CHỈ TIÊU ===
{json.dumps(recon_result, ensure_ascii=False, indent=2)[:3000]}

=== KẾT QUẢ DỊCH PHƯƠNG PHÁP (SOP) ===
{json.dumps(sample_methods, ensure_ascii=False, indent=2)[:7000]}

Hãy trả về JSON chuẩn (chỉ trả về JSON, không markdown thừa) với cấu trúc sau:
{{
  "scores": {{
    "1_tach_noi_dung": {{"score": <0-10>, "reason": "<nhận xét ngắn + dẫn chứng>"}},
    "2_nhan_dien_chi_tieu": {{"score": <0-10>, "reason": "<nhận xét ngắn + dẫn chứng>"}},
    "3_chi_tieu_giong_nhau": {{"score": <0-10>, "reason": "<nhận xét ngắn + dẫn chứng>"}},
    "4_so_sanh_gioi_han": {{"score": <0-10>, "reason": "<nhận xét ngắn + dẫn chứng>"}},
    "5_dich_sat_nghia": {{"score": <0-10>, "reason": "<nhận xét ngắn + dẫn chứng thuật ngữ/con số>"}},
    "6_dich_tu_nhien": {{"score": <0-10>, "reason": "<nhận xét ngắn + dẫn chứng văn phong QC VN>"}},
    "7_dich_de_hieu": {{"score": <0-10>, "reason": "<nhận xét ngắn + dẫn chứng cấu trúc bước làm>"}},
    "8_trinh_bay_thuan_mat": {{"score": <0-10>, "reason": "<nhận xét ngắn + dẫn chứng format/ký tự>"}},
    "9_dien_template": {{"score": <0-10>, "reason": "<nhận xét ngắn khả năng ánh xạ vào bảng TCNL>"}},
    "10_phan_tich_thong_minh": {{"score": <0-10>, "reason": "<nhận xét ngắn khả năng suy luận/gắn thư viện>"}}
  }},
  "strengths": ["<điểm mạnh 1>", "<điểm mạnh 2>", "<điểm mạnh 3>"],
  "weaknesses": ["<lỗi/hạn chế cụ thể 1>", "<lỗi/hạn chế cụ thể 2>", "<lỗi/hạn chế cụ thể 3>"],
  "upgrade_recommendations": ["<gợi ý nâng cấp code/prompt 1>", "<gợi ý nâng cấp 2>", "<gợi ý nâng cấp 3>"]
}}"""

    raw = call_ai_engine(
        "Bạn là chuyên gia thẩm định quy trình kiểm nghiệm dược phẩm (USP/EP/DĐVN). Luôn chấm điểm nghiêm khắc, khách quan và chỉ ra lỗi cụ thể.",
        prompt,
        "Google API",
        JUDGE_MODEL,
        google_keys=google_keys,
        is_json=True,
        temperature=0.1,
    )
    parsed = safe_json_loads(raw)
    if not isinstance(parsed, dict) or "scores" not in parsed:
        return {"scores": {}, "strengths": [], "weaknesses": [f"Judge parse error: {str(raw)[:200]}"], "upgrade_recommendations": []}
    return parsed


def run_for_model(model_name: str, google_keys: list[str], usp_data: list, coa_data: list, usp_text: str, coa_text: str) -> dict:
    print(f"\n{'=' * 75}\n🚀 BẮT ĐẦU KIỂM TRA MODEL: {model_name}\n{'=' * 75}")
    all_files = usp_data + coa_data
    timings = {}

    t0 = time.perf_counter()
    monograph_name = tcnl_extract_monograph_name(None, "Google API", model_name, google_keys, None, files_data=usp_data)
    timings["monograph_s"] = round(time.perf_counter() - t0, 2)
    print(f"  [Node 0] Monograph: {monograph_name} ({timings['monograph_s']}s)")

    t0 = time.perf_counter()
    scan_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = {
            ex.submit(tcnl_scan_criteria_and_limits, None, "Dược điển USP", "Google API", model_name, google_keys, None, True, usp_data, monograph_name): "USP",
            ex.submit(tcnl_scan_criteria_and_limits, None, "COA Nhà sản xuất", "Google API", model_name, google_keys, None, True, coa_data, monograph_name): "COA",
        }
        for f in concurrent.futures.as_completed(futs):
            lbl = futs[f]
            try:
                scan_results[lbl] = f.result() or []
            except Exception as exc:
                print(f"  ❌ Scan {lbl} error: {exc}")
                scan_results[lbl] = []
    timings["scan_s"] = round(time.perf_counter() - t0, 2)
    usp_criteria = scan_results.get("USP", [])
    coa_criteria = scan_results.get("COA", [])
    print(f"  [Node 1] USP={len(usp_criteria)} chỉ tiêu, COA={len(coa_criteria)} chỉ tiêu ({timings['scan_s']}s)")

    t0 = time.perf_counter()
    try:
        recon_result = tcnl_ai_semantic_reconciliation(
            {"Dược điển USP": usp_criteria, "COA Nhà sản xuất": coa_criteria},
            "Google API",
            model_name,
            google_keys,
            None,
            bilingual=True,
        ) or {}
    except Exception as exc:
        print(f"  ❌ Reconcile error: {exc}")
        recon_result = {}
    timings["reconcile_s"] = round(time.perf_counter() - t0, 2)
    print(f"  [Node 2] Reconcile xong ({timings['reconcile_s']}s)")

    criteria_formatted = [
        {"ten": c.get("ten_chi_tieu", ""), "gioi_han": c.get("gioi_han", "")}
        for c in usp_criteria
        if c.get("ten_chi_tieu")
    ]
    t0 = time.perf_counter()
    try:
        methods_result = tcnl_generate_methods(
            None,
            criteria_formatted,
            "Google API",
            model_name,
            google_keys,
            None,
            bilingual=True,
            files_data=all_files,
        ) or {}
    except Exception as exc:
        print(f"  ❌ Generate methods error: {exc}")
        methods_result = {}
    timings["methods_s"] = round(time.perf_counter() - t0, 2)
    print(f"  [Node 3] Sinh phương pháp xong: {len(methods_result)} mục ({timings['methods_s']}s)")

    # HSKN metadata scan check
    t0 = time.perf_counter()
    try:
        meta_scan = node_phase_1_scan_metadata([MockFile(USP_PATH)], "Google API", model_name, google_keys, None) or {}
    except Exception as exc:
        print(f"  ⚠️ HSKN metadata scan error: {exc}")
        meta_scan = {}
    timings["hskn_meta_s"] = round(time.perf_counter() - t0, 2)

    # Export Word (.docx) via Template_Form_TCNL.docx
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    final_json = {}
    for i in range(50):
        idx = i + 1
        if i < len(usp_criteria):
            c = usp_criteria[i]
            ten = c.get("ten_chi_tieu", "")
            yc = c.get("gioi_han", "")
            pp = methods_result.get(ten, "")
            final_json[f"tcnl_ct_{idx}"] = ten
            final_json[f"tcnl_yc_{idx}"] = yc
            final_json[f"tcnl_pp_{idx}"] = pp
        else:
            final_json[f"tcnl_ct_{idx}"] = "XOA_HANG"
            final_json[f"tcnl_yc_{idx}"] = "XOA_HANG"
            final_json[f"tcnl_pp_{idx}"] = "XOA_HANG"

    final_json.update({
        "ten_thuong_mai": "Potassium Sorbate",
        "ten_nguyen_lieu": monograph_name or "Potassium Sorbate",
        "nha_san_xuat": "Test Manufacturer",
        "ma_hang": f"TEST-{model_name}",
        "tieu_chuan": "USP-NF / TCCS",
        "soan_thao": "QA Evaluation",
        "kiem_tra": "",
        "phe_duyet": "",
        "ngay_soan_thao": datetime.date.today().strftime("%d/%m/%Y"),
        "ngay_hieu_luc": "",
        "han_ra_soat": "",
        "ngay_sua": "",
        "noi_dung_sua_doi": "",
        "ly_do_sua_doi": "",
        "lan_bh": "01",
        "bao_quan": "Bảo quản trong bao bì kín, nơi khô mát, tránh ánh sáng.",
    })

    docx_filename = f"TCNL_Potassium_Sorbate_{model_name.replace('/', '_')}.docx"
    docx_path = os.path.join(OUTPUT_DIR, docx_filename)
    doc_io = node_4_generate_word(final_json, TEMPLATE_TCNL, {}, bilingual=True)
    with open(docx_path, "wb") as f:
        f.write(doc_io.getvalue())

    docx_check = inspect_docx_output(docx_path, len(usp_criteria), monograph_name)
    det_scores = deterministic_score(usp_criteria, coa_criteria, recon_result, methods_result, docx_check, meta_scan)

    print(f"  [Node 4] Đã xuất {docx_filename} (Template score={docx_check['score']}/10, leftover_tags={len(docx_check['leftover_tags'])})")
    print(f"  [Judge] Chấm điểm 10 tiêu chí bằng {JUDGE_MODEL}...")
    judge = llm_judge_model(model_name, usp_text, coa_text, usp_criteria, coa_criteria, recon_result, methods_result, google_keys)

    return {
        "model": model_name,
        "monograph_name": monograph_name,
        "timings": timings,
        "total_time_s": round(sum(timings.values()), 2),
        "usp_criteria": usp_criteria,
        "coa_criteria": coa_criteria,
        "recon_result": recon_result,
        "methods_result": methods_result,
        "docx_path": docx_path,
        "docx_check": docx_check,
        "deterministic": det_scores,
        "judge": judge,
    }


def build_reports(results: list[dict]) -> None:
    criteria_labels = [
        ("1_tach_noi_dung", "1. Khả năng tách được đúng nội dung", "c1_extract"),
        ("2_nhan_dien_chi_tieu", "2. Khả năng nhận diện chỉ tiêu", "c2_identify"),
        ("3_chi_tieu_giong_nhau", "3. Nhận diện chỉ tiêu giống nhau", "c3_similarity"),
        ("4_so_sanh_gioi_han", "4. Khả năng so sánh giới hạn", "c4_limits"),
        ("5_dich_sat_nghia", "5. Khả năng dịch thuật sát nghĩa", None),
        ("6_dich_tu_nhien", "6. Khả năng dịch thuật tự nhiên", None),
        ("7_dich_de_hieu", "7. Khả năng dịch thuật dễ hiểu", None),
        ("8_trinh_bay_thuan_mat", "8. Trình bày nội dung dễ hiểu, thuận mắt", None),
        ("9_dien_template", "9. Điền đúng nội dung vào template", "c9_template"),
        ("10_phan_tich_thong_minh", "10. Phân tích thông minh của AI", None),
    ]

    md = [
        "# Báo Cáo Đánh Giá Khả Năng Dịch Thuật & Phân Tích (10 Chỉ Tiêu)",
        "",
        f"- **Thời gian chạy:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "- **Tài liệu test:** `Test/Potassium Sorbate.pdf` (USP-NF) & `Test/COA Potassium Sorbate.pdf` (COA)",
        f"- **Mô hình so sánh:** {', '.join(r['model'] for r in results)}",
        "",
        "## 1. Bảng Điểm Tổng Hợp (Thang 10)",
        "",
    ]

    header = "| Tiêu chí đánh giá | " + " | ".join(f"{r['model']} (Auto / Judge)" for r in results) + " |"
    sep = "|---|" + "|".join("---" for _ in results) + "|"
    md.extend([header, sep])

    totals = {r["model"]: [] for r in results}
    for j_key, label, det_key in criteria_labels:
        cells = []
        for r in results:
            j_score = r["judge"].get("scores", {}).get(j_key, {}).get("score", "—")
            if det_key:
                d_score = r["deterministic"].get(det_key, "—")
                cells.append(f"**{d_score}** / {j_score}")
                if isinstance(d_score, (int, float)) and isinstance(j_score, (int, float)):
                    totals[r["model"]].append((d_score + j_score) / 2.0)
                elif isinstance(j_score, (int, float)):
                    totals[r["model"]].append(j_score)
            else:
                cells.append(f"— / **{j_score}**")
                if isinstance(j_score, (int, float)):
                    totals[r["model"]].append(j_score)
        md.append(f"| {label} | " + " | ".join(cells) + " |")

    avg_row = "| **Điểm Trung Bình Chung** | " + " | ".join(
        f"**{round(sum(totals[r['model']]) / max(1, len(totals[r['model']])), 2)} / 10**" for r in results
    ) + " |"
    time_row = "| **Tổng Thời Gian Xử Lý** | " + " | ".join(f"{r['total_time_s']}s" for r in results) + " |"
    md.extend([avg_row, time_row, ""])

    for r in results:
        md.extend([
            f"## 2. Chi Tiết Đánh Giá: `{r['model']}`",
            f"- **Tên chuyên luận nhận diện:** `{r['monograph_name']}`",
            f"- **Số chỉ tiêu bóc tách:** USP={r['deterministic']['total_usp_criteria']} | COA={r['deterministic']['total_coa_criteria']} | Hợp nhất={r['deterministic']['merged_count']}",
            f"- **File Word xuất thử:** `{os.path.basename(r['docx_path'])}` (Tag sót: `{len(r['docx_check']['leftover_tags'])}`, Hàng bảng: `{r['docx_check']['best_table_rows']}`)",
            "",
            "### Nhận xét từng tiêu chí (AI-as-a-Judge)",
        ])
        for j_key, label, _ in criteria_labels:
            item = r["judge"].get("scores", {}).get(j_key, {})
            md.append(f"- **{label}** ({item.get('score', '—')}/10): {item.get('reason', '—')}")

        md.append("\n### Điểm mạnh")
        for s in r["judge"].get("strengths", []):
            md.append(f"- {s}")

        md.append("\n### Hạn chế / Lỗi cần khắc phục")
        for w in r["judge"].get("weaknesses", []):
            md.append(f"- {w}")

        md.append("\n### Đề xuất nâng cấp ứng dụng")
        for rec in r["judge"].get("upgrade_recommendations", []):
            md.append(f"- {rec}")
        md.append("")

    md_text = "\n".join(md)
    md_path = os.path.join(OUTPUT_DIR, "BAO_CAO_DANH_GIA_DICH_THUAT.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)

    # Simple clean HTML report
    html_rows = ""
    for j_key, label, det_key in criteria_labels:
        tds = ""
        for r in results:
            j_obj = r["judge"].get("scores", {}).get(j_key, {})
            j_s = j_obj.get("score", "—")
            reason = html_lib.escape(str(j_obj.get("reason", "")))
            d_s = r["deterministic"].get(det_key, "—") if det_key else "—"
            tds += f"<td><b>Auto: {d_s} | Judge: {j_s}</b><br><small>{reason}</small></td>"
        html_rows += f"<tr><td><b>{html_lib.escape(label)}</b></td>{tds}</tr>\n"

    html_doc = f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8"><title>Báo Cáo Đánh Giá Dịch Thuật QC AI</title>
<style>
body{{font-family:Inter,Segoe UI,sans-serif;background:#f4f5f7;color:#111827;margin:32px;line-height:1.55}}
.card{{background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:24px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,.04)}}
table{{width:100%;border-collapse:collapse;background:#fff}}
th,td{{border:1px solid #e5e7eb;padding:12px;text-align:left;vertical-align:top}}
th{{background:#f8fafc;font-weight:600}}
h1,h2{{color:#0071e3}}
</style></head><body>
<div class="card"><h1>Báo Cáo Kiểm Tra 10 Chỉ Tiêu Dịch Thuật & Phân Tích</h1>
<p>Tài liệu: <b>Potassium Sorbate (USP-NF &amp; COA)</b> | Ngày chạy: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<table><tr><th>Tiêu chí</th>{"".join(f"<th>{html_lib.escape(r['model'])}</th>" for r in results)}</tr>
{html_rows}</table></div></body></html>"""
    html_path = os.path.join(OUTPUT_DIR, "BAO_CAO_DANH_GIA_DICH_THUAT.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_doc)

    json_path = os.path.join(OUTPUT_DIR, "eval_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Đã xuất báo cáo:\n  - {md_path}\n  - {html_path}\n  - {json_path}")


def main() -> None:
    keys = [k["key_string"] for k in load_api_keys().get("keys", []) if k.get("is_active") and k.get("provider") == "Google API"]
    if not keys:
        raise RuntimeError("Không tìm thấy Google API key đang hoạt động trong api_key.json")

    usp_data = prepare_file_for_ai([MockFile(USP_PATH)])
    coa_data = prepare_file_for_ai([MockFile(COA_PATH)])
    usp_text = extract_pdf_text(USP_PATH)
    coa_text = extract_pdf_text(COA_PATH)

    results = []
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for model_name in MODELS_TO_TEST:
        res = run_for_model(model_name, keys, usp_data, coa_data, usp_text, coa_text)
        results.append(res)
        partial_path = os.path.join(OUTPUT_DIR, f"partial_{model_name.replace('/', '_')}.json")
        with open(partial_path, "w", encoding="utf-8") as pf:
            json.dump(res, pf, ensure_ascii=False, indent=2)

    build_reports(results)


if __name__ == "__main__":
    main()
