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
    Path to the widget .exe. If omitted, looks at (in order):
      1. %LocalAppData%\ClaudeUsageWidget\ClaudeUsageWidget.exe (installed)
      2. releases\ClaudeUsageWidget-*.exe (most recent build, repo only)
      3. dist\ClaudeUsageWidget.exe (PyInstaller output, repo only)
    The repo-relative fallbacks are skipped when the script is invoked
    remotely (e.g. via `irm ... | iex`) since $PSScriptRoot is empty.

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

# ── Resolve target exe ────────────────────────────────────────────────────────
if (-not $ExePath) {
    $candidates = @(
        # Installed location (works whether the script runs from the repo
        # or remotely via `irm ... | iex`).
        (Join-Path $env:LOCALAPPDATA "ClaudeUsageWidget\ClaudeUsageWidget.exe")
    )

    # If we are running as a real .ps1 file inside the repo, also look at
    # the build outputs. $PSScriptRoot is empty when invoked via iex, so
    # this block is silently skipped in that case.
    if ($PSScriptRoot) {
        $RepoRoot = Split-Path $PSScriptRoot -Parent
        $latestRelease = Get-ChildItem (Join-Path $RepoRoot "releases\ClaudeUsageWidget*.exe") -ErrorAction SilentlyContinue |
                         Sort-Object LastWriteTime -Descending |
                         Select-Object -First 1 -ExpandProperty FullName
        if ($latestRelease) { $candidates += $latestRelease }
        $candidates += (Join-Path $RepoRoot "dist\ClaudeUsageWidget.exe")
    }

    $found = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $found) {
        Write-Error "No widget .exe found. Tried:`n  $($candidates -join "`n  ")`nPass -ExePath explicitly or install the widget first."
        exit 1
    }
    $ExePath = $found
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
