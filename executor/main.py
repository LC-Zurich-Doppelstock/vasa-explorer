"""
Vasaloppet Code Executor Service

Isolated container that executes LLM-generated Python code against the
Vasaloppet results dataset. Exposes a single POST /execute endpoint.
"""

import base64
import io
import sys
import traceback

import matplotlib

matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
import seaborn as sns
from fastapi import FastAPI

app = FastAPI(title="Vasaloppet Code Executor")

# ---------------------------------------------------------------------------
# Load the dataset once at startup
# ---------------------------------------------------------------------------
DATA_PATH = "/data/results_clean.csv"

print(f"Loading dataset from {DATA_PATH} ...")
df = pd.read_csv(DATA_PATH, index_col=0, low_memory=False)

# Convert split columns from seconds (float) to timedelta for convenience.
# Keep the raw seconds columns too, prefixed with _sec.
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
for col in SPLIT_COLS:
    df[f"{col}_td"] = pd.to_timedelta(df[col], unit="s")

print(f"Dataset loaded: {df.shape[0]} rows, {df.shape[1]} columns")


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

    # Capture stdout
    old_stdout = sys.stdout
    sys.stdout = captured = io.StringIO()

    # Prepare a BytesIO buffer for figures
    fig_buf = io.BytesIO()
    image_b64 = None
    error = None

    # Build the execution namespace
    namespace = {
        "df": df.copy(),  # Give a copy so bad code can't corrupt the original
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
            plt.savefig(fig_buf, format="png", dpi=150, bbox_inches="tight")
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
