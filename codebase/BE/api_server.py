import os
import asyncio
from typing import Optional
from fastapi import FastAPI, Query, Response
from fastapi.responses import PlainTextResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from py_modules import codeops  # your existing Gemini helpers

API_TITLE = "Codebase Genius API"
app = FastAPI(title=API_TITLE)

# CORS - allow local tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True, "service": API_TITLE}

# -------- Chat (non-stream) --------
@app.get("/chat")
def chat(message: str = Query(..., min_length=1)):
    out = codeops.chat_with_llm(message)
    if not out.get("success"):
        return JSONResponse({"error": out.get("error", "unknown")}, status_code=500)
    return {"response": out["response"]}

# -------- Chat (stream) --------
@app.get("/chat/stream")
def chat_stream(message: str = Query(..., min_length=1)):
    gen = codeops.stream_chat_with_llm(message)

    async def agen():
        for chunk in gen:
            # yield small pieces so Streamlit updates immediately
            yield chunk
            await asyncio.sleep(0)  # cooperative

    return StreamingResponse(agen(), media_type="text/plain")

# -------- Docs (non-stream) --------
@app.get("/docs")
def docs(url: str = Query(..., min_length=4)):
    out = codeops.generate_docs_from_url(url)
    if not out.get("success"):
        return JSONResponse({"error": out.get("error", "unknown")}, status_code=500)
    return {"file_name": out["file_name"], "content": out["content"]}

# -------- Docs (stream) --------
@app.get("/docs/stream")
def docs_stream(url: str = Query(..., min_length=4)):
    gen = codeops.stream_docs_from_url(url)

    async def agen():
        for chunk in gen:
            yield chunk
            await asyncio.sleep(0)

    return StreamingResponse(agen(), media_type="text/plain")
