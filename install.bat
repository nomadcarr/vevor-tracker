@echo off
echo.
echo ====================================
echo   Vevor Stock Tracker — Инсталация
echo ====================================
echo.

echo [1/2] Инсталиране на Python пакети...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ГРЕШКА: pip install неуспешен.
    pause
    exit /b 1
)

echo.
echo [2/2] Инсталиране на Chromium браузър...
playwright install chromium
if %errorlevel% neq 0 (
    echo ГРЕШКА: playwright install неуспешен.
    pause
    exit /b 1
)

echo.
echo ====================================
echo   Готово! Стартирайте start.bat
echo ====================================
pause
