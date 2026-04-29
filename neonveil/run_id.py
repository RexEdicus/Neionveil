"""
neonveil/run_id.py
───────────────────
Helpers for generating and resolving run IDs.

Run ID format: YYYY-MM-DD_<theme>_run-NNNN
Example:       2026-04-29_neon-rain_run-0001
"""

import re
from datetime import date
from pathlib import Path


def make_run_id(theme: str, runs_dir: Path) -> str:
    """
    Generate the next available run ID for today + theme.

    Scans *runs_dir* for existing entries matching the same date+theme
    and returns the next number in sequence.
    """
    today   = date.today().strftime("%Y-%m-%d")
    # Normalise theme name: spaces/underscores → hyphens for readability
    theme_slug = theme.replace("_", "-").replace(" ", "-").lower()
    prefix  = f"{today}_{theme_slug}_run-"

    runs_dir = Path(runs_dir)
    existing = []

    if runs_dir.exists():
        for entry in runs_dir.iterdir():
            if entry.is_dir() and entry.name.startswith(prefix):
                suffix = entry.name[len(prefix):]
                if suffix.isdigit():
                    existing.append(int(suffix))

    next_n = max(existing, default=0) + 1
    return f"{prefix}{next_n:04d}"


def resolve_run_dir(run_id: str, runs_dir: Path) -> Path:
    """Return the absolute Path for a given run_id under runs_dir."""
    return Path(runs_dir) / run_id


def parse_theme_from_run_id(run_id: str) -> str | None:
    """
    Extract the theme slug from a run_id string.
    Returns None if the format doesn't match.
    """
    m = re.match(r"^\d{4}-\d{2}-\d{2}_(.+)_run-\d+$", run_id)
    return m.group(1).replace("-", "_") if m else None
