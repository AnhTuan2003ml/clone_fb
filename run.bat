@echo off
chcp 65001 >nul
setlocal

title Cloudflare Tunnel Auto

echo ==========================
echo START SYSTEM
echo ==========================
echo.

:: CONFIG
set TUNNEL_NAME=metasupport
set DEST_DIR=%~dp0cloudflared

:: CHECK CLOUDFLARED
where cloudflared >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Chua cai cloudflared!
    pause
    exit
)

:: START PYTHON
start "APP" cmd /k "cd /d %~dp0 && python main.py"

timeout /t 5 >nul

:: START TUNNEL
start "TUNNEL" cmd /k "cd /d %DEST_DIR% && cloudflared tunnel --config config.yml run %TUNNEL_NAME%"

echo.
echo DONE - OPEN:
echo https://metasupportnow.com
echo.

pause