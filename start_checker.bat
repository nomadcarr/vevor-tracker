@echo off
title Vevor Stock Checker
cd /d "d:\системи за проверки на стоки и веворски пратки"

:loop
echo.
echo ============================================
echo   Стартиране на проверка: %date% %time%
echo ============================================
python local_checker.py
echo.
echo Следваща проверка след 1 час...
echo Не затваряй този прозорец!
timeout /t 3600 /nobreak
goto loop
