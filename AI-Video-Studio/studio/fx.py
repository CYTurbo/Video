"""FFmpeg filter-graph builders for cinematic effects.

Each function returns a filter string (or list of strings) that can be joined with ','.
Everything here is plain FFmpeg -- no paid plugins.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np

from . import config

# ---------------------------------------------------------------- colour grades
GRADES: dict[str, list[str]] = {
    "none": [],
    "neutral": ["eq=contrast=1.04:saturation=1.05"],
    "cinematic": [  # teal shadows / warm highlights, gentle S-curve
        "colorbalance=rs=-0.07:gs=-0.01:bs=0.09:rm=0.02:bm=-0.02:rh=0.08:gh=0.02:bh=-0.07",
        "curves=all='0/0.02 0.25/0.21 0.5/0.5 0.75/0.79 1/0.97'",
        "eq=contrast=1.08:saturation=1.08",
    ],
    "teal_orange": [
        "colorbalance=rs=-0.12:gs=-0.02:bs=0.14:rh=0.12:gh=0.03:bh=-0.12",
        "eq=contrast=1.12:saturation=1.15:gamma=0.98",
    ],
    "warm_film": [
        "colortemperature=temperature=5000:mix=0.6",
        "curves=all='0/0.07 0.5/0.52 1/0.93'",
        "eq=saturation=0.92:contrast=1.04",
    ],
    "moody": [
        "colorbalance=rs=-0.05:bs=0.08:rm=-0.03:bm=0.03",
        "eq=contrast=1.15:saturation=0.78:gamma=0.92:brightness=-0.02",
    ],
    "bright_vlog": ["eq=brightness=0.03:saturation=1.18:contrast=1.03", "vibrance=intensity=0.15"],
    "bw_contrast": ["hue=s=0", "eq=contrast=1.3:gamma=0.95"],
    "retro": ["curves=preset=vintage", "eq=saturation=0.85"],
    "neon": ["colorbalance=rs=0.06:bs=0.10:gh=-0.05:gm=-0.04", "eq=saturation=1.35:contrast=1.1"],
}


def grade(name_or_lut: str | None) -> list[str]:
    if not name_or_lut:
        return []
    if name_or_lut.lower().endswith(".cube"):
        return [f"lut3d=file='{config.ff_filter_path(name_or_lut)}':interp=tetrahedral"]
    if name_or_lut not in GRADES:
        raise ValueError(f"Unknown grade '{name_or_lut}'. Options: {', '.join(GRADES)} or a .cube LUT path")
    return list(GRADES[name_or_lut])


# ---------------------------------------------------------------- per-frame effects
def grain(strength: float = 10) -> str:
    """Temporal luma grain (strength 0-40)."""
    return f"noise=c0s={int(strength)}:c0f=t+u"


def vignette(angle: float = math.pi / 5) -> str:
    return f"vignette=angle={angle:.4f}"


def rgb_split(px: int = 4) -> str:
    return f"rgbashift=rh=-{px}:bh={px}:edge=smear"


def motion_blur(frames: int = 3) -> str:
    """Approximate shutter blur by blending adjacent frames."""
    w = {2: "1 1", 3: "1 2 1", 4: "1 2 2 1", 5: "1 2 3 2 1"}.get(frames, "1 2 1")
    return f"tmix=frames={frames}:weights='{w}'"


def sharpen(amount: float = 0.6) -> str:
    return f"unsharp=5:5:{amount}:5:5:0"


def letterbox(w: int, h: int, ratio: float = 2.39) -> str:
    bar = max(0, int((h - w / ratio) / 2))
    return f"drawbox=x=0:y=0:w={w}:h={bar}:color=black:t=fill,drawbox=x=0:y={h-bar}:w={w}:h={bar}:color=black:t=fill"


def _enable(windows: list[tuple[float, float]]) -> str:
    return "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in windows) or "0"


def glitch(windows: list[tuple[float, float]], intensity: float = 1.0) -> list[str]:
    """RGB split + noise + hue jitter, only inside the given time windows."""
    if not windows:
        return []
    en = _enable(windows)
    px = int(14 * intensity)
    return [
        f"rgbashift=rh=-{px}:gh={px//3}:bh={px}:edge=smear:enable='{en}'",
        f"noise=alls={int(35*intensity)}:allf=t:enable='{en}'",
        f"hue=h=25*sin(t*90):enable='{en}'",
    ]


def flashes(times: list[float], dur: float = 0.08, strength: float = 0.22) -> list[str]:
    if not times:
        return []
    return [f"eq=brightness={strength}:enable='{_enable([(t, t + dur) for t in times])}'"]


def zoom_punch(times: list[float], w: int, h: int, fps: int, amount: float = 0.07, decay: float = 9.0) -> str:
    """Quick scale-punch at each time (beat), easing back out exponentially."""
    terms = "+".join(f"gte(it,{t:.3f})*exp(-(it-{t:.3f})*{decay})" for t in times) or "0"
    z = f"1+{amount}*min(1,{terms})"
    return (f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={fps}")


# ---------------------------------------------------------------- per-segment motion
def fit(w: int, h: int, focus_x: float = 0.5) -> list[str]:
    """Scale to cover the frame and crop (focus_x 0..1 picks the horizontal crop centre)."""
    return [f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos",
            f"crop={w}:{h}:(iw-{w})*{focus_x:.3f}:(ih-{h})/2"]


def zoom(kind: str, dur: float, w: int, h: int, fps: int, amount: float = 0.12) -> list[str]:
    """Smooth Ken-Burns zoom in/out. Upscales 2x first to avoid zoompan jitter."""
    n = max(1, int(round(dur * fps)))
    ease = f"(0.5-0.5*cos(PI*min(on/{n},1)))"  # ease-in-out
    z = f"1+{amount}*{ease}" if kind == "in" else f"{1+amount}-{amount}*{ease}"
    return [f"scale={w*2}:{h*2}:flags=lanczos",
            f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={fps}"]


def shake(w: int, h: int, amp: float = 12, freq: float = 1.0) -> list[str]:
    """Handheld-style camera shake: overscan 6% and crop with layered sines."""
    W, H = int(w * 1.06) // 2 * 2, int(h * 1.06) // 2 * 2
    mx, my = (W - w) / 2, (H - h) / 2
    a = min(amp, mx, my)
    f = freq
    x = f"{mx}+{a}*(0.6*sin(t*{7.3*f:.2f})+0.4*sin(t*{17.1*f:.2f}+1.3))"
    y = f"{my}+{a}*(0.6*sin(t*{6.1*f:.2f}+0.7)+0.4*sin(t*{15.7*f:.2f}+2.1))"
    return [f"scale={W}:{H}", f"crop={w}:{h}:'{x}':'{y}'"]


def speed(src_dur: float, base: float = 1.0, ramp: float = 0.0) -> str:
    """Time remap. base>1 = faster. ramp 0..0.85 = fast-slow-fast speed ramp (slow-mo in the middle).

    out_time = (T - ramp*D/(2pi)*sin(2pi*T/D)) / base   -> continuous, monotonic, total = D/base.
    """
    D = max(src_dur, 1e-3)
    r = max(0.0, min(ramp, 0.85))
    return f"setpts='((T-{r}*{D:.4f}/(2*PI)*sin(2*PI*T/{D:.4f}))/{base:.4f})/TB'"


# ---------------------------------------------------------------- transitions
XFADE = {
    "fade", "dissolve", "fadeblack", "fadewhite", "smoothleft", "smoothright", "smoothup", "smoothdown",
    "circleopen", "circleclose", "zoomin", "slideleft", "slideright", "slideup", "slidedown", "wipeleft",
    "wiperight", "radial", "hblur", "pixelize", "distance", "squeezeh", "squeezev", "hlslice", "diagtl",
}
TRANSITION_ALIASES = {
    "smooth": "smoothleft", "crossfade": "fade", "cross": "fade", "zoom": "zoomin", "whip": "hblur",
    "blur": "hblur", "slide": "slideleft", "wipe": "wipeleft", "circle": "circleopen", "flash": "fadewhite",
    "dip": "fadeblack", "cut": "cut", "glitch": "glitch",
}


def transition_name(name: str) -> str:
    n = TRANSITION_ALIASES.get(name, name)
    if n not in XFADE | {"cut", "glitch"}:
        raise ValueError(f"Unknown transition '{name}'. Options: {sorted(XFADE | set(TRANSITION_ALIASES))}")
    return n


# ---------------------------------------------------------------- generated overlays
def make_light_leak(out: Path, w: int, h: int, dur: float, fps: int, seed: int = 3,
                    windows: list[tuple[float, float]] | None = None) -> Path:
    """Procedural light-leak clip (warm drifting blobs), rendered at 1/4 res and upscaled by FFmpeg.

    If `windows` is given, the leak is only visible (with soft in/out) during those times."""
    rng = np.random.default_rng(seed)
    lw, lh = max(64, w // 4) // 2 * 2, max(64, h // 4) // 2 * 2
    n = int(round(dur * fps))
    yy, xx = np.mgrid[0:lh, 0:lw].astype(np.float32)
    blobs = []
    for _ in range(3):
        blobs.append(dict(cx=rng.uniform(-0.2, 1.2), cy=rng.uniform(-0.2, 1.2), vx=rng.uniform(-0.15, 0.15),
                          vy=rng.uniform(-0.1, 0.1), r=rng.uniform(0.35, 0.7),
                          col=np.array(rng.choice([[255, 120, 40], [255, 70, 90], [255, 190, 90], [250, 90, 30]]), np.float32)))
    cmd = [config.ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{lw}x{lh}",
           "-r", str(fps), "-i", "-", "-vf", f"scale={w}:{h}:flags=bicubic,gblur=sigma=6", "-c:v", "libx264",
           "-crf", "16", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        t = i / fps
        if windows:
            a = 0.0
            for (s, e) in windows:
                if s <= t <= e:
                    m = (e - s) / 2
                    a = max(a, 1 - abs(t - (s + m)) / max(m, 1e-3))
            gate = a ** 0.7
        else:
            gate = 0.65 + 0.35 * math.sin(t * 1.3)
        img = np.zeros((lh, lw, 3), np.float32)
        for b in blobs:
            cx = (b["cx"] + b["vx"] * t) * lw
            cy = (b["cy"] + b["vy"] * t) * lh
            r = b["r"] * max(lw, lh)
            d2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / (r * r)
            img += np.exp(-d2 * 2.2)[..., None] * b["col"]
        img = np.clip(img * gate, 0, 255).astype(np.uint8)
        p.stdin.write(img.tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("light leak generation failed")
    return out
