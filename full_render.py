"""
render_engine/full_render.py
─────────────────────────────
Blender Python script — executed INSIDE Blender via:
    blender.exe -b <template.blend> -P full_render.py -- --config <path> --output <path> --seed <n>

This script runs in Blender's embedded Python. Do NOT import project
modules here — only stdlib + bpy. All settings arrive via CLI args.

Design contract:
    - Reads config values from CLI args (passed by master_run.py)
    - Loads the theme's .blend template (not factory reset)
    - Applies config-driven resolution, frame count, engine, seed
    - Outputs a PNG image sequence to the specified frames folder
    - Saves the final .blend to output for re-editability
"""

import bpy
import sys
import os
import random
import argparse


def parse_args():
    """
    Parse args passed after '--' in the blender command line.
    Example: blender -b scene.blend -P full_render.py -- --seed 42 --output temp/frames
    """
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Neonveil Blender render script")
    parser.add_argument("--output",     required=True,  help="Path to frames output folder")
    parser.add_argument("--blend-save", required=True,  help="Path to save the final .blend file")
    parser.add_argument("--fps",        type=int,   default=30)
    parser.add_argument("--duration",   type=int,   default=120,  help="Duration in minutes")
    parser.add_argument("--res-x",      type=int,   default=2560)
    parser.add_argument("--res-y",      type=int,   default=1440)
    parser.add_argument("--samples",    type=int,   default=64)
    parser.add_argument("--seed",       type=int,   default=42)
    parser.add_argument("--engine",     type=str,   default="BLENDER_EEVEE_NEXT")
    parser.add_argument("--bloom",      type=str,   default="true")
    parser.add_argument("--volumetrics",type=str,   default="true")

    return parser.parse_args(argv)


def apply_render_settings(scene, args):
    """Apply all render settings from parsed args to the Blender scene."""

    # Engine — BLENDER_EEVEE_NEXT is correct for Blender 4.x / 5.x
    scene.render.engine = args.engine

    # Resolution
    scene.render.resolution_x = args.res_x
    scene.render.resolution_y = args.res_y
    scene.render.resolution_percentage = 100

    # Output format — PNG sequence for editability
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode  = "RGBA"
    scene.render.image_settings.compression  = 15   # 0-100, lower = faster write

    # Frame range — calculate from duration + fps
    total_frames = args.duration * 60 * args.fps
    scene.frame_start = 1
    scene.frame_end   = total_frames
    scene.render.fps  = args.fps

    print(f"[Render] Total frames: {total_frames} ({args.duration} min @ {args.fps}fps)")

    # Output path — Blender needs a trailing slash for image sequences
    os.makedirs(args.output, exist_ok=True)
    scene.render.filepath = os.path.join(args.output, "") + "####"

    # EEVEE-specific settings
    if args.engine == "BLENDER_EEVEE_NEXT":
        eevee = scene.eevee

        # Samples
        eevee.taa_render_samples = args.samples

        # Bloom — the glow that makes cyberpunk look correct
        if hasattr(eevee, "use_bloom"):
            eevee.use_bloom = (args.bloom.lower() == "true")

        # Volumetrics — atmospheric fog / depth
        if hasattr(eevee, "use_volumetric_lights"):
            eevee.use_volumetric_lights = (args.volumetrics.lower() == "true")
        if hasattr(eevee, "volumetric_samples"):
            eevee.volumetric_samples = 64

        # Shadows
        if hasattr(eevee, "shadow_cube_size"):
            eevee.shadow_cube_size = "2048"
        if hasattr(eevee, "shadow_cascade_size"):
            eevee.shadow_cascade_size = "2048"

    print(f"[Render] Engine  : {args.engine}")
    print(f"[Render] Samples : {args.samples}")
    print(f"[Render] Res     : {args.res_x}×{args.res_y}")


def apply_seed_variation(scene, seed: int):
    """
    Apply seed-based variation to the scene.
    This randomizes properties that are tagged for variation in the .blend
    (particle system seeds, noise offsets, light intensity jitter).
    Keeps the same theme aesthetic while producing visually unique renders.
    """
    rng = random.Random(seed)

    for obj in bpy.data.objects:

        # Vary particle system seeds if present
        if obj.particle_systems:
            for psys in obj.particle_systems:
                psys.seed = rng.randint(0, 65535)
                print(f"[Render] Particle seed on '{obj.name}': {psys.seed}")

        # Slight light energy variation for mood difference between runs
        if obj.type == "LIGHT":
            base_energy = obj.data.energy
            jitter = rng.uniform(0.85, 1.15)
            obj.data.energy = base_energy * jitter

    # World shader seed variation (if world uses a noise node)
    # This shifts procedural fog/atmosphere subtly
    for node in bpy.data.worlds["World"].node_tree.nodes:
        if node.type == "TEX_NOISE":
            node.inputs["W"].default_value = rng.uniform(0.0, 100.0)

    print(f"[Render] Seed variation applied (seed={seed})")


def main():
    args = parse_args()

    print(f"[Render] Script started")
    print(f"[Render] Output  : {args.output}")
    print(f"[Render] Seed    : {args.seed}")

    scene = bpy.context.scene

    # Apply all settings
    apply_render_settings(scene, args)

    # Apply seed-based variation to the loaded template
    try:
        apply_seed_variation(scene, args.seed)
    except Exception as e:
        # Non-fatal — template may not have all variatable nodes
        print(f"[Render] Seed variation partial (non-fatal): {e}")

    # Save the configured .blend for re-editability
    os.makedirs(os.path.dirname(args.blend_save), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=args.blend_save)
    print(f"[Render] .blend saved → {args.blend_save}")

    # Render animation
    print("[Render] Starting render — this will take a while...")
    bpy.ops.render.render(animation=True, write_still=True)

    print(f"[Render] Done — frames written to {args.output}")


main()
