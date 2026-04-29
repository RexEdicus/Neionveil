"""
master_run.py
──────────────
Neonveil — fully local ambience video generator (music + Blender + final MP4).

USAGE:
  python master_run.py --mode {full,assets,render,assemble} [options]

MODES:
  full        Generate editable assets (music + .blend) → render → assemble final MP4
  assets      Generate editable assets only (music + .blend). Rendering is optional.
  render      Render only from an existing .blend (no music generation)
  assemble    Assemble final MP4 for an existing run using existing/edited assets

EXAMPLES:
  # Generate everything (2-hour ambient video):
  python master_run.py --mode full --theme neon_rain --duration 7200

  # Generate editable assets only (no final MP4):
  python master_run.py --mode assets --theme neon_rain --duration 7200 --seed 1234

  # Later, assemble final MP4 from (possibly edited) assets:
  python master_run.py --mode assemble --run-id 2026-04-29_neon-rain_run-0001

  # Assemble with camera cuts every 3 minutes:
  python master_run.py --mode assemble --run-id <id> \\
    --render-cache rerender --camera-mode cuts --cut-every 180 --cut-style hard

  # List cameras available in a theme:
  python master_run.py --theme neon_rain --list-cameras

  # Dry-run to preview planned actions:
  python master_run.py --mode full --theme neon_rain --duration 7200 --dry-run
"""

import os
import sys
import logging
import argparse
import random
from pathlib import Path

# ── Project root on sys.path ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))


# ─── CLI ─────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        prog="master_run.py",
        description=(
            "Neonveil — fully local ambience video generator (music + Blender + final MP4).\n\n"
            "MODES:\n"
            "  full      Generate assets (music + .blend) → render → assemble final MP4\n"
            "  assets    Generate editable assets only (music + .blend); rendering optional\n"
            "  render    Render only from an existing .blend in a run folder\n"
            "  assemble  Build final MP4 from existing/edited assets in a run folder\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "EXAMPLES:\n"
            "  python master_run.py --mode full --theme neon_rain --duration 7200\n"
            "  python master_run.py --mode assets --theme neon_rain --duration 3600 --seed 42\n"
            "  python master_run.py --mode assemble --run-id 2026-04-29_neon-rain_run-0001\n"
            "  python master_run.py --mode assemble --run-id <id> \\\n"
            "    --camera-mode cuts --cut-every 180 --cut-style crossfade --cut-fade 1.0\n"
            "  python master_run.py --theme neon_rain --list-cameras\n"
        ),
    )

    # ── Mode ─────────────────────────────────────────────────────────────────
    parser.add_argument(
        "--mode",
        choices=["full", "assets", "render", "assemble"],
        default="full",
        metavar="MODE",
        help=(
            "Pipeline mode: full | assets | render | assemble  (default: full)\n"
            "  full     = assets + render + assemble (complete pipeline)\n"
            "  assets   = generate music + .blend only (edit before assembling)\n"
            "  render   = render an existing .blend in a run folder\n"
            "  assemble = produce final MP4 from existing/edited run assets"
        ),
    )

    # ── Run identity ─────────────────────────────────────────────────────────
    identity = parser.add_argument_group("Run identity")
    identity.add_argument(
        "--theme",
        type=str,
        default=None,
        metavar="THEME_NAME",
        help="Theme folder under themes/  (required for full and assets)",
    )
    identity.add_argument(
        "--run-id",
        type=str,
        default=None,
        metavar="RUN_ID",
        help=(
            "Existing run ID under runs/  (required for assemble and render).\n"
            "Format: YYYY-MM-DD_<theme>_run-NNNN\n"
            "Example: 2026-04-29_neon-rain_run-0001"
        ),
    )
    identity.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="INT",
        help="Master seed for reproducibility (default: random, stored in manifest)",
    )
    identity.add_argument(
        "--duration",
        type=int,
        default=None,
        metavar="SECONDS",
        help=(
            "Total duration in seconds  (required for full and assets).\n"
            "Examples: 3600 = 1 hour, 7200 = 2 hours"
        ),
    )

    # ── Output format ─────────────────────────────────────────────────────────
    output_fmt = parser.add_argument_group("Output format")
    output_fmt.add_argument(
        "--render-mode",
        choices=["loop", "frames", "both", "off"],
        default=None,
        metavar="MODE",
        help=(
            "Render output mode  (default depends on --mode):\n"
            "  loop   = render video file  [default for full / assemble]\n"
            "  frames = render PNG image sequence\n"
            "  both   = render frames + encode video\n"
            "  off    = skip Blender render entirely  [default for assets]"
        ),
    )
    output_fmt.add_argument(
        "--res",
        choices=["1920x1080", "2560x1440", "3840x2160"],
        default="2560x1440",
        metavar="WxH",
        help="Output resolution  (default: 2560x1440)",
    )
    output_fmt.add_argument(
        "--fps",
        type=int,
        choices=[30, 60],
        default=30,
        metavar="FPS",
        help="Frames per second  (default: 30)",
    )
    output_fmt.add_argument(
        "--quality",
        choices=["fast", "balanced", "final"],
        default="balanced",
        metavar="PRESET",
        help=(
            "Quality/speed trade-off preset  (default: balanced)\n"
            "  fast     = 16 samples, CRF 28, ultrafast encode\n"
            "  balanced = 64 samples, CRF 18, slow encode\n"
            "  final    = 256 samples, CRF 12, veryslow encode"
        ),
    )

    # ── Camera controls ───────────────────────────────────────────────────────
    cam = parser.add_argument_group("Camera controls")
    cam.add_argument(
        "--camera-mode",
        choices=["continuous", "cuts"],
        default="continuous",
        metavar="MODE",
        help=(
            "Camera switching mode  (default: continuous)\n"
            "  continuous = one camera for the entire video\n"
            "  cuts       = switch cameras at --cut-every intervals"
        ),
    )
    cam.add_argument(
        "--camera",
        type=str,
        default="auto",
        metavar="CAMERA_NAME",
        help=(
            "Camera to use for continuous mode  (default: auto = theme default).\n"
            "Example: --camera CAM_MAIN"
        ),
    )
    cam.add_argument(
        "--camera-sequence",
        type=str,
        default=None,
        metavar="CAM1,CAM2,...",
        help=(
            "Comma-separated camera sequence for cuts mode.\n"
            "Cycles in order (never random).  Default: auto (from cameras.yaml).\n"
            "Example: --camera-sequence CAM_MAIN,CAM_ALT_01,CAM_ALT_02"
        ),
    )
    cam.add_argument(
        "--cut-every",
        type=int,
        default=240,
        metavar="SECONDS",
        help="Seconds per camera segment for cuts mode  (default: 240 = 4 min)",
    )
    cam.add_argument(
        "--cut-style",
        choices=["hard", "crossfade"],
        default="hard",
        metavar="STYLE",
        help="Transition style between camera cuts  (default: hard)",
    )
    cam.add_argument(
        "--cut-fade",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Crossfade duration in seconds (only for --cut-style crossfade, default: 1.0)",
    )
    cam.add_argument(
        "--list-cameras",
        action="store_true",
        help="List cameras available for the theme and exit (uses cameras.yaml or Blender)",
    )

    # ── Editable overrides ────────────────────────────────────────────────────
    overrides = parser.add_argument_group("Editable file overrides")
    overrides.add_argument(
        "--blend-file",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "Explicit .blend file to use for rendering.\n"
            "Default selection order:\n"
            "  1) runs/<run-id>/render/edited/scene_edited.blend  (your edit)\n"
            "  2) runs/<run-id>/render/scene_used.blend           (auto-generated)\n"
            "  3) themes/<theme>/scene.blend                      (full/assets only)"
        ),
    )
    overrides.add_argument(
        "--audio-file",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "Explicit audio file (.wav) to use when assembling the final MP4.\n"
            "Default selection order:\n"
            "  1) runs/<run-id>/music/edited/final_from_fl.wav  (your FL Studio export)\n"
            "  2) runs/<run-id>/music/full_mix.wav              (auto-generated)"
        ),
    )
    overrides.add_argument(
        "--render-cache",
        choices=["reuse", "rerender"],
        default="reuse",
        metavar="POLICY",
        help=(
            "Render cache policy  (default: reuse)\n"
            "  reuse    = reuse existing rendered frames/video if present (faster)\n"
            "  rerender = always re-render from the selected .blend (safer after edits)"
        ),
    )

    # ── Utility flags ─────────────────────────────────────────────────────────
    util = parser.add_argument_group("Utility / diagnostics")
    util.add_argument(
        "--open-run-folder",
        action="store_true",
        help="Open the run folder in your file manager after completion",
    )
    util.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions and paths — do NOT invoke Blender or ffmpeg",
    )
    util.add_argument(
        "--verbose",
        action="store_true",
        help="Emit extra log output",
    )

    return parser.parse_args()


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_args(args):
    """
    Validate argument combinations and apply mode-specific defaults.
    Prints a friendly error and exits on invalid input.
    """
    if args.mode in ("full", "assets"):
        if not args.theme:
            _die("--theme is required for --mode full and --mode assets.\n"
                 "Example: --theme neon_rain")
        if not args.duration and not args.list_cameras:
            _die("--duration is required for --mode full and --mode assets.\n"
                 "Example: --duration 7200  (2 hours)")

    if args.mode in ("assemble", "render"):
        if not args.run_id:
            _die(f"--run-id is required for --mode {args.mode}.\n"
                 "Example: --run-id 2026-04-29_neon-rain_run-0001")

    if args.camera_mode == "cuts" and args.cut_fade < 0:
        _die("--cut-fade must be >= 0")

    if args.cut_every <= 0:
        _die("--cut-every must be a positive integer (seconds per segment)")


def _die(msg: str):
    print(f"\n[Error] {msg}\n", file=sys.stderr)
    print("Run with --help for usage information.", file=sys.stderr)
    sys.exit(1)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        format="%(message)s",
        level=level,
    )

    # ── Handle --list-cameras before validation (needs --theme, not --mode) ──
    if args.list_cameras:
        _cmd_list_cameras(args)
        return

    validate_args(args)

    # Load config
    from config.config_loader import load_config, reset_cache
    reset_cache()                            # allow fresh load each run
    cfg = load_config()

    # Apply CLI overrides to config
    if args.theme:
        cfg["theme"] = args.theme
    if args.seed is not None:
        cfg["seed"] = args.seed
    elif cfg.get("seed") is None:
        cfg["seed"] = random.randint(0, 999999)
        print(f"[System] Auto seed: {cfg['seed']}")

    # Propagate fps + resolution into config so downstream modules see them
    cfg["video"]["fps"] = args.fps
    w, h = args.res.split("x")
    cfg["video"]["resolution_x"] = int(w)
    cfg["video"]["resolution_y"] = int(h)

    # ── Dispatch to orchestrator ───────────────────────────────────────────────
    from neonveil.orchestrator import Orchestrator
    orch = Orchestrator(args, cfg)

    try:
        orch.run()
    except KeyboardInterrupt:
        print("\n[System] Interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n[System] ═══ PIPELINE FAILED ═══")
        print(f"[System] Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        print("\n[System] Use --verbose for a full traceback.")
        sys.exit(1)


# ─── --list-cameras handler ───────────────────────────────────────────────────

def _cmd_list_cameras(args):
    """Handle --list-cameras: print cameras and exit."""
    if not args.theme:
        _die("--theme is required with --list-cameras.\nExample: --theme neon_rain")

    from config.config_loader import load_config, reset_cache, get_theme_dir
    reset_cache()
    cfg = load_config()
    if args.theme:
        cfg["theme"] = args.theme

    theme_dir  = get_theme_dir(cfg)
    theme_blend = theme_dir / "scene.blend"

    # Try the blend override too
    blend_file = args.blend_file or (str(theme_blend) if theme_blend.exists() else None)

    from neonveil.steps.render import list_cameras
    cameras = list_cameras(theme_dir, blend_file, cfg)

    print(f"\n[Cameras] Theme: {args.theme}")
    if cameras:
        print(f"[Cameras] Found {len(cameras)} camera(s):")
        for cam in cameras:
            print(f"  {cam}")
    else:
        print("[Cameras] No cameras found (place cameras in cameras.yaml or in the .blend).")
    print()


if __name__ == "__main__":
    main()
