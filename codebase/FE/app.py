# codebase/FE/app.py

import os
import time
import json
import requests
import streamlit as st
from pathlib import Path
from contextlib import contextmanager
from streamlit.components.v1 import html as components_html

# --------------------------
# Page setup
# --------------------------
st.set_page_config(
    page_title="Codebase Genius",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.title("🧠 Codebase Genius – Documentation Assistant")

# --------------------------
# Config / Endpoints
# --------------------------
JASECI_BASE = os.getenv("JASECI_BASE", "http://localhost:8000")  # Jaseci walker server
API_BASE    = os.getenv("API_BASE", "http://localhost:8001")     # FastAPI AI server

GENIUS_WALKER = f"{JASECI_BASE}/walker/run"             # generic walker endpoint
GET_ART       = f"{JASECI_BASE}/walker/get_last_artifact"
GET_SESSIONS  = f"{JASECI_BASE}/walker/get_all_sessions"  # optional health/info if available

CHAT_API      = f"{API_BASE}/chat"
CHAT_STREAM   = f"{API_BASE}/chat/stream"
DOCS_API      = f"{API_BASE}/docs"
DOCS_STREAM   = f"{API_BASE}/docs/stream"
HEALTH_API    = f"{API_BASE}/health"

# --------------------------
# Helpers
# --------------------------
DEFAULT_TIMEOUT = (5, 60)  # (connect, read) seconds


def _fmt_exc(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"


def get_json(url: str, params=None, timeout=DEFAULT_TIMEOUT):
    """GET and parse JSON; return (data, error_str)."""
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.JSONDecodeError:
        return None, "Response was not valid JSON"
    except requests.exceptions.RequestException as e:
        return None, _fmt_exc(e)


def post_json(url: str, payload=None, timeout=DEFAULT_TIMEOUT):
    """POST JSON; return (data, error_str)."""
    try:
        r = requests.post(url, json=(payload or {}), timeout=timeout)
        r.raise_for_status()
        return r.json(), None
    except requests.exceptions.JSONDecodeError:
        return None, "Response was not valid JSON"
    except requests.exceptions.RequestException as e:
        return None, _fmt_exc(e)


@contextmanager
def _stream(url: str, params=None, timeout=DEFAULT_TIMEOUT):
    """Context manager to stream text/plain responses chunk-by-chunk."""
    try:
        with requests.get(url, params=params, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            yield r.iter_content(chunk_size=None)
    except requests.exceptions.RequestException as e:
        # Propagate as a RuntimeError to handle uniformly
        raise RuntimeError(_fmt_exc(e)) from e


def stream_text(url: str, params=None, timeout=DEFAULT_TIMEOUT):
    """Generator yielding decoded text chunks (str)."""
    with _stream(url, params=params, timeout=timeout) as chunks:
        for raw in chunks:
            if not raw:
                continue
            yield raw.decode("utf-8", errors="ignore")


def show_status_badge(ok: bool, label: str):
    color = "#16a34a" if ok else "#ef4444"
    icon = "🟢" if ok else "🔴"
    st.markdown(
        f"<span style='font-size:0.95rem'>{icon} "
        f"<span style='background:{color}20;border:1px solid {color};padding:2px 8px;"
        f"border-radius:999px;color:{color}'>{label}</span></span>",
        unsafe_allow_html=True,
    )


def check_api_health():
    data, err = get_json(HEALTH_API, timeout=(3, 6))
    return err is None


def check_jaseci_alive():
    # Try a lightweight walker (if not present, just consider it "unknown" not fatal)
    data, err = post_json(GET_SESSIONS, timeout=(3, 6))
    # If endpoint doesn't exist, fall back to GET_ART with empty payload
    if err:
        data2, err2 = post_json(GET_ART, payload={}, timeout=(3, 6))
        return err2 is None
    return True


# --------------------------
# Session state
# --------------------------
st.session_state.setdefault("messages", [])        # chat messages
st.session_state.setdefault("doc_content", None)   # last generated markdown (str)
st.session_state.setdefault("doc_file_name", None) # filename for download


# --------------------------
# Sidebar
# --------------------------
with st.sidebar:
    st.header("⚙️ Settings & Status")

    colA, colB = st.columns(2)
    with colA:
        api_ok = check_api_health()
        show_status_badge(api_ok, "AI API :8001")
    with colB:
        jac_ok = check_jaseci_alive()
        show_status_badge(jac_ok, "Jaseci :8000")

    st.caption("Tip: Keep both backends running. AI API serves /chat and /docs; Jaseci serves walker endpoints.")

    st.markdown("---")
    st.header("🧾 Documentation")
    repo_url = st.text_input(
        "URL to analyze (GitHub repo or any webpage)",
        placeholder="https://github.com/owner/repo or https://example.com",
    )
    run_btn = st.button("Generate Documentation (stream)")

    st.markdown("---")
    sel_repo = st.text_input("Preview saved doc by name (optional)")
    load_btn = st.button("Load Saved Doc")


# --------------------------
# Tabs
# --------------------------
tab1, tab2 = st.tabs(["💬 Chat", "📄 Documentation"])

# ==========================
# Chat Tab
# ==========================
with tab1:
    st.subheader("Real-time Chat with Gemini")

    # Render history
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # Chat input
    if prompt := st.chat_input("Ask me anything…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            acc = []

            try:
                for chunk in stream_text(CHAT_STREAM, params={"message": prompt}, timeout=(5, 60)):
                    acc.append(chunk)
                    placeholder.markdown("".join(acc))
            except RuntimeError as e:
                st.error(f"Cannot reach {CHAT_STREAM}. Is the API server running on port 8001?\n\nDetails: {e}")
            else:
                final = "".join(acc).strip()
                if final.startswith("[ERROR]"):
                    st.error(final)
                else:
                    st.session_state.messages.append({"role": "assistant", "content": final})

    # Clear chat
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()

# ==========================
# Docs Tab
# ==========================
with tab2:
    st.subheader("Documentation Generator (Streaming)")

    if run_btn and repo_url:
        with st.spinner("Generating documentation…"):
            area = st.empty()
            acc = []
            start = time.time()

            try:
                for chunk in stream_text(DOCS_STREAM, params={"url": repo_url}, timeout=(5, 180)):
                    acc.append(chunk)
                    area.markdown("".join(acc))
            except RuntimeError as e:
                st.error(f"Cannot reach {DOCS_STREAM}. Is the API server running on port 8001?\n\nDetails: {e}")
            else:
                md = "".join(acc).strip()
                if md.startswith("[ERROR]"):
                    st.error(md)
                elif not md:
                    st.warning("No content returned from AI.")
                else:
                    st.session_state.doc_content = md
                    st.session_state.doc_file_name = "documentation.md"
                    st.success(f"Documentation generated in {time.time()-start:.1f}s")
                    st.download_button(
                        "⬇️ Download documentation.md",
                        md.encode("utf-8"),
                        file_name="documentation.md",
                        mime="text/markdown",
                    )

    # Q&A over generated doc
    if st.session_state.doc_content:
        st.markdown("---")
        st.markdown("### Current Documentation Preview")
        st.markdown(st.session_state.doc_content)

        st.markdown("### Ask a question about this doc")
        q = st.text_input("Question about the current documentation")
        if q:
            context_msg = (
                f"Use this documentation context to answer briefly and precisely:\n\n"
                f"{st.session_state.doc_content}\n\n"
                f"Question: {q}"
            )
            with st.spinner("Answering…"):
                area = st.empty()
                acc = []
                try:
                    for chunk in stream_text(CHAT_STREAM, params={"message": context_msg}, timeout=(5, 90)):
                        acc.append(chunk)
                        area.markdown("".join(acc))
                except RuntimeError as e:
                    st.error(f"Cannot reach {CHAT_STREAM}. Is the API server running on port 8001?\n\nDetails: {e}")

# ==========================
# Load saved artifact via walker
# ==========================
if load_btn:
    with st.spinner("Loading saved artifact…"):
        data, err = post_json(GET_ART, payload={"repo_name": sel_repo} if sel_repo else {}, timeout=(5, 30))
        if err:
            st.error(f"Walker error: {err}")
        else:
            reports = data.get("reports", [])
            if reports and isinstance(reports[0], dict):
                path = reports[0].get("path", "docs.md")
                content = reports[0].get("content", "")
                st.subheader(f"📄 {path}")
                st.download_button("⬇️ Download docs.md", content.encode("utf-8"), file_name="docs.md")
                st.markdown("---")
                st.markdown(content)
                st.session_state.doc_content = content
                st.session_state.doc_file_name = "docs.md"
            else:
                st.info("No artifact found.")

# Small auto-scroll helper for nicer streaming UX
components_html(
    "<script>setTimeout(()=>{window.scrollTo(0,document.body.scrollHeight)},120)</script>",
    height=0
)
