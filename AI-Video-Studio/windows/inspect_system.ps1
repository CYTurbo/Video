<#
  AI-Video-Studio - Phase 1 system inspection (READ-ONLY: installs and changes nothing).
  Run from the AI-Video-Studio folder:
      powershell -ExecutionPolicy Bypass -File .\windows\inspect_system.ps1
  Writes logs\system_report.json and logs\system_report.md
#>
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null

function Get-ToolVersion($cmd, [string[]]$verArgs = @("--version")) {
    $c = Get-Command $cmd -ErrorAction SilentlyContinue
    if (-not $c) { return $null }
    if ($c.Source -match "WindowsApps\\python") { return @{ path = $c.Source; version = "Microsoft Store alias only (not a real Python)" } }
    try { $v = (& $c.Source @verArgs 2>&1 | Select-Object -First 1) -join "" } catch { $v = "found" }
    return @{ path = $c.Source; version = "$v".Trim() }
}

$os   = Get-CimInstance Win32_OperatingSystem
$cpu  = Get-CimInstance Win32_Processor | Select-Object -First 1
$gpus = Get-CimInstance Win32_VideoController
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3"

$report = [ordered]@{
    arch    = $env:PROCESSOR_ARCHITECTURE
    windows = @{ caption = $os.Caption; version = $os.Version; build = $os.BuildNumber; arch = $os.OSArchitecture }
    cpu     = @{ name = $cpu.Name.Trim(); cores = $cpu.NumberOfCores; threads = $cpu.NumberOfLogicalProcessors }
    ram_gb  = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
    gpus    = @($gpus | ForEach-Object { @{ name = $_.Name; driver = $_.DriverVersion; driver_date = "$($_.DriverDate)"; vram_gb_reported = [math]::Round($_.AdapterRAM / 1GB, 1) } })
    disks   = @($disk | ForEach-Object { @{ drive = $_.DeviceID; free_gb = [math]::Round($_.FreeSpace / 1GB, 1); size_gb = [math]::Round($_.Size / 1GB, 1) } })
    tools   = [ordered]@{
        python  = (Get-ToolVersion "python")
        py_launcher = (Get-ToolVersion "py" @("--list"))
        node    = (Get-ToolVersion "node")
        npm     = (Get-ToolVersion "npm.cmd")
        git     = (Get-ToolVersion "git")
        ffmpeg  = (Get-ToolVersion "ffmpeg" @("-version"))
        ffprobe = (Get-ToolVersion "ffprobe" @("-version"))
        blender = (Get-ToolVersion "blender")
        vscode  = (Get-ToolVersion "code")
        winget  = (Get-ToolVersion "winget")
        claude  = (Get-ToolVersion "claude")
        nvidia_smi = (Get-ToolVersion "nvidia-smi" @("--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"))
    }
    apps = @()
}
# Blender / editors installed but not on PATH
$known = @(
    "C:\Program Files\Blender Foundation\*\blender.exe",
    "C:\Program Files\kdenlive\bin\kdenlive.exe",
    "C:\Program Files\Audacity\Audacity.exe",
    "C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe",
    "C:\Program Files\Shotcut\shotcut.exe",
    "C:\Program Files\obs-studio\bin\64bit\obs64.exe"
)
foreach ($k in $known) { Get-Item $k -ErrorAction SilentlyContinue | ForEach-Object { $report.apps += $_.FullName } }

# GPU class -> recommendations
$gpuNames = ($gpus | ForEach-Object Name) -join "; "
$rec = @()
if ($gpuNames -match "NVIDIA") { $rec += "NVIDIA GPU: use Blender Cycles OptiX/CUDA, FFmpeg h264_nvenc, Whisper on CUDA (optional pip: nvidia-cublas-cu12 nvidia-cudnn-cu12)." }
elseif ($gpuNames -match "AMD|Radeon") { $rec += "AMD GPU: Blender Cycles HIP (RDNA2+), FFmpeg h264_amf; Whisper runs on CPU (int8)." }
elseif ($gpuNames -match "Intel") { $rec += "Intel GPU: Blender Cycles oneAPI (Arc only), FFmpeg h264_qsv; Whisper on CPU." }
else { $rec += "No discrete GPU detected: everything works on CPU; use EEVEE for fast Blender previews, Cycles for finals." }
if ($env:PROCESSOR_ARCHITECTURE -ne "AMD64") { $rec += "Non-x64 CPU ($($env:PROCESSOR_ARCHITECTURE)): Remotion and Whisper (ctranslate2) have no Windows-on-ARM builds." }
if ($report.ram_gb -lt 8) { $rec += "Under 8 GB RAM: keep Remotion concurrency at 1-2 and Whisper model at 'base' or 'small'." }
$free = ($report.disks | Where-Object { $_.drive -eq "C:" }).free_gb
if ($free -lt 15) { $rec += "Less than 15 GB free on C: - full install needs ~6 GB (Blender ~1 GB, FFmpeg ~0.2 GB, Node modules ~0.6 GB, Python libs ~1.5 GB, Whisper small ~0.5 GB)." }
$report.recommendations = $rec

$report | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 "$root\logs\system_report.json"

$md = @("# System report ($(Get-Date -Format 'yyyy-MM-dd HH:mm'))", "",
  "- Windows: $($report.windows.caption) $($report.windows.version) (build $($report.windows.build), $($report.windows.arch))",
  "- CPU: $($report.cpu.name) - $($report.cpu.cores) cores / $($report.cpu.threads) threads",
  "- RAM: $($report.ram_gb) GB",
  "- GPU(s): " + (($report.gpus | ForEach-Object { "$($_.name) (driver $($_.driver))" }) -join "; "),
  "- Disks: " + (($report.disks | ForEach-Object { "$($_.drive) $($_.free_gb) GB free of $($_.size_gb) GB" }) -join "; "), "", "## Tools")
foreach ($k in $report.tools.Keys) {
  $t = $report.tools[$k]
  $md += "- ${k}: " + ($(if ($t) { "$($t.version)  ($($t.path))" } else { "NOT FOUND" }))
}
$md += ""; $md += "## Other apps"; $md += ($report.apps | ForEach-Object { "- $_" }); $md += ""; $md += "## Recommendations"; $md += ($rec | ForEach-Object { "- $_" })
$md | Out-File -Encoding utf8 "$root\logs\system_report.md"
$md | ForEach-Object { Write-Host $_ }
Write-Host "`nSaved: logs\system_report.md and logs\system_report.json"
