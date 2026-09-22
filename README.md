# Windows Usage Widgets

Monorepo con tres widgets independientes para la bandeja de Windows:

- **Claude Usage Widget** muestra las ventanas de consumo de Claude Code.
- **Codex Usage Widget** muestra las ventanas que expone OpenAI Codex CLI.
- **OpenCode Usage Widget** muestra las ventanas de la suscripción OpenCode Go.

Los tres ofrecen porcentaje en el icono, popup con todas las ventanas disponibles,
cuenta atrás hasta el reinicio, refresco automático/manual y estados de carga,
error o sesión no iniciada. Tienen nombres de bandeja, procesos, ejecutables,
directorios de instalación y entradas de autoarranque distintos, por lo que se
pueden ejecutar simultáneamente.

## Arquitectura

```text
apps/
  claude-usage-widget/     # autenticación y API de Claude
  codex-usage-widget/      # cliente oficial codex app-server
  opencode-usage-widget/   # credencial local y endpoint de OpenCode Go
packages/
  widget-common/           # pystray, Tkinter, popup, scheduler, iconos y fechas
installer/                 # un script Inno Setup por aplicación
scripts/                   # build compartido y utilidades de distribución
tests/                     # pruebas unitarias y App Server simulado
```

La autenticación y la lectura de datos no se comparten entre proveedores. La
capa común solo conoce modelos de uso neutrales y la experiencia de escritorio.

## Requisitos

- Windows 10 u 11.
- Python 3.10 o posterior para ejecutar desde código fuente.
- Dependencias de [`requirements.txt`](requirements.txt).
- Para Claude: [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code/overview)
  instalado y autenticado.
- Para Codex: una versión compatible de
  [Codex CLI](https://developers.openai.com/codex/cli/) instalada con la opción
  oficial para Windows, disponible en `PATH` y autenticada. El widget usa
  exclusivamente el protocolo oficial
  [`codex app-server`](https://developers.openai.com/codex/app-server/); no lee,
  copia ni renueva manualmente `~/.codex/auth.json`.
- Para OpenCode: [OpenCode](https://opencode.ai/docs/) configurado con una
  suscripción Go. El widget lee exclusivamente la entrada `opencode-go` de
  `%USERPROFILE%\.local\share\opencode\auth.json` y nunca modifica ese archivo.

## Autenticación

Claude Code:

```powershell
claude login
```

Codex CLI (tras instalarlo desde la guía oficial enlazada arriba):

```powershell
codex login
codex --version
```

Codex Usage Widget inicia `codex app-server` como subproceso local, realiza el
handshake `initialize`/`initialized` y consulta `account/rateLimits/read`. No
crea conversaciones, hilos o turnos y no consume inferencia. Si el CLI no está
instalado, no hay sesión o la versión no soporta el método, el popup muestra una
explicación sin exponer datos de cuenta.

OpenCode Go (dentro de la TUI de OpenCode):

```text
/connect
OpenCode Go
```

OpenCode Usage Widget consulta `GET https://opencode.ai/zen/go/v1/usage` con la
clave que OpenCode ya tiene guardada. La respuesta incluye las ventanas móvil
de cinco horas, semanal y mensual. La consulta no crea sesiones ni consume
inferencia.

> [!WARNING]
>
> Claude Usage Widget consulta actualmente el endpoint privado y no documentado
> que utiliza Claude Code. Anthropic puede modificarlo o retirarlo sin aviso.
> Codex Usage Widget, en cambio, usa el App Server oficial de OpenAI y requiere
> una versión de Codex CLI compatible con los métodos de cuenta.
> OpenCode Usage Widget usa una ruta implementada por OpenCode, pero todavía no
> documentada como contrato estable. Solo expone OpenCode Go: no incluye saldo
> Zen ni consumo de proveedores externos.

## Ejecutar desde código fuente

Preparación común:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Claude:

```powershell
python .\apps\claude-usage-widget\main.py
```

El comando histórico continúa funcionando y ejecuta Claude:

```powershell
python .\main.py
```

Codex:

```powershell
python .\apps\codex-usage-widget\main.py
```

OpenCode:

```powershell
python .\apps\opencode-usage-widget\main.py
```

Para usar los tres a la vez, ejecuta cada comando en una terminal distinta. Los
identificadores internos son `claude-usage`, `codex-usage` y `opencode-usage`.

## Pruebas

Las pruebas usan respuestas y procesos locales simulados; no requieren cuentas
reales ni llamadas de red:

```powershell
python -m unittest discover -s tests -v
```

Cubren los formatos actuales y heredados de Claude, ventanas primarias,
secundarias y múltiples `limitId` de Codex, campos desconocidos, timestamps,
etiquetas por duración, correlación JSONL, notificaciones intercaladas, timeout,
reinicio y cierre del subproceso. Para OpenCode cubren credenciales locales,
porcentajes, ventanas parciales, respuestas incompatibles y errores HTTP.

## Compilar ejecutables

El script compartido acepta `claude`, `codex`, `opencode` o `all`. Si se omite `-App`, se
compila Claude para conservar el comportamiento del comando anterior.

```powershell
.\scripts\build-release.ps1 -App claude -Version "1.1.0"
.\scripts\build-release.ps1 -App codex  -Version "1.1.0"
.\scripts\build-release.ps1 -App opencode -Version "1.1.0"
.\scripts\build-release.ps1 -App all    -Version "1.1.0"
```

Los binarios independientes quedan en:

```text
dist\ClaudeUsageWidget.exe
dist\CodexUsageWidget.exe
dist\OpenCodeUsageWidget.exe
releases\ClaudeUsageWidget-1.1.0.exe
releases\CodexUsageWidget-1.1.0.exe
releases\OpenCodeUsageWidget-1.1.0.exe
```

La firma opcional mantiene los parámetros existentes:

```powershell
.\scripts\build-release.ps1 -App all -Version "1.1.0" `
  -Sign -CertThumbprint "<sha1>"
```

## Generar instaladores

Instala Inno Setup 6 (`winget install JRSoftware.InnoSetup`) y añade
`-Installer`:

```powershell
.\scripts\build-release.ps1 -App claude -Version "1.1.0" -Installer
.\scripts\build-release.ps1 -App codex  -Version "1.1.0" -Installer
.\scripts\build-release.ps1 -App opencode -Version "1.1.0" -Installer
.\scripts\build-release.ps1 -App all    -Version "1.1.0" -Installer
```

Los instaladores se generan sin sobrescribirse:

```text
releases\ClaudeUsageWidget-Setup-1.1.0.exe
releases\CodexUsageWidget-Setup-1.1.0.exe
releases\OpenCodeUsageWidget-Setup-1.1.0.exe
```

Cada instalador usa su propio GUID, directorio bajo `%LocalAppData%`, acceso del
menú Inicio y valor de autoarranque. Desinstalar uno no afecta al otro ni a las
credenciales administradas por los CLI oficiales.

## Iconos

Claude conserva su marca actual. Codex usa por ahora un símbolo geométrico
neutral y original incluido en el código; no reutiliza el logotipo de Claude ni
pretende ser una marca oficial de OpenAI. OpenCode usa el primer glifo de su
logotipo monocromo publicado bajo la licencia MIT del proyecto original, con el
gris como color de énfasis del widget.

## Licencia

Distribuido según [`LICENSE.txt`](LICENSE.txt).
