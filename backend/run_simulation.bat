@echo off
echo ========================================
echo  KampungKonekt - Run Simulation
echo ========================================
echo.
echo This will simulate one week of senior interactions
echo and generate a welfare report.
echo.
echo Press any key to start...
pause >nul
cd /d "%~dp0"
python main.py --simulate
echo.
echo ========================================
echo Simulation complete!
echo Check reports/ folder for welfare reports.
echo ========================================
echo.
pause