"""
music_engine/generator.py
──────────────────────────
Generates the ambient audio track and exports stems/MIDI/mix into the
run's music/ directory layout:

    runs/<run_id>/music/
        stems/          ← per-instrument WAV stems
        midi/           ← MIDI exports (placeholder .mid files)
        meta/           ← sections.csv, tempo_map.json
        full_mix.wav    ← combined stereo mix

Current state: V1 sine-wave placeholder that produces a valid stereo WAV.
               The function signature and output contract are already
               designed for MusicGen — wiring it in later is a one-block swap.

Upgrade path to MusicGen (when ready):
    pip install audiocraft
    → Replace the _generate_placeholder() call with _generate_musicgen()
    → Everything else (paths, config, stereo, duration) stays identical.
"""

import os
import csv
import json
import wave
import struct
import random
import shutil
import numpy as np
from pathlib import Path


def generate_music_assets(
    music_dir: str | Path,
    config: dict,
    duration_sec: int,
    seed: int,
) -> dict:
    """
    Generate all music assets into *music_dir*.

    Creates:
        stems/main_mix.wav      — the full mix as the primary stem
        midi/main.mid           — placeholder standard MIDI file
        meta/sections.csv       — section markers
        meta/tempo_map.json     — tempo / key information
        full_mix.wav            — copy of stems/main_mix.wav

    Args:
        music_dir:    Path to runs/<run_id>/music/
        config:       Full config dict from config_loader.load_config().
        duration_sec: Duration in seconds.
        seed:         Integer seed for reproducibility.

    Returns:
        dict with keys: full_mix, stems_dir, midi_dir, meta_dir
    """
    music_dir = Path(music_dir)
    stems_dir = music_dir / "stems"
    midi_dir  = music_dir / "midi"
    meta_dir  = music_dir / "meta"
    edited_dir = music_dir / "edited"

    for d in (stems_dir, midi_dir, meta_dir, edited_dir):
        d.mkdir(parents=True, exist_ok=True)

    sample_rate = config["audio"]["sample_rate"]
    channels    = config["audio"]["channels"]
    prompt      = _resolve_prompt(config)

    print(f"[Music] Theme   : {config['theme']}")
    print(f"[Music] Prompt  : {prompt}")
    print(f"[Music] Duration: {duration_sec // 60} min {duration_sec % 60}s ({duration_sec}s total)")
    print(f"[Music] Seed    : {seed}")
    print(f"[Music] Output  : {music_dir}")

    # ── Swap this block when MusicGen is installed ──────────────────────────
    audio_data = _generate_placeholder(
        duration_sec=duration_sec,
        sample_rate=sample_rate,
        channels=channels,
        seed=seed,
    )
    # ── End swappable block ─────────────────────────────────────────────────

    stem_path  = str(stems_dir / "main_mix.wav")
    mix_path   = str(music_dir / "full_mix.wav")

    _write_wav(stem_path, audio_data, sample_rate, channels)
    shutil.copy2(stem_path, mix_path)

    midi_path = str(midi_dir / "main.mid")
    _write_placeholder_midi(midi_path, duration_sec, seed)

    _write_meta(meta_dir, duration_sec, seed, config)

    size_mb = os.path.getsize(mix_path) / (1024 * 1024)
    print(f"[Music] Done — {size_mb:.1f} MB full mix at {mix_path}")
    print(f"[Music] Stems : {stems_dir}")
    print(f"[Music] MIDI  : {midi_path}")
    print(f"[Music] Meta  : {meta_dir}")

    # Remind user where to place FL Studio exports
    notes_path = edited_dir / "notes.txt"
    if not notes_path.exists():
        notes_path.write_text(
            "Place your FL Studio / DAW export here as:\n"
            "    final_from_fl.wav\n\n"
            "This file will automatically be used instead of full_mix.wav\n"
            "when you run:  python master_run.py --mode assemble --run-id <id>\n",
            encoding="utf-8",
        )

    return {
        "full_mix": mix_path,
        "stems_dir": str(stems_dir),
        "midi_dir": str(midi_dir),
        "meta_dir": str(meta_dir),
    }


def generate_audio(output_path: str, config: dict) -> str:
    """
    Legacy single-file entry point (kept for backward compatibility).
    Writes a single WAV to output_path.
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

    audio_data = _generate_placeholder(
        duration_sec=duration_sec,
        sample_rate=sample_rate,
        channels=channels,
        seed=seed,
    )

    _write_wav(output_path, audio_data, sample_rate, channels)

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
    freqs   = [27.5, 55.0, 82.5, 110.0, 137.5]
    weights = [0.35, 0.25, 0.15, 0.15,  0.10]

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
#
#     torch.manual_seed(seed)
#     model = MusicGen.get_pretrained(model_name)
#
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


# ─── MIDI placeholder ─────────────────────────────────────────────────────────

def _write_placeholder_midi(path: str, duration_sec: int, seed: int):
    """
    Write a minimal valid Standard MIDI File (format 0, 1 track).
    This is a placeholder — replace with real MIDI generation later.
    The file is valid and can be opened in a DAW.
    """
    rng = random.Random(seed)

    # MIDI tempo in microseconds per beat (120 BPM = 500000 us/beat)
    tempo_us = 500000  # 120 BPM

    def var_len(value: int) -> bytes:
        """Encode integer as MIDI variable-length quantity."""
        result = [value & 0x7F]
        value >>= 7
        while value:
            result.append((value & 0x7F) | 0x80)
            value >>= 7
        return bytes(reversed(result))

    # Build track events
    events = bytearray()

    # Tempo event at tick 0
    events += b"\x00\xFF\x51\x03"
    events += struct.pack(">I", tempo_us)[1:]  # 3 bytes, big-endian

    # One sustained root note (A2 = MIDI note 45) for the full duration
    ticks_per_beat = 480
    total_ticks = int((duration_sec / (tempo_us / 1_000_000)) * ticks_per_beat)
    note = 45  # A2 — matches drone frequencies

    # Note on at tick 0
    events += b"\x00\x90" + bytes([note, 64])

    # Note off at end
    events += var_len(total_ticks) + b"\x80" + bytes([note, 0])

    # End of track
    events += b"\x00\xFF\x2F\x00"

    # Build MIDI file
    header = b"MThd\x00\x00\x00\x06\x00\x00\x00\x01"  # format 0, 1 track
    header += struct.pack(">H", ticks_per_beat)

    track_data = bytes(events)
    track = b"MTrk" + struct.pack(">I", len(track_data)) + track_data

    with open(path, "wb") as f:
        f.write(header + track)


# ─── Metadata writers ─────────────────────────────────────────────────────────

def _write_meta(meta_dir: Path, duration_sec: int, seed: int, config: dict):
    """Write sections.csv and tempo_map.json."""
    # Simple section breakdown: intro → main → outro
    sections = [
        {"name": "intro",  "start_sec": 0,                    "end_sec": min(60, duration_sec // 10)},
        {"name": "main",   "start_sec": min(60, duration_sec // 10), "end_sec": max(0, duration_sec - 60)},
        {"name": "outro",  "start_sec": max(0, duration_sec - 60),   "end_sec": duration_sec},
    ]

    csv_path = meta_dir / "sections.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "start_sec", "end_sec"])
        writer.writeheader()
        writer.writerows(sections)

    tempo_map = {
        "bpm": 120,
        "key": "A minor",
        "seed": seed,
        "duration_sec": duration_sec,
        "sections": sections,
        "generator": "placeholder_v1",
    }

    json_path = meta_dir / "tempo_map.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(tempo_map, f, indent=2)


# ─── Prompt resolution ────────────────────────────────────────────────────────

def _resolve_prompt(config: dict) -> str:
    """
    Try to load the prompt from the active theme's prompts.yaml.
    Falls back to config audio.fallback_prompt if not found.
    """
    import yaml

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
