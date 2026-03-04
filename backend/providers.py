"""
LLM Provider abstraction.

Each provider implements model listing and chat completion using raw httpx,
so the backend has zero SDK dependencies for LLM calls.
"""

from abc import ABC, abstractmethod

import httpx
import ssl

# Shared SSL context — disables verification for Docker / corporate proxy envs.
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE


class LLMProvider(ABC):
    """Interface that every LLM provider must implement."""

    @abstractmethod
    async def list_models(self, api_key: str) -> list[dict]:
        """Return available models as [{"id": "...", "name": "..."}, ...]."""
        ...

    @abstractmethod
    async def chat(
        self,
        api_key: str,
        model: str,
        system: str,
        messages: list[dict],
    ) -> str:
        """Send a chat completion request and return the assistant's text.

        Parameters
        ----------
        api_key:  User-supplied key for this provider.
        model:    Model identifier (e.g. "claude-sonnet-4-20250514").
        system:   System prompt text.
        messages: Conversation history as [{"role": "user"|"assistant", "content": "..."}].

        Returns
        -------
        The assistant's response text.
        """
        ...


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


class AnthropicProvider(LLMProvider):
    """Anthropic Messages API via raw httpx."""

    BASE_URL = "https://api.anthropic.com"
    API_VERSION = "2023-06-01"

    def _headers(self, api_key: str) -> dict:
        return {
            "x-api-key": api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }

    async def list_models(self, api_key: str) -> list[dict]:
        models: list[dict] = []
        after_id: str | None = None

        async with httpx.AsyncClient(verify=_ssl_ctx, timeout=15.0) as client:
            while True:
                params: dict = {"limit": 1000}
                if after_id:
                    params["after_id"] = after_id

                resp = await client.get(
                    f"{self.BASE_URL}/v1/models",
                    headers=self._headers(api_key),
                    params=params,
                )

                if resp.status_code == 401:
                    raise ProviderAuthError("Invalid Anthropic API key.")
                resp.raise_for_status()

                data = resp.json()
                models.extend(
                    {"id": m["id"], "name": m.get("display_name", m["id"])}
                    for m in data.get("data", [])
                )

                if not data.get("has_more"):
                    break
                after_id = data.get("last_id")

        return models

    async def chat(
        self,
        api_key: str,
        model: str,
        system: str,
        messages: list[dict],
    ) -> str:
        payload = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": messages,
        }

        async with httpx.AsyncClient(verify=_ssl_ctx, timeout=120.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/v1/messages",
                headers=self._headers(api_key),
                json=payload,
            )

            if resp.status_code == 401:
                raise ProviderAuthError("Invalid Anthropic API key.")
            if resp.status_code >= 400:
                body = (
                    resp.json()
                    if resp.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else {}
                )
                detail = body.get("error", {}).get("message", resp.text)
                raise ProviderAPIError(
                    f"Anthropic API error ({resp.status_code}): {detail}"
                )

            data = resp.json()
            # Response shape: {"content": [{"type": "text", "text": "..."}], ...}
            return data["content"][0]["text"]


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


class OpenAIProvider(LLMProvider):
    """OpenAI Chat Completions API via raw httpx."""

    BASE_URL = "https://api.openai.com"

    # Model prefixes that are NOT chat models (used to filter the models list).
    _EXCLUDE_PREFIXES = (
        "whisper",
        "tts",
        "dall-e",
        "davinci",
        "babbage",
        "curie",
        "ada",
        "text-embedding",
        "embedding",
        "moderation",
        "canary",
    )

    def _headers(self, api_key: str) -> dict:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def list_models(self, api_key: str) -> list[dict]:
        async with httpx.AsyncClient(verify=_ssl_ctx, timeout=15.0) as client:
            resp = await client.get(
                f"{self.BASE_URL}/v1/models",
                headers=self._headers(api_key),
            )

            if resp.status_code == 401:
                raise ProviderAuthError("Invalid OpenAI API key.")
            resp.raise_for_status()

            data = resp.json()
            models = []
            for m in data.get("data", []):
                mid = m["id"]
                if any(mid.startswith(p) for p in self._EXCLUDE_PREFIXES):
                    continue
                # OpenAI doesn't have display_name; use the id as the name.
                models.append({"id": mid, "name": mid})

            # Sort: gpt-4o first, then gpt-4, then gpt-3.5, then the rest.
            def sort_key(m: dict) -> tuple:
                mid = m["id"]
                if mid.startswith("o"):
                    return (0, mid)
                if mid.startswith("gpt-4o"):
                    return (1, mid)
                if mid.startswith("gpt-4"):
                    return (2, mid)
                if mid.startswith("gpt-3"):
                    return (3, mid)
                return (4, mid)

            models.sort(key=sort_key)
            return models

    async def chat(
        self,
        api_key: str,
        model: str,
        system: str,
        messages: list[dict],
    ) -> str:
        # OpenAI takes the system prompt as a message with role "system".
        oai_messages = [{"role": "system", "content": system}]
        oai_messages.extend(messages)

        payload = {
            "model": model,
            "max_tokens": 4096,
            "messages": oai_messages,
        }

        async with httpx.AsyncClient(verify=_ssl_ctx, timeout=120.0) as client:
            resp = await client.post(
                f"{self.BASE_URL}/v1/chat/completions",
                headers=self._headers(api_key),
                json=payload,
            )

            if resp.status_code == 401:
                raise ProviderAuthError("Invalid OpenAI API key.")
            if resp.status_code >= 400:
                body = (
                    resp.json()
                    if resp.headers.get("content-type", "").startswith(
                        "application/json"
                    )
                    else {}
                )
                detail = body.get("error", {}).get("message", resp.text)
                raise ProviderAPIError(
                    f"OpenAI API error ({resp.status_code}): {detail}"
                )

            data = resp.json()
            # Response shape: {"choices": [{"message": {"content": "..."}}]}
            return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Provider errors
# ---------------------------------------------------------------------------


class ProviderAuthError(Exception):
    """Raised when the API key is invalid / unauthorized."""

    pass


class ProviderAPIError(Exception):
    """Raised on non-auth API errors (rate limit, server error, etc.)."""

    pass


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, LLMProvider] = {
    "anthropic": AnthropicProvider(),
    "openai": OpenAIProvider(),
}
