# window_to_primary_watch.ps1 — 새로 뜨는 창을 주 모니터로 옮기는 상주 감시 (GM 지시 2026-09-07).
# 왜: 크롬·카카오톡·파워셸 등 어떤 앱이든 새 창은 그 앱이 마지막으로 있던 모니터에 뜬다.
#     GM PC 는 서브 모니터(왼쪽 · X<0)에 창이 쌓여 매번 손으로 옮겼다. 앱마다 고치는 대신
#     '처음 나타난 창'만 주 모니터로 옮긴다 — GM 이 일부러 서브로 끌어다 둔 창은 건드리지 않는다.
# 실행: powershell -NoProfile -WindowStyle Hidden -File scripts/window_to_primary_watch.ps1
# 등록: 예약작업 Wellperion-Window-To-Primary (로그온 시) — scripts/open_primary.ps1 과 짝.
# 끄기: 그 예약작업 끝내기(schtasks /end) 또는 powershell 프로세스 종료.

Add-Type -Namespace W -Name Win -MemberDefinition @'
public delegate bool EnumProc(IntPtr h, IntPtr l);
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
[DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
[DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr h);
[DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr h);
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern int GetWindowLong(IntPtr h, int i);
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
public struct RECT { public int L, T, R, B; }
public static System.Collections.Generic.List<IntPtr> All() {
    var l = new System.Collections.Generic.List<IntPtr>();
    EnumWindows((h, p) => { l.Add(h); return true; }, IntPtr.Zero);
    return l;
}
'@
Add-Type -AssemblyName System.Windows.Forms
$GWL_EXSTYLE = -20; $WS_EX_TOOLWINDOW = 0x80
$SWP_NOSIZE = 0x1; $SWP_NOZORDER = 0x4; $SWP_NOACTIVATE = 0x10

function Get-Candidates {
    $prim = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $out = @()
    foreach ($h in [W.Win]::All()) {
        if (-not [W.Win]::IsWindowVisible($h)) { continue }
        if ([W.Win]::GetWindowTextLength($h) -eq 0) { continue }
        if ([W.Win]::IsIconic($h)) { $out += [pscustomobject]@{ H = $h; OnPrimary = $true; W = 0; Ht = 0 }; continue }   # 최소화 창은 기억만(옮기지 않음)
        if (([W.Win]::GetWindowLong($h, $GWL_EXSTYLE) -band $WS_EX_TOOLWINDOW) -ne 0) { continue }
        $r = New-Object W.Win+RECT
        if (-not [W.Win]::GetWindowRect($h, [ref]$r)) { continue }
        $w = $r.R - $r.L; $ht = $r.B - $r.T
        if ($w -lt 200 -or $ht -lt 120) { continue }
        $cx = [int](($r.L + $r.R) / 2); $cy = [int](($r.T + $r.B) / 2)
        $onPrimary = $prim.Contains($cx, $cy) -or ([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Contains($cx, $cy))
        $out += [pscustomobject]@{ H = $h; OnPrimary = $onPrimary; W = $w; Ht = $ht }
    }
    return $out
}

# 처음 훑은 창은 전부 '본 것'으로 — 이미 서브에 있는 창은 그대로 둔다(그건 GM 이 둔 자리일 수 있다).
$seen = New-Object 'System.Collections.Generic.HashSet[long]'
foreach ($c in Get-Candidates) { [void]$seen.Add([long]$c.H) }

while ($true) {
    Start-Sleep -Milliseconds 700
    $prim = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $live = New-Object 'System.Collections.Generic.HashSet[long]'
    foreach ($c in Get-Candidates) {
        [void]$live.Add([long]$c.H)
        if ($seen.Contains([long]$c.H)) { continue }
        [void]$seen.Add([long]$c.H)
        if ($c.OnPrimary) { continue }
        $wasMax = [W.Win]::IsZoomed($c.H)
        if ($wasMax) { [void][W.Win]::ShowWindow($c.H, 9) }   # SW_RESTORE — 최대화 창은 풀어야 옮겨진다
        $w = [Math]::Min($c.W, $prim.Width); $ht = [Math]::Min($c.Ht, $prim.Height)
        $x = $prim.X + [int](($prim.Width - $w) / 2); $y = $prim.Y + [int](($prim.Height - $ht) / 2)
        [void][W.Win]::SetWindowPos($c.H, [IntPtr]::Zero, $x, $y, $w, $ht, ($SWP_NOZORDER -bor $SWP_NOACTIVATE))
        if ($wasMax) { [void][W.Win]::ShowWindow($c.H, 3) }   # SW_MAXIMIZE
        try { Add-Content -Path (Join-Path $PSScriptRoot '..\logs\window_to_primary.log') -Value ("{0} moved hwnd={1} to {2},{3} {4}x{5}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $c.H, $x, $y, $w, $ht) } catch {}
    }
    # 닫힌 창 핸들은 잊는다(핸들 재사용 대비)
    $gone = @($seen | Where-Object { -not $live.Contains($_) })
    foreach ($g in $gone) { [void]$seen.Remove($g) }
}
