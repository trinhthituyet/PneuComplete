@echo off
rem PneuComplete - mo phan mem bang Docker (Windows)
rem
rem Nhay dup tep nay. Khong can cai Python, khong can cai thu vien.
rem Lan dau chay se LAU (5-15 phut) vi Docker phai tai va dung anh.
rem
rem Tep nay khong dung dau tieng Viet: Command Prompt tren nhieu may Windows
rem hien dau tieng Viet thanh ky tu la, doc con kho hon khong dau.

chcp 65001 >nul 2>&1
cd /d "%~dp0"

set PORT=8765
set URL=http://localhost:%PORT%

echo PneuComplete - dung danh sach vat tu khi nen (chay bang Docker)
echo ======================================================================

rem ---------- 1. Co Docker chua? ----------
where docker >nul 2>&1
if errorlevel 1 (
    echo.
    echo   [X] MAY CHUA CO DOCKER DESKTOP
    echo.
    echo   Phan mem nay chay trong Docker nen may can cai Docker Desktop 1 lan.
    echo.
    echo   Cach cai:
    echo     1. Vao  https://www.docker.com/products/docker-desktop
    echo     2. Tai ban cho Windows, cai dat
    echo     3. Khoi dong lai may neu Docker yeu cau
    echo     4. Mo Docker Desktop, cho hinh ca voi o goc phai duoi dung yen
    echo     5. Quay lai nhay dup tep nay lan nua
    echo.
    pause
    exit /b 1
)

rem ---------- 2. Docker da CHAY chua? ----------
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker chua chay - dang thu mo Docker Desktop...
    start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" 2>nul
    echo   cho Docker khoi dong, xin doi...
    for /l %%i in (1,1,60) do (
        timeout /t 2 /nobreak >nul
        docker info >nul 2>&1
        if not errorlevel 1 goto docker_ready
    )
    echo.
    echo   [X] DOCKER DESKTOP CHUA KHOI DONG XONG
    echo.
    echo   Cach sua:
    echo     1. Mo Docker Desktop tu menu Start
    echo     2. Cho toi khi bao "Engine running"
    echo     3. Quay lai nhay dup tep nay lan nua
    echo.
    pause
    exit /b 1
)
:docker_ready

rem ---------- 3. Bat phan mem ----------
set DC=docker compose
docker compose version >nul 2>&1
if errorlevel 1 set DC=docker-compose

echo Dang chuan bi phan mem (lan dau co the mat 5-15 phut, xin cho)...
%DC% up -d --build
if errorlevel 1 (
    echo.
    echo   [X] KHONG DUNG DUOC PHAN MEM
    echo.
    echo   Nguyen nhan thuong gap:
    echo     - May khong vao duoc internet (lan dau can tai Python va PyYAML)
    echo     - Het dung luong o dia - can khoang 1 GB trong
    echo     - Cong ty chan Docker Hub - nho bo phan IT
    echo.
    echo   Hay chup anh TOAN BO cua so nay va gui nguoi phu trach.
    echo.
    pause
    exit /b 1
)

rem ---------- 4. Cho UI tra loi roi moi mo trinh duyet ----------
rem Mo trinh duyet qua som thi nguoi dung thay "khong ket noi duoc" va tuong loi.
rem Dung vong lap nhan thay cho "for /l": bien dat trong "for" can delayed
rem expansion moi doc lai duoc, rat de viet sai.
echo Dang cho phan mem san sang...
set /a TRIES=0
:wait_ui
curl -fs %URL%/api/series >nul 2>&1
if not errorlevel 1 goto ui_ready
set /a TRIES+=1
if %TRIES% GEQ 45 goto ui_timeout
timeout /t 1 /nobreak >nul
goto wait_ui

:ui_timeout
echo.
echo Phan mem chay nhung chua tra loi. Log 30 dong cuoi:
echo ----------------------------------------------------------------------
%DC% logs --tail 30
echo ----------------------------------------------------------------------
echo.
echo Thu mo tay dia chi nay trong trinh duyet: %URL%
echo Neu van khong duoc, chup anh phan log tren gui nguoi phu trach.
echo.
pause
exit /b 1

:ui_ready
start "" %URL%

echo.
echo   [OK] PHAN MEM DANG CHAY
echo.
echo   Dia chi: %URL%   (trinh duyet vua duoc mo)
echo.
echo   Phan mem chay NGAM - dong cua so nay KHONG lam no tat.
echo   Muon tat han: nhay dup tep  Tat-PneuComplete.bat
echo.
echo   Phuong an BOM ban dung duoc luu o thu muc  data\  canh tep nay.
echo   Sao luu thu muc do la sao luu toan bo cong viec cua ban.
echo.
pause
