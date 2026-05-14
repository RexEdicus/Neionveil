"""
master_run.py
──────────────
The single entry point for the entire Neonveil pipeline.
"""

import os
import sys
import time
import json
import copy
import argparse
import threading
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

try:
    from config.config_loader import load_config
except ModuleNotFoundError:
    from config_loader import load_config

from run_spec import build_run_spec, expand_variation_manifests


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Neonveil Pipeline")
    parser.add_argument("--theme", type=str, default=None, help="Override theme")
    parser.add_argument("--seed", type=int, default=None, help="Override seed")
    parser.add_argument("--skip-music", action="store_true", help="Skip music generation")
    parser.add_argument("--skip-render", action="store_true", help="Skip Blender render")
    parser.add_argument("--no-review", action="store_true", help="Skip review gate")

    # LLM contract
    parser.add_argument("--llm-prompt", type=str, default=None, help="Single prompt used to derive run intent")
    parser.add_argument("--llm-model", type=str, default=None, help="Ollama model name (e.g. llama3:8b)")
    parser.add_argument("--variations", type=int, default=1, help="Number of render variations to generate")
    parser.add_argument("--run-id", type=str, default=None, help="Output run identifier")
    parser.add_argument("--dry-run", action="store_true", help="Print normalized spec + manifests and exit")
    parser.add_argument("--ollama-url", type=str, default="http://localhost:11434/api/generate", help="Ollama generate endpoint")
    parser.add_argument("--ollama-timeout", type=int, default=45, help="Ollama timeout in seconds")

    args = parser.parse_args(argv)

    if args.llm_prompt and not args.llm_model:
        parser.error("--llm-model is required when --llm-prompt is provided")
    if args.llm_model and not args.llm_prompt:
        parser.error("--llm-prompt is required when --llm-model is provided")
    if args.variations < 1:
        parser.error("--variations must be >= 1")

    return args


def run_music(config: dict, audio_path: str, result_bag: dict):
    try:
        try:
            from music_engine.generator import generate_audio
        except ModuleNotFoundError:
            from generator import generate_audio
        generate_audio(output_path=audio_path, config=config)
        result_bag["music"] = "ok"
    except Exception as e:
        result_bag["music"] = e


def run_render(config: dict, frames_dir: str, blend_save_path: str, result_bag: dict):
    import subprocess

    blender_exe = config["paths"]["blender_exe"]
    packaged_script = BASE_DIR / "render_engine" / "full_render.py"
    render_script = str(packaged_script if packaged_script.exists() else BASE_DIR / "full_render.py")

    theme_dir = BASE_DIR / config["paths"]["themes_dir"] / config["theme"]
    blend_template = theme_dir / "scene.blend"

    if not blend_template.exists():
        result_bag["render"] = FileNotFoundError(
            f"[Render] Template not found: {blend_template}\n"
            f"Create a base scene.blend in themes/{config['theme']}/ first."
        )
        return

    if not Path(blender_exe).exists():
        result_bag["render"] = FileNotFoundError(
            f"[Render] Blender not found at: {blender_exe}\n"
            f"Update paths.blender_exe in config.yaml"
        )
        return

    variation = config.get("variation", {})

    cmd = [
        blender_exe,
        "-b", str(blend_template),
        "-P", render_script,
        "--",
        "--output", str(frames_dir),
        "--blend-save", str(blend_save_path),
        "--fps", str(config["video"]["fps"]),
        "--duration", str(config["video"]["duration_minutes"]),
        "--res-x", str(config["video"]["resolution_x"]),
        "--res-y", str(config["video"]["resolution_y"]),
        "--samples", str(config["render"]["samples"]),
        "--seed", str(config["seed"]),
        "--engine", config["render"]["engine"],
        "--bloom", str(config["render"]["bloom"]).lower(),
        "--volumetrics", str(config["render"]["volumetrics"]).lower(),
        "--camera-jitter", str(variation.get("camera_jitter", 0.0)),
        "--light-jitter", str(variation.get("light_jitter", 0.0)),
        "--noise-offset", str(variation.get("noise_offset", 0.0)),
    ]

    print(f"[Render] Launching Blender... {config.get('variation_id', 'var-001')}")
    result = subprocess.run(cmd, text=True)

    if result.returncode != 0:
        result_bag["render"] = RuntimeError(
            f"[Render] Blender exited with code {result.returncode}."
        )
    else:
        result_bag["render"] = "ok"


def review_gate(audio_path: str, frames_dir: str, config: dict, variation_id: str) -> str:
    frames = list(Path(frames_dir).glob("*.png"))
    audio_mb = os.path.getsize(audio_path) / (1024 * 1024) if os.path.exists(audio_path) else 0

    print("\n" + "═" * 60)
    print(f"  REVIEW GATE ({variation_id})")
    print("═" * 60)
    print(f"  Theme    : {config['theme']}")
    print(f"  Seed     : {config['seed']}")
    print(f"  Audio    : {audio_mb:.1f} MB — {audio_path}")
    print(f"  Frames   : {len(frames)} PNG files — {frames_dir}")
    print("═" * 60)

    while True:
        choice = input("  Your choice (y/n/r): ").strip().lower()
        if choice == "y":
            return "approve"
        if choice == "n":
            return "abort"
        if choice == "r":
            return "reject"
        print("  Please enter y, n, or r.")


def _apply_manifest_to_config(base_cfg: dict, manifest: dict) -> dict:
    cfg = copy.deepcopy(base_cfg)
    cfg["theme"] = manifest["theme"]
    cfg["seed"] = manifest["seed"]
    cfg["video"]["fps"] = manifest["render"]["fps"]
    cfg["video"]["duration_minutes"] = manifest["render"]["duration_minutes"]
    cfg["video"]["resolution_x"] = manifest["render"]["resolution_x"]
    cfg["video"]["resolution_y"] = manifest["render"]["resolution_y"]
    cfg["render"]["engine"] = manifest["render"]["engine"]
    cfg["render"]["samples"] = manifest["render"]["samples"]
    cfg["render"]["bloom"] = manifest["render"]["bloom"]
    cfg["render"]["volumetrics"] = manifest["render"]["volumetrics"]

    cfg["runtime_music_prompt"] = manifest["music_prompt"]
    cfg["variation"] = manifest["variation"]
    cfg["variation_id"] = manifest["variation_id"]
    return cfg


def main(argv=None):
    start_time = time.time()
    args = parse_args(argv)
    cfg = load_config()

    if args.theme:
        cfg["theme"] = args.theme
    if args.seed is not None:
        cfg["seed"] = args.seed

    spec = build_run_spec(cfg, args)
    manifests = expand_variation_manifests(spec)

    if args.dry_run:
        print(json.dumps({"spec": spec, "manifests": manifests}, indent=2))
        return

    run_output_root = BASE_DIR / cfg["paths"]["output_dir"] / spec["run_id"]
    run_output_root.mkdir(parents=True, exist_ok=True)

    rendered_videos = []

    for manifest in manifests:
        cfg_run = _apply_manifest_to_config(cfg, manifest)
        var_id = manifest["variation_id"]

        run_temp_dir = BASE_DIR / cfg["paths"]["temp_dir"] / spec["run_id"] / var_id
        frames_dir = run_temp_dir / "frames"
        audio_path = str(run_temp_dir / "audio.wav")
        blend_save = str(run_output_root / f"{cfg_run['theme']}_{cfg_run['seed']}_{var_id}.blend")
        final_video = str(run_output_root / f"{cfg_run['theme']}_{cfg_run['seed']}_{var_id}.mp4")

        run_temp_dir.mkdir(parents=True, exist_ok=True)
        frames_dir.mkdir(parents=True, exist_ok=True)

        result_bag = {}
        threads = []

        if not args.skip_music:
            t_music = threading.Thread(target=run_music, args=(cfg_run, audio_path, result_bag), name=f"MusicThread-{var_id}")
            threads.append(t_music)
            t_music.start()
        else:
            result_bag["music"] = "ok"

        if not args.skip_render:
            t_render = threading.Thread(target=run_render, args=(cfg_run, str(frames_dir), blend_save, result_bag), name=f"RenderThread-{var_id}")
            threads.append(t_render)
            t_render.start()
        else:
            result_bag["render"] = "ok"

        for t in threads:
            t.join()

        errors = []
        if isinstance(result_bag.get("music"), Exception):
            errors.append(("Music", result_bag["music"]))
        if isinstance(result_bag.get("render"), Exception):
            errors.append(("Render", result_bag["render"]))
        if errors:
            print(f"\n[System] Variation {var_id} FAILED")
            for stage, err in errors:
                print(f"[{stage}] {err}")
            sys.exit(1)

        if args.no_review:
            decision = "approve"
        else:
            decision = review_gate(audio_path, str(frames_dir), cfg_run, var_id)

        if decision == "abort":
            print("[System] Aborted at review gate.")
            sys.exit(0)

        if decision == "reject":
            print(f"[System] Rejected {var_id}. Skipping compose for this variation.")
            continue

        try:
            from composer.compose import compose
        except ModuleNotFoundError:
            from compose import compose

        compose(
            audio_path=audio_path,
            frames_dir=str(frames_dir),
            output_path=final_video,
            config=cfg_run,
        )
        rendered_videos.append(final_video)

    total_elapsed = (time.time() - start_time) / 60
    print(f"\n[System] ═══ DONE ═══")
    print(f"[System] Run ID     : {spec['run_id']}")
    print(f"[System] Variations : {len(rendered_videos)}/{len(manifests)} composed")
    print(f"[System] Total time : {total_elapsed:.1f} min")
    for video in rendered_videos:
        print(f"[System] Video      : {video}")


if __name__ == "__main__":
    main()
