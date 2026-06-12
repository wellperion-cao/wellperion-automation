# -*- coding: utf-8 -*-
"""운영부 체계.html 생성 스크립트"""
import sys, os

BASE = r'C:\Users\jjky0\welperion-automation\3. 웰페리온 가이드\coo\check'
SRC  = os.path.join(BASE, '주차관리부 체계.html')
DEST = os.path.join(BASE, '운영부 체계.html')

with open(SRC, encoding='utf-8') as f:
    src = f.read()

# ── 1. title
src = src.replace('<title>웰페리온 주차관리부 체계</title>',
                  '<title>웰페리온 운영부 체계</title>', 1)

# ── 2. h1
src = src.replace(
    '<h1>주차관리부 체계 <span style="font-size:11px;font-weight:500;color:var(--dim);margin-left:8px;letter-spacing:0.02em;">v1.0 · 2026-06-08</span> <span id="dayType"></span></h1>',
    '<h1>운영부 체계 <span style="font-size:11px;font-weight:500;color:var(--dim);margin-left:8px;letter-spacing:0.02em;">v1.0 · 2026-06-08</span> <span id="dayType"></span></h1>',
    1)

# ── 3. 탭 버튼 (주차관리부 규정 → 운영부 규정 + VOC 탭 추가)
old_tabs = """<button class="tab active" onclick="switchTab('policy')">주차관리부 규정</button>
  <button class="tab" onclick="switchTab('guide')">가이드</button>
  <button class="tab" onclick="switchTab('manual')">매뉴얼</button>
  <button class="tab" onclick="switchTab('check-m','lock')">점검(지상) 🔒</button>
  <button class="tab" onclick="switchTab('check-f','lock')">점검(지하) 🔒</button>"""
new_tabs = """<button class="tab active" onclick="switchTab('policy')">운영부 규정</button>
  <button class="tab" onclick="switchTab('voc')">VOC 이슈 접수</button>
  <button class="tab" onclick="switchTab('guide')">가이드</button>
  <button class="tab" onclick="switchTab('manual')">매뉴얼</button>
  <button class="tab" onclick="switchTab('check-m','lock')">점검(오전) 🔒</button>
  <button class="tab" onclick="switchTab('check-f','lock')">점검(오후) 🔒</button>"""
assert old_tabs in src, 'tabs not found'
src = src.replace(old_tabs, new_tabs, 1)

# ── 4. policy 탭 전체 교체
old_p_start = '<div id="tab-policy" class="content">'
old_p_end   = "<!-- 고도화 정의·개선 로드맵은 관리자 영역(웰페리온 ERP O1 운영 통합 체계 '구축 가이드')으로 이관 (2026-06-06 GM: 현장 규정 탭엔 뜬금없음) -->\n</div>"
assert old_p_start in src, 'policy start'
assert old_p_end   in src, 'policy end'
i1 = src.index(old_p_start)
i2 = src.index(old_p_end) + len(old_p_end)

new_policy = r"""<div id="tab-policy" class="content">
  <h2 style="font-size:20px;margin-bottom:6px;">운영부 규정</h2>
  <p style="font-size:13px;color:var(--dim);margin-bottom:14px;line-height:1.6;">주제별 칸(컬럼)에 규정·회의를 카드로 정리했습니다. 각 카드의 <b>편집</b> 버튼으로 내용을 바로 수정·저장하면 모든 기기에 반영됩니다. <span style="color:var(--accent);">운영시간 등 공식값은 임의 변경 금지.</span></p>
  <div class="board-fullwidth" style="display:flex;gap:14px;align-items:flex-start;">
    <div id="policy-board" class="board-scroll" style="flex:0 0 auto;min-width:0;max-width:calc(100% - 694px);"></div>
    <div class="manual-section" style="flex:0 0 680px;width:680px;margin-top:0;border-left:4px solid var(--red);align-self:flex-start;">
    <div class="manual-header" onclick="togManual(this)">
      <h3 style="color:var(--red);">⏱ 근무·휴게 시간</h3><span class="arrow">&#9654;</span>
    </div>
    <div class="manual-body">
  <div style="background:var(--red-bg);border:2px solid rgba(237,91,63,0.5);border-radius:12px;padding:16px 18px;margin-bottom:16px;">
    <p style="font-size:16px;font-weight:800;color:var(--red);margin:0 0 6px;">⚠ 리셉션을 절대 비우지 않는다</p>
    <p style="font-size:14px;font-weight:600;color:var(--text);margin:0;line-height:1.7;">리셉션·프론트에는 항상 최소 1명이 자리를 지킵니다.<br>
    2인 이상 근무 시 <strong>휴게를 반드시 엇갈려</strong> 진행하고, 한 명이 쉬는 동안 나머지 한 명은 리셉션을 지킵니다.</p>
  </div>
  <p style="font-size:14px;font-weight:700;color:var(--accent);margin:0 0 8px;">2인 동시 근무 — 교대 휴게 규칙</p>
  <div style="background:var(--paper);border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin-bottom:12px;">
    <p style="font-size:12px;color:var(--dim);margin:0 0 10px;">매 시간(정시~정시) 기준 — 10분 단위 엇갈림</p>
    <div style="margin-bottom:8px;">
      <div style="font-size:12px;font-weight:700;color:var(--accent);margin-bottom:4px;">근무자 A</div>
      <div style="display:flex;height:22px;border-radius:6px;overflow:hidden;font-size:11px;font-weight:700;">
        <div style="flex:5;background:var(--accent);color:#fff;display:flex;align-items:center;justify-content:center;">근무 (정시~50분)</div>
        <div style="flex:1;background:var(--red);color:#fff;display:flex;align-items:center;justify-content:center;">휴게</div>
      </div>
    </div>
    <div>
      <div style="font-size:12px;font-weight:700;color:var(--green);margin-bottom:4px;">근무자 B</div>
      <div style="display:flex;height:22px;border-radius:6px;overflow:hidden;font-size:11px;font-weight:700;">
        <div style="flex:1;background:var(--red);color:#fff;display:flex;align-items:center;justify-content:center;">휴게</div>
        <div style="flex:5;background:var(--green);color:#fff;display:flex;align-items:center;justify-content:center;">근무 (10분~정시)</div>
      </div>
    </div>
    <p style="font-size:12px;color:var(--dim);margin:10px 0 0;">→ A·B 휴게가 겹치지 않아 리셉션이 항상 1명 이상 커버됩니다.</p>
  </div>
  <table style="width:100%;border-collapse:collapse;margin-bottom:8px;font-size:13px;">
    <tr style="background:var(--paper);">
      <th style="padding:10px;border:1px solid var(--border);width:90px;">구분</th>
      <th style="padding:10px;border:1px solid var(--border);">근무</th>
      <th style="padding:10px;border:1px solid var(--border);">휴게</th>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid var(--border);font-weight:700;color:var(--accent);">근무자 A</td>
      <td style="padding:8px;border:1px solid var(--border);">정시 ~ 50분</td>
      <td style="padding:8px;border:1px solid var(--border);">50분 ~ 정시 <span style="font-size:11px;color:var(--dim);">(매시 끝 10분)</span></td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid var(--border);font-weight:700;color:var(--green);">근무자 B</td>
      <td style="padding:8px;border:1px solid var(--border);">10분 ~ 정시</td>
      <td style="padding:8px;border:1px solid var(--border);">정시 ~ 10분 <span style="font-size:11px;color:var(--dim);">(매시 처음 10분)</span></td>
    </tr>
  </table>
  <p style="font-size:12px;color:var(--dim);margin:0 0 4px;">※ 위는 2인 동시 근무 시 적용하는 <strong>원칙(예시)</strong>입니다 · 1인 근무·3인 이상 케이스는 GM 추후 지정 예정</p>
  <p style="font-size:14px;font-weight:700;color:var(--accent);margin:18px 0 8px;">실제 운영 근무조</p>
  <table style="width:100%;border-collapse:collapse;margin-bottom:10px;font-size:13px;">
    <tr style="background:var(--paper);">
      <th style="padding:10px;border:1px solid var(--border);width:64px;">근무조</th>
      <th style="padding:10px;border:1px solid var(--border);">담당</th>
      <th style="padding:10px;border:1px solid var(--border);width:120px;">근무시간</th>
      <th style="padding:10px;border:1px solid var(--border);">고정 휴게(10분)</th>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid var(--border);font-weight:700;color:var(--accent);">오전</td>
      <td style="padding:8px;border:1px solid var(--border);">이경연 실장</td>
      <td style="padding:8px;border:1px solid var(--border);color:var(--dim);white-space:nowrap;">미정</td>
      <td style="padding:8px;border:1px solid var(--border);color:var(--dim);">미정</td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid var(--border);font-weight:700;color:var(--green);">오후</td>
      <td style="padding:8px;border:1px solid var(--border);color:var(--dim);">충원 예정</td>
      <td style="padding:8px;border:1px solid var(--border);color:var(--dim);white-space:nowrap;">미정</td>
      <td style="padding:8px;border:1px solid var(--border);color:var(--dim);">미정</td>
    </tr>
  </table>
  <p style="font-size:12px;color:var(--dim);margin:0 0 4px;line-height:1.6;">※ 근무시간·담당자는 임의로 채우지 않고, GM 확정 후 갱신합니다.</p>
    </div>
  </div>
  </div>
</div>"""

src = src[:i1] + new_policy + src[i2:]
print('policy replaced, len=', len(src))

# ── 5. VOC 탭 (tab-guide 앞에 삽입)
voc_tab = """<div id="tab-voc" class="content hidden">
  <h2 style="font-size:20px;margin-bottom:6px;">VOC 이슈 접수 · 처리 체계</h2>
  <p style="font-size:13px;color:var(--dim);margin-bottom:18px;line-height:1.6;">회원 건의(VOC)는 접수 직원이 구글 폼에 기록 → 장소·부서 분류 → 해당 부서 전달 → 처리·완료. 접수·응답 현황은 이슈 응답 시트에서 확인합니다.</p>

  <div style="display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap;">
    <a href="https://docs.google.com/forms/d/e/1FAIpQLSd7mDzTyZT5FSXVcxmpMCaqv7M-RR3EmEu2lFqGRksUE77osA/viewform" target="_blank"
       style="flex:1;min-width:200px;display:flex;align-items:center;justify-content:center;gap:8px;padding:14px 18px;background:var(--green-bg);color:var(--green);border:1.5px solid rgba(106,191,123,0.4);border-radius:12px;font-size:14px;font-weight:700;text-decoration:none;">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm-1 1.5L18.5 9H13V3.5zM6 20V4h5v7h7v9H6z"/></svg>
      이슈 접수하기 (VOC 폼)
    </a>
    <a href="https://docs.google.com/spreadsheets/d/1akZLs7ITs3FZWFIzMQvSYrdRucGQglmerOvTC2TLEcQ/edit?gid=1576318230" target="_blank"
       style="flex:1;min-width:200px;display:flex;align-items:center;justify-content:center;gap:8px;padding:14px 18px;background:var(--blue-bg);color:var(--blue);border:1.5px solid rgba(91,159,213,0.4);border-radius:12px;font-size:14px;font-weight:700;text-decoration:none;">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M3 3h18v18H3V3zm2 2v14h14V5H5zm2 2h10v2H7V7zm0 4h10v2H7v-2zm0 4h7v2H7v-2z"/></svg>
      이슈 응답 시트 보기
    </a>
  </div>

  <!-- 처리 흐름도 -->
  <div style="background:var(--paper);border:1px solid var(--border);border-radius:12px;padding:16px 18px;margin-bottom:18px;">
    <p style="font-size:15px;font-weight:700;color:var(--accent);margin:0 0 14px;">처리 흐름도</p>
    <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;">
      <div style="background:var(--green-bg);border:1.5px solid rgba(106,191,123,0.4);border-radius:10px;padding:10px 14px;text-align:center;min-width:90px;">
        <div style="font-size:18px;margin-bottom:4px;">🙋</div>
        <div style="font-size:12px;font-weight:700;color:var(--green);">회원 건의</div>
      </div>
      <div style="font-size:20px;color:var(--dim);">→</div>
      <div style="background:var(--accent-bg);border:1.5px solid rgba(183,159,138,0.4);border-radius:10px;padding:10px 14px;text-align:center;min-width:90px;">
        <div style="font-size:18px;margin-bottom:4px;">📝</div>
        <div style="font-size:12px;font-weight:700;color:var(--accent);">직원 접수<br><span style="font-size:11px;font-weight:500;">(폼 기록)</span></div>
      </div>
      <div style="font-size:20px;color:var(--dim);">→</div>
      <div style="background:var(--yellow-bg);border:1.5px solid rgba(230,200,78,0.4);border-radius:10px;padding:10px 14px;text-align:center;min-width:90px;">
        <div style="font-size:18px;margin-bottom:4px;">🗂️</div>
        <div style="font-size:12px;font-weight:700;color:var(--yellow);">장소·부서<br>분류</div>
      </div>
      <div style="font-size:20px;color:var(--dim);">→</div>
      <div style="background:var(--blue-bg);border:1.5px solid rgba(91,159,213,0.4);border-radius:10px;padding:10px 14px;text-align:center;min-width:90px;">
        <div style="font-size:18px;margin-bottom:4px;">📨</div>
        <div style="font-size:12px;font-weight:700;color:var(--blue);">해당 부서<br>전달</div>
      </div>
      <div style="font-size:20px;color:var(--dim);">→</div>
      <div style="background:var(--purple-bg);border:1.5px solid rgba(167,139,218,0.4);border-radius:10px;padding:10px 14px;text-align:center;min-width:90px;">
        <div style="font-size:18px;margin-bottom:4px;">🔧</div>
        <div style="font-size:12px;font-weight:700;color:var(--purple);">처리</div>
      </div>
      <div style="font-size:20px;color:var(--dim);">→</div>
      <div style="background:var(--green-bg);border:1.5px solid rgba(106,191,123,0.4);border-radius:10px;padding:10px 14px;text-align:center;min-width:90px;">
        <div style="font-size:18px;margin-bottom:4px;">✅</div>
        <div style="font-size:12px;font-weight:700;color:var(--green);">완료/회신</div>
      </div>
    </div>
  </div>

  <!-- VOC 폼 입력 항목 -->
  <div style="background:var(--paper);border:1px solid var(--border);border-radius:12px;padding:16px 18px;margin-bottom:14px;">
    <p style="font-size:15px;font-weight:700;color:var(--accent);margin:0 0 12px;">VOC 폼 입력 항목</p>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <tr style="background:var(--bg);">
        <th style="padding:9px 12px;border:1px solid var(--border);color:var(--accent);font-weight:700;width:160px;">항목</th>
        <th style="padding:9px 12px;border:1px solid var(--border);color:var(--accent);font-weight:700;">내용</th>
        <th style="padding:9px 12px;border:1px solid var(--border);color:var(--accent);font-weight:700;width:60px;">필수</th>
      </tr>
      <tr><td style="padding:8px 12px;border:1px solid var(--border);">직원 &amp; 회원명</td><td style="padding:8px 12px;border:1px solid var(--border);color:var(--dim);">접수한 직원 이름 + 건의한 회원 이름</td><td style="padding:8px 12px;border:1px solid var(--border);text-align:center;color:var(--red);font-weight:700;">*</td></tr>
      <tr><td style="padding:8px 12px;border:1px solid var(--border);">연락처</td><td style="padding:8px 12px;border:1px solid var(--border);color:var(--dim);">회원 연락처 (선택)</td><td style="padding:8px 12px;border:1px solid var(--border);text-align:center;color:var(--dim);">-</td></tr>
      <tr><td style="padding:8px 12px;border:1px solid var(--border);">이슈 내용</td><td style="padding:8px 12px;border:1px solid var(--border);color:var(--dim);">불편 사항·건의 내용 상세 기술</td><td style="padding:8px 12px;border:1px solid var(--border);text-align:center;color:var(--red);font-weight:700;">*</td></tr>
      <tr><td style="padding:8px 12px;border:1px solid var(--border);">불편했던 장소</td><td style="padding:8px 12px;border:1px solid var(--border);color:var(--dim);">해당 장소 복수 선택 (14개 분류)</td><td style="padding:8px 12px;border:1px solid var(--border);text-align:center;color:var(--red);font-weight:700;">*</td></tr>
      <tr><td style="padding:8px 12px;border:1px solid var(--border);">접수자</td><td style="padding:8px 12px;border:1px solid var(--border);color:var(--dim);">폼을 기록한 직원 이름</td><td style="padding:8px 12px;border:1px solid var(--border);text-align:center;color:var(--red);font-weight:700;">*</td></tr>
      <tr><td style="padding:8px 12px;border:1px solid var(--border);">전달 부서</td><td style="padding:8px 12px;border:1px solid var(--border);color:var(--dim);">처리 담당 부서 선택 (11개 분류)</td><td style="padding:8px 12px;border:1px solid var(--border);text-align:center;color:var(--red);font-weight:700;">*</td></tr>
    </table>
    <p style="font-size:12px;color:var(--dim);margin:8px 0 0;">* 표시 항목은 필수 입력</p>
  </div>

  <!-- 불편 장소 분류 14 -->
  <div style="background:var(--paper);border:1px solid var(--border);border-radius:12px;padding:16px 18px;margin-bottom:14px;">
    <p style="font-size:15px;font-weight:700;color:var(--accent);margin:0 0 10px;">불편 장소 분류 <span style="font-size:13px;font-weight:500;color:var(--dim);">(복수 선택 · 14개)</span></p>
    <div style="display:flex;flex-wrap:wrap;gap:7px;">
      <span style="display:inline-block;padding:5px 12px;background:var(--accent-bg);color:var(--accent);border-radius:20px;font-size:13px;font-weight:600;">카페</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--accent-bg);color:var(--accent);border-radius:20px;font-size:13px;font-weight:600;">운영부</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--accent-bg);color:var(--accent);border-radius:20px;font-size:13px;font-weight:600;">프론트</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--accent-bg);color:var(--accent);border-radius:20px;font-size:13px;font-weight:600;">주차장</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--accent-bg);color:var(--accent);border-radius:20px;font-size:13px;font-weight:600;">사우나</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--accent-bg);color:var(--accent);border-radius:20px;font-size:13px;font-weight:600;">헬스장</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--accent-bg);color:var(--accent);border-radius:20px;font-size:13px;font-weight:600;">필라테스룸</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--accent-bg);color:var(--accent);border-radius:20px;font-size:13px;font-weight:600;">G.X룸</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--accent-bg);color:var(--accent);border-radius:20px;font-size:13px;font-weight:600;">골프장</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--accent-bg);color:var(--accent);border-radius:20px;font-size:13px;font-weight:600;">수영장</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--accent-bg);color:var(--accent);border-radius:20px;font-size:13px;font-weight:600;">스쿼시장</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--accent-bg);color:var(--accent);border-radius:20px;font-size:13px;font-weight:600;">뮤지컬룸</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--accent-bg);color:var(--accent);border-radius:20px;font-size:13px;font-weight:600;">키즈샤워실</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--accent-bg);color:var(--accent);border-radius:20px;font-size:13px;font-weight:600;">본에스티스</span>
    </div>
  </div>

  <!-- 전달 부서 분류 11 -->
  <div style="background:var(--paper);border:1px solid var(--border);border-radius:12px;padding:16px 18px;">
    <p style="font-size:15px;font-weight:700;color:var(--accent);margin:0 0 10px;">전달 부서 분류 <span style="font-size:13px;font-weight:500;color:var(--dim);">(11개)</span></p>
    <div style="display:flex;flex-wrap:wrap;gap:7px;">
      <span style="display:inline-block;padding:5px 12px;background:var(--blue-bg);color:var(--blue);border-radius:20px;font-size:13px;font-weight:600;">운영</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--blue-bg);color:var(--blue);border-radius:20px;font-size:13px;font-weight:600;">관리</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--blue-bg);color:var(--blue);border-radius:20px;font-size:13px;font-weight:600;">시설</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--blue-bg);color:var(--blue);border-radius:20px;font-size:13px;font-weight:600;">지원</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--blue-bg);color:var(--blue);border-radius:20px;font-size:13px;font-weight:600;">P.T</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--blue-bg);color:var(--blue);border-radius:20px;font-size:13px;font-weight:600;">필라테스</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--blue-bg);color:var(--blue);border-radius:20px;font-size:13px;font-weight:600;">수영</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--blue-bg);color:var(--blue);border-radius:20px;font-size:13px;font-weight:600;">골프</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--blue-bg);color:var(--blue);border-radius:20px;font-size:13px;font-weight:600;">스쿼시</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--blue-bg);color:var(--blue);border-radius:20px;font-size:13px;font-weight:600;">체조&amp;트램폴린</span>
      <span style="display:inline-block;padding:5px 12px;background:var(--blue-bg);color:var(--blue);border-radius:20px;font-size:13px;font-weight:600;">기타</span>
    </div>
  </div>
</div>

"""

assert '<div id="tab-guide" class="content hidden">' in src
src = src.replace('<div id="tab-guide" class="content hidden">',
                  voc_tab + '<div id="tab-guide" class="content hidden">', 1)
print('voc tab inserted, len=', len(src))

# ── 6. 가이드 탭 내용 — 주차 관련 내용을 운영부 리셉션 내용으로 교체
# h2 제목
src = src.replace(
    '<h2 style="font-size:20px;margin-bottom:16px;">가이드</h2>',
    '<h2 style="font-size:20px;margin-bottom:16px;">가이드</h2>\n  <!-- 운영부 체계 가이드 탭 -->', 1)

# 시간대별 업무 절차 h3 + 오전/오후/야간조 섹션은 운영부 버전으로 교체
# 섹션 시작: "시간대별 업무 절차" h3, 끝: </div>\n\n<div id="tab-manual"
old_guide_proc_start = '  <!-- 시간대별 업무 절차 -->\n  <h3 style="font-size:17px;margin:24px 0 10px;padding-top:8px;border-top:1px solid var(--border);">시간대별 업무 절차</h3>'
old_guide_proc_end   = '</div>\n\n<div id="tab-manual"'

if old_guide_proc_start in src and old_guide_proc_end in src:
    g1 = src.index(old_guide_proc_start)
    g2 = src.index(old_guide_proc_end, g1)
    new_guide_proc = """  <!-- 시간대별 업무 절차 -->
  <h3 style="font-size:17px;margin:24px 0 10px;padding-top:8px;border-top:1px solid var(--border);">시간대별 업무 절차</h3>

  <!-- 오전 오픈조 -->
  <div class="manual-section">
    <div class="manual-header" onclick="togManual(this)" style="background:var(--accent-bg);">
      <h3 style="color:var(--accent);">오전조 (오픈~인수인계)</h3><span class="arrow">&#9654;</span>
    </div>
    <div class="manual-body">
      <span class="manual-label">오픈 점검</span>
      <ul>
        <li>리셉션 조명·PC·전화·POS 전원 점검</li>
        <li>당일 예약·방문 일정 확인 (투어·상담 사전 확인)</li>
        <li>프론트 카운터·대기 공간 청결·비품(안내물·음료 등) 점검</li>
        <li>입구 안내 표지·현수막 위치 점검</li>
      </ul>
      <span class="manual-label">회원 응대</span>
      <ul>
        <li>입장 회원 확인·인사 (눈 맞춤+미소 필수)</li>
        <li>방문객·투어 문의 접수 → 안내 또는 담당자 연결</li>
        <li>전화 문의 응대 — 예약 일정 안내·기록</li>
      </ul>
      <span class="manual-label">인수인계</span>
      <ul>
        <li>당일 접수된 VOC·건의 사항 기록 확인</li>
        <li>오전조 → 오후조: 미결 문의·이슈 공유</li>
      </ul>
    </div>
  </div>

  <!-- 오후조 -->
  <div class="manual-section">
    <div class="manual-header" onclick="togManual(this)" style="background:var(--green-bg);">
      <h3 style="color:var(--green);">오후조 (오후~마감)</h3><span class="arrow">&#9654;</span>
    </div>
    <div class="manual-body">
      <span class="manual-label">오후 운영</span>
      <ul>
        <li>퇴장 회원 인사·물품 분실 확인</li>
        <li>전화·방문 문의 응대 — 투어 예약 기록</li>
        <li>VOC 접수 건 폼 기록 완료 확인 + 해당 부서 전달</li>
      </ul>
      <span class="manual-label">마감</span>
      <ul>
        <li>방문자 일지·문의 일지 마감 기록</li>
        <li>리셉션 카운터 정리·비품 재고 확인</li>
        <li>PC·전화·조명 오프 / 잠금 확인 후 마감 보고</li>
      </ul>
    </div>
  </div>

</div>

"""
    src = src[:g1] + new_guide_proc + src[g2:]
    print('guide proc section replaced')
else:
    print('WARN: guide proc section not found, skipping')

# ── 7. 가이드 탭 구역별 관리 기준 h3 + 표를 운영부 기준으로 교체
old_zone = """  <h3 style="font-size:17px;margin:16px 0 10px;">구역별 관리 기준</h3>
  <table style="width:100%;border-collapse:collapse;">
    <tr style="background:var(--paper);"><th style="padding:10px;border:1px solid var(--border);width:160px;">구역</th><th style="padding:10px;border:1px solid var(--border);">관리 기준</th></tr>
    <tr><td style="padding:8px;border:1px solid var(--border);"><strong>출입·차단기</strong></td><td style="padding:8px;border:1px solid var(--border);">입·출차 차단기 정상 작동 / LPR(번호인식) 카메라 청결·인식 / 오작동 시 수동 개방 + 즉시 보고</td></tr>
    <tr><td style="padding:8px;border:1px solid var(--border);"><strong>정산·요금기</strong></td><td style="padding:8px;border:1px solid var(--border);">화면·카드리더·지폐/동전부·영수증 정상 / 현금 시재 인수인계 / 미정산 건 즉시 공유</td></tr>
    <tr><td style="padding:8px;border:1px solid var(--border);"><strong>지상 주차장</strong></td><td style="padding:8px;border:1px solid var(--border);">불법·이중·장기 주차 계도 / 통행로 확보 / 조명·배수·바닥 표시선 점검</td></tr>
    <tr><td style="padding:8px;border:1px solid var(--border);"><strong>지하 주차장</strong></td><td style="padding:8px;border:1px solid var(--border);">층별 순찰 / 환기·제연 가동 / 누수·고임물·결빙 / 빈자리 안내</td></tr>
    <tr><td style="padding:8px;border:1px solid var(--border);"><strong>우선·지정 구역</strong></td><td style="padding:8px;border:1px solid var(--border);">장애인·여성우선·전기차 구역 불법 점유 단속 / 표지·도색 식별</td></tr>
    <tr><td style="padding:8px;border:1px solid var(--border);"><strong>안전·소방</strong></td><td style="padding:8px;border:1px solid var(--border);">소화기·소화전·비상구·피난통로 / CCTV 사각지대 / 주차장 화장실 청결</td></tr>
  </table>"""
new_zone = """  <h3 style="font-size:17px;margin:16px 0 10px;">구역별 관리 기준</h3>
  <table style="width:100%;border-collapse:collapse;">
    <tr style="background:var(--paper);"><th style="padding:10px;border:1px solid var(--border);width:160px;">구역</th><th style="padding:10px;border:1px solid var(--border);">관리 기준</th></tr>
    <tr><td style="padding:8px;border:1px solid var(--border);"><strong>리셉션 카운터</strong></td><td style="padding:8px;border:1px solid var(--border);">PC·전화·POS 정상 / 안내물·비품 충분 / 카운터 청결 유지</td></tr>
    <tr><td style="padding:8px;border:1px solid var(--border);"><strong>대기·로비 공간</strong></td><td style="padding:8px;border:1px solid var(--border);">좌석 청결·정돈 / 음료·안내물 보충 / 방문객 안내 즉시</td></tr>
    <tr><td style="padding:8px;border:1px solid var(--border);"><strong>입구·안내 표지</strong></td><td style="padding:8px;border:1px solid var(--border);">운영시간 표지 정상 / 현수막·안내판 위치·상태 / 오픈·마감 안내</td></tr>
    <tr><td style="padding:8px;border:1px solid var(--border);"><strong>방문자·문의 일지</strong></td><td style="padding:8px;border:1px solid var(--border);">방문·투어·전화 문의 당일 기록 완료 / VOC 폼 접수 확인</td></tr>
    <tr><td style="padding:8px;border:1px solid var(--border);"><strong>VOC 전달</strong></td><td style="padding:8px;border:1px solid var(--border);">접수된 VOC는 당일 해당 부서 전달 / 처리 결과 회원 고지</td></tr>
  </table>"""
if old_zone in src:
    src = src.replace(old_zone, new_zone, 1)
    print('zone table replaced')
else:
    print('WARN: zone table not found')

# ── 8. FALLBACK_STAFF — 운영부 직원
old_staff = """// 점검자 명단 — 주차관리부 직원 구성(2026-06-08 GM 확정).
// 양상규 고문(책임자) + 추가 담당 1명(충원 예정). 지상=m / 지하=f.
const FALLBACK_STAFF = [
  {name:'양상규 고문', role:'고문(책임자)', shift:'all', gender:'m'},
  {name:'추가 담당(충원 예정)', role:'담당', shift:'all', gender:'f'}
];"""
new_staff = """// 점검자 명단 — 운영부 직원 구성(2026-06-08).
// 이경연 실장(오전 총괄) + 추가 담당(충원 예정). 오전=m / 오후=f.
const FALLBACK_STAFF = [
  {name:'이경연 실장', role:'실장(오전 총괄)', shift:'am', gender:'m'},
  {name:'추가 담당(충원 예정)', role:'담당', shift:'pm', gender:'f'}
];"""
assert old_staff in src, 'FALLBACK_STAFF not found'
src = src.replace(old_staff, new_staff, 1)
print('staff replaced')

# ── 9. loadStaffFromSheet 주석
old_lss = """  // 주차관리부 담당자 — 양상규 고문(책임자) 확정(2026-06-08 GM). 추가 담당 충원 예정.
  // 시트 동적 로드 비활성화 — STAFF_LIST는 FALLBACK 고정 유지."""
new_lss = """  // 운영부 담당자 — 이경연 실장(오전 총괄) 확정. 추가 담당 충원 예정.
  // 시트 동적 로드 비활성화 — STAFF_LIST는 FALLBACK 고정 유지."""
assert old_lss in src, 'loadStaff comment not found'
src = src.replace(old_lss, new_lss, 1)

# ── 10. Storage keys — 운영부 전용 분리
src = src.replace("const ITEM_CACHE_KEY = 'pkcheck_items_cache';",
                  "const ITEM_CACHE_KEY = 'opscheck_items_cache';", 1)
src = src.replace("const LK=d=>`wcheck3_${d}`;",
                  "const LK=d=>`opscheck3_${d}`;", 1)
src = src.replace("localStorage.setItem('pkcheck_submitter_'+g,v)",
                  "localStorage.setItem('opscheck_submitter_'+g,v)", 1)
src = src.replace("const savedKey='pkcheck_submitter_'+gender;",
                  "const savedKey='opscheck_submitter_'+gender;", 1)
src = src.replace("const savedM=localStorage.getItem('pkcheck_submitter_m');",
                  "const savedM=localStorage.getItem('opscheck_submitter_m');", 1)
src = src.replace("const savedF=localStorage.getItem('pkcheck_submitter_f');",
                  "const savedF=localStorage.getItem('opscheck_submitter_f');", 1)
src = src.replace("const savedOld=localStorage.getItem('pkcheck_submitter');",
                  "const savedOld=localStorage.getItem('opscheck_submitter');", 1)
src = src.replace("const MGMT_STORAGE_KEY = 'pkcheck_custom_items';",
                  "const MGMT_STORAGE_KEY = 'opscheck_custom_items';", 1)
src = src.replace("const POLICY_STORAGE_KEY = 'PARKING_POLICY_BOARD';",
                  "const POLICY_STORAGE_KEY = 'OPS_POLICY_BOARD';", 1)
src = src.replace("const BOARD_STORAGE_KEY = 'PARKING_MANUAL_BOARD';",
                  "const BOARD_STORAGE_KEY = 'OPS_MANUAL_BOARD';", 1)
print('storage keys replaced')

# ── 11. POLICY_COLS + POLICY_SEED — 운영부 규정
old_pcols = """const POLICY_COLS = [
  {key:'ops',   label:'운영 기준', cls:'male'},
  {key:'meet',  label:'정기 회의', cls:'female'}
];
/* 시드 — 주차관리부 규정·회의 기본값(placeholder). 담당자·근무조 미정(충원/정의 예정).
   각 카드 = {id, title, body}. 공식값(운영시간 등)은 확정 후 GM이 직접 편집·저장. */
const POLICY_SEED = {
  ops:[
    {id:'op_hours', title:'운영시간(확정 예정)', body:'주차장 운영시간은 클럽 운영시간 기준으로 확정 예정.\\n야간 무인 운영 여부 포함 정의 예정.'},
    {id:'op_shift', title:'근무조 편성(충원/정의 예정)', body:'오전·오후·야간 근무조 및 담당자 미정.\\n충원/정의 후 본 카드 갱신.'},
    {id:'op_zone',  title:'담당 구역', body:'지상 주차장 / 지하 주차장(층별) / 출입·정산 / 우선구역(장애인·여성우선·전기차)'},
    {id:'op_safe',  title:'안전 보고', body:'차량 접촉/파손·차단기 고장·누수·화재 위험 발견 시 즉시 조치 후 팀장·소장 보고.\\n자의 판단 금지.'},
    {id:'op_cash',  title:'정산·시재 관리', body:'정산기 현금 시재는 교대 시 인수인계·기록 의무.\\n미정산/미수 건은 즉시 공유.'},
    {id:'op_priv',  title:'개인정보·CCTV', body:'차량번호·CCTV 영상은 회원 개인정보. 외부 유출·임의 열람 금지.\\n열람은 사고·민원 처리 목적+책임자 승인 한정.'},
    {id:'op_note',  title:'※ 규정 확정 안내', body:'본 규정은 기본값(placeholder)이며, 주차관리부 인원·근무조·세부 절차 확정 후 GM 검토를 거쳐 갱신됩니다.'}
  ],
  meet:[
    {id:'mt_week',  title:'주간 브리핑(정의 예정)', body:'주기: 미정 (예: 매주 월 오전)\\n참석: 충원/정의 예정\\n안건: 지난주 이슈 / 이번주 집중 구역 / 설비 현황'},
    {id:'mt_month', title:'월간 운영 회의(정의 예정)', body:'주기: 미정 (예: 매월 첫째주)\\n참석: 충원/정의 예정\\n안건: 이슈·노하우 취합 / 매뉴얼 개정 여부'},
    {id:'mt_urgent',title:'긴급 회의', body:'주기: 사고·고장 등 이슈 발생 즉시\\n참석: 해당 담당자+팀장\\n안건: 원인 분석 / 즉시 조치'}
  ]
};"""
new_pcols = """const POLICY_COLS = [
  {key:'ops',   label:'운영 기준', cls:'male'},
  {key:'voc',   label:'VOC 처리', cls:'outer'},
  {key:'meet',  label:'정기 회의', cls:'female'}
];
/* 시드 — 운영부 규정·회의 기본값. 공식값 확정 후 GM이 직접 편집·저장. */
const POLICY_SEED = {
  ops:[
    {id:'op_hours', title:'운영시간', body:'클럽 공식 운영시간 기준 리셉션 운영.\\n자세한 운영시간은 웰페리온 ERP 공식값 참조.'},
    {id:'op_shift', title:'근무조 편성', body:'오전조: 이경연 실장\\n오후조: 충원 예정\\n2인 이상 근무 시 교대 휴게(리셉션 비우지 않음).'},
    {id:'op_zone',  title:'담당 구역', body:'리셉션 카운터 / 프론트 로비 / 입구 안내 / 방문자 응대 / VOC 접수'},
    {id:'op_report',title:'이슈 보고', body:'회원 민원·안전 이슈 발생 시 즉시 조치 후 실장·GM 보고.\\n자의 판단 금지.'},
    {id:'op_priv',  title:'개인정보', body:'회원 연락처·예약 정보는 외부 유출 금지.\\n열람은 업무 목적+책임자 승인 한정.'},
    {id:'op_note',  title:'※ 규정 확정 안내', body:'본 규정은 기본값(placeholder)이며, 운영부 인원·세부 절차 확정 후 GM 검토를 거쳐 갱신됩니다.'}
  ],
  voc:[
    {id:'voc_recv', title:'VOC 접수 원칙', body:'회원 건의 접수 즉시 구글 폼(멤버의 소리 VOC) 기록.\\n직원명·회원명·이슈 내용·장소·전달 부서 필수 입력.'},
    {id:'voc_fwd',  title:'부서 전달', body:'접수 당일 해당 부서에 전달.\\n전달 기록은 이슈 응답 시트(리셉션 업무 시트 VOC 탭) 확인.'},
    {id:'voc_close',title:'처리 완료 고지', body:'처리 완료 시 회원에게 결과 고지(가능한 경우).\\n미처리 건은 다음 교대조에 인계.'},
    {id:'voc_link', title:'폼/시트 링크', body:'VOC 폼: docs.google.com/forms/d/e/1FAIpQLSd7mDzTyZT5FSXVcxmpMCaqv7M-RR3EmEu2lFqGRksUE77osA/viewform\\n응답 시트: spreadsheets/d/1akZLs7ITs3FZWFIzMQvSYrdRucGQglmerOvTC2TLEcQ (gid=1576318230)'}
  ],
  meet:[
    {id:'mt_week',  title:'주간 운영 미팅(정의 예정)', body:'주기: 미정 (예: 매주 월 오전)\\n참석: 운영부 직원 + 실장\\n안건: 지난주 VOC 현황 / 이번주 방문 일정 / 이슈 공유'},
    {id:'mt_month', title:'월간 운영 회의(정의 예정)', body:'주기: 미정 (예: 매월 첫째주)\\n참석: 실장 + GM\\n안건: VOC 트렌드 / 매뉴얼 개정 / 개선 사항'},
    {id:'mt_urgent',title:'긴급 회의', body:'주기: 민원·사고 등 이슈 발생 즉시\\n참석: 해당 담당자+실장\\n안건: 원인 분석 / 즉시 조치'}
  ]
};"""
assert old_pcols in src, 'POLICY_COLS/SEED not found'
src = src.replace(old_pcols, new_pcols, 1)
print('policy cols/seed replaced')

# ── 12. 점검항목 WEEKDAY — 운영부 리셉션 항목으로 교체
# WEEKDAY 배열 전체 찾기
weekday_start = '/* ── Data: gender field added (m/f/all) ── */\n\nconst WEEKDAY=['
weekday_end   = '\n\nconst WEEKEND=['
assert weekday_start in src, 'WEEKDAY start not found'
assert weekday_end in src,   'WEEKEND end not found'
w1 = src.index(weekday_start)
w2 = src.index(weekday_end, w1)

new_weekday = """/* ── Data: gender field added (m/f/all) ── */

const WEEKDAY=[
  {slot:"오픈 점검 07:30~08:30",shift:"am",groups:[
    {title:"O-A 리셉션 오픈",items:[
      {id:"oa1",name:"O-A1 PC·전화·POS 전원 점검",detail:"리셉션 PC·전화·POS 정상 부팅 | 당일 예약 일정 확인",gender:"m"},
      {id:"oa2",name:"O-A2 카운터 청결·비품 점검",detail:"카운터 정돈·청결 | 안내물·음료·소모품 보충",gender:"m"},
      {id:"oa3",name:"O-A3 입구·안내 표지 점검",detail:"입구 안내판·현수막 위치·상태 | 운영시간 표기 정상",gender:"m"}
    ]}
  ]},
  {slot:"오전 응대 08:30~13:00",shift:"am",groups:[
    {title:"O-B 회원 응대",items:[
      {id:"ob1",name:"O-B1 입장 회원 확인·인사",detail:"눈 맞춤+미소 | 회원 카드 확인 | 이름 알면 호칭 사용",gender:"m"},
      {id:"ob2",name:"O-B2 방문·투어 응대",detail:"방문 목적 파악 | 투어 안내 또는 담당자 연결 | 예약 기록",gender:"m"},
      {id:"ob3",name:"O-B3 전화 문의 응대",detail:"3회 이내 응답 | 내용 기록 | 추후 연락 건 메모",gender:"m"}
    ]},
    {title:"O-C VOC 접수",items:[
      {id:"oc1",name:"O-C1 VOC 폼 기록",detail:"회원 건의 즉시 구글 폼 기록 | 직원명·회원명·장소·부서 필수",gender:"all"},
      {id:"oc2",name:"O-C2 해당 부서 전달",detail:"접수 당일 해당 부서에 전달 | 이슈 응답 시트 확인",gender:"all"}
    ]}
  ]},
  {slot:"인수인계 13:00~14:00",shift:"am",groups:[
    {title:"O-D 교대 인수인계",items:[
      {id:"od1",name:"O-D1 미결 문의·이슈 인계",detail:"미처리 VOC | 방문 예정 | 전화 메모 | 이슈 공유",gender:"all"},
      {id:"od2",name:"O-D2 카운터 점검 인계",detail:"비품 재고 | 현금/포스 상태 | 청결 상태 인계",gender:"all"}
    ]}
  ]},
  {slot:"오후 응대 14:00~19:00",shift:"pm",groups:[
    {title:"O-B 회원 응대",items:[
      {id:"ob_pm1",name:"O-B1 입·퇴장 회원 응대",detail:"눈 맞춤+미소 | 퇴장 인사 | 분실물 확인",gender:"f"},
      {id:"ob_pm2",name:"O-B2 방문·문의 응대",detail:"방문 목적 파악 | 투어 예약 기록 | 전화 문의 메모",gender:"f"}
    ]},
    {title:"O-C VOC 접수",items:[
      {id:"oc_pm1",name:"O-C1 오후 VOC 기록",detail:"오후 접수 건의 즉시 폼 기록 | 전달 완료 확인",gender:"all"}
    ]}
  ]},
  {slot:"마감 19:00~",shift:"pm",groups:[
    {title:"O-E 마감",items:[
      {id:"oe1",name:"O-E1 방문자·문의 일지 마감",detail:"당일 방문·문의·VOC 기록 최종 확인",gender:"f"},
      {id:"oe2",name:"O-E2 카운터·비품 정리",detail:"카운터 정돈 | 소모품 재고 확인 | 쓰레기 처리",gender:"f"},
      {id:"oe3",name:"O-E3 시스템·잠금 마감",detail:"PC·전화 오프 | 조명 소등 | 잠금 확인 | 마감 보고",gender:"f"}
    ]}
  ]},
  {slot:"상시",shift:"all",groups:[
    {title:"O-F 복장·에티켓",items:[
      {id:"of1",name:"O-F1 유니폼·명찰",detail:"웰페리온 유니폼 청결 | 명찰 좌측 가슴 패용",gender:"all"},
      {id:"of2",name:"O-F2 응대 태도",detail:"먼저 인사 | 끝까지 경청 | 처리 결과 반드시 고지",gender:"all"}
    ]}
  ]}
]"""

src = src[:w1] + new_weekday + src[w2:]
print('WEEKDAY replaced')

# ── 13. WEEKEND 배열 교체
weekend_start = '\n\nconst WEEKEND=['
weekend_end_marker = '\n];\n\n/* ── Night schedule'
assert weekend_start in src, 'WEEKEND start not found'

w3 = src.index(weekend_start)
# WEEKEND 끝 찾기 — "];\n\n" 패턴
w4_candidate = src.index('];\n\n', w3 + len(weekend_start))
# 혹시 중간에 ];\n\n 가 있을 수 있으니 "const NIGHT" 로 끝 앵커
try:
    w4 = src.index('\n\nconst NIGHT_WEEKDAY', w3)
except ValueError:
    w4 = w4_candidate + 3

new_weekend = """

const WEEKEND=[
  {slot:"오픈 점검 09:00~10:00",shift:"am",groups:[
    {title:"O-A 리셉션 오픈",items:[
      {id:"oa1w",name:"O-A1 PC·전화·POS 점검",detail:"전원 확인 | 주말 예약 일정 확인",gender:"m"},
      {id:"oa2w",name:"O-A2 카운터·비품 점검",detail:"카운터 정돈 | 안내물·음료 보충",gender:"m"}
    ]}
  ]},
  {slot:"주말 응대 10:00~17:00",shift:"am",groups:[
    {title:"O-B 회원·방문 응대",items:[
      {id:"ob_w1",name:"O-B1 회원 입장 응대",detail:"눈 맞춤+미소 | 혼잡 시 대기 안내",gender:"m"},
      {id:"ob_w2",name:"O-B2 방문·투어 응대",detail:"방문 목적 파악 | 예약 기록 | 담당자 연결",gender:"m"},
      {id:"ob_w3",name:"O-B3 VOC 접수",detail:"건의 즉시 폼 기록 | 해당 부서 전달",gender:"all"}
    ]}
  ]},
  {slot:"마감 17:00~",shift:"pm",groups:[
    {title:"O-E 마감",items:[
      {id:"oe_w1",name:"O-E1 일지·VOC 마감 기록",detail:"당일 방문·문의·VOC 최종 확인",gender:"f"},
      {id:"oe_w2",name:"O-E2 시스템·잠금 마감",detail:"PC·조명 오프 | 잠금 확인 | 마감 보고",gender:"f"}
    ]}
  ]}
]"""

# NIGHT_WEEKDAY 부분 앞까지 잘라내고 교체
src = src[:w3] + new_weekend + src[w4:]
print('WEEKEND replaced')

# ── 14. NIGHT 스케줄 — 운영부는 야간 운영 없음 (빈 배열)
# NIGHT_WEEKDAY, NIGHT_WEEKEND 배열을 빈 배열로 교체
import re

# NIGHT_WEEKDAY
src = re.sub(
    r'const NIGHT_WEEKDAY=\[[\s\S]*?\];',
    'const NIGHT_WEEKDAY=[];  // 운영부 야간 미운영',
    src, count=1)

src = re.sub(
    r'const NIGHT_WEEKEND=\[[\s\S]*?\];',
    'const NIGHT_WEEKEND=[];  // 운영부 야간 미운영',
    src, count=1)
print('NIGHT schedules cleared')

# ── 15. DAY_FOCUS — 운영부 버전으로 교체
old_df_start = '/* ── E: Day-of-week focused inspection ── */\nconst DAY_FOCUS={'
old_df_end   = '\n};\n\n/* ── Helper functions ── */'
assert old_df_start in src, 'DAY_FOCUS start not found'
d1 = src.index(old_df_start)
d2 = src.index('\n};\n\n/* ── Helper functions ── */', d1) + len('\n};\n\n/* ── Helper functions ── */')

new_df = """/* ── E: Day-of-week focused inspection ── */
const DAY_FOCUS={
  1:[ // 월
    {id:"df_mon1",name:"VOC 미처리 건 정리",detail:"주말·전주 미처리 VOC 건 현황 확인·부서 재전달",gender:"all"},
    {id:"df_mon2",name:"비품 재고 점검",detail:"안내물·음료·소모품 재고 확인·발주 요청",gender:"all"}
  ],
  2:[ // 화
    {id:"df_tue1",name:"방문자 일지 정리",detail:"지난주 방문·문의·투어 일지 정리·백업",gender:"all"},
    {id:"df_tue2",name:"PC·전화 상태 점검",detail:"리셉션 PC·전화 소프트웨어 업데이트 | 비정상 여부",gender:"all"}
  ],
  3:[ // 수
    {id:"df_wed1",name:"카운터 정밀 청소",detail:"카운터 내부·서랍·비품함 정밀 정리",gender:"all"},
    {id:"df_wed2",name:"안내물·현수막 점검",detail:"훼손·노후 안내물 교체 요청 | 표지 위치 점검",gender:"all"}
  ],
  4:[ // 목
    {id:"df_thu1",name:"VOC 응답 시트 확인",detail:"이슈 응답 시트 미처리 건 점검 | 처리 완료 건 고지 여부",gender:"all"},
    {id:"df_thu2",name:"로비·대기 공간 집중 청소",detail:"좌석·바닥·창문 청결 집중 관리",gender:"all"}
  ],
  5:[ // 금
    {id:"df_fri1",name:"주간 VOC 현황 정리",detail:"이번 주 접수 건 요약 | 미결 건 실장 보고",gender:"all"},
    {id:"df_fri2",name:"주간 방문·문의 현황 보고",detail:"방문자·투어 문의 주간 집계 기록",gender:"all"}
  ],
  6:[ // 토
    {id:"df_sat1",name:"주말 방문 대비 점검",detail:"주말 예약·투어 일정 최종 확인 | 비품 보충",gender:"all"},
    {id:"df_sat2",name:"VOC 폼 정상 작동 확인",detail:"폼 링크 정상 접속·제출 테스트",gender:"all"}
  ],
  0:[ // 일
    {id:"df_sun1",name:"주간 일지 마감",detail:"전주 방문·문의·VOC 기록 최종 정리",gender:"all"},
    {id:"df_sun2",name:"다음주 준비",detail:"안내물·비품 보충 | 다음주 예약 일정 확인",gender:"all"}
  ]
};

/* ── Helper functions ── */"""

src = src[:d1] + new_df + src[d2:]
print('DAY_FOCUS replaced')

# ── 16. 점검 탭 레이블 — 지상/지하 → 오전/오후 (submit 버튼 및 탭 타이틀)
src = src.replace('>오전조 제출<', '>오전 제출<')
src = src.replace('>오후조 제출<', '>오후 제출<')
src = src.replace('>야간조 제출<', '>야간 제출<')

# ── 17. 헤더 sheet-links 중 "시트(연동 예정)" 유지, 현황 대시보드 이동 링크 유지

# ── 18. switchTab에 'voc' 케이스 추가 (tab-voc 패널)
old_switch = "case 'guide':"
new_switch = "case 'voc':\n    case 'guide':"
if old_switch in src:
    src = src.replace(old_switch, new_switch, 1)
    print('switchTab voc added')

# ── 19. DASH_DEPT 변경
src = src.replace("const DASH_DEPT = 'support';", "const DASH_DEPT = 'ops';", 1)
print('DASH_DEPT changed')

# ── 20. 최종 저장
with open(DEST, 'w', encoding='utf-8') as f:
    f.write(src)
print('DONE - written to', DEST)
print('final len=', len(src))
