"""
drive_manager.py
================
Quản lý tích hợp Google Drive API cho QC AI CPC1HN.

Hỗ trợ 2 phương thức xác thực:
  1. OAuth 2.0  – Đăng nhập tài khoản Google cá nhân (credentials.json)
  2. Service Account – Dùng JSON key từ Google Cloud Console (service_account.json)

Cấu hình lưu tại: drive_config.json (thư mục gốc ứng dụng)
"""

import os
import io
import json
import mimetypes
import traceback
from pathlib import Path

# ─────────────────────────────────────────────────
#  Config file path
# ─────────────────────────────────────────────────
_BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(_BASE_DIR, "drive_config.json")

_DEFAULT_CONFIG = {
    "auth_type": "oauth",           # "oauth" hoặc "service_account"
    "credentials_file": "",         # Đường dẫn tuyệt đối tới credentials.json / service_account.json
    "token_file": os.path.join(_BASE_DIR, "drive_token.json"),
    "root_folder_id": "",           # ID folder gốc trên Drive
    "root_folder_name": "QC Hồ Sơ Kiểm Nghiệm",
    "scopes": [
        "https://www.googleapis.com/auth/drive"
    ]
}

SCOPES = ["https://www.googleapis.com/auth/drive"]


# ══════════════════════════════════════════════════════════
#  Config I/O
# ══════════════════════════════════════════════════════════

def load_drive_config() -> dict:
    """Tải cấu hình Drive. Tạo mới nếu chưa tồn tại."""
    if not os.path.exists(CONFIG_FILE):
        save_drive_config(_DEFAULT_CONFIG.copy())
        return _DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # Merge defaults cho các key mới
        for k, v in _DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
        return cfg
    except Exception:
        return _DEFAULT_CONFIG.copy()


def save_drive_config(cfg: dict):
    """Lưu cấu hình Drive xuống file."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════
#  Authentication
# ══════════════════════════════════════════════════════════

def _check_google_libs() -> bool:
    """Kiểm tra thư viện Google đã cài chưa."""
    try:
        import googleapiclient
        import google.auth
        return True
    except ImportError:
        return False


def authenticate_drive(cfg: dict = None):
    """
    Xác thực và trả về Google Drive service object.

    Parameters
    ----------
    cfg : dict, optional
        Cấu hình drive (load từ load_drive_config() nếu None).

    Returns
    -------
    service : googleapiclient.discovery.Resource
        Drive API service object, hoặc None nếu lỗi.

    Raises
    ------
    ImportError  – Thư viện Google chưa được cài đặt.
    FileNotFoundError – File credentials không tồn tại.
    Exception    – Lỗi xác thực khác.
    """
    if not _check_google_libs():
        raise ImportError(
            "Thư viện Google chưa được cài đặt. "
            "Chạy CaiDat_ThuVien.bat để cài đặt."
        )

    from googleapiclient.discovery import build

    if cfg is None:
        cfg = load_drive_config()

    auth_type   = cfg.get("auth_type", "oauth")
    creds_file  = cfg.get("credentials_file", "")
    token_file  = cfg.get("token_file", os.path.join(_BASE_DIR, "drive_token.json"))

    if not creds_file or not os.path.exists(creds_file):
        raise FileNotFoundError(
            f"File credentials không tìm thấy: '{creds_file}'\n"
            "Hãy vào tab Cài Đặt Drive để cấu hình."
        )

    creds = None

    if auth_type == "service_account":
        # ── Service Account ──────────────────────────────────────────
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            creds_file, scopes=SCOPES
        )

    else:
        # ── OAuth 2.0 ────────────────────────────────────────────────
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request

        # Thử load token đã lưu
        if os.path.exists(token_file):
            try:
                creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            except Exception:
                creds = None

        # Nếu token hết hạn hoặc chưa có
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception:
                    creds = None

            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
                # Chạy luồng xác thực local (mở browser)
                creds = flow.run_local_server(port=0)

            # Lưu token để dùng lần sau
            with open(token_file, "w") as f:
                f.write(creds.to_json())

    service = build("drive", "v3", credentials=creds)
    return service


# ══════════════════════════════════════════════════════════
#  Folder Operations
# ══════════════════════════════════════════════════════════

def list_folders(service, parent_id: str = "root") -> list[dict]:
    """
    Liệt kê các folder con trong parent_id.

    Returns list of {id, name, createdTime, modifiedTime}
    """
    query = (
        f"'{parent_id}' in parents "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    results = []
    page_token = None

    while True:
        params = dict(
            q=query,
            spaces="drive",
            fields="nextPageToken, files(id, name, createdTime, modifiedTime)",
            pageSize=100,
            orderBy="name"
        )
        if page_token:
            params["pageToken"] = page_token

        resp = service.files().list(**params).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


def create_folder(service, name: str, parent_id: str = "root") -> dict:
    """
    Tạo folder mới.

    Returns dict {id, name}
    """
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }
    folder = service.files().create(
        body=metadata,
        fields="id, name"
    ).execute()
    return folder


def get_folder_path(service, folder_id: str) -> list[dict]:
    """
    Lấy breadcrumb path từ root đến folder_id.
    Returns list of {id, name} từ gốc → hiện tại.
    """
    path = []
    fid = folder_id
    visited = set()

    while fid and fid != "root" and fid not in visited:
        visited.add(fid)
        try:
            meta = service.files().get(
                fileId=fid,
                fields="id, name, parents"
            ).execute()
            path.insert(0, {"id": meta["id"], "name": meta["name"]})
            parents = meta.get("parents", [])
            fid = parents[0] if parents else None
        except Exception:
            break

    return path


# ══════════════════════════════════════════════════════════
#  File Operations
# ══════════════════════════════════════════════════════════

def list_files(service, folder_id: str, name_query: str = "") -> list[dict]:
    """
    Liệt kê files (không bao gồm folder) trong folder_id.
    name_query: lọc theo tên chứa chuỗi này (không phân biệt hoa thường).

    Returns list of {id, name, mimeType, size, createdTime, modifiedTime, webViewLink}
    """
    conditions = [
        f"'{folder_id}' in parents",
        "mimeType != 'application/vnd.google-apps.folder'",
        "trashed = false"
    ]
    if name_query:
        safe_q = name_query.replace("'", "\\'")
        conditions.append(f"name contains '{safe_q}'")

    query = " and ".join(conditions)
    results = []
    page_token = None

    while True:
        params = dict(
            q=query,
            spaces="drive",
            fields="nextPageToken, files(id, name, mimeType, size, createdTime, modifiedTime, webViewLink, webContentLink)",
            pageSize=100,
            orderBy="name"
        )
        if page_token:
            params["pageToken"] = page_token

        resp = service.files().list(**params).execute()
        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


_FOLDER_PARENTS_CACHE = {}  # folder_id -> list of parent folder_ids

def _is_descendant(service, folder_id: str, target_root_id: str) -> bool:
    """Kiểm tra đệ quy xem folder_id có nằm trong target_root_id hay không."""
    if not folder_id or not target_root_id:
        return False
    if folder_id == target_root_id:
        return True
    
    # Kiểm tra trong cache trước
    if folder_id in _FOLDER_PARENTS_CACHE:
        parents = _FOLDER_PARENTS_CACHE[folder_id]
    else:
        try:
            meta = service.files().get(
                fileId=folder_id,
                fields="parents"
            ).execute()
            parents = meta.get("parents", [])
            _FOLDER_PARENTS_CACHE[folder_id] = parents
        except Exception:
            parents = []
            _FOLDER_PARENTS_CACHE[folder_id] = parents
            
    for p in parents:
        if p == target_root_id or _is_descendant(service, p, target_root_id):
            return True
            
    return False


def search_files_global(
    service,
    root_folder_id: str,
    name_query: str = "",
    bfo_query: str = "",
    max_results: int = 200
) -> list[dict]:
    """
    Tìm kiếm file trên toàn Drive (trong root_folder_id).
    - name_query: tìm theo tên file chứa chuỗi
    - bfo_query : tìm file có tên chứa mã BFO

    Returns list of {id, name, mimeType, size, createdTime, modifiedTime,
                     webViewLink, webContentLink, parents}
    """
    conditions = ["trashed = false",
                  "mimeType != 'application/vnd.google-apps.folder'"]

    search_term = name_query or bfo_query
    if search_term:
        safe_q = search_term.replace("'", "\\'")
        conditions.append(f"name contains '{safe_q}'")

    query = " and ".join(conditions)
    results = []
    page_token = None

    while True:
        params = dict(
            q=query,
            spaces="drive",
            fields="nextPageToken, files(id, name, mimeType, size, createdTime, modifiedTime, webViewLink, webContentLink, parents)",
            pageSize=min(max_results, 100),
            orderBy="modifiedTime desc"
        )
        if page_token:
            params["pageToken"] = page_token

        resp = service.files().list(**params).execute()
        batch = resp.get("files", [])

        # Lọc chỉ lấy file nằm trong root_folder_id nếu có
        if root_folder_id and root_folder_id != "root":
            for f in batch:
                f_parents = f.get("parents", [])
                is_inside = False
                for p in f_parents:
                    if p == root_folder_id or _is_descendant(service, p, root_folder_id):
                        is_inside = True
                        break
                if is_inside:
                    results.append(f)
        else:
            results.extend(batch)

        page_token = resp.get("nextPageToken")
        if not page_token or len(results) >= max_results:
            break

    return results[:max_results]


def get_file_metadata(service, file_id: str) -> dict:
    """Lấy metadata của file."""
    return service.files().get(
        fileId=file_id,
        fields="id, name, mimeType, size, createdTime, modifiedTime, webViewLink, webContentLink, parents"
    ).execute()


def download_file(service, file_id: str) -> bytes:
    """
    Download file về dạng bytes.
    Nếu là Google Doc thì export sang docx.
    """
    from googleapiclient.http import MediaIoBaseDownload

    meta = get_file_metadata(service, file_id)
    mime = meta.get("mimeType", "")

    # Google Docs → export docx
    if mime == "application/vnd.google-apps.document":
        request = service.files().export_media(
            fileId=file_id,
            mimeType="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    else:
        request = service.files().get_media(fileId=file_id)

    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    return buf.getvalue()


def upload_file(
    service,
    file_bytes: bytes,
    file_name: str,
    folder_id: str,
    mime_type: str = None
) -> dict:
    """
    Upload file lên Google Drive folder.

    Returns dict {id, name, webViewLink}
    """
    from googleapiclient.http import MediaIoBaseUpload

    if mime_type is None:
        mime_type, _ = mimetypes.guess_type(file_name)
        if mime_type is None:
            mime_type = "application/octet-stream"

    metadata = {
        "name": file_name,
        "parents": [folder_id]
    }
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type)

    uploaded = service.files().create(
        body=metadata,
        media_body=media,
        fields="id, name, webViewLink"
    ).execute()

    return uploaded


def delete_file(service, file_id: str):
    """Xóa file (chuyển vào thùng rác)."""
    service.files().delete(fileId=file_id).execute()


# ══════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════

def format_file_size(size_str) -> str:
    """Định dạng kích thước file thân thiện."""
    try:
        size = int(size_str)
    except (TypeError, ValueError):
        return "—"
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 ** 3:
        return f"{size / 1024 ** 2:.1f} MB"
    else:
        return f"{size / 1024 ** 3:.1f} GB"


def format_datetime(dt_str: str) -> str:
    """Định dạng datetime từ ISO 8601 sang dd/mm/yyyy HH:MM."""
    if not dt_str:
        return "—"
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone()
        return local_dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return dt_str[:10]


def get_file_icon(mime_type: str) -> str:
    """Trả về icon emoji theo loại file."""
    icons = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "📄",
        "application/msword": "📄",
        "application/vnd.google-apps.document": "📝",
        "application/pdf": "📕",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "📊",
        "application/vnd.ms-excel": "📊",
        "application/vnd.google-apps.spreadsheet": "📊",
        "image/jpeg": "🖼️",
        "image/png": "🖼️",
        "text/plain": "📃",
    }
    return icons.get(mime_type, "📎")


def is_printable(mime_type: str) -> bool:
    """Kiểm tra file có thể in qua browser không."""
    printable = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "application/vnd.google-apps.document",
    }
    return mime_type in printable
