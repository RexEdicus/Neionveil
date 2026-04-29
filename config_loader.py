"""
config_loader.py
─────────────────
Shared utility. Every module imports this to get the config dict.
Never import config directly — always go through load_config().

Usage:
    from config.config_loader import load_config
    cfg = load_config()
    print(cfg["video"]["fps"])
"""

import os
import yaml
from pathlib import Path


_CONFIG_PATH = Path(__file__).parent / "config.yaml"
_cached_config = None


def load_config(path: str = None) -> dict:
    """
    Load and return the config dict. Cached after first call.
    Pass a custom path string to override (useful for testing).
    """
    global _cached_config

    if _cached_config is not None and path is None:
        return _cached_config

    target = Path(path) if path else _CONFIG_PATH

    if not target.exists():
        raise FileNotFoundError(
            f"[Config] config.yaml not found at: {target}\n"
            f"Expected location: {_CONFIG_PATH}"
        )

    with open(target, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Validate required top-level keys
    required_keys = ["project_name", "video", "audio", "render", "paths", "theme"]
    missing = [k for k in required_keys if k not in config]
    if missing:
        raise KeyError(f"[Config] Missing required keys in config.yaml: {missing}")

    # Resolve seed: if null, generate a random one and inject it
    import random
    if config.get("seed") is None:
        config["seed"] = random.randint(0, 999999)
        print(f"[Config] No seed set — using random seed: {config['seed']}")

    _cached_config = config
    return config


def get_theme_dir(config: dict) -> Path:
    """Return the absolute path to the active theme folder."""
    base = Path(__file__).parent.parent
    return base / config["paths"]["themes_dir"] / config["theme"]


def get_temp_dir(config: dict) -> Path:
    """Return temp dir path, scoped per theme + seed to prevent collisions."""
    base = Path(__file__).parent.parent
    theme = config["theme"]
    seed = config["seed"]
    return base / config["paths"]["temp_dir"] / f"{theme}_{seed}"


def get_output_dir(config: dict) -> Path:
    """Return the output vault path."""
    base = Path(__file__).parent.parent
    return base / config["paths"]["output_dir"]
