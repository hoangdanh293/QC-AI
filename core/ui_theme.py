"""
Shared Design System & Motion Tokens for QC AI CPC1HN.
Combines clean Apple HIG surface hierarchy with accessible contrast,
GPU-composited micro-interactions, and reduced-motion support.
"""
import streamlit as st

_THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
    --font-apple: "Inter", -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;

    /* Surface & Canvas */
    --apple-bg: #f4f5f7;
    --apple-surface: #ffffff;
    --apple-surface-2: #f8f9fb;
    --apple-surface-hover: #f1f3f6;

    /* Typography */
    --apple-text-main: #111827;
    --apple-text-secondary: #374151;
    --apple-text-muted: #6b7280;
    --apple-text-placeholder: #9ca3af;

    /* Brand & Semantic */
    --apple-blue: #0071e3;
    --apple-blue-hover: #0062c4;
    --apple-blue-light: #e8f1fd;
    --apple-green: #16a34a;
    --apple-green-bg: #ecfdf3;
    --apple-red: #dc2626;
    --apple-red-bg: #fef2f2;
    --apple-orange: #d97706;
    --apple-orange-bg: #fffbeb;

    /* Borders & Radii */
    --apple-separator: rgba(15, 23, 42, 0.10);
    --apple-separator-strong: rgba(15, 23, 42, 0.16);
    --apple-radius-xs: 6px;
    --apple-radius-sm: 10px;
    --apple-radius-md: 13px;
    --apple-radius-lg: 18px;
    --apple-radius-xl: 24px;

    /* Elevation */
    --shadow-xs: 0 1px 2px rgba(15, 23, 42, 0.04);
    --shadow-sm: 0 2px 8px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);
    --shadow-md: 0 6px 20px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(15, 23, 42, 0.04);

    /* Motion Tokens */
    --ease-out-expo: cubic-bezier(0.22, 1, 0.36, 1);
    --dur-press: 120ms;
    --dur-hover: 160ms;
    --dur-enter: 220ms;
}

@keyframes qcFadeSlideIn {
    from {
        opacity: 0;
        transform: translateY(6px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes qcPulseBorder {
    0%, 100% { box-shadow: 0 0 0 0 rgba(0, 113, 227, 0.16); }
    50% { box-shadow: 0 0 0 4px rgba(0, 113, 227, 0.06); }
}

/* ─── Base ─── */
.stApp, html, body {
    background-color: var(--apple-bg) !important;
    color: var(--apple-text-main) !important;
    font-family: var(--font-apple) !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}
.block-container {
    padding-top: 3rem !important;
    padding-bottom: 3rem !important;
    max-width: 94% !important;
}
header[data-testid="stHeader"] {
    background-color: transparent !important;
}
div[data-testid="stVerticalBlock"] {
    gap: 0.45rem !important;
}

/* ─── Cards & Containers ─── */
div[data-testid="stContainer"] {
    background-color: var(--apple-surface) !important;
    border-radius: var(--apple-radius-md) !important;
    border: 1px solid var(--apple-separator) !important;
    box-shadow: var(--shadow-xs) !important;
    padding: 16px !important;
}
div[data-testid="stContainer"] div[data-testid="stContainer"] {
    padding: 10px !important;
    margin: 0 !important;
}
div[data-testid="stExpander"] {
    background-color: var(--apple-surface) !important;
    border-radius: var(--apple-radius-md) !important;
    border: 1px solid var(--apple-separator) !important;
    box-shadow: var(--shadow-xs) !important;
    overflow: hidden;
    transition: border-color var(--dur-hover) var(--ease-out-expo),
                box-shadow var(--dur-hover) var(--ease-out-expo);
}
div[data-testid="stExpander"] summary {
    font-weight: 600 !important;
    font-size: 14px !important;
    color: var(--apple-text-main) !important;
    padding: 13px 16px !important;
}
@media (hover: hover) and (pointer: fine) {
    div[data-testid="stExpander"]:hover {
        border-color: var(--apple-separator-strong) !important;
        box-shadow: var(--shadow-sm) !important;
    }
}

/* ─── Inputs & Focus Ring (WCAG AA) ─── */
.stTextInput input,
div[data-testid="stNumberInput"] input {
    background-color: var(--apple-surface) !important;
    border: 1px solid var(--apple-separator) !important;
    border-radius: var(--apple-radius-sm) !important;
    color: var(--apple-text-main) !important;
    font-size: 14.5px !important;
    font-weight: 400 !important;
    height: 40px !important;
    padding: 0 12px !important;
    transition: border-color var(--dur-hover) ease, box-shadow var(--dur-hover) ease;
}
.stTextInput input:focus,
div[data-testid="stNumberInput"] input:focus {
    border-color: var(--apple-blue) !important;
    box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.18) !important;
    outline: none !important;
}
.stTextInput input::placeholder {
    color: var(--apple-text-placeholder) !important;
}

.stTextArea textarea {
    background-color: var(--apple-surface) !important;
    border: 1px solid var(--apple-separator) !important;
    border-radius: var(--apple-radius-sm) !important;
    color: var(--apple-text-main) !important;
    font-size: 14px !important;
    line-height: 1.6 !important;
    padding: 10px 12px !important;
    transition: border-color var(--dur-hover) ease, box-shadow var(--dur-hover) ease;
}
.stTextArea textarea:focus {
    border-color: var(--apple-blue) !important;
    box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.18) !important;
}
div[data-baseweb="textarea"][disabled] textarea,
.stTextArea textarea:disabled {
    background-color: var(--apple-surface-2) !important;
    color: var(--apple-text-secondary) !important;
    cursor: default !important;
}

/* ─── Selectbox ─── */
.stSelectbox div[data-baseweb="select"] {
    background-color: var(--apple-surface) !important;
    border: 1px solid var(--apple-separator) !important;
    border-radius: var(--apple-radius-sm) !important;
    font-size: 14.5px !important;
}
.stSelectbox div[data-baseweb="select"]:focus-within {
    border-color: var(--apple-blue) !important;
    box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.18) !important;
}

/* ─── Labels & Typography ─── */
.stTextInput label, .stSelectbox label, .stFileUploader label,
.stTextArea label, .stNumberInput label, .stSlider label {
    font-size: 13px !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
    color: var(--apple-text-secondary) !important;
    margin-bottom: 4px !important;
}
.stMarkdown p strong {
    color: var(--apple-text-main) !important;
}
.stMarkdown p {
    color: var(--apple-text-secondary);
    font-size: 14px !important;
    line-height: 1.55;
}
h1, h2, h3, h4 {
    letter-spacing: -0.025em !important;
    color: var(--apple-text-main);
}

/* ─── Checkboxes ─── */
div[data-testid="stCheckbox"] label span,
div[data-testid="stCheckbox"] label div,
div[data-testid="stCheckbox"] label p {
    color: var(--apple-text-main) !important;
    font-size: 14px !important;
    font-weight: 500 !important;
}

/* ─── File Uploader ─── */
div[data-testid="stFileUploadDropzone"] {
    background-color: var(--apple-surface) !important;
    border: 2px dashed var(--apple-separator-strong) !important;
    border-radius: var(--apple-radius-md) !important;
    transition: border-color var(--dur-hover) ease, background-color var(--dur-hover) ease;
}
div[data-testid="stFileUploadDropzone"]:hover {
    border-color: var(--apple-blue) !important;
    background-color: var(--apple-blue-light) !important;
}

/* ─── Buttons (Press vs Hover fixed) ─── */
.stButton > button,
.stFormSubmitButton > button {
    min-height: 40px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    font-family: var(--font-apple) !important;
    border-radius: 980px !important;
    cursor: pointer;
    transition:
        background-color var(--dur-hover) var(--ease-out-expo),
        border-color var(--dur-hover) var(--ease-out-expo),
        box-shadow var(--dur-hover) var(--ease-out-expo),
        transform var(--dur-press) var(--ease-out-expo) !important;
    letter-spacing: -0.01em !important;
}

.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
    background-color: var(--apple-blue) !important;
    color: #ffffff !important;
    border: 1px solid transparent !important;
    box-shadow: 0 1px 3px rgba(0, 113, 227, 0.28) !important;
}
@media (hover: hover) and (pointer: fine) {
    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button[kind="primary"]:hover {
        background-color: var(--apple-blue-hover) !important;
        box-shadow: 0 4px 12px rgba(0, 113, 227, 0.30) !important;
    }
}

.stButton > button[kind="secondary"],
.stFormSubmitButton > button[kind="secondary"] {
    background-color: var(--apple-surface) !important;
    color: var(--apple-text-main) !important;
    border: 1px solid var(--apple-separator-strong) !important;
    box-shadow: var(--shadow-xs) !important;
}
@media (hover: hover) and (pointer: fine) {
    .stButton > button[kind="secondary"]:hover,
    .stFormSubmitButton > button[kind="secondary"]:hover {
        background-color: var(--apple-surface-hover) !important;
        border-color: rgba(15, 23, 42, 0.25) !important;
    }
}

.stButton > button:active,
.stFormSubmitButton > button:active {
    transform: scale(0.97) !important;
}
.stButton > button:focus-visible,
.stFormSubmitButton > button:focus-visible {
    outline: 2px solid var(--apple-blue) !important;
    outline-offset: 2px !important;
}

/* Sidebar buttons */
section[data-testid="stSidebar"] .stButton > button {
    min-height: 36px !important;
    height: 36px !important;
    font-size: 13px !important;
    border-radius: var(--apple-radius-sm) !important;
}

/* ─── Sidebar Navigation ─── */
section[data-testid="stSidebar"] {
    background-color: #f8f9fb !important;
    border-right: 1px solid var(--apple-separator) !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {
    gap: 3px !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] label {
    font-size: 13.5px !important;
    font-weight: 500 !important;
    color: var(--apple-text-secondary) !important;
    padding: 7px 10px !important;
    border-radius: var(--apple-radius-sm) !important;
    transition: background-color var(--dur-hover) ease, color var(--dur-hover) ease !important;
    margin: 0 !important;
}
@media (hover: hover) and (pointer: fine) {
    section[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
        background-color: rgba(0, 113, 227, 0.06) !important;
        color: var(--apple-text-main) !important;
    }
}
section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background-color: var(--apple-blue-light) !important;
    color: var(--apple-blue) !important;
    font-weight: 600 !important;
}

/* ─── Progress Bar ─── */
.apple-progress-container {
    background-color: #e5e7eb;
    border-radius: 980px;
    height: 6px;
    width: 100%;
    overflow: hidden;
    margin-top: 8px;
    margin-bottom: 20px;
}
.apple-progress-bar {
    background: linear-gradient(90deg, var(--apple-blue), #38bdf8);
    height: 100%;
    border-radius: 980px;
    transition: width 0.45s var(--ease-out-expo);
}

/* ─── Node Cards (Existing workflow screens) ─── */
.node-card {
    background-color: var(--apple-surface);
    border: 1px solid var(--apple-separator);
    border-radius: var(--apple-radius-md);
    padding: 14px 18px;
    margin-bottom: 10px;
    box-shadow: var(--shadow-xs);
    display: flex;
    align-items: center;
    gap: 14px;
    animation: qcFadeSlideIn var(--dur-enter) var(--ease-out-expo) both;
    transition: border-color var(--dur-hover) ease, box-shadow var(--dur-hover) ease, opacity var(--dur-hover) ease;
}
.node-card.pending { opacity: 0.48; filter: grayscale(70%); }
.node-card.running {
    border-left: 4px solid var(--apple-blue);
    background: linear-gradient(135deg, #f0f7ff 0%, #ffffff 100%);
    animation: qcPulseBorder 2s ease-in-out infinite;
}
.node-card.success { border-left: 4px solid var(--apple-green); }
.node-card.error { border-left: 4px solid var(--apple-red); background-color: var(--apple-red-bg); }
.node-icon { font-size: 22px; flex-shrink: 0; }
.node-text-title { font-weight: 600; font-size: 14px; color: var(--apple-text-main); margin-bottom: 2px; letter-spacing: -0.01em; }
.node-text-desc { font-size: 12.5px; color: var(--apple-text-muted); line-height: 1.4; }

/* ─── Translated Box ─── */
.translated-box {
    background-color: var(--apple-surface);
    padding: 20px;
    border-radius: var(--apple-radius-lg);
    border: 1px solid var(--apple-separator);
    box-shadow: var(--shadow-sm);
    font-size: 14px;
    max-height: 400px;
    overflow-y: auto;
    white-space: pre-wrap;
    margin-bottom: 20px;
    color: var(--apple-text-main);
    line-height: 1.65;
}

/* ─── Enterprise UI Helpers (KPI, Badges, Empty State) ─── */
.qc-kpi-card {
    background: var(--apple-surface);
    border: 1px solid var(--apple-separator);
    border-radius: var(--apple-radius-md);
    padding: 14px 16px;
    box-shadow: var(--shadow-xs);
    animation: qcFadeSlideIn var(--dur-enter) var(--ease-out-expo) both;
}
.qc-kpi-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--apple-text-muted);
    margin-bottom: 4px;
}
.qc-kpi-value {
    font-size: 22px;
    font-weight: 700;
    color: var(--apple-text-main);
    letter-spacing: -0.02em;
    line-height: 1.2;
}
.qc-kpi-sub {
    font-size: 11.5px;
    color: var(--apple-text-muted);
    margin-top: 4px;
}

.qc-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    border-radius: 980px;
    padding: 3px 10px;
    font-size: 11.5px;
    font-weight: 600;
    white-space: nowrap;
}
.qc-badge-blue { background: var(--apple-blue-light); color: var(--apple-blue); }
.qc-badge-green { background: var(--apple-green-bg); color: var(--apple-green); }
.qc-badge-red { background: var(--apple-red-bg); color: var(--apple-red); }
.qc-badge-amber { background: var(--apple-orange-bg); color: var(--apple-orange); }
.qc-badge-neutral { background: #f3f4f6; color: var(--apple-text-secondary); }

.qc-empty-state {
    background: var(--apple-surface);
    border: 1px dashed var(--apple-separator-strong);
    border-radius: var(--apple-radius-md);
    padding: 28px 20px;
    text-align: center;
    color: var(--apple-text-muted);
    animation: qcFadeSlideIn var(--dur-enter) var(--ease-out-expo) both;
}

.qc-version-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #eef2f6;
    color: var(--apple-text-secondary);
    border: 1px solid var(--apple-separator);
    border-radius: 980px;
    padding: 3px 10px;
    font-size: 11.5px;
    font-weight: 600;
}

/* ─── Alerts / Tabs / DataEditor / Scrollbar ─── */
div[data-testid="stAlert"] {
    border-radius: var(--apple-radius-sm) !important;
    font-size: 14px !important;
    animation: qcFadeSlideIn var(--dur-enter) var(--ease-out-expo) both;
}
div[data-testid="stDataEditor"] {
    border-radius: var(--apple-radius-sm) !important;
    overflow: hidden;
    border: 1px solid var(--apple-separator) !important;
}
div[data-testid="stTabs"] button {
    font-size: 14px !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
}
div[data-testid="stTabs"] [data-baseweb="tab-panel"] {
    animation: qcFadeSlideIn 180ms var(--ease-out-expo) both;
}
hr {
    border-color: var(--apple-separator) !important;
    margin: 14px 0 !important;
}
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 10px; }
::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

/* Card Action Column Fix */
div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
    display: flex !important;
    flex-direction: column !important;
    justify-content: flex-start !important;
}
div[data-testid="column"]:last-child .stButton > button {
    min-height: 38px !important;
    height: auto !important;
    padding: 6px 12px !important;
}

/* ─── Reduced Motion (Accessibility) ─── */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }
    .stButton > button:active,
    .stFormSubmitButton > button:active {
        transform: none !important;
    }
}
</style>
"""


def inject_theme() -> None:
    """Inject global design system and motion tokens into Streamlit."""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


def render_kpi_card(label: str, value: str, sub: str = "") -> str:
    """Return HTML markup for a compact KPI summary card."""
    sub_html = f"<div class='qc-kpi-sub'>{sub}</div>" if sub else ""
    return (
        f"<div class='qc-kpi-card'>"
        f"<div class='qc-kpi-label'>{label}</div>"
        f"<div class='qc-kpi-value'>{value}</div>"
        f"{sub_html}"
        f"</div>"
    )
