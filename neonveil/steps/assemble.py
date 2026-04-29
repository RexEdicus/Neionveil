"""
neonveil/steps/assemble.py
───────────────────────────
"Assemble" pipeline step.

Responsibilities:
  1. Resolve the audio file to use (edited override → full_mix.wav fallback).
  2. Resolve the .blend file to use (edited override → scene_used.blend fallback).
  3. Render (if needed: camera-mode=cuts → per-segment renders; else single render).
  4. Concatenate segments with ffmpeg (hard cut or crossfade).
  5. Mux audio + video → runs/<run_id>/video/final_youtube.mp4.

Called by the orchestrator for --mode full and --mode assemble.
"""

import os
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def run_assemble_step(
    run_dir: Path,
    config: dict,
    duration_sec: int,
    seed: int,
    render_mode: str = "loop",
    quality: str = "balanced",
    res: str = "2560x1440",
    fps: int = 30,
    camera_mode: str = "continuous",
    camera: str = "auto",
    camera_sequence: list = None,
    cut_every: int = 240,
    cut_style: str = "hard",
    cut_fade: float = 1.0,
    blend_file_override: str = None,
    audio_file_override: str = None,
    render_cache: str = "reuse",
    dry_run: bool = False,
    verbose: bool = False,
) -> str:
    """
    Execute the assemble step and produce the final YouTube MP4.

    Args:
        run_dir:              Path to runs/<run_id>/.
        config:               Full config dict.
        duration_sec:         Total duration in seconds (from manifest or CLI).
        seed:                 Render seed.
        render_mode:          "loop" | "frames" | "both" | "off".
        quality:              Quality preset name.
        res:                  Resolution string.
        fps:                  Frames per second.
        camera_mode:          "continuous" | "cuts".
        camera:               Camera name for continuous mode.
        camera_sequence:      List of camera names for cuts mode.
        cut_every:            Seconds per camera segment.
        cut_style:            "hard" | "crossfade".
        cut_fade:             Crossfade duration in seconds.
        blend_file_override:  Explicit .blend path (skips auto-selection).
        audio_file_override:  Explicit audio path (skips auto-selection).
        render_cache:         "reuse" | "rerender".
        dry_run:              Print actions only.
        verbose:              Extra logging.

    Returns:
        Path to the final MP4.
    """
    run_dir = Path(run_dir)
    video_dir = run_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    final_mp4 = str(video_dir / "final_youtube.mp4")

    # ── 1. Resolve audio file ────────────────────────────────────────────────
    audio_path = _resolve_audio(run_dir, audio_file_override)
    print(f"[Assemble] Audio  : {audio_path}")

    # ── 2. Resolve .blend file ───────────────────────────────────────────────
    blend_path = _resolve_blend(run_dir, blend_file_override)
    print(f"[Assemble] Blend  : {blend_path}")

    if render_mode == "off":
        # Reuse an existing render without re-rendering
        existing_video = _find_existing_render_video(run_dir)
        if existing_video:
            print(f"[Assemble] render-mode=off — reusing {existing_video}")
            return _mux_audio_video(
                audio_path=audio_path,
                video_path=existing_video,
                output_path=final_mp4,
                config=config,
                dry_run=dry_run,
            )
        else:
            print("[Assemble] render-mode=off but no existing render found. Skipping video.")
            return None

    # ── 3. Render ─────────────────────────────────────────────────────────────
    from neonveil.steps.render import run_render_step, render_segment

    if camera_mode == "cuts":
        final_mp4 = _assemble_with_cuts(
            run_dir=run_dir,
            blend_path=blend_path,
            audio_path=audio_path,
            config=config,
            duration_sec=duration_sec,
            seed=seed,
            fps=fps,
            res=res,
            quality=quality,
            camera_sequence=camera_sequence,
            cut_every=cut_every,
            cut_style=cut_style,
            cut_fade=cut_fade,
            render_cache=render_cache,
            dry_run=dry_run,
            verbose=verbose,
            final_mp4=final_mp4,
        )
    else:
        # Continuous: single render with one camera
        render_result = run_render_step(
            run_dir=run_dir,
            blend_file=blend_path,
            config=config,
            duration_sec=duration_sec,
            seed=seed,
            render_mode=render_mode,
            quality=quality,
            res=res,
            fps=fps,
            camera=camera,
            render_cache=render_cache,
            dry_run=dry_run,
            verbose=verbose,
        )

        render_video = render_result.get("video_path")
        frames_dir   = render_result.get("frames_dir")

        if dry_run:
            print(f"[DryRun] Would mux {audio_path} + video → {final_mp4}")
            return final_mp4

        if render_video and os.path.exists(render_video):
            final_mp4 = _mux_audio_video(
                audio_path=audio_path,
                video_path=render_video,
                output_path=final_mp4,
                config=config,
                dry_run=dry_run,
            )
        elif frames_dir and os.path.exists(frames_dir):
            from composer.compose import compose
            from neonveil.steps.render import _load_quality_preset
            preset = _load_quality_preset(quality)
            final_mp4 = compose(
                audio_path=audio_path,
                frames_dir=frames_dir,
                output_path=final_mp4,
                config=config,
                ffmpeg_exe=config.get("paths", {}).get("ffmpeg_exe"),
                crf=preset.get("ffmpeg_crf", 18),
                preset=preset.get("ffmpeg_preset", "slow"),
            )
        else:
            raise RuntimeError(
                "[Assemble] No render output found (no video or frames). "
                "Try --render-cache rerender."
            )

    return final_mp4


# ─── Camera-cuts assembly ─────────────────────────────────────────────────────

def _assemble_with_cuts(
    run_dir, blend_path, audio_path, config, duration_sec, seed, fps, res,
    quality, camera_sequence, cut_every, cut_style, cut_fade, render_cache,
    dry_run, verbose, final_mp4,
):
    """Render per-segment with different cameras, then concatenate + mux audio."""
    from neonveil.steps.render import render_segment, _load_quality_preset

    total_frames = duration_sec * fps
    segment_frames = cut_every * fps
    segments = _build_segments(total_frames, segment_frames, camera_sequence, fps)

    print(f"[Assemble] Camera mode: cuts — {len(segments)} segments")
    for i, (fs, fe, cam) in enumerate(segments, 1):
        duration_s = (fe - fs + 1) / fps
        print(f"[Assemble]   Segment {i:3d}: frames {fs}–{fe} ({duration_s:.0f}s) → camera={cam}")

    if dry_run:
        print(f"[DryRun] Would render {len(segments)} segments and concat → {final_mp4}")
        return final_mp4

    segment_videos = []
    for i, (frame_start, frame_end, cam) in enumerate(segments, 1):
        print(f"\n[Assemble] Rendering segment {i}/{len(segments)} (camera={cam})...")
        seg_video = render_segment(
            run_dir=run_dir,
            blend_file=blend_path,
            config=config,
            segment_index=i,
            frame_start=frame_start,
            frame_end=frame_end,
            camera=cam,
            fps=fps,
            res=res,
            quality=quality,
            seed=seed,
            render_cache=render_cache,
            dry_run=dry_run,
            verbose=verbose,
        )
        segment_videos.append(seg_video)
        print(f"[Assemble] Segment {i} done → {seg_video}")

    # Concatenate segments (video only, no audio yet)
    render_dir    = Path(run_dir) / "render"
    combined_vid  = str(render_dir / "combined_segments.mp4")

    from composer.compose import concat_segments
    preset = _load_quality_preset(quality)

    concat_segments(
        segment_paths=segment_videos,
        output_path=combined_vid,
        config=config,
        ffmpeg_exe=config.get("paths", {}).get("ffmpeg_exe"),
        cut_style=cut_style,
        cut_fade=cut_fade,
        audio_bitrate=preset.get("ffmpeg_audio_bitrate", "320k"),
    )

    # Mux audio into combined video
    return _mux_audio_video(
        audio_path=audio_path,
        video_path=combined_vid,
        output_path=final_mp4,
        config=config,
        dry_run=dry_run,
    )


def _build_segments(total_frames: int, segment_frames: int, camera_sequence: list, fps: int):
    """
    Build list of (frame_start, frame_end, camera_name) tuples.
    Cycles through camera_sequence in order (never random).
    """
    if not camera_sequence:
        camera_sequence = ["auto"]

    segments = []
    frame = 1
    idx   = 0

    while frame <= total_frames:
        fs  = frame
        fe  = min(frame + segment_frames - 1, total_frames)
        cam = camera_sequence[idx % len(camera_sequence)]
        segments.append((fs, fe, cam))
        frame += segment_frames
        idx   += 1

    return segments


# ─── Audio / blend resolution ─────────────────────────────────────────────────

def _resolve_audio(run_dir: Path, override: str = None) -> str:
    """
    Resolve audio file to use for assembly.

    Priority:
    1. Explicit --audio-file override
    2. runs/<run_id>/music/edited/final_from_fl.wav  (user edit)
    3. runs/<run_id>/music/full_mix.wav              (auto-generated)
    """
    if override:
        if not os.path.exists(override):
            raise FileNotFoundError(f"[Assemble] Specified --audio-file not found: {override}")
        return override

    edited = run_dir / "music" / "edited" / "final_from_fl.wav"
    if edited.exists():
        print(f"[Assemble] Using edited audio: {edited}")
        return str(edited)

    full_mix = run_dir / "music" / "full_mix.wav"
    if full_mix.exists():
        return str(full_mix)

    raise FileNotFoundError(
        f"[Assemble] No audio file found in {run_dir / 'music'}.\n"
        f"Expected: {full_mix}\n"
        f"Or place your FL Studio export at: {edited}\n"
        f"Or use: --audio-file <path>"
    )


def _resolve_blend(run_dir: Path, override: str = None) -> str:
    """
    Resolve .blend file to use for rendering.

    Priority:
    1. Explicit --blend-file override
    2. runs/<run_id>/render/edited/scene_edited.blend  (user edit)
    3. runs/<run_id>/render/scene_used.blend           (auto-generated)
    """
    if override:
        if not os.path.exists(override):
            raise FileNotFoundError(f"[Assemble] Specified --blend-file not found: {override}")
        return override

    edited = run_dir / "render" / "edited" / "scene_edited.blend"
    if edited.exists():
        print(f"[Assemble] Using edited blend: {edited}")
        return str(edited)

    used = run_dir / "render" / "scene_used.blend"
    if used.exists():
        return str(used)

    raise FileNotFoundError(
        f"[Assemble] No .blend file found in {run_dir / 'render'}.\n"
        f"Expected: {used}\n"
        f"Or place your edited blend at: {edited}\n"
        f"Or use: --blend-file <path>"
    )


def _find_existing_render_video(run_dir: Path):
    """Return path to existing output_loop.mp4 if it exists."""
    video = run_dir / "render" / "output_loop.mp4"
    return str(video) if video.exists() else None


def _mux_audio_video(audio_path, video_path, output_path, config, dry_run=False):
    """Mux audio + video into the final MP4."""
    if dry_run:
        print(f"[DryRun] Would mux: {audio_path} + {video_path} → {output_path}")
        return output_path

    from composer.compose import compose_from_video
    from neonveil.steps.render import _load_quality_preset

    quality_name = "balanced"   # default; caller should pass quality if needed
    preset = _load_quality_preset(quality_name)

    return compose_from_video(
        audio_path=audio_path,
        video_path=video_path,
        output_path=output_path,
        config=config,
        ffmpeg_exe=config.get("paths", {}).get("ffmpeg_exe"),
        crf=preset.get("ffmpeg_crf", 18),
        preset=preset.get("ffmpeg_preset", "slow"),
    )
