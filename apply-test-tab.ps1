$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

Write-Host '=== 웰페리온 테스트 탭 추가 스크립트 ==='

# git 설치 확인
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'git이 설치되어 있지 않습니다. https://git-scm.com/download/win 에서 설치 후 다시 실행하세요.'
}

# 1) 저장소 준비 (현재 폴더에 없으면 새로 clone)
$repoDir = Join-Path (Get-Location) 'wellperion-automation'
if (-not (Test-Path (Join-Path $repoDir '.git'))) {
    Write-Host '저장소를 내려받는 중...'
    git clone https://github.com/wellperion-cao/wellperion-automation.git
}
Set-Location $repoDir

# 2) 대상 파일 경로
$rel = Join-Path (Join-Path (Join-Path '3. 웰페리온 가이드' 'cpo') 'product') '상품기획.html'
if (-not (Test-Path $rel)) { throw ('파일을 찾을 수 없습니다: ' + $rel) }

# 3) UTF-8로 읽기
$html = [System.IO.File]::ReadAllText($rel, [System.Text.Encoding]::UTF8)

# 4) 줄바꿈 방식 감지
$nl = if ($html -match "`r`n") { "`r`n" } else { "`n" }

# 5) 이미 적용되어 있으면 건너뜀
if ($html.Contains("switchTab('test'")) {
    Write-Host '이미 테스트 탭이 존재합니다. 파일 수정은 건너뜁니다.'
} else {
    # 탭 버튼 추가
    $btnAnchor = 'switchTab(''workshop'',this)"><span class="tab-icon">✏️</span>기획 작업대</button>'
    if (-not $html.Contains($btnAnchor)) { throw '탭 버튼 위치를 찾지 못했습니다.' }
    $btnAdd = $nl + '      <button class="tab-btn" role="tab" onclick="switchTab(''test'',this)"><span class="tab-icon">🧪</span>테스트</button>'
    $html = $html.Replace($btnAnchor, $btnAnchor + $btnAdd)

    # 테스트 패널 추가
    $panelAnchor = '</div><!-- /tab-workshop -->'
    if (-not $html.Contains($panelAnchor)) { throw '탭 패널 위치를 찾지 못했습니다.' }
    $panelLines = @(
        '',
        '',
        '  <!-- ══ TAB: 테스트 ══ -->',
        '  <div id="tab-test" class="tab-panel">',
        '    <div class="section-badge edit">🧪 테스트 — 실험·검토용 작업 공간</div>',
        '    <div class="card">',
        '      <div class="card-title">🧪 테스트 탭</div>',
        '      <p style="line-height:1.7;color:var(--dim-mid);margin:0;">기획 작업대 옆에 새로 만든 테스트 탭입니다. 여기에 실험할 내용이나 검토할 항목을 채워 넣으면 됩니다.</p>',
        '    </div>',
        '  </div><!-- /tab-test -->'
    )
    $panelAdd = ($panelLines -join $nl)
    $html = $html.Replace($panelAnchor, $panelAnchor + $panelAdd)

    # 6) UTF-8(BOM 없음)로 저장
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($rel, $html, $utf8)
    Write-Host '파일 수정 완료.'
}

# 7) 커밋 정보 없으면 설정
if (-not (git config user.email)) {
    git config user.email 'info@wellperion.com'
    git config user.name 'wellperion'
}

# 8) 커밋 & 푸시 (메시지는 인코딩 안전을 위해 영문)
git add -A
git commit -m "Add test tab next to planning workbench"
git push origin master

Write-Host ''
Write-Host '=== 완료! 잠시 후 GitHub Pages 자동 배포가 실행됩니다. ==='
Write-Host '몇 분 뒤 페이지를 새로고침하면 테스트 탭이 보입니다.'
