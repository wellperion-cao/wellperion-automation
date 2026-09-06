# open_primary.ps1 — 파일·URL 을 열고 그 창을 주 모니터로 옮겨 최대화한다 (GM 지시 2026-09-07).
# 왜: 새 창은 그 앱이 마지막으로 있던 모니터에 뜬다. AI 가 띄우는 파일이 전부 서브 모니터로 가서
#     GM 이 매번 손으로 옮겼다. 여는 자리를 이 한 관문으로 모아 주 모니터(0,0)에 놓는다.
# 사용: powershell -NoProfile -File scripts/open_primary.ps1 <경로 또는 URL> [--incognito]
#       (여러 개면 인자를 이어 적는다 · 크롬으로 열 수 있는 것은 크롬, 나머지는 기본 앱)
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Targets)

Add-Type -Namespace W -Name U32 -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
'@
Add-Type -AssemblyName System.Windows.Forms
$prim = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea

$incog = $Targets -contains '--incognito'
$items = @($Targets | Where-Object { $_ -ne '--incognito' })
if (-not $items) { Write-Host "열 대상 없음"; exit 1 }

$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$urls = @($items | ForEach-Object { if ($_ -match '^[a-z]+://') { $_ } elseif (Test-Path $_) { 'file:///' + ((Resolve-Path $_).Path -replace '\\', '/') } else { $_ } })

$before = [W.U32]::GetForegroundWindow()
if (Test-Path $chrome) {
    $args = @('--new-window', "--window-position=$($prim.X),$($prim.Y)", "--window-size=$($prim.Width),$($prim.Height)")
    if ($incog) { $args += '--incognito' }
    Start-Process $chrome -ArgumentList ($args + $urls)
} else {
    foreach ($u in $urls) { Start-Process $u }
}

# 새 창이 앞에 올 때까지 최대 6초 기다렸다가 주 모니터로 옮기고 최대화한다.
$h = [IntPtr]::Zero
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 200
    $f = [W.U32]::GetForegroundWindow()
    if ($f -ne [IntPtr]::Zero -and $f -ne $before) { $h = $f; break }
}
if ($h -eq [IntPtr]::Zero) { $h = [W.U32]::GetForegroundWindow() }
[void][W.U32]::ShowWindow($h, 9)   # SW_RESTORE (최대화 상태면 먼저 풀어야 위치가 먹는다)
[void][W.U32]::SetWindowPos($h, [IntPtr]::Zero, $prim.X, $prim.Y, $prim.Width, $prim.Height, 0x0040)
[void][W.U32]::ShowWindow($h, 3)   # SW_MAXIMIZE
[void][W.U32]::SetForegroundWindow($h)
Write-Host ("opened on primary monitor: " + ($urls -join ' '))
