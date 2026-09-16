@echo off
setlocal
if "%KNOWLEDGE_VAULT_SERVER%"=="" set "KNOWLEDGE_VAULT_SERVER=http://127.0.0.1:8000"
where py >nul 2>nul
if %errorlevel%==0 (
  py "%~dp0cli.py" --server "%KNOWLEDGE_VAULT_SERVER%" %*
) else (
  python "%~dp0cli.py" --server "%KNOWLEDGE_VAULT_SERVER%" %*
)
endlocal
