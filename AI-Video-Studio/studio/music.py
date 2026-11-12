"""Music structure map: the musical skeleton an edit is built on.

analyze(path) returns
  tempo_bpm, tempo_curve        global tempo + local tempo every ~4 s (flags tempo changes)
  beats, downbeats, bars        4/4 assumed; downbeat phase chosen by kick/bass accent strength
  phrases                       groups of 4 bars starting on downbeats (8-bar phrases = every 2nd)
  kicks, snares, hats           per-band percussive hits (HPSS + band-limited onset envelopes), with strength
  energy                        0..1 loudness curve (10 Hz) and per-bar energy / low-end / onset density
  sections                      contiguous bar ranges labelled intro / verse / build / drop / break / outro
  drops                         times where energy + low end jump after a quieter/building passage
  builds                        rising-density passages that lead into a drop
  accents                       the strongest few hits (where high-impact effects are allowed)

Everything is local and free (librosa, ISC). Assumes 4/4; odd meters and rubato get approximate bars.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .audio import analyze_beats, load_mono
from .log import log

SR = 22050
HOP = 256  # ~11.6 ms resolution for hit timing


def _band_level(P: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Band power in dB per frame (relative to the band's own loudest frame)."""
    band = P[(freqs >= lo) & (freqs < hi)].sum(axis=0) + 1e-12
    db = 10 * np.log10(band)
    return db - db.max()


def _band_hits(level_db: np.ndarray, times: np.ndarray, min_gap: float, gate_db: float = -24.0,
               rise_db: float = 9.0) -> list[dict]:
    """Onsets in one band. A hit is the first frame where the band level comes within 6 dB of its local
    peak (next ~90 ms), after rising by more than `rise_db` (+ local 1-s baseline) over the previous ~60 ms,
    and the peak is above `gate_db` (relative to the band's loudest frame).
    Timing uses the attack itself, not the start of the slope: the STFT window + HPSS smear the slope
    ~70 ms early, which is what broke the first version."""
    from scipy.ndimage import median_filter
    n = len(level_db)
    look, back = 8, 5
    pre_min = np.array([level_db[max(0, i - back):i].min() if i > 0 else level_db[0] for i in range(n)])
    rise = level_db - pre_min
    base = median_filter(np.maximum(rise, 0), size=max(3, int(1.0 / (HOP / SR))))
    gap = max(1, int(min_gap / (HOP / SR)))
    out, last = [], -10 ** 9
    for i in range(1, n):
        if i - last < gap:
            continue
        pk = level_db[i:min(n, i + look)].max()
        if pk < gate_db:
            continue
        if level_db[i] >= pk - 6.0 and level_db[i - 1] < pk - 6.0 and rise[i] > rise_db + base[i]:
            out.append((i, float(rise[i])))
            last = i
    if not out:
        return []
    mx = max(v for _, v in out)
    return [{"t": round(float(times[j]), 4), "s": round(v / mx, 3), "_i": j} for j, v in out]


def analyze(path: str | Path, out_dir: Path | None = None) -> dict:
    import librosa

    path = str(path)
    y, sr = load_mono(path, sr=SR)
    D = len(y) / sr
    log(f"== Music structure: {Path(path).name} ({D:.1f}s)")
    bt = analyze_beats(path)
    beats = np.array(bt["beats"])
    tempo = bt["tempo_bpm"]

    # --- percussive bands (HPSS percussive part, per-band power)
    y_h, y_p = librosa.effects.hpss(y)
    P = np.abs(librosa.stft(y_p, n_fft=1024, hop_length=HOP)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=1024)
    times = librosa.frames_to_time(np.arange(P.shape[1]), sr=sr, hop_length=HOP)
    lv_kick = _band_level(P, freqs, 30, 150)
    lv_mid = _band_level(P, freqs, 1500, 5000)
    lv_hat = _band_level(P, freqs, 7000, 11000)
    kicks = _band_hits(lv_kick, times, 0.09)
    mids = _band_hits(lv_mid, times, 0.05)
    hats = _band_hits(lv_hat, times, 0.04)
    # snare vs hat: a snare puts relatively more energy in 1.5-5 kHz than above 7 kHz (absolute band power ratio)
    mid_abs = P[(freqs >= 1500) & (freqs < 5000)].sum(axis=0) + 1e-12
    hi_abs = P[(freqs >= 7000) & (freqs < 11000)].sum(axis=0) + 1e-12
    snares = []
    for h in mids:
        j = h["_i"]
        seg = slice(j, min(len(times), j + 6))
        ratio = float(mid_abs[seg].sum() / hi_abs[seg].sum())
        if ratio > 0.5:  # measured: snares 0.86-1.06, hats 0.18-0.23 on the ground-truth track
            snares.append(h)
    for lst in (kicks, snares, hats):
        for h in lst:
            h.pop("_i", None)
    e_kick = np.maximum(0, np.r_[0, 0, lv_kick[2:] - lv_kick[:-2]])
    e_kick /= e_kick.max() + 1e-9

    # --- energy curve (10 Hz) and low-end curve
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    rms_db = librosa.amplitude_to_db(rms + 1e-6, ref=np.max)
    S_full = np.abs(librosa.stft(y, n_fft=2048, hop_length=HOP))
    f_full = librosa.fft_frequencies(sr=sr, n_fft=2048)
    low = S_full[(f_full >= 30) & (f_full < 150)].mean(axis=0)
    low_db = librosa.amplitude_to_db(low + 1e-6, ref=np.max)

    def norm_db(x):
        x = np.clip(x, -60, 0)
        return (x + 60) / 60

    energy = norm_db(rms_db)
    lowe = norm_db(low_db)

    # --- downbeat phase: which of the 4 beat phases carries the strongest kick/low-end accent
    if len(beats) >= 8:
        def at(curve, t):
            return curve[np.clip(np.searchsorted(times, t), 0, len(curve) - 1)]
        scores = []
        for ph in range(4):
            sel = beats[ph::4]
            scores.append(float(np.mean([max(at(e_kick, b), 0) + 0.5 * at(lowe, b) for b in sel])))
        # tie-break: bass/harmony changes happen on downbeats -> chroma novelty
        chroma = librosa.feature.chroma_stft(y=y_h, sr=sr, hop_length=HOP)
        nov = np.r_[0, np.linalg.norm(np.diff(chroma, axis=1), axis=0)]
        for ph in range(4):
            scores[ph] += 0.3 * float(np.mean([at(nov / (nov.max() + 1e-9), b) for b in beats[ph::4]]))
        phase = int(np.argmax(scores))
    else:
        phase = 0
    downbeats = beats[phase::4]
    # extrapolate bar grid backwards to cover the intro before the first detected downbeat
    if len(beats) > 3:
        period = float(np.polyfit(np.arange(len(beats)), beats, 1)[0])
        first = downbeats[0] if len(downbeats) else 0.0
        pre = np.arange(first - 4 * period, -period * 0.5, -4 * period)[::-1]
        downbeats = np.r_[pre[pre >= -0.05], downbeats]
    downbeats = np.clip(downbeats, 0, None)
    bars_edges = list(downbeats) + [D]

    # --- continuous activity: positive level rises in mid + high percussive bands (dB per frame)
    act_curve = np.r_[0, np.maximum(0, np.diff(lv_mid))] + np.r_[0, np.maximum(0, np.diff(lv_hat))]
    Pf = np.abs(librosa.stft(y, n_fft=1024, hop_length=HOP)) ** 2
    lv_hat_full = _band_level(Pf, freqs, 7000, 11000)

    # --- per-bar features
    bars = []
    for i in range(len(bars_edges) - 1):
        a, b = bars_edges[i], bars_edges[i + 1]
        m = (times >= a) & (times < b)
        if not m.any():
            continue
        mt = (times >= a) & (times < b)
        # continuous percussive activity (works for rolls whose hits are too dense to separate) + riser level
        act = float(act_curve[mt].mean()) if mt.any() else 0.0
        riser = float(lv_hat_full[mt].mean()) if mt.any() else -60.0
        bars.append({"i": i, "start": round(float(a), 4), "end": round(float(b), 4),
                     "energy": round(float(energy[m].mean()), 3), "low": round(float(lowe[m].mean()), 3),
                     "density": round(act, 3), "riser_db": round(riser, 1),
                     "kicks": sum(1 for h in kicks if a <= h["t"] < b and h["s"] > 0.25)})
    E = np.array([b["energy"] for b in bars]) if bars else np.array([0.0])
    L = np.array([b["low"] for b in bars]) if bars else np.array([0.0])
    DEN = np.array([b["density"] for b in bars]) if bars else np.array([0.0])
    K = np.array([b["kicks"] for b in bars]) if bars else np.array([0])
    RIS = np.array([b["riser_db"] for b in bars]) if bars else np.array([0.0])

    # --- section boundaries: change in (energy, low, density, kick count) between 2-bar windows
    feat = np.stack([E / (E.max() + 1e-9), L / (L.max() + 1e-9), DEN / (DEN.max() + 1e-9), K / (K.max() + 1e-9)], 1)
    nb = len(bars)
    nov = np.zeros(nb)
    for i in range(1, nb):
        a = feat[max(0, i - 2):i].mean(0)
        c = feat[i:min(nb, i + 2)].mean(0)
        nov[i] = float(np.linalg.norm(c - a))
    cut_idx = [0]
    for i in range(1, nb):
        local = nov[max(1, i - 2):min(nb, i + 3)]
        if nov[i] >= local.max() and nov[i] > 0.25 and i - cut_idx[-1] >= 2:
            cut_idx.append(i)
    sections = []
    for k, s in enumerate(cut_idx):
        e = cut_idx[k + 1] if k + 1 < len(cut_idx) else nb
        sl = slice(s, e)
        sections.append({"start": bars[s]["start"], "end": bars[e - 1]["end"], "bars": e - s,
                         "energy": round(float(E[sl].mean()), 3), "low": round(float(L[sl].mean()), 3),
                         "density": round(float(DEN[sl].mean()), 2), "kick_bars": int((K[sl] >= 2).sum()),
                         "density_slope": round(float(np.polyfit(np.arange(e - s), DEN[sl], 1)[0]) if e - s >= 2 else 0.0, 3),
                         "riser_slope": round(float(np.polyfit(np.arange(e - s), RIS[sl], 1)[0]) if e - s >= 2 else 0.0, 2)})
    # --- label sections (relative to the track's own range)
    hi_e = np.percentile(E, 75) if nb else 0
    for k, s in enumerate(sections):
        full = s["kick_bars"] >= max(1, s["bars"] // 2) and s["low"] >= np.percentile(L, 60)
        nxt = sections[k + 1] if k + 1 < len(sections) else None
        nxt_full = nxt and nxt["kick_bars"] >= max(1, nxt["bars"] // 2)
        if full:
            s["label"] = "drop" if s["energy"] >= hi_e * 0.92 else "verse"
        # a build must actually RISE (riser noise / rolls getting louder or denser), not just precede a drop
        elif nxt_full and (s["riser_slope"] > 1.0 or s["density_slope"] > 0.05 * (DEN.max() + 1e-9)):
            s["label"] = "build"
        elif k == 0:
            s["label"] = "intro"
        elif k == len(sections) - 1:
            s["label"] = "outro"
        else:
            s["label"] = "break"
    drops = [s["start"] for k, s in enumerate(sections) if s["label"] == "drop" and
             (k == 0 or sections[k - 1]["label"] in ("build", "break", "intro") or sections[k - 1]["energy"] < s["energy"] - 0.08)]
    builds = [[s["start"], s["end"]] for s in sections if s["label"] == "build"]

    # --- tempo curve (local tempo every ~4 s)
    oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
    lt = librosa.feature.tempo(onset_envelope=oenv, sr=sr, hop_length=512, aggregate=None, start_bpm=tempo)
    lt_t = librosa.times_like(lt, sr=sr, hop_length=512)
    step = max(1, int(4.0 / (512 / sr)))
    tempo_curve = [{"t": round(float(lt_t[i]), 2), "bpm": round(float(lt[i]), 1)} for i in range(0, len(lt), step)]
    changes = [tc for tc in tempo_curve if abs(tc["bpm"] - tempo) / tempo > 0.06 and abs(tc["bpm"] * 2 - tempo) / tempo > 0.06
               and abs(tc["bpm"] / 2 - tempo) / tempo > 0.06]

    # --- accents: strongest hits overall, but at most ~1 per bar, preferring downbeats of drops
    pool = sorted(kicks + snares, key=lambda h: -h["s"])
    accents, used_bars = [], set()
    for h in pool:
        bi = int(np.searchsorted(downbeats, h["t"], side="right")) - 1
        if bi in used_bars:
            continue
        used_bars.add(bi)
        accents.append(h["t"])
        if len(accents) >= max(4, len(bars) // 2):
            break
    phrases = [round(float(downbeats[i]), 4) for i in range(0, len(downbeats), 4)]

    res = {"source": path, "duration": round(D, 3), "tempo_bpm": round(tempo, 2), "tempo_curve": tempo_curve,
           "tempo_changes": changes, "beats": [round(float(b), 4) for b in beats],
           "downbeats": [round(float(b), 4) for b in downbeats], "phrases_4bar": phrases,
           "bars": bars, "kicks": kicks, "snares": snares, "hats": hats,
           "energy_10hz": [round(float(energy[i]), 3) for i in range(0, len(energy), max(1, int(0.1 / (HOP / SR))))],
           "sections": sections, "drops": [round(d, 4) for d in drops], "builds": builds,
           "accents": sorted(round(a, 4) for a in accents),
           "assumptions": ["4/4 meter", "downbeat phase from kick/low-end accent + harmonic change"]}
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "music_structure.json").write_text(json.dumps(res, indent=1))
        timeline_png(res, out_dir / "music_structure.png")
    log(f"   {tempo:.1f} BPM, {len(res['downbeats'])} bars, sections "
        + " | ".join(f"{s['label']}@{s['start']:.1f}s" for s in sections) + f", drops {res['drops']}")
    return res


def timeline_png(m: dict, out: Path, width: int = 1400) -> Path:
    """Visual timeline: energy curve, sections, downbeats, kicks/snares, drops (for human/Claude review)."""
    from PIL import Image, ImageDraw
    H = 260
    im = Image.new("RGB", (width, H), (18, 18, 24))
    d = ImageDraw.Draw(im)
    D = m["duration"]
    X = lambda t: int(t / D * (width - 1))  # noqa: E731
    cols = {"intro": (60, 90, 140), "verse": (70, 120, 90), "build": (180, 140, 40), "drop": (200, 60, 60),
            "break": (90, 70, 140), "outro": (80, 80, 80)}
    for s in m["sections"]:
        d.rectangle([X(s["start"]), 0, X(s["end"]), 26], fill=cols.get(s["label"], (90, 90, 90)))
        d.text((X(s["start"]) + 4, 7), s["label"], fill=(255, 255, 255))
    e = m["energy_10hz"]
    pts = [(int(i / max(1, len(e) - 1) * (width - 1)), int(200 - v * 150)) for i, v in enumerate(e)]
    d.line(pts, fill=(120, 220, 255), width=2)
    for b in m["downbeats"]:
        d.line([X(b), 30, X(b), 205], fill=(70, 70, 80))
    for k in m["kicks"]:
        d.line([X(k["t"]), 215, X(k["t"]), 215 + int(18 * k["s"])], fill=(255, 120, 60))
    for s in m["snares"]:
        d.line([X(s["t"]), 238, X(s["t"]), 238 + int(18 * s["s"])], fill=(240, 240, 120))
    for t in m["drops"]:
        d.line([X(t), 0, X(t), H], fill=(255, 40, 40), width=3)
    d.text((4, 212), "kick", fill=(255, 120, 60)); d.text((4, 236), "snare", fill=(240, 240, 120))
    im.save(out)
    return out
