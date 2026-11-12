<#
  AI-Video-Studio - Windows setup (free/open-source tools only).

  What it does (asks before every install; skips anything already working):
    1. Runs the read-only system inspection.
    2. Installs missing tools with winget from the official winget repository:
         Gyan.FFmpeg, BlenderFoundation.Blender, OpenJS.NodeJS.LTS, Python.Python.3.13, Git.Git
       Optional (only with -WithOptional): KDE.Kdenlive, Audacity.Audacity
    3. Creates the Python virtual environment (.venv) and installs requirements.txt pinned by requirements.lock.txt.
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
# Run a native command and return its output; never throws (Windows PowerShell 5.1 turns native stderr into
# terminating errors when ErrorActionPreference=Stop, e.g. `py -3.13` when 3.13 is not installed).
function Try-Native([string]$exe, [string[]]$argv) {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { $out = (& $exe @argv 2>&1 | Out-String) } catch { $out = "" } finally { $ErrorActionPreference = $old }
    return $out
}
# A usable Python 3.13: the py launcher, or python.exe that is NOT the Microsoft Store alias (WindowsApps stub).
function Find-Python313 {
    if ((Has "py") -and ((Try-Native "py" @("-3.13", "--version")) -match "Python 3\.13")) { return @("py", "-3.13") }
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c -and $c.Source -notmatch "WindowsApps" -and ((Try-Native $c.Source @("--version")) -match "Python 3\.13")) { return @($c.Source) }
    return $null
}
function Node-Major {
    if (-not (Has "node")) { return 0 }
    $v = Try-Native "node" @("--version")
    if ($v -match "v(\d+)\.") { return [int]$Matches[1] } else { return 0 }
}
function Fail($m) { Log "ERROR: $m"; Log "Setup stopped. See docs\TROUBLESHOOTING.md"; exit 1 }

if (-not $SkipInspect) { & "$PSScriptRoot\inspect_system.ps1" }

$arch = $env:PROCESSOR_ARCHITECTURE
if ($env:PROCESSOR_ARCHITEW6432) { $arch = $env:PROCESSOR_ARCHITEW6432 }
if ($arch -ne "AMD64") {
    Log "WARNING: this PC is $arch, not x64. Remotion has no Windows-on-ARM renderer and several Python wheels"
    Log "         (ctranslate2/Whisper) are x64-only. FFmpeg editing may work; motion graphics and captions will not."
    if (-not (Ask "Continue anyway?")) { exit 1 }
}

if (-not (Has "winget")) {
    Log "winget not found. Install 'App Installer' from the Microsoft Store (free), then re-run. Or install tools manually - see docs\SETUP_REPORT.md."
    exit 1
}

$packages = @(
    @{ id = "Gyan.FFmpeg";               check = { Has "ffmpeg" };  why = "video/audio processing (GPL build with libass, x264, x265)" },
    @{ id = "OpenJS.NodeJS.LTS";         check = { (Node-Major) -ge 18 };  why = "Remotion (React motion graphics); needs Node 18+" },
    @{ id = "Python.Python.3.13";        check = { [bool](Find-Python313) }; why = "pipeline scripts (all pinned wheels verified for Python 3.13 x64)" },
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
$py = Find-Python313
if (-not $py) { Fail "Python 3.13 not found (the Microsoft Store 'python' alias does not count). Install Python.Python.3.13 and re-run." }
if (-not (Test-Path "$root\.venv\Scripts\python.exe")) {
    Log "Creating virtual environment .venv with $($py -join ' ')"
    if ($py.Count -gt 1) { & $py[0] $py[1] -m venv "$root\.venv" } else { & $py[0] -m venv "$root\.venv" }
    if ($LASTEXITCODE -ne 0) { Fail "python -m venv failed" }
}
$vpy = "$root\.venv\Scripts\python.exe"
Log "Installing Python packages (exact tested versions from requirements.lock.txt, all open-source) ..."
& $vpy -m pip install --upgrade pip
& $vpy -m pip install -r "$root\requirements.txt" -c "$root\requirements.lock.txt"
if ($LASTEXITCODE -ne 0) { Fail "pip install failed (see output above)" }

# Optional: NVIDIA GPU acceleration for Whisper subtitles (free NVIDIA runtime wheels)
$gpu = (Get-CimInstance Win32_VideoController | ForEach-Object Name) -join ";"
if ($gpu -match "NVIDIA" -and (Ask "NVIDIA GPU found. Install CUDA runtime wheels for faster subtitles (~1 GB)?")) {
    & $vpy -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
    if ($LASTEXITCODE -ne 0) { Log "WARNING: CUDA wheels failed to install - captions will run on CPU" }
}

# --- Remotion
if ((Node-Major) -ge 18 -and (Has "npm.cmd")) {
    Log "Installing Remotion dependencies (npm ci) ..."
    Push-Location "$root\remotion"
    if (Test-Path "package-lock.json") { npm.cmd ci --no-fund --no-audit } else { npm.cmd install --no-fund --no-audit }
    $npmExit = $LASTEXITCODE
    Pop-Location
    if ($npmExit -ne 0) { Fail "npm ci failed in remotion\ (Node $(Node-Major))" }
} else { Log "Node.js 18+/npm not found - Remotion will be unavailable until Node.js LTS is installed." }

# --- Verify
Log "Running studio doctor ..."
& $vpy "$root\studio.py" doctor
Log "Setup finished. Next: .\studio.cmd make `"your instruction`" --media media\raw\clip.mp4  (see docs\WORKFLOW.md)"
Log "Optional: run the full test suite:  .\.venv\Scripts\python.exe tests\run_tests.py"
