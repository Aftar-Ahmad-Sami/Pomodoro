# Builds dist\Pomodoro.exe using the "misc" conda env.
# Conda keeps the Tcl/Tk DLLs in Library\bin, which PyInstaller doesn't pick up
# on its own, so they are added explicitly.

$envDir = "$env:USERPROFILE\.conda\envs\misc"
$bin = "$envDir\Library\bin"
$env:PATH = "$envDir;$bin;$env:PATH"

& "$envDir\python.exe" -m PyInstaller --clean --onefile --windowed --name Pomodoro --noconfirm `
    --icon assets\icon.ico `
    --add-data "assets;assets" `
    --add-binary "$bin\tcl86t.dll;." `
    --add-binary "$bin\tk86t.dll;." `
    pomodoro.py
