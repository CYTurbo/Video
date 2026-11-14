# WORKFLOW — creating edits with natural language

## 0. Where things go

```
AI-Video-Studio/
  media/raw/          your video clips          (read-only to the pipeline)
  media/images/       photos, logos, stills     (read-only)
  media/audio/        music, voice-overs, SFX   (read-only)
  media/reference/    reference videos to imitate (read-only)
  projects/<name>/    plan.json, LUTs, analysis for each edit
  renders/intermediate/<name>/   segments, overlays, audio mix (safe to delete)
  exports/            finished videos + .qc.json + .contact.png
  logs/studio.log     every command that was run
  presets/            reusable styles (JSON)
  remotion/src/       motion-graphics templates (React)
  blender/scripts/    3D templates (Python)
```

Commands below use `studio` = `.\studio.cmd` on Windows, `./studio.sh` on Linux/macOS.

## 1. The easiest way: ask Claude Code

Open a terminal in `AI-Video-Studio`, run `claude`, and talk to it normally:

> Take `media/raw/beach.mp4` and `media/raw/city.mp4`, create a cinematic edit with smooth transitions,
> dynamic typography saying "SUMMER 26", and professional color grading. Export it as an Instagram reel.

Claude reads `CLAUDE.md`, inspects the media, writes `projects/<name>/plan.json`, renders, runs QC,
looks at the contact sheet and iterates. You get the path of the finished MP4 plus the QC summary.

> Analyze `media/reference/ad.mp4` and recreate its editing style using my footage in `media/raw`.

> Create a 20-second animated typography sequence with dramatic camera movement, synchronized to
> `media/audio/track.mp3`. Lines: "DREAM BIG", "WORK HARD", "STAY HUMBLE".

## 2. The same thing from the CLI (no Claude needed)

```bash
# cinematic reel (planner reads the sentence: format, duration, preset, transitions, effects, titles)
studio make "Create a 15-second cinematic Instagram reel with smooth transitions, light leaks, grain and the title \"SUMMER 26\"" --media media/raw/beach.mp4 media/raw/city.mp4 --music media/audio/song.mp3

# preview the plan without rendering (then edit projects/<name>/plan.json and `studio render` it)
studio make "..." --media ... --dry-run
studio render projects/<name>/plan.json

# beat-synced hype edit
studio make "energetic glitch edit synced to the beat, flashes on beats, vertical" --media media/raw/*.mp4 --music media/audio/edm.mp3

# reference-style recreation
studio reference analyze media/reference/ad.mp4          # style report + keyframes in projects/
studio reference recreate media/reference/ad.mp4 --media media/raw/a.mp4 media/raw/b.mp4 --music media/audio/song.mp3
studio reference compare media/reference/ad.mp4 exports/recreate_ad.mp4

# motion typography (Remotion), beat-pulsed if music given
studio typography "DREAM BIG|WORK HARD|STAY HUMBLE" --duration 20 --music media/audio/track.mp3 --camera dramatic

# 3D title (Blender)
studio title3d "LAUNCH DAY" --format 16:9 --duration 4

# subtitles (local Whisper) burned in with word highlighting
studio captions media/raw/interview.mp4 --style bold_pop       # or --srt my.srt

# utilities
studio inspect                       # resolution / fps / duration / audio of everything in media/
studio beats media/audio/song.mp3    # tempo + beat times -> projects/beats_song.json
studio audio-clean media/audio/voice.wav --lufs -16
studio reformat media/raw/wide.mp4 --format 9:16 --fit blur     # horizontal -> vertical with blurred fill
studio qc exports/my_reel.mp4 --width 1080 --height 1920 --fps 30 --duration 15
studio presets
studio doctor
```

### Words the planner understands
| You say | It does |
|---|---|
| reel, shorts, tiktok, vertical, 9:16 / youtube, horizontal, 16:9 / square / 4:5 / 4k | output format |
| "15-second", "1 minute" | duration |
| cinematic, moody, retro/vintage, vlog/bright, black and white, neon/cyberpunk, clean/corporate, glitch/hype | preset |
| smooth / zoom / whip / glitch / flash / dissolve / slide transitions, hard cuts, dip to black | transition |
| grain, light leaks, glitch, RGB split, shake/handheld, motion blur, vignette, letterbox | effects |
| slow motion, speed ramp | fast-slow-fast ramp on alternate clips |
| zoom, ken burns, push in | per-clip zoom in/out |
| synced to the beat / music, "every 2 beats", flashes on beats, punch on beats | beat sync |
| keep original audio, voice cleanup / denoise | audio handling |
| subtitles / captions (boxed / clean) | Whisper captions |
| "quoted text", typography, titles, lower thirds, typewriter | animated titles (Remotion) |
| 3D title / 3D intro | Blender intro clip |
| logo | Remotion logo sting outro |
| reference, recreate, same style | reference job |

## 3. Plan JSON reference

| key | meaning |
|---|---|
| `job` | `edit` (default) · `typography` · `reference` |
| `preset` | name in `presets/` – merged first, your keys override |
| `width`,`height`,`fps`,`duration` | output format (seconds) |
| `clips[]` | `src`, `in` (start s), `speed` (1=normal, 2=2x), `ramp` (0–0.85 fast-slow-fast), `zoom` (`in`/`out`), `zoom_amount`, `shake` (px), `focus_x` (0–1 crop centre), `smooth_slowmo` |
| `cut_mode` | `even` (equal shots) · `beats` (cuts on prominent beats, `beat_every` s) · `explicit` (`cuts` list) |
| `segments` | number of shots for `even` (defaults to number of clips; clips are cycled) |
| `transition` | `{type, duration}` or a list (one per cut). Types: fade, dissolve, smoothleft/right/up/down, zoomin, slideleft…, wipeleft…, circleopen, radial, hblur (whip), pixelize, fadeblack, fadewhite (flash), cut, glitch |
| `grade` | none, neutral, cinematic, teal_orange, warm_film, moody, bright_vlog, bw_contrast, retro, neon, or a `.cube` LUT path |
| `effects` | `grain` (0–40), `vignette`, `motion_blur` (2–5 frames), `light_leaks` (true / "cuts"), `light_leak_opacity`, `glitch_on_cuts`, `rgb_split` (px), `flash_on_beats`, `punch_on_beats`, `letterbox` (16:9 only), `shake`, `sharpen` |
| `titles[]` | `text`, `start`, `duration`, `position` (top/center/bottom), `style` |
| `title_style` | kinetic · bigpop · lowerthird · typewriter · glitch |
| `title_renderer` | auto (Remotion, falls back to FFmpeg drawtext) · remotion · ffmpeg |
| `captions` | `{auto:true, model:"small", language:"en", style:"bold_pop|clean|boxed|neon", max_words:3}` or `{srt:"file.srt"}` |
| `audio` | `music`, `music_volume`, `keep_original`, `original_volume`, `voice_cleanup`, `normalize` (LUFS, null=off), `fade_in`, `fade_out` |
| `intro_3d` | `{text, duration, samples}` – Blender 3D title prepended |
| `outro_logo` | `{text, tagline, duration}` – Remotion logo sting appended |
| `export` | `crf` (quality, 18 default), `preset` (x264 speed), `filename` |

## 4. What happens during a render
1. Sources probed (resolution, fps, duration, audio) and logged.
2. Music analysed (tempo, beats, prominent beats) if needed.
3. Cut times computed (even / beats / explicit), snapped to the frame grid; transition lengths clamped so they never overlap.
4. Each shot rendered: trim → speed/ramp → fps → cover-crop to format → zoom/shake.
5. Shots joined with `xfade` transitions; assembled length asserted.
6. Audio mixed (music + optional original audio with fades), then two-pass loudness normalisation (-14 LUFS default).
7. Finishing pass: motion blur → grade/LUT → sharpen → RGB split → glitch on cuts → beat flashes/punch → grain → vignette → letterbox → light leaks → titles (Remotion alpha overlay) → captions (libass).
8. Encode H.264 High / yuv420p / AAC 48 kHz / +faststart (plays everywhere, social-ready).
9. **QC**: re-probe specs, decode every frame, black/frozen/silence detection, loudness, exposure, sampled-frame sanity, contact sheet. Mechanical issues are auto-fixed into `*_fixed.mp4`; content issues fail loudly.

## 5. Reference-based workflow
1. Put the reference in `media/reference/`.
2. `studio reference analyze <ref>` → `projects/reference_<name>/style_report.md`, `style_profile.json`, keyframes, contact sheet.
3. `studio reference recreate <ref> --media <your clips> [--music song]` → copies the shot rhythm (scaled to the target duration), maps transitions, builds a colour-matching 3D LUT (`match_reference.cube`), adds grain/shake/zoom/letterbox if detected, renders, then compares.
4. Read the comparison table (`exports/<name>.comparison.json`, side-by-side `*.vs_reference.png`). "close" means within a stated tolerance — it is not a claim of a perfect match. The limitations list in the style report says what could not be reproduced.

## 6. First video in 5 minutes
1. Copy 2–5 clips into `media/raw/` and a song into `media/audio/`.
2. `studio inspect`
3. `studio make "15 second cinematic Instagram reel synced to the music with the title \"MY FIRST EDIT\"" --media media/raw/* --music media/audio/<song>`
4. Open `exports/<name>.mp4` and `exports/<name>.contact.png`.
5. Tweak `projects/<name>/plan.json` (in-points, title text, grade) → `studio render projects/<name>/plan.json`.

## 7. Ranking / countdown videos ("Top 5 ...")
1. Put each entry's BEFORE and AFTER photo in `media/images/` (only photos you have permission to use).
2. Copy `templates/ranking_spec.example.json` to `projects/my_ranking.json`, fill in ranks, names, captions, file
   names and your music track (one you have rights to). You decide the order.
3. `studio ranking projects/my_ranking.json`
   - entries play #5 → #1; each: rank slam → BEFORE (slow push-in) → flash + wipe to AFTER on a strong beat → caption
   - the song is started at the right downbeat so its **drop hits the #1 reveal** (when the track has a drop)
   - output `exports/<name>.mp4` (1080×1920 by default), QC + contact sheet
