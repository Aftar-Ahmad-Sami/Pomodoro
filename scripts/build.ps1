<#
.SYNOPSIS
    Builds dist\Pomodoro.exe and the installer dist\PomodoroSetup.exe with PyInstaller.

.DESCRIPTION
    Uses the project's .venv by default; pass -Python to use another interpreter.
    Conda environments keep the Tcl/Tk DLLs in Library\bin, which PyInstaller doesn't
    pick up on its own, so they are added explicitly when present.
#>
param(
    [string]$Python = (Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe")
)

# No $ErrorActionPreference = "Stop": PowerShell 5.1 would treat PyInstaller's stderr
# logging as a failure. Exit codes are checked explicitly instead.
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

if (-not (Test-Path $Python)) {
    throw "Python not found at '$Python'. Create the venv first (see README) or pass -Python."
}

$extra = @()
$condaBin = Join-Path (Split-Path (Resolve-Path $Python)) "Library\bin"
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
