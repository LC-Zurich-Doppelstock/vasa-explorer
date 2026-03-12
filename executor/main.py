"""
Vasaloppet Code Executor — MCP Server

Isolated container that executes LLM-generated Python code against the
Vasaloppet results dataset. Exposes MCP tools and resources via Streamable
HTTP transport.

MCP Tools:
  - execute_python: Run Python code against the dataset
  - install_package: Install a pip package at runtime

MCP Resources (skills):
  - vasaloppet://skills/data-dictionary: Auto-generated data dictionary
  - vasaloppet://skills/installed-packages: List of installed pip packages

Uses multiprocessing for true parallelism — each code execution runs in its
own worker process with isolated sys.stdout and matplotlib state.
"""

import subprocess
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, TimeoutError

import matplotlib

matplotlib.use("Agg")  # Non-interactive backend — must precede any pyplot import

import pandas as pd
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent

from resources import build_data_dictionary, get_installed_packages
from sandbox import SPLIT_COLS, init_worker, run_code
from theme import apply_theme

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATA_PATH = "/data/results_clean.csv"
EXEC_TIMEOUT_SECONDS = 30
MAX_WORKERS = 4

# ---------------------------------------------------------------------------
# Bootstrap — theme, dataset, process pool
# ---------------------------------------------------------------------------
apply_theme()

print(f"Loading dataset from {DATA_PATH} ...")
df = pd.read_csv(DATA_PATH, index_col=0, low_memory=False)
for col in SPLIT_COLS:
    df[f"{col}_td"] = pd.to_timedelta(df[col], unit="s")
print(f"Dataset loaded: {df.shape[0]} rows, {df.shape[1]} columns")

print(f"Starting process pool with {MAX_WORKERS} workers ...")
_pool = ProcessPoolExecutor(
    max_workers=MAX_WORKERS,
    initializer=init_worker,
    initargs=(DATA_PATH,),
)
print("Process pool ready.")

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "Vasaloppet Code Executor",
    host="0.0.0.0",
    port=9000,
)


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------
@mcp.resource("vasaloppet://skills/data-dictionary")
def data_dictionary() -> str:
    """Auto-generated data dictionary for the Vasaloppet results dataset.

    Describes all columns, their dtypes, unique values for categorical columns,
    data availability timelines, and NaN patterns. Use this to write correct
    code against the DataFrame without guessing column values.
    """
    return build_data_dictionary(df)


@mcp.resource("vasaloppet://skills/installed-packages")
def installed_packages() -> str:
    """List of all Python packages installed in the executor environment.

    Refreshed on each read, so it reflects any packages installed at runtime
    via the install_package tool.
    """
    return get_installed_packages()


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------
@mcp.tool()
def install_package(package: str) -> str:
    """Install a Python package using pip.

    The package is installed into the running executor environment. This is
    ephemeral — packages installed this way are lost when the container restarts.

    Args:
        package: Package specifier (e.g. "scikit-learn", "plotly>=5.0").

    Returns:
        The pip install output (stdout + stderr).
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        if result.returncode != 0:
            return f"pip install failed (exit code {result.returncode}):\n{output}"
        return f"Successfully installed {package}.\n{output}"
    except subprocess.TimeoutExpired:
        return f"pip install timed out after 120 seconds for package: {package}"
    except Exception:
        return f"Failed to install {package}:\n{traceback.format_exc()}"


@mcp.tool()
def execute_python(code: str) -> CallToolResult:
    """Execute Python code against the Vasaloppet dataset (764,830 rows, 1922-2026).

    The code runs in a sandboxed process with the following variables in scope:
    - df: pandas DataFrame with the full dataset
    - pd, np, plt, sns, scipy: standard data science libraries
    - SPLIT_COLS: list of checkpoint column names

    Use print() for text output. Use plt for matplotlib charts.
    Returns text output and/or a PNG chart image.
    """
    try:
        future = _pool.submit(run_code, code)
        result = future.result(timeout=EXEC_TIMEOUT_SECONDS)
    except TimeoutError:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=(
                        f"Code execution timed out after {EXEC_TIMEOUT_SECONDS} "
                        "seconds. The code may contain an infinite loop or a very "
                        "expensive operation."
                    ),
                )
            ],
            isError=True,
        )
    except Exception:
        return CallToolResult(
            content=[TextContent(type="text", text=traceback.format_exc())],
            isError=True,
        )

    # Build the MCP content list
    content = []

    if result.get("error"):
        return CallToolResult(
            content=[TextContent(type="text", text=result["error"])],
            isError=True,
        )

    stdout = result.get("stdout", "")
    if stdout:
        content.append(TextContent(type="text", text=stdout))

    image_b64 = result.get("image")
    if image_b64:
        content.append(ImageContent(type="image", data=image_b64, mimeType="image/png"))

    if not content:
        content.append(
            TextContent(type="text", text="Code executed successfully (no output).")
        )

    return CallToolResult(content=content, isError=False)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
