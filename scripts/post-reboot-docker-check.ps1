$ErrorActionPreference = 'Continue'

try {
  $transcriptPath = Join-Path $env:USERPROFILE 'Desktop\docker-wsl-session.txt'
  Start-Transcript -Path $transcriptPath -Append | Out-Null
} catch {}

Write-Host "Post-reboot Docker verification started: $(Get-Date -Format o)"

# Ensure Docker CLI is on PATH
$dockerBin = Join-Path $Env:ProgramFiles 'Docker\Docker\resources\bin'
if (Test-Path $dockerBin) { $env:Path = "$dockerBin;$env:Path" }

# Launch Docker Desktop if not already running
try {
  if (-not (Get-Process 'Docker Desktop' -ErrorAction SilentlyContinue)) {
    $ddExe = Join-Path $Env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $ddExe) { Start-Process -FilePath $ddExe }
  }
} catch {}

# Wait up to 6 minutes for docker-desktop distros to appear
$deadline = (Get-Date).AddMinutes(6)
$found = $false
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Seconds 5
  $list = & wsl -l -v 2>$null
  if ($LASTEXITCODE -eq 0 -and $null -ne $list) {
    # Avoid inserting NULs by joining as text rather than casting
    $text = ($list -join "`n")
    if ($text -match 'docker-desktop' -and $text -match 'docker-desktop-data') { $found = $true; break }
  }
}

# Collect diagnostics
$lines = @()
$lines += "Timestamp: $(Get-Date -Format o)"
$lines += "Found docker-desktop distros: $found"

# WSL diagnostics
try { $lines += "`nWSL --version:"; $lines += ((& wsl --version 2>&1) | Out-String) } catch { $lines += ("wsl --version error: " + ($_ | Out-String)) }
try { $lines += "`nWSL --status:";  $lines += ((& wsl --status 2>&1)  | Out-String) } catch { $lines += ("wsl --status error: "  + ($_ | Out-String)) }
try { $lines += "`nWSL -l -v:";    $lines += (((& wsl -l -v 2>&1)    | Out-String)) } catch { $lines += ("WSL list error: "     + ($_ | Out-String)) }

# Windows optional features for WSL2
try {
  $features = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux, VirtualMachinePlatform | Select-Object FeatureName, State
  $lines += "`nWindows optional features (WSL):"
  $lines += ($features | Format-Table -AutoSize | Out-String)
} catch { $lines += ("Windows feature query error: " + ($_ | Out-String)) }

# Docker context and versions
try { $lines += "`ndocker context ls:";     $lines += ((& docker context ls 2>&1)     | Out-String) } catch { $lines += ("docker context error: " + ($_ | Out-String)) }
try { $lines += "`ndocker compose version:"; $lines += ((& docker compose version 2>&1) | Out-String) } catch { $lines += ("docker compose error: " + ($_ | Out-String)) }
try { $lines += "`ndocker version:";        $lines += ((& docker version 2>&1)        | Out-String) } catch { $lines += ("docker version error: " + ($_ | Out-String)) }
try { $lines += "`ndocker info:";           $lines += ((& docker info 2>&1)           | Out-String) } catch { $lines += ("docker info error: "    + ($_ | Out-String)) }

# Docker Desktop settings.json snapshot
try {
  $settingsPath = Join-Path $env:APPDATA 'Docker\settings.json'
  $lines += "`nDocker Desktop settings.json: $settingsPath"
  if (Test-Path $settingsPath) {
    $json = Get-Content $settingsPath -Raw -ErrorAction Stop
    try {
      $obj = $json | ConvertFrom-Json -ErrorAction Stop
      $subset = [pscustomobject]@{
        wslEngineEnabled   = $obj.wslEngineEnabled
        kubernetesEnabled  = $obj.kubernetesEnabled
        autoStart          = $obj.autoStart
        wslIntegration     = $obj.wslIntegration
      }
      $lines += ($subset | ConvertTo-Json -Depth 6)
    } catch {
      $lines += "(raw JSON)"
      $lines += $json
    }
  } else {
    $lines += "settings.json not found"
  }
} catch { $lines += ("Docker settings read error: " + ($_ | Out-String)) }

# Named pipes (helps confirm engine pipes present)
try {
  $pipes = [System.IO.Directory]::GetFiles("\\.\pipe\")
  $dockPipes = $pipes | Where-Object { $_ -match 'docker' }
  $lines += "`nNamed pipes matching 'docker' (count=$($dockPipes.Count)):"
  $lines += ($dockPipes | Sort-Object)
} catch { $lines += ("Named pipe enumeration error: " + ($_ | Out-String)) }

# Optional smoke test
if ($found) {
  try {
    $lines += "`ndocker run hello-world:";
    $lines += ((& docker run --rm hello-world 2>&1) | Out-String)
  } catch { $lines += ("hello-world error: " + ($_ | Out-String)) }
}

# Write summary back into repo root
$repoRoot = Split-Path -Parent $PSScriptRoot
$summaryPath = Join-Path $repoRoot 'docker-post-reboot-status.txt'
$lines | Out-File -FilePath $summaryPath -Encoding UTF8 -Force

# Also emit a UTF-8 (no BOM) copy for editors that mis-detect encoding
try {
  $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
  [System.IO.File]::WriteAllText((Join-Path $repoRoot 'docker-post-reboot-status.utf8.txt'), ($lines -join "`r`n"), $utf8NoBom)
} catch {}

try { Stop-Transcript | Out-Null } catch {}

# Clean up Startup stub if used
$startupCmd = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\docker-post-reboot-check.cmd'
if (Test-Path $startupCmd) { Remove-Item $startupCmd -Force -ErrorAction SilentlyContinue }

# Try to include Docker Desktop logs for troubleshooting (best-effort)
try {
  $repoRoot = Split-Path -Parent $PSScriptRoot
  $logOut = @()
  $logOut += "`n--- Docker Desktop Logs (tail) ---"
  $localLog = Join-Path $env:LOCALAPPDATA 'Docker\log.txt'
  if (Test-Path $localLog) {
    $logOut += "`n$localLog (last 200 lines):"
    $logOut += (Get-Content $localLog -Tail 200 -ErrorAction SilentlyContinue)
  }
  $hostLogs = Get-ChildItem -Path (Join-Path $env:APPDATA 'Docker\log') -Recurse -Filter *.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 3
  foreach ($hl in $hostLogs) {
    $logOut += "`n$($hl.FullName) (last 200 lines):"
    $logOut += (Get-Content $hl.FullName -Tail 200 -ErrorAction SilentlyContinue)
  }
  $logsPath = Join-Path $repoRoot 'docker-post-reboot-logs.utf8.txt'
  [System.IO.File]::WriteAllText($logsPath, ($logOut -join "`r`n"), [System.Text.UTF8Encoding]::new($false))
} catch {}
