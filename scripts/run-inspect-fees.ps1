param(
  [string]$RatecardName
)

# Resolve Python from backend virtualenv if present, else fallback to system python
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$venvPython = Join-Path $repoRoot 'backend/.venv/Scripts/python.exe'

if (Test-Path $venvPython) {
  $python = $venvPython
} else {
  Write-Host "Note: backend venv not found; using system 'python'" -ForegroundColor Yellow
  $python = 'python'
}

if ($RatecardName -and $RatecardName.Trim().Length -gt 0) {
  $env:RATECARD_NAME = $RatecardName
}

& $python (Join-Path $repoRoot 'scripts/inspect_fees.py') @args
