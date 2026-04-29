"""
music_engine/generator.py
──────────────────────────
Generates the ambient audio track.

Current state: V1 sine-wave placeholder that produces a valid stereo WAV.
               The function signature and output contract are already
               designed for MusicGen — wiring it in later is a one-block swap.

Upgrade path to MusicGen (when ready):
    pip install audiocraft
    → Replace the _generate_placeholder() call with _generate_musicgen()
    → Everything else (paths, config, stereo, duration) stays identical.
"""

import os
import wave
import struct
import random
import numpy as np
from pathlib import Path


def generate_audio(output_path: str, config: dict) -> str:
    """
    Main entry point. Called by master_run.py.

    Args:
        output_path: Full path where the .wav file will be saved.
        config:      Full config dict from config_loader.load_config().

    Returns:
        output_path on success. Raises on failure.
    """
    sample_rate  = config["audio"]["sample_rate"]
    channels     = config["audio"]["channels"]
    duration_sec = config["video"]["duration_minutes"] * 60
    seed         = config["seed"]
    prompt       = _resolve_prompt(config)

    print(f"[Music] Theme   : {config['theme']}")
    print(f"[Music] Prompt  : {prompt}")
    print(f"[Music] Duration: {duration_sec // 60} min ({duration_sec}s)")
    print(f"[Music] Seed    : {seed}")
    print(f"[Music] Output  : {output_path}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # ── Swap this block when MusicGen is installed ──────────────────────────
    audio_data = _generate_placeholder(
        duration_sec=duration_sec,
        sample_rate=sample_rate,
        channels=channels,
        seed=seed,
    )
    # ── End swappable block ─────────────────────────────────────────────────

    _write_wav(
        path=output_path,
        audio=audio_data,
        sample_rate=sample_rate,
        channels=channels,
    )

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[Music] Done — {size_mb:.1f} MB written to {output_path}")
    return output_path


# ─── Placeholder generator ────────────────────────────────────────────────────

def _generate_placeholder(
    duration_sec: int,
    sample_rate: int,
    channels: int,
    seed: int,
) -> np.ndarray:
    """
    Produces a dark ambient drone using layered sine waves.
    This is V1 — it sounds minimal but is a valid stereo WAV the
    whole pipeline can process end-to-end for testing.

    Returns:
        numpy array of shape (samples, channels), dtype float32, range [-1, 1]
    """
    rng = np.random.default_rng(seed)
    n_samples = int(sample_rate * duration_sec)
    t = np.linspace(0, duration_sec, n_samples, dtype=np.float32)

    # Fundamental drone frequencies (dark, low)
    freqs = [27.5, 55.0, 82.5, 110.0, 137.5]
    weights = [0.35, 0.25, 0.15, 0.15, 0.10]

    mono = np.zeros(n_samples, dtype=np.float32)
    for freq, w in zip(freqs, weights):
        # Slight per-harmonic detuning for organic movement
        detune = rng.uniform(-0.08, 0.08)
        phase  = rng.uniform(0, 2 * np.pi)
        mono  += w * np.sin(2 * np.pi * (freq + detune) * t + phase)

    # Slow amplitude modulation — gives the breathing / pulsing quality
    lfo_rate = rng.uniform(0.03, 0.07)
    lfo = 0.85 + 0.15 * np.sin(2 * np.pi * lfo_rate * t)
    mono *= lfo

    # Stereo spread — slightly different phase per channel for width
    if channels == 2:
        phase_spread = rng.uniform(0.002, 0.006)
        right_shift  = int(sample_rate * phase_spread)
        left  = mono.copy()
        right = np.roll(mono, right_shift)
        audio = np.stack([left, right], axis=1)
    else:
        audio = mono.reshape(-1, 1)

    # Normalise to -1 dB headroom
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio * (0.891 / peak)

    return audio


# ─── MusicGen stub (uncomment when audiocraft is installed) ───────────────────

# def _generate_musicgen(
#     prompt: str,
#     duration_sec: int,
#     sample_rate: int,
#     channels: int,
#     seed: int,
#     model_name: str,
# ) -> np.ndarray:
#     import torch
#     from audiocraft.models import MusicGen
#     from audiocraft.data.audio import audio_write
#
#     torch.manual_seed(seed)
#     model = MusicGen.get_pretrained(model_name)
#
#     # MusicGen max single segment is 30s — for long audio we generate in
#     # segments and concatenate. Set chunk to 30s.
#     chunk_sec = 30
#     n_chunks  = duration_sec // chunk_sec
#
#     model.set_generation_params(duration=chunk_sec)
#     segments = []
#
#     print(f"[Music] Generating {n_chunks} × {chunk_sec}s segments...")
#     for i in range(n_chunks):
#         print(f"[Music] Segment {i+1}/{n_chunks}")
#         wav = model.generate([prompt])      # shape: (1, channels, samples)
#         segments.append(wav[0].cpu().numpy())
#
#     audio = np.concatenate(segments, axis=-1)  # (channels, total_samples)
#     audio = audio.T                             # → (total_samples, channels)
#     return audio.astype(np.float32)


# ─── WAV writer ───────────────────────────────────────────────────────────────

def _write_wav(path: str, audio: np.ndarray, sample_rate: int, channels: int):
    """Write float32 numpy array to 16-bit PCM WAV."""
    pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16)

    with wave.open(path, "w") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)          # 16-bit = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


# ─── Prompt resolution ────────────────────────────────────────────────────────

def _resolve_prompt(config: dict) -> str:
    """
    Try to load the prompt from the active theme's prompts.yaml.
    Falls back to config audio.fallback_prompt if not found.
    """
    import yaml
    from pathlib import Path

    theme_dir = (
        Path(__file__).parent.parent
        / config["paths"]["themes_dir"]
        / config["theme"]
    )
    prompts_file = theme_dir / "prompts.yaml"

    if prompts_file.exists():
        with open(prompts_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        prompt = data.get("music_prompt", config["audio"]["fallback_prompt"])
    else:
        prompt = config["audio"]["fallback_prompt"]
        print(f"[Music] No theme prompts.yaml found — using fallback prompt")

    return prompt
