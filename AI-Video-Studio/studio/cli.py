"""AI-Video-Studio command line.

  python studio.py doctor                         check every tool / integration
  python studio.py inspect [files...]             resolution, fps, duration, audio tracks
  python studio.py make "instruction" [--media f ...] [--music m] [--title T] [--preset P] [--dry-run]
  python studio.py render plan.json               render a (hand-written or Claude-written) plan
  python studio.py reference analyze REF
  python studio.py reference recreate REF --media f ... [--music m]
  python studio.py reference compare REF OUTPUT
  python studio.py typography "LINE ONE|LINE TWO" [--duration 20] [--music m] [--format 16:9]
  python studio.py title3d "TEXT" [--format 16:9] [--duration 4]
  python studio.py beats music.wav
  python studio.py captions video.mp4 [--style bold_pop] [--srt file.srt]
  python studio.py audio-clean in.wav             voice cleanup + loudness normalisation (new file)
  python studio.py reformat video.mp4 --format 9:16 [--fit blur|crop]
  python studio.py qc video.mp4 [--width W --height H --fps F --duration D]
  python studio.py presets
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config
from .log import log

FMT = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350), "4k": (3840, 2160)}


def _fmt(s: str | None, default=(1080, 1920)):
    return FMT.get(s, default) if s else default


def cmd_doctor(a) -> int:
    from . import doctor
    return doctor.run_doctor()


def cmd_inspect(a) -> int:
    from .media import describe, list_media, probe
    files = a.files or [str(p) for p in list_media(config.MEDIA)]
    if not files:
        print("No media found. Put files into media/raw, media/images, media/audio or media/reference.")
    rows = []
    for f in files:
        from .media import IMAGE_EXT
        if Path(f).suffix.lower() in IMAGE_EXT:
            from PIL import Image
            with Image.open(f) as im:
                print(f"{Path(f).name} | image {im.size[0]}x{im.size[1]} {im.mode}")
            continue
        info = probe(f)
        rows.append(info)
        print(describe(info))
    if a.json:
        print(json.dumps(rows, indent=2))
    return 0


def cmd_make(a) -> int:
    from . import jobs, planner
    plan = planner.plan_from_text(a.instruction, a.media, a.music, a.name, a.title, a.preset)
    if a.reference:
        plan["job"] = "reference"
        plan["reference"] = a.reference
    if a.format:
        plan["width"], plan["height"] = _fmt(a.format)
        if plan["job"] == "reference":
            plan["width_override"], plan["height_override"] = plan["width"], plan["height"]
    if a.duration:
        plan["duration"] = a.duration
        plan["duration_override"] = a.duration
    proj = config.PROJECTS / plan["name"]
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "plan.json").write_text(json.dumps(plan, indent=2))
    log(f"Plan written to {proj / 'plan.json'}  (job={plan['job']}, preset={plan.get('preset')}, "
        f"{plan['width']}x{plan['height']}, {plan['duration']}s, {len(plan['clips'])} clip(s), music={bool(plan['audio'].get('music'))})")
    if plan.get("_note"):
        log("NOTE: " + plan["_note"])
    if a.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    if plan["job"] != "typography" and not plan["clips"]:
        print("No footage found: pass --media or put clips in media/raw / media/images.")
        return 2
    res = jobs.execute(plan)
    return _report(res)


def _report(res: dict) -> int:
    qc = res.get("qc", {})
    print(f"\nOUTPUT: {res['output']}")
    if qc:
        from .qc import summarize
        print(summarize(qc))
        if qc.get("contact_sheet"):
            print(f"Contact sheet: {qc['contact_sheet']}")
    if res.get("comparison"):
        print(res["comparison"]["table_md"])
        print(res["comparison"]["note"])
    return 0 if qc.get("passed", True) else 1


def cmd_render(a) -> int:
    from . import jobs
    plan = json.loads(Path(a.plan).read_text())
    return _report(jobs.execute(plan))


def cmd_reference(a) -> int:
    from . import jobs
    from . import reference as R
    if a.action == "analyze":
        p = R.analyze(a.ref)
        print(R.report_md(p))
        return 0
    if a.action == "compare":
        r = R.compare(a.ref, a.output)
        print(r["table_md"]); print(r["note"])
        return 0
    plan = {"job": "reference", "reference": a.ref, "name": a.name or f"recreate_{Path(a.ref).stem}",
            "clips": [{"src": m} for m in a.media], "audio": {"music": a.music}}
    if a.format:
        plan["width_override"], plan["height_override"] = _fmt(a.format)
    if a.duration:
        plan["duration_override"] = a.duration
    return _report(jobs.execute(plan))


def cmd_typography(a) -> int:
    from . import jobs
    W, H = _fmt(a.format, (1920, 1080))
    plan = {"job": "typography", "name": a.name or "typography", "width": W, "height": H, "fps": 30,
            "duration": a.duration, "lines": [s.strip() for s in a.lines.split("|") if s.strip()],
            "camera": a.camera, "audio": {"music": a.music}}
    return _report(jobs.execute(plan))


def cmd_title3d(a) -> int:
    from . import blender_bridge, qc
    W, H = _fmt(a.format, (1920, 1080))
    out = config.EXPORTS / f"title3d_{''.join(ch for ch in a.text if ch.isalnum())[:20] or 'title'}.mp4"
    blender_bridge.render_title3d(a.text, out, W, H, 30, a.duration, samples=a.samples)
    rep = qc.check(out, {"width": W, "height": H, "fps": 30, "duration": a.duration})
    print(qc.summarize(rep))
    return 0 if rep["passed"] else 1


def cmd_beats(a) -> int:
    from .audio import analyze_beats
    b = analyze_beats(a.audio)
    print(f"tempo {b['tempo_bpm']:.1f} BPM, {len(b['beats'])} beats, {len(b['prominent_beats'])} prominent")
    print("first beats:", b["beats"][:16])
    out = config.PROJECTS / f"beats_{Path(a.audio).stem}.json"
    out.write_text(json.dumps(b, indent=1))
    print(f"saved {out}")
    return 0


def cmd_captions(a) -> int:
    from . import qc, subtitles
    from .media import probe, run
    info = probe(a.video)
    W, H = info["video"]["width"], info["video"]["height"]
    work = config.INTERMEDIATE / f"captions_{Path(a.video).stem}"
    work.mkdir(parents=True, exist_ok=True)
    cap = {"srt": a.srt} if a.srt else {"auto": True, "model": a.model, "language": a.language, "source": a.video}
    cap["style"] = a.style
    ass = subtitles.prepare_ass(cap, {"width": W, "height": H, "clips": [{"src": a.video}]}, work)
    out = config.EXPORTS / f"{Path(a.video).stem}_captioned.mp4"
    run([config.ffmpeg(), "-y", "-v", "error", "-i", a.video, "-vf", f"subtitles=filename='{config.ff_filter_path(ass)}'",
         "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "copy", str(out)])
    if (work / "captions.srt").exists():
        print(f"SRT: {work / 'captions.srt'}")
    rep = qc.check(out, {"width": W, "height": H, "duration": info["duration"], "duration_tol": 0.2})
    print(qc.summarize(rep))
    return 0


def cmd_audio_clean(a) -> int:
    from . import audio as A
    from .media import run
    out = config.EXPORTS / f"{Path(a.input).stem}_clean.wav"
    tmp = config.INTERMEDIATE / f"_clean_{Path(a.input).stem}.wav"
    run([config.ffmpeg(), "-y", "-v", "error", "-i", a.input, "-vn", "-af", A.voice_cleanup_filter(a.strength), str(tmp)])
    run([config.ffmpeg(), "-y", "-v", "error", "-i", str(tmp), "-af", A.loudnorm_filter(tmp, target=a.lufs), "-ar", "48000", str(out)])
    print(f"before: {A.loudness(a.input).get('lufs')} LUFS  after: {A.loudness(out).get('lufs')} LUFS -> {out}")
    return 0


def cmd_reformat(a) -> int:
    from . import qc
    from .media import probe, run
    W, H = _fmt(a.format)
    out = config.EXPORTS / f"{Path(a.video).stem}_{a.format.replace(':', 'x')}.mp4"
    if a.fit == "blur":
        vf = (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=30,eq=brightness=-0.08[bg];"
              f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p")
    else:
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,format=yuv420p"
    info = probe(a.video)
    run([config.ffmpeg(), "-y", "-v", "error", "-i", a.video, "-vf", vf, "-c:v", "libx264", "-crf", "18", "-preset", "medium",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    rep = qc.check(out, {"width": W, "height": H, "duration": info["duration"], "duration_tol": 0.2})
    print(qc.summarize(rep))
    return 0


def cmd_qc(a) -> int:
    from . import qc
    exp = {k: v for k, v in dict(width=a.width, height=a.height, fps=a.fps, duration=a.duration).items() if v}
    rep = qc.check(a.video, exp)
    print(qc.summarize(rep))
    print(f"contact sheet: {rep.get('contact_sheet')}")
    return 0 if rep["passed"] else 1


def cmd_presets(a) -> int:
    for p in sorted(config.PRESETS.glob("*.json")):
        d = json.loads(p.read_text())
        print(f"{p.stem:20s} {d.get('description', '')}")
    from .fx import GRADES
    print("\ngrades:", ", ".join(GRADES))
    return 0


def main(argv=None) -> int:
    config.ensure_dirs()
    ap = argparse.ArgumentParser(prog="studio", description="AI-Video-Studio: natural-language video editing")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("doctor").set_defaults(f=cmd_doctor)
    s = sp.add_parser("inspect"); s.add_argument("files", nargs="*"); s.add_argument("--json", action="store_true"); s.set_defaults(f=cmd_inspect)
    s = sp.add_parser("make"); s.add_argument("instruction"); s.add_argument("--media", nargs="*", default=[])
    s.add_argument("--music"); s.add_argument("--title", action="append"); s.add_argument("--preset"); s.add_argument("--name")
    s.add_argument("--format", choices=list(FMT)); s.add_argument("--duration", type=float); s.add_argument("--reference")
    s.add_argument("--dry-run", action="store_true"); s.set_defaults(f=cmd_make)
    s = sp.add_parser("render"); s.add_argument("plan"); s.set_defaults(f=cmd_render)
    s = sp.add_parser("reference"); s.add_argument("action", choices=["analyze", "recreate", "compare"]); s.add_argument("ref")
    s.add_argument("output", nargs="?"); s.add_argument("--media", nargs="*", default=[]); s.add_argument("--music")
    s.add_argument("--name"); s.add_argument("--format", choices=list(FMT)); s.add_argument("--duration", type=float); s.set_defaults(f=cmd_reference)
    s = sp.add_parser("typography"); s.add_argument("lines"); s.add_argument("--duration", type=float, default=20)
    s.add_argument("--music"); s.add_argument("--format", choices=list(FMT)); s.add_argument("--camera", default="dramatic",
                                                                                         choices=["dramatic", "subtle", "none"])
    s.add_argument("--name"); s.set_defaults(f=cmd_typography)
    s = sp.add_parser("title3d"); s.add_argument("text"); s.add_argument("--format", choices=list(FMT))
    s.add_argument("--duration", type=float, default=4); s.add_argument("--samples", type=int, default=16); s.set_defaults(f=cmd_title3d)
    s = sp.add_parser("beats"); s.add_argument("audio"); s.set_defaults(f=cmd_beats)
    s = sp.add_parser("captions"); s.add_argument("video"); s.add_argument("--style", default="bold_pop")
    s.add_argument("--srt"); s.add_argument("--model", default="small"); s.add_argument("--language"); s.set_defaults(f=cmd_captions)
    s = sp.add_parser("audio-clean"); s.add_argument("input"); s.add_argument("--strength", default="medium")
    s.add_argument("--lufs", type=float, default=-16.0); s.set_defaults(f=cmd_audio_clean)
    s = sp.add_parser("reformat"); s.add_argument("video"); s.add_argument("--format", default="9:16", choices=list(FMT))
    s.add_argument("--fit", default="blur", choices=["blur", "crop"]); s.set_defaults(f=cmd_reformat)
    s = sp.add_parser("qc"); s.add_argument("video"); s.add_argument("--width", type=int); s.add_argument("--height", type=int)
    s.add_argument("--fps", type=float); s.add_argument("--duration", type=float); s.set_defaults(f=cmd_qc)
    sp.add_parser("presets").set_defaults(f=cmd_presets)
    a = ap.parse_args(argv)
    try:
        return a.f(a)
    except KeyboardInterrupt:
        return 130
    except Exception as e:  # noqa: BLE001
        log(f"ERROR: {e}")
        log("See logs/studio.log for the full command log and docs/TROUBLESHOOTING.md for fixes.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
