# TROUBLESHOOTING

Every command the pipeline runs is in `logs/studio.log` (with the full FFmpeg/Remotion/Blender error text).
Start with `studio doctor`.

## Installation (Windows)
| Symptom | Fix |
|---|---|
| `running scripts is disabled on this system` | Run with `powershell -ExecutionPolicy Bypass -File .\windows\setup.ps1` (affects only that one run; nothing is changed permanently). |
| `winget` not found | Install/update **App Installer** from the Microsoft Store (free). |
| winget installed FFmpeg/Node but the command is not found | Close and reopen the terminal (PATH refresh). FFmpeg from Gyan.FFmpeg lives under `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\...\bin`; or set `FFMPEG` / `FFPROBE` env vars to the exe paths. |
| UAC prompt during Blender/Git install | That installer needs admin. Approve to install, or decline to skip it (you can install Blender later; the pipeline falls back to the `bpy` module if `.venv-blender` exists). |
| `pip install` fails building a wheel | Make sure the venv uses Python 3.11–3.13 x64 (`py -3.13 -m venv .venv`). All required packages ship Windows wheels. |
| `npm ci` fails | Delete `remotion\node_modules` and run `npm install` in `remotion\`. Requires Node 18+ (LTS recommended). |

## Rendering
| Symptom | Cause / fix |
|---|---|
| `Unknown grade` / `Unknown transition` | Typo — see `studio presets` and the tables in WORKFLOW.md. |
| `assembly produced Xs, expected Ys` | Transition timing problem (should not happen since frame-snapping). Report the plan; workaround: use `"transition":{"type":"cut"}` or fewer, longer shots. |
| Output has frozen video for seconds | QC flags it as a problem. Usually a source clip shorter than the requested shot (it loops) or a corrupt source. Check `studio inspect`, set `in` points, or remux the source: `ffmpeg -i in.mp4 -c copy fixed.mp4`. |
| Vertical output crops off the subject | Set `focus_x` on that clip (0 = left, 1 = right), or use `studio reformat --fit blur`. |
| Overexposed warning | Use a gentler grade (`neutral`, `moody`), or a LUT. |
| Remotion: `Could not find a browser` / download blocked | Remotion downloads Chrome Headless Shell on first render (free). Behind a firewall, point it at an installed Chrome/Edge/Chromium: set env `REMOTION_BROWSER=C:\Program Files\Google\Chrome\Application\chrome.exe`. |
| Remotion very slow / runs out of memory | Lower concurrency: in `remotion_bridge.render(..., concurrency=1)`. Close the browser studio preview. |
| Titles missing, log says "falling back to FFmpeg drawtext" | Remotion is unavailable (Node/npm not installed). Simple fade titles are used instead; install Node LTS and run `npm ci` in `remotion\`. |
| Blender: `Blender not found` | Install Blender (winget `BlenderFoundation.Blender`) or set `BLENDER_EXE` to `blender.exe`. |
| Blender extremely slow | It is rendering Cycles on CPU. With a GPU: `set BLENDER_ENGINE=BLENDER_EEVEE` (fast) or keep Cycles — the script auto-enables OptiX/CUDA/HIP/oneAPI if available. Lower `--samples`. |
| Blender EEVEE crashes headless on a server/VM | EEVEE needs OpenGL; use Cycles (default). |
| Subtitle filter error with Windows paths | Paths are escaped by `config.ff_filter_path`; avoid `'` and `[]` in folder names if it still fails. |
| `minterpolate` (smooth_slowmo) takes forever | It is CPU-heavy; use only on short ramped shots or drop it (frame blending is used otherwise). |

## Audio
| Symptom | Fix |
|---|---|
| Beat cuts feel off | `studio beats song.mp3` to inspect tempo. For songs with weak drums, use `"cut_mode":"explicit"` with your own `cuts`, or `beat_every` = multiples of the beat period. |
| Loudness not -14 LUFS | QC auto-fixes it (`*_fixed.mp4`). For speech-only content use `"normalize": -16`. |
| Original clip audio missing | Set `"keep_original": true`. Speed-changed/ramped shots are muted on purpose (pitch artefacts). |

## Subtitles (Whisper)
| Symptom | Fix |
|---|---|
| Model download fails | First run downloads the model (free) from huggingface.co into `models/`. Needs internet once. Offline: supply an `.srt` (`--srt`). |
| Slow on CPU | Use `--model base` or `tiny`; NVIDIA users: install the optional CUDA wheels (setup.ps1 offers it). |
| Wrong language | `--language en` (or `de`, `es`, …). |

## Safety
- The pipeline refuses to write into `media/` (`PermissionError: Refusing to write into protected source-media folder`). Choose an output under `exports/`.
- Safe to delete any time: `renders/intermediate/*`, `exports/*` you no longer need, `logs/*`.
