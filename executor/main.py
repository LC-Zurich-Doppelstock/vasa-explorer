"""
Vasaloppet Code Executor Service

Isolated container that executes LLM-generated Python code against the
Vasaloppet results dataset. Exposes a single POST /execute endpoint.

Uses multiprocessing for true parallelism — each code execution runs in its
own worker process with isolated sys.stdout and matplotlib state.
"""

import base64
import io
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, TimeoutError

import matplotlib

matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
import seaborn as sns
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATA_PATH = "/data/results_clean.csv"
EXEC_TIMEOUT_SECONDS = 30
MAX_WORKERS = 4

SPLIT_COLS = [
    "Högsta punkten",
    "Smågan",
    "Mångsbodarna",
    "Risberg",
    "Evertsberg",
    "Oxberg",
    "Hökberg",
    "Eldris",
    "Finish",
]

# ---------------------------------------------------------------------------
# Dark theme for plots — matches the app's dark UI (#141416 background)
# ---------------------------------------------------------------------------
_BRIGHT_TEXT = "#d4d4d8"
_DIM_TEXT = "#a1a1aa"
_GRID_COLOR = "#2e2e33"
_ACCENT_PALETTE = [
    "#fb923c",  # orange (primary accent)
    "#34d399",  # emerald
    "#60a5fa",  # blue
    "#f472b6",  # pink
    "#a78bfa",  # violet
    "#facc15",  # yellow
    "#2dd4bf",  # teal
    "#f87171",  # red
    "#c084fc",  # purple
    "#38bdf8",  # sky
]

_MATPLOTLIB_THEME = {
    # Transparent figure & axes
    "figure.facecolor": "none",
    "axes.facecolor": "none",
    "savefig.facecolor": "none",
    # Text
    "text.color": _BRIGHT_TEXT,
    "axes.labelcolor": _BRIGHT_TEXT,
    "xtick.color": _DIM_TEXT,
    "ytick.color": _DIM_TEXT,
    # Spines
    "axes.edgecolor": _GRID_COLOR,
    # Grid
    "axes.grid": True,
    "grid.color": _GRID_COLOR,
    "grid.alpha": 0.6,
    "grid.linewidth": 0.5,
    # Color cycle — set dynamically in _apply_theme() since cycler needs plt
    # Legend
    "legend.facecolor": "none",
    "legend.edgecolor": _GRID_COLOR,
    "legend.labelcolor": _BRIGHT_TEXT,
    # Figure size
    "figure.figsize": (10, 5),
    "figure.dpi": 150,
    # Font sizes
    "font.size": 11,
    "axes.titlesize": 14,
    "axes.titleweight": "bold",
    "axes.labelsize": 12,
}


def _apply_theme():
    """Apply the dark matplotlib theme and seaborn palette."""
    plt.rcParams.update(_MATPLOTLIB_THEME)
    plt.rcParams["axes.prop_cycle"] = plt.cycler(color=_ACCENT_PALETTE)
    sns.set_palette(_ACCENT_PALETTE)


# Apply theme in the main process (inherited by forked workers)
_apply_theme()


# ---------------------------------------------------------------------------
# Worker process globals — populated by _init_worker.
# ---------------------------------------------------------------------------
_w_df: pd.DataFrame | None = None


def _init_worker(data_path: str):
    """
    Initialize each worker process.

    Each worker loads its own copy of the dataset. This avoids any
    copy-on-write pitfalls with fork and ensures complete isolation.
    The matplotlib theme is re-applied explicitly.
    """
    global _w_df  # noqa: PLW0603

    # Re-apply matplotlib theme in the worker
    _apply_theme()

    # Load the dataset in this worker process
    _w_df = pd.read_csv(data_path, index_col=0, low_memory=False)
    for col in SPLIT_COLS:
        _w_df[f"{col}_td"] = pd.to_timedelta(_w_df[col], unit="s")


def _run_code(code: str) -> dict:
    """
    Execute Python code with the DataFrame in scope.

    This runs in a worker process — sys.stdout and plt are process-local,
    so no locking is needed. Fully parallel across workers.

    Returns: {"stdout": str, "image": str|None, "error": str|None}
    """
    old_stdout = sys.stdout
    sys.stdout = captured = io.StringIO()

    fig_buf = io.BytesIO()
    image_b64 = None
    error = None

    namespace = {
        "df": _w_df.copy(),  # Copy so bad code can't corrupt the worker's data
        "pd": pd,
        "np": np,
        "plt": plt,
        "sns": sns,
        "scipy": scipy,
        "SPLIT_COLS": SPLIT_COLS,
    }

    try:
        plt.close("all")  # Clean slate
        exec(code, namespace)  # noqa: S102

        # Check if any figure was created
        if plt.get_fignums():
            plt.tight_layout()
            plt.savefig(
                fig_buf,
                format="png",
                dpi=150,
                bbox_inches="tight",
                transparent=True,
            )
            fig_buf.seek(0)
            image_b64 = base64.b64encode(fig_buf.read()).decode("utf-8")
            plt.close("all")

    except Exception:
        error = traceback.format_exc()
    finally:
        sys.stdout = old_stdout

    return {
        "stdout": captured.getvalue(),
        "image": image_b64,
        "error": error,
    }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Vasaloppet Code Executor")

# Load the dataset in the main process (for the /health endpoint row count)
print(f"Loading dataset from {DATA_PATH} ...")
df = pd.read_csv(DATA_PATH, index_col=0, low_memory=False)
for col in SPLIT_COLS:
    df[f"{col}_td"] = pd.to_timedelta(df[col], unit="s")
print(f"Dataset loaded: {df.shape[0]} rows, {df.shape[1]} columns")

# ---------------------------------------------------------------------------
# Process pool — workers load their own copy of the data via _init_worker.
# Using fork start method (Linux default) so matplotlib config is inherited.
# ---------------------------------------------------------------------------
print(f"Starting process pool with {MAX_WORKERS} workers ...")
_pool = ProcessPoolExecutor(
    max_workers=MAX_WORKERS,
    initializer=_init_worker,
    initargs=(DATA_PATH,),
)
print("Process pool ready.")


@app.get("/health")
def health():
    return {"status": "ok", "rows": len(df)}


@app.post("/execute")
def execute(payload: dict):
    """
    Execute Python code with the DataFrame `df` in scope.

    Expects: { "code": "..." }
    Returns: { "stdout": "...", "image": "<base64 png or null>", "error": "<traceback or null>" }
    """
    code = payload.get("code", "")

    try:
        future = _pool.submit(_run_code, code)
        result = future.result(timeout=EXEC_TIMEOUT_SECONDS)
    except TimeoutError:
        result = {
            "stdout": "",
            "image": None,
            "error": (
                f"Code execution timed out after {EXEC_TIMEOUT_SECONDS} seconds. "
                "The code may contain an infinite loop or a very expensive operation."
            ),
        }
    except Exception:
        result = {
            "stdout": "",
            "image": None,
            "error": traceback.format_exc(),
        }

    return result
