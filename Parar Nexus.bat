@echo off
rem Para o Nexus local: so o processo que escuta na porta 5070 (nao mexe na plataforma 5050 nem em outro Python).
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$c = Get-NetTCPConnection -LocalPort 5070 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if ($c) { Stop-Process -Id $c.OwningProcess -Force; 'Nexus parado.' } else { 'O Nexus ja estava parado.' }"
timeout /t 3 >nul
