# One-time setup (Windows PowerShell): backend venv + deps, frontend deps.
$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
Set-Location backend
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Set-Location ..\frontend
npm install
Pop-Location
Write-Host "`nSetup complete. Run .\start.ps1" -ForegroundColor Green
