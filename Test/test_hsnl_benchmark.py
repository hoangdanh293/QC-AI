# -*- coding: utf-8 -*-
import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf_8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
"""
=============================================================================
BENCHMARK: Kiểm tra Tốc Độ & Độ Chính Xác — Chức năng Tạo Hồ Sơ Nguyên Liệu
=============================================================================
Model: gemma-4-31b-it (Google API)
Tài liệu test: Test/Folic acid hydrate - EP.pdf  (Dược điển EP)
               Test/COA Folic acid.pdf            (COA)
=============================================================================
Chạy từ thư mục gốc: python test/test_hsnl_benchmark.py
"""

import os
import sys
import time
import json
import io

# Đảm bảo import đúng module từ thư mục gốc
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# ── Ground Truth: Các chỉ tiêu biết trước của Folic Acid (Hydrate) EP ────────
GROUND_TRUTH = {
    # key: (tên hiển thị chuẩn, giới hạn số cần có, từ khóa bắt buộc trong SOP)
    "cam_quan": (
        "Tính chất / Cảm quan",
        "",
        ["yellow", "orange", "vàng", "cam", "powder", "bột", "tinh thể"]
    ),
    "do_tan": (
        "Độ tan",
        "",
        ["water", "nước", "soluble", "insoluble", "alkali", "kiềm"]
    ),
    "dinh_tinh": (
        "Định tính",
        "",
        ["identification", "định tính", "infrared", "optical", "TLC", "folic"]
    ),
    "ham_luong_nuoc": (
        "Hàm lượng nước / Water",
        "5.0",
        ["karl fischer", "5.0", "8.5", "water", "nuoc"]
    ),
    "tap_chat_lien_quan": (
        "Tạp chất liên quan / Related substances",
        "0.5",
        ["HPLC", "related", "impurity", "0.5", "liquid chromatography"]
    ),
    "dinh_luong": (
        "Định lượng / Assay",
        "96.0",
        ["assay", "định lượng", "96.0", "102.0", "hplc", "anhydrous"]
    ),
    "tro_sulfat": (
        "Tro sulfat / Sulfated ash",
        "0.2",
        ["sulfated", "ash", "0.2", "nung", "ignite"]
    ),
    "acid_d_folic": (
        "Acid D-folic",
        "0.3",
        ["d-folic", "0.3", "chiral", "optical", "folic"]
    ),
}

# Chỉ tiêu mapping sang criteria_master (các ID thực tế)
CRITERIA_FOR_TEST = {
    "cam_quan": "Bóc tách tính chất cảm quan, mô tả ngoại quan của nguyên liệu từ tài liệu đính kèm.",
    "do_tan": "Bóc tách thông tin về độ tan của nguyên liệu trong các dung môi khác nhau.",
    "dinh_tinh": "Bóc tách toàn bộ phản ứng định tính (A, B, C, D), bao gồm thuốc thử, cách làm và kết quả dự kiến.",
    "ham_luong_nuoc": "Bóc tách yêu cầu hàm lượng nước (Water content), phương pháp Karl Fischer, giới hạn 5.0%-8.5%.",
    "tap_chat_lien_quan": "Bóc tách phương pháp và giới hạn tạp chất liên quan (Related substances) bằng HPLC.",
    "dinh_luong": "Bóc tách phương pháp định lượng (Assay) bằng HPLC, gồm cách cân, pha dung dịch, điều kiện sắc ký và công thức tính toán.",
    "tro_sulfat": "Bóc tách giới hạn và phương pháp xác định tro sulfat (tối đa 0.2%).",
    "acid_d_folic": "Bóc tách giới hạn và phương pháp xác định acid D-folic (không quá 0.3%).",
}

# ── Helper: Wrapper file để truyền vào prepare_file_for_ai ───────────────────
class MockFile:
    """Giả lập Streamlit UploadedFile để dùng với prepare_file_for_ai()"""
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        with open(path, "rb") as f:
            self._data = f.read()
        self._pos = 0

    def seek(self, pos):
        self._pos = pos

    def read(self):
        return self._data

    def tell(self):
        return self._pos


# ── Scoring Functions ─────────────────────────────────────────────────────────
def score_result(result: dict) -> dict:
    """
    Đánh giá độ chính xác kết quả so với ground truth.
    Trả về dict chứa điểm từng chỉ tiêu và tổng điểm.
    Thang điểm mỗi chỉ tiêu: 20 điểm tối đa
      - 8 điểm: chỉ tiêu được tìm thấy (không phải XOA_HANG)
      - 6 điểm: trường yeu_cau/gioi_han không rỗng
      - 6 điểm: sop_text có nội dung chi tiết (>80 ký tự) và chứa ít nhất 1 từ khóa
    """
    scores = {}
    total = 0
    max_total = len(GROUND_TRUTH) * 20

    for crit_id, (display_name, expected_limit, keywords) in GROUND_TRUTH.items():
        score = 0
        details = []

        entry = result.get(crit_id, {})
        if not entry or not isinstance(entry, dict):
            scores[crit_id] = {
                "name": display_name,
                "score": 0,
                "max": 20,
                "details": ["❌ Không tìm thấy chỉ tiêu trong kết quả"]
            }
            continue

        # Lấy giá trị từ entry
        chot = entry.get("chot", "")
        yeu_cau = entry.get("yeu_cau", "")
        gioi_han = entry.get("gioi_han", "")
        duoc_dien = entry.get("duoc_dien", "") or entry.get("sop_text", "")
        tieu_chuan = entry.get("tieu_chuan", "")
        coa_text = entry.get("coa", "")

        # Gom sop text từ nhiều nguồn
        all_sop = " ".join(filter(None, [chot, duoc_dien, tieu_chuan, coa_text, yeu_cau]))
        all_sop_lower = all_sop.lower()

        # Điểm 1: Chỉ tiêu được tìm thấy (không phải XOA_HANG)
        main_text = chot or duoc_dien or tieu_chuan or coa_text
        if main_text and "XOA_HANG" not in str(main_text).upper() and "XOA_DONG" not in str(main_text).upper():
            score += 8
            details.append("✅ Chỉ tiêu được tìm thấy (+8)")
        else:
            details.append(f"❌ Chỉ tiêu rỗng hoặc bị XOA (chot={chot[:50] if chot else 'N/A'})")

        # Điểm 2: yeu_cau / gioi_han không rỗng
        has_limit = bool((yeu_cau and len(yeu_cau.strip()) > 3) or (gioi_han and len(gioi_han.strip()) > 0))
        if has_limit:
            score += 6
            details.append(f"✅ Có yêu cầu/giới hạn: yeu_cau={yeu_cau[:60]!r} (+6)")
        else:
            details.append("❌ Thiếu yêu cầu/giới hạn")

        # Điểm 3: SOP chi tiết và chứa từ khóa chuyên môn
        has_detail = len(all_sop) > 80
        keyword_hits = [kw for kw in keywords if kw.lower() in all_sop_lower]
        if has_detail and keyword_hits:
            score += 6
            details.append(f"✅ SOP chi tiết ({len(all_sop)} ký tự), từ khóa: {keyword_hits[:3]} (+6)")
        elif has_detail:
            score += 3
            details.append(f"⚠️ SOP có nội dung ({len(all_sop)} ký tự) nhưng thiếu từ khóa (+3)")
        else:
            details.append(f"❌ SOP quá ngắn ({len(all_sop)} ký tự)")

        scores[crit_id] = {
            "name": display_name,
            "score": score,
            "max": 20,
            "details": details,
            "chot_preview": str(main_text)[:200] if main_text else "",
        }
        total += score

    return {
        "per_criteria": scores,
        "total_score": total,
        "max_score": max_total,
        "accuracy_pct": round(total / max_total * 100, 1) if max_total > 0 else 0,
    }


def print_separator(char="=", width=70):
    print(char * width)


def print_score_report(scoring: dict, label: str = ""):
    print_separator()
    print(f"📊 BÁO CÁO ĐỘ CHÍNH XÁC{' — ' + label if label else ''}")
    print_separator()

    per = scoring["per_criteria"]
    for crit_id, info in per.items():
        pct = round(info["score"] / info["max"] * 100)
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        print(f"\n  [{bar}] {pct:3d}%  {info['name']}  ({info['score']}/{info['max']})")
        for d in info["details"]:
            print(f"         {d}")
        if info.get("chot_preview"):
            preview = info["chot_preview"].replace("\n", " ")[:120]
            print(f"         📄 Preview: {preview}...")

    print_separator("-")
    total = scoring["total_score"]
    mx = scoring["max_score"]
    acc = scoring["accuracy_pct"]
    emoji = "🏆" if acc >= 80 else "✅" if acc >= 60 else "⚠️" if acc >= 40 else "❌"
    print(f"\n  {emoji} TỔNG ĐIỂM: {total}/{mx} = {acc}%")
    print_separator()


# ── Main Benchmark ────────────────────────────────────────────────────────────
def run_benchmark(label: str = "BASELINE"):
    print_separator("═")
    print(f"🚀 BENCHMARK: {label}")
    print(f"   Model: gemma-4-31b-it | Provider: Google API")
    print(f"   Test files: Folic acid hydrate EP + COA Folic acid")
    print_separator("═")

    PROVIDER = "Google API"
    MODEL = "gemma-4-31b-it"

    # Load API keys
    from core.key_manager import get_active_keys
    keys = get_active_keys(PROVIDER, MODEL)
    if not keys:
        print("❌ Không tìm thấy API key cho gemma-4-31b-it. Thử lấy key từ provider...")
        from core.key_manager import load_api_keys
        key_data = load_api_keys()
        keys = [
            item["key_string"]
            for item in key_data.get("keys", [])
            if item.get("provider") == PROVIDER
            and item.get("is_active") is True
            and item.get("key_string", "")
            and item.get("key_string", "") != "[GIẢI MÃ THẤT BẠI]"
        ]
        if not keys:
            print("❌ KHÔNG CÓ API KEY NÀO! Vui lòng cấu hình API key trong ứng dụng trước.")
            return None

    print(f"   ✅ Tìm thấy {len(keys)} API key(s)\n")

    # Load test files
    test_dir = os.path.join(ROOT, "Test")
    bp_path  = os.path.join(test_dir, "Folic acid hydrate - EP.pdf")
    coa_path = os.path.join(test_dir, "COA Folic acid.pdf")

    for p in [bp_path, coa_path]:
        if not os.path.exists(p):
            print(f"❌ File không tồn tại: {p}")
            return None

    mock_bp  = MockFile(bp_path)   # EP pharmacopoeia
    mock_coa = MockFile(coa_path)  # COA

    print(f"   📁 EP file:  {os.path.getsize(bp_path)/1024:.1f} KB")
    print(f"   📁 COA file: {os.path.getsize(coa_path)/1024:.1f} KB\n")

    # ── PHASE 1: Scan Metadata ─────────────────────────────────────────────
    print_separator("─")
    print("📡 PHASE 1: node_phase_1_scan_metadata()")
    print_separator("─")

    from core.doc_processor import node_phase_1_scan_metadata, prepare_file_for_ai, node_phase_2_deep_extract_v2

    t0 = time.perf_counter()
    meta_result = node_phase_1_scan_metadata([mock_bp, mock_coa], PROVIDER, MODEL, keys, None)
    t1 = time.perf_counter()
    phase1_time = t1 - t0

    print(f"⏱️  Thời gian Phase 1: {phase1_time:.2f} giây")
    print(f"📋 Kết quả metadata:")
    print(f"   Tên chuyên luận: {meta_result.get('Ten_chuyen_luan', 'N/A')}")
    print(f"   Nguồn tài liệu:  {meta_result.get('Nguon_tai_lieu', 'N/A')}")
    found_criteria = meta_result.get("Danh_sach_TEN_cac_chi_tieu", [])
    print(f"   Số chỉ tiêu phát hiện: {len(found_criteria)}")
    for c in found_criteria[:15]:
        print(f"     • {c}")
    if len(found_criteria) > 15:
        print(f"     ... và {len(found_criteria)-15} chỉ tiêu nữa")
    print()

    # ── PHASE 2: Deep Extraction v2 (song song theo nguồn) ────────────────
    print_separator("─")
    print("🔬 PHASE 2: node_phase_2_deep_extract_v2() — Song song theo nguồn")
    print(f"   Số chỉ tiêu test: {len(CRITERIA_FOR_TEST)}")
    print_separator("─")

    # Chuẩn bị file data (encode base64) — giống cách UI làm
    mock_bp.seek(0)
    mock_coa.seek(0)

    files_data_ep  = prepare_file_for_ai([mock_bp])
    files_data_coa = prepare_file_for_ai([mock_coa])

    # Mapping nguồn → files_data (giống files_by_source trong UI)
    files_by_source = {
        "Dược điển": files_data_ep,
        "COA": files_data_coa,
    }

    # Tải dictionary_rules từ criteria_master
    from core.doc_processor import get_dynamic_method_instructions
    _, criteria_master, _ = get_dynamic_method_instructions()
    dictionary_rules = "\n".join([
        f"    - {v['tu_dien_dich']}"
        for k, v in criteria_master.items()
        if v.get("tu_dien_dich", "").strip()
    ])

    t2 = time.perf_counter()
    raw_result = node_phase_2_deep_extract_v2(
        source_files_dict=files_by_source,
        extra_files_data=[],
        criteria_config=CRITERIA_FOR_TEST,
        dictionary_rules=dictionary_rules,
        provider=PROVIDER,
        model=MODEL,
        google_keys=keys,
        openai_keys=None,
        bilingual=True,
        chunk_size=0,     # 0 = auto: Gemma→3, khác→5
        max_workers=None  # Auto
    )
    t3 = time.perf_counter()
    phase2_time = t3 - t2
    total_time = t3 - t0

    print(f"⏱️  Thời gian Phase 2: {phase2_time:.2f} giây")
    print(f"⏱️  Tổng thời gian:    {total_time:.2f} giây\n")

    # ── Đánh giá độ chính xác ─────────────────────────────────────────────
    scoring = score_result(raw_result)
    print_score_report(scoring, label)

    # ── Lưu kết quả raw ───────────────────────────────────────────────────
    result_path = os.path.join(ROOT, "test", f"result_{label.lower().replace(' ', '_')}.json")
    try:
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump({
                "label": label,
                "model": MODEL,
                "phase1_time_sec": round(phase1_time, 2),
                "phase2_time_sec": round(phase2_time, 2),
                "total_time_sec": round(total_time, 2),
                "accuracy_pct": scoring["accuracy_pct"],
                "total_score": scoring["total_score"],
                "max_score": scoring["max_score"],
                "meta_result": meta_result,
                "raw_result": raw_result,
                "scoring": scoring,
            }, f, ensure_ascii=False, indent=2)
        print(f"💾 Đã lưu kết quả chi tiết: {result_path}")
    except Exception as e:
        print(f"⚠️ Không lưu được file kết quả: {e}")

    return {
        "label": label,
        "phase1_time": phase1_time,
        "phase2_time": phase2_time,
        "total_time": total_time,
        "accuracy_pct": scoring["accuracy_pct"],
        "total_score": scoring["total_score"],
        "max_score": scoring["max_score"],
        "scoring": scoring,
        "raw_result": raw_result,
    }


def compare_results(baseline: dict, improved: dict):
    """So sánh baseline vs improved và in ra bảng so sánh"""
    print_separator("═")
    print("📊 SO SÁNH TRƯỚC/SAU CẢI THIỆN")
    print_separator("═")

    def delta_arrow(before, after, higher_is_better=True):
        diff = after - before
        if abs(diff) < 0.01:
            return "→ Không đổi"
        up = diff > 0
        emoji = ("⬆️" if up else "⬇️") if higher_is_better else ("⬇️" if up else "⬆️")
        return f"{emoji} {'+' if diff > 0 else ''}{diff:.2f}"

    print(f"\n  {'Tiêu chí':<35} {'Baseline':>12} {'Improved':>12} {'Thay đổi':>20}")
    print(f"  {'-'*35} {'-'*12} {'-'*12} {'-'*20}")

    b_t1 = baseline.get("phase1_time_sec", baseline.get("phase1_time", 0))
    i_t1 = improved.get("phase1_time_sec", improved.get("phase1_time", 0))
    print(f"  {'Phase 1 (giay)':<35} {b_t1:>12.2f} {i_t1:>12.2f} {delta_arrow(b_t1, i_t1, False):>20}")

    b_t2 = baseline.get("phase2_time_sec", baseline.get("phase2_time", 0))
    i_t2 = improved.get("phase2_time_sec", improved.get("phase2_time", 0))
    print(f"  {'Phase 2 (giay)':<35} {b_t2:>12.2f} {i_t2:>12.2f} {delta_arrow(b_t2, i_t2, False):>20}")

    b_tt = baseline.get("total_time_sec", baseline.get("total_time", 0))
    i_tt = improved.get("total_time_sec", improved.get("total_time", 0))
    pct_speedup = round((b_tt - i_tt) / b_tt * 100, 1) if b_tt > 0 else 0
    print(f"  {'Tong thoi gian (giay)':<35} {b_tt:>12.2f} {i_tt:>12.2f} {delta_arrow(b_tt, i_tt, False):>20}")

    b_acc = baseline.get("accuracy_pct", 0)
    i_acc = improved.get("accuracy_pct", 0)
    print(f"  {'🎯 Độ chính xác (%)':<35} {b_acc:>12.1f} {i_acc:>12.1f} {delta_arrow(b_acc, i_acc, True):>20}")

    b_sc = baseline.get("total_score", 0)
    i_sc = improved.get("total_score", 0)
    b_mx = baseline.get("max_score", 0)
    print(f"  {'🎯 Điểm tổng':<35} {b_sc}/{b_mx}{'':>4} {i_sc}/{b_mx}{'':>4} {delta_arrow(b_sc, i_sc, True):>20}")

    print(f"\n  🚀 Tăng tốc tổng: {pct_speedup:+.1f}%")
    acc_delta = i_acc - b_acc
    print(f"  🎯 Tăng chính xác: {acc_delta:+.1f} điểm %")

    print_separator("═")


# ── Entry Point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Benchmark HSNL profile generation")
    parser.add_argument("--mode", choices=["baseline", "improved", "compare"], default="baseline",
                        help="baseline=đo lần đầu, improved=đo sau cải thiện, compare=so sánh 2 file")
    args = parser.parse_args()

    if args.mode == "baseline":
        run_benchmark("BASELINE")
    elif args.mode == "improved":
        run_benchmark("IMPROVED")
    elif args.mode == "compare":
        b_path = os.path.join(ROOT, "test", "result_baseline.json")
        i_path = os.path.join(ROOT, "test", "result_improved.json")
        if not os.path.exists(b_path) or not os.path.exists(i_path):
            print(f"❌ Cần chạy --mode baseline và --mode improved trước!")
        else:
            with open(b_path, encoding="utf-8") as f:
                baseline = json.load(f)
            with open(i_path, encoding="utf-8") as f:
                improved = json.load(f)
            compare_results(baseline, improved)
