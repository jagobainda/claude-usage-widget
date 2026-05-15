; Inno Setup script for Claude Usage Widget.
; Per-user install to %LocalAppData%\ClaudeUsageWidget, no admin required.
;
; Compiled by scripts\build-release.ps1 when -Installer is passed.
; Manual compile:
;   ISCC.exe /DAppVersion=1.0.0 /DRepoRoot="..\" installer\ClaudeUsageWidget.iss

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#ifndef RepoRoot
  #define RepoRoot ".."
#endif

#define AppName       "ClaudeUsageWidget"
#define AppDisplay    "Claude Usage Widget"
#define AppPublisher  "Jagoba Inda"
#define AppExe        "ClaudeUsageWidget.exe"

[Setup]
; Stable per-app GUID. Do NOT change between versions or upgrades will
; reinstall side-by-side instead of replacing the previous install.
AppId={{B92F4A7C-1E5D-4F8A-B6C3-9E2D8F7A1C45}
AppName={#AppDisplay}
AppVersion={#AppVersion}
AppVerName={#AppDisplay} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppDisplay}
PrivilegesRequired=lowest
OutputDir={#RepoRoot}\releases
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#RepoRoot}\build\app.ico
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppDisplay} Setup
VersionInfoProductName={#AppDisplay}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "startmenuicon"; Description: "Crear acceso directo en el menu Inicio (recomendado)"; GroupDescription: "Opciones adicionales:"
Name: "autostart"; Description: "Iniciar {#AppDisplay} con Windows"; GroupDescription: "Opciones adicionales:"; Flags: unchecked

[Files]
Source: "{#RepoRoot}\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\{#AppDisplay}"; Filename: "{app}\{#AppExe}"; Tasks: startmenuicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
; No 'postinstall' flag = no checkbox on the Finish page; the app is launched
; unconditionally at the end of install (skipped only on /SILENT /VERYSILENT).
Filename: "{app}\{#AppExe}"; Flags: nowait skipifsilent

[UninstallRun]
; Best-effort: close the running widget before files are removed, so the
; uninstall doesn't get blocked by "file in use".
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "KillRunning"
