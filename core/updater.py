"""
GitHub Auto-Updater & Smart Library Merger for QC AI CPC1HN.
Supports both Private repositories (via GitHub Personal Access Token)
and Public repositories without requiring Git to be installed on client machines.
"""
from __future__ import annotations

import datetime
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from typing import Callable

import requests

REPO_OWNER = "hoangdanh293"
REPO_NAME = "QC-AI"
BRANCH = "main"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = "app_version.json"
GITHUB_TOKEN_FILE = "github_token.json"

# Files that must NEVER overwrite existing local machine files
PROTECTED_EXACT = {
    "api_key.json",
    "drive_token.json",
    "drive_config.json",
    "github_token.json",
    "app_version.json",
    "personal_style.json",
    "ui_cache.dat",
    "render_state.dat",
    "streamlit_run.log",
    "restart.txt",
    "shutdown.txt",
    "desktop.ini",
}

# Prefixes/directories that should not be synced or overwritten from GitHub
IGNORED_DIR_PREFIXES = (
    ".git/",
    "__pycache__/",
    "cache_print/",
    "scratch/",
    "Test/",
)

# Runtime files that should never be created from repo if missing locally
RUNTIME_SKIP_IF_MISSING = {
    "ui_cache.dat",
    "render_state.dat",
    "streamlit_run.log",
    "restart.txt",
    "shutdown.txt",
    "desktop.ini",
}

# JSON dict libraries: preserve existing local keys, add new keys from GitHub
SMART_MERGE_DICT_JSON = {
    "criteria_master.json",
    "reagent_library.json",
    "sop_reference_library.json",
    "method_library.json",
    "style_examples_library.json",
}

MODEL_CONFIG_FILE = "model_config.json"


def _abs_path(base_dir: str, rel_path: str) -> str:
    return os.path.join(base_dir, *rel_path.split("/"))


def _file_sha256(path: str) -> str:
    if not os.path.exists(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ══════════════════════════════════════════════════════════════════════
#  GitHub Token Management (for Private Repositories)
# ══════════════════════════════════════════════════════════════════════

def load_github_token(base_dir: str = BASE_DIR) -> str:
    env_tok = os.environ.get("QC_AI_GITHUB_TOKEN", "").strip()
    if env_tok:
        return env_tok
    path = os.path.join(base_dir, GITHUB_TOKEN_FILE)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("token", "")).strip()
    except Exception:
        return ""


def save_github_token(token: str, base_dir: str = BASE_DIR) -> None:
    path = os.path.join(base_dir, GITHUB_TOKEN_FILE)
    cleaned = token.strip()
    if not cleaned:
        clear_github_token(base_dir=base_dir)
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"token": cleaned}, f, ensure_ascii=False, indent=2)


def clear_github_token(base_dir: str = BASE_DIR) -> None:
    path = os.path.join(base_dir, GITHUB_TOKEN_FILE)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _build_headers(token: str = "") -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "QC-AI-CPC1HN-Updater",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ══════════════════════════════════════════════════════════════════════
#  Local Version Tracking
# ══════════════════════════════════════════════════════════════════════

def _no_window_flags() -> int:
    """Return CREATE_NO_WINDOW on Windows so pythonw never flashes a console."""
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _read_git_head_sha(base_dir: str) -> str:
    """Read current git commit SHA directly from .git files without spawning git.exe."""
    git_dir = os.path.join(base_dir, ".git")
    head_path = os.path.join(git_dir, "HEAD")
    if not os.path.isfile(head_path):
        return ""
    try:
        with open(head_path, "r", encoding="utf-8") as f:
            head = f.read().strip()
        if head.startswith("ref: "):
            ref = head[5:].strip()
            ref_path = os.path.join(git_dir, *ref.split("/"))
            if os.path.isfile(ref_path):
                with open(ref_path, "r", encoding="utf-8") as rf:
                    return rf.read().strip()
            packed_path = os.path.join(git_dir, "packed-refs")
            if os.path.isfile(packed_path):
                with open(packed_path, "r", encoding="utf-8") as pf:
                    for line in pf:
                        if not line.startswith("#") and not line.startswith("^"):
                            parts = line.strip().split(" ", 1)
                            if len(parts) == 2 and parts[1] == ref:
                                return parts[0]
            return ""
        return head
    except Exception:
        return ""


def get_local_version(base_dir: str = BASE_DIR) -> dict:
    path = os.path.join(base_dir, VERSION_FILE)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # Fallback: read directly from .git files (zero subprocesses, no console flash)
    sha = _read_git_head_sha(base_dir)
    if sha:
        return {
            "commit_sha": sha,
            "commit_message": "Đang chạy từ mã nguồn Git",
            "commit_date": "",
            "updated_at": "",
        }

    return {
        "commit_sha": "",
        "commit_message": "Chưa đồng bộ phiên bản từ GitHub",
        "commit_date": "",
        "updated_at": "",
    }


def _save_local_version(info: dict, base_dir: str = BASE_DIR) -> None:
    path = os.path.join(base_dir, VERSION_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════
#  Smart Merge Helpers
# ══════════════════════════════════════════════════════════════════════

def smart_merge_dict_json(local_path: str, incoming_path: str) -> tuple[bool, int]:
    """
    Merge incoming JSON dict into local JSON dict.
    Existing local keys are preserved untouched; only missing keys are added.
    Returns (changed, added_count).
    """
    try:
        with open(incoming_path, "r", encoding="utf-8") as f:
            incoming = json.load(f)
    except Exception:
        return False, 0

    if not isinstance(incoming, dict):
        return False, 0

    if not os.path.exists(local_path):
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        shutil.copy2(incoming_path, local_path)
        return True, len(incoming)

    try:
        with open(local_path, "r", encoding="utf-8") as f:
            local = json.load(f)
    except Exception:
        local = {}

    if not isinstance(local, dict):
        return False, 0

    added = 0
    for k, v in incoming.items():
        if k not in local:
            local[k] = v
            added += 1

    if added > 0:
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(local, f, ensure_ascii=False, indent=4)
        return True, added
    return False, 0


def smart_merge_model_config(local_path: str, incoming_path: str) -> tuple[bool, int]:
    """
    Merge provider model lists: preserve all local models and append new ones from GitHub.
    Returns (changed, added_count).
    """
    try:
        with open(incoming_path, "r", encoding="utf-8") as f:
            incoming = json.load(f)
    except Exception:
        return False, 0

    if not isinstance(incoming, dict):
        return False, 0

    if not os.path.exists(local_path):
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        shutil.copy2(incoming_path, local_path)
        return True, sum(len(v) for v in incoming.values() if isinstance(v, list))

    try:
        with open(local_path, "r", encoding="utf-8") as f:
            local = json.load(f)
    except Exception:
        local = {}

    if not isinstance(local, dict):
        return False, 0

    added = 0
    for provider, models in incoming.items():
        if not isinstance(models, list):
            continue
        if provider not in local or not isinstance(local[provider], list):
            local[provider] = list(models)
            added += len(models)
        else:
            existing_set = set(local[provider])
            for m in models:
                if m not in existing_set:
                    local[provider].append(m)
                    existing_set.add(m)
                    added += 1

    if added > 0:
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(local, f, ensure_ascii=False, indent=4)
        return True, added
    return False, 0


# ══════════════════════════════════════════════════════════════════════
#  Check & Apply Update from GitHub
# ══════════════════════════════════════════════════════════════════════

def check_for_updates(base_dir: str = BASE_DIR, timeout: int = 8) -> dict:
    """Check latest commit on GitHub main branch against local version."""
    local_info = get_local_version(base_dir=base_dir)
    local_sha = local_info.get("commit_sha", "")
    token = load_github_token(base_dir=base_dir)

    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/{BRANCH}"
    try:
        resp = requests.get(url, headers=_build_headers(token), timeout=timeout)
    except requests.RequestException as exc:
        return {
            "ok": False,
            "has_update": False,
            "local_sha": local_sha,
            "remote_sha": "",
            "remote_short_sha": "",
            "commit_message": "",
            "commit_date": "",
            "author": "",
            "needs_token": False,
            "error": f"Không thể kết nối GitHub: {exc}",
        }

    if resp.status_code in (401, 403, 404):
        if not token:
            msg = (
                "Không truy cập được repository (Repo đang ở chế độ Private). "
                "Vui lòng nhập GitHub Personal Access Token hoặc chuyển Repo sang Public."
            )
        else:
            msg = f"GitHub Token không hợp lệ hoặc không có quyền đọc repo (HTTP {resp.status_code})."
        return {
            "ok": False,
            "has_update": False,
            "local_sha": local_sha,
            "remote_sha": "",
            "remote_short_sha": "",
            "commit_message": "",
            "commit_date": "",
            "author": "",
            "needs_token": True,
            "error": msg,
        }

    if resp.status_code != 200:
        return {
            "ok": False,
            "has_update": False,
            "local_sha": local_sha,
            "remote_sha": "",
            "remote_short_sha": "",
            "commit_message": "",
            "commit_date": "",
            "author": "",
            "needs_token": False,
            "error": f"GitHub API trả về lỗi HTTP {resp.status_code}.",
        }

    data = resp.json()
    remote_sha = data.get("sha", "")
    commit_obj = data.get("commit", {})
    commit_msg = (commit_obj.get("message") or "").splitlines()[0]
    commit_date = (commit_obj.get("committer") or {}).get("date", "")
    author = (commit_obj.get("author") or {}).get("name", "")

    has_update = bool(remote_sha and remote_sha != local_sha)
    return {
        "ok": True,
        "has_update": has_update,
        "local_sha": local_sha,
        "remote_sha": remote_sha,
        "remote_short_sha": remote_sha[:7],
        "commit_message": commit_msg,
        "commit_date": commit_date,
        "author": author,
        "needs_token": False,
        "error": None,
    }


def _is_protected_file(rel_norm: str) -> bool:
    if rel_norm in PROTECTED_EXACT:
        return True
    base_name = os.path.basename(rel_norm)
    if base_name.startswith("client_secret_") and base_name.endswith(".json"):
        return True
    return False


def _is_ignored_path(rel_norm: str) -> bool:
    if any(rel_norm.startswith(prefix) for prefix in IGNORED_DIR_PREFIXES):
        return True
    if "/__pycache__/" in f"/{rel_norm}" or rel_norm.endswith(".pyc"):
        return True
    return False


def apply_update_from_archive_bytes(
    zip_bytes: bytes,
    remote_info: dict,
    base_dir: str = BASE_DIR,
    install_deps: bool = True,
    progress_cb: Callable[[str], None] | None = None,
) -> dict:
    """
    Extract a GitHub repository zip archive and apply updates safely:
    - Overwrite source code and templates
    - Preserve protected local configs/keys
    - Smart-merge JSON dictionary libraries and model_config.json
    - Re-install requirements.txt if changed
    """
    def _log(msg: str):
        if progress_cb:
            progress_cb(msg)

    req_path = os.path.join(base_dir, "requirements.txt")
    old_req_hash = _file_sha256(req_path)

    updated_files = 0
    merged_files = 0
    merged_new_keys = 0
    skipped_protected = 0
    deps_installed = False

    tmp_dir = tempfile.mkdtemp(prefix="qc_ai_upd_")
    try:
        _log("Đang giải nén gói cập nhật...")
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(tmp_dir)

        entries = [os.path.join(tmp_dir, d) for d in os.listdir(tmp_dir)]
        roots = [d for d in entries if os.path.isdir(d)]
        src_root = roots[0] if len(roots) == 1 else tmp_dir

        _log("Đang cập nhật mã nguồn và hợp nhất thư viện...")
        for root, _, files in os.walk(src_root):
            for fname in files:
                src_file = os.path.join(root, fname)
                rel_path = os.path.relpath(src_file, src_root)
                rel_norm = rel_path.replace("\\", "/")

                if _is_ignored_path(rel_norm):
                    continue

                dest_file = _abs_path(base_dir, rel_norm)

                if _is_protected_file(rel_norm):
                    if os.path.exists(dest_file) or rel_norm in RUNTIME_SKIP_IF_MISSING:
                        skipped_protected += 1
                        continue
                    os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                    shutil.copy2(src_file, dest_file)
                    updated_files += 1
                    continue

                if rel_norm in SMART_MERGE_DICT_JSON:
                    changed, added = smart_merge_dict_json(dest_file, src_file)
                    if changed:
                        merged_files += 1
                        merged_new_keys += added
                    continue

                if rel_norm == MODEL_CONFIG_FILE:
                    changed, added = smart_merge_model_config(dest_file, src_file)
                    if changed:
                        merged_files += 1
                        merged_new_keys += added
                    continue

                os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                shutil.copy2(src_file, dest_file)
                updated_files += 1

        new_req_hash = _file_sha256(req_path)
        if install_deps and os.path.exists(req_path) and new_req_hash != old_req_hash:
            _log("Phát hiện thư viện mới, đang cài đặt packages...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req_path],
                check=False,
                capture_output=True,
                text=True,
                creationflags=_no_window_flags(),
            )
            deps_installed = True

        version_payload = {
            "commit_sha": remote_info.get("remote_sha", ""),
            "commit_message": remote_info.get("commit_message", ""),
            "commit_date": remote_info.get("commit_date", ""),
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "req_hash": new_req_hash,
        }
        _save_local_version(version_payload, base_dir=base_dir)

        return {
            "ok": True,
            "message": "Cập nhật thành công!",
            "updated_files": updated_files,
            "merged_files": merged_files,
            "merged_new_keys": merged_new_keys,
            "skipped_protected": skipped_protected,
            "deps_installed": deps_installed,
            "remote_sha": remote_info.get("remote_sha", ""),
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def apply_update(
    base_dir: str = BASE_DIR,
    remote_info: dict | None = None,
    install_deps: bool = True,
    progress_cb: Callable[[str], None] | None = None,
    timeout: int = 30,
) -> dict:
    """Download latest main branch archive from GitHub and apply update."""
    if remote_info is None or not remote_info.get("ok"):
        remote_info = check_for_updates(base_dir=base_dir, timeout=10)
        if not remote_info.get("ok"):
            return {
                "ok": False,
                "message": remote_info.get("error", "Không kiểm tra được phiên bản."),
                "needs_token": remote_info.get("needs_token", False),
            }

    if progress_cb:
        progress_cb("Đang tải mã nguồn mới từ GitHub...")

    token = load_github_token(base_dir=base_dir)
    zip_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/zipball/{BRANCH}"
    try:
        resp = requests.get(zip_url, headers=_build_headers(token), timeout=timeout)
    except requests.RequestException as exc:
        return {
            "ok": False,
            "message": f"Lỗi khi tải gói cập nhật từ GitHub: {exc}",
            "needs_token": False,
        }

    if resp.status_code != 200:
        return {
            "ok": False,
            "message": f"Không thể tải gói cập nhật (HTTP {resp.status_code}).",
            "needs_token": resp.status_code in (401, 403, 404),
        }

    return apply_update_from_archive_bytes(
        zip_bytes=resp.content,
        remote_info=remote_info,
        base_dir=base_dir,
        install_deps=install_deps,
        progress_cb=progress_cb,
    )


def trigger_restart(base_dir: str = BASE_DIR) -> None:
    """Signal run_app.py to restart Streamlit with updated source files."""
    restart_file = os.path.join(base_dir, "restart.txt")
    with open(restart_file, "w", encoding="utf-8") as f:
        f.write("restart")


def _cli_main() -> int:
    print("=== KIEM TRA & CAP NHAT QC AI CPC1HN TU GITHUB ===")
    info = check_for_updates()
    if not info.get("ok"):
        print(f"[LOI] {info.get('error')}")
        return 1

    print(f"Phien ban hien tai : {info.get('local_sha')[:7] or 'Chua co'}")
    print(f"Phien ban GitHub   : {info.get('remote_short_sha')} - {info.get('commit_message')}")

    if not info.get("has_update"):
        print("He thong dang o phien ban moi nhat!")
        return 0

    res = apply_update(remote_info=info, progress_cb=lambda m: print(f"-> {m}"))
    if not res.get("ok"):
        print(f"[LOI] {res.get('message')}")
        return 1

    print(
        f"[HOAN TAT] Da cap nhat {res['updated_files']} file, "
        f"hop nhat {res['merged_new_keys']} muc thu vien moi "
        f"({res['skipped_protected']} file cau hinh cuc bo duoc giu nguyen)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(_cli_main())
