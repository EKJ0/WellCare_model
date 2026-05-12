@echo off
REM ============================================================
REM  WellCare - train on REAL check-in data.
REM
REM  Usage:
REM    1. In the web app: Profile -> Export CSV.
REM       (Saved as checkins-YYYY-MM-DD.csv in your Downloads.)
REM    2. Either drag that CSV onto this .bat,
REM       OR double-click this .bat and it will auto-find the
REM       newest checkins-*.csv in Downloads / project root.
REM
REM  What it does:
REM    a) cd into outputs - Copy
REM    b) Train logreg + GBT on your real data, blended with
REM       30 synthetic people so a small dataset still works.
REM    c) Export model_bundle_real.json -> model_bundle.js
REM       so the web app loads it on next refresh.
REM    d) Bump the service-worker cache version.
REM ============================================================

setlocal enabledelayedexpansion

set ROOT=%~dp0
set MODEL_DIR=%ROOT%outputs - Copy

REM ---- 1. Figure out which CSV to use ------------------------
set CSV=
if not "%~1"=="" (
  set CSV=%~1
  echo Using CSV from argument: !CSV!
  goto :have_csv
)

REM Look in project root first.
for /f "delims=" %%F in ('dir /b /o-d "%ROOT%checkins-*.csv" 2^>nul') do (
  set CSV=%ROOT%%%F
  goto :have_csv
)

REM Then in the user's Downloads folder.
for /f "delims=" %%F in ('dir /b /o-d "%USERPROFILE%\Downloads\checkins-*.csv" 2^>nul') do (
  set CSV=%USERPROFILE%\Downloads\%%F
  goto :have_csv
)

echo.
echo X No checkins-*.csv found in project root or Downloads.
echo.
echo   In the web app: Profile -> Export CSV
echo   Then run this script again (or drag the CSV onto it).
echo.
exit /b 1

:have_csv
echo.
echo CSV: %CSV%

REM ---- 2. Train on real data (blended with synthetic) --------
echo.
echo === [1/3] Training on real data ===========================
pushd "%MODEL_DIR%"
python train_real.py --csv "%CSV%" --blend 30 --min-rows 5 --min-positives 0
if errorlevel 1 (
  echo.
  echo X train_real.py failed. Stopping.
  popd
  exit /b 1
)
popd

REM ---- 3. Export the REAL bundle to model_bundle.js ----------
echo.
echo === [2/3] Exporting model_bundle.js =======================
pushd "%MODEL_DIR%"
python bundle_to_js.py --bundle "%MODEL_DIR%\model_bundle_real.json"
if errorlevel 1 (
  echo.
  echo X bundle_to_js.py failed. Stopping.
  popd
  exit /b 1
)
popd

REM ---- 4. Bump SW cache so browser drops the old shell -------
echo.
echo === [3/3] Bumping service-worker cache version ============
REM PowerShell handles both the timestamp and the in-place edit so
REM this works on Windows 11 24H2+ where wmic is gone. The regex
REM matches any non-quote characters after "v" so it also recovers
REM previously-broken tokens.
powershell -NoProfile -Command "$now = Get-Date -Format 'yyyyMMddHHmmss'; (Get-Content -Raw '%ROOT%sw.js') -replace \"const CACHE = 'wellcare-checkin-v[^']+';\", \"const CACHE = 'wellcare-checkin-v$now';\" | Set-Content -NoNewline '%ROOT%sw.js'; Write-Host ('Bumped sw.js cache token to v' + $now)"

echo.
echo Done. Now hard-refresh the web app (Ctrl+F5).
echo.
endlocal
