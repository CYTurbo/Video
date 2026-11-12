"""Synthetic, license-free test assets (procedural 'footage', images and music).

Used by the automated tests so nothing has to be downloaded and no copyrighted media is involved.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from . import config
from .audio import synth_music


def _pipe_writer(out: Path, w: int, h: int, fps: int, scale_to: tuple[int, int] | None = None):
    vf = f"scale={scale_to[0]}:{scale_to[1]}:flags=bicubic" if scale_to else "null"
    cmd = [config.ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
           "-i", "-", "-vf", vf, "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out)]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def bokeh_city(out: Path, dur: float = 6, fps: int = 30, seed: int = 1, warm: bool = True) -> Path:
    """Night-city style bokeh lights drifting with a slow camera pan."""
    w, h = 480, 270
    rng = np.random.default_rng(seed)
    n = 60
    xs, ys = rng.uniform(-0.2, 1.4, n), rng.uniform(0, 1, n)
    rs = rng.uniform(6, 26, n)
    pal = np.array([[255, 170, 60], [255, 90, 60], [255, 220, 150], [80, 160, 255], [255, 120, 200]] if warm else
                   [[60, 160, 255], [120, 220, 255], [180, 120, 255], [255, 255, 255], [60, 255, 200]], np.float32)
    cols = pal[rng.integers(0, len(pal), n)]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    p = _pipe_writer(out, w, h, fps, (1920, 1080))
    for i in range(int(dur * fps)):
        t = i / fps
        img = np.zeros((h, w, 3), np.float32)
        img += np.linspace(10, 35, h)[:, None, None] * np.array([0.4, 0.5, 1.0])
        pan = t * 0.06
        for k in range(n):
            cx = ((xs[k] - pan * (0.5 + rs[k] / 26)) % 1.6 - 0.2) * w
            cy = ys[k] * h + np.sin(t * 0.7 + k) * 3
            d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            disk = np.clip((rs[k] - d) / 2.0, 0, 1) * (0.35 + 0.25 * np.sin(t * 2 + k) ** 2)
            img += disk[..., None] * cols[k]
        img += rng.normal(0, 2, img.shape)
        p.stdin.write(np.clip(img, 0, 255).astype(np.uint8).tobytes())
    p.stdin.close(); p.wait()
    return out


def ocean_sunset(out: Path, dur: float = 6, fps: int = 30, seed: int = 2) -> Path:
    """Gradient sky, sun, animated waves, slow push-in."""
    w, h = 480, 270
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    p = _pipe_writer(out, w, h, fps, (1920, 1080))
    horizon = h * 0.55
    for i in range(int(dur * fps)):
        t = i / fps
        z = 1 + 0.05 * t / dur
        X = (xx - w / 2) / z + w / 2
        Y = (yy - h / 2) / z + h / 2
        sky_t = np.clip(Y / horizon, 0, 1)[..., None]
        sky = (1 - sky_t) * np.array([40, 60, 140]) + sky_t * np.array([255, 150, 80])
        sun = np.exp(-(((X - w * 0.6) ** 2 + (Y - horizon * 0.82) ** 2) / (2 * 22 ** 2)))[..., None] * np.array([255, 230, 170])
        depth = np.clip((Y - horizon) / (h - horizon), 1e-3, 1)
        wave = np.sin(X * 0.08 / depth ** 0.6 + t * 2.0 + np.sin(Y * 0.3) * 2) * 0.5 + 0.5
        sea = (np.array([20, 40, 80]) + wave[..., None] * np.array([60, 60, 70]) * depth[..., None])
        glint = np.exp(-((X - w * 0.6) ** 2) / (2 * (10 + 40 * depth) ** 2))[..., None] * wave[..., None] ** 3 * np.array([255, 190, 120])
        img = np.where((Y < horizon)[..., None], sky + sun, sea + glint)
        p.stdin.write(np.clip(img, 0, 255).astype(np.uint8).tobytes())
    p.stdin.close(); p.wait()
    return out


def neon_tunnel(out: Path, dur: float = 6, fps: int = 30) -> Path:
    """Fast forward motion through neon rings (good for speed ramps / motion blur)."""
    w, h = 480, 270
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w / 2, h / 2
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) + 1
    ang = np.arctan2(yy - cy, xx - cx)
    p = _pipe_writer(out, w, h, fps, (1920, 1080))
    for i in range(int(dur * fps)):
        t = i / fps
        depth = 400 / r + t * 6
        rings = (np.sin(depth * 3.0) > 0.85).astype(np.float32)
        hue = (depth * 0.15 + ang / np.pi * 0.2) % 1
        col = np.stack([0.5 + 0.5 * np.sin(6.28 * hue), 0.5 + 0.5 * np.sin(6.28 * hue + 2.1), 0.5 + 0.5 * np.sin(6.28 * hue + 4.2)], -1)
        stripes = (np.sin(ang * 12 + t * 2) > 0.7) * 0.25
        img = (rings[..., None] + stripes[..., None]) * col * 255 * np.clip(r / 120, 0.2, 1)[..., None]
        p.stdin.write(np.clip(img, 0, 255).astype(np.uint8).tobytes())
    p.stdin.close(); p.wait()
    return out


def mountains(out: Path, dur: float = 6, fps: int = 30, seed: int = 4) -> Path:
    """Layered parallax mountain ridges with drifting fog (lateral camera move)."""
    w, h = 480, 270
    rng = np.random.default_rng(seed)
    xs = np.arange(w, dtype=np.float32)
    layers = []
    for k in range(4):
        freqs = rng.uniform(0.004, 0.03, 5)
        phases = rng.uniform(0, 6.28, 5)
        layers.append((freqs, phases, h * (0.35 + 0.13 * k), 0.4 + k * 0.6, np.array([90 - k * 18, 110 - k * 20, 150 - k * 25], np.float32)))
    yy = np.arange(h, dtype=np.float32)[:, None]
    p = _pipe_writer(out, w, h, fps, (1920, 1080))
    for i in range(int(dur * fps)):
        t = i / fps
        img = np.zeros((h, w, 3), np.float32) + (np.array([200, 210, 230]) - yy[..., None] * np.array([0.3, 0.2, 0.0]))
        for freqs, phases, base, speed, col in layers:
            x = xs + t * 25 * speed
            ridge = base + sum(18 / (j + 1) * np.sin(x * f + ph) for j, (f, ph) in enumerate(zip(freqs, phases)))
            mask = (yy > ridge[None, :])[..., None]
            img = np.where(mask, col, img)
        fog = (0.5 + 0.5 * np.sin(xs[None, :] * 0.02 + t * 0.6 + yy * 0.05)) * np.clip((yy - h * 0.5) / h, 0, 1) * 70
        img += fog[..., None]
        p.stdin.write(np.clip(img, 0, 255).astype(np.uint8).tobytes())
    p.stdin.close(); p.wait()
    return out


def fractal_zoom(out: Path, dur: float = 6, fps: int = 30) -> Path:
    config_ff = config.ffmpeg()
    subprocess.run([config_ff, "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"mandelbrot=s=960x540:rate={fps}:start_scale=2.5:end_scale=0.05:outer=normalized_iteration_count",
                    "-t", str(dur), "-vf", "scale=1920:1080:flags=bicubic,hue=h=t*20", "-c:v", "libx264", "-crf", "18",
                    "-preset", "veryfast", "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


def talking_tone(out: Path, dur: float = 6, fps: int = 30) -> Path:
    """A clip WITH an audio track (sine sweep + noise) to test keep-original-audio and A/V sync."""
    subprocess.run([config.ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", f"gradients=s=1920x1080:r={fps}:speed=0.02:n=4",
                    "-f", "lavfi", "-i", f"aevalsrc='0.3*sin(2*PI*(220+40*sin(2*PI*0.5*t))*t)':s=48000:d={dur}",
                    "-t", str(dur), "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)], check=True)
    return out


def still_image(out: Path, text: str = "PHOTO", seed: int = 5) -> Path:
    from PIL import Image, ImageDraw, ImageFilter
    rng = np.random.default_rng(seed)
    w, h = 2400, 1600
    arr = np.zeros((h, w, 3), np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    for _ in range(6):
        cx, cy, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(300, 900)
        c = rng.uniform(40, 255, 3)
        arr += np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r))[..., None] * c
    arr = arr / max(arr.max(), 1) * 220  # keep highlights below clipping
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(4))
    d = ImageDraw.Draw(im)
    for k in range(12):
        x0, y0 = rng.uniform(0, w), rng.uniform(0, h)
        d.rectangle([x0, y0, x0 + rng.uniform(80, 300), y0 + rng.uniform(80, 300)], outline=(255, 255, 255), width=6)
    im.save(out, quality=92)
    return out


def make_all(folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    out = {
        "bokeh": bokeh_city(folder / "clip_bokeh_city.mp4"),
        "ocean": ocean_sunset(folder / "clip_ocean_sunset.mp4"),
        "tunnel": neon_tunnel(folder / "clip_neon_tunnel.mp4"),
        "mountains": mountains(folder / "clip_mountains.mp4"),
        "fractal": fractal_zoom(folder / "clip_fractal.mp4"),
        "withaudio": talking_tone(folder / "clip_with_audio.mp4"),
        "image": still_image(folder / "image_abstract.jpg"),
        "music": folder / "music_120bpm.wav",
    }
    synth_music(out["music"], duration=22, bpm=120)
    return {k: str(v) for k, v in out.items()}
