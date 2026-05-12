@echo off
REM ============================================================
REM  WellCare — one-click retrain.
REM
REM  1. Retrains logreg + GBT on the daily synthetic dataset.
REM     (Test metrics are printed at the end of this step.)
REM  2. Exports model_bundle.js (the file the web app loads).
REM  3. Bumps the service-worker cache version so the browser
REM     picks up the new model on next refresh.
REM
REM  Double-click this file, or run from PowerShell:
REM      .\retrain.bat
REM ============================================================

setlocal enabledelayedexpansion

set ROOT=%~dp0
set MODEL_DIR=%ROOT%outputs - Copy

echo.
echo === [1/3] Training daily model ============================
pushd "%MODEL_DIR%"
python train.py
if errorlevel 1 (
  echo.
  echo X train.py failed. Stopping.
  popd
  exit /b 1
)
popd

echo.
echo === [2/3] Exporting model_bundle.js =======================
pushd "%MODEL_DIR%"
python bundle_to_js.py
if errorlevel 1 (
  echo.
  echo X bundle_to_js.py failed. Stopping.
  popd
  exit /b 1
)
popd

echo.
echo === [3/3] Bumping service-worker cache version ============
REM Use PowerShell for both the timestamp and the in-place edit so
REM this works on modern Windows (wmic is gone on 24H2+). The regex
REM matches any non-quote characters after the "v" so it also fixes
REM previously-broken tokens like v~0,14.
powershell -NoProfile -Command "$now = Get-Date -Format 'yyyyMMddHHmmss'; (Get-Content -Raw '%ROOT%sw.js') -replace \"const CACHE = 'wellcare-checkin-v[^']+';\", \"const CACHE = 'wellcare-checkin-v$now';\" | Set-Content -NoNewline '%ROOT%sw.js'; Write-Host ('Bumped sw.js cache token to v' + $now)"

echo.
echo Done. Now hard-refresh the web app (Ctrl+F5) to pick up the new bundle.
echo (Scroll up to "Test metrics:" above to see the model's ROC-AUC / PR-AUC / Brier.)
echo.
endlocal
