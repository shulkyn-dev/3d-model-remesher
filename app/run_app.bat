@echo off
rem Запуск мини-приложения 3D Retopo Optimizer (Blender работает скрыто в фоне)
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python gui_app.py
) else (
    py gui_app.py
)
if errorlevel 1 pause
