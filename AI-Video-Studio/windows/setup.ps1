<#
  AI-Video-Studio - Windows setup (free/open-source tools only).

  What it does (asks before every install; skips anything already working):
    1. Runs the read-only system inspection.
    2. Installs missing tools with winget from the official winget repository:
         Gyan.FFmpeg, BlenderFoundation.Blender, OpenJS.NodeJS.LTS, Python.Python.3.13, Git.Git
       Optional (only with -WithOptional): KDE.Kdenlive, Audacity.Audacity
    3. Creates the Python virtual environment (.venv) and installs requirements.txt.
    4. Installs the Remotion project's npm dependencies (exact versions from package-lock.json).
    5. Runs `studio doctor`.

  It never: disables security software, changes execution policy permanently, downloads from
  non-official sources, or touches your media. Some winget installers (Blender, Git) show a UAC
  prompt - that is Windows asking YOU for admin approval; decline it to skip that package.

  Usage (PowerShell, from the AI-Video-Studio folder):
      powershell -ExecutionPolicy Bypass -File .\windows\setup.ps1
      powershell -ExecutionPolicy Bypass -File .\windows\setup.ps1 -WithOptional
      powershell -ExecutionPolicy Bypass -File .\windows\setup.ps1 -Yes      # no per-package prompts
#>
param([switch]$WithOptional, [switch]$Yes, [switch]$SkipInspect)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$log = "$root\logs\setup.log"
New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null
function Log($m) { $line = "[$(Get-Date -Format 'HH:mm:ss')] $m"; Write-Host $line; Add-Content -Path $log -Value $line }
function Ask($q) { if ($Yes) { return $true }; $a = Read-Host "$q [y/N]"; return $a -match '^(y|yes)$' }
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") }
function Has($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

if (-not $SkipInspect) { & "$PSScriptRoot\inspect_system.ps1" }

if (-not (Has "winget")) {
    Log "winget not found. Install 'App Installer' from the Microsoft Store (free), then re-run. Or install tools manually - see docs\SETUP_REPORT.md."
    exit 1
}

$packages = @(
    @{ id = "Gyan.FFmpeg";               check = { Has "ffmpeg" };  why = "video/audio processing (GPL build with libass, x264, x265)" },
    @{ id = "OpenJS.NodeJS.LTS";         check = { Has "node" };    why = "Remotion (React motion graphics)" },
    @{ id = "Python.Python.3.13";        check = { (Has "py") -and ((& py -3.13 --version 2>$null) -match "3\.13") }; why = "pipeline scripts (3.13 matches Blender's bpy module)" },
    @{ id = "Git.Git";                   check = { Has "git" };     why = "version control for projects/templates" },
    @{ id = "BlenderFoundation.Blender"; check = { (Has "blender") -or (Test-Path "C:\Program Files\Blender Foundation\*\blender.exe") }; why = "3D motion graphics / compositing (~400 MB download)" }
)
if ($WithOptional) {
    $packages += @{ id = "KDE.Kdenlive";      check = { Test-Path "C:\Program Files\kdenlive\bin\kdenlive.exe" }; why = "manual timeline editing (optional)" }
    $packages += @{ id = "Audacity.Audacity"; check = { Test-Path "C:\Program Files\Audacity\Audacity.exe" };  why = "manual audio editing (optional)" }
}

foreach ($p in $packages) {
    if (& $p.check) { Log "OK (already installed): $($p.id)"; continue }
    if (Ask "Install $($p.id) - $($p.why)?") {
        Log "Installing $($p.id) via winget ..."
        winget install --id $p.id --exact --source winget --accept-package-agreements --accept-source-agreements --silent
        if ($LASTEXITCODE -ne 0) { Log "WARNING: winget returned $LASTEXITCODE for $($p.id) (see TROUBLESHOOTING.md)" }
        Refresh-Path
    } else { Log "Skipped: $($p.id)" }
}

# --- Python environment
$py = $null
if (Has "py") { try { if ((& py -3.13 --version) -match "3\.13") { $py = @("py", "-3.13") } } catch {} }
if (-not $py -and (Has "python")) { $py = @("python") }
if (-not $py) { Log "Python not available - install Python 3.13 and re-run."; exit 1 }
if (-not (Test-Path "$root\.venv\Scripts\python.exe")) {
    Log "Creating virtual environment .venv"
    if ($py.Count -gt 1) { & py -3.13 -m venv "$root\.venv" } else { & python -m venv "$root\.venv" }
}
Log "Installing Python packages (requirements.txt, all open-source) ..."
& "$root\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$root\.venv\Scripts\python.exe" -m pip install -r "$root\requirements.txt"

# Optional: NVIDIA GPU acceleration for Whisper subtitles (free NVIDIA runtime wheels)
$gpu = (Get-CimInstance Win32_VideoController | ForEach-Object Name) -join ";"
if ($gpu -match "NVIDIA" -and (Ask "NVIDIA GPU found. Install CUDA runtime wheels for faster subtitles (~1 GB)?")) {
    & "$root\.venv\Scripts\python.exe" -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
}

# --- Remotion
if (Has "npm.cmd") {
    Log "Installing Remotion dependencies (npm ci) ..."
    Push-Location "$root\remotion"
    if (Test-Path "package-lock.json") { npm.cmd ci --no-fund --no-audit } else { npm.cmd install --no-fund --no-audit }
    Pop-Location
} else { Log "npm not found - Remotion will be unavailable until Node.js LTS is installed." }

# --- Verify
Log "Running studio doctor ..."
& "$root\.venv\Scripts\python.exe" "$root\studio.py" doctor
Log "Setup finished. Next: .\studio.cmd make `"your instruction`" --media media\raw\clip.mp4  (see docs\WORKFLOW.md)"
Log "Optional: run the full test suite:  .\.venv\Scripts\python.exe tests\run_tests.py"
