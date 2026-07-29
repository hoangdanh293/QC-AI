# -*- coding: utf-8 -*-
import sys, io
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf_8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
"""
=============================================================================
BENCHMARK: Toc Do & Do Chinh Xac --- Tao Tieu Chuan Nguyen Lieu (TCNL)
=============================================================================
Model: gemma-4-31b-it (Google API)
File test: Test/Folic acid hydrate - EP.pdf  (Duoc dien EP)
           Test/COA Folic acid.pdf           (COA)
=============================================================================
Chay tu thu muc goc: python test/test_tcnl_benchmark.py
"""

import os, sys, time, json, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

PROVIDER = "Google API"
MODEL    = "gemma-4-31b-it"

# ── Ground truth: Folic Acid (Hydrate) EP ────────────────────────────────────
# Cac chi tieu chinh trong chuyen luan Folic Acid EP
# Format: (ten_hien_thi, tu_khoa_gioi_han, tu_khoa_sop, tu_khoa_cam)
GROUND_TRUTH_CRITERIA = {
    "tinh_chat": (
        "Tinh chat / Appearance",
        ["yellow", "orange", "vang", "cam", "powder", "bot", "tinh the"],
        [],
        []
    ),
    "dinh_tinh_nhom": (
        "Dinh tinh nhom / Identification group",
        ["first", "second", "nhom i", "nhom ii", "a", "b", "c", "d"],
        [],
        []
    ),
    "dinh_tinh_A": (
        "Dinh tinh A / Identification A",
        ["quay cuc", "optical rotation", "+18", "+22", "anhydrous"],
        [],
        []
    ),
    "dinh_tinh_B": (
        "Dinh tinh B / Identification B",
        ["infrared", "hong ngoai", "ir", "folic acid crs", "pho"],
        ["infrared", "absorption", "hong ngoai"],
        []
    ),
    "dinh_tinh_C": (
        "Dinh tinh C / Identification C",
        ["thin layer", "chromatography", "tlc", "sac ky lop mong", "vet chinh", "principal spot"],
        ["thin layer", "tlc", "sac ky", "silica", "ammonia"],
        []
    ),
    "dinh_tinh_D": (
        "Dinh tinh D / Identification D",
        ["water", "nuoc", "see tests", "xem phep thu"],
        ["water", "nuoc", "tests", "xem"],
        []
    ),
    "do_tan": (
        "Do tan / Solubility",
        ["soluble", "tan", "water", "nuoc", "acid", "kiem"],
        [],
        []
    ),
    "ham_luong_nuoc": (
        "Ham luong nuoc / Water",
        ["5.0", "8.5", "5,0", "8,5", "water", "nuoc", "per cent"],
        ["karl fischer", "2.5.12", "nuoc", "water"],
        []
    ),
    "tap_chat_lien_quan": (
        "Tap chat lien quan / Related substances",
        ["0.5", "0,5", "impurity", "tap chat", "0.4", "1.2"],
        ["related", "hplc", "sac ky", "impurit"],
        []
    ),
    "dinh_luong": (
        "Dinh luong / Assay",
        ["96.0", "96,0", "102.0", "102,0", "percent", "phan tram", "anhydrous", "khan"],
        ["assay", "dinh luong", "hplc", "sac ky", "liquid chromatography"],
        []
    ),
    "tro_sulfat": (
        "Tro sulfat / Sulfated ash",
        ["0.2", "0,2", "sulfated", "tro", "ash"],
        ["ignite", "nung", "sulfated", "sulfuric"],
        []
    ),
    "acid_d_folic": (
        "Acid D-folic / D-folic acid",
        ["0.3", "0,3"],
        ["theo", "chuyen luan", "nha san xuat", "standard", "manufacturer"],
        ["detector", "column", "flow rate", "stationary phase", "chiral", "buong tiem", "the tich tiem", "toc do dong", "pha dong"]
    ),
    "acetone": (
        "Acetone",
        ["1000", "ppm"],
        ["theo", "chuyen luan", "nha san xuat", "standard", "manufacturer"],
        ["headspace", "detector", "injector", "carrier gas", "fid", "khi mang", "buong tiem", "nhiet do buong", "khi sac"]
    ),
}

# ── Helper classes ────────────────────────────────────────────────────────────
class MockFile:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        with open(path, "rb") as f:
            self._data = f.read()
    def seek(self, pos): pass
    def read(self): return self._data
    def tell(self): return 0

def sep(char="=", w=70): print(char * w)

# ── Scoring ───────────────────────────────────────────────────────────────────
def score_scan(scanned_list: list) -> dict:
    """
    Danh gia ket qua tcnl_scan_criteria_and_limits.
    Moi chi tieu Ground Truth: 20 diem toi da
      - 10 diem: ten chi tieu duoc phat hien (fuzzy match)
      - 5 diem : gioi_han khong rong
      - 5 diem : gioi_han chua it nhat 1 tu khoa dung
    """
    # Build lookup tu ket qua scan (lowercase, bo dau)
    def norm(s):
        if not s: return ""
        s = str(s).lower()
        char_map = {
            'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
            'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
            'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
            'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
            'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
            'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
            'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
            'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
            'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
            'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
            'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
            'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
            'đ': 'd'
        }
        res = []
        for c in s:
            res.append(char_map.get(c, c))
        s = "".join(res)
        s = re.sub(r'[^a-z0-9 ]', ' ', s)
        return re.sub(r'\s+', ' ', s).strip()

    scanned_norms = [(norm(x.get("ten_chi_tieu","")), x.get("gioi_han","")) for x in scanned_list]

    scores = {}
    total = 0
    max_total = len(GROUND_TRUTH_CRITERIA) * 20

    for crit_id, gt_tuple in GROUND_TRUTH_CRITERIA.items():
        display_name = gt_tuple[0]
        limit_kws = gt_tuple[1]
        sop_kws = gt_tuple[2]
        score = 0
        details = []
        matched_gl = ""

        norm_display = norm(display_name)
        # Tim phan khop tot nhat trong ket qua scan
        best_match_gl = ""
        best_match_score = 0
        for scanned_norm, scanned_gl in scanned_norms:
            # Tránh khớp nhầm chéo giữa định tính A, B, C, D và Định tính nhóm
            is_id_scanned = "dinh tinh" in scanned_norm or "identification" in scanned_norm
            is_id_gt = "dinh tinh" in norm_display or "identification" in norm_display
            if is_id_scanned and is_id_gt:
                words_scanned = set(scanned_norm.split())
                words_gt = set(norm_display.split())
                suffixes = {"a", "b", "c", "d", "nhom", "group"}
                s_scanned = words_scanned & suffixes
                s_gt = words_gt & suffixes
                if s_scanned != s_gt:
                    continue

            # Kiem tra xem co cung goc tu khoa khong
            # Voi tu dai: dung substring match (linh hoat)
            # Voi tu ngan (1-3 ky tu nhu 'A', 'B', 'C'): dung whole-word match de tranh false-positive
            def _kw_match(kw, text):
                if len(kw) > 3:
                    return kw in text
                else:  # Whole-word match cho chu cai phan loai (A, B, C, D)
                    import re as _re
                    return bool(_re.search(r'(?<![a-z0-9])' + _re.escape(kw) + r'(?![a-z0-9])', text))
            kw_hits = sum(1 for kw in norm_display.split() if len(kw) >= 1 and _kw_match(kw, scanned_norm))
            if kw_hits >= 1:
                if kw_hits > best_match_score:
                    best_match_score = kw_hits
                    best_match_gl = scanned_gl

        # Diem 1: Phat hien ten chi tieu
        if best_match_score >= 1:
            score += 10
            details.append(f"[OK] Chi tieu duoc phat hien (match={best_match_score} tu khoa) (+10)")
            matched_gl = best_match_gl
        else:
            details.append(f"[FAIL] Chi tieu KHONG duoc phat hien trong ket qua scan")

        # Diem 2: gioi_han khong rong
        if matched_gl and len(matched_gl.strip()) > 3:
            score += 5
            details.append(f"[OK] Gioi han khong rong: {matched_gl[:80]!r} (+5)")
        else:
            details.append(f"[FAIL] Gioi han rong hoac qua ngan")

        # Diem 3: gioi_han chua tu khoa dung
        gl_norm = norm(matched_gl)
        kw_hits = [kw for kw in limit_kws if norm(kw) in gl_norm]
        if kw_hits:
            score += 5
            details.append(f"[OK] Gioi han chua tu khoa: {kw_hits[:3]} (+5)")
        elif not limit_kws:
            score += 5
            details.append(f"[OK] Khong co tu khoa kiem tra (+5)")
        else:
            details.append(f"[FAIL] Thieu tu khoa trong gioi han: {limit_kws[:3]}")

        scores[crit_id] = {
            "name": display_name,
            "score": score, "max": 20,
            "details": details,
            "matched_gl": matched_gl[:200] if matched_gl else "",
        }
        total += score

    return {
        "per_criteria": scores,
        "total_score": total,
        "max_score": max_total,
        "accuracy_pct": round(total / max_total * 100, 1) if max_total else 0,
    }


def score_methods(methods_dict: dict, scanned_list: list) -> dict:
    """
    Danh gia ket qua tcnl_generate_methods.
    Moi chi tieu: 20 diem toi da
      - 8 diem : co phuong phap (value khong rong, > 50 ky tu)
      - 6 diem : chua tu khoa SOP
      - 6 diem : chi tieu duoc nhan dien dung ten (key match voi ten scan)
    """
    def norm(s):
        if not s: return ""
        s = str(s).lower()
        char_map = {
            'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
            'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
            'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
            'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
            'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
            'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
            'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
            'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
            'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
            'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
            'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
            'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
            'đ': 'd'
        }
        res = []
        for c in s:
            res.append(char_map.get(c, c))
        s = "".join(res)
        s = re.sub(r'[^a-z0-9 ]', ' ', s)
        return re.sub(r'\s+', ' ', s).strip()

    methods_lower = {norm(k): v for k, v in methods_dict.items()}

    scores = {}
    total = 0
    max_total = len(GROUND_TRUTH_CRITERIA) * 20

    for crit_id, gt_tuple in GROUND_TRUTH_CRITERIA.items():
        display_name = gt_tuple[0]
        limit_kws = gt_tuple[1]
        sop_kws = gt_tuple[2]
        forbidden_kws = gt_tuple[3] if len(gt_tuple) >= 4 else []
        score = 0
        details = []
        norm_display = norm(display_name)
        # Tim phuong phap khop
        best_val = ""
        best_score = 0
        for mk, mv in methods_lower.items():
            # Tránh khớp nhầm chéo giữa định tính A, B, C, D và Định tính nhóm
            is_id_scanned = "dinh tinh" in mk or "identification" in mk
            is_id_gt = "dinh tinh" in norm_display or "identification" in norm_display
            if is_id_scanned and is_id_gt:
                words_scanned = set(mk.split())
                words_gt = set(norm_display.split())
                suffixes = {"a", "b", "c", "d", "nhom", "group"}
                s_scanned = words_scanned & suffixes
                s_gt = words_gt & suffixes
                if s_scanned != s_gt:
                    continue

            def _kw_match_m(kw, text):
                if len(kw) > 3:
                    return kw in text
                else:
                    import re as _re
                    return bool(_re.search(r'(?<![a-z0-9])' + _re.escape(kw) + r'(?![a-z0-9])', text))
            kw_hits = sum(1 for kw in norm_display.split() if len(kw) >= 1 and _kw_match_m(kw, mk))
            if kw_hits > best_score:
                best_score = kw_hits
                best_val = mv or ""

        # Diem 1: Co phuong phap
        if best_val and len(str(best_val).strip()) > 50:
            score += 8
            details.append(f"[OK] Co phuong phap ({len(best_val)} ky tu) (+8)")
        else:
            details.append(f"[FAIL] Khong co / qua ngan ({len(str(best_val))} ky tu)")

        # Kiem tra xem co chua tu khoa bi cam khong (Chong bia dat thong tin)
        val_norm = norm(best_val)
        forbidden_hits = [kw for kw in forbidden_kws if norm(kw) in val_norm]
        
        # Diem 2: Chua tu khoa SOP
        if sop_kws:
            sop_hits = [kw for kw in sop_kws if norm(kw) in val_norm]
            if sop_hits:
                score += 6
                details.append(f"[OK] Chua tu khoa SOP: {sop_hits[:3]} (+6)")
            else:
                details.append(f"[FAIL] Thieu tu khoa SOP: {sop_kws[:3]}")
        else:
            score += 6
            details.append(f"[OK] Khong co tu khoa SOP kiem tra (+6)")

        # Diem 3: Key match dung
        if best_score >= 1:
            score += 6
            details.append(f"[OK] Ten chi tieu nhan dien dung (match={best_score}) (+6)")
        else:
            details.append(f"[FAIL] Ten chi tieu KHONG khop trong methods dict")

        if forbidden_hits:
            score = max(0, score - 15)
            details.append(f"[FAIL] BIA DAT THONG TIN (Chua tu khoa cam: {forbidden_hits[:4]}) (-15)")

        scores[crit_id] = {
            "name": display_name,
            "score": score, "max": 20,
            "details": details,
            "method_preview": str(best_val)[:200] if best_val else "",
        }
        total += score

    return {
        "per_criteria": scores,
        "total_score": total,
        "max_score": max_total,
        "accuracy_pct": round(total / max_total * 100, 1) if max_total else 0,
    }


def print_score_report(scoring: dict, title: str):
    sep()
    print(f"[BCRITING] {title}")
    sep()
    for crit_id, info in scoring["per_criteria"].items():
        pct = round(info["score"] / info["max"] * 100)
        bar = "#" * (pct // 10) + "." * (10 - pct // 10)
        print(f"\n  [{bar}] {pct:3d}%  {info['name']}  ({info['score']}/{info['max']})")
        for d in info["details"]:
            print(f"         {d}")
        if info.get("matched_gl"):
            print(f"         Gioi han: {info['matched_gl'][:100]}...")
        if info.get("method_preview"):
            print(f"         SOP preview: {info['method_preview'][:120].replace(chr(10),' ')}...")
    sep("-")
    acc = scoring["accuracy_pct"]
    emoji = "EXCELLENT" if acc >= 85 else ("GOOD" if acc >= 70 else ("FAIR" if acc >= 50 else "POOR"))
    print(f"\n  [{emoji}] TONG DIEM: {scoring['total_score']}/{scoring['max_score']} = {acc}%")
    sep()


# ── Main Benchmark ────────────────────────────────────────────────────────────
def run_tcnl_benchmark(label: str = "BASELINE"):
    sep("=")
    print(f"[BENCHMARK] {label}")
    print(f"   Model: {MODEL} | Provider: {PROVIDER}")
    print(f"   Test: Folic Acid (EP + COA)")
    sep("=")

    from core.key_manager import get_active_keys
    keys = get_active_keys(PROVIDER, MODEL)
    if not keys:
        from core.key_manager import load_api_keys
        kd = load_api_keys()
        keys = [i["key_string"] for i in kd.get("keys", [])
                if i.get("provider") == PROVIDER and i.get("is_active") and
                i.get("key_string","") not in ("", "[GIAI MA THAT BAI]")]
    if not keys:
        print("KHONG CO API KEY!")
        return None

    print(f"   Tim thay {len(keys)} API key(s)\n")

    test_dir = os.path.join(ROOT, "Test")
    ep_path  = os.path.join(test_dir, "Folic acid hydrate - EP.pdf")
    coa_path = os.path.join(test_dir, "COA Folic acid.pdf")
    for p in [ep_path, coa_path]:
        if not os.path.exists(p):
            print(f"KHONG TIM THAY: {p}")
            return None

    mock_ep  = MockFile(ep_path)
    mock_coa = MockFile(coa_path)
    print(f"   EP  file: {os.path.getsize(ep_path)/1024:.1f} KB")
    print(f"   COA file: {os.path.getsize(coa_path)/1024:.1f} KB\n")

    from core.doc_processor import (
        prepare_file_for_ai,
        tcnl_scan_criteria_and_limits,
        tcnl_generate_methods,
        tcnl_extract_monograph_name,
    )

    # Encode files mot lan
    t_enc0 = time.perf_counter()
    files_data_ep  = prepare_file_for_ai([mock_ep])
    files_data_coa = prepare_file_for_ai([mock_coa])
    all_files_data = files_data_ep + files_data_coa
    t_enc1 = time.perf_counter()
    print(f"   [Encode] {t_enc1-t_enc0:.2f}s\n")

    # ── Node 0: Trich ten chuyen luan ────────────────────────────────────────
    sep("-")
    print("[Node 0] tcnl_extract_monograph_name()")
    sep("-")
    t0 = time.perf_counter()
    monograph = tcnl_extract_monograph_name(None, PROVIDER, MODEL, keys, None, files_data=files_data_ep)
    t1 = time.perf_counter()
    node0_time = t1 - t0
    print(f"   Ten chuyen luan: {monograph!r}")
    print(f"   Thoi gian: {node0_time:.2f}s\n")

    # ── Node 1: Scan criteria (song song EP + COA) ────────────────────────────
    sep("-")
    print("[Node 1] tcnl_scan_criteria_and_limits() x 2 nguon (song song)")
    sep("-")
    import concurrent.futures
    t2 = time.perf_counter()
    scan_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fut_map = {
            ex.submit(tcnl_scan_criteria_and_limits, None, "Duoc dien EP", PROVIDER, MODEL,
                      keys, None, True, files_data_ep, monograph_name=monograph): "Duoc dien EP",
            ex.submit(tcnl_scan_criteria_and_limits, None, "COA", PROVIDER, MODEL,
                      keys, None, True, files_data_coa, monograph_name=monograph): "COA",
        }
        for fut in concurrent.futures.as_completed(fut_map):
            lbl = fut_map[fut]
            try:
                scan_results[lbl] = fut.result()
            except Exception as e:
                print(f"   LOI scan '{lbl}': {e}")
                scan_results[lbl] = []
    t3 = time.perf_counter()
    node1_time = t3 - t2

    ep_list  = scan_results.get("Duoc dien EP", [])
    coa_list = scan_results.get("COA", [])
    print(f"   EP scan:  {len(ep_list)} chi tieu")
    for x in ep_list[:12]: print(f"     - {x.get('ten_chi_tieu','')}: {x.get('gioi_han','')[:60]}")
    if len(ep_list) > 12: print(f"     ... va {len(ep_list)-12} chi tieu nua")
    print(f"\n   COA scan: {len(coa_list)} chi tieu")
    for x in coa_list[:6]: print(f"     - {x.get('ten_chi_tieu','')}: {x.get('gioi_han','')[:60]}")
    print(f"\n   Thoi gian Node 1: {node1_time:.2f}s\n")

    # Danh gia do chinh xac Node 1 (dung EP result vi la nguon chinh)
    combined_list = ep_list + [x for x in coa_list
                                if not any(y.get("ten_chi_tieu","").lower()[:15] ==
                                           x.get("ten_chi_tieu","").lower()[:15] for y in ep_list)]
    scan_scoring = score_scan(combined_list)
    print_score_report(scan_scoring, f"Do chinh xac Node 1 (Scan) -- {label}")

    # ── Node 2: Generate methods ──────────────────────────────────────────────
    sep("-")
    # Dung danh sach FIXED cho Node 2 de so sanh cong bang (doc lap voi ket qua scan)
    # Danh sach chuyen luan Folic Acid Hydrate EP (9 chi tieu chinh)
    FIXED_CRITERIA_FOR_NODE2 = [
        {"ten": "Tính chất / Appearance",
         "gioi_han": "Bột kết tinh màu vàng hoặc cam / Yellowish or orange, crystalline powder"},
        {"ten": "Định tính nhóm / Identification group",
         "gioi_han": "Nhóm I (First identification): Phép thử A, B, D. Nhóm II (Second identification): Phép thử A, C. / First identification: A, B, D; Second identification: A, C."},
        {"ten": "Định tính A (Quay cực đặc trưng) / Identification A (Specific optical rotation)",
         "gioi_han": "+18 đến +22 (tính trên chế phẩm khan) / +18 to +22 (anhydrous substance)"},
        {"ten": "Định tính B (Phổ hấp thụ hồng ngoại) / Identification B (IR spectrophotometry)",
         "gioi_han": "Phù hợp với folic acid CRS / Comparison: folic acid CRS"},
        {"ten": "Định tính C (Sắc ký lớp mỏng) / Identification C (Thin-layer chromatography)",
         "gioi_han": "Vết chính trong sắc ký đồ thu được từ dung dịch thử tương tự về vị trí, huỳnh quang và kích thước so với dung dịch đối chiếu / Principal spot similar in position, fluorescence and size to reference solution"},
        {"ten": "Định tính D (Hàm lượng nước) / Identification D (Water)",
         "gioi_han": "Đáp ứng phép thử Hàm lượng nước (xem mục nước) / Complies with the test for water"},
        {"ten": "Độ tan / Solubility",
         "gioi_han": "Hầu như không tan trong nước; tan trong dung dịch kiềm / Practically insoluble in water; soluble in alkali solutions"},
        {"ten": "Hàm lượng nước / Water",
         "gioi_han": "5,0% đến 8,5% / 5.0 per cent to 8.5 per cent"},
        {"ten": "Tạp chất liên quan / Related substances",
         "gioi_han": "Tạp chất A: tối đa 0,5%; Tổng tạp: tối đa 1,2% / Impurity A max 0.5%; Total max 1.2%"},
        {"ten": "Định lượng / Assay",
         "gioi_han": "96,0% đến 102,0% (tính trên chế phẩm khan) / 96.0 to 102.0 per cent (anhydrous substance)"},
        {"ten": "Tro sulfat / Sulfated ash",
         "gioi_han": "Tối đa 0,2% / Maximum 0.2 per cent"},
        {"ten": "Acid D-folic / D-folic acid",
         "gioi_han": "Không quá 0,3% (a/a) / ≤ 0.3% (a/a)"},
        {"ten": "Acetone",
         "gioi_han": "Không quá 1000 ppm / ≤ 1000 ppm"},
    ]
    criteria_for_gen = FIXED_CRITERIA_FOR_NODE2
    print(f"[Node 2] tcnl_generate_methods() -- {len(criteria_for_gen)} chi tieu (FIXED list)")
    sep("-")
    t4 = time.perf_counter()
    methods = tcnl_generate_methods(
        None,
        criteria_for_gen,
        PROVIDER, MODEL,
        keys, None,
        chunk_size=None,   # Auto
        max_workers=None,  # Auto
        bilingual=True,
        files_data=all_files_data
    )
    t5 = time.perf_counter()
    node2_time = t5 - t4
    total_time = t5 - t_enc0

    print(f"   So phuong phap sinh duoc: {len(methods)}")
    for k, v in list(methods.items())[:5]:
        print(f"   [{k[:40]}]: {str(v)[:80].replace(chr(10),' ')}...")
    print(f"\n   Thoi gian Node 2: {node2_time:.2f}s")
    print(f"   Tong thoi gian:   {total_time:.2f}s\n")

    methods_scoring = score_methods(methods, combined_list)
    print_score_report(methods_scoring, f"Do chinh xac Node 2 (Methods) -- {label}")

    # Tinh diem trung binh
    combined_acc = round((scan_scoring["accuracy_pct"] + methods_scoring["accuracy_pct"]) / 2, 1)

    # Luu ket qua
    result = {
        "label": label,
        "model": MODEL,
        "node0_time_sec":    round(node0_time, 2),
        "node1_time_sec":    round(node1_time, 2),
        "node2_time_sec":    round(node2_time, 2),
        "total_time_sec":    round(total_time, 2),
        "monograph_name":    monograph,
        "ep_criteria_count": len(ep_list),
        "coa_criteria_count": len(coa_list),
        "methods_count":     len(methods),
        "scan_accuracy_pct":    scan_scoring["accuracy_pct"],
        "methods_accuracy_pct": methods_scoring["accuracy_pct"],
        "combined_accuracy_pct": combined_acc,
        "scan_scoring":    scan_scoring,
        "methods_scoring": methods_scoring,
        "ep_list":  ep_list,
        "methods":  methods,
    }
    out = os.path.join(ROOT, "test", f"result_tcnl_{label.lower().replace(' ','_')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[SAVED] {out}")
    return result


def compare_tcnl(b: dict, i: dict):
    sep("=")
    print("SO SANH TRUOC/SAU CAI THIEN (TCNL)")
    sep("=")
    def arrow(bv, iv, higher_good=True):
        d = iv - bv
        if abs(d) < 0.05: return "-> Khong doi"
        return ("UP " if d > 0 else "DN ") + f"{d:+.2f}" + (" (BETTER)" if (d>0)==higher_good else " (WORSE)")

    rows = [
        ("Node 0 - Trich ten (s)",    b["node0_time_sec"],   i["node0_time_sec"],   False),
        ("Node 1 - Scan (s)",          b["node1_time_sec"],   i["node1_time_sec"],   False),
        ("Node 2 - Methods (s)",       b["node2_time_sec"],   i["node2_time_sec"],   False),
        ("Tong thoi gian (s)",         b["total_time_sec"],   i["total_time_sec"],   False),
        ("EP chi tieu tim thay",       b["ep_criteria_count"],i["ep_criteria_count"],True),
        ("Scan accuracy (%)",          b["scan_accuracy_pct"],i["scan_accuracy_pct"],True),
        ("Methods accuracy (%)",       b["methods_accuracy_pct"],i["methods_accuracy_pct"],True),
        ("Combined accuracy (%)",      b["combined_accuracy_pct"],i["combined_accuracy_pct"],True),
    ]
    print(f"  {'Tieu chi':<35} {'Baseline':>12} {'Improved':>12} {'Thay doi':>22}")
    print(f"  {'-'*35} {'-'*12} {'-'*12} {'-'*22}")
    for name, bv, iv, hg in rows:
        print(f"  {name:<35} {bv:>12.2f} {iv:>12.2f} {arrow(bv, iv, hg):>22}")
    speedup = round((b["total_time_sec"]-i["total_time_sec"])/b["total_time_sec"]*100, 1) if b["total_time_sec"] else 0
    acc_delta = i["combined_accuracy_pct"] - b["combined_accuracy_pct"]
    print(f"\n  Toc do tang: {speedup:+.1f}%")
    print(f"  Do chinh xac tang: {acc_delta:+.1f} diem %")
    sep("=")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["baseline","improved","compare"], default="baseline")
    args = p.parse_args()

    if args.mode == "baseline":
        run_tcnl_benchmark("BASELINE")
    elif args.mode == "improved":
        run_tcnl_benchmark("IMPROVED")
    elif args.mode == "compare":
        bp = os.path.join(ROOT,"test","result_tcnl_baseline.json")
        ip = os.path.join(ROOT,"test","result_tcnl_improved.json")
        if not os.path.exists(bp) or not os.path.exists(ip):
            print("Chay --mode baseline va --mode improved truoc!")
        else:
            with open(bp, encoding="utf-8") as f: b = json.load(f)
            with open(ip, encoding="utf-8") as f: i = json.load(f)
            compare_tcnl(b, i)
