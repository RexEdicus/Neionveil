"""
render_engine/full_render.py
─────────────────────────────
Blender Python script — executed INSIDE Blender via:
    blender.exe -b <template.blend> -P full_render.py -- [options]

This script runs in Blender's embedded Python. Do NOT import project
modules here — only stdlib + bpy. All settings arrive via CLI args.

Design contract:
    - Reads config values from CLI args (passed by master_run.py / orchestrator)
    - Loads the theme's .blend template (not factory reset)
    - Applies config-driven resolution, frame range, engine, seed, camera
    - Outputs a PNG image sequence (or video) to the specified folder
    - Saves the final .blend to the specified path for re-editability
"""

import bpy
import sys
import os
import random
import argparse


def parse_args():
    """
    Parse args passed after '--' in the blender command line.
    Example:
        blender -b scene.blend -P full_render.py -- \\
            --output runs/my_run/render/frames \\
            --blend-save runs/my_run/render/scene_used.blend \\
            --fps 30 --duration 7200 --res-x 2560 --res-y 1440 \\
            --samples 64 --seed 42 --engine BLENDER_EEVEE_NEXT \\
            --camera CAM_MAIN \\
            --frame-start 1 --frame-end 5400
    """
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Neonveil Blender render script")
    parser.add_argument("--output",      required=True,  help="Path to frames output folder")
    parser.add_argument("--blend-save",  required=True,  help="Path to save the .blend file")
    parser.add_argument("--fps",         type=int,   default=30)
    parser.add_argument("--duration",    type=int,   default=7200, help="Duration in seconds")
    parser.add_argument("--res-x",       type=int,   default=2560)
    parser.add_argument("--res-y",       type=int,   default=1440)
    parser.add_argument("--samples",     type=int,   default=64)
    parser.add_argument("--seed",        type=int,   default=42)
    parser.add_argument("--engine",      type=str,   default="BLENDER_EEVEE_NEXT")
    parser.add_argument("--bloom",       type=str,   default="true")
    parser.add_argument("--volumetrics", type=str,   default="true")
    parser.add_argument("--camera",      type=str,   default=None,
                        help="Camera name to use for rendering (default: scene active camera)")
    # For segment rendering (camera cuts)
    parser.add_argument("--frame-start", type=int,   default=None,
                        help="Override frame start for segment renders")
    parser.add_argument("--frame-end",   type=int,   default=None,
                        help="Override frame end for segment renders")

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

    # Frame range
    if args.frame_start is not None and args.frame_end is not None:
        # Segment render (camera cuts)
        scene.frame_start = args.frame_start
        scene.frame_end   = args.frame_end
    else:
        # Full render from duration
        total_frames = args.duration * args.fps
        scene.frame_start = 1
        scene.frame_end   = total_frames

    scene.render.fps = args.fps

    total_frames = scene.frame_end - scene.frame_start + 1
    print(f"[Render] Frame range : {scene.frame_start}–{scene.frame_end} ({total_frames} frames)")

    # Output path — Blender needs a trailing slash for image sequences
    os.makedirs(args.output, exist_ok=True)
    scene.render.filepath = os.path.join(args.output, "") + "####"

    # EEVEE-specific settings
    if args.engine == "BLENDER_EEVEE_NEXT":
        eevee = scene.eevee

        eevee.taa_render_samples = args.samples

        if hasattr(eevee, "use_bloom"):
            eevee.use_bloom = (args.bloom.lower() == "true")

        if hasattr(eevee, "use_volumetric_lights"):
            eevee.use_volumetric_lights = (args.volumetrics.lower() == "true")
        if hasattr(eevee, "volumetric_samples"):
            eevee.volumetric_samples = 64

        if hasattr(eevee, "shadow_cube_size"):
            eevee.shadow_cube_size = "2048"
        if hasattr(eevee, "shadow_cascade_size"):
            eevee.shadow_cascade_size = "2048"

    print(f"[Render] Engine  : {args.engine}")
    print(f"[Render] Samples : {args.samples}")
    print(f"[Render] Res     : {args.res_x}×{args.res_y}")


def apply_camera(scene, camera_name: str):
    """
    Set the active camera by name.
    Raises ValueError if camera_name is not found in the scene.
    """
    if camera_name is None or camera_name.lower() == "auto":
        print(f"[Render] Camera  : {scene.camera.name if scene.camera else 'default'} (auto)")
        return

    cam_obj = bpy.data.objects.get(camera_name)
    if cam_obj is None or cam_obj.type != "CAMERA":
        available = [o.name for o in bpy.data.objects if o.type == "CAMERA"]
        raise ValueError(
            f"[Render] Camera '{camera_name}' not found in scene.\n"
            f"Available cameras: {available}\n"
            f"Use --list-cameras to see cameras for this theme."
        )

    scene.camera = cam_obj
    print(f"[Render] Camera  : {camera_name}")


def apply_seed_variation(scene, seed: int):
    """
    Apply seed-based variation to the scene.
    Non-fatal — template may not have all variatable nodes.
    """
    rng = random.Random(seed)

    for obj in bpy.data.objects:
        if obj.particle_systems:
            for psys in obj.particle_systems:
                psys.seed = rng.randint(0, 65535)
                print(f"[Render] Particle seed on '{obj.name}': {psys.seed}")

        if obj.type == "LIGHT":
            base_energy = obj.data.energy
            jitter = rng.uniform(0.85, 1.15)
            obj.data.energy = base_energy * jitter

    # World shader seed variation
    world = bpy.data.worlds.get("World")
    if world and world.node_tree:
        for node in world.node_tree.nodes:
            if node.type == "TEX_NOISE":
                node.inputs["W"].default_value = rng.uniform(0.0, 100.0)

    print(f"[Render] Seed variation applied (seed={seed})")


def main():
    args = parse_args()

    print(f"[Render] Script started")
    print(f"[Render] Output  : {args.output}")
    print(f"[Render] Seed    : {args.seed}")

    scene = bpy.context.scene

    apply_render_settings(scene, args)

    # Set active camera before rendering
    try:
        apply_camera(scene, args.camera)
    except ValueError as e:
        print(f"[Render] ERROR: {e}")
        sys.exit(1)

    try:
        apply_seed_variation(scene, args.seed)
    except Exception as e:
        print(f"[Render] Seed variation partial (non-fatal): {e}")

    # Save the configured .blend for re-editability
    blend_save_dir = os.path.dirname(args.blend_save)
    if blend_save_dir:
        os.makedirs(blend_save_dir, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=args.blend_save)
    print(f"[Render] .blend saved → {args.blend_save}")

    # Render animation
    print("[Render] Starting render — this will take a while...")
    bpy.ops.render.render(animation=True, write_still=True)

    print(f"[Render] Done — frames written to {args.output}")


main()
