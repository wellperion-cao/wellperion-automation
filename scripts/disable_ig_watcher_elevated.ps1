# IG 폴링 감시기 영구 비활성 + 상주 프로세스 종료 (관리자 권한 실행)
# 발행 엔진 스크립트(ig_review_publish_watcher.py)는 보존 — 봇이 --once로 on-demand 호출.
$log = "C:\Users\jjky0\welperion-automation\logs\ig_watcher_disable.log"
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"=== $ts IG 폴링 감시기 비활성 ===" | Out-File -FilePath $log -Encoding utf8

# [1] 예약작업 비활성 (Disable — 가역적, 삭제 아님)
try {
    Disable-ScheduledTask -TaskName "Wellperion-IG-Publish-Watcher" -ErrorAction Stop | Out-Null
    "[1] Disable-ScheduledTask: OK" | Out-File -FilePath $log -Append -Encoding utf8
} catch {
    "[1] Disable 실패: $($_.Exception.Message)" | Out-File -FilePath $log -Append -Encoding utf8
}

# [2] 상주 워처 프로세스만 식별·종료 (bot.py·daily_scheduler 보호)
$killed = @()
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ForEach-Object {
    if ($_.CommandLine -and $_.CommandLine -match 'ig_review_publish_watcher') {
        try { Stop-Process -Id $_.ProcessId -Force; $killed += $_.ProcessId } catch {}
    }
}
"[2] 종료한 워처 PID: $($killed -join ', ')" | Out-File -FilePath $log -Append -Encoding utf8

# [3] 최종 상태
$st = (Get-ScheduledTask -TaskName "Wellperion-IG-Publish-Watcher").State
"[3] 예약작업 State: $st" | Out-File -FilePath $log -Append -Encoding utf8
$remain = (Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'ig_review_publish_watcher' }).Count
"[3] 잔존 워처 프로세스: $remain" | Out-File -FilePath $log -Append -Encoding utf8
