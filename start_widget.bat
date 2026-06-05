@echo off
cd /d "%~dp0"
echo Starting DeepSeek Balance Widget...
echo.
if not "%1"=="/w" (
    start /min "" pythonw "%~dp0ds_balance_widget.py"
) else (
    python "%~dp0ds_balance_widget.py"
    pause
)
