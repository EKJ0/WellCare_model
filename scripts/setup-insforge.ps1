# Run from repo root:  pwsh -File scripts\setup-insforge.ps1
# Do NOT commit secrets. Set your key only in the shell session:
#   $env:INSFORGE_USER_API_KEY = 'uak_...'

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $env:INSFORGE_USER_API_KEY) {
  Write-Host 'Set INSFORGE_USER_API_KEY to your InsForge user API key, then re-run.' -ForegroundColor Yellow
  exit 1
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$projectId = '1228b30a-2f07-4905-b4d7-ee7258ea5705'

Write-Host 'Logging in...' -ForegroundColor Cyan
npx --yes @insforge/cli@latest login --user-api-key $env:INSFORGE_USER_API_KEY

Write-Host 'Linking project (installs agent skills per InsForge CLI)...' -ForegroundColor Cyan
# Official README: non-interactive link may require --org-id; if this fails, run:
#   npx @insforge/cli list --json
# and pass --org-id <your-org-id> below.
npx --yes @insforge/cli@latest link --project-id $projectId -y

Write-Host 'Current context:' -ForegroundColor Cyan
npx --yes @insforge/cli@latest current --json

Write-Host 'Done. Add .insforge/ only via local link — it is gitignored.' -ForegroundColor Green
