"""
neonveil/steps/render.py
─────────────────────────
"Render" pipeline step.

Responsibilities:
  - Invoke Blender as a subprocess with render_engine/full_render.py.
  - Support render-mode: loop | frames | both | off.
  - Support --camera for single-camera renders.
  - Support segment-based rendering for camera cuts (called per segment by
    the assemble step).
  - Support --render-cache reuse|rerender.

Called by the orchestrator for --mode full, --mode assets (optional preview),
--mode render, and --mode assemble (when render is needed).
"""

import os
import sys
import shutil
import subprocess
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Path to the Blender render script (inside this repo)
_RENDER_SCRIPT = Path(__file__).parent.parent.parent / "render_engine" / "full_render.py"


def run_render_step(
    run_dir: Path,
    blend_file: Path,
    config: dict,
    duration_sec: int,
    seed: int,
    render_mode: str = "loop",
    quality: str = "balanced",
    res: str = "2560x1440",
    fps: int = 30,
    camera: str = "auto",
    frame_start: int = None,
    frame_end: int = None,
    render_cache: str = "reuse",
    dry_run: bool = False,
    verbose: bool = False,
    output_subdir: str = None,
) -> dict:
    """
    Render frames / video from a .blend file using Blender.

    Args:
        run_dir:      Path to runs/<run_id>/.
        blend_file:   Path to the .blend to render from.
        config:       Full config dict.
        duration_sec: Total duration in seconds.
        seed:         Render seed.
        render_mode:  "loop" | "frames" | "both" | "off".
        quality:      "fast" | "balanced" | "final" preset name.
        res:          Resolution string "WxH".
        fps:          Frames per second.
        camera:       Camera name or "auto".
        frame_start:  Override frame start (for segment renders).
        frame_end:    Override frame end (for segment renders).
        render_cache: "reuse" (skip if output exists) | "rerender" (always).
        dry_run:      Print actions only.
        verbose:      Extra logging.
        output_subdir: Override for frames sub-directory name (for segments).

    Returns:
        dict with keys:
            frames_dir  — path to frames directory
            video_path  — path to rendered video (if loop/both, else None)
    """
    if render_mode == "off":
        print("[Render] render-mode=off — skipping render")
        return {"frames_dir": None, "video_path": None}

    run_dir   = Path(run_dir)
    render_dir = run_dir / "render"
    render_dir.mkdir(parents=True, exist_ok=True)

    # Determine output paths
    subdir_name = output_subdir or "frames"
    frames_dir  = render_dir / subdir_name

    # Load presets
    preset = _load_quality_preset(quality)
    res_x, res_y = _parse_resolution(res)
    samples = preset.get("blender_samples", config.get("render", {}).get("samples", 64))

    # Check render cache
    if render_cache == "reuse" and _render_outputs_exist(frames_dir, render_dir, render_mode):
        print(f"[Render] render-cache=reuse — using existing outputs in {render_dir}")
        video_path = _find_existing_video(render_dir)
        return {"frames_dir": str(frames_dir), "video_path": video_path}

    blender_exe = _resolve_blender(config)

    if dry_run:
        print(f"[DryRun] Would invoke Blender: {blender_exe}")
        print(f"[DryRun]   blend  : {blend_file}")
        print(f"[DryRun]   output : {frames_dir}")
        print(f"[DryRun]   camera : {camera}")
        print(f"[DryRun]   res    : {res_x}×{res_y}  fps={fps}  samples={samples}")
        if frame_start is not None:
            print(f"[DryRun]   frames : {frame_start}–{frame_end}")
        return {"frames_dir": str(frames_dir), "video_path": None}

    if not Path(blender_exe).exists():
        raise FileNotFoundError(
            f"[Render] Blender not found at: {blender_exe}\n"
            f"Update paths.blender_exe in config/config.yaml"
        )
    if not Path(blend_file).exists():
        raise FileNotFoundError(
            f"[Render] .blend file not found: {blend_file}"
        )

    frames_dir.mkdir(parents=True, exist_ok=True)

    cmd = _build_blender_cmd(
        blender_exe=blender_exe,
        blend_file=str(blend_file),
        frames_dir=str(frames_dir),
        blend_save=str(render_dir / "scene_used.blend"),
        fps=fps,
        duration_sec=duration_sec,
        res_x=res_x,
        res_y=res_y,
        samples=samples,
        seed=seed,
        engine=config.get("render", {}).get("engine", "BLENDER_EEVEE_NEXT"),
        bloom=str(config.get("render", {}).get("bloom", True)).lower(),
        volumetrics=str(config.get("render", {}).get("volumetrics", True)).lower(),
        camera=camera,
        frame_start=frame_start,
        frame_end=frame_end,
    )

    print(f"[Render] Launching Blender...")
    print(f"[Render] blend   : {blend_file}")
    print(f"[Render] output  : {frames_dir}")
    print(f"[Render] camera  : {camera}")
    if verbose:
        print(f"[Render] cmd     : {' '.join(cmd)}")

    result = subprocess.run(cmd, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"[Render] Blender exited with code {result.returncode}.\n"
            f"Check Blender's console output above for details."
        )

    print(f"[Render] Frames written to {frames_dir}")

    # If render_mode includes video, encode frames → video
    video_path = None
    if render_mode in ("loop", "both"):
        video_path = str(render_dir / "output_loop.mp4")
        video_path = _encode_frames_to_video(
            frames_dir=str(frames_dir),
            output_path=video_path,
            fps=fps,
            crf=preset.get("ffmpeg_crf", 18),
            ffmpeg_preset=preset.get("ffmpeg_preset", "slow"),
            ffmpeg_exe=config.get("paths", {}).get("ffmpeg_exe", "ffmpeg"),
        )

    return {"frames_dir": str(frames_dir), "video_path": video_path}


def render_segment(
    run_dir: Path,
    blend_file: Path,
    config: dict,
    segment_index: int,
    frame_start: int,
    frame_end: int,
    camera: str,
    fps: int,
    res: str,
    quality: str,
    seed: int,
    render_cache: str = "reuse",
    dry_run: bool = False,
    verbose: bool = False,
) -> str:
    """
    Render a single camera segment and return the path to the encoded .mp4.

    Returns:
        Path to the segment .mp4 file.
    """
    subdir_name = f"frames_seg{segment_index:03d}"

    result = run_render_step(
        run_dir=run_dir,
        blend_file=blend_file,
        config=config,
        duration_sec=0,                # unused when frame_start/end provided
        seed=seed,
        render_mode="loop",
        quality=quality,
        res=res,
        fps=fps,
        camera=camera,
        frame_start=frame_start,
        frame_end=frame_end,
        render_cache=render_cache,
        dry_run=dry_run,
        verbose=verbose,
        output_subdir=subdir_name,
    )

    # The video is in render_dir/output_loop.mp4 — rename for this segment
    render_dir   = Path(run_dir) / "render"
    generic_vid  = render_dir / "output_loop.mp4"
    segment_vid  = render_dir / f"segment_{segment_index:03d}.mp4"

    if not dry_run and generic_vid.exists() and not segment_vid.exists():
        generic_vid.rename(segment_vid)

    return str(segment_vid)


# ─── Camera listing ───────────────────────────────────────────────────────────

def list_cameras(theme_dir: Path, blend_file: Path, config: dict) -> list:
    """
    Return list of camera names for a theme.

    Priority:
    1. Read from themes/<theme>/cameras.yaml (fast, no Blender needed)
    2. Fall back: launch Blender in background with inspect_cameras.py
    """
    cameras_yaml = Path(theme_dir) / "cameras.yaml"

    if cameras_yaml.exists():
        import yaml
        with open(cameras_yaml, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        cameras = data.get("cameras", [])
        if cameras:
            return [c if isinstance(c, str) else c["name"] for c in cameras]

    # Fall back to Blender inspection
    return _inspect_cameras_via_blender(blend_file, config)


def _inspect_cameras_via_blender(blend_file: Path, config: dict) -> list:
    """
    Launch Blender in background with tools/blender/inspect_cameras.py
    to enumerate cameras in the blend file.
    """
    inspect_script = (
        Path(__file__).parent.parent.parent / "tools" / "blender" / "inspect_cameras.py"
    )
    blender_exe = _resolve_blender(config)

    if not Path(blender_exe).exists():
        print(f"[Render] Blender not found at {blender_exe} — cannot inspect cameras.")
        return []

    if not Path(blend_file).exists():
        print(f"[Render] blend file not found: {blend_file} — cannot inspect cameras.")
        return []

    print(f"[Render] Inspecting cameras via Blender (one-off background run)...")
    result = subprocess.run(
        [blender_exe, "-b", str(blend_file), "-P", str(inspect_script), "--"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    cameras = []
    for line in result.stdout.splitlines():
        if line.startswith("CAMERA:"):
            cameras.append(line.split("CAMERA:", 1)[1].strip())

    return cameras


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _resolve_blender(config: dict) -> str:
    return config.get("paths", {}).get("blender_exe", "blender") or "blender"


def _parse_resolution(res: str) -> tuple:
    """Parse '2560x1440' → (2560, 1440)."""
    try:
        w, h = res.lower().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        return 2560, 1440


def _load_quality_preset(quality: str) -> dict:
    """Load the quality preset from config/presets.yaml."""
    presets_path = Path(__file__).parent.parent.parent / "config" / "presets.yaml"
    try:
        import yaml
        with open(presets_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("quality", {}).get(quality, data["quality"]["balanced"])
    except Exception:
        # Fallback defaults
        defaults = {
            "fast":     {"blender_samples": 16,  "ffmpeg_crf": 28, "ffmpeg_preset": "ultrafast"},
            "balanced": {"blender_samples": 64,  "ffmpeg_crf": 18, "ffmpeg_preset": "slow"},
            "final":    {"blender_samples": 256, "ffmpeg_crf": 12, "ffmpeg_preset": "veryslow"},
        }
        return defaults.get(quality, defaults["balanced"])


def _render_outputs_exist(frames_dir: Path, render_dir: Path, render_mode: str) -> bool:
    """Return True if render outputs already exist for the given mode."""
    if render_mode in ("frames", "both"):
        return frames_dir.exists() and any(frames_dir.glob("*.png"))
    if render_mode == "loop":
        video = render_dir / "output_loop.mp4"
        return video.exists() and video.stat().st_size > 0
    return False


def _find_existing_video(render_dir: Path):
    """Return path to existing output_loop.mp4 if it exists, else None."""
    video = render_dir / "output_loop.mp4"
    return str(video) if video.exists() else None


def _build_blender_cmd(
    blender_exe, blend_file, frames_dir, blend_save,
    fps, duration_sec, res_x, res_y, samples, seed,
    engine, bloom, volumetrics, camera, frame_start, frame_end,
) -> list:
    render_script = str(_RENDER_SCRIPT)

    cmd = [
        blender_exe,
        "-b", blend_file,
        "-P", render_script,
        "--",
        "--output",      frames_dir,
        "--blend-save",  blend_save,
        "--fps",         str(fps),
        "--duration",    str(duration_sec),
        "--res-x",       str(res_x),
        "--res-y",       str(res_y),
        "--samples",     str(samples),
        "--seed",        str(seed),
        "--engine",      engine,
        "--bloom",       bloom,
        "--volumetrics", volumetrics,
    ]

    if camera and camera.lower() != "auto":
        cmd += ["--camera", camera]

    if frame_start is not None and frame_end is not None:
        cmd += ["--frame-start", str(frame_start), "--frame-end", str(frame_end)]

    return cmd


def _encode_frames_to_video(
    frames_dir: str,
    output_path: str,
    fps: int,
    crf: int,
    ffmpeg_preset: str,
    ffmpeg_exe: str,
) -> str:
    """Encode a PNG frame sequence to .mp4 using ffmpeg."""
    ffmpeg = ffmpeg_exe or "ffmpeg"

    if not Path(frames_dir).exists() or not any(Path(frames_dir).glob("*.png")):
        print(f"[Render] No frames found in {frames_dir} — skipping video encode.")
        return None

    print(f"[Render] Encoding frames → {output_path}")

    cmd = [
        ffmpeg, "-y",
        "-framerate", str(fps),
        "-i", os.path.join(frames_dir, "%04d.png"),
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", ffmpeg_preset,
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print("[Render] ffmpeg encode FAILED:")
        print(result.stderr[-2000:])
        raise RuntimeError(f"[Render] ffmpeg exited with code {result.returncode}.")

    return output_path
