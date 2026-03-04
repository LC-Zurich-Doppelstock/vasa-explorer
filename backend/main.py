"""
Vasaloppet Q&A Backend

Orchestrates between the frontend, LLM providers, and the isolated code executor.
Maintains per-session conversation history for multi-turn interactions.
"""

import os
import re
import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from providers import PROVIDERS, ProviderAuthError, ProviderAPIError

app = FastAPI(title="Vasaloppet Q&A Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
EXECUTOR_URL = os.environ.get("EXECUTOR_URL", "http://executor:9000")
MAX_RETRIES = 2
SESSION_TTL = 1800  # 30 minutes

# Server-side API keys (optional). When present the frontend can use the app
# without the user having to provide their own key.
SERVER_KEYS: dict[str, str] = {}
for _prov, _env in [("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY")]:
    _val = os.environ.get(_env, "").strip()
    if _val:
        SERVER_KEYS[_prov] = _val

# Sentinel value the frontend sends to indicate "use the server key".
SERVER_KEY_SENTINEL = "__server__"


def resolve_api_key(provider_name: str, request_key: str) -> str:
    """Return the actual API key to use.

    If the request carries the sentinel (or is empty) and a server key exists
    for this provider, use the server key. Otherwise use whatever the request
    sent. Raises HTTPException if nothing is available.
    """
    if request_key and request_key != SERVER_KEY_SENTINEL:
        return request_key
    server_key = SERVER_KEYS.get(provider_name)
    if server_key:
        return server_key
    raise HTTPException(
        status_code=400,
        detail="API key is required. Please configure it in Settings.",
    )


# ---------------------------------------------------------------------------
# Session store: session_id -> { "messages": [...], "last_active": timestamp }
# ---------------------------------------------------------------------------
sessions: dict[str, dict] = {}

from pathlib import Path

SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.txt").read_text(
    encoding="utf-8"
)


def cleanup_sessions():
    """Remove sessions older than SESSION_TTL."""
    now = time.time()
    expired = [
        sid for sid, s in sessions.items() if now - s["last_active"] > SESSION_TTL
    ]
    for sid in expired:
        del sessions[sid]


def get_or_create_session(session_id: str | None) -> tuple[str, list]:
    """Return (session_id, messages) for the given or a new session."""
    cleanup_sessions()
    if session_id and session_id in sessions:
        sessions[session_id]["last_active"] = time.time()
        return session_id, sessions[session_id]["messages"]
    sid = session_id or str(uuid.uuid4())
    sessions[sid] = {"messages": [], "last_active": time.time()}
    return sid, sessions[sid]["messages"]


def extract_code_block(text: str) -> str | None:
    """Extract Python code from a fenced code block in the response."""
    pattern = r"```python\s*\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


async def execute_code(code: str) -> dict:
    """Send code to the executor container and return the result."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{EXECUTOR_URL}/execute", json={"code": code})
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    question: str
    session_id: str | None = None
    provider: str = "anthropic"
    api_key: str = ""
    model: str = "claude-sonnet-4-20250514"


class AskResponse(BaseModel):
    text: str
    image: str | None = None
    session_id: str


class ModelsRequest(BaseModel):
    provider: str = "anthropic"
    api_key: str = ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/defaults")
def defaults():
    """Tell the frontend whether a server-side API key is available.

    Returns the first provider that has a server key so the frontend can
    pre-select it and skip the settings modal. The actual key is never exposed.
    """
    for prov in ["anthropic", "openai"]:
        if prov in SERVER_KEYS:
            return {
                "has_server_key": True,
                "provider": prov,
                "model": (
                    "claude-sonnet-4-20250514" if prov == "anthropic" else "gpt-4o"
                ),
            }
    return {"has_server_key": False, "provider": None, "model": None}


@app.post("/api/models")
async def list_models(req: ModelsRequest):
    """Fetch available models from the selected provider using the user's key."""
    provider = PROVIDERS.get(req.provider)
    if not provider:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider: {req.provider}. Available: {', '.join(PROVIDERS)}",
        )

    api_key = resolve_api_key(req.provider, req.api_key)

    try:
        models = await provider.list_models(api_key)
        return {"models": models}
    except ProviderAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch models: {e}")


@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    provider = PROVIDERS.get(req.provider)
    if not provider:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider: {req.provider}. Available: {', '.join(PROVIDERS)}",
        )

    api_key = resolve_api_key(req.provider, req.api_key)
    session_id, messages = get_or_create_session(req.session_id)

    # Add the user's question
    messages.append({"role": "user", "content": req.question})

    system_prompt = SYSTEM_PROMPT.format(row_count="764,830")

    # Retry loop: ask LLM, execute code if needed, retry on errors
    final_text = ""
    final_image = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            assistant_text = await provider.chat(
                api_key=api_key,
                model=req.model,
                system=system_prompt,
                messages=messages,
            )
        except ProviderAuthError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except ProviderAPIError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"LLM request failed: {e}")

        code = extract_code_block(assistant_text)

        if code is None:
            # LLM answered directly without code
            messages.append({"role": "assistant", "content": assistant_text})
            final_text = assistant_text
            break

        # Execute the code
        try:
            result = await execute_code(code)
        except Exception as e:
            messages.append({"role": "assistant", "content": assistant_text})
            error_msg = f"Failed to reach the code executor: {e}"
            messages.append(
                {
                    "role": "user",
                    "content": f"Error executing code:\n{error_msg}\nPlease fix the code.",
                }
            )
            final_text = f"Execution error: {error_msg}"
            continue

        if result.get("error"):
            # Code errored — feed traceback back to the LLM
            messages.append({"role": "assistant", "content": assistant_text})
            error_feedback = (
                f"The code produced an error:\n```\n{result['error']}\n```\n"
                "Please fix the code and try again."
            )
            messages.append({"role": "user", "content": error_feedback})
            final_text = f"Code error (attempt {attempt + 1}): {result['error']}"
            continue

        # Success
        messages.append({"role": "assistant", "content": assistant_text})

        stdout = result.get("stdout", "").strip()
        image = result.get("image")

        # Build a clean text response from the code execution output only.
        # We discard the LLM's surrounding text because it may contain
        # hallucinated answers not grounded in the actual data.
        if stdout:
            final_text = stdout
        else:
            final_text = "Done."
        final_image = f"data:image/png;base64,{image}" if image else None

        # Add a summary of the execution result to the conversation so the LLM
        # knows what happened for follow-up questions
        exec_summary = ""
        if stdout:
            exec_summary += f"Code output:\n{stdout}\n"
        if image:
            exec_summary += "[A figure was generated and displayed to the user.]\n"
        if exec_summary:
            messages.append(
                {
                    "role": "user",
                    "content": f"[System: the code executed successfully.]\n{exec_summary}",
                }
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": "Understood, the results have been shown to the user.",
                }
            )

        break

    return AskResponse(text=final_text, image=final_image, session_id=session_id)
