# AI-Video-Studio — operating instructions for Claude Code

You are operating a local, free/open-source video editing & motion-graphics workstation.
The user gives natural-language edit requests plus media; you produce finished, QC-verified videos.

## Golden rules
1. **Never modify, move, overwrite or delete anything in `media/`** (the user's originals). Read only.
   The pipeline refuses to write there (`config.assert_writable_output`). Outputs go to `exports/`,
   scratch to `renders/intermediate/<project>/`, plans to `projects/<project>/`.
2. **Free tools only.** No paid APIs, trials, stock sites or cloud renderers. Everything here runs locally.
3. **Never claim success without QC.** Every render is re-probed and inspected by `studio/qc.py`
   (specs, decode errors, black/frozen/blank frames, loudness, A/V length). Look at the generated
   `*.contact.png` with the Read tool before telling the user it looks right.
4. Ask before: admin-level installs, downloads > ~500 MB, deleting anything, or broad filesystem access.

## Tools (auto-selected by the pipeline)
| Need | Tool | Where |
|---|---|---|
| cutting, transitions, grading, effects, audio, encode | FFmpeg | `studio/render.py`, `studio/fx.py` |
| animated titles, kinetic typography, logo stings | Remotion (React) | `remotion/src/*.tsx`, `studio/remotion_bridge.py` |
| 3D titles, camera moves, lighting, compositing | Blender (headless) | `blender/scripts/*.py`, `studio/blender_bridge.py` |
| beats, loudness, voice cleanup | librosa + FFmpeg | `studio/audio.py` |
| scene cuts, style analysis, LUT matching | PySceneDetect + OpenCV | `studio/reference.py` |
| subtitles | faster-whisper (local) + libass | `studio/subtitles.py` |

Run everything through the venv: Windows `.\studio.cmd <cmd>` (or `.venv\Scripts\python.exe studio.py <cmd>`),
Linux/macOS `./studio.sh <cmd>`.

## Standard workflow for a request
1. `studio inspect` (or `inspect <files>`) — learn resolutions, fps, durations, audio tracks.
2. Translate the request into a plan. Fast path: `studio make "<request>" --media ... --music ... --dry-run`
   prints the planner's JSON (`projects/<name>/plan.json`). **Refine it yourself**: set exact `in` points
   for the best moments (look at frames via `studio qc <clip>` contact sheets), titles text, durations.
3. Render: `studio render projects/<name>/plan.json` (or `make` without `--dry-run`).
4. Read the QC summary + contact sheet. If something is off (wrong crop, title overlaps a face, weak grade),
   edit the plan and re-render. Mechanical problems (size/fps/duration/loudness) are auto-fixed.
5. Report: output path, specs, QC result, what was approximated.

## Plan JSON (key fields — full reference in docs/WORKFLOW.md)
```json
{"name":"my_reel","preset":"cinematic","width":1080,"height":1920,"fps":30,"duration":15,
 "clips":[{"src":"media/raw/a.mp4","in":12.5,"speed":1.0,"ramp":0.6,"zoom":"in","shake":0,"focus_x":0.5}],
 "cut_mode":"even|beats|explicit","cuts":[],"beat_every":1.5,
 "transition":{"type":"smoothleft","duration":0.45},
 "grade":"cinematic | <name> | path/to/look.cube",
 "effects":{"grain":8,"vignette":true,"motion_blur":3,"light_leaks":"cuts","glitch_on_cuts":false,
            "rgb_split":0,"flash_on_beats":false,"punch_on_beats":false,"letterbox":false,"shake":0,"sharpen":0},
 "titles":[{"text":"Golden Hour","start":0.4,"duration":2.6,"position":"center","style":"kinetic"}],
 "title_style":"kinetic|bigpop|lowerthird|typewriter|glitch",
 "captions":{"auto":true,"style":"bold_pop","model":"small"},
 "audio":{"music":"media/audio/song.mp3","keep_original":false,"original_volume":0.35,"normalize":-14,
          "fade_in":0.3,"fade_out":1.2,"voice_cleanup":false},
 "intro_3d":{"text":"TITLE","duration":3}, "outro_logo":{"text":"BRAND","tagline":"","duration":2.5}}
```
Jobs: `"job":"edit"` (default), `"typography"` (Remotion only: `lines`, `camera`), `"reference"` (`reference` path).

## Commands
`doctor` · `inspect` · `make` · `render` · `reference analyze|recreate|compare` · `typography` · `title3d` ·
`beats` · `captions` · `audio-clean` · `reformat` · `qc` · `presets` — see `python studio.py -h`.

## Extending
- New look: add to `GRADES` in `studio/fx.py` or drop a `.cube` LUT in `templates/` and use its path as `grade`.
- New preset: JSON in `presets/` (any plan keys + `description`).
- New Remotion template: add a component in `remotion/src/`, register in `Root.tsx` (props must include
  width/height/fps/durationSec), add a wrapper in `remotion_bridge.py`. Preview with `npm run studio` in `remotion/`.
  The official Remotion plugin (skills: `/remotion-best-practices`) can be enabled via `templates/claude-settings.example.json`
  (user copies it to `.claude/settings.json`) or in Claude Code: `/plugin marketplace add remotion-dev/claude-code-plugin`, `/plugin install remotion@remotion`.
- New Blender scene: script in `blender/scripts/` reading JSON args after `--`, call via `blender_bridge.run_script`.
- After changing pipeline code run `python tests/run_tests.py` (or a subset, e.g. `A C`) — it rewrites docs/TEST_RESULTS.md.

## Known limits (be honest with the user)
- Motion blur = frame blending (tmix), not true optical-flow shutter blur. `smooth_slowmo: true` on a clip uses
  FFmpeg minterpolate (slow, can warp).
- Reference matching copies pacing, transition types, colour statistics (LUT), grain, shake/zoom tendencies,
  letterbox. It does not OCR text, identify fonts, or reproduce bespoke VFX. Comparison is metric-based.
- Reference transition detection: cut / dissolve / dip-to-black / flash only; slides & wipes read as cuts.
- Text "tracking" to moving objects is not automated (no free robust tracker wired in); titles are screen-anchored.
- Whisper models download once from Hugging Face (free); without internet, use `--srt` captions.
- Blender on CPU (Cycles) is slow; with a GPU set `BLENDER_ENGINE=BLENDER_EEVEE` for fast renders.
