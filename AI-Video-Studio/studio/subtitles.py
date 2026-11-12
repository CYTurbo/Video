"""Local speech-to-text (faster-whisper, MIT, runs offline after a one-time model download)
and styled caption generation (ASS, burned in with libass)."""
from __future__ import annotations

import re
from pathlib import Path

from . import config
from .log import log

MODELS_DIR = config.ROOT / "models"

STYLES = {
    # name: (font size as fraction of height, primary, highlight, outline, box?)
    "bold_pop": dict(size=0.052, primary="&H00FFFFFF", highlight="&H0000D7FF", outline=6, box=False, upper=True),
    "clean": dict(size=0.040, primary="&H00FFFFFF", highlight="&H00FFFFFF", outline=3, box=False, upper=False),
    "boxed": dict(size=0.040, primary="&H00FFFFFF", highlight="&H0066E0FF", outline=0, box=True, upper=False),
    "neon": dict(size=0.048, primary="&H00FFF0B0", highlight="&H00FF60FF", outline=4, box=False, upper=True),
}


def transcribe(media: str | Path, model: str = "small", language: str | None = None, device: str = "auto") -> list[dict]:
    """Return segments [{start,end,text,words:[{start,end,word}]}]. Downloads the model once (free, from Hugging Face)."""
    from faster_whisper import WhisperModel

    MODELS_DIR.mkdir(exist_ok=True)
    compute = "int8"
    if device == "auto":
        try:
            import ctranslate2
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:  # noqa: BLE001
            device = "cpu"
        if device == "cuda":
            compute = "float16"
    log(f"   whisper: model={model} device={device} ({compute})")
    m = WhisperModel(model, device=device, compute_type=compute, download_root=str(MODELS_DIR))
    segs, info = m.transcribe(str(media), language=language, word_timestamps=True, vad_filter=True)
    out = []
    for s in segs:
        out.append({"start": s.start, "end": s.end, "text": s.text.strip(),
                    "words": [{"start": w.start, "end": w.end, "word": w.word.strip()} for w in (s.words or [])]})
    log(f"   whisper: {len(out)} segments, language={info.language}")
    return out


def _ts_srt(t: float) -> str:
    h, rem = divmod(max(0, t), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)) % 1000:03d}"


def write_srt(segs: list[dict], out: Path) -> Path:
    lines = []
    for i, s in enumerate(segs, 1):
        lines += [str(i), f"{_ts_srt(s['start'])} --> {_ts_srt(s['end'])}", s["text"], ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def read_srt(path: str | Path) -> list[dict]:
    txt = Path(path).read_text(encoding="utf-8-sig")
    out = []
    for block in re.split(r"\n\s*\n", txt.strip()):
        ls = [l for l in block.splitlines() if l.strip()]
        tl = next((l for l in ls if "-->" in l), None)
        if not tl:
            continue
        a, b = [x.strip() for x in tl.split("-->")]

        def p(x):
            h, m, s = x.replace(",", ".").split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        text = " ".join(ls[ls.index(tl) + 1:])
        st, en = p(a), p(b)
        words = text.split()
        # no word timings in SRT -> distribute evenly (good enough for highlight styles)
        step = (en - st) / max(1, len(words))
        out.append({"start": st, "end": en, "text": text,
                    "words": [{"start": st + i * step, "end": st + (i + 1) * step, "word": w} for i, w in enumerate(words)]})
    return out


def _ts_ass(t: float) -> str:
    h, rem = divmod(max(0, t), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_ass(segs: list[dict], out: Path, W: int, H: int, style: str = "bold_pop", position: str = "lower",
              max_words: int = 3) -> Path:
    """Short, punchy caption chunks (max_words per line) with the active word highlighted."""
    st = STYLES.get(style, STYLES["bold_pop"])
    size = int(H * st["size"]) if H > W else int(H * st["size"] * 1.25)
    align = {"lower": 2, "center": 5, "upper": 8}.get(position, 2)
    marginv = int(H * (0.22 if H > W else 0.08)) if align == 2 else int(H * 0.1)
    border = 3 if st["box"] else 1
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Arial,{size},{st['primary']},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,{border},{st['outline'] if not st['box'] else 12},2,{align},60,60,{marginv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for s in segs:
        words = s.get("words") or [{"start": s["start"], "end": s["end"], "word": w} for w in s["text"].split()]
        for i in range(0, len(words), max_words):
            chunk = words[i:i + max_words]
            c0, c1 = chunk[0]["start"], chunk[-1]["end"]
            for j, w in enumerate(chunk):
                ws = w["start"]
                we = chunk[j + 1]["start"] if j + 1 < len(chunk) else c1
                parts = []
                for k, x in enumerate(chunk):
                    t = x["word"].upper() if st["upper"] else x["word"]
                    t = t.replace("{", "(").replace("}", ")")
                    if k == j:
                        parts.append(f"{{\\c{st['highlight']}\\fscx108\\fscy108}}{t}{{\\c{st['primary']}\\fscx100\\fscy100}}")
                    else:
                        parts.append(t)
                pop = "{\\fad(60,0)\\t(0,90,\\fscx104\\fscy104)\\t(90,180,\\fscx100\\fscy100)}" if j == 0 else ""
                ev.append(f"Dialogue: 0,{_ts_ass(ws if j else c0)},{_ts_ass(we)},Cap,,0,0,0,,{pop}{' '.join(parts)}")
    out.write_text(head + "\n".join(ev) + "\n", encoding="utf-8")
    return out


def prepare_ass(cap: dict, plan: dict, work: Path) -> Path | None:
    """From a plan's `captions` block: use a given .srt/.ass, or auto-transcribe the speech source."""
    W, H = plan["width"], plan["height"]
    style = cap.get("style", "bold_pop")
    if cap.get("ass"):
        return Path(cap["ass"])
    if cap.get("srt"):
        segs = read_srt(cap["srt"])
    elif cap.get("auto"):
        src = cap.get("source") or next((c["src"] for c in plan["clips"] if Path(c["src"]).suffix.lower() not in
                                         {".png", ".jpg", ".jpeg", ".webp"}), None)
        if not src:
            return None
        segs = transcribe(src, model=cap.get("model", "small"), language=cap.get("language"))
        write_srt(segs, work / "captions.srt")
    else:
        return None
    return write_ass(segs, work / "captions.ass", W, H, style, cap.get("position", "lower"), cap.get("max_words", 3))
