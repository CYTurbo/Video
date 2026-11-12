"""Media inspection helpers (ffprobe), hashing, frame extraction and contact sheets."""
from __future__ import annotations

import hashlib
import json
import subprocess
from fractions import Fraction
from pathlib import Path

from . import config
from .log import log

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mts", ".wmv"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def run(cmd: list[str], check: bool = True, quiet: bool = True) -> subprocess.CompletedProcess:
    log("$ " + " ".join(str(c) for c in cmd), echo=False)
    cp = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and cp.returncode != 0:
        log(cp.stderr[-4000:], echo=False)
        raise RuntimeError(f"Command failed ({cp.returncode}): {cmd[0]} ...\n{cp.stderr[-2000:]}")
    return cp


def probe(path: str | Path) -> dict:
    cp = run([config.ffprobe(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    data = json.loads(cp.stdout)
    fmt = data.get("format", {})
    info: dict = {
        "path": str(path),
        "duration": float(fmt.get("duration", 0) or 0),
        "size_bytes": int(fmt.get("size", 0) or 0),
        "container": fmt.get("format_name"),
        "video": None,
        "audio": [],
    }
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and info["video"] is None and s.get("disposition", {}).get("attached_pic", 0) == 0:
            fr = s.get("avg_frame_rate") or s.get("r_frame_rate") or "0/1"
            try:
                fps = float(Fraction(fr)) if fr != "0/0" else 0.0
            except (ZeroDivisionError, ValueError):
                fps = 0.0
            rot = 0
            for sd in s.get("side_data_list", []) or []:
                if "rotation" in sd:
                    rot = int(sd["rotation"])
            info["video"] = {
                "codec": s.get("codec_name"),
                "width": s.get("width"),
                "height": s.get("height"),
                "fps": round(fps, 3),
                "pix_fmt": s.get("pix_fmt"),
                "nb_frames": int(s["nb_frames"]) if str(s.get("nb_frames", "")).isdigit() else None,
                "duration": float(s.get("duration", 0) or 0),
                "rotation": rot,
                "color_space": s.get("color_space"),
                "has_alpha": (s.get("pix_fmt") or "").startswith(("yuva", "rgba", "argb", "bgra", "abgr", "gbrap", "ya")),
            }
        elif s.get("codec_type") == "audio":
            info["audio"].append({
                "codec": s.get("codec_name"),
                "sample_rate": int(s.get("sample_rate", 0) or 0),
                "channels": s.get("channels"),
                "duration": float(s.get("duration", 0) or 0),
            })
    return info


def describe(info: dict) -> str:
    v = info["video"]
    parts = [Path(info["path"]).name, f"{info['duration']:.2f}s"]
    if v:
        parts.append(f"{v['width']}x{v['height']} @ {v['fps']}fps {v['codec']} {v['pix_fmt']}")
    for a in info["audio"]:
        parts.append(f"audio {a['codec']} {a['sample_rate']}Hz {a['channels']}ch")
    if not info["audio"]:
        parts.append("no audio")
    return " | ".join(parts)


def sha256(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def snapshot_hashes(folder: Path) -> dict[str, str]:
    out = {}
    for p in sorted(folder.rglob("*")):
        if p.is_file() and p.name != ".gitkeep":
            out[str(p.relative_to(folder))] = sha256(p)
    return out


def list_media(folder: Path, kinds=("video", "audio", "image")) -> list[Path]:
    exts = set()
    if "video" in kinds:
        exts |= VIDEO_EXT
    if "audio" in kinds:
        exts |= AUDIO_EXT
    if "image" in kinds:
        exts |= IMAGE_EXT
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in exts)


def extract_frames(path: str | Path, times: list[float], out_dir: Path, width: int = 480) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = []
    for i, t in enumerate(times):
        o = out_dir / f"frame_{i:03d}_{t:07.2f}s.jpg"
        run([config.ffmpeg(), "-y", "-v", "error", "-ss", f"{max(t,0):.3f}", "-i", str(path), "-frames:v", "1",
             "-vf", f"scale={width}:-2", "-q:v", "3", str(o)])
        if o.exists():
            outs.append(o)
    return outs


def contact_sheet(path: str | Path, out_png: Path, n: int = 12, cols: int = 4, width: int = 360) -> Path:
    """Grid of N evenly spaced frames, each labelled with its timestamp."""
    from PIL import Image, ImageDraw

    info = probe(path)
    dur = info["duration"] or (info["video"] or {}).get("duration", 0)
    times = [dur * (i + 0.5) / n for i in range(n)]
    tmp = config.INTERMEDIATE / ("_cs_" + Path(path).stem)
    frames = extract_frames(path, times, tmp, width=width)
    if not frames:
        raise RuntimeError("No frames could be extracted for contact sheet")
    ims = [Image.open(f).convert("RGB") for f in frames]
    w, h = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * (h + 22)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, (im, t) in enumerate(zip(ims, times)):
        x, y = (i % cols) * w, (i // cols) * (h + 22)
        sheet.paste(im, (x, y + 22))
        d.text((x + 6, y + 4), f"t={t:.2f}s", fill=(240, 240, 240))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_png)
    for f in frames:
        f.unlink(missing_ok=True)
    try:
        tmp.rmdir()
    except OSError:
        pass
    return out_png
