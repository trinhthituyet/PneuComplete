@echo off
rem Tat PneuComplete (Windows).
rem
rem Vi sao can tep rieng: ban Docker chay NGAM, dong cua so den khong tat no.
rem Phuong an BOM da dung nam o thu muc data\ nen tat KHONG mat du lieu.

chcp 65001 >nul 2>&1
cd /d "%~dp0"

set DC=docker compose
docker compose version >nul 2>&1
if errorlevel 1 set DC=docker-compose

echo Dang tat PneuComplete...
%DC% down
echo.
echo [OK] Da tat. Du lieu trong thu muc data\ van con nguyen.
echo      Muon dung lai: nhay dup PneuComplete-Docker.bat
echo.
pause
