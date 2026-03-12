"""
FastAPI route handlers.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from config import (
    DEFAULT_MODEL,
    PROVIDER_MODEL_DEFAULTS,
    SERVER_KEYS,
    resolve_api_key,
)
import mcp_client
from models import AskRequest, AskResponse, ModelsRequest
from orchestrator import orchestrate_ask
from providers import PROVIDERS, ProviderAuthError
from sessions import get_or_create_session

router = APIRouter()

SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.txt").read_text(
    encoding="utf-8"
)


@router.get("/health")
@router.get("/api/health")
def health():
    return {"status": "ok"}


@router.get("/api/defaults")
def defaults():
    """Tell the frontend whether a server-side API key is available."""
    for prov in ["anthropic", "openai"]:
        if prov in SERVER_KEYS:
            model = DEFAULT_MODEL or PROVIDER_MODEL_DEFAULTS.get(prov, "")
            return {
                "has_server_key": True,
                "provider": prov,
                "model": model,
            }
    return {"has_server_key": False, "provider": None, "model": None}


@router.post("/api/models")
async def list_models(req: ModelsRequest):
    """Fetch available models from the selected provider."""
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


@router.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    provider = PROVIDERS.get(req.provider)
    if not provider:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider: {req.provider}. Available: {', '.join(PROVIDERS)}",
        )

    api_key = resolve_api_key(req.provider, req.api_key)
    session_id, messages = get_or_create_session(req.session_id)

    messages.append({"role": "user", "content": req.question})

    # Build system prompt with MCP resources appended
    system_prompt = SYSTEM_PROMPT.format(row_count="764,830")
    if mcp_client.data_dictionary:
        system_prompt += f"\n\n---\n\n{mcp_client.data_dictionary}"
    if mcp_client.installed_packages:
        system_prompt += f"\n\n---\n\n{mcp_client.installed_packages}"

    final_text, final_image = await orchestrate_ask(
        provider=provider,
        api_key=api_key,
        model=req.model,
        system_prompt=system_prompt,
        messages=messages,
    )

    return AskResponse(text=final_text, image=final_image, session_id=session_id)
