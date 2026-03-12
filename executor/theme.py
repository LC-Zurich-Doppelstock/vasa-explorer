"""
Dark matplotlib/seaborn theme — matches the app's dark UI (#141416 background).

Call apply_theme() once in each process (main + workers) to activate.
"""

import matplotlib.pyplot as plt
import seaborn as sns

_BRIGHT_TEXT = "#d4d4d8"
_DIM_TEXT = "#a1a1aa"
_GRID_COLOR = "#2e2e33"

ACCENT_PALETTE = [
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


def apply_theme():
    """Apply the dark matplotlib theme and seaborn palette."""
    plt.rcParams.update(_MATPLOTLIB_THEME)
    plt.rcParams["axes.prop_cycle"] = plt.cycler(color=ACCENT_PALETTE)
    sns.set_palette(ACCENT_PALETTE)
