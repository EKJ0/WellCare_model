<#
    make-deploy.ps1

    Builds the `wellcare-deploy/` folder containing exactly the files
    that need to be uploaded to Netlify Drop (or any static host) to
    serve the WellCare burnout check-in PWA.

    Usage (from the project root):
        powershell -ExecutionPolicy Bypass -File .\make-deploy.ps1

    Then drag the resulting `wellcare-deploy` folder onto
    https://app.netlify.com/drop
#>

$ErrorActionPreference = 'Stop'

$root   = $PSScriptRoot
$out    = Join-Path $root 'wellcare-deploy'

$files = @(
    'index.html',
    'checkin-app.html',
    'manifest.webmanifest',
    'sw.js',
    'model_bundle.js'   # optional; warn (don't fail) if missing
)

Write-Host "Building deploy folder at: $out" -ForegroundColor Cyan

if (Test-Path $out) {
    Remove-Item -Recurse -Force $out
}
New-Item -ItemType Directory -Path $out | Out-Null

$missing = @()
foreach ($f in $files) {
    $src = Join-Path $root $f
    if (Test-Path $src) {
        Copy-Item $src -Destination (Join-Path $out $f)
        $size = (Get-Item $src).Length
        $sizeKb = [math]::Round($size / 1KB, 1)
        Write-Host ("  + {0,-25} {1,8} KB" -f $f, $sizeKb) -ForegroundColor Green
    } else {
        $missing += $f
        Write-Host ("  - {0,-25} MISSING" -f $f) -ForegroundColor Yellow
    }
}

if ($missing -contains 'model_bundle.js') {
    Write-Host ""
    Write-Host "Note: model_bundle.js is missing. The app will still work," -ForegroundColor Yellow
    Write-Host "      but users will have to import a model bundle manually." -ForegroundColor Yellow
    Write-Host "      To generate it, run:  python `"outputs - Copy/bundle_to_js.py`"" -ForegroundColor Yellow
}

$critical = $missing | Where-Object { $_ -ne 'model_bundle.js' }
if ($critical.Count -gt 0) {
    Write-Host ""
    Write-Host "ERROR: Critical files are missing: $($critical -join ', ')" -ForegroundColor Red
    exit 1
}

$totalKb = [math]::Round(((Get-ChildItem $out | Measure-Object Length -Sum).Sum / 1KB), 1)
Write-Host ""
Write-Host "Done. Total: $totalKb KB" -ForegroundColor Cyan
Write-Host "Next step: drag the 'wellcare-deploy' folder onto https://app.netlify.com/drop" -ForegroundColor Cyan
