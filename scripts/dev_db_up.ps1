Param()
$ErrorActionPreference = 'Stop'

Push-Location (Join-Path $PSScriptRoot '..')
try {
  Write-Host 'Starting Postgres (docker-compose) ...'
  docker compose up -d postgres | Out-Null
  $dbUrl = 'postgres://rateengine:rateengine@127.0.0.1:5432/rateengine'
  Write-Host 'Postgres started. Set in your session:'
  Write-Host "  `$env:DATABASE_URL = '$dbUrl'"
} finally {
  Pop-Location
}

