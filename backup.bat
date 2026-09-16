@echo off
cd /d "%~dp0"
uv run python -c "import sqlite3; from pathlib import Path; from datetime import datetime; p=Path('data'); p.mkdir(exist_ok=True); (p/'backup').mkdir(exist_ok=True); s=sqlite3.connect(p/'knowledge.db'); t=p/'backup'/f'knowledge_{datetime.now():%%Y%%m%%d_%%H%%M%%S}.db'; d=sqlite3.connect(t); s.backup(d); d.close(); s.close(); print(f'Backup: {t}')"
pause
