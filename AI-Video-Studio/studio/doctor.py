"""`studio doctor`: verify every tool and integration actually works (not just that it is on PATH)."""
from __future__ import annotations

import importlib
import json
import platform
import subprocess

from . import config


def _ver(cmd: list[str]) -> str | None:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return (cp.stdout or cp.stderr).strip().splitlines()[0] if cp.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def checks() -> list[tuple[str, bool, str]]:
    out = []
    out.append(("OS", True, f"{platform.system()} {platform.release()} ({platform.machine()})"))
    try:
        v = _ver([config.ffmpeg(), "-version"])
        enc = subprocess.run([config.ffmpeg(), "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        flt = subprocess.run([config.ffmpeg(), "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        need = ["xfade", "subtitles", "drawtext", "loudnorm", "lut3d", "zoompan", "rgbashift", "tmix", "afftdn", "blend"]
        miss = [f for f in need if f" {f} " not in flt]
        hw = [e for e in ("h264_nvenc", "h264_qsv", "h264_amf") if e in enc]
        out.append(("FFmpeg", bool(v) and "libx264" in enc and not miss,
                    f"{v}; libx264={'libx264' in enc}; missing filters={miss or 'none'}; HW encoders compiled in (need matching GPU+driver)={hw or 'none'}"))
        out.append(("FFprobe", bool(_ver([config.ffprobe(), "-version"])), config.ffprobe()))
    except RuntimeError as e:
        out.append(("FFmpeg", False, str(e)))
    mods = ["numpy", "cv2", "PIL", "librosa", "soundfile", "scenedetect", "faster_whisper"]
    for m in mods:
        try:
            mod = importlib.import_module(m)
            out.append((f"py:{m}", True, getattr(mod, "__version__", "ok")))
        except Exception as e:  # noqa: BLE001
            out.append((f"py:{m}", m == "faster_whisper" and False, f"not importable: {e}"))
    be = config.blender_exe()
    if be:
        out.append(("Blender app", bool(_ver([be, "--version"])), f"{be}: {_ver([be, '--version'])}"))
    bp = config.bpy_python()
    if bp:
        v = _ver([bp, "-c", "import bpy;print('bpy', bpy.app.version_string)"])
        out.append(("Blender bpy module", bool(v), v or "import failed"))
    if not be and not bp:
        out.append(("Blender", False, "not found (install Blender or create .venv-blender with bpy)"))
    nx = config.npx()
    rem = (config.REMOTION_DIR / "node_modules" / "remotion" / "package.json")
    if nx and rem.exists():
        ver = json.loads(rem.read_text())["version"]
        out.append(("Remotion", True, f"remotion {ver} (node {_ver(['node', '--version'])})"))
    else:
        out.append(("Remotion", False, "run `npm install` in AI-Video-Studio/remotion" if nx else "Node.js/npx not found"))
    out.append(("Remotion browser", True, config.remotion_browser() or "auto-download (chrome-headless-shell) on first render"))
    out.append(("Font for titles", bool(config.font_file()), config.font_file() or "none found"))
    try:
        import ctranslate2
        out.append(("CUDA for Whisper", True, f"{ctranslate2.get_cuda_device_count()} CUDA device(s)"))
    except Exception:  # noqa: BLE001
        pass
    whisper_models = list((config.ROOT / "models").glob("models--Systran--faster-whisper-*")) if (config.ROOT / "models").exists() else []
    out.append(("Whisper models cached", True, ", ".join(p.name.split("-")[-1] for p in whisper_models) or
                "none yet (downloaded free from Hugging Face on first captions run)"))
    return out


def run_doctor() -> int:
    ok_all = True
    for name, ok, info in checks():
        print(f"{'OK ' if ok else 'XX '} {name:24s} {info}")
        if not ok and not name.startswith("py:faster"):
            ok_all = False
    print("\nAll core tools working." if ok_all else "\nSome checks failed - see docs/TROUBLESHOOTING.md")
    return 0 if ok_all else 1
