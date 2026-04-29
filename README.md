# Neonveil

Fully local ambience video generator — dark ambient music + Blender 3D renders + final YouTube MP4.

No paid APIs. Everything runs on your machine.

---

## What it does

1. **Generates ambient music** (stems, MIDI, mix) using the theme's prompt
2. **Prepares a Blender scene** for rendering (`scene_used.blend`)
3. **Renders the 3D animation** via Blender (optional, supports camera cuts)
4. **Assembles the final MP4** with ffmpeg

Each step produces **editable artifacts** so you can:
- Import stems/MIDI into FL Studio and produce your own mix
- Edit the `.blend` in Blender before rendering
- Re-assemble the final video from your edited files at any time

---

## Requirements

- **Python 3.12+** with `pyyaml` and `numpy`
- **Blender 5.0** (or 4.x) — set path in `config/config.yaml`
- **FFmpeg** — set path in `config/config.yaml`

Install Python dependencies:
```bash
pip install pyyaml numpy
```

---

## Quick start

### 1) Generate editable assets only (no final MP4 yet)
```bash
python master_run.py --mode assets --theme neon_rain --duration 7200 --seed 42
```

This creates:
```
runs/2026-04-29_neon-rain_run-0001/
├── manifest.json
├── music/
│   ├── stems/main_mix.wav          ← import into FL Studio
│   ├── midi/main.mid               ← MIDI for your DAW
│   ├── meta/sections.csv
│   ├── meta/tempo_map.json
│   ├── full_mix.wav                ← auto-generated mix
│   └── edited/                     ← PUT YOUR FL EXPORT HERE
│       └── notes.txt
└── render/
    ├── scene_used.blend            ← the render-ready .blend
    └── edited/                     ← PUT YOUR EDITED BLEND HERE
        └── notes.txt
```

### 2) Edit your files (optional)

- Edit `render/scene_used.blend` in Blender, save as `render/edited/scene_edited.blend`
- Export your FL Studio project as `music/edited/final_from_fl.wav`

### 3) Assemble the final MP4

```bash
python master_run.py --mode assemble --run-id 2026-04-29_neon-rain_run-0001
```

The pipeline automatically picks your edited files if they exist:
- `render/edited/scene_edited.blend` → preferred over `render/scene_used.blend`
- `music/edited/final_from_fl.wav` → preferred over `music/full_mix.wav`

Output: `runs/2026-04-29_neon-rain_run-0001/video/final_youtube.mp4`

---

## All modes

| Mode | What it does | Required flags |
|------|-------------|----------------|
| `full` | Assets + render + assemble (complete pipeline) | `--theme`, `--duration` |
| `assets` | Generate music + `.blend` only | `--theme`, `--duration` |
| `render` | Render `.blend` in an existing run | `--run-id` |
| `assemble` | Build final MP4 from existing/edited assets | `--run-id` |

---

## All CLI flags

### Run identity
```
--theme THEME_NAME      Theme folder under themes/
--run-id RUN_ID         Existing run folder ID (for assemble/render)
--seed INT              Master seed for reproducibility (default: random)
--duration SECONDS      Duration in seconds (3600 = 1h, 7200 = 2h)
```

### Output format
```
--render-mode loop|frames|both|off    Render output type (default: loop for full/assemble, off for assets)
--res 1920x1080|2560x1440|3840x2160   Resolution (default: 2560x1440)
--fps 30|60                           Frame rate (default: 30)
--quality fast|balanced|final         Blender samples + ffmpeg CRF preset (default: balanced)
```

### Camera controls
```
--camera-mode continuous|cuts         Camera mode (default: continuous)
--camera CAMERA_NAME                  Camera for continuous mode (default: auto = theme default)
--camera-sequence CAM_A,CAM_B,...     Camera order for cuts mode (cycles in sequence)
--cut-every SECONDS                   Seconds per segment for cuts mode (default: 240 = 4 min)
--cut-style hard|crossfade            Transition style (default: hard)
--cut-fade SECONDS                    Crossfade length (default: 1.0s, only for crossfade)
--list-cameras                        Print cameras available for a theme and exit
```

### Editable overrides
```
--blend-file PATH       Use this .blend instead of the default
--audio-file PATH       Use this audio file instead of the default
--render-cache reuse|rerender   reuse=skip if rendered, rerender=always re-render (default: reuse)
```

### Utility
```
--open-run-folder       Open the run folder in file manager after completion
--dry-run               Print planned actions without executing Blender or ffmpeg
--verbose               Extra log output
```

---

## Camera cuts workflow

Render with camera switching every 3 minutes:
```bash
python master_run.py --mode assemble --run-id <id> \
  --render-cache rerender \
  --camera-mode cuts \
  --cut-every 180 \
  --cut-style crossfade \
  --cut-fade 1.0
```

The pipeline:
1. Renders segment 1 with `CAM_MAIN` (frames 1–5400)
2. Renders segment 2 with `CAM_ALT_01` (frames 5401–10800)
3. Renders segment 3 with `CAM_ALT_02` (frames 10801–16200)
4. ...
5. Concatenates all segments with crossfade transitions
6. Muxes your audio into the final MP4

To use specific cameras:
```bash
python master_run.py --mode assemble --run-id <id> \
  --camera-mode cuts \
  --camera-sequence CAM_MAIN,CAM_ALT_02 \
  --cut-every 300
```

---

## Configuration

Edit `config/config.yaml` to set:
- **`paths.blender_exe`** — full path to your `blender.exe` (Windows default provided)
- **`paths.ffmpeg_exe`** — full path to `ffmpeg.exe`, or `"ffmpeg"` if it's on your PATH
- Default theme, seed, resolution, FPS
- Audio settings (sample rate, bitrate)
- Render settings (engine, samples, bloom, volumetrics)

### Windows FFmpeg path example:
```yaml
paths:
  blender_exe: "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe"
  # WinGet install location (replace <YourName> with your Windows username):
  ffmpeg_exe: "C:\\Users\\<YourName>\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-8.1-full_build\\bin\\ffmpeg.exe"
  # Or if ffmpeg is on PATH:
  # ffmpeg_exe: "ffmpeg"
```

Edit `config/presets.yaml` to adjust quality presets (Blender samples, ffmpeg CRF/preset).

---

## Run folder layout

```
runs/<run_id>/
├── manifest.json          ← run metadata + status + file registry
├── logs/                  ← pipeline logs (future)
├── music/
│   ├── stems/             ← per-instrument WAV stems
│   ├── midi/              ← MIDI files
│   ├── meta/              ← sections.csv, tempo_map.json
│   ├── full_mix.wav       ← auto-generated combined mix
│   └── edited/            ← YOUR edits go here
│       └── final_from_fl.wav  ← preferred over full_mix.wav if present
├── render/
│   ├── scene_used.blend   ← Blender scene for rendering (auto-generated)
│   ├── output_loop.mp4    ← rendered video (if loop/both mode)
│   ├── frames/            ← PNG image sequence (if frames/both mode)
│   └── edited/            ← YOUR edits go here
│       └── scene_edited.blend  ← preferred over scene_used.blend if present
└── video/
    └── final_youtube.mp4  ← final output
```

---

## Themes

Each theme lives under `themes/<name>/`:

```
themes/neon_rain/
├── scene.blend         ← base Blender scene
├── prompts.yaml        ← music generation prompt
└── cameras.yaml        ← camera list + default sequence
```

Create a new theme by copying the `neon_rain` folder and editing its files.

---

## Running tests

```bash
pip install pytest numpy pyyaml
python -m pytest tests/ -v
```

---

## Project structure

```
master_run.py              ← CLI entry point
config/
  config.yaml              ← main configuration
  config_loader.py         ← config loading utility
  presets.yaml             ← quality/resolution presets
music_engine/
  generator.py             ← audio generation (placeholder V1, upgradeable to MusicGen)
composer/
  compose.py               ← ffmpeg video assembly helpers
render_engine/
  full_render.py           ← Blender Python script (runs inside Blender)
neonveil/
  orchestrator.py          ← pipeline dispatcher
  run_id.py                ← run ID generation
  manifest.py              ← manifest read/write
  steps/
    assets.py              ← assets generation step
    render.py              ← Blender render step
    assemble.py            ← ffmpeg assembly step
tools/
  blender/
    inspect_cameras.py     ← Blender script to list cameras
themes/
  neon_rain/               ← example theme
tests/
  test_config.py
  test_cli.py
  test_music_engine.py
runs/                      ← created at runtime (gitignored)
```
