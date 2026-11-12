"""Run Blender Python scripts headlessly (full Blender app, or the `bpy` module fallback)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import config
from .log import log
from .media import run


def available() -> str | None:
    if config.blender_exe():
        return "blender"
    if config.bpy_python():
        return "bpy"
    return None


def run_script(script: str | Path, args: dict, timeout_note: str = "") -> None:
    script = Path(script)
    if not script.is_absolute():
        script = config.BLENDER_SCRIPTS / script
    argfile = config.INTERMEDIATE / f"_blender_args_{script.stem}.json"
    argfile.parent.mkdir(parents=True, exist_ok=True)
    argfile.write_text(json.dumps(args))
    mode = available()
    if mode == "blender":
        cmd = [config.blender_exe(), "--background", "--factory-startup", "--python", str(script), "--", str(argfile)]
    elif mode == "bpy":
        cmd = [config.bpy_python(), str(script), "--", str(argfile)]
    else:
        raise RuntimeError("Blender not found. Install Blender (winget install BlenderFoundation.Blender) or set BLENDER_EXE.")
    log(f"   blender ({mode}): {script.name} {timeout_note}")
    run(cmd)


def frames_to_video(frame_dir: Path, fps: int, out: Path, pattern: str = "frame_%04d.png",
                    size: tuple[int, int] | None = None) -> Path:
    vf = ["scale=%d:%d:flags=lanczos" % size] if size else []
    run([config.ffmpeg(), "-y", "-v", "error", "-framerate", str(fps), "-i", str(frame_dir / pattern)] +
        (["-vf", ",".join(vf)] if vf else []) +
        ["-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)])
    return out


def render_title3d(text: str, out: Path, width: int = 1920, height: int = 1080, fps: int = 30, duration: float = 4.0,
                   engine: str = "auto", samples: int = 16, color=(1.0, 0.45, 0.1), bg=(0.02, 0.02, 0.05),
                   percent: int | None = None) -> Path:
    """3D extruded title with keyframed, eased camera orbit + lights. Returns an MP4."""
    out = Path(out)
    frames = config.INTERMEDIATE / f"blender_{out.stem}"
    frames.mkdir(parents=True, exist_ok=True)
    for f in frames.glob("frame_*.png"):
        f.unlink()
    if engine == "auto":
        # EEVEE needs a GPU/OpenGL context; Cycles CPU works everywhere (slower).
        engine = os.environ.get("BLENDER_ENGINE", "CYCLES")
    if percent is None:  # render smaller and upscale when big frames would be slow on CPU (override: BLENDER_PERCENT)
        percent = int(os.environ.get("BLENDER_PERCENT", 50 if width * height > 1280 * 720 else 100))
    run_script("title3d.py", {"text": text, "out_dir": str(frames), "width": width, "height": height, "fps": fps,
                              "frames": int(round(duration * fps)), "engine": engine, "samples": samples,
                              "color": list(color), "bg": list(bg), "percent": percent})
    return frames_to_video(frames, fps, out, size=(width, height))
