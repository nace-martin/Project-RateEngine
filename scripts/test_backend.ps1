Param()
$ErrorActionPreference = 'Stop'

Push-Location (Join-Path $PSScriptRoot '..' 'backend')
try {
  if (-not $env:DATABASE_URL) {
    $env:DATABASE_URL = 'postgres://rateengine:rateengine@127.0.0.1:5432/rateengine'
  }

  Write-Host "Running migrations ..."
  python manage.py migrate

  Write-Host "Running tests ..."
  python manage.py test -v 2
} finally {
  Pop-Location
}

