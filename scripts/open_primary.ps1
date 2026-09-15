# open_primary.ps1 — 파일·URL 을 열고 그 창을 주 모니터에 보통 크기로 놓는다 (GM 지시 2026-09-07 · 2026-09-15 최대화 폐지).
# 2026-09-15 GM 「자꾸 전체화면으로 확대돼 불편」 — 최대화를 없앴다. 주 모니터 가운데 · 작업영역의 70% 크기 창.
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
# 창 = 주 모니터 작업영역 전체(최대화). 2026-09-15 13:04 에 70% 가운데로 줄였다가 GM 「부분확대가 되는데?」(17:3x)로 되돌렸다 —
# GM 이 보려고 여는 창은 크게, 사람이 볼 필요 없는 자동화 브라우저만 화면 밖(browser_quiet)이다.
$ww = $prim.Width; $wh = $prim.Height
$wx = $prim.X; $wy = $prim.Y

$incog = $Targets -contains '--incognito'
$items = @($Targets | Where-Object { $_ -ne '--incognito' })
if (-not $items) { Write-Host "열 대상 없음"; exit 1 }

$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
# 경로에 공백·한글이 있으면 인자가 셋으로 쪼개져 깨진 탭 3개가 뜬다(2026-09-07 실사고) — Uri 로 %20 인코딩 + 따옴표.
$urls = @($items | ForEach-Object { if ($_ -match '^[a-z]+://') { $_ } elseif (Test-Path $_) { ([Uri](Resolve-Path $_).Path).AbsoluteUri } else { $_ } })
$quoted = @($urls | ForEach-Object { '"' + $_ + '"' })

$before = [W.U32]::GetForegroundWindow()
if (Test-Path $chrome) {
    $args = @('--new-window', "--window-position=$wx,$wy", "--window-size=$ww,$wh")
    if ($incog) { $args += '--incognito' }
    Start-Process $chrome -ArgumentList ($args + $quoted)
} else {
    foreach ($u in $urls) { Start-Process $u }
}

# 새 창이 앞에 올 때까지 최대 6초 기다렸다가 주 모니터 가운데로 옮긴다(최대화하지 않는다).
$h = [IntPtr]::Zero
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 200
    $f = [W.U32]::GetForegroundWindow()
    if ($f -ne [IntPtr]::Zero -and $f -ne $before) { $h = $f; break }
}
if ($h -eq [IntPtr]::Zero) { $h = [W.U32]::GetForegroundWindow() }
[void][W.U32]::ShowWindow($h, 9)   # SW_RESTORE (최대화 상태면 먼저 풀어야 위치가 먹는다)
[void][W.U32]::SetWindowPos($h, [IntPtr]::Zero, $wx, $wy, $ww, $wh, 0x0040)
[void][W.U32]::ShowWindow($h, 3)   # SW_MAXIMIZE — 주 모니터에 놓은 뒤 최대화
[void][W.U32]::SetForegroundWindow($h)
Write-Host ("opened on primary monitor: " + ($urls -join ' '))
