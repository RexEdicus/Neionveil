"""
tools/blender/inspect_cameras.py
──────────────────────────────────
Blender Python script — executed INSIDE Blender in background mode via:
    blender.exe -b scene.blend -P inspect_cameras.py --

Prints all camera objects in the scene to stdout, one per line, prefixed
with "CAMERA:" so the caller can parse them reliably.

Usage (invoked by neonveil/steps/render.py):
    blender -b <blend_file> -P tools/blender/inspect_cameras.py --

Output format (one line per camera):
    CAMERA: CAM_MAIN
    CAMERA: CAM_ALT_01
    CAMERA: CAM_ALT_02
"""

import bpy
import sys

# We only need output after '--' (in case extra args are passed)
argv = sys.argv
if "--" in argv:
    argv = argv[argv.index("--") + 1:]

print("[CameraInspect] Listing cameras in scene...")

cameras = [obj.name for obj in bpy.data.objects if obj.type == "CAMERA"]

if not cameras:
    print("[CameraInspect] No cameras found in this .blend file.")
else:
    print(f"[CameraInspect] Found {len(cameras)} camera(s):")
    for cam in cameras:
        print(f"CAMERA: {cam}")

print("[CameraInspect] Done.")
