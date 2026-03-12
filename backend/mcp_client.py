"""
MCP Client — manages the long-lived connection to the executor MCP server.

The streamablehttp_client context manager creates an anyio task group that
must be entered *and* exited inside the same asyncio task.  FastAPI's
lifespan, however, spans different internal tasks, which causes a
"cancel scope in a different task" crash.

Solution: a dedicated background asyncio.Task that owns the MCP connection
for the entire app lifetime, coordinated via asyncio.Event objects.
"""

import asyncio
import logging

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import ImageContent, TextContent

from config import EXECUTOR_URL

logger = logging.getLogger("backend")

# ---------------------------------------------------------------------------
# Module-level state — accessed by the orchestrator and routes.
# ---------------------------------------------------------------------------
session: ClientSession | None = None
tools: list | None = None
data_dictionary: str = ""
installed_packages: str = ""

_ready = asyncio.Event()
_shutdown = asyncio.Event()
_task: asyncio.Task | None = None


async def _connection_task():
    """Long-lived task that owns the MCP client connection."""
    global session, tools, data_dictionary, installed_packages  # noqa: PLW0603

    mcp_url = f"{EXECUTOR_URL}/mcp"

    for attempt in range(10):
        try:
            logger.info(f"MCP connection attempt {attempt + 1} to {mcp_url} ...")
            async with streamablehttp_client(mcp_url) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as sess:
                    await sess.initialize()

                    # Discover tools
                    tools_result = await sess.list_tools()
                    tool_names = [t.name for t in tools_result.tools]
                    logger.info(f"MCP connection established. Tools: {tool_names}")

                    # Read MCP resources (skills)
                    resources_result = await sess.list_resources()
                    resource_uris = [r.uri for r in resources_result.resources]
                    logger.info(f"MCP resources available: {resource_uris}")

                    for resource in resources_result.resources:
                        content = await sess.read_resource(resource.uri)
                        text = content.contents[0].text if content.contents else ""
                        uri_str = str(resource.uri)
                        if "data-dictionary" in uri_str:
                            data_dictionary = text
                            logger.info(f"Loaded data dictionary ({len(text)} chars)")
                        elif "installed-packages" in uri_str:
                            installed_packages = text
                            logger.info(
                                f"Loaded installed packages ({len(text)} chars)"
                            )

                    session = sess
                    tools = tools_result.tools
                    _ready.set()

                    # Keep alive until shutdown
                    await _shutdown.wait()

                    session = None
                    tools = None
            return

        except Exception as e:
            if attempt < 9:
                wait = min(2**attempt, 10)
                logger.warning(
                    f"MCP connection attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {wait}s ..."
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    f"Failed to connect to MCP executor after 10 attempts: {e}"
                )
                _ready.set()  # unblock lifespan so the app can report failure
                raise


async def connect():
    """Start the background MCP connection task and wait until ready."""
    global _task  # noqa: PLW0603
    _task = asyncio.create_task(_connection_task())
    await _ready.wait()
    if session is None:
        raise RuntimeError("MCP connection could not be established")


async def disconnect():
    """Signal the background task to shut down and wait for it."""
    _shutdown.set()
    if _task:
        await _task


async def execute_code(code: str) -> dict:
    """Execute code via the MCP executor's execute_python tool.

    Returns: {"stdout": str, "image": str|None, "error": str|None}
    """
    if session is None:
        raise RuntimeError("MCP session not initialized")

    result = await session.call_tool("execute_python", {"code": code})

    stdout = ""
    image = None
    error = None

    if result.isError:
        error_parts = []
        for item in result.content:
            if isinstance(item, TextContent):
                error_parts.append(item.text)
        error = "\n".join(error_parts) if error_parts else "Unknown execution error"
    else:
        for item in result.content:
            if isinstance(item, TextContent):
                stdout += item.text
            elif isinstance(item, ImageContent):
                image = item.data

    return {"stdout": stdout, "image": image, "error": error}
