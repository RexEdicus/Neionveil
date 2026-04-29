"""
tests/test_cli.py
──────────────────
Tests for the master_run.py CLI argument parsing, validation, and
orchestrator building blocks (run_id, manifest).
"""

import sys
import pytest
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestArgParsing:
    """Test that the CLI parser correctly handles all flags."""

    def _parse(self, argv: list):
        """Helper: call parse_args with a custom argv."""
        import sys
        old_argv = sys.argv
        sys.argv = ["master_run.py"] + argv
        try:
            from master_run import parse_args
            return parse_args()
        finally:
            sys.argv = old_argv

    def test_mode_defaults_to_full(self):
        args = self._parse(["--theme", "neon_rain", "--duration", "3600"])
        assert args.mode == "full"

    def test_mode_assets(self):
        args = self._parse(["--mode", "assets", "--theme", "neon_rain", "--duration", "3600"])
        assert args.mode == "assets"

    def test_mode_assemble(self):
        args = self._parse(["--mode", "assemble", "--run-id", "2026-04-29_neon-rain_run-0001"])
        assert args.mode == "assemble"
        assert args.run_id == "2026-04-29_neon-rain_run-0001"

    def test_mode_render(self):
        args = self._parse(["--mode", "render", "--run-id", "2026-04-29_neon-rain_run-0001"])
        assert args.mode == "render"

    def test_defaults(self):
        args = self._parse(["--mode", "assets", "--theme", "x", "--duration", "60"])
        assert args.quality == "balanced"
        assert args.res == "2560x1440"
        assert args.fps == 30
        assert args.camera_mode == "continuous"
        assert args.camera == "auto"
        assert args.cut_every == 240
        assert args.cut_style == "hard"
        assert args.cut_fade == 1.0
        assert args.render_cache == "reuse"
        assert args.dry_run is False
        assert args.verbose is False

    def test_camera_flags(self):
        args = self._parse([
            "--mode", "assemble",
            "--run-id", "r",
            "--camera-mode", "cuts",
            "--camera-sequence", "CAM_MAIN,CAM_ALT_01",
            "--cut-every", "180",
            "--cut-style", "crossfade",
            "--cut-fade", "2.0",
        ])
        assert args.camera_mode == "cuts"
        assert args.camera_sequence == "CAM_MAIN,CAM_ALT_01"
        assert args.cut_every == 180
        assert args.cut_style == "crossfade"
        assert args.cut_fade == 2.0

    def test_quality_choices(self):
        for quality in ("fast", "balanced", "final"):
            args = self._parse(["--mode", "assets", "--theme", "x", "--duration", "60",
                                 "--quality", quality])
            assert args.quality == quality

    def test_res_choices(self):
        for res in ("1920x1080", "2560x1440", "3840x2160"):
            args = self._parse(["--mode", "assets", "--theme", "x", "--duration", "60",
                                 "--res", res])
            assert args.res == res

    def test_render_mode_choices(self):
        for rm in ("loop", "frames", "both", "off"):
            args = self._parse(["--mode", "assets", "--theme", "x", "--duration", "60",
                                 "--render-mode", rm])
            assert args.render_mode == rm

    def test_blend_file_and_audio_file(self):
        args = self._parse([
            "--mode", "assemble", "--run-id", "r",
            "--blend-file", "/tmp/test.blend",
            "--audio-file", "/tmp/test.wav",
        ])
        assert args.blend_file == "/tmp/test.blend"
        assert args.audio_file == "/tmp/test.wav"

    def test_dry_run_and_verbose(self):
        args = self._parse([
            "--mode", "assets", "--theme", "x", "--duration", "60",
            "--dry-run", "--verbose",
        ])
        assert args.dry_run is True
        assert args.verbose is True

    def test_render_cache_choices(self):
        for policy in ("reuse", "rerender"):
            args = self._parse(["--mode", "assemble", "--run-id", "r",
                                 "--render-cache", policy])
            assert args.render_cache == policy


class TestValidation:
    """Test validate_args catches invalid combinations."""

    def _parse(self, argv: list):
        import sys
        old_argv = sys.argv
        sys.argv = ["master_run.py"] + argv
        try:
            from master_run import parse_args
            return parse_args()
        finally:
            sys.argv = old_argv

    def test_full_requires_theme(self):
        args = self._parse(["--mode", "full", "--duration", "60"])
        args.theme = None
        from master_run import validate_args
        with pytest.raises(SystemExit):
            validate_args(args)

    def test_full_requires_duration(self):
        args = self._parse(["--mode", "full", "--theme", "neon_rain"])
        args.duration = None
        from master_run import validate_args
        with pytest.raises(SystemExit):
            validate_args(args)

    def test_assemble_requires_run_id(self):
        args = self._parse(["--mode", "assemble", "--run-id", "r"])
        args.run_id = None
        from master_run import validate_args
        with pytest.raises(SystemExit):
            validate_args(args)


class TestRunId:
    """Test run ID generation helpers."""

    def test_make_run_id_format(self, tmp_path):
        from neonveil.run_id import make_run_id
        run_id = make_run_id("neon_rain", tmp_path)
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}_neon-rain_run-\d{4}$", run_id), \
            f"Unexpected run_id format: {run_id}"

    def test_make_run_id_increments(self, tmp_path):
        from neonveil.run_id import make_run_id
        id1 = make_run_id("neon_rain", tmp_path)
        (tmp_path / id1).mkdir()
        id2 = make_run_id("neon_rain", tmp_path)
        assert id2 != id1
        # The suffix number should be higher
        n1 = int(id1.split("_run-")[1])
        n2 = int(id2.split("_run-")[1])
        assert n2 == n1 + 1

    def test_parse_theme_from_run_id(self):
        from neonveil.run_id import parse_theme_from_run_id
        assert parse_theme_from_run_id("2026-04-29_neon-rain_run-0001") == "neon_rain"
        assert parse_theme_from_run_id("invalid") is None

    def test_resolve_run_dir(self, tmp_path):
        from neonveil.run_id import resolve_run_dir
        run_id = "2026-04-29_neon-rain_run-0001"
        run_dir = resolve_run_dir(run_id, tmp_path)
        assert run_dir == tmp_path / run_id


class TestManifest:
    """Test manifest creation and updates."""

    def test_create_manifest(self, tmp_path):
        from neonveil.manifest import create_manifest, load_manifest
        manifest = create_manifest(
            run_dir=tmp_path,
            run_id="2026-04-29_neon-rain_run-0001",
            theme="neon_rain",
            seed=42,
            duration_sec=3600,
            mode="assets",
            cli_args={"theme": "neon_rain"},
        )
        assert manifest["run_id"] == "2026-04-29_neon-rain_run-0001"
        assert manifest["status"] == "in_progress"

        # Should be loadable from disk
        loaded = load_manifest(tmp_path)
        assert loaded["theme"] == "neon_rain"
        assert loaded["seed"] == 42

    def test_update_manifest(self, tmp_path):
        from neonveil.manifest import create_manifest, update_manifest, load_manifest
        create_manifest(tmp_path, "r", "t", 1, 60, "full", {})
        update_manifest(tmp_path, {"status": "complete", "extra_key": "value"})
        m = load_manifest(tmp_path)
        assert m["status"] == "complete"
        assert m["extra_key"] == "value"

    def test_register_file(self, tmp_path):
        from neonveil.manifest import create_manifest, register_file, load_manifest
        create_manifest(tmp_path, "r", "t", 1, 60, "full", {})
        register_file(tmp_path, "full_mix", "/path/to/full_mix.wav")
        m = load_manifest(tmp_path)
        assert m["files"]["full_mix"] == "/path/to/full_mix.wav"


class TestCameraSequenceBuilding:
    """Test segment building for camera cuts mode."""

    def test_single_camera_full_duration(self):
        from neonveil.steps.assemble import _build_segments
        total_frames  = 100
        segment_frames = 50
        cameras = ["CAM_A"]
        segs = _build_segments(total_frames, segment_frames, cameras, fps=1)
        assert len(segs) == 2
        assert segs[0] == (1, 50, "CAM_A")
        assert segs[1] == (51, 100, "CAM_A")

    def test_camera_sequence_cycling(self):
        from neonveil.steps.assemble import _build_segments
        total_frames  = 300
        segment_frames = 100
        cameras = ["CAM_A", "CAM_B", "CAM_C"]
        segs = _build_segments(total_frames, segment_frames, cameras, fps=1)
        assert len(segs) == 3
        assert segs[0][2] == "CAM_A"
        assert segs[1][2] == "CAM_B"
        assert segs[2][2] == "CAM_C"

    def test_camera_sequence_cycles_wrap(self):
        from neonveil.steps.assemble import _build_segments
        total_frames  = 400
        segment_frames = 100
        cameras = ["CAM_A", "CAM_B"]
        segs = _build_segments(total_frames, segment_frames, cameras, fps=1)
        assert len(segs) == 4
        assert segs[0][2] == "CAM_A"
        assert segs[1][2] == "CAM_B"
        assert segs[2][2] == "CAM_A"
        assert segs[3][2] == "CAM_B"

    def test_last_segment_trimmed_to_total(self):
        from neonveil.steps.assemble import _build_segments
        total_frames  = 250
        segment_frames = 100
        cameras = ["CAM_A"]
        segs = _build_segments(total_frames, segment_frames, cameras, fps=1)
        assert len(segs) == 3
        assert segs[2][1] == 250      # last segment ends at total
