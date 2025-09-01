[CmdletBinding()]
param(
  [switch]$Install,
  [switch]$Migrate,
  [switch]$Seed,
  [switch]$Run
)

$ErrorActionPreference = 'Stop'

# Move to backend directory
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
Set-Location $backend

# Ensure virtual environment exists
if (-not (Test-Path .venv)) {
  if (Get-Command py -ErrorAction SilentlyContinue) { py -m venv .venv } else { python -m venv .venv }
}

$python = Join-Path .venv 'Scripts/python.exe'
$pip = Join-Path .venv 'Scripts/pip.exe'

# Upgrade pip quietly
& $python -m pip install -q -U pip

# Default behavior: install + migrate + run
$doAll = -not ($Install -or $Migrate -or $Seed -or $Run)
if ($doAll) { $Install=$true; $Migrate=$true; $Run=$true }

if ($Install) { & $pip install -r requirements.txt }
if ($Migrate) { & $python manage.py migrate }
if ($Seed) { & $python manage.py create_test_users }
if ($Run) { & $python manage.py runserver }

