Write-Host "🔍 Running Gitleaks pre-push secret scan..."

# Run gitleaks in protect mode
gitleaks detect --source . --no-banner

# Check if gitleaks returned a non-zero exit (i.e. found secrets)
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Gitleaks found potential secrets in this push."
    exit 1
} else {
    Write-Host "✅ No secrets found. Safe to push!"
}
