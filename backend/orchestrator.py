"""
LLM orchestration — the retry loop that drives question answering.

Takes a user question, calls the LLM, extracts code, executes it via the
MCP executor, handles errors (including auto-installing missing packages),
and returns the final response.
"""

import logging
import re

from mcp.types import TextContent

from providers import ProviderAuthError, ProviderAPIError
import mcp_client
from config import MAX_RETRIES

logger = logging.getLogger("backend")


def extract_code_block(text: str) -> str | None:
    """Extract Python code from a fenced code block in the response."""
    pattern = r"```python\s*\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _build_success_messages(
    assistant_text: str, stdout: str, image: str | None, extra_note: str = ""
) -> list[dict]:
    """Build conversation messages for a successful execution result."""
    msgs: list[dict] = [{"role": "assistant", "content": assistant_text}]
    exec_summary = ""
    if stdout:
        exec_summary += f"Code output:\n{stdout}\n"
    if image:
        exec_summary += "[A figure was generated and displayed to the user.]\n"
    if exec_summary:
        note = extra_note or "the code executed successfully."
        msgs.append({"role": "user", "content": f"[System: {note}]\n{exec_summary}"})
        msgs.append(
            {
                "role": "assistant",
                "content": "Understood, the results have been shown to the user.",
            }
        )
    return msgs


async def _try_auto_install(error_text: str, code: str) -> dict | None:
    """If the error is an ImportError, try installing the package and re-running.

    Returns the successful execution result dict, or None if auto-install
    didn't apply or didn't fix the problem.  Updates mcp_client.installed_packages
    on success.
    """
    import_match = re.search(
        r"(?:ModuleNotFoundError|ImportError): No module named ['\"](\w+)['\"]",
        error_text,
    )
    if not import_match or mcp_client.session is None:
        return None

    module_name = import_match.group(1)
    logger.info(f"Auto-installing missing module: {module_name}")

    try:
        install_result = await mcp_client.session.call_tool(
            "install_package", {"package": module_name}
        )
        install_text = ""
        for item in install_result.content:
            if isinstance(item, TextContent):
                install_text += item.text
        logger.info(f"install_package result: {install_text[:200]}")

        # Refresh the installed packages resource
        try:
            pkg_content = await mcp_client.session.read_resource(
                "vasaloppet://skills/installed-packages"
            )
            if pkg_content.contents:
                mcp_client.installed_packages = pkg_content.contents[0].text
        except Exception as e:
            logger.warning(f"Failed to refresh installed packages: {e}")

        # Retry the same code after installing
        retry_result = await mcp_client.execute_code(code)
        if not retry_result.get("error"):
            retry_result["_auto_installed"] = module_name
            return retry_result
        else:
            return None

    except Exception as e:
        logger.warning(f"Auto-install failed for {module_name}: {e}")
        return None


async def orchestrate_ask(
    *,
    provider,
    api_key: str,
    model: str,
    system_prompt: str,
    messages: list[dict],
) -> tuple[str, str | None]:
    """Run the ask retry loop.

    Returns (final_text, final_image) where final_image is a data-URI or None.
    Raises HTTPException on auth / provider errors.
    """
    from fastapi import HTTPException

    final_text = ""
    final_image = None

    for attempt in range(MAX_RETRIES + 1):
        # 1. Call the LLM
        try:
            assistant_text = await provider.chat(
                api_key=api_key,
                model=model,
                system=system_prompt,
                messages=messages,
            )
        except ProviderAuthError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except ProviderAPIError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"LLM request failed: {e}")

        # 2. Extract code (if any)
        code = extract_code_block(assistant_text)

        if code is None:
            messages.append({"role": "assistant", "content": assistant_text})
            final_text = assistant_text
            break

        # 3. Execute code
        try:
            result = await mcp_client.execute_code(code)
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

        # 4. Handle execution errors
        if result.get("error"):
            error_text = result["error"]

            # Try auto-installing missing packages
            auto_result = await _try_auto_install(error_text, code)
            if auto_result:
                module_name = auto_result.pop("_auto_installed")
                stdout = auto_result.get("stdout", "").strip()
                image = auto_result.get("image")
                final_text = stdout if stdout else "Done."
                final_image = f"data:image/png;base64,{image}" if image else None
                note = f"the code executed successfully after auto-installing {module_name}."
                messages.extend(
                    _build_success_messages(assistant_text, stdout, image, note)
                )
                break

            # Normal error — feed traceback back to LLM for retry
            messages.append({"role": "assistant", "content": assistant_text})
            error_feedback = (
                f"The code produced an error:\n```\n{error_text}\n```\n"
                "Please fix the code and try again."
            )
            messages.append({"role": "user", "content": error_feedback})
            final_text = f"Code error (attempt {attempt + 1}): {error_text}"
            continue

        # 5. Success
        stdout = result.get("stdout", "").strip()
        image = result.get("image")
        final_text = stdout if stdout else "Done."
        final_image = f"data:image/png;base64,{image}" if image else None
        messages.extend(_build_success_messages(assistant_text, stdout, image))
        break

    return final_text, final_image
