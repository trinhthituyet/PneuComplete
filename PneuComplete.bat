@echo off
REM Nhay dup tep nay de mo PneuComplete (Windows).
cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel%==0 (
  python start.py
  goto :eof
)
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 start.py
  goto :eof
)

echo.
echo   [X] May chua cai Python.
echo.
echo   PneuComplete can Python 3.10 tro len.
echo   Cach cai: mo python.org - Downloads - tai ban cho Windows,
echo   khi cai NHO TICH vao o "Add Python to PATH".
echo   Cai xong mo lai tep PneuComplete.bat nay.
echo.
pause
