@echo off
rem ============================================================
rem  Start Deep Work - double-clickable launcher
rem  Elevates itself (one UAC prompt), opens the control panel in
rem  your browser, and runs the app with live logs in this window.
rem ============================================================

rem Work from this file's own folder regardless of launch location -
rem %~dp0 expands to the .bat's drive+path (https://ss64.com/nt/syntax-args.html);
rem main.py expects cwd to hold .env, results/ and logs/.
cd /d "%~dp0"

rem --- self-elevation -----------------------------------------
rem "net session" succeeds only in an elevated console - the classic
rem admin check (https://stackoverflow.com/q/4051883). If not admin,
rem relaunch THIS file with the UAC "runas" verb and exit; the elevated
rem copy re-enters from the top (https://stackoverflow.com/q/1894967).
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator permission for website blocking...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

rem --- dependency check ---------------------------------------
rem "where" searches PATH (https://ss64.com/nt/where.html); a missing uv
rem gets a friendly hint instead of a cryptic crash.
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo uv was not found. Install it from https://docs.astral.sh/uv/ then run this again.
    pause
    exit /b 1
)

rem --- run ----------------------------------------------------
echo Starting Deep Work (logs stream below; closing this window stops the app)...
rem Python owns UI_PORT and opens the browser only after /status responds, so
rem first-time dependency work can take as long as needed without a failed tab.
uv run python main.py --open-browser

rem Keep the window open after exit/crash so the last log lines stay readable.
pause
