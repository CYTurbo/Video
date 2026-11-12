"""Automated output inspection and auto-correction.

`check()` never trusts that a render command "completed": it re-probes the file, decodes every frame,
looks for black/frozen/silent stretches, measures loudness and samples frames for blank output.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from . import config
from .log import log
from .media import contact_sheet, probe, run


def _detect(path: str, vf: str | None = None, af: str | None = None) -> str:
    cmd = [config.ffmpeg(), "-hide_banner", "-nostats", "-i", path]
    if vf:
        cmd += ["-vf", vf]
    else:
        cmd += ["-vn"]
    if af:
        cmd += ["-af", af]
    else:
        cmd += ["-an"]
    cmd += ["-f", "null", "-"]
    return run(cmd, check=False).stderr


def decode_errors(path: str) -> list[str]:
    cp = run([config.ffmpeg(), "-v", "error", "-i", path, "-f", "null", "-"], check=False)
    return [ln for ln in cp.stderr.splitlines() if ln.strip()][:20]


def black_segments(path: str, min_dur: float = 0.4) -> list[tuple[float, float]]:
    err = _detect(path, vf=f"blackdetect=d={min_dur}:pix_th=0.08")
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)]


def frozen_segments(path: str, min_dur: float = 1.5) -> list[tuple[float, float]]:
    err = _detect(path, vf=f"freezedetect=n=0.002:d={min_dur}")
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", err)]
    return list(zip(starts, ends + [float("nan")] * (len(starts) - len(ends))))


def silent_segments(path: str, min_dur: float = 1.0) -> list[tuple[float, float]]:
    err = _detect(path, af=f"silencedetect=n=-50dB:d={min_dur}")
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.\-]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    return list(zip(starts, ends + [float("nan")] * (len(starts) - len(ends))))


def frame_stats(path: str, n: int = 8) -> list[dict]:
    """Mean/std luminance of N sampled frames (detects blank or garbage renders)."""
    import cv2

    info = probe(path)
    dur = info["duration"]
    out = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        import subprocess
        raw = subprocess.run([config.ffmpeg(), "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
                              "-vf", "scale=320:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                             capture_output=True).stdout
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE) if raw else None
        if img is None:
            out.append({"t": round(t, 2), "ok": False})
            continue
        out.append({"t": round(t, 2), "ok": True, "mean": round(float(img.mean()), 1), "std": round(float(img.std()), 1),
                    "clip_hi": round(float((img >= 250).mean()), 3), "clip_lo": round(float((img <= 5).mean()), 3)})
    return out


def check(path: str | Path, expect: dict | None = None, sheet: bool = True) -> dict:
    """Return a QC report. `expect` may contain width, height, fps, duration, vcodec, acodec, audio (bool),
    duration_tol, lufs (target), lufs_tol."""
    expect = expect or {}
    path = str(path)
    rep: dict = {"file": path, "problems": [], "warnings": []}
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        rep["problems"].append("output file missing or empty")
        rep["passed"] = False
        return rep
    info = probe(path)
    rep["probe"] = info
    v = info["video"]
    if not v:
        rep["problems"].append("no video stream")
    else:
        for k in ("width", "height"):
            if k in expect and v[k] != expect[k]:
                rep["problems"].append(f"{k} {v[k]} != expected {expect[k]}")
        if "fps" in expect and abs(v["fps"] - expect["fps"]) > 0.05:
            rep["problems"].append(f"fps {v['fps']} != expected {expect['fps']}")
        if "vcodec" in expect and v["codec"] != expect["vcodec"]:
            rep["problems"].append(f"video codec {v['codec']} != {expect['vcodec']}")
        if v["pix_fmt"] not in ("yuv420p", "yuvj420p") and expect.get("vcodec") == "h264":
            rep["warnings"].append(f"pix_fmt {v['pix_fmt']} may not play on phones/social apps")
    if "duration" in expect:
        tol = expect.get("duration_tol", 0.15)
        if abs(info["duration"] - expect["duration"]) > tol:
            rep["problems"].append(f"duration {info['duration']:.3f}s != expected {expect['duration']}s (tol {tol})")
    want_audio = expect.get("audio", None)
    if want_audio and not info["audio"]:
        rep["problems"].append("expected an audio track but none found")
    if info["audio"]:
        a = info["audio"][0]
        if "acodec" in expect and a["codec"] != expect["acodec"]:
            rep["problems"].append(f"audio codec {a['codec']} != {expect['acodec']}")
        if v and a["duration"] and v["duration"] and abs(a["duration"] - v["duration"]) > 0.2:
            rep["problems"].append(f"audio/video length mismatch: a={a['duration']:.2f}s v={v['duration']:.2f}s")

    errs = decode_errors(path)
    if errs:
        rep["problems"].append(f"decode errors: {errs[:3]}")
    rep["black_segments"] = black_segments(path)
    for a, b in rep["black_segments"]:
        if b - a > expect.get("max_black", 0.6):
            rep["problems"].append(f"black frames {a:.2f}-{b:.2f}s")
    rep["frozen_segments"] = frozen_segments(path, expect.get("max_freeze", 1.5))
    if rep["frozen_segments"] and not expect.get("allow_freeze"):
        dur = info["duration"] or 1
        frozen = sum((b if b == b else dur) - a for a, b in rep["frozen_segments"])
        msg = f"frozen video {frozen:.1f}s total {rep['frozen_segments'][:3]}"
        if frozen > max(2.0, 0.2 * dur):
            rep["problems"].append(msg)
        else:
            rep["warnings"].append(msg)
    if info["audio"]:
        rep["silent_segments"] = silent_segments(path)
        from .audio import loudness
        rep["loudness"] = {k: v for k, v in loudness(path).items() if not k.startswith("_")}
        if "lufs" in expect and rep["loudness"]:
            if abs(rep["loudness"]["lufs"] - expect["lufs"]) > expect.get("lufs_tol", 2.0):
                rep["problems"].append(f"loudness {rep['loudness']['lufs']} LUFS, target {expect['lufs']}")
    fs = frame_stats(path)
    rep["frame_stats"] = fs
    bad = [f for f in fs if not f["ok"] or f["std"] < 2.0]
    if len(bad) >= max(2, len(fs) // 2):
        rep["problems"].append(f"{len(bad)}/{len(fs)} sampled frames are blank/flat or undecodable")
    over = [f["t"] for f in fs if f.get("ok") and f["clip_hi"] > 0.25]
    under = [f["t"] for f in fs if f.get("ok") and f["clip_lo"] > 0.5]
    if over:
        rep["warnings"].append(f"overexposed (>25% clipped highlights) at t={over} - consider a darker grade/LUT")
    if under:
        rep["warnings"].append(f"crushed shadows (>50% pure black) at t={under}")
    if sheet:
        rep["contact_sheet"] = str(contact_sheet(path, p.with_suffix(".contact.png")))
    rep["passed"] = not rep["problems"]
    return rep


def autofix(path: str | Path, rep: dict, expect: dict) -> Path | None:
    """Fix the detectable, mechanical problems (size, fps, duration, codecs, loudness, missing audio).
    Returns a new file path, or None if nothing fixable was found. The input is never overwritten."""
    from .audio import loudnorm_filter

    path = Path(path)
    if any(k in " ".join(rep.get("problems", [])) for k in ("frozen", "blank", "decode", "no video")):
        return None  # content problems need a re-render, not a re-encode
    probs = " | ".join(rep.get("problems", [])) + " | " + " | ".join(rep.get("warnings", []))
    if not probs.strip(" |"):
        return None
    out = path.with_name(path.stem + "_fixed" + path.suffix)
    vf, af, pre = [], [], []
    W, H, fps, D = expect.get("width"), expect.get("height"), expect.get("fps"), expect.get("duration")
    if W and H and ("width" in probs or "height" in probs):
        vf += [f"scale={W}:{H}:force_original_aspect_ratio=increase", f"crop={W}:{H}", "setsar=1"]
    if fps and "fps" in probs:
        vf.append(f"fps={fps}")
    if D and "duration" in probs:
        vf.append(f"tpad=stop_mode=clone:stop_duration={D}")
    vf.append("format=yuv420p")
    has_audio = bool(rep.get("probe", {}).get("audio"))
    if "loudness" in probs and has_audio:
        af.append(loudnorm_filter(path, target=expect.get("lufs", -14)))
    if D and has_audio:
        af.append(f"apad=whole_dur={D}")
    cmd = [config.ffmpeg(), "-y", "-v", "error", "-i", str(path)]
    if expect.get("audio") and not has_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        pre = ["-map", "0:v", "-map", "1:a"]
    cmd += pre + ["-vf", ",".join(vf)]
    if af:
        cmd += ["-af", ",".join(af)]
    if D:
        cmd += ["-t", f"{D}"]
    cmd += ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart", str(out)]
    log(f"QC auto-fix -> {out.name}  ({probs.strip(' |')[:200]})")
    run(cmd)
    return out


def check_and_fix(path: str | Path, expect: dict, max_rounds: int = 2) -> tuple[Path, dict]:
    cur = Path(path)
    rep = check(cur, expect)
    rounds = 0
    while not rep["passed"] and rounds < max_rounds:
        fixed = autofix(cur, rep, expect)
        if not fixed:
            break
        cur = fixed
        rep = check(cur, expect)
        rep["autofixed"] = True
        rounds += 1
    rep_path = cur.with_suffix(".qc.json")
    rep_path.write_text(json.dumps(rep, indent=2, default=str))
    return cur, rep


def summarize(rep: dict) -> str:
    v = (rep.get("probe") or {}).get("video") or {}
    a = ((rep.get("probe") or {}).get("audio") or [{}])[0] if (rep.get("probe") or {}).get("audio") else {}
    s = (f"{'PASS' if rep.get('passed') else 'FAIL'}  {Path(rep['file']).name}: {v.get('width')}x{v.get('height')} "
         f"{v.get('fps')}fps {v.get('codec')}/{a.get('codec', 'no-audio')} {rep.get('probe', {}).get('duration', 0):.2f}s")
    if rep.get("loudness"):
        s += f" {rep['loudness']['lufs']:.1f} LUFS"
    for p in rep.get("problems", []):
        s += f"\n   ✗ {p}"
    for w in rep.get("warnings", []):
        s += f"\n   ! {w}"
    return s
