<#
.SYNOPSIS
    Builds Claude Usage Widget into a single Windows .exe and optionally signs it.

.DESCRIPTION
    1. Ensures a build venv exists with the project dependencies + PyInstaller
    2. Generates app.ico from scripts/_make_icon.py
    3. Builds a one-file, no-console executable with PyInstaller
    4. Optionally signs the .exe with the Certum smart card via signtool

.PARAMETER Sign
    Sign the resulting .exe with the Certum smart card (ACR39U reader).
    Requires the card inserted and -CertThumbprint.

.PARAMETER CertThumbprint
    SHA1 thumbprint of the code-signing certificate. Required with -Sign.

.PARAMETER KeyInfoFile
    Path to the Certum keyinfo.inf used by `certutil -repairstore`.
    Defaults to C:\Users\Jagoba\keyinfo.inf (same as LostieLauncher).

.PARAMETER Version
    Version label appended to the output filename. Defaults to 1.0.0.

.EXAMPLE
    .\scripts\build-release.ps1
    .\scripts\build-release.ps1 -Sign -CertThumbprint "20ed2e50..."
    .\scripts\build-release.ps1 -Version "1.2.0" -Sign -CertThumbprint "20ed2e50..."
#>

param(
    [switch]$Sign,
    [string]$CertThumbprint = "",
    [string]$KeyInfoFile = "C:\Users\Jagoba\keyinfo.inf",
    [string]$Version = "1.0.0"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Config ────────────────────────────────────────────────────────────────────
$TimestampUrl = "http://time.certum.pl"
$SigntoolExe  = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe"
$AppName      = "ClaudeUsageWidget"
$AppDisplay   = "Claude Usage Widget"

# ── Paths ─────────────────────────────────────────────────────────────────────
$RepoRoot   = Split-Path $PSScriptRoot -Parent
$Main       = Join-Path $RepoRoot "main.py"
$Reqs       = Join-Path $RepoRoot "requirements.txt"
$BuildDir   = Join-Path $RepoRoot "build"
$DistDir    = Join-Path $RepoRoot "dist"
$ReleaseDir = Join-Path $RepoRoot "releases"
$IconFile   = Join-Path $BuildDir "app.ico"
$VenvDir    = Join-Path $RepoRoot ".venv"
$Python     = Join-Path $VenvDir "Scripts\python.exe"
$Pip        = Join-Path $VenvDir "Scripts\pip.exe"
$MakeIcon   = Join-Path $PSScriptRoot "_make_icon.py"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Claude Usage Widget — Release Build" -ForegroundColor Cyan
Write-Host "  Version : $Version" -ForegroundColor Cyan
if ($Sign) {
    Write-Host "  Signing : Enabled (Certum smart card)" -ForegroundColor Cyan
    Write-Host "  Thumbprint: $CertThumbprint" -ForegroundColor Cyan
}
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ── Validate signing prerequisites ────────────────────────────────────────────
if ($Sign) {
    if (-not $CertThumbprint) {
        Write-Error "-CertThumbprint is required when using -Sign."; exit 1
    }
    if (-not (Test-Path $SigntoolExe)) {
        Write-Error "signtool.exe not found at: $SigntoolExe`nInstall the Windows SDK or update the path in this script."
        exit 1
    }
    if (-not (Test-Path $KeyInfoFile)) {
        Write-Error "keyinfo.inf not found at: $KeyInfoFile"
        exit 1
    }
}

# ── Venv ──────────────────────────────────────────────────────────────────────
if (-not (Test-Path $Python)) {
    Write-Host "[1/5] Creating venv at $VenvDir..." -ForegroundColor Yellow
    python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Write-Error "venv creation failed."; exit 1 }
} else {
    Write-Host "[1/5] Reusing existing venv at $VenvDir." -ForegroundColor Yellow
}

# ── Deps ──────────────────────────────────────────────────────────────────────
Write-Host "[2/5] Installing dependencies..." -ForegroundColor Yellow
& $Python -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { Write-Error "pip upgrade failed."; exit 1 }
& $Pip install -r $Reqs --quiet
if ($LASTEXITCODE -ne 0) { Write-Error "pip install requirements failed."; exit 1 }
& $Pip install pyinstaller --quiet
if ($LASTEXITCODE -ne 0) { Write-Error "pip install pyinstaller failed."; exit 1 }

# ── Icon ──────────────────────────────────────────────────────────────────────
Write-Host "[3/5] Generating app.ico..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
& $Python $MakeIcon $IconFile
if ($LASTEXITCODE -ne 0) { Write-Error "icon generation failed."; exit 1 }

# ── Build ─────────────────────────────────────────────────────────────────────
Write-Host "[4/5] Building with PyInstaller..." -ForegroundColor Yellow
Remove-Item $DistDir -Recurse -Force -ErrorAction SilentlyContinue
$pyiWork = Join-Path $BuildDir "pyinstaller"
Remove-Item $pyiWork -Recurse -Force -ErrorAction SilentlyContinue

& $Python -m PyInstaller `
    --onefile `
    --noconsole `
    --name $AppName `
    --icon $IconFile `
    --distpath $DistDir `
    --workpath $pyiWork `
    --specpath $BuildDir `
    --hidden-import pystray._win32 `
    $Main
if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller failed."; exit 1 }

$ExePath = Join-Path $DistDir "$AppName.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "Expected exe not found at: $ExePath"; exit 1
}

# ── Sign ──────────────────────────────────────────────────────────────────────
if ($Sign) {
    Write-Host "[5/5] Signing executable..." -ForegroundColor Yellow
    Write-Host "Registrando clave de tarjeta inteligente..." -ForegroundColor Yellow
    certutil -repairstore -user MY $CertThumbprint $KeyInfoFile
    if ($LASTEXITCODE -ne 0) { Write-Error "certutil -repairstore falló."; exit 1 }

    & $SigntoolExe sign `
        /sha1 $CertThumbprint `
        /tr $TimestampUrl `
        /td SHA256 `
        /fd SHA256 `
        /d $AppDisplay `
        $ExePath
    if ($LASTEXITCODE -ne 0) { Write-Error "signtool sign failed."; exit 1 }

    & $SigntoolExe verify /pa $ExePath
    if ($LASTEXITCODE -ne 0) { Write-Error "signtool verify failed."; exit 1 }
} else {
    Write-Host "[5/5] Skipping signing (pass -Sign to enable)." -ForegroundColor DarkGray
}

# ── Stage release ─────────────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$ReleaseExe = Join-Path $ReleaseDir "$AppName-$Version.exe"
Copy-Item $ExePath $ReleaseExe -Force

Write-Host ""
Write-Host "✅ Build complete: $ReleaseExe" -ForegroundColor Green
Get-Item $ReleaseExe | Format-Table Name, Length, LastWriteTime -AutoSize
