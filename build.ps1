# build.ps1 -- Compile FontLicenseClassifier en un .exe Windows autonome.
#
# Utilisation :
#   1) Ouvrir PowerShell dans le dossier du projet
#   2) .\build.ps1
#   3) L'executable se trouve dans .\dist\FontLicenseClassifier.exe
#
# Prerequis : Python 3.10+ installe depuis python.org (coche "Add to PATH"
# a l'installation). Un Python "embarque"/minimal sans Tkinter ne fonctionnera
# pas : l'installeur officiel python.org inclut Tkinter par defaut.

$ErrorActionPreference = 'Stop'

Write-Host "Verification de Python..."
python --version

Write-Host "Creation de l'environnement virtuel (.venv)..."
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& ".\.venv\Scripts\Activate.ps1"

Write-Host "Installation des dependances..."
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
python -m pip install pyinstaller --quiet

Write-Host "Nettoyage des anciennes compilations..."
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

Write-Host "Compilation avec PyInstaller..."
python -m PyInstaller --noconfirm --clean FontLicenseClassifier.spec

Write-Host ""
Write-Host "Termine. Executable genere : $PWD\dist\FontLicenseClassifier.exe" -ForegroundColor Green
