"""
render_engine/full_render.py
─────────────────────────────
Blender Python script — executed INSIDE Blender.
"""

import bpy
import sys
import os
import random
import argparse


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    parser = argparse.ArgumentParser(description="Neonveil Blender render script")
    parser.add_argument("--output", required=True, help="Path to frames output folder")
    parser.add_argument("--blend-save", required=True, help="Path to save the final .blend file")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--duration", type=int, default=120, help="Duration in minutes")
    parser.add_argument("--res-x", type=int, default=2560)
    parser.add_argument("--res-y", type=int, default=1440)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--engine", type=str, default="BLENDER_EEVEE_NEXT")
    parser.add_argument("--bloom", type=str, default="true")
    parser.add_argument("--volumetrics", type=str, default="true")

    # variation controls
    parser.add_argument("--camera-jitter", type=float, default=0.0)
    parser.add_argument("--light-jitter", type=float, default=0.0)
    parser.add_argument("--noise-offset", type=float, default=0.0)

    return parser.parse_args(argv)


def apply_render_settings(scene, args):
    scene.render.engine = args.engine
    scene.render.resolution_x = args.res_x
    scene.render.resolution_y = args.res_y
    scene.render.resolution_percentage = 100

    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.compression = 15

    total_frames = args.duration * 60 * args.fps
    scene.frame_start = 1
    scene.frame_end = total_frames
    scene.render.fps = args.fps

    print(f"[Render] Total frames: {total_frames} ({args.duration} min @ {args.fps}fps)")

    os.makedirs(args.output, exist_ok=True)
    scene.render.filepath = os.path.join(args.output, "") + "####"

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


def apply_seed_variation(scene, seed: int, camera_jitter: float, light_jitter: float, noise_offset: float):
    rng = random.Random(seed)

    for obj in bpy.data.objects:
        if obj.particle_systems:
            for psys in obj.particle_systems:
                psys.seed = rng.randint(0, 65535)

        if obj.type == "LIGHT":
            base_energy = obj.data.energy
            jitter = 1.0 + rng.uniform(-light_jitter, light_jitter)
            obj.data.energy = max(0.0, base_energy * jitter)

    cameras = [o for o in bpy.data.objects if o.type == "CAMERA"]
    for cam in cameras:
        dx = rng.uniform(-camera_jitter, camera_jitter)
        dy = rng.uniform(-camera_jitter, camera_jitter)
        dz = rng.uniform(-camera_jitter * 0.5, camera_jitter * 0.5)
        cam.location.x += dx
        cam.location.y += dy
        cam.location.z += dz

    for world in bpy.data.worlds:
        if not world.node_tree:
            continue
        for node in world.node_tree.nodes:
            if node.type == "TEX_NOISE" and "W" in node.inputs:
                node.inputs["W"].default_value += rng.uniform(0.0, noise_offset)

    print(
        f"[Render] Variation applied seed={seed} "
        f"camera_jitter={camera_jitter} light_jitter={light_jitter} noise_offset={noise_offset}"
    )


def main():
    args = parse_args()

    print(f"[Render] Script started")
    print(f"[Render] Output  : {args.output}")
    print(f"[Render] Seed    : {args.seed}")

    scene = bpy.context.scene
    apply_render_settings(scene, args)

    try:
        apply_seed_variation(
            scene,
            seed=args.seed,
            camera_jitter=max(0.0, args.camera_jitter),
            light_jitter=max(0.0, args.light_jitter),
            noise_offset=max(0.0, args.noise_offset),
        )
    except Exception as e:
        print(f"[Render] Seed variation partial (non-fatal): {e}")

    os.makedirs(os.path.dirname(args.blend_save), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=args.blend_save)
    print(f"[Render] .blend saved → {args.blend_save}")

    print("[Render] Starting render — this will take a while...")
    bpy.ops.render.render(animation=True, write_still=True)
    print(f"[Render] Done — frames written to {args.output}")


main()
