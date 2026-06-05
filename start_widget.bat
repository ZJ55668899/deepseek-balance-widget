@echo off
cd /d "D:\×ÀÃæ"
echo Starting...
echo If error, send me the output below.
echo.
"D:\miniforge\python.exe" "D:\×ÀÃæ\ds_balance_widget.py"
echo.
echo Exited code: %errorlevel%
pause
