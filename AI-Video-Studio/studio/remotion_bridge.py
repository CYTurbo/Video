"""Drive Remotion (React motion graphics) from Python via the Remotion CLI."""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import config
from .log import log
from .media import run


def available() -> bool:
    return bool(config.npx()) and (config.REMOTION_DIR / "node_modules" / "remotion").exists()


def render(composition: str, props: dict, out: Path, alpha: bool = False, concurrency: int | None = None) -> Path:
    if not available():
        raise RuntimeError("Remotion not installed: run `npm install` inside AI-Video-Studio/remotion")
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    props_file = out.with_suffix(".props.json")
    props_file.write_text(json.dumps(props))
    cmd = [config.npx(), "remotion", "render", "src/index.ts", composition, str(out), f"--props={props_file}",
           "--log=error"]
    if alpha:
        cmd += ["--codec=prores", "--prores-profile=4444", "--pixel-format=yuva444p10le", "--image-format=png"]
    else:
        cmd += ["--codec=h264", "--crf=16", "--pixel-format=yuv420p"]
    cmd += [f"--concurrency={concurrency or max(1, (os.cpu_count() or 2) // 2)}"]
    br = config.remotion_browser()
    if br:  # only set when REMOTION_BROWSER is given or a preinstalled headless shell exists (Linux)
        cmd += [f"--browser-executable={br}"]
    log(f"   remotion: rendering {composition} -> {out.name}")
    cwd = os.getcwd()
    try:
        os.chdir(config.REMOTION_DIR)
        run(cmd)
    finally:
        os.chdir(cwd)
    if not out.exists():
        raise RuntimeError(f"Remotion reported success but {out} is missing")
    return out


def render_title_overlay(titles: list[dict], W: int, H: int, fps: int, D: float, style: str, work: Path) -> Path:
    props = {"width": W, "height": H, "fps": fps, "durationSec": D, "style": style, "titles": titles}
    return render("TitleOverlay", props, work / "titles_overlay.mov", alpha=True)


def render_kinetic(lines: list[str], W: int, H: int, fps: int, D: float, out: Path, beats: list[float] | None = None,
                   palette: list[str] | None = None, camera: str = "dramatic") -> Path:
    props = {"width": W, "height": H, "fps": fps, "durationSec": D, "lines": lines, "beats": beats or [],
             "palette": palette or ["#0b0f2b", "#4c1d95", "#f97316", "#22d3ee"], "camera": camera}
    return render("KineticTypography", props, out)


def render_logo(text: str, tagline: str, W: int, H: int, fps: int, D: float, out: Path, color: str = "#f97316") -> Path:
    props = {"width": W, "height": H, "fps": fps, "durationSec": D, "text": text, "tagline": tagline, "color": color}
    return render("LogoReveal", props, out)
