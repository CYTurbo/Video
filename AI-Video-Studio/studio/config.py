"""Paths and tool discovery for AI-Video-Studio (Windows + Linux + macOS)."""
from __future__ import annotations

import glob
import os
import platform
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = platform.system() == "Windows"

MEDIA = ROOT / "media"
RAW = MEDIA / "raw"
IMAGES = MEDIA / "images"
AUDIO = MEDIA / "audio"
REFERENCE = MEDIA / "reference"
PROJECTS = ROOT / "projects"
TEMPLATES = ROOT / "templates"
PRESETS = ROOT / "presets"
INTERMEDIATE = ROOT / "renders" / "intermediate"
EXPORTS = ROOT / "exports"
LOGS = ROOT / "logs"
REMOTION_DIR = ROOT / "remotion"
BLENDER_SCRIPTS = ROOT / "blender" / "scripts"

# Folders the pipeline must never write into (originals are read-only by policy).
PROTECTED_DIRS = [MEDIA]


def ensure_dirs() -> None:
    for d in (RAW, IMAGES, AUDIO, REFERENCE, PROJECTS, INTERMEDIATE, EXPORTS, LOGS):
        d.mkdir(parents=True, exist_ok=True)


def _which(*names: str) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def ffmpeg() -> str:
    p = os.environ.get("FFMPEG") or _which("ffmpeg")
    if not p:
        raise RuntimeError("FFmpeg not found. Install it (Windows: winget install Gyan.FFmpeg) or set FFMPEG.")
    return p


def ffprobe() -> str:
    p = os.environ.get("FFPROBE") or _which("ffprobe")
    if not p:
        raise RuntimeError("FFprobe not found (ships with FFmpeg).")
    return p


def blender_exe() -> str | None:
    """Full Blender application, if installed."""
    p = os.environ.get("BLENDER_EXE") or _which("blender")
    if p:
        return p
    if IS_WINDOWS:
        cands = sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"))
        if cands:
            return cands[-1]
    elif platform.system() == "Darwin":
        mac = "/Applications/Blender.app/Contents/MacOS/Blender"
        if os.path.exists(mac):
            return mac
    return None


def bpy_python() -> str | None:
    """Fallback: Python venv with the official `bpy` module (Blender as a Python module)."""
    sub = "Scripts/python.exe" if IS_WINDOWS else "bin/python"
    p = ROOT / ".venv-blender" / sub
    return str(p) if p.exists() else None


def npx() -> str | None:
    return _which("npx.cmd", "npx") if IS_WINDOWS else _which("npx")


def remotion_browser() -> str | None:
    """Optional browser override for Remotion (only needed when Remotion cannot download its own)."""
    p = os.environ.get("REMOTION_BROWSER")
    if p:
        return p
    cand = sorted(glob.glob("/opt/pw-browsers/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))
    return cand[-1] if cand else None


def font_file() -> str | None:
    """A bold font for FFmpeg drawtext / fallback titles."""
    cands = []
    if IS_WINDOWS:
        cands += [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf"]
    cands += [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def ff_filter_path(p: str | Path) -> str:
    """Escape a path for use *inside* an FFmpeg filter argument (subtitles=, lut3d=, movie=).
    Windows drive colons and backslashes must be escaped."""
    s = str(Path(p).resolve()).replace("\\", "/")
    s = s.replace(":", "\\:").replace("'", "\\'")
    return s


def is_protected(path: str | Path) -> bool:
    rp = Path(path).resolve()
    return any(str(rp).startswith(str(d.resolve())) for d in PROTECTED_DIRS)


def assert_writable_output(path: str | Path) -> None:
    if is_protected(path):
        raise PermissionError(f"Refusing to write into protected source-media folder: {path}")
