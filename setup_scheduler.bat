@echo off
echo Настройване на автоматична проверка...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Unregister-ScheduledTask -TaskName 'VevorChecker' -Confirm:$false -ErrorAction SilentlyContinue;" ^
  "$python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source;" ^
  "if (-not $python) { $python = 'C:\Users\User\AppData\Local\Microsoft\WindowsApps\python.exe' };" ^
  "$action = New-ScheduledTaskAction -Execute $python -Argument 'C:\vevor\run.py';" ^
  "$triggers = 6..20 | ForEach-Object { New-ScheduledTaskTrigger -Daily -At \"$($_):00\" };" ^
  "$settings = New-ScheduledTaskSettingsSet -RunOnlyIfNetworkAvailable -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30);" ^
  "$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest;" ^
  "Register-ScheduledTask -TaskName 'VevorChecker' -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Force;" ^
  "Write-Host 'Задачата е регистрирана. Стартирам тест...'"

echo.
echo Тест...
"C:\Users\User\AppData\Local\Microsoft\WindowsApps\python.exe" C:\vevor\run.py
echo Готово. Провери C:\vevor\log.txt
pause
