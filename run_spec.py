import json
import random
import urllib.request
import urllib.error
from copy import deepcopy

MAX_VARIATIONS = 32


def _fallback_music_prompt(config: dict) -> str:
    return config.get("audio", {}).get("fallback_prompt", "ambient cinematic background")


def _heuristic_mood(prompt: str) -> str:
    p = (prompt or "").lower()
    if any(k in p for k in ["dark", "rain", "noir", "cyberpunk", "night"]):
        return "dark"
    if any(k in p for k in ["calm", "soft", "gentle", "peaceful"]):
        return "calm"
    if any(k in p for k in ["bright", "hope", "uplift", "happy"]):
        return "uplifting"
    return "ambient"


def _default_spec(config: dict, prompt: str, model: str | None, run_id: str | None, variations: int) -> dict:
    return {
        "run_id": run_id,
        "user_prompt": prompt,
        "llm_model": model,
        "theme": config.get("theme"),
        "mood": _heuristic_mood(prompt),
        "music_prompt": prompt or _fallback_music_prompt(config),
        "seed": int(config.get("seed", 42)),
        "variations": variations,
        "render": {
            "engine": config.get("render", {}).get("engine", "BLENDER_EEVEE_NEXT"),
            "samples": int(config.get("render", {}).get("samples", 64)),
            "bloom": bool(config.get("render", {}).get("bloom", True)),
            "volumetrics": bool(config.get("render", {}).get("volumetrics", True)),
            "fps": int(config.get("video", {}).get("fps", 30)),
            "duration_minutes": int(config.get("video", {}).get("duration_minutes", 120)),
            "resolution_x": int(config.get("video", {}).get("resolution_x", 2560)),
            "resolution_y": int(config.get("video", {}).get("resolution_y", 1440)),
        },
        "variation_strategy": {
            "camera_jitter_max": 0.06,
            "light_jitter_max": 0.15,
            "noise_offset_max": 35.0,
        },
    }


def _call_ollama_for_spec(prompt: str, model: str, ollama_url: str, timeout_sec: int) -> dict | None:
    """
    Request a structured run-spec proposal from Ollama.

    Args:
        prompt: User intent text describing desired generation.
        model: Ollama model name to query.
        ollama_url: HTTP endpoint for the Ollama generate API.
        timeout_sec: Request timeout in seconds.

    Returns:
        A dict parsed from model JSON output when successful, otherwise None.
        None is returned for network failures, HTTP errors, timeouts, or
        invalid/non-dict JSON responses.
    """
    system_instruction = (
        "Return ONLY valid JSON with keys: theme,mood,music_prompt,render,variation_strategy. "
        "Do not include run_id, seed, or variations (those are CLI-controlled). "
        "render keys: engine,samples,bloom,volumetrics,fps,duration_minutes,resolution_x,resolution_y. "
        "variation_strategy keys: camera_jitter_max,light_jitter_max,noise_offset_max."
    )
    payload = {
        "model": model,
        "stream": False,
        "prompt": f"{system_instruction}\nUser request: {prompt}",
        "format": "json",
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ollama_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        print(f"[Spec] Ollama unavailable or invalid response ({exc}); using safe defaults.")
        return None

    response_text = data.get("response")
    if not response_text:
        return None
    try:
        parsed = json.loads(response_text)
        return parsed if isinstance(parsed, dict) else None
    except ValueError:
        return None


def validate_and_normalize_spec(spec: dict, config: dict, run_id: str | None = None, variations: int | None = None) -> dict:
    """
    Validate and normalize a run spec against safe defaults and constraints.

    Ensures required keys exist, coerces types, clamps unsafe values, and
    applies CLI overrides (run_id, variations) when provided.
    """
    normalized = deepcopy(spec or {})

    normalized["theme"] = normalized.get("theme") or config.get("theme")
    normalized["mood"] = normalized.get("mood") or "ambient"
    normalized["music_prompt"] = (normalized.get("music_prompt") or _fallback_music_prompt(config)).strip()

    seed = normalized.get("seed", config.get("seed", 42))
    try:
        seed = int(seed)
    except (TypeError, ValueError):
        seed = int(config.get("seed", 42))
    normalized["seed"] = seed

    v = variations if variations is not None else normalized.get("variations", 1)
    try:
        v = int(v)
    except (TypeError, ValueError):
        v = 1
    normalized["variations"] = max(1, min(v, MAX_VARIATIONS))

    if run_id:
        normalized["run_id"] = run_id
    elif not normalized.get("run_id"):
        normalized["run_id"] = f"{normalized['theme']}-{normalized['seed']}"

    render = deepcopy(normalized.get("render", {}))
    render_defaults = _default_spec(config, "", None, None, 1)["render"]
    for k, dv in render_defaults.items():
        render[k] = render.get(k, dv)

    try:
        render["samples"] = max(1, int(render["samples"]))
        render["fps"] = max(1, int(render["fps"]))
        render["duration_minutes"] = max(1, int(render["duration_minutes"]))
        render["resolution_x"] = max(64, int(render["resolution_x"]))
        render["resolution_y"] = max(64, int(render["resolution_y"]))
    except (TypeError, ValueError):
        render = render_defaults

    render["engine"] = str(render.get("engine", "BLENDER_EEVEE_NEXT"))
    render["bloom"] = bool(render.get("bloom", True))
    render["volumetrics"] = bool(render.get("volumetrics", True))
    normalized["render"] = render

    strategy = deepcopy(normalized.get("variation_strategy", {}))
    strategy_defaults = _default_spec(config, "", None, None, 1)["variation_strategy"]
    for k, dv in strategy_defaults.items():
        strategy[k] = strategy.get(k, dv)

    for key in ["camera_jitter_max", "light_jitter_max", "noise_offset_max"]:
        try:
            strategy[key] = max(0.0, float(strategy[key]))
        except (TypeError, ValueError):
            strategy[key] = strategy_defaults[key]

    normalized["variation_strategy"] = strategy
    return normalized


def build_run_spec(config: dict, args) -> dict:
    base = _default_spec(
        config=config,
        prompt=getattr(args, "llm_prompt", None),
        model=getattr(args, "llm_model", None),
        run_id=getattr(args, "run_id", None),
        variations=getattr(args, "variations", 1),
    )

    if getattr(args, "llm_prompt", None) and getattr(args, "llm_model", None):
        llm_spec = _call_ollama_for_spec(
            prompt=args.llm_prompt,
            model=args.llm_model,
            ollama_url=args.ollama_url,
            timeout_sec=args.ollama_timeout,
        )
        if llm_spec:
            # Merge only supported top-level keys from model output.
            base.update({k: v for k, v in llm_spec.items() if k in base or k in {"render", "variation_strategy"}})

    # CLI overrides always win
    if getattr(args, "theme", None):
        base["theme"] = args.theme
    if getattr(args, "seed", None) is not None:
        base["seed"] = args.seed

    return validate_and_normalize_spec(
        spec=base,
        config=config,
        run_id=getattr(args, "run_id", None),
        variations=getattr(args, "variations", 1),
    )


def expand_variation_manifests(spec: dict) -> list[dict]:
    """
    Expand a normalized run spec into deterministic per-variation manifests.

    Each manifest contains a unique seed, stable variation_id, inherited render
    settings, and derived camera/light/noise variation controls.
    """
    manifests = []
    base_seed = int(spec["seed"])
    strategy = spec["variation_strategy"]

    for idx in range(spec["variations"]):
        variation_seed = base_seed + idx
        rng = random.Random(variation_seed)

        manifests.append(
            {
                "variation_index": idx + 1,
                "variation_id": f"var-{idx + 1:03d}",
                "run_id": spec["run_id"],
                "theme": spec["theme"],
                "mood": spec["mood"],
                "music_prompt": spec["music_prompt"],
                "seed": variation_seed,
                "render": deepcopy(spec["render"]),
                "variation": {
                    "camera_jitter": round(rng.uniform(0.0, strategy["camera_jitter_max"]), 5),
                    "light_jitter": round(rng.uniform(0.0, strategy["light_jitter_max"]), 5),
                    "noise_offset": round(rng.uniform(0.0, strategy["noise_offset_max"]), 5),
                },
            }
        )

    return manifests
