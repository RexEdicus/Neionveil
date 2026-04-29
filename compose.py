"""
composer/compose.py
────────────────────
Combines the PNG image sequence + WAV audio into the final .mp4.

Uses subprocess (not os.system) so we can:
  - Capture stdout/stderr
  - Detect failures and raise proper exceptions
  - Handle paths with spaces safely

Output contract:
  - Final .mp4 at 1440p, H.264 video, AAC audio at configured bitrate
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
) -> str:
    """
    Merge audio + PNG frame sequence into final .mp4.

    Args:
        audio_path:  Path to the .wav audio file.
        frames_dir:  Path to folder containing ####.png frames.
        output_path: Destination .mp4 path.
        config:      Full config dict.

    Returns:
        output_path on success. Raises RuntimeError on ffmpeg failure.
    """
    fps          = config["video"]["fps"]
    audio_bitrate = config["audio"]["encode_bitrate"]

    _check_ffmpeg()
    _check_inputs(audio_path, frames_dir)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"[Compose] Audio   : {audio_path}")
    print(f"[Compose] Frames  : {frames_dir}")
    print(f"[Compose] Output  : {output_path}")
    print(f"[Compose] FPS     : {fps}")

    cmd = [
        "ffmpeg",
        "-y",                              # Overwrite output without asking

        # Video input — PNG image sequence
        "-framerate", str(fps),
        "-i", os.path.join(frames_dir, "%04d.png"),

        # Audio input
        "-i", str(audio_path),

        # Video codec
        "-c:v", "libx264",
        "-crf", "18",                      # Quality: 0=lossless, 23=default, 51=worst
        "-preset", "slow",                 # Better compression at same quality
        "-pix_fmt", "yuv420p",             # Required for YouTube compatibility
        "-colorspace", "bt709",            # Correct color space for 1080p+

        # Audio codec
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-ar", "44100",                    # Resample to 44.1kHz for compatibility

        # Use shortest stream (video) to set output length
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


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _check_ffmpeg():
    """Verify ffmpeg is installed and on PATH before attempting to use it."""
    result = subprocess.run(
        ["ffmpeg", "-version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise EnvironmentError(
            "[Compose] ffmpeg not found. Install it and make sure it's on your PATH.\n"
            "Download: https://ffmpeg.org/download.html\n"
            "On Windows, add ffmpeg/bin to your system PATH environment variable."
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
