"""
tests/test_music_engine.py
───────────────────────────
Tests for music_engine/generator.py placeholder generation.
"""

import sys
import wave
import struct
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestGenerateAudio:
    """Test the legacy single-file audio generation."""

    def test_generates_valid_wav(self, tmp_path):
        """Should produce a valid WAV file at the specified path."""
        from music_engine.generator import generate_audio
        from config.config_loader import reset_cache

        reset_cache()
        cfg = _minimal_config()
        output = str(tmp_path / "test.wav")
        result = generate_audio(output_path=output, config=cfg)

        assert result == output
        assert Path(output).exists()
        assert Path(output).stat().st_size > 0

        # Validate WAV headers
        with wave.open(output, "rb") as wf:
            assert wf.getnchannels() == 2
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 44100

    def test_generates_expected_duration(self, tmp_path):
        """Generated WAV should have approximately the correct duration."""
        from music_engine.generator import generate_audio

        cfg = _minimal_config(duration_minutes=0.1)  # 6 seconds
        output = str(tmp_path / "test.wav")
        generate_audio(output_path=output, config=cfg)

        with wave.open(output, "rb") as wf:
            nframes = wf.getnframes()
            rate    = wf.getframerate()
            actual_sec = nframes / rate

        expected_sec = 0.1 * 60
        # Allow 1% tolerance
        assert abs(actual_sec - expected_sec) < expected_sec * 0.01


class TestGenerateMusicAssets:
    """Test the new multi-output generate_music_assets function."""

    def test_creates_expected_structure(self, tmp_path):
        """Should create stems/, midi/, meta/, full_mix.wav."""
        from music_engine.generator import generate_music_assets

        cfg = _minimal_config()
        result = generate_music_assets(
            music_dir=tmp_path / "music",
            config=cfg,
            duration_sec=5,
            seed=42,
        )

        music_dir = tmp_path / "music"
        assert (music_dir / "full_mix.wav").exists()
        assert (music_dir / "stems" / "main_mix.wav").exists()
        assert (music_dir / "midi" / "main.mid").exists()
        assert (music_dir / "meta" / "sections.csv").exists()
        assert (music_dir / "meta" / "tempo_map.json").exists()

    def test_returns_correct_keys(self, tmp_path):
        from music_engine.generator import generate_music_assets

        cfg = _minimal_config()
        result = generate_music_assets(
            music_dir=tmp_path / "music",
            config=cfg,
            duration_sec=5,
            seed=42,
        )
        assert "full_mix" in result
        assert "stems_dir" in result
        assert "midi_dir" in result
        assert "meta_dir" in result

    def test_midi_is_valid_smf(self, tmp_path):
        """Generated MIDI should start with MThd header."""
        from music_engine.generator import generate_music_assets

        cfg = _minimal_config()
        generate_music_assets(
            music_dir=tmp_path / "music",
            config=cfg,
            duration_sec=5,
            seed=42,
        )
        midi_path = tmp_path / "music" / "midi" / "main.mid"
        with open(midi_path, "rb") as f:
            header = f.read(4)
        assert header == b"MThd", "MIDI file should start with MThd"

    def test_reproducible_with_same_seed(self, tmp_path):
        """Same seed should produce identical WAV files."""
        from music_engine.generator import generate_audio

        cfg = _minimal_config(duration_minutes=0.05)

        out1 = str(tmp_path / "a.wav")
        out2 = str(tmp_path / "b.wav")
        generate_audio(out1, cfg)
        generate_audio(out2, cfg)

        assert Path(out1).read_bytes() == Path(out2).read_bytes()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _minimal_config(duration_minutes: float = 0.05):
    return {
        "project_name": "test",
        "theme": "test_theme",
        "seed": 42,
        "video": {"duration_minutes": duration_minutes, "fps": 30,
                  "resolution_x": 1920, "resolution_y": 1080},
        "audio": {
            "sample_rate": 44100,
            "channels": 2,
            "encode_bitrate": "320k",
            "fallback_prompt": "test prompt",
        },
        "render": {"engine": "BLENDER_EEVEE_NEXT", "samples": 4},
        "paths": {"blender_exe": "blender", "themes_dir": "themes",
                  "ffmpeg_exe": "ffmpeg"},
    }
