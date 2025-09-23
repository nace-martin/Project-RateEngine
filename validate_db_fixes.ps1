# Validate RateEngine v2 DB Fixes
# PowerShell version of the validation script

Write-Host "=== Validating RateEngine v2 DB Fixes ==="

# Check if DATABASE_URL is set
if (-not $env:DATABASE_URL) {
    Write-Host "DATABASE_URL is not set. Please set it to your PostgreSQL database connection string."
    exit 1
}

Write-Host "Running verification script..."
psql $env:DATABASE_URL -f verify_db_reform_v2.sql

Write-Host "=== Validation Complete ==="