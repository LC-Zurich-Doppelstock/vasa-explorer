"""
Sandboxed code execution in worker processes.

Each worker loads its own copy of the dataset and runs user code with
isolated sys.stdout and matplotlib state. Fully parallel across workers.
"""

import base64
import io
import sys
import traceback

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
import seaborn as sns

from theme import apply_theme

# ---------------------------------------------------------------------------
# Constants shared with the execution namespace
# ---------------------------------------------------------------------------
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
# Worker process globals — populated by init_worker.
# ---------------------------------------------------------------------------
_w_df: pd.DataFrame | None = None


def init_worker(data_path: str):
    """
    Initialize each worker process.

    Each worker loads its own copy of the dataset. This avoids any
    copy-on-write pitfalls with fork and ensures complete isolation.
    The matplotlib theme is re-applied explicitly.
    """
    global _w_df  # noqa: PLW0603

    apply_theme()

    _w_df = pd.read_csv(data_path, index_col=0, low_memory=False)
    for col in SPLIT_COLS:
        _w_df[f"{col}_td"] = pd.to_timedelta(_w_df[col], unit="s")


def run_code(code: str) -> dict:
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
