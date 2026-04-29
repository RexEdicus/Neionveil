"""
master_run.py
──────────────
The single entry point for the entire Neonveil pipeline.

Usage:
    python master_run.py                          # Uses config defaults
    python master_run.py --theme void_station     # Override theme
    python master_run.py --seed 1337              # Override seed
    python master_run.py --skip-render            # Regenerate audio only
    python master_run.py --skip-music             # Re-render with same audio

Pipeline stages:
    1. Load config
    2. Music generation  ─┐  (parallel)
    3. Blender render    ─┘
    4. Review gate       ← YOU decide here before anything is finalized
    5. Compose to .mp4
    6. Output vault

Design principles:
    - Audio and render run in parallel threads — neither waits for the other
    - If either fails, the other is allowed to finish before we report errors
    - Review gate is a hard stop — nothing composes until you approve
    - All paths are derived from config — nothing is hardcoded here
    - Outputs are versioned by theme + seed so runs never collide
"""

import os
import sys
import time
import argparse
import threading
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

from config.config_loader import load_config, get_temp_dir, get_output_dir, get_theme_dir


# ─── CLI args ─────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Neonveil Pipeline")
    parser.add_argument("--theme",        type=str, default=None, help="Override theme from config")
    parser.add_argument("--seed",         type=int, default=None, help="Override seed from config")
    parser.add_argument("--skip-music",   action="store_true",    help="Skip music generation (reuse existing audio)")
    parser.add_argument("--skip-render",  action="store_true",    help="Skip Blender render (reuse existing frames)")
    parser.add_argument("--no-review",    action="store_true",    help="Skip review gate (auto-approve) — use for batch testing only")
    return parser.parse_args()


# ─── Stage 1: Music ───────────────────────────────────────────────────────────

def run_music(config: dict, audio_path: str, result_bag: dict):
    """Runs in a thread. Stores result or exception in result_bag."""
    try:
        from music_engine.generator import generate_audio
        generate_audio(output_path=audio_path, config=config)
        result_bag["music"] = "ok"
    except Exception as e:
        result_bag["music"] = e


# ─── Stage 2: Render ──────────────────────────────────────────────────────────

def run_render(config: dict, frames_dir: str, blend_save_path: str, result_bag: dict):
    """Runs in a thread. Launches Blender as a subprocess."""
    import subprocess

    blender_exe = config["paths"]["blender_exe"]
    render_script = str(BASE_DIR / "render_engine" / "full_render.py")

    # Resolve the theme's .blend template
    theme_dir = get_theme_dir(config)
    blend_template = theme_dir / "scene.blend"

    if not blend_template.exists():
        result_bag["render"] = FileNotFoundError(
            f"[Render] Template not found: {blend_template}\n"
            f"Create a base scene.blend in themes/{config['theme']}/ first.\n"
            f"See: themes/neon_rain/scene.blend (starter template)"
        )
        return

    if not Path(blender_exe).exists():
        result_bag["render"] = FileNotFoundError(
            f"[Render] Blender not found at: {blender_exe}\n"
            f"Update paths.blender_exe in config/config.yaml"
        )
        return

    cmd = [
        blender_exe,
        "-b", str(blend_template),         # Load template (not factory reset)
        "-P", render_script,
        "--",                              # Everything after -- goes to our script
        "--output",      str(frames_dir),
        "--blend-save",  str(blend_save_path),
        "--fps",         str(config["video"]["fps"]),
        "--duration",    str(config["video"]["duration_minutes"]),
        "--res-x",       str(config["video"]["resolution_x"]),
        "--res-y",       str(config["video"]["resolution_y"]),
        "--samples",     str(config["render"]["samples"]),
        "--seed",        str(config["seed"]),
        "--engine",      config["render"]["engine"],
        "--bloom",       str(config["render"]["bloom"]).lower(),
        "--volumetrics", str(config["render"]["volumetrics"]).lower(),
    ]

    print(f"[Render] Launching Blender...")
    print(f"[Render] Template: {blend_template}")

    result = subprocess.run(cmd, text=True)

    if result.returncode != 0:
        result_bag["render"] = RuntimeError(
            f"[Render] Blender exited with code {result.returncode}.\n"
            f"Check Blender's console output above for details."
        )
    else:
        result_bag["render"] = "ok"


# ─── Stage 3: Review gate ─────────────────────────────────────────────────────

def review_gate(audio_path: str, frames_dir: str, config: dict) -> bool:
    """
    Hard stop — shows you what was generated and waits for approval.
    Returns True to proceed, False to abort.
    """
    from pathlib import Path

    frames = list(Path(frames_dir).glob("*.png"))
    audio_mb = os.path.getsize(audio_path) / (1024 * 1024) if os.path.exists(audio_path) else 0

    print("\n" + "═" * 60)
    print("  REVIEW GATE")
    print("═" * 60)
    print(f"  Theme    : {config['theme']}")
    print(f"  Seed     : {config['seed']}")
    print(f"  Audio    : {audio_mb:.1f} MB — {audio_path}")
    print(f"  Frames   : {len(frames)} PNG files — {frames_dir}")
    print()
    print("  Actions:")
    print("  [y] Approve — proceed to compose")
    print("  [n] Abort   — stop here, keep files for manual inspection")
    print("  [r] Reject  — delete outputs and re-run from scratch")
    print("═" * 60)

    while True:
        choice = input("  Your choice (y/n/r): ").strip().lower()
        if choice == "y":
            return "approve"
        elif choice == "n":
            return "abort"
        elif choice == "r":
            return "reject"
        else:
            print("  Please enter y, n, or r.")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    start_time = time.time()
    args = parse_args()

    # Load config
    cfg = load_config()

    # Apply CLI overrides
    if args.theme:
        cfg["theme"] = args.theme
        print(f"[System] Theme override: {args.theme}")
    if args.seed is not None:
        cfg["seed"] = args.seed
        print(f"[System] Seed override: {args.seed}")

    print(f"\n[System] ═══ Neonveil Pipeline Starting ═══")
    print(f"[System] Project : {cfg['project_name']}")
    print(f"[System] Theme   : {cfg['theme']}")
    print(f"[System] Seed    : {cfg['seed']}")
    print(f"[System] Duration: {cfg['video']['duration_minutes']} min")
    print()

    # Resolve all paths — scoped to theme + seed so runs never collide
    temp_dir    = get_temp_dir(cfg)
    output_dir  = get_output_dir(cfg)
    frames_dir  = temp_dir / "frames"
    audio_path  = str(temp_dir / "audio.wav")
    blend_save  = str(output_dir / f"{cfg['theme']}_{cfg['seed']}.blend")
    final_video = str(output_dir / f"{cfg['theme']}_{cfg['seed']}.mp4")

    # Create directories
    temp_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Stage 2+3: Parallel music + render ───────────────────────────────────
    result_bag = {}
    threads = []

    if not args.skip_music:
        t_music = threading.Thread(
            target=run_music,
            args=(cfg, audio_path, result_bag),
            name="MusicThread",
        )
        threads.append(t_music)
        t_music.start()
        print("[System] Music generation started (background thread)")
    else:
        print("[System] --skip-music: reusing existing audio")
        result_bag["music"] = "ok"

    if not args.skip_render:
        t_render = threading.Thread(
            target=run_render,
            args=(cfg, str(frames_dir), blend_save, result_bag),
            name="RenderThread",
        )
        threads.append(t_render)
        t_render.start()
        print("[System] Blender render started (background thread)")
    else:
        print("[System] --skip-render: reusing existing frames")
        result_bag["render"] = "ok"

    # Wait for both to finish
    for t in threads:
        t.join()

    # Check for failures
    errors = []
    if isinstance(result_bag.get("music"), Exception):
        errors.append(("Music", result_bag["music"]))
    if isinstance(result_bag.get("render"), Exception):
        errors.append(("Render", result_bag["render"]))

    if errors:
        print("\n[System] ═══ PIPELINE FAILED ═══")
        for stage, err in errors:
            print(f"\n[{stage}] ERROR:\n  {err}")
        print("\n[System] Fix the errors above and re-run.")
        print("[System] Use --skip-music or --skip-render to skip the stage that succeeded.")
        sys.exit(1)

    elapsed = (time.time() - start_time) / 60
    print(f"\n[System] Generation complete in {elapsed:.1f} min")

    # ── Stage 4: Review gate ──────────────────────────────────────────────────
    if args.no_review:
        print("[System] --no-review: skipping review gate (auto-approve)")
        decision = "approve"
    else:
        decision = review_gate(audio_path, str(frames_dir), cfg)

    if decision == "abort":
        print("\n[System] Aborted at review gate. Files kept in temp/")
        print(f"  Audio  : {audio_path}")
        print(f"  Frames : {frames_dir}")
        print("[System] Re-run with --skip-music --skip-render to just re-compose.")
        sys.exit(0)

    if decision == "reject":
        print("\n[System] Rejected. Cleaning temp and re-running...")
        import shutil
        shutil.rmtree(str(temp_dir), ignore_errors=True)
        # Re-run with a new random seed
        cfg["seed"] = None
        from config.config_loader import load_config as _lc
        # Just restart cleanly
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ── Stage 5: Compose ─────────────────────────────────────────────────────
    print(f"\n[System] Composing final video...")
    from composer.compose import compose
    compose(
        audio_path=audio_path,
        frames_dir=str(frames_dir),
        output_path=final_video,
        config=cfg,
    )

    # ── Stage 6: Output summary ───────────────────────────────────────────────
    total_elapsed = (time.time() - start_time) / 60
    video_mb = os.path.getsize(final_video) / (1024 * 1024)

    print(f"\n[System] ═══ DONE ═══")
    print(f"[System] Total time : {total_elapsed:.1f} min")
    print(f"[System] Video      : {final_video} ({video_mb:.0f} MB)")
    print(f"[System] .blend     : {blend_save}")
    print(f"[System] Audio WAV  : {audio_path}")
    print()


if __name__ == "__main__":
    main()
