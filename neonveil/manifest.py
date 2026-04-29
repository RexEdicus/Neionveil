"""
neonveil/manifest.py
─────────────────────
Helpers for reading / writing the per-run manifest.json.

Layout:
    runs/<run_id>/manifest.json
"""

import json
import datetime
from datetime import timezone
from pathlib import Path


def create_manifest(
    run_dir: Path,
    run_id: str,
    theme: str,
    seed: int,
    duration_sec: int,
    mode: str,
    cli_args: dict,
) -> dict:
    """
    Create an initial manifest.json in the run directory.
    Returns the manifest dict.
    """
    manifest = {
        "run_id": run_id,
        "theme": theme,
        "seed": seed,
        "duration_sec": duration_sec,
        "mode": mode,
        "created_at": datetime.datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.datetime.now(timezone.utc).isoformat(),
        "cli_args": cli_args,
        "status": "in_progress",
        "files": {},
    }
    _write(run_dir, manifest)
    return manifest


def load_manifest(run_dir: Path) -> dict:
    """Load and return the manifest from *run_dir*."""
    path = Path(run_dir) / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"[Manifest] manifest.json not found in {run_dir}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def update_manifest(run_dir: Path, updates: dict) -> dict:
    """
    Merge *updates* into the existing manifest and write it back.
    Always sets updated_at to now.
    """
    manifest = load_manifest(run_dir)
    manifest.update(updates)
    manifest["updated_at"] = datetime.datetime.now(timezone.utc).isoformat()
    _write(run_dir, manifest)
    return manifest


def set_status(run_dir: Path, status: str) -> dict:
    """Convenience: update only the status field."""
    return update_manifest(run_dir, {"status": status})


def register_file(run_dir: Path, key: str, path: str) -> dict:
    """Register a produced file path in the manifest's 'files' dict."""
    manifest = load_manifest(run_dir)
    manifest.setdefault("files", {})[key] = str(path)
    manifest["updated_at"] = datetime.datetime.now(timezone.utc).isoformat()
    _write(run_dir, manifest)
    return manifest


def _write(run_dir: Path, manifest: dict):
    path = Path(run_dir) / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
