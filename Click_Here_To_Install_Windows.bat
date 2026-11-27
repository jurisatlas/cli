@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

title JurisAtlas Setup Launcher (Windows)
echo ========================================================================
echo   JurisAtlas v2.0 - Official Legal Sources for Your AI Assistant
echo   Read-Only  ^|  Free (MIT)  ^|  Never touches personal files
echo ========================================================================
echo.

set "JA_ROOT=%LOCALAPPDATA%\JurisAtlas"
set "JA_CLI_DIR=%JA_ROOT%\cli"
set "UV_CACHE_DIR=%JA_ROOT%\uv-cache"
set "SCRIPT_DIR=%~dp0"

if not exist "%JA_CLI_DIR%" mkdir "%JA_CLI_DIR%" >nul 2>&1

set "IN_ZIP_PREVIEW=0"
if /I not "%SCRIPT_DIR:.zip\=%X"=="%SCRIPT_DIR%X" set "IN_ZIP_PREVIEW=1"

set "HAS_LOCAL_BUNDLE=0"
if "%IN_ZIP_PREVIEW%"=="0" if exist "%SCRIPT_DIR%jurisatlas_cli.py" if exist "%SCRIPT_DIR%jurisatlas_i18n.py" set "HAS_LOCAL_BUNDLE=1"

if "%HAS_LOCAL_BUNDLE%"=="1" goto :copy_local
goto :after_copy

:copy_local
copy /Y "%SCRIPT_DIR%jurisatlas_cli.py" "%JA_CLI_DIR%\jurisatlas_cli.py" >nul
if errorlevel 1 goto :copy_fail
copy /Y "%SCRIPT_DIR%jurisatlas_i18n.py" "%JA_CLI_DIR%\jurisatlas_i18n.py" >nul
if errorlevel 1 goto :copy_fail
if exist "%SCRIPT_DIR%pyproject.toml" copy /Y "%SCRIPT_DIR%pyproject.toml" "%JA_CLI_DIR%\pyproject.toml" >nul
goto :after_copy

:copy_fail
echo [ERROR] Could not copy installer files to "%JA_CLI_DIR%".
goto :fail

:after_copy
set "PATH=%USERPROFILE%\.local\bin;%LOCALAPPDATA%\uv;%USERPROFILE%\.cargo\bin;%PATH%"

call :find_uv
if defined UV_EXE goto :have_uv

echo Installing lightweight uv package runner (no admin rights required)...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}; Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1' -UseBasicParsing | Invoke-Expression"
if errorlevel 1 goto :uv_install_fail

set "PATH=%USERPROFILE%\.local\bin;%LOCALAPPDATA%\uv;%USERPROFILE%\.cargo\bin;%PATH%"
call :find_uv
if defined UV_EXE goto :have_uv

echo [ERROR] Could not locate uv.exe after installation.
echo Please visit https://docs.astral.sh/uv/getting-started/installation/ or restart your computer.
goto :fail

:uv_install_fail
echo [ERROR] Failed to install uv package runner. Please check your internet connection or corporate proxy.
goto :fail

:have_uv
echo Preparing isolated Python 3.12 runtime (with GUI support)...
set "MANAGED_PY="
for /f "usebackq delims=" %%P in (`"%UV_EXE%" python find --managed-python 3.12 2^>nul`) do set "MANAGED_PY=%%P"
if defined MANAGED_PY goto :have_py

"%UV_EXE%" python install 3.12
if errorlevel 1 goto :py_install_fail

for /f "usebackq delims=" %%P in (`"%UV_EXE%" python find --managed-python 3.12 2^>nul`) do set "MANAGED_PY=%%P"
if defined MANAGED_PY goto :have_py

echo [ERROR] Managed Python 3.12 executable was not found after installation.
goto :fail

:py_install_fail
echo [ERROR] Failed to download isolated Python 3.12 runtime.
goto :fail

:have_py
echo Launching JurisAtlas Setup Window...
echo.

if "%HAS_LOCAL_BUNDLE%"=="1" goto :run_local
goto :run_remote

:run_local
"%MANAGED_PY%" "%JA_CLI_DIR%\jurisatlas_cli.py" %*
if errorlevel 1 goto :fail
goto :success

:run_remote
call :find_uvx
if not defined UVX_EXE goto :download_cli_zip
echo Fetching latest JurisAtlas Setup Wizard from GitHub...
"%UVX_EXE%" --refresh --python "%MANAGED_PY%" --from https://github.com/jurisatlas/cli/archive/refs/heads/main.zip jurisatlas %*
if errorlevel 1 goto :fail
goto :success

:download_cli_zip
echo Downloading latest JurisAtlas Setup Wizard files from GitHub...
set "CLI_ZIP=%JA_ROOT%\cli.zip"
set "CLI_EXT=%JA_ROOT%\cli_extracted"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12; if (Test-Path -LiteralPath $env:CLI_EXT) { Remove-Item -LiteralPath $env:CLI_EXT -Recurse -Force }; Invoke-WebRequest -Uri 'https://github.com/jurisatlas/cli/archive/refs/heads/main.zip' -OutFile $env:CLI_ZIP -UseBasicParsing; Expand-Archive -LiteralPath $env:CLI_ZIP -DestinationPath $env:CLI_EXT -Force; Remove-Item -LiteralPath $env:CLI_ZIP -Force -ErrorAction SilentlyContinue"
if errorlevel 1 goto :fail

set "BOOT_CLI="
for /d %%D in ("%CLI_EXT%\*") do if exist "%%~fD\jurisatlas_cli.py" set "BOOT_CLI=%%~fD\jurisatlas_cli.py"
if not defined BOOT_CLI goto :fail
"%MANAGED_PY%" "%BOOT_CLI%" %*
if errorlevel 1 goto :fail
goto :success

:success
echo.
echo JurisAtlas Setup finished cleanly.
exit /b 0

:find_uv
set "UV_EXE="
for %%P in ("%USERPROFILE%\.local\bin\uv.exe" "%LOCALAPPDATA%\uv\uv.exe" "%USERPROFILE%\.cargo\bin\uv.exe") do (
    if not defined UV_EXE if exist "%%~P" set "UV_EXE=%%~P"
)
if not defined UV_EXE (
    for /f "delims=" %%P in ('where uv 2^>nul') do (
        if not defined UV_EXE set "UV_EXE=%%P"
    )
)
exit /b 0

:find_uvx
set "UVX_EXE="
for %%P in ("%USERPROFILE%\.local\bin\uvx.exe" "%LOCALAPPDATA%\uv\uvx.exe" "%USERPROFILE%\.cargo\bin\uvx.exe") do (
    if not defined UVX_EXE if exist "%%~P" set "UVX_EXE=%%~P"
)
if not defined UVX_EXE (
    for /f "delims=" %%P in ('where uvx 2^>nul') do (
        if not defined UVX_EXE set "UVX_EXE=%%P"
    )
)
exit /b 0

:fail
echo.
echo ========================================================================
echo   JurisAtlas Setup could not complete. See the message above for help.
echo   Help and troubleshooting: https://jurisatlas.github.io
echo ========================================================================
echo.
pause
exit /b 1
