@echo off
cd /d "%~dp0"
echo.
echo ==========================================
echo   Knowledge Vault
echo ==========================================
echo.
echo Starting server...
echo Local:  http://127.0.0.1:8000
echo LAN:    http://%COMPUTERNAME%:8000
echo.
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
