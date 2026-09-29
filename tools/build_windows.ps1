param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
$previousCache = $env:PYINSTALLER_CONFIG_DIR
try {
    $buildPython = Join-Path $projectRoot ".venv-build\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $buildPython)) {
        & $Python -m venv .venv-build
        if ($LASTEXITCODE -ne 0) { throw "Could not create build environment" }
    }
    & $buildPython -m pip install --cache-dir build/pip-cache -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw "Could not install build dependencies" }
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $projectRoot "build\pyinstaller-cache"
    & $buildPython tools/prepare_tk.py
    if ($LASTEXITCODE -ne 0) { throw "Could not collect Tcl/Tk resources" }
    $tclData = (Join-Path $projectRoot "build\tk\_tcl_data") + ":_tcl_data"
    $tkData = (Join-Path $projectRoot "build\tk\_tk_data") + ":_tk_data"
    $licenseData = (Join-Path $projectRoot "build\licenses") + ":licenses"
    & $buildPython -m PyInstaller --noconfirm --clean --onefile --windowed --noupx --name BlackWhiteChess --add-data $tclData --add-data $tkData --add-data $licenseData --distpath dist --workpath build/pyinstaller --specpath build main.py
    if ($LASTEXITCODE -ne 0) { throw "Packaging failed" }
    Compress-Archive -LiteralPath @("dist\BlackWhiteChess.exe", "DISTRIBUTION.md", "LICENSE", "build\licenses") -DestinationPath "dist\BlackWhiteChess-Windows-x64.zip" -Force
    Write-Host "Ready: $projectRoot\dist\BlackWhiteChess.exe"
} finally {
    $env:PYINSTALLER_CONFIG_DIR = $previousCache
    Pop-Location
}
