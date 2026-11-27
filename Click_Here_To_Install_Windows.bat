@echo off
setlocal EnableExtensions EnableDelayedExpansion
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

if not exist "%JA_CLI_DIR%" (
    mkdir "%JA_CLI_DIR%" >nul 2>&1
)

rem Copy bundled installer files into persistent %LOCALAPPDATA%\JurisAtlas\cli
rem so moving or deleting your Downloads ZIP never breaks setup.
if exist "%~dp0jurisatlas_cli.py" (
    copy /Y "%~dp0jurisatlas_cli.py" "%JA_CLI_DIR%\jurisatlas_cli.py" >nul
    if errorlevel 1 (
        echo [ERROR] Could not copy installer to "%JA_CLI_DIR%".
        goto :fail
    )
    if exist "%~dp0jurisatlas_i18n.py" (
        copy /Y "%~dp0jurisatlas_i18n.py" "%JA_CLI_DIR%\jurisatlas_i18n.py" >nul
    )
    if exist "%~dp0pyproject.toml" (
        copy /Y "%~dp0pyproject.toml" "%JA_CLI_DIR%\pyproject.toml" >nul
    )
)

rem Refresh PATH with standard uv install directories
set "PATH=%USERPROFILE%\.local\bin;%LOCALAPPDATA%\uv;%USERPROFILE%\.cargo\bin;%PATH%"

call :find_uv
if not defined UV_EXE (
    echo Installing lightweight uv package runner ^(no admin rights required^)...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}; Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1' -UseBasicParsing | Invoke-Expression"
    if errorlevel 1 (
        echo [ERROR] Failed to install uv package runner. Please check your internet connection or corporate proxy.
        goto :fail
    )
    set "PATH=%USERPROFILE%\.local\bin;%LOCALAPPDATA%\uv;%USERPROFILE%\.cargo\bin;%PATH%"
    call :find_uv
)

if not defined UV_EXE (
    echo [ERROR] Could not locate uv.exe after installation.
    echo Please visit https://docs.astral.sh/uv/getting-started/installation/ or restart your terminal.
    goto :fail
)

echo Preparing isolated Python 3.12 runtime ^(with GUI support^)...
set "MANAGED_PY="
for /f "usebackq delims=" %%P in (`"%UV_EXE%" python find --managed-python 3.12 2^>nul`) do (
    set "MANAGED_PY=%%P"
)

if not defined MANAGED_PY (
    "%UV_EXE%" python install 3.12
    if errorlevel 1 (
        echo [ERROR] Failed to download isolated Python 3.12 runtime.
        goto :fail
    )
    for /f "usebackq delims=" %%P in (`"%UV_EXE%" python find --managed-python 3.12 2^>nul`) do (
        set "MANAGED_PY=%%P"
    )
)

if not defined MANAGED_PY (
    echo [ERROR] Managed Python 3.12 executable was not found after installation.
    goto :fail
)

echo Launching JurisAtlas Setup Window...
echo.
if exist "%JA_CLI_DIR%\jurisatlas_cli.py" (
    "%MANAGED_PY%" "%JA_CLI_DIR%\jurisatlas_cli.py" %*
    if errorlevel 1 goto :fail
) else (
    call :find_uvx
    if not defined UVX_EXE (
        echo [ERROR] Could not locate uvx.exe and jurisatlas_cli.py was not found next to this launcher.
        echo Tip: Extract the entire ZIP folder before double-clicking this file.
        goto :fail
    )
    "%UVX_EXE%" --python "%MANAGED_PY%" --from https://github.com/jurisatlas/cli/archive/refs/heads/main.zip jurisatlas %*
    if errorlevel 1 goto :fail
)

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
