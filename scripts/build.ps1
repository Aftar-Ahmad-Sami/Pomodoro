<#
.SYNOPSIS
    Builds dist\Pomodoro.exe and the installer dist\PomodoroSetup.exe with PyInstaller.

.DESCRIPTION
    Picks the Python interpreter in this order:
      1. -Python, if given
      2. the activated virtual environment ($env:VIRTUAL_ENV)
      3. the activated conda environment ($env:CONDA_PREFIX)
      4. the project's .venv
      5. python on PATH
    Conda environments keep the Tcl/Tk DLLs in Library\bin, which PyInstaller doesn't
    pick up on its own, so they are added explicitly when present.

.EXAMPLE
    .\scripts\build.ps1
.EXAMPLE
    .\scripts\build.ps1 -Python C:\path\to\python.exe
#>
param(
    [string]$Python
)

# No $ErrorActionPreference = "Stop": PowerShell 5.1 would treat PyInstaller's stderr
# logging as a failure. Exit codes are checked explicitly instead.
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

function Find-Python {
    $candidates = @()
    if ($env:VIRTUAL_ENV) { $candidates += Join-Path $env:VIRTUAL_ENV "Scripts\python.exe" }
    if ($env:CONDA_PREFIX) { $candidates += Join-Path $env:CONDA_PREFIX "python.exe" }
    $candidates += Join-Path $root ".venv\Scripts\python.exe"
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    $onPath = Get-Command python -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    return $null
}

if (-not $Python) { $Python = Find-Python }
if (-not $Python -or -not (Test-Path $Python)) {
    throw "No Python found. Activate an environment with the project installed (pip install -e "".[build]""), or pass -Python."
}
$Python = (Resolve-Path $Python).Path
Write-Host "Using Python: $Python"

& $Python -c "import PyInstaller, pomodoro" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller or the pomodoro package is missing from '$Python'. Run: pip install -e "".[build]"""
}

$extra = @()
$condaBin = Join-Path (Split-Path $Python) "Library\bin"
if (Test-Path (Join-Path $condaBin "tk86t.dll")) {
    $env:PATH = "$condaBin;$env:PATH"
    $extra += "--add-binary", "$condaBin\tcl86t.dll;.", "--add-binary", "$condaBin\tk86t.dll;."
}

function Invoke-PyInstaller([string]$Name, [string]$Entry, [string[]]$More) {
    & $Python -m PyInstaller --clean --onefile --windowed --noconfirm --name $Name `
        --icon src\pomodoro\assets\icon.ico `
        --add-data "src\pomodoro\assets;pomodoro\assets" `
        --paths src `
        @extra @More `
        $Entry
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed for $Name with exit code $LASTEXITCODE" }
}

Push-Location $root
try {
    Invoke-PyInstaller "Pomodoro" "src\pomodoro\__main__.py" @()
    # The installer embeds the app exe built above
    Invoke-PyInstaller "PomodoroSetup" "src\pomodoro\installer.py" @("--add-data", "dist\Pomodoro.exe;payload")
}
finally {
    Pop-Location
}
