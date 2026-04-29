"""
neonveil/steps/assets.py
─────────────────────────
"Assets" pipeline step.

Responsibilities:
  1. Copy themes/<theme>/scene.blend → runs/<run_id>/render/scene_used.blend
  2. Generate music assets into runs/<run_id>/music/
     (stems, MIDI, meta, full_mix.wav)
  3. Create placeholder edit folders (render/edited/, music/edited/)

Called by the orchestrator for --mode full and --mode assets.
"""

import shutil
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def run_assets_step(
    run_dir: Path,
    theme_dir: Path,
    config: dict,
    duration_sec: int,
    seed: int,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """
    Execute the assets generation step.

    Args:
        run_dir:      Path to runs/<run_id>/ (must already exist).
        theme_dir:    Path to themes/<theme>/.
        config:       Full config dict.
        duration_sec: Duration in seconds.
        seed:         Integer seed for reproducibility.
        dry_run:      If True, only print planned actions — do not execute.
        verbose:      If True, emit extra logging.

    Returns:
        dict with keys:
            blend_path  — path to scene_used.blend
            music_dir   — path to runs/<run_id>/music/
            full_mix    — path to full_mix.wav
    """
    run_dir   = Path(run_dir)
    theme_dir = Path(theme_dir)

    render_dir  = run_dir / "render"
    music_dir   = run_dir / "music"

    # ── 1. Copy theme blend ──────────────────────────────────────────────────
    theme_blend = theme_dir / "scene.blend"
    blend_dest  = render_dir / "scene_used.blend"

    if verbose:
        log.info(f"[Assets] Theme blend : {theme_blend}")
        log.info(f"[Assets] Dest blend  : {blend_dest}")

    print(f"[Assets] Theme  : {config['theme']}")
    print(f"[Assets] Source : {theme_blend}")
    print(f"[Assets] Dest   : {blend_dest}")

    if dry_run:
        print(f"[DryRun] Would copy {theme_blend} → {blend_dest}")
    else:
        if not theme_blend.exists():
            raise FileNotFoundError(
                f"[Assets] Theme blend not found: {theme_blend}\n"
                f"Create a base scene.blend in themes/{config['theme']}/ first."
            )
        render_dir.mkdir(parents=True, exist_ok=True)
        (render_dir / "edited").mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(theme_blend), str(blend_dest))
        print(f"[Assets] .blend copied → {blend_dest}")

        # Drop a README in the edited folder
        edit_readme = render_dir / "edited" / "notes.txt"
        if not edit_readme.exists():
            edit_readme.write_text(
                "Place your edited .blend file here as:\n"
                "    scene_edited.blend\n\n"
                "This will be automatically preferred over scene_used.blend\n"
                "when you run:  python master_run.py --mode assemble --run-id <id>\n",
                encoding="utf-8",
            )

    # ── 2. Generate music assets ─────────────────────────────────────────────
    if dry_run:
        print(f"[DryRun] Would generate music assets in {music_dir}")
        full_mix = str(music_dir / "full_mix.wav")
    else:
        from music_engine.generator import generate_music_assets
        result = generate_music_assets(
            music_dir=music_dir,
            config=config,
            duration_sec=duration_sec,
            seed=seed,
        )
        full_mix = result["full_mix"]

    return {
        "blend_path": str(blend_dest),
        "music_dir":  str(music_dir),
        "full_mix":   full_mix,
    }
