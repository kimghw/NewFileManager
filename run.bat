@echo off
cd /d "%~dp0"
rem HWPX web editor server - port 8114 (registered in port_manager)
python -m uvicorn app.server:app --host 127.0.0.1 --port 8114
