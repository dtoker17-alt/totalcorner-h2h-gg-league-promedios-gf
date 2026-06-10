$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . ".\.venv\Scripts\Activate.ps1"
}

python -m h2hbot.webapp --host 0.0.0.0 --port 8000
