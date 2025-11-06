# NOTE: This is called via Jac py_module. Keep imports local to speed up load.
import os, re, json, tempfile, shutil, subprocess, pathlib, time
from datetime import datetime
from typing import Optional, Dict, Any, List, Generator

import requests
from dotenv import load_dotenv
import google.generativeai as genai

# ------------ Env & Gemini ------------
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

# Configure Gemini once
genai.configure(api_key=GEMINI_API_KEY)

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")  # fast/cheap + streams well
DOCS_MODEL    = os.getenv("GEMINI_DOCS_MODEL", "gemini-2.0-pro") # better for longer docs

def _model(model_name: Optional[str] = None, temperature: float = 0.6) -> genai.GenerativeModel:
    """
    Return a configured Gemini model. model_name defaults to DEFAULT_MODEL.
    """
    name = model_name or DEFAULT_MODEL
    safety = None  # customize if you need specific safety settings
    generation_config = {
        "temperature": temperature,
        "top_p": 0.9,
        "top_k": 40,
        "max_output_tokens": 2048,
    }
    return genai.GenerativeModel(model_name=name, safety_settings=safety, generation_config=generation_config)

# ------------ URL fetching ------------
def fetch_url_content(url: str) -> Dict[str, Any]:
    try:
        headers = {
            "User-Agent": "CodebaseGenius/1.0 (+https://example.local)"
        }
        r = requests.get(url, timeout=20, headers=headers)
        r.raise_for_status()
        return {"success": True, "content": r.text}
    except requests.RequestException as e:
        return {"success": False, "error": f"Failed to fetch URL: {e}"}

# ------------ Documentation generation (non-stream) ------------
def generate_docs_from_url(url: str) -> Dict[str, Any]:
    try:
        content_result = fetch_url_content(url)
        if not content_result["success"]:
            return {"success": False, "error": content_result["error"]}

        content = content_result["content"]
        model = _model(DOCS_MODEL, temperature=0.35)

        prompt = f"""You are a senior technical writer. Analyze the web content at: {url}

Create a clean, developer-friendly Markdown document with these sections if applicable:
1. Overview and Purpose
2. Key Features and Functionality
3. Architecture / Data Flow
4. Installation and Setup
5. Usage Examples
6. API Reference (endpoints/params) or CLI Reference
7. Configuration (env vars, secrets)
8. Dependencies and Requirements
9. Troubleshooting
10. Best Practices and Security Notes

Write concise, actionable docs. Avoid marketing fluff.

--- BEGIN SOURCE (truncated if long) ---
{content[:100_000]}
--- END SOURCE ---
"""
        resp = model.generate_content(prompt)
        text = (resp.text or "").strip()
        if not text:
            return {"success": False, "error": "No response from Gemini"}

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        fname = f"docs_{ts}.md"
        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, fname)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)

        return {"success": True, "content": text, "file_path": out_path, "file_name": fname}
    except Exception as e:
        return {"success": False, "error": f"Documentation generation failed: {e}"}

# ------------ Documentation generation (streaming) ------------
def stream_docs_from_url(url: str) -> Generator[str, None, None]:
    """
    Stream Markdown chunks from Gemini as they arrive.
    """
    content_result = fetch_url_content(url)
    if not content_result["success"]:
        yield f"[ERROR] {content_result['error']}"
        return

    content = content_result["content"]
    model = _model(DOCS_MODEL, temperature=0.35)

    prompt = f"""You are a senior technical writer. Produce concise, high-signal Markdown docs for {url}.
(Overview, Features, Architecture, Install, Usage, API, Config, Dependencies, Troubleshooting, Best Practices)
Avoid fluff; use headings and code blocks where useful.

--- BEGIN SOURCE (truncated) ---
{content[:100_000]}
--- END SOURCE ---
"""

    try:
        response = model.generate_content(prompt, stream=True)
        for chunk in response:
            if hasattr(chunk, "text") and chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"[ERROR] Streaming failed: {e}"

# ------------ Chat (non-stream) ------------
def chat_with_llm(message: str, chat_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    try:
        model = _model(DEFAULT_MODEL, temperature=0.6)

        system = (
            "You are a helpful AI assistant for software engineering and documentation. "
            "Be precise, cite assumptions, and prefer stepwise clarity. If unsure, say so briefly."
        )

        history_txt = ""
        if chat_history:
            # Normalize chat_history from Streamlit (role/content pairs)
            keep = chat_history[-10:]
            for m in keep:
                role = m.get("role", "user")
                content = m.get("content", "")
                history_txt += f"{role}: {content}\n"

        prompt = f"{system}\n\n{history_txt}\nuser: {message}\nassistant:"
        resp = model.generate_content(prompt)
        text = (resp.text or "").strip()
        if not text:
            return {"success": False, "error": "No response generated"}
        return {"success": True, "response": text}
    except Exception as e:
        return {"success": False, "error": f"Chat failed: {e}"}

# ------------ Chat (streaming) ------------
def stream_chat_with_llm(message: str, chat_history: Optional[List[Dict[str, str]]] = None) -> Generator[str, None, None]:
    model = _model(DEFAULT_MODEL, temperature=0.6)
    system = (
        "You are a helpful AI assistant for software engineering and documentation. "
        "Be precise, cite assumptions, and prefer stepwise clarity. If unsure, say so."
    )

    history_txt = ""
    if chat_history:
        keep = chat_history[-10:]
        for m in keep:
            role = m.get("role", "user")
            content = m.get("content", "")
            history_txt += f"{role}: {content}\n"

    prompt = f"{system}\n\n{history_txt}\nuser: {message}\nassistant:"
    try:
        resp = model.generate_content(prompt, stream=True)
        for chunk in resp:
            if hasattr(chunk, "text") and chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"[ERROR] {e}"



def chat_with_llm_ex(
    message: str,
    history_text: Optional[str] = None,
    system_prompt: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.6,
    top_p: float = 0.9,
    top_k: int = 40,
) -> Dict[str, Any]:
    """
    Gemini chat that accepts explicit runtime config and a preformatted history_text.
    Returns {"success": bool, "response": str, "usage": {...}} on success.
    """
    try:
        # Pick model (falls back to your DEFAULT_MODEL)
        name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        # Build model with ad-hoc generation config
        genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
        model = genai.GenerativeModel(
            model_name=name,
            generation_config={
                "temperature": float(temperature),
                "top_p": float(top_p),
                "top_k": int(top_k),
                "max_output_tokens": 2048,
            },
        )

        sys_preamble = (
            system_prompt.strip()
            if system_prompt
            else (
                "You are a precise, concise software/dev assistant. "
                "Cite assumptions briefly and prefer stepwise clarity. "
                "If unsure, say so."
            )
        )

        history_txt = f"\n{history_text.strip()}\n" if history_text else ""
        prompt = f"{sys_preamble}\n{history_txt}\nuser: {message}\nassistant:"

        resp = model.generate_content(prompt)
        txt = (getattr(resp, "text", "") or "").strip()
        if not txt:
            return {"success": False, "error": "No response generated"}
        # Usage (best-effort; fields vary by SDK version)
        usage = {}
        try:
            usage = {
                "input_tokens": getattr(resp, "usage_metadata", {}).get("prompt_token_count"),
                "output_tokens": getattr(resp, "usage_metadata", {}).get("candidates_token_count"),
                "total_tokens": getattr(resp, "usage_metadata", {}).get("total_token_count"),
                "model": name,
                "temperature": temperature,
                "top_p": top_p,
                "top_k": top_k,
            }
        except Exception:
            pass

        return {"success": True, "response": txt, "usage": usage}
    except Exception as e:
        return {"success": False, "error": f"chat_with_llm_ex failed: {e}"}