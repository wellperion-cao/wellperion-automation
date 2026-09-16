# Open the live AWS PostgreSQL (erp) in Chrome via pgweb, read-only, through an SSH tunnel.
# - No server change. DB password is fetched over SSH at runtime and never written to disk here.
# - Usage: powershell -NoProfile -File ops/pgweb/open_db.ps1
$ErrorActionPreference = "Stop"
$Key  = "$env:USERPROFILE\.aws\wellperion-sito.pem"
$Host_ = "ec2-user@15.164.151.105"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Exe  = Join-Path $Here "pgweb.exe"
$Port = 15432
$Web  = 8081

# 1) read-only connection string from the server (masked in logs)
$url = ssh -i $Key -o StrictHostKeyChecking=accept-new $Host_ "sudo grep '^ERP_DB_URL_RO=' /srv/erp/db.env | cut -d= -f2-"
if (-not $url) { throw "ERP_DB_URL_RO not found on server" }
$url = $url.Trim() -replace '@127\.0\.0\.1/', "@127.0.0.1:$Port/"
if ($url -notmatch 'sslmode=') { $url = $url + "?sslmode=disable" }

# 2) SSH tunnel (skip if already listening)
$tunListen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $tunListen) {
  Start-Process -WindowStyle Hidden ssh -ArgumentList @("-i", $Key, "-o", "StrictHostKeyChecking=accept-new", "-N", "-L", "$Port`:127.0.0.1:5432", $Host_)
  Start-Sleep -Seconds 3
}

# 3) pgweb read-only (skip if already listening)
$webListen = Get-NetTCPConnection -LocalPort $Web -State Listen -ErrorAction SilentlyContinue
if (-not $webListen) {
  $env:PGWEB_DATABASE_URL = $url
  Start-Process -WindowStyle Hidden $Exe -ArgumentList @("--readonly", "--listen", "$Web", "--bind", "127.0.0.1", "--skip-open")
  Start-Sleep -Seconds 3
}

# 4) show it
& powershell -NoProfile -File (Join-Path (Split-Path -Parent (Split-Path -Parent $Here)) "scripts\open_primary.ps1") "http://127.0.0.1:$Web/"
Write-Output "pgweb read-only at http://127.0.0.1:$Web/ (tunnel 127.0.0.1:$Port -> server 5432)"
