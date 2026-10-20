@echo off
setlocal
cd /d "%~dp0"

echo Installing the exact statsmodels version used by the ES expected values...
python -m pip uninstall -y statsmodels
python -m pip install statsmodels==0.14.6
if errorlevel 1 (
    echo.
    echo ERROR: statsmodels 0.14.6 installation failed.
    pause
    exit /b 1
)

echo.
echo statsmodels 0.14.6 installed successfully.
echo Restart Odoo and upgrade spreadsheet_dashboard_sale_enhancements_withAI.
pause
