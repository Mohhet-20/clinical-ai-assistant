# Starts API (http://localhost:8000) and UI (http://localhost:5173) in two windows.
Set-Location $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$PSScriptRoot\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
Start-Process powershell -ArgumentList "-NoExit","-Command","cd '$PSScriptRoot\frontend'; npm run dev"
Start-Sleep 6
Start-Process "http://localhost:5173"
