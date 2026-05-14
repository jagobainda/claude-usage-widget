<#
.SYNOPSIS
    Promotes the Claude Usage Widget tray icon out of the overflow flyout
    so it shows directly on the Windows 10/11 taskbar.

.DESCRIPTION
    Windows stores per-icon tray placement under
    HKCU\Control Panel\NotifyIconSettings\<id>. Each subkey carries the
    ExecutablePath that registered the icon and an IsPromoted DWORD:
      0 → icon lives in the "^" overflow flyout
      1 → icon is pinned to the always-visible taskbar tray

    This script finds the entry that matches the widget's .exe and flips
    IsPromoted to 1, then restarts explorer.exe so the change shows up.

    The widget must have run at least once with this exact .exe path
    before the registry entry exists.

.PARAMETER ExePath
    Path to the widget .exe. If omitted, looks at:
      1. releases\ClaudeUsageWidget-*.exe (most recent)
      2. dist\ClaudeUsageWidget.exe

.PARAMETER NoRestart
    Skip the explorer.exe restart at the end. The change will then take
    effect after the next sign-out.

.EXAMPLE
    .\scripts\promote-tray-icon.ps1
    .\scripts\promote-tray-icon.ps1 -ExePath "C:\Tools\ClaudeUsageWidget.exe"
    .\scripts\promote-tray-icon.ps1 -NoRestart
#>

param(
    [string]$ExePath = "",
    [switch]$NoRestart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path $PSScriptRoot -Parent

# ── Resolve target exe ────────────────────────────────────────────────────────
if (-not $ExePath) {
    $candidate = Get-ChildItem (Join-Path $RepoRoot "releases\ClaudeUsageWidget*.exe") -ErrorAction SilentlyContinue |
                 Sort-Object LastWriteTime -Descending |
                 Select-Object -First 1
    if (-not $candidate) {
        $fallback = Join-Path $RepoRoot "dist\ClaudeUsageWidget.exe"
        if (Test-Path $fallback) { $candidate = Get-Item $fallback }
    }
    if (-not $candidate) {
        Write-Error "No exe found. Pass -ExePath explicitly or build first with scripts\build-release.ps1."
        exit 1
    }
    $ExePath = $candidate.FullName
}

if (-not (Test-Path $ExePath)) {
    Write-Error "Exe not found: $ExePath"; exit 1
}
$ExePath = (Resolve-Path $ExePath).Path
Write-Host "Target exe: $ExePath" -ForegroundColor Cyan

# ── Enumerate tray icon entries ───────────────────────────────────────────────
$Base = "HKCU:\Control Panel\NotifyIconSettings"
if (-not (Test-Path $Base)) {
    Write-Error "Registry key not found: $Base`nRun the widget at least once first, then re-run this script."
    exit 1
}

$entries = Get-ChildItem $Base | ForEach-Object {
    $props = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
    if ($props -and $props.PSObject.Properties.Name -contains 'ExecutablePath') {
        $promoted = 0
        if ($props.PSObject.Properties.Name -contains 'IsPromoted') {
            $promoted = [int]$props.IsPromoted
        }
        [PSCustomObject]@{
            KeyPath        = $_.PSPath
            ExecutablePath = [string]$props.ExecutablePath
            IsPromoted     = $promoted
        }
    }
}

$matched = @($entries | Where-Object { $_.ExecutablePath -ieq $ExePath })

if ($matched.Count -eq 0) {
    $exeName = Split-Path $ExePath -Leaf
    $byName  = @($entries | Where-Object { (Split-Path $_.ExecutablePath -Leaf) -ieq $exeName })
    if ($byName.Count -gt 0) {
        Write-Warning "No tray entry for exactly '$ExePath', but found these by filename:"
        $byName | Format-Table ExecutablePath, IsPromoted -AutoSize
        Write-Warning "Re-run with -ExePath set to one of the paths above."
    } else {
        Write-Warning "No tray entry references $exeName."
        Write-Warning "Run the widget once so Windows registers it, then re-run this script."
        Write-Host ""
        Write-Host "Existing tray entries (for reference):"
        $entries | Format-Table ExecutablePath, IsPromoted -AutoSize
    }
    exit 1
}

$changed = 0
foreach ($m in $matched) {
    if ($m.IsPromoted -eq 1) {
        Write-Host "Already promoted: $($m.ExecutablePath)" -ForegroundColor DarkGray
        continue
    }
    Set-ItemProperty -Path $m.KeyPath -Name "IsPromoted" -Value 1 -Type DWord
    Write-Host "Promoted: $($m.ExecutablePath)" -ForegroundColor Green
    $changed++
}

if ($changed -eq 0) {
    Write-Host ""
    Write-Host "Nothing to do." -ForegroundColor DarkGray
    exit 0
}

# ── Restart explorer to apply ─────────────────────────────────────────────────
if ($NoRestart) {
    Write-Host ""
    Write-Host "Skipped explorer restart. Sign out / in (or restart explorer.exe) to apply."
    exit 0
}

Write-Host ""
Write-Host "Restarting explorer.exe to apply..." -ForegroundColor Yellow
Get-Process explorer -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
if (-not (Get-Process explorer -ErrorAction SilentlyContinue)) {
    Start-Process explorer.exe
}
Write-Host "✅ Done." -ForegroundColor Green
