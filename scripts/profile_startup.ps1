# scripts/profile_startup.ps1
# Capture cold-import timings for glados_pycromanager.GUI.GUI_napari.
# Run from the repo root after `make dev` / install_windows.bat.
#
# Usage:
#   .\.venv\Scripts\Activate.ps1
#   .\scripts\profile_startup.ps1
#
# Output: docs/perf-baseline.txt (appended with a timestamped header)

$outFile = "docs\perf-baseline.txt"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$header = "=== $timestamp ==="

Write-Host "Profiling startup import times..."
$importtimeOutput = & python -X importtime -c "import glados_pycromanager.GUI.GUI_napari" 2>&1

Add-Content -Path $outFile -Value ""
Add-Content -Path $outFile -Value $header
$importtimeOutput | Add-Content -Path $outFile

Write-Host "Results appended to $outFile"
Write-Host "Top 20 slowest imports:"
$importtimeOutput |
    Where-Object { $_ -match "import time" -or $_ -match "^\s+\d" } |
    Select-Object -Last 20 |
    Write-Host
