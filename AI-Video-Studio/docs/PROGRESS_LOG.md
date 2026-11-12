# PROGRESS_LOG

Chronological build log (build session 2026-11-12). Command-level detail is in `logs/studio.log` during runs.

## Phase 1 — investigation
- Session turned out to run in a **Linux cloud container** (Ubuntu 24.04, 4 threads, 15 GB RAM, no GPU), not on the
  user's Windows PC. No Remote Control folder was shared, so the Windows machine could not be inspected or modified.
- Decision: build + verify everything here, ship `windows/inspect_system.ps1` (read-only) and `windows/setup.ps1`
  (winget, per-package confirmation) for the PC.
- Present: Python 3.13.18, Node 22.23.4, npm 10.9.9, Git 2.43, FFmpeg 6.1.1 (all needed filters + libx264/libass).
- Network policy: PyPI/npm reachable; blender.org, huggingface.co, Chrome-for-Testing storage blocked.

## Phase 2 — tools
- Python venv `.venv`: numpy, opencv-python-headless, pillow, librosa, soundfile, scenedetect, faster-whisper.
- Blender: official `bpy` 5.3.0 wheel (Blender Foundation, PyPI) in `.venv-blender` because blender.org was blocked.
  Cycles CPU verified; EEVEE/Workbench need OpenGL (not available headless here).
- Remotion 4.0.543 project (`remotion/`), using the preinstalled Chromium headless shell.
- Kdenlive/Audacity intentionally not installed (no benefit for the automated pipeline; optional in setup.ps1).

## Phase 3 — integrations (details in SETUP_REPORT.md)
- Remotion official Claude Code plugin: verified (official org, MIT, skills only) → recommended; enabling it requires
  editing Claude Code settings, which the agent's auto-mode correctly refused → provided as
  `templates/claude-settings.example.json` + `/plugin` commands for the user.
- blender-mcp: source audited (arbitrary `exec` over local socket, opt-in screenshot telemetry, paid-API hooks) → not
  installed; direct `blender --background --python` is used instead.
- FFmpeg / filesystem / inspection MCPs: redundant with direct CLI + Claude Code tools → not installed.

## Phases 4–6 — pipeline
- `studio/` package: config, media probe, effects library, audio analysis, render engine, QC + auto-fix, planner (NL →
  plan), jobs (tool selection), Remotion & Blender bridges, subtitles, reference analysis/LUT matching/comparison,
  doctor, CLI. 9 presets. 3 Remotion compositions. 1 Blender scene script.

## Phase 7 — testing: real bugs found by the tests (and fixed)
1. **Frozen video in beat-synced edits** — xfade chain ended early because cut times weren't frame-aligned
   (segment ran out a fraction of a frame before its transition finished). QC had only *warned*.
   Fix: frame-snapped cuts and transition lengths, 2-frame segment padding, assembled-length assertion, QC now fails
   on long freezes.
2. **Beat detection locked on the wrong tempo (80.7 vs 120 BPM)** — hi-hat off-beats dominated the full-band onset
   envelope. Fix: combined full-band + kick-band envelope; tempo from least-squares beat period. Now 120.0 BPM,
   98 % recall/precision vs ground truth.
3. **Glitch hits 120 ms before the beat** — glitch window started before the cut. Fix: starts on the cut frame.
4. **Typography loudness −16.1 instead of −14 LUFS** — loudness measured on the full song, applied to a trimmed
   excerpt (QC auto-fixed it, root cause fixed: trim first, then measure).
5. **"professional color grading" chose the corporate preset** — ambiguous keyword removed; explicit "cinematic" wins.
6. **Reference analysis: false dissolves / missed cuts on fast-moving footage** — fix: cut threshold relative to the
   quieter side of the boundary, dissolves must pass a linear-blend test.
7. **Grain estimate blind** — measured on downscaled frames (grain averaged away). Fix: full-resolution crop.
8. **Colour match short of target** — fix: full mean transfer + closed-loop correction LUT after measuring the render.
9. **Grain nearly invisible after a LUT** — `lut3d` outputs RGB planes, so luma grain hit only the green channel.
   Fix: convert back to YUV right after grading.
10. Added exposure (clipped highlights / crushed shadows) warnings to QC after visually spotting a blown-out shot.

## Phases 8–10
- CLI (`studio.cmd` / `studio.sh`), Claude Code instruction file (`CLAUDE.md`), docs, final full test run
  (TEST_RESULTS.md), `studio doctor` verification.
11. **Long typography lines ran off-frame (Test B)** — passed all metrics but was visibly clipped on the contact sheet.
    Fix: width-based font sizing in KineticTypography/TitleOverlay, gentler camera sway, plus a new automated
    "text stays inside frame" check (it scores 0.19 on the defective render, 0.000 after the fix).
