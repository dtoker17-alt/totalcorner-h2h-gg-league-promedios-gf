$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TaskName = "H2H GG League Picks Bot"
$ScriptPath = Join-Path $PSScriptRoot "run_once.ps1"

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 10)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Scraper H2H GG League cada 10 min con Telegram y Excel" `
    -Force

Write-Host "Tarea instalada: $TaskName"
Write-Host "Proyecto: $ProjectRoot"
