"""
tests/test_config.py
─────────────────────
Tests for config loading and presets.
"""

import os
import sys
import tempfile
import yaml
import pytest
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestLoadConfig:
    """Tests for config/config_loader.load_config()."""

    def test_load_default_config(self):
        """Should load config/config.yaml without errors."""
        from config.config_loader import load_config, reset_cache
        reset_cache()
        cfg = load_config()

        assert "project_name" in cfg
        assert "video" in cfg
        assert "audio" in cfg
        assert "render" in cfg
        assert "paths" in cfg
        assert "theme" in cfg

    def test_seed_auto_generated_when_null(self, tmp_path):
        """Null seed should be replaced with a random integer."""
        minimal = {
            "project_name": "test",
            "video": {"duration_minutes": 1, "resolution_x": 1920, "resolution_y": 1080, "fps": 30},
            "audio": {"sample_rate": 44100, "channels": 2, "encode_bitrate": "320k",
                      "fallback_prompt": "test"},
            "render": {"engine": "BLENDER_EEVEE_NEXT", "samples": 4},
            "paths": {"blender_exe": "blender", "themes_dir": "themes"},
            "theme": "test_theme",
            "seed": None,
        }
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump(minimal))

        from config.config_loader import load_config, reset_cache
        reset_cache()
        cfg = load_config(str(cfg_file))

        assert cfg["seed"] is not None
        assert isinstance(cfg["seed"], int)

    def test_seed_preserved_when_set(self, tmp_path):
        """Explicit seed should be preserved as-is."""
        minimal = {
            "project_name": "test",
            "video": {"duration_minutes": 1, "resolution_x": 1920, "resolution_y": 1080, "fps": 30},
            "audio": {"sample_rate": 44100, "channels": 2, "encode_bitrate": "320k",
                      "fallback_prompt": "test"},
            "render": {"engine": "BLENDER_EEVEE_NEXT", "samples": 4},
            "paths": {"blender_exe": "blender", "themes_dir": "themes"},
            "theme": "test_theme",
            "seed": 12345,
        }
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump(minimal))

        from config.config_loader import load_config, reset_cache
        reset_cache()
        cfg = load_config(str(cfg_file))

        assert cfg["seed"] == 12345

    def test_missing_required_keys_raises(self, tmp_path):
        """Config missing required keys should raise KeyError."""
        minimal = {"project_name": "x"}
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump(minimal))

        from config.config_loader import load_config, reset_cache
        reset_cache()
        with pytest.raises(KeyError):
            load_config(str(cfg_file))

    def test_missing_file_raises(self, tmp_path):
        """Non-existent config file should raise FileNotFoundError."""
        from config.config_loader import load_config, reset_cache
        reset_cache()
        with pytest.raises(FileNotFoundError):
            load_config(str(tmp_path / "nonexistent.yaml"))

    def test_get_theme_dir(self, tmp_path):
        """get_theme_dir should return the correct path."""
        from config.config_loader import get_theme_dir
        cfg = {"paths": {"themes_dir": "themes"}, "theme": "neon_rain"}
        theme_dir = get_theme_dir(cfg)
        assert theme_dir.name == "neon_rain"
        assert "themes" in str(theme_dir)

    def test_get_runs_dir(self):
        """get_runs_dir should return a path ending in 'runs'."""
        from config.config_loader import get_runs_dir
        runs = get_runs_dir()
        assert runs.name == "runs"


class TestPresets:
    """Tests for config/presets.yaml structure."""

    def test_presets_file_exists(self):
        presets_path = Path(__file__).parent.parent / "config" / "presets.yaml"
        assert presets_path.exists(), "config/presets.yaml must exist"

    def test_presets_quality_keys(self):
        presets_path = Path(__file__).parent.parent / "config" / "presets.yaml"
        with open(presets_path) as f:
            data = yaml.safe_load(f)

        assert "quality" in data
        for key in ("fast", "balanced", "final"):
            assert key in data["quality"], f"Missing quality preset: {key}"
            preset = data["quality"][key]
            assert "blender_samples" in preset
            assert "ffmpeg_crf" in preset
            assert "ffmpeg_preset" in preset

    def test_presets_resolution_keys(self):
        presets_path = Path(__file__).parent.parent / "config" / "presets.yaml"
        with open(presets_path) as f:
            data = yaml.safe_load(f)

        assert "resolution" in data
        for key in ("1920x1080", "2560x1440", "3840x2160"):
            assert key in data["resolution"]
            res = data["resolution"][key]
            assert "width" in res and "height" in res

    def test_render_mode_defaults_present(self):
        presets_path = Path(__file__).parent.parent / "config" / "presets.yaml"
        with open(presets_path) as f:
            data = yaml.safe_load(f)

        defaults = data.get("render_mode_defaults", {})
        assert defaults.get("full") == "loop"
        assert defaults.get("assets") == "off"
        assert defaults.get("assemble") == "loop"
