"""
composer/compose.py
────────────────────
Combines an audio file + PNG image sequence (or video) into the final .mp4.

Uses subprocess (not os.system) so we can:
  - Capture stdout/stderr
  - Detect failures and raise proper exceptions
  - Handle paths with spaces safely

Output contract:
  - Final .mp4 at configured resolution, H.264 video, AAC audio
  - CRF 18 = visually near-lossless (good for ambient content with
    subtle gradients — lower CRF = better quality, larger file)
"""

import os
import subprocess
from pathlib import Path


def compose(
    audio_path: str,
    frames_dir: str,
    output_path: str,
    config: dict,
    ffmpeg_exe: str = None,
    crf: int = 18,
    preset: str = "slow",
    audio_bitrate: str = None,
) -> str:
    """
    Merge audio + PNG frame sequence into final .mp4.

    Args:
        audio_path:    Path to the .wav (or .mp3) audio file.
        frames_dir:    Path to folder containing ####.png frames.
        output_path:   Destination .mp4 path.
        config:        Full config dict.
        ffmpeg_exe:    Path to ffmpeg executable (overrides config/PATH).
        crf:           ffmpeg CRF quality value (lower = better).
        preset:        ffmpeg encoding preset.
        audio_bitrate: AAC bitrate string (e.g. "320k").

    Returns:
        output_path on success. Raises RuntimeError on ffmpeg failure.
    """
    fps           = config["video"]["fps"]
    audio_bitrate = audio_bitrate or config["audio"]["encode_bitrate"]
    exe           = _resolve_ffmpeg(config, ffmpeg_exe)

    _check_ffmpeg(exe)
    _check_inputs(audio_path, frames_dir)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    print(f"[Compose] Audio   : {audio_path}")
    print(f"[Compose] Frames  : {frames_dir}")
    print(f"[Compose] Output  : {output_path}")
    print(f"[Compose] FPS     : {fps}")
    print(f"[Compose] CRF     : {crf}  Preset: {preset}")

    cmd = [
        exe,
        "-y",                              # Overwrite output without asking

        # Video input — PNG image sequence
        "-framerate", str(fps),
        "-i", os.path.join(frames_dir, "%04d.png"),

        # Audio input
        "-i", str(audio_path),

        # Video codec
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-pix_fmt", "yuv420p",             # Required for YouTube compatibility
        "-colorspace", "bt709",            # Correct color space for 1080p+

        # Audio codec
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-ar", "44100",                    # Resample to 44.1kHz for compatibility

        # Use shortest stream to set output length
        "-shortest",

        str(output_path),
    ]

    print("[Compose] Running ffmpeg...")
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        print("[Compose] ffmpeg FAILED. stderr output:")
        print(result.stderr[-3000:])       # Last 3000 chars — ffmpeg is verbose
        raise RuntimeError(
            f"[Compose] ffmpeg exited with code {result.returncode}. "
            f"Check output above for details."
        )

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[Compose] Done — {size_mb:.0f} MB → {output_path}")
    return output_path


def compose_from_video(
    audio_path: str,
    video_path: str,
    output_path: str,
    config: dict,
    ffmpeg_exe: str = None,
    crf: int = 18,
    preset: str = "slow",
    audio_bitrate: str = None,
) -> str:
    """
    Merge audio + an existing video file into final .mp4.
    Used when the render step already produced a video (not PNG frames).
    """
    audio_bitrate = audio_bitrate or config["audio"]["encode_bitrate"]
    exe           = _resolve_ffmpeg(config, ffmpeg_exe)

    _check_ffmpeg(exe)

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"[Compose] Audio file not found: {audio_path}")
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"[Compose] Video file not found: {video_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    print(f"[Compose] Audio : {audio_path}")
    print(f"[Compose] Video : {video_path}")
    print(f"[Compose] Output: {output_path}")

    cmd = [
        exe, "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-ar", "44100",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        str(output_path),
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        print("[Compose] ffmpeg FAILED. stderr:")
        print(result.stderr[-3000:])
        raise RuntimeError(f"[Compose] ffmpeg exited with code {result.returncode}.")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[Compose] Done — {size_mb:.0f} MB → {output_path}")
    return output_path


def concat_segments(
    segment_paths: list,
    output_path: str,
    config: dict,
    ffmpeg_exe: str = None,
    cut_style: str = "hard",
    cut_fade: float = 1.0,
    audio_bitrate: str = None,
) -> str:
    """
    Concatenate multiple video segments into one file.

    Args:
        segment_paths: List of .mp4 file paths to concatenate in order.
        output_path:   Destination .mp4 path.
        config:        Full config dict.
        ffmpeg_exe:    Path to ffmpeg executable (overrides config/PATH).
        cut_style:     "hard" or "crossfade".
        cut_fade:      Crossfade duration in seconds (only for crossfade).
        audio_bitrate: AAC bitrate string.

    Returns:
        output_path on success.
    """
    exe = _resolve_ffmpeg(config, ffmpeg_exe)
    _check_ffmpeg(exe)

    if not segment_paths:
        raise ValueError("[Compose] No segments provided to concatenate.")

    if len(segment_paths) == 1:
        import shutil
        shutil.copy2(segment_paths[0], output_path)
        print(f"[Compose] Single segment — copied to {output_path}")
        return output_path

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if cut_style == "crossfade":
        return _concat_crossfade(segment_paths, output_path, exe, cut_fade, audio_bitrate, config)
    else:
        return _concat_hard(segment_paths, output_path, exe, audio_bitrate, config)


def _concat_hard(segment_paths, output_path, exe, audio_bitrate, config):
    """Hard-cut concatenation via ffmpeg concat demuxer."""
    import tempfile

    audio_bitrate = audio_bitrate or config["audio"]["encode_bitrate"]

    # Write concat file list
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        for p in segment_paths:
            # ffmpeg concat list requires forward slashes or escaped backslashes
            safe = str(p).replace("\\", "/")
            tf.write(f"file '{safe}'\n")
        concat_file = tf.name

    try:
        cmd = [
            exe, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-b:a", audio_bitrate,
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        print(f"[Compose] Hard-cut concat: {len(segment_paths)} segments → {output_path}")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode != 0:
            print("[Compose] ffmpeg concat FAILED:")
            print(result.stderr[-3000:])
            raise RuntimeError(f"[Compose] concat exited with code {result.returncode}.")
    finally:
        os.unlink(concat_file)

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[Compose] Concat done — {size_mb:.0f} MB → {output_path}")
    return output_path


def _concat_crossfade(segment_paths, output_path, exe, cut_fade, audio_bitrate, config):
    """
    Crossfade concatenation using xfade + acrossfade filters.
    Works for any number of segments by chaining filters.
    """
    audio_bitrate = audio_bitrate or config["audio"]["encode_bitrate"]
    n = len(segment_paths)

    # Build complex ffmpeg filter graph for n segments with crossfades
    inputs = []
    for p in segment_paths:
        inputs += ["-i", str(p)]

    # Get duration of each segment (needed for xfade offset calculation)
    durations = []
    for p in segment_paths:
        dur = _get_video_duration(p, exe)
        durations.append(dur)

    # Build xfade + acrossfade filter chain
    # For n inputs: chain n-1 crossfades
    vfilters = []
    afilters = []

    # Label inputs
    vstreams = [f"[{i}:v]" for i in range(n)]
    astreams = [f"[{i}:a]" for i in range(n)]

    offset = 0.0
    for i in range(n - 1):
        offset += durations[i] - cut_fade
        offset = max(0.0, offset)

        out_v = f"[v{i}]" if i < n - 2 else "[vout]"
        out_a = f"[a{i}]" if i < n - 2 else "[aout]"

        in_v1 = vstreams[i] if i == 0 else f"[v{i-1}]"
        in_a1 = astreams[i] if i == 0 else f"[a{i-1}]"

        vfilters.append(
            f"{in_v1}{vstreams[i+1]}xfade=transition=fade:duration={cut_fade}:offset={offset:.3f}{out_v}"
        )
        afilters.append(
            f"{in_a1}{astreams[i+1]}acrossfade=d={cut_fade}{out_a}"
        )

    filter_complex = ";".join(vfilters + afilters)

    cmd = (
        [exe, "-y"]
        + inputs
        + [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", audio_bitrate,
            str(output_path),
        ]
    )

    print(f"[Compose] Crossfade concat: {n} segments, {cut_fade}s fade → {output_path}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        print("[Compose] ffmpeg crossfade FAILED:")
        print(result.stderr[-3000:])
        raise RuntimeError(f"[Compose] crossfade exited with code {result.returncode}.")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[Compose] Crossfade done — {size_mb:.0f} MB → {output_path}")
    return output_path


def _get_video_duration(path: str, ffmpeg_exe: str) -> float:
    """Return video duration in seconds using ffprobe."""
    # Try ffprobe (sibling to ffmpeg)
    ffprobe = str(Path(ffmpeg_exe).parent / "ffprobe")
    if not Path(ffprobe).exists():
        ffprobe = "ffprobe"  # try PATH

    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _resolve_ffmpeg(config: dict, override: str = None) -> str:
    """Resolve ffmpeg executable: override > config paths > 'ffmpeg' on PATH."""
    if override:
        return override
    return config.get("paths", {}).get("ffmpeg_exe", "ffmpeg") or "ffmpeg"


def _check_ffmpeg(exe: str):
    """Verify ffmpeg is reachable before attempting to use it."""
    result = subprocess.run(
        [exe, "-version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise EnvironmentError(
            f"[Compose] ffmpeg not found or failed at: {exe}\n"
            "Install ffmpeg and set paths.ffmpeg_exe in config/config.yaml, or\n"
            "add ffmpeg/bin to your system PATH environment variable.\n"
            "Download: https://ffmpeg.org/download.html"
        )


def _check_inputs(audio_path: str, frames_dir: str):
    """Verify both inputs exist before attempting compose."""
    if not os.path.exists(audio_path):
        raise FileNotFoundError(
            f"[Compose] Audio file not found: {audio_path}\n"
            f"Music generation may have failed — check music_engine logs."
        )

    frames = list(Path(frames_dir).glob("*.png"))
    if not frames:
        raise FileNotFoundError(
            f"[Compose] No PNG frames found in: {frames_dir}\n"
            f"Blender render may have failed — check render_engine logs."
        )

    print(f"[Compose] Found {len(frames)} frames in {frames_dir}")
