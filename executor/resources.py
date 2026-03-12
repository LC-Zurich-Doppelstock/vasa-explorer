"""
MCP Resource generators — contextual data the LLM can reference.

These are pure functions: DataFrame/system state in, markdown string out.
The MCP @resource decorators are applied in main.py.
"""

import json
import subprocess
import sys

import pandas as pd

from sandbox import SPLIT_COLS


def build_data_dictionary(dataframe: pd.DataFrame) -> str:
    """Generate a markdown data dictionary from the DataFrame."""
    lines = ["## Data Dictionary", ""]
    lines.append(
        f"The DataFrame `df` has **{dataframe.shape[0]:,} rows** "
        f"and **{dataframe.shape[1]} columns**."
    )
    lines.append("")

    # Column listing with dtypes
    lines.append("### Columns and dtypes")
    lines.append("")
    for col in dataframe.columns:
        if col.endswith("_td"):
            continue  # skip timedelta helpers in the listing
        lines.append(f"- **{col}** ({dataframe[col].dtype})")
    lines.append("")

    # Year range
    lines.append("### Year coverage")
    yr = dataframe["Year"]
    all_years = set(range(yr.min(), yr.max() + 1))
    missing = sorted(all_years - set(yr.unique()))
    lines.append(f"- Range: {yr.min()} to {yr.max()} ({yr.nunique()} unique years)")
    lines.append(f"- Missing years (no race held): {missing}")
    lines.append("")

    # Categorical columns — exact unique values
    lines.append("### Status values")
    lines.append("")
    for val, cnt in dataframe["Status"].value_counts(dropna=False).items():
        label = "NaN" if pd.isna(val) else f'"{val}"'
        lines.append(f"- {label}: {cnt:,}")
    lines.append("")

    lines.append("### Sex values")
    lines.append("")
    for val, cnt in dataframe["Sex"].value_counts(dropna=False).items():
        label = "NaN" if pd.isna(val) else f'"{val}"'
        lines.append(f"- {label}: {cnt:,}")
    lines.append("")

    lines.append("### Group values (age/sex categories)")
    lines.append("H = Herrar (Men), D = Damer (Women). Number = minimum age.")
    lines.append("")
    for val, cnt in dataframe["Group"].value_counts(dropna=False).items():
        label = "NaN" if pd.isna(val) else f'"{val}"'
        lines.append(f"- {label}: {cnt:,}")
    lines.append("")

    lines.append("### StartGroup values")
    lines.append("")
    for val, cnt in dataframe["StartGroup"].value_counts(dropna=False).items():
        label = "NaN" if pd.isna(val) else f'"{val}"'
        lines.append(f"- {label}: {cnt:,}")
    lines.append("")

    # Nations — top 20 + total
    lines.append(
        "### Nation values (top 20 of {})".format(dataframe["Nation"].nunique())
    )
    lines.append("3-letter country codes.")
    lines.append("")
    for val, cnt in dataframe["Nation"].value_counts(dropna=False).head(20).items():
        label = "NaN" if pd.isna(val) else f'"{val}"'
        lines.append(f"- {label}: {cnt:,}")
    lines.append("")

    # Split column availability
    lines.append("### Checkpoint split columns")
    lines.append(
        "Times are in **seconds** (float64). NaN if the participant didn't reach "
        "that checkpoint."
    )
    lines.append(
        "Timedelta versions are also available with a `_td` suffix (e.g., `Finish_td`)."
    )
    lines.append("")
    lines.append("| Checkpoint | Distance | Available from | NaN % |")
    lines.append("|---|---|---|---|")
    distances = {
        "Högsta punkten": "~11 km",
        "Smågan": "~24 km",
        "Mångsbodarna": "~35 km",
        "Risberg": "~47 km",
        "Evertsberg": "~58 km",
        "Oxberg": "~71 km",
        "Hökberg": "~81 km",
        "Eldris": "~88 km",
        "Finish": "~90 km",
    }
    for col in SPLIT_COLS:
        pct = dataframe[col].isna().mean() * 100
        first_year = dataframe[dataframe[col].notna()]["Year"].min()
        dist = distances.get(col, "")
        lines.append(f"| {col} | {dist} | {first_year} | {pct:.1f}% |")
    lines.append("")

    # Bib availability
    lines.append("### Bib column")
    lines.append("Bib numbers are strings. Mostly NaN for years before ~2000.")
    lines.append("")

    # Name format
    lines.append("### Name format")
    lines.append('Names are in "Lastname, Firstname" format (e.g., "Persson, Nils").')
    lines.append("")

    # SPLIT_COLS helper
    lines.append("### SPLIT_COLS")
    lines.append(
        "A list variable is available in the executor: "
        "`SPLIT_COLS = " + repr(SPLIT_COLS) + "`"
    )
    lines.append("")

    # Note about column names
    lines.append("### Important: column names use Swedish characters")
    lines.append(
        'Use the exact names with Swedish characters: "Högsta punkten", '
        '"Smågan", "Mångsbodarna", "Hökberg", etc.'
    )

    return "\n".join(lines)


def get_installed_packages() -> str:
    """Get a formatted list of all installed pip packages."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "list", "--format=json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    packages = json.loads(result.stdout)

    lines = ["## Installed Python Packages", ""]
    lines.append(f"{len(packages)} packages installed:")
    lines.append("")
    for pkg in sorted(packages, key=lambda p: p["name"].lower()):
        lines.append(f"- {pkg['name']}=={pkg['version']}")

    return "\n".join(lines)
