$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . ".\.venv\Scripts\Activate.ps1"
}

python -m h2hbot run-once
