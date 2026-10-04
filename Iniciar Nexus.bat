@echo off
rem Sobe o Nexus local (http://localhost:5070) com dois cliques e abre o navegador.
rem Se ele ja estiver no ar, so abre o navegador. Roda escondido (pythonw), sem janela, e nao depende de nenhuma
rem sessao do Claude: antes ele caia toda vez que a sessao que o tinha subido fechava (01/10/2026).
rem O log fica em logs\nexus.log. Para parar: Parar Nexus.bat.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$no_ar = $false; try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 5070); $c.Close(); $no_ar = $true } catch {};" ^
  "if (-not $no_ar) {" ^
  "  $py = (Get-Command pythonw -ErrorAction SilentlyContinue).Source;" ^
  "  if (-not $py) { $py = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\pythonw.exe' };" ^
  "  New-Item -ItemType Directory -Force logs | Out-Null;" ^
  "  Start-Process $py -ArgumentList 'app.py' -WorkingDirectory (Get-Location) -WindowStyle Hidden -RedirectStandardError 'logs\nexus.log' -RedirectStandardOutput 'logs\nexus-saida.log';" ^
  "  for ($i = 0; $i -lt 30; $i++) { Start-Sleep -Milliseconds 500; try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 5070); $c.Close(); break } catch {} }" ^
  "};" ^
  "Start-Process 'http://localhost:5070'"
