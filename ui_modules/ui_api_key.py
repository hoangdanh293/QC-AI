"""
UI: API Key, AI Model & GitHub Auto-Update Management.
Direct access (no 2FA/password lock); API keys remain AES-256 encrypted on disk.
"""
import html
import uuid
import streamlit as st

from core import key_manager, updater
from core.key_manager import (
    load_api_keys,
    save_api_keys,
    load_model_config,
    save_model_config,
)
from core.ui_theme import render_kpi_card


def _render_update_tab() -> None:
    """Render GitHub auto-update & private-repo token configuration."""
    st.markdown("#### 🚀 Cập Nhật Phiên Bản Từ GitHub")
    local_ver = updater.get_local_version()
    local_sha = local_ver.get("commit_sha", "")
    short_sha = local_sha[:7] if local_sha else "Chưa đồng bộ"
    updated_at = local_ver.get("updated_at") or "—"
    commit_msg = local_ver.get("commit_message") or "—"

    c_info1, c_info2 = st.columns([2, 1])
    with c_info1:
        st.markdown(
            f"<div class='qc-kpi-card'>"
            f"<div class='qc-kpi-label'>PHIÊN BẢN HIỆN TẠI TRÊN MÁY</div>"
            f"<div style='display:flex;align-items:center;gap:10px;margin-top:4px;'>"
            f"<span class='qc-badge qc-badge-blue'>Commit: {html.escape(short_sha)}</span>"
            f"<span class='qc-badge qc-badge-neutral'>Nhánh: {updater.BRANCH}</span>"
            f"</div>"
            f"<div class='qc-kpi-sub' style='margin-top:8px;'>"
            f"<b>Ghi chú:</b> {html.escape(commit_msg)}<br>"
            f"<b>Cập nhật lúc:</b> {html.escape(updated_at)}"
            f"</div></div>",
            unsafe_allow_html=True,
        )
    with c_info2:
        st.info(
            "**Quy tắc an toàn khi cập nhật:**\n"
            "- Tự động giữ nguyên `api_key.json`, `drive_token.json` và dữ liệu riêng.\n"
            "- Thêm dữ liệu mới vào thư viện JSON, giữ nguyên mục cũ."
        )

    st.markdown("")
    col_chk, col_rst = st.columns([2, 1])
    with col_chk:
        if st.button("🔍 Kiểm tra phiên bản mới trên GitHub", type="primary", use_container_width=True, key="btn_check_upd_tab"):
            with st.spinner("Đang kết nối GitHub..."):
                st.session_state["upd_check_result"] = updater.check_for_updates()
    with col_rst:
        if st.button("🔁 Nạp lại ứng dụng", type="secondary", use_container_width=True, key="btn_restart_only_tab"):
            updater.trigger_restart()
            st.info("Đang khởi động lại hệ thống...")
            st.stop()

    chk = st.session_state.get("upd_check_result")
    if chk:
        if not chk.get("ok"):
            st.error(f"❌ {chk.get('error')}")
        elif not chk.get("has_update"):
            st.success(
                f"✅ Hệ thống đang ở phiên bản mới nhất (`{chk.get('remote_short_sha')}` — {chk.get('commit_message')})."
            )
        else:
            st.warning(
                f"🆕 **Có phiên bản mới trên GitHub!**\n\n"
                f"- **Commit mới:** `{chk.get('remote_short_sha')}` — {chk.get('commit_message')}\n"
                f"- **Tác giả:** {chk.get('author') or '—'} | **Thời gian:** {chk.get('commit_date') or '—'}"
            )
            if st.button("⬇️ Tải & Cập nhật ngay", type="primary", use_container_width=True, key="btn_apply_upd_tab"):
                status_box = st.empty()
                res = updater.apply_update(
                    remote_info=chk,
                    progress_cb=lambda msg: status_box.info(f"⏳ {msg}"),
                )
                if res.get("ok"):
                    st.session_state.pop("upd_check_result", None)
                    deps_note = " | Đã cài đặt thư viện mới" if res.get("deps_installed") else ""
                    st.success(
                        f"✅ {res['message']} "
                        f"(Cập nhật {res['updated_files']} file mã nguồn, "
                        f"hợp nhất {res['merged_new_keys']} mục thư viện mới, "
                        f"giữ nguyên {res['skipped_protected']} file cấu hình máy{deps_note}). "
                        f"Đang khởi động lại..."
                    )
                    updater.trigger_restart()
                    st.stop()
                else:
                    st.error(f"❌ {res.get('message')}")

    st.divider()
    with st.expander("🔑 Cấu hình GitHub Token (Chỉ cần nếu Repository đang đặt Private)", expanded=False):
        has_token = bool(updater.load_github_token())
        badge = (
            "<span class='qc-badge qc-badge-green'>🟢 Đã cấu hình Token cục bộ</span>"
            if has_token
            else "<span class='qc-badge qc-badge-neutral'>⚪ Chưa cấu hình (Dùng chế độ Public)</span>"
        )
        st.markdown(badge, unsafe_allow_html=True)
        st.caption(
            "Nếu repository `hoangdanh293/QC-AI` ở chế độ **Private**, mỗi máy chỉ cần nhập 1 lần "
            "GitHub Personal Access Token (quyền `Contents: Read-only`). Token được lưu riêng tại `github_token.json` trên máy này."
        )
        with st.form("github_token_form"):
            tok_input = st.text_input(
                "GitHub Personal Access Token",
                type="password",
                placeholder="github_pat_... hoặc ghp_...",
            )
            c_save, c_del = st.columns([2, 1])
            with c_save:
                if st.form_submit_button("💾 Lưu Token", type="primary", use_container_width=True):
                    if not tok_input.strip():
                        st.warning("Vui lòng nhập chuỗi Token trước khi lưu.")
                    else:
                        updater.save_github_token(tok_input.strip())
                        st.session_state.pop("upd_check_result", None)
                        st.success("✅ Đã lưu GitHub Token cục bộ!")
                        st.rerun()
            with c_del:
                if st.form_submit_button("🗑️ Xóa Token", type="secondary", use_container_width=True):
                    updater.clear_github_token()
                    st.session_state.pop("upd_check_result", None)
                    st.info("Đã xóa GitHub Token.")
                    st.rerun()


def _render_manager() -> None:
    f = key_manager._get_fernet()
    model_config = load_model_config()
    key_data = load_api_keys(fernet=f)
    keys_list = key_data.get("keys", [])
    active_count = sum(1 for k in keys_list if k.get("is_active"))
    total_models = sum(len(v) for v in model_config.values() if isinstance(v, list))
    local_ver = updater.get_local_version()
    short_sha = (local_ver.get("commit_sha") or "")[:7] or "Local"

    # ── Header ──
    st.markdown(
        "<h2 style='color:#0071e3;margin-bottom:4px;'>🔑 Quản Lý API Keys & Cấu Hình</h2>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<span class='qc-badge qc-badge-green'>🔒 Mã hóa AES-256 trên đĩa</span>&nbsp;"
        "<span class='qc-badge qc-badge-blue'>⚡ Truy cập trực tiếp</span>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    # ── KPI Summary Strip ──
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(render_kpi_card("Tổng API Keys", str(len(keys_list)), "Đã lưu trên máy"), unsafe_allow_html=True)
    k2.markdown(render_kpi_card("Keys Đang Bật", str(active_count), "Sẵn sàng gọi AI"), unsafe_allow_html=True)
    k3.markdown(render_kpi_card("Mô Hình AI", str(total_models), f"{len(model_config)} nhà cung cấp"), unsafe_allow_html=True)
    k4.markdown(render_kpi_card("Phiên Bản GitHub", short_sha, f"Nhánh {updater.BRANCH}"), unsafe_allow_html=True)

    st.markdown("")
    tab1, tab2, tab3 = st.tabs(["⚙️ Quản lý API Keys", "🤖 Mô Hình AI", "🔄 Cập nhật & Hệ thống"])

    # ══════════════════════════════════════════
    # TAB 1 — API KEYS
    # ══════════════════════════════════════════
    with tab1:
        with st.expander("➕ Thêm API Key mới", expanded=not bool(keys_list)):
            with st.form("add_key_form"):
                col1, col2 = st.columns(2)
                with col1:
                    provider = st.selectbox("Nhà cung cấp (Provider)*", ["Google API", "OpenAI"])
                    owner = st.text_input("Người sở hữu / Định danh*", placeholder="Ví dụ: QC_NhanVien_A")
                with col2:
                    avail_mdl = model_config.get(provider, [])
                    model = st.selectbox("Mô hình*", avail_mdl if avail_mdl else ["(Chưa có mô hình)"])
                    is_active = st.checkbox("Kích hoạt ngay", value=True)

                key_string = st.text_input("Chuỗi API Key*", type="password", placeholder="Nhập chuỗi key...")

                if st.form_submit_button("💾 Lưu API Key", type="primary"):
                    if not owner.strip() or not key_string.strip() or not model:
                        st.error("❌ Vui lòng điền đầy đủ các trường bắt buộc!")
                    else:
                        new_key = {
                            "id": str(uuid.uuid4()),
                            "provider": provider,
                            "model": model,
                            "owner": owner.strip(),
                            "key_string": key_string.strip(),
                            "is_active": is_active,
                        }
                        key_data.setdefault("keys", []).append(new_key)
                        save_api_keys(key_data, fernet=f)
                        st.success("✅ Đã thêm và mã hóa API Key thành công!")
                        st.rerun()

        st.markdown("#### Danh sách API Key hiện tại")
        if not keys_list:
            st.markdown(
                "<div class='qc-empty-state'>"
                "<b>Chưa có API Key nào được cấu hình</b><br>"
                "<span style='font-size:13px;'>Hãy mở mục '➕ Thêm API Key mới' ở trên để thêm khóa Google Gemini hoặc OpenAI.</span>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            for idx, item in enumerate(keys_list):
                status_icon = "🟢" if item.get("is_active") else "🔴"
                status_text = "Đang bật" if item.get("is_active") else "Đang tắt"
                label = f"{status_icon} {item.get('provider', '')} — {item.get('model', '')} | {item.get('owner', '')} ({status_text})"
                with st.expander(label):
                    with st.form(f"edit_key_{item['id']}"):
                        c1, c2 = st.columns(2)
                        with c1:
                            edit_owner = st.text_input("Sở hữu", value=item.get("owner", ""), key=f"eo_{item['id']}")
                            edit_key = st.text_input(
                                "Chuỗi Key (để trống = giữ nguyên)",
                                type="password",
                                key=f"ek_{item['id']}",
                            )
                        with c2:
                            edit_active = st.checkbox("Kích hoạt", value=bool(item.get("is_active")), key=f"ea_{item['id']}")
                            prov_cls = "qc-badge-blue" if item.get("provider") == "Google API" else "qc-badge-amber"
                            st.markdown(
                                f"<span class='qc-badge {prov_cls}'>{html.escape(item.get('provider', ''))}</span>&nbsp;"
                                f"<span class='qc-badge qc-badge-green'>🔒 AES-256</span>",
                                unsafe_allow_html=True,
                            )

                        b1, b2 = st.columns([1, 1])
                        with b1:
                            if st.form_submit_button("💾 Cập nhật", type="primary"):
                                item["owner"] = edit_owner.strip()
                                item["is_active"] = edit_active
                                if edit_key.strip():
                                    item["key_string"] = edit_key.strip()
                                save_api_keys(key_data, fernet=f)
                                st.success("✅ Đã cập nhật!")
                                st.rerun()
                        with b2:
                            if st.form_submit_button("🗑️ Xóa Key này", type="secondary"):
                                keys_list.pop(idx)
                                save_api_keys(key_data, fernet=f)
                                st.warning("Đã xóa!")
                                st.rerun()

    # ══════════════════════════════════════════
    # TAB 2 — MODELS
    # ══════════════════════════════════════════
    with tab2:
        st.markdown("#### Cấu hình danh sách Mô hình (Model)")
        c_prov, c_mod = st.columns(2)
        with c_prov:
            prov_sel = st.selectbox("Chọn Provider:", ["Google API", "OpenAI"], key="prov_sel")
        with c_mod:
            new_model = st.text_input(f"Tên mô hình mới cho {prov_sel}:", placeholder="Ví dụ: gpt-4o")
            if st.button("➕ Thêm Mô Hình", type="primary"):
                if new_model.strip():
                    if new_model.strip() not in model_config.get(prov_sel, []):
                        model_config.setdefault(prov_sel, []).append(new_model.strip())
                        save_model_config(model_config)
                        st.success(f"Đã thêm {new_model} vào {prov_sel}!")
                        st.rerun()
                    else:
                        st.warning("Mô hình này đã tồn tại!")

        st.markdown(f"**Các mô hình hiện tại của {prov_sel}:**")
        for m in model_config.get(prov_sel, []):
            col_t, col_b = st.columns([4, 1])
            col_t.code(m)
            if col_b.button("🗑️ Xóa", key=f"del_model_{m}", type="secondary"):
                model_config[prov_sel].remove(m)
                save_model_config(model_config)
                st.rerun()

    # ══════════════════════════════════════════
    # TAB 3 — GITHUB UPDATE & SYSTEM
    # ══════════════════════════════════════════
    with tab3:
        _render_update_tab()


# ══════════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════

def render_api_key_manager() -> None:
    _render_manager()
