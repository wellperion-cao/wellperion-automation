"""
weekly_page_hygiene.py — 주간 페이지 위생 자동화 (배 CTO-2026-07-14-WEEKLY-PAGE-HYGIENE, GM 지시 2026-07-14).

목표: 오늘(2026-07-14) GM이 수동으로 진행한 시우(COO) 14페이지 감사
     (하위모델→A죽은코드/B중복/C낡은안내/D장황 분류→GM승인→적용)를
     매주 일요일 09:00 무인 파이프로 제품화한다.

★안전 모델★
  1) 대상: PAGE_TARGETS — 2026-07-14 GM 지시로 전 ERP 47페이지 커버로 확장(COO 14 +
     CPO 3 + CMO 7 + CTO 2 + CFO 3 + CHRO 12 + shared 3 + 리다이렉트 스텁 3 = 47).
     load_targets(clevel)로 C-Level별 서브셋, load_targets(None)으로 전체 조회.
  2) 감사: 페이지(또는 메인가이드 섹션)마다 headless claude(-p, --permission-mode plan —
     편집 불가·읽기전용 분석 전용)를 호출해 A/B/C/D 카테고리 구조화 후보를 JSON으로 받는다.
     감사 자체는 게이트와 무관하게 매번 실행된다(GM이 매주 결과를 받아보는 것이 핵심 가치).
  3) 카테고리 A(죽은 코드)만 자동 적용 후보. 적용 직전 반드시 3중 게이트를 통과해야 한다:
       a) grep-0 하드 게이트(verify_zero_consumers) — symbol이 선언 자체 외에 리포 전체에서
          0건이어야 함(1건이라도 있으면 자동적용 스킵·제안으로 강등).
       b) snippet 고유성 게이트 — LLM이 제시한 정확 삭제범위(snippet)가 파일 내 정확히 1회만
          등장해야 함(모호하면 자동적용 금지 원칙 — GM 못박기).
       c) 적용 후 파싱 무결성 게이트(check_parse_integrity) — <script>/<style>/<div> 태그
          균형이 깨지면 그 후보만 롤백·스킵(파일 자체는 다른 안전 후보 적용 계속).
     B/C/D는 항상 제안(status/page_hygiene_proposal_{date}.md)만 — 자동적용 금지.
  4) 라이브 게이트: env PAGE_HYGIENE_APPLY(기본 OFF)="1"일 때만 카테고리 A를 실제 파일에
     반영·커밋한다. OFF면 "적용됐다면"을 grep-0 게이트까지 미리 계산해 제안서에
     "자동적용 조건 충족(다음 GM go 시 적용 예정)" 꼬리표로 미리보기만 남긴다(파일 무변경).
     --dry-run CLI 플래그는 env와 무관하게 이번 실행만 강제 미적용(검증용).
  5) 파일별 1커밋(가역·되돌리기 쉬움) — 커밋 실패(index.lock 등) 시 비파괴 재시도(포기 아님,
     강제삭제·reset 금지).
  6) 텔레그램 요약 발송 + module_registry cto-weekly-page-hygiene 자율현황 노출.

★2026-08-17 배662 수리(웰리 실측 25/44 실패 → 원인 규명): 실패 2종 다 콘텐츠 크기와
  관련이지만 원인은 서로 다르다.
    a) 타임아웃(20건) — claude -p 가 이 리포 cwd에서 매 호출마다 CLAUDE.md·메모리·
       플러그인·훅을 통째로 로드해, 53KB짜리 작은 페이지조차 221초(240초 타임아웃 코앞)가
       걸렸다. --safe-mode(훅·플러그인·CLAUDE.md 끄되 인증은 그대로 — --bare는
       ANTHROPIC_API_KEY를 강제해 이 계정의 OAuth 로그인과 안 맞아 배제)로 같은 페이지가
       28초로 줄었다(run_audit_claude).
    b) JSON 파싱 실패(5건, 메인가이드·문의회원처럼 700KB+ 페이지) — 모델 생성이 늦은 게
       아니라 claude -p 가 "Prompt is too long"으로 2초 만에 즉시 거부했다. CHUNK_MAX_CHARS
       상수로 줄바꿈 경계에서 나눠 보낸다(_split_content_chunks/_run_audit_chunked).

라이브 부작용 0 함수(순수) — build_audit_prompt, verify_zero_consumers(읽기전용 git grep),
check_parse_integrity, apply_category_a(메모리상 문자열 연산), write_proposal_file은 파일
1개만 쓴다(제안서). 실제 페이지 파일 쓰기·git commit은 run_pipeline()만 게이트에 따라 수행.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)

# ── 게이트 env ──
APPLY_ENV_VAR = "PAGE_HYGIENE_APPLY"

# ── 대상 페이지 config (2026-07-14 GM 지시로 전 ERP 47페이지 커버로 확장) ──
# 메인가이드 O1~O4는 한 물리 파일(wellperion_guide(main).html) 안의 4개 섹션이라, 같은
# path를 가리키되 anchor로 섹션을 구분한다(오늘 GM 감사와 동일 단위 — 14페이지 카운트 일치).
# clevel="shared"는 특정 C-Level 소유가 아닌 전사 공용 페이지(공용 3) 및 리다이렉트
# 스텁(감사 가치 낮으나 무해 — GM 지시로 포함, 3)에 사용.
PAGE_TARGETS: list[dict] = [
    # ── COO 14 (기존) ──
    {"clevel": "coo", "label": "시설부 체계", "path": "3. 웰페리온 가이드/coo/check/시설부 체계.html"},
    {"clevel": "coo", "label": "지원부 체계", "path": "3. 웰페리온 가이드/coo/check/지원부 체계.html"},
    {"clevel": "coo", "label": "운영부 체계", "path": "3. 웰페리온 가이드/coo/check/운영부 체계.html"},
    {"clevel": "coo", "label": "주차관리부 체계", "path": "3. 웰페리온 가이드/coo/check/주차관리부 체계.html"},
    {"clevel": "coo", "label": "파트너팀 체계", "path": "3. 웰페리온 가이드/coo/check/파트너팀 체계.html"},
    # "강습팀 업장관리" 2026-07-16 e1a2f73 로 페이지 삭제(감사 레지스트리 정리 포함) — 본 목록에서도 함께 제거.
    {"clevel": "coo", "label": "전사_일정", "path": "3. 웰페리온 가이드/coo/check/전사_일정.html"},
    {"clevel": "coo", "label": "업무 현황 SSOT", "path": "3. 웰페리온 가이드/coo/todo/업무 현황 SSOT.html"},
    {"clevel": "coo", "label": "결재 현황 SSOT", "path": "3. 웰페리온 가이드/coo/todo/결재 현황 SSOT.html"},
    {"clevel": "coo", "label": "공지 템플릿", "path": "3. 웰페리온 가이드/coo/notice/notice_template.html"},
    {"clevel": "coo", "label": "메인가이드 O1(운영통합체계)", "path": "3. 웰페리온 가이드/wellperion_guide(main).html", "anchor": "O1"},
    {"clevel": "coo", "label": "메인가이드 O2(공지)", "path": "3. 웰페리온 가이드/wellperion_guide(main).html", "anchor": "O2"},
    {"clevel": "coo", "label": "메인가이드 O3(재등록)", "path": "3. 웰페리온 가이드/wellperion_guide(main).html", "anchor": "O3"},
    {"clevel": "coo", "label": "메인가이드 O4", "path": "3. 웰페리온 가이드/wellperion_guide(main).html", "anchor": "O4"},
    # ── CPO 3 (2026-07-14 추가) ──
    {"clevel": "cpo", "label": "문의회원", "path": "3. 웰페리온 가이드/cpo/member/membership.html"},
    {"clevel": "cpo", "label": "강습회원관리", "path": "3. 웰페리온 가이드/cpo/member/강습회원관리.html"},
    {"clevel": "cpo", "label": "상품기획", "path": "3. 웰페리온 가이드/cpo/product/상품기획.html"},
    # ── CMO 7 (2026-07-14 추가) ──
    {"clevel": "cmo", "label": "콘텐츠문의현황", "path": "3. 웰페리온 가이드/cmo/funnel/콘텐츠문의현황.html"},
    {"clevel": "cmo", "label": "월간마케팅보고서", "path": "3. 웰페리온 가이드/cmo/funnel/월간마케팅보고서.html"},
    {"clevel": "cmo", "label": "홈페이지", "path": "3. 웰페리온 가이드/cmo/home/홈페이지.html"},
    {"clevel": "cmo", "label": "AI시리즈보드", "path": "3. 웰페리온 가이드/cmo/series/AI시리즈보드.html"},
    {"clevel": "cmo", "label": "wp_inquiry_block", "path": "3. 웰페리온 가이드/cmo/survey/wp_inquiry_block.html"},
    {"clevel": "cmo", "label": "wp_inquiry_block_en", "path": "3. 웰페리온 가이드/cmo/survey/wp_inquiry_block_en.html"},
    # ── CTO 2 (2026-07-14 추가) — 자율현황.html은 실제로 리포 루트에 위치(cto/automation/
    # 하위 아님, 08-27 확인) ──
    {"clevel": "cto", "label": "카톡전송관리", "path": "3. 웰페리온 가이드/cto/automation/카톡전송관리.html"},
    {"clevel": "cto", "label": "자율현황", "path": "3. 웰페리온 가이드/자율현황.html"},
    # ── CFO 3 (2026-07-14 추가) ──
    {"clevel": "cfo", "label": "매출지출현황", "path": "3. 웰페리온 가이드/cfo/finance/매출지출현황.html"},
    {"clevel": "cfo", "label": "매출현황", "path": "3. 웰페리온 가이드/cfo/finance/매출현황.html"},
    {"clevel": "cfo", "label": "지출현황", "path": "3. 웰페리온 가이드/cfo/finance/지출현황.html"},
    # ── CHRO 12 (2026-07-14 추가) — hub 6 + recruiting 6 ──
    {"clevel": "chro", "label": "인사허브", "path": "3. 웰페리온 가이드/chro/hub/index.html"},
    {"clevel": "chro", "label": "휴가", "path": "3. 웰페리온 가이드/chro/hub/leave.html"},
    {"clevel": "chro", "label": "오피스", "path": "3. 웰페리온 가이드/chro/hub/office.html"},
    {"clevel": "chro", "label": "온보딩", "path": "3. 웰페리온 가이드/chro/hub/onboarding.html"},
    {"clevel": "chro", "label": "온보딩(셀프)", "path": "3. 웰페리온 가이드/chro/hub/onboarding-self.html"},
    {"clevel": "chro", "label": "조직구조", "path": "3. 웰페리온 가이드/chro/hub/structure.html"},
    {"clevel": "chro", "label": "채용허브", "path": "3. 웰페리온 가이드/chro/recruiting/index.html"},
    {"clevel": "chro", "label": "채용-쇼퍼", "path": "3. 웰페리온 가이드/chro/recruiting/chauffeur.html"},
    {"clevel": "chro", "label": "채용-골프프로", "path": "3. 웰페리온 가이드/chro/recruiting/golfpro.html"},
    {"clevel": "chro", "label": "채용-운영", "path": "3. 웰페리온 가이드/chro/recruiting/operations.html"},
    {"clevel": "chro", "label": "채용-주차", "path": "3. 웰페리온 가이드/chro/recruiting/parking.html"},
    {"clevel": "chro", "label": "채용-사우나", "path": "3. 웰페리온 가이드/chro/recruiting/sauna.html"},
    # ── shared 3 — 공용 (2026-07-14 추가) ──
    {"clevel": "shared", "label": "전사회의", "path": "3. 웰페리온 가이드/전사회의.html"},
    {"clevel": "shared", "label": "웰페리온 대시보드(웹)", "path": "3. 웰페리온 가이드/wellperion_dashboard_web.html"},
    # ── shared 3 — 리다이렉트 스텁(감사 가치 낮으나 GM 지시로 포함) ──
    {"clevel": "shared", "label": "index(리다이렉트 스텁)", "path": "3. 웰페리온 가이드/index.html"},
    {"clevel": "shared", "label": "항해지도(리다이렉트 스텁)", "path": "3. 웰페리온 가이드/항해지도.html"},
    {"clevel": "shared", "label": "northstar_today(리다이렉트 스텁)", "path": "3. 웰페리온 가이드/northstar_today.html"},
]

DEFAULT_LOG_PATH = os.path.join(_PROJECT_ROOT, "status", "weekly_page_hygiene_log.jsonl")

# 자동삭제 잠금 — 소유자가 사람이라 AI 가 파일을 직접 고치지 않는다.
#   chro·cfo = 나우열M 라인(자율화규약 §9 · 약속 L22 — 접촉 금지)
#   coo      = 이경연 실장 라인(safe_commit.COO_DOMAIN_PATHS 가 커밋도 막는다 —
#              여기서 막지 않으면 파일만 고쳐지고 커밋은 거부되는 어중간한 상태가 된다)
#   ★GM 확정 2026-08-10: "업무&결재 SSOT도 CHRO 건이라 건드리면 안 된다"
AUTO_APPLY_LOCKED_CLEVELS = frozenset({"chro", "cfo", "coo"})

# ── 오탐 영구 제외 목록 (웰리 판정 2026-08-05, 배386/배8) ──
# (path_contains, symbol_or_snippet_contains) — 두 조건이 모두 맞으면 후보 제외.
FALSE_POSITIVE_EXCLUSIONS: list[tuple[str, str]] = [
    ("onboarding-self.html", "banner.ok"),   # setBanner('ok') 2곳 실사용 — 지우면 완료 배너 깨짐
    ("카톡전송관리.html", "../../assets/"),  # assets/wp-typography.css 정상 링크 — 404 아님
]

CATEGORY_LABELS = {
    "A": "죽은 코드(자동삭제 대상)",
    "B": "중복 설명 병합",
    "C": "낡은 안내·버전 배지",
    "D": "장황 단순화",
}


def load_targets(clevel: str | None = None) -> list[dict]:
    """clevel이 None이면 전체, 아니면 해당 clevel 소유 target만 반환(확장 포인트)."""
    if clevel is None:
        return list(PAGE_TARGETS)
    return [t for t in PAGE_TARGETS if t.get("clevel") == clevel]


def _apply_live() -> bool:
    return os.environ.get(APPLY_ENV_VAR, "0") == "1"


# ── 대형 페이지 청크 분할 (2026-08-17 배662 수리) ──
# 실측(웰리 배662 재현): claude -p 프롬프트 783,664자(메인가이드 O1 섹션·페이지 원본 946KB)에서
# "Prompt is too long"으로 2초 만에 즉시 거부됨 — 생성이 느린 게 아니라 CLI가 애초에 받지 않는다.
# 505,639자(지원부 체계)는 거부되지 않고 접수됐다(경계는 그 사이 어딘가). CHUNK_MAX_CHARS는 그
# 경계보다 넉넉히 낮게 잡아 페이지 크기와 무관하게 항상 통과하게 한다 — 이 값을 넘는 44페이지 중
# 2곳(메인가이드·문의회원)만 분할 대상이고 나머지는 지금처럼 한 번에 감사한다.
# ★200K로 잡은 이유(하드 상한 350K 대신): "Prompt too long" 회피 목적 하나뿐이면 350K도
# 충분하지만, 실측 중 이 세션이 동시 실행 중인 다른 에이전트 다수와 자원을 다퉈 지원부 체계
# (조각 250K)가 안전모드를 켜고도 240초 타임아웃을 두 조각 다 넘긴 사례가 나왔다 — 콘텐츠
# 크기에 비례해 처리 시간도 늘어난다는 뜻. 조각을 더 작게 잡아 호출당 시간을 줄여 안전마진을 둔다.
CHUNK_MAX_CHARS = 200_000


def _split_content_chunks(content: str, max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    """content가 max_chars보다 크면 줄바꿈 근처에서 잘라 청크 목록으로 나눈다(순수 함수).
    후보(candidate)의 symbol/snippet은 항상 모델이 실제로 본 청크 텍스트 안에서만 나오므로
    (청크 밖을 볼 수 없다) 청크 경계가 태그 중간을 지나도 안전 — apply_category_a의 게이트는
    분할 없는 전체 파일 원문을 대상으로 별도 검증한다."""
    if len(content) <= max_chars:
        return [content]
    chunks = []
    start, n = 0, len(content)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            nl = content.rfind("\n", start, end)
            if nl > start:
                end = nl + 1
        chunks.append(content[start:end])
        start = end
    return chunks


# ── 감사 프롬프트 조립 (순수 함수) ──
def build_audit_prompt(target: dict, content: str, chunk_index: int = 0, chunk_total: int = 1) -> str:
    anchor = target.get("anchor")
    scope_note = (
        f"\n\n★분석 범위 한정: id=\"{anchor}\" 섹션(및 그 하위 요소)만 후보 대상으로 삼는다. "
        "다른 섹션 내용은 후보에 포함하지 마라(참고용으로만 읽어라)."
        if anchor else ""
    )
    chunk_note = (
        f"\n\n★이 페이지는 커서 {chunk_total}개 조각으로 나눠 보낸다. 지금은 조각 {chunk_index + 1}/"
        f"{chunk_total}만 보인다 — 이 조각 안에서 완결된 후보만 판단하라(잘린 태그·문장 경계는 "
        "조각 분할 때문이니 그 자체를 낡은 코드로 보지 마라)."
        if chunk_total > 1 else ""
    )
    return (
        "너는 웰페리온 ERP 페이지 위생 감사관이다. 아래 HTML 페이지 전체를 검토해 "
        "무분별·무의미·중복·죽은 콘텐츠 후보를 찾아라. 너는 파일을 수정하지 않는다 — "
        "오직 JSON 분석 결과만 출력한다.\n\n"
        f"페이지: {target.get('label')} ({target.get('path')}){scope_note}{chunk_note}\n\n"
        "카테고리:\n"
        "A. 죽은 코드 — 미사용 CSS 클래스/ID, 미사용 JS 함수, 호출부 0인 죽은 마크업.\n"
        "B. 중복 설명 — 같은 내용이 페이지 내/페이지 간 두 곳 이상 반복.\n"
        "C. 낡은 안내 — 버전 배지 stale, 이미 해소된 경고 문구, 시제가 틀린 안내.\n"
        "D. 장황 — 실무진 가독성을 해치는 장황한 설명(표→한 줄 등 단순화 후보).\n\n"
        "★절대 보존 규칙: 실데이터 배선·기능(fetch·GAS·onclick·저장·필터)·SSOT 표·링크·버튼은 "
        "절대 후보에 포함 금지. 조금이라도 죽은 코드인지 애매하면(주석·조건부 참조·향후 재사용 "
        "가능성 등) 카테고리 A로 넣지 말고 C 또는 D로 낮춰라(모호=자동삭제 금지 원칙).\n\n"
        "카테고리 A로 넣는 항목은 다음 두 필드를 반드시 정확히 채워라:\n"
        "  - symbol: 리포 전체에서 grep 가능한 정확한 식별자(CSS 클래스는 dot 없이, id는 # 없이, "
        "함수명은 그대로). 여러 심볼이 얽혀 있으면 대표 심볼 1개.\n"
        "  - snippet: 파일 원문에서 문자 그대로(공백·줄바꿈 포함) 정확히 일치하는 삭제 대상 "
        "전체 텍스트(예: CSS 룰셋 전체 `.foo{...}`, JS 함수 전체, 죽은 마크업 블록 전체). "
        "이 필드가 없거나 파일에 정확히 1회 등장하지 않으면 자동적용되지 않는다.\n\n"
        "출력 형식: 오직 JSON 한 덩어리만 출력하라(설명 문장·마크다운 코드펜스·기타 텍스트 금지). "
        "스키마:\n"
        '{"candidates": [{"category": "A|B|C|D", "kind": "css-class|css-id|js-function|'
        'dead-markup|duplicate-text|stale-notice|verbose-block", "symbol": "...", '
        '"snippet": "...", "location": "대략 위치(줄/섹션)", "reason": "한 줄 근거", '
        '"preserve_check": "보존 확인 근거(왜 실데이터/기능이 아닌지)"}]}\n\n'
        "후보가 없으면 candidates를 빈 배열로 출력하라.\n\n"
        "--- 페이지 전체 내용 시작 ---\n"
        f"{content}\n"
        "--- 페이지 전체 내용 끝 ---"
    )


def _extract_json(text: str) -> dict | None:
    """claude -p 응답 텍스트에서 JSON 블록만 추출(코드펜스·서두문장 관대 처리)."""
    if not text:
        return None
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
    stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(stripped[start:end + 1])
    except json.JSONDecodeError:
        return None


def _claude_bin() -> str | None:
    return shutil.which("claude")


def run_audit_claude(prompt: str, timeout: int = 900, model: str = "claude-sonnet-4-6") -> dict:
    """
    headless claude 감사 호출(welly_auto_runner의 LIVE 호출 패턴 재사용). 읽기전용 분석
    전용이라 --permission-mode plan(편집 불가)로 호출한다.

    ★--safe-mode(2026-08-17 배662 수리): 실측 — 같은 53KB 페이지가 이 플래그 없이는 221초
    (240초 타임아웃 코앞), 있으면 진짜 원인이 CLAUDE.md·메모리·플러그인·훅 로딩(콘텐츠 크기와
    무관한 매 호출 고정비)이었음이 드러난다 — 이 감사는 순수 텍스트 분석뿐이라 그런 컨텍스트가
    애초에 필요 없다. --bare는 더 강력하지만 ANTHROPIC_API_KEY를 강제해(OAuth·키체인 안 읽음)
    이 계정 로그인 방식과 안 맞아 인증이 깨진다 — 확인 후 배제. --safe-mode는 인증 방식을
    그대로 두고 훅·플러그인·CLAUDE.md만 끈다.
    반환: {"ok": bool, "candidates": list, "raw": str, "error": str|None}
    """
    claude_bin = _claude_bin()
    if not claude_bin:
        return {"ok": False, "candidates": [], "raw": "", "error": "claude CLI 미설치(PATH 미해결)"}

    cmd = [
        claude_bin, "-p",
        "--model", model,
        "--permission-mode", "plan",
        "--output-format", "text",
        "--safe-mode",
    ]
    try:
        proc = subprocess.run(
            cmd, input=prompt, cwd=_PROJECT_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        raw = proc.stdout or ""
    except subprocess.TimeoutExpired:
        return {"ok": False, "candidates": [], "raw": "", "error": f"타임아웃({timeout}s)"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "candidates": [], "raw": "", "error": f"{type(e).__name__}: {e}"}

    parsed = _extract_json(raw)
    if parsed is None:
        return {"ok": False, "candidates": [], "raw": raw, "error": "JSON 파싱 실패"}
    candidates = parsed.get("candidates", []) if isinstance(parsed, dict) else []
    if not isinstance(candidates, list):
        candidates = []
    return {"ok": True, "candidates": candidates, "raw": raw, "error": None}


def verify_zero_consumers(symbol: str, declaring_path: str, repo_root: str | None = None) -> dict:
    """
    symbol(클래스명/id/함수명 등)을 리포 전체에서 git grep -F로 확인해, declaring_path 내
    "선언 자체" 외에 소비자가 0건인지 검증한다(읽기전용 — 부작용 없음).
    보수적 판정: declaring_path 내 매치가 2건 이상이면(선언+재사용) 소비자 존재로 간주.
    반환: {"zero": bool, "match_count": int, "reason": str}
    """
    repo_root = repo_root or _PROJECT_ROOT
    symbol = (symbol or "").strip()
    if not symbol:
        return {"zero": False, "match_count": -1, "reason": "symbol 비어있음 — 안전 우선 스킵"}
    try:
        out = subprocess.run(
            ["git", "grep", "-n", "-F", symbol],
            cwd=repo_root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
    except Exception as e:  # noqa: BLE001
        return {"zero": False, "match_count": -1, "reason": f"git grep 실행 실패: {e}"}

    if out.returncode not in (0, 1):
        return {
            "zero": False, "match_count": -1,
            "reason": f"git grep 오류(rc={out.returncode}): {out.stderr.strip()[:200]}",
        }

    lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
    norm_declaring = declaring_path.replace("\\", "/")
    same_file = [ln for ln in lines if ln.replace("\\", "/").startswith(norm_declaring + ":")]
    other_file = [ln for ln in lines if not ln.replace("\\", "/").startswith(norm_declaring + ":")]

    # ★한 건도 안 잡히면 "쓰는 데가 없다"가 아니라 "찾지 못했다"이다 (배507 · 2026-08-13).
    #   git grep 은 **추적 중인 파일만** 본다. 선언이 있는 파일이 .gitignore 대상이거나 아직
    #   커밋 전이면 선언조차 0건으로 나오고, 그 상태가 그대로 '소비자 0건 = 자동삭제 가능'이 된다.
    #   선언은 반드시 잡혀야 정상이므로, 0건이면 판정을 거부한다(안전측).
    if not lines:
        return {"zero": False, "match_count": 0,
                "reason": "선언조차 검색에 안 잡힘 — 추적 안 되는 파일일 수 있다. 판정 거부(안전측)"}

    zero = (len(other_file) == 0) and (len(same_file) <= 1)
    reason = (
        "소비자 0건(선언 자체만) — 자동삭제 가능"
        if zero else
        f"소비자 {len(lines)}건 확인(선언 외 참조 존재) — 자동삭제 스킵·제안으로 강등"
    )
    return {"zero": zero, "match_count": len(lines), "reason": reason}


def check_parse_integrity(html_text: str) -> dict:
    """
    <script>/<style>/<div> 태그 균형 러프 점검(완전한 HTML 파서는 아님 — 대규모 블록 삭제 시
    짝 깨짐을 잡아내는 안전 가드). 반환: {"ok": bool, "issues": list[str]}
    """
    issues = []
    checks = [
        ("script", r"<script\b[^>]*>", r"</script\s*>"),
        ("style", r"<style\b[^>]*>", r"</style\s*>"),
    ]
    for name, open_pat, close_pat in checks:
        opens = len(re.findall(open_pat, html_text, re.IGNORECASE))
        closes = len(re.findall(close_pat, html_text, re.IGNORECASE))
        if opens != closes:
            issues.append(f"<{name}> 태그 불균형(open={opens}, close={closes})")

    open_div = len(re.findall(r"<div\b", html_text, re.IGNORECASE))
    close_div = len(re.findall(r"</div\s*>", html_text, re.IGNORECASE))
    if open_div != close_div:
        issues.append(f"<div> 태그 불균형(open={open_div}, close={close_div})")

    return {"ok": not issues, "issues": issues}


def apply_category_a(content: str, candidate: dict, declaring_path: str) -> dict:
    """
    카테고리 A 후보 1건 적용 시도(순수 — content 원본을 바꾸지 않고 결과만 반환).
    3중 게이트: grep-0(symbol) → snippet 파일 내 고유 1회 매치 → 적용 후 파싱 무결성.
    하나라도 실패하면 applied=False(제안으로 강등), content는 원본 그대로 반환.
    반환: {"applied": bool, "content": str, "reason": str}
    """
    symbol = (candidate.get("symbol") or "").strip()
    snippet = candidate.get("snippet") or ""

    if not symbol:
        return {"applied": False, "content": content, "reason": "symbol 없음 — grep-0 검증 불가, 자동적용 스킵"}
    if not snippet.strip():
        return {"applied": False, "content": content, "reason": "snippet 없음 — 정확한 삭제 범위 불명, 자동적용 스킵"}

    check = verify_zero_consumers(symbol, declaring_path)
    if not check["zero"]:
        return {"applied": False, "content": content, "reason": check["reason"]}

    occurrences = content.count(snippet)
    if occurrences != 1:
        return {
            "applied": False, "content": content,
            "reason": f"snippet이 파일 내 {occurrences}회 매치(1회 고유 아님) — 자동적용 스킵",
        }

    new_content = content.replace(snippet, "", 1)
    integrity = check_parse_integrity(new_content)
    if not integrity["ok"]:
        return {
            "applied": False, "content": content,
            "reason": f"적용 후 파싱 무결성 실패({'; '.join(integrity['issues'])}) — 롤백",
        }

    return {"applied": True, "content": new_content, "reason": check["reason"]}


def _git_commit_file(path: str, message_body: str, repo_root: str | None = None,
                      retries: int = 5, delay_sec: float = 2.0) -> str | None:
    """
    단일 파일 git add+commit(락 경합 시 비파괴 재시도 — 강제삭제·reset 금지).
    성공 시 새 HEAD 커밋 해시, 실패 시 None.
    """
    repo_root = repo_root or _PROJECT_ROOT
    msg = (
        f"chore(coo): 주간 페이지 위생 자동정리 — {os.path.basename(path)}\n\n"
        f"{message_body}\n\n"
        "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>\n"
        "Claude-Session: https://claude.ai/code/session_016oLhdsseB7CyDF6FM2rZj6"
    )
    for attempt in range(retries):
        add = subprocess.run(
            ["git", "add", path], cwd=repo_root, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if add.returncode != 0:
            if "index.lock" in (add.stderr or "") and attempt < retries - 1:
                time.sleep(delay_sec)
                continue
            return None

        # pathspec 강제(2026-07-20 시토·동시커밋 사고대응): path 로 커밋 스코프 —
        # add~commit 사이 다른 세션이 스테이징해둔 무관 파일이 섞여 들어가지 않는다.
        commit = subprocess.run(
            ["git", "commit", "-m", msg, "--", path], cwd=repo_root, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if commit.returncode == 0:
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            return head.stdout.strip() if head.returncode == 0 else None
        if "index.lock" in (commit.stderr or "") and attempt < retries - 1:
            time.sleep(delay_sec)
            continue
        return None
    return None


def write_proposal_file(per_target_results: list[dict], clevel_label: str,
                         date_str: str | None = None, out_dir: str | None = None) -> str:
    """카테고리별(A 자동적용됨/A~D 제안) 마크다운 정리안 생성. 반환: 파일 경로."""
    date_str = date_str or datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = out_dir or os.path.join(_PROJECT_ROOT, "status")
    path = os.path.join(out_dir, f"page_hygiene_proposal_{date_str}.md")

    lines = [
        f"# 주간 페이지 위생 정리안 — {date_str} (하위모델 감사 → GM 승인 대기)",
        "",
        f"자동화: scripts/weekly_page_hygiene.py · 대상: {clevel_label}",
        "",
    ]
    for r in per_target_results:
        t = r["target"]
        label = t.get("label", t.get("path"))
        lines.append(f"## {label} — `{t.get('path')}`")
        if not r.get("audit_ok"):
            lines.append(f"- ⚠️ 감사 실패: {r.get('error')}")
            lines.append("")
            continue

        applied = r.get("applied") or []
        if applied:
            lines.append(f"### 자동 적용됨 ({len(applied)}건)")
            for c in applied:
                lines.append(f"- [{c.get('kind')}] `{c.get('symbol')}` — {c.get('reason')} ({c.get('gate_reason')})")

        proposed = r.get("proposed") or []
        by_cat: dict[str, list] = {}
        for c in proposed:
            by_cat.setdefault((c.get("category") or "?").upper(), []).append(c)
        for cat in ["A", "B", "C", "D"]:
            items = by_cat.get(cat)
            if not items:
                continue
            lines.append(f"### {cat}. {CATEGORY_LABELS.get(cat, cat)} ({len(items)}건)")
            for c in items:
                tag = " · 자동적용 조건 충족(다음 GM go 시 적용 예정)" if c.get("would_auto_apply") else ""
                # ★지울 대상 이름을 반드시 앞에 적는다 (배507 · 2026-08-10 실사고).
                #   전에는 위치와 사유만 적었다. 사유 문장에 **살아있는 다른 함수 이름**이
                #   등장하면(예: "…같은 역할을 usedAnnual2026() 이 수행") 읽는 사람은 그
                #   함수가 지워지는 줄 안다. 실제로 웰리가 그렇게 읽고 "활성 함수를 죽은
                #   코드로 찍었다"고 배를 띄웠는데, 판정기는 정상이었고 제안서 표기가 문제였다.
                #   무엇이 지워지는지 안 보이면 사람이 확인할 수가 없다.
                sym = (c.get("symbol") or "").strip()
                head = f"`{sym}`" if sym else "⚠️ 대상 이름 없음(자동적용 불가)"
                lines.append(f"- [{c.get('kind')}] {head} — {c.get('location', '')} — {c.get('reason')}{tag}")
                if c.get("gate_reason"):
                    lines.append(f"  - 게이트: {c['gate_reason']}")

        if not applied and not proposed:
            lines.append("- (정리 후보 없음)")
        lines.append("")

    os.makedirs(out_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def build_telegram_summary(apply_total: int, proposal_total: int, commit_count: int,
                            proposal_path: str, apply_gate: bool, error_count: int = 0) -> str:
    gate_note = "라이브(자동삭제 ON)" if apply_gate else "제안모드(자동삭제 OFF — 첫 주 dry)"
    rel_path = os.path.relpath(proposal_path, _PROJECT_ROOT).replace("\\", "/")
    lines = [
        "🧹 <b>주간 페이지 위생 자동화</b> — 시토",
        f"모드: {gate_note}",
        f"자동 적용: {apply_total}건 (커밋 {commit_count}건)",
        f"제안: {proposal_total}건",
        f"정리안 기록: {rel_path}",
    ]
    if error_count:
        lines.append(f"⚠️ 감사 실패: {error_count}건(claude 호출/파싱 오류 — 로그 확인 필요)")
    return "\n".join(lines)


def dispatch_proposal_ship(proposal_total: int, proposal_path: str) -> dict:
    """정리안을 **배로도** 올린다 — 파일만 쓰면 아무도 안 읽기 때문이다.

    ★2026-08-04 시토(배316). 이 감사는 3주(07-19·07-26·08-02) 동안 정상 작동해
    죽은 코드 후보를 실제로 찾아냈는데, **그 제안을 반영한 커밋이 0건**이었다.
    원인은 감지가 아니라 **도착지**다 — 결과가 status/ 아래 .md 파일로만 남고
    사람이 보는 목록(항로)에는 한 번도 오르지 않았다. 오늘 같은 종류의 결함
    (산출물이 만들어만 지고 사람에게 안 닿음)을 저장소 전반에서 고쳤고, 이건
    그 마지막 조각이다.

    - 받는 쪽 = 웰리(ceo). 대상이 실무진이 여는 페이지라 프론트 라인 소관이다.
    - 제목을 매주 같게 둔다 → queue_dispatch 가 같은 제목의 열린 배를 새로 만들지
      않고 갱신한다(배가 매주 늘지 않는다).
    - 찾은 게 없으면 배도 안 만든다 — 빈 배는 그 자체로 소음이다.
    - 실패해도 주간 감사는 계속된다(fail-soft). 이 배선 때문에 감사가 멈추면 안 된다.
    """
    if proposal_total <= 0:
        return {"ok": True, "skipped": "정리 후보 0건 — 배 생성 안 함"}
    rel = os.path.relpath(proposal_path, _PROJECT_ROOT).replace("\\", "/")
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(_PROJECT_ROOT, "scripts", "queue_dispatch.py"),
             "--to", "ceo", "--sender", "cto",
             "--title", "주간 페이지 위생 — 이번 주 정리 후보 검토",
             "--note", (f"자동 감사가 페이지 정리 후보 {proposal_total}건을 찾았습니다. "
                        f"상세=`{rel}`.\n\n"
                        "이 배는 매주 일요일 감사가 갱신합니다(같은 제목이라 새로 늘지 않습니다). "
                        "판단할 것은 하나입니다 — 이번 주 후보 중 실제로 지울 것을 고르는 것. "
                        "고르면 시토가 실행합니다.\n\n"
                        "※ 배316 배경: 이 감사는 3주간 정상 작동했지만 결과가 파일로만 남아 "
                        "반영 커밋이 0건이었습니다. 그래서 결과를 항로로 올리게 바꿨습니다."),
             "--next", "이번 주 정리 후보 중 반영할 것 선택 → 시토가 실행",
             "--priority", "⛵돛단배", "--audience", "office",
             "--reversible", "yes", "--work-type", "update"],
            cwd=_PROJECT_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
        )
        return {"ok": r.returncode == 0, "stdout": (r.stdout or "")[-300:]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def send_telegram_summary(text: str) -> dict:
    agents_dir = os.path.join(_PROJECT_ROOT, "wellperion-agents")
    if agents_dir not in sys.path:
        sys.path.insert(0, agents_dir)
    try:
        from telegram_notifier import TelegramNotifier  # noqa: E402
        return TelegramNotifier().send(text)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _append_log(entry: dict, path: str | None = None) -> None:
    path = path or DEFAULT_LOG_PATH
    entry = dict(entry)
    entry.setdefault("at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _run_audit_chunked(target: dict, content: str, claude_timeout: int, model: str) -> dict:
    """content가 CHUNK_MAX_CHARS 이하면 지금처럼 1회 호출. 넘으면 여러 조각으로 나눠 각각
    감사하고 후보를 합친다(부분 실패해도 성공한 조각 후보는 버리지 않는다 — 조용히 전부
    버려지던 게 이번 수리의 핵심이라 일부 조각 성공을 온전한 실패로 뭉개면 안 된다).
    반환: {"ok": bool, "candidates": list, "error": str|None(부분 실패 시 경고만)}
    """
    chunks = _split_content_chunks(content)
    all_candidates: list[dict] = []
    chunk_errors: list[str] = []
    for i, chunk in enumerate(chunks):
        prompt = build_audit_prompt(target, chunk, chunk_index=i, chunk_total=len(chunks))
        audit = run_audit_claude(prompt, timeout=claude_timeout, model=model)
        if audit["ok"]:
            all_candidates.extend(audit["candidates"])
        else:
            chunk_errors.append(f"조각 {i + 1}/{len(chunks)}: {audit['error']}")

    if chunk_errors and not all_candidates:
        return {"ok": False, "candidates": [], "error": "; ".join(chunk_errors)}
    if chunk_errors:
        print(f"[weekly_page_hygiene] {target.get('label')} 일부 조각 실패(나머지로 계속): "
              f"{'; '.join(chunk_errors)}", file=sys.stderr)
    return {"ok": True, "candidates": all_candidates, "error": None}


def _audit_one_target(target: dict, working_content: str, apply_gate: bool, force_dry_run: bool,
                       claude_timeout: int, model: str) -> dict:
    """
    target 1개(페이지 또는 섹션) 감사 + (게이트 통과 시) 카테고리 A 적용 시도.
    working_content = 이 target 감사 시점의 현재 파일 내용(같은 파일을 공유하는 앞선 target의
    적용 결과가 이미 반영된 상태일 수 있음).
    반환: {"target", "audit_ok", "error", "applied"(list), "proposed"(list), "content"(str, 최신)}
    """
    audit = _run_audit_chunked(target, working_content, claude_timeout, model)
    if not audit["ok"]:
        return {
            "target": target, "audit_ok": False, "error": audit["error"],
            "applied": [], "proposed": [], "content": working_content,
        }

    domain_locked = target.get("clevel") in AUTO_APPLY_LOCKED_CLEVELS
    live_apply = apply_gate and not force_dry_run and not domain_locked
    applied: list[dict] = []
    proposed: list[dict] = []
    content = working_content

    def _is_false_positive(tpath: str, c: dict) -> bool:
        combined = (c.get("symbol") or "") + (c.get("snippet") or "")
        return any(pp in tpath and sp in combined for pp, sp in FALSE_POSITIVE_EXCLUSIONS)

    for cand in audit["candidates"]:
        if _is_false_positive(target["path"], cand):
            continue
        cat = (cand.get("category") or "").strip().upper()
        if cat != "A":
            proposed.append({**cand, "gate_reason": "", "would_auto_apply": False})
            continue

        if live_apply:
            result = apply_category_a(content, cand, target["path"])
            if result["applied"]:
                content = result["content"]
                applied.append({**cand, "gate_reason": result["reason"]})
            else:
                proposed.append({**cand, "gate_reason": result["reason"], "would_auto_apply": False})
        elif domain_locked:
            reason = f"자동적용 잠김(소유={target.get('clevel')} 도메인 · 사람이 판단)"
            print(f"[weekly_page_hygiene] {reason} — {target.get('label')} / {cand.get('symbol')}", file=sys.stderr)
            proposed.append({**cand, "gate_reason": reason, "would_auto_apply": False})
        else:
            symbol = (cand.get("symbol") or "").strip()
            snippet = cand.get("snippet") or ""
            if symbol and snippet.strip() and content.count(snippet) == 1:
                check = verify_zero_consumers(symbol, target["path"])
            else:
                check = {"zero": False, "reason": "symbol/snippet 불충분 — grep-0 미리보기 불가"}
            proposed.append({**cand, "gate_reason": check.get("reason", ""), "would_auto_apply": bool(check.get("zero"))})

    return {
        "target": target, "audit_ok": True, "error": None,
        "applied": applied, "proposed": proposed, "content": content,
    }


def run_pipeline(clevel: str | None = "coo", apply: bool | None = None, force_dry_run: bool = False,
                  claude_timeout: int = 300, model: str = "claude-sonnet-4-6",
                  targets: list[dict] | None = None, notify: bool = True,
                  log_path: str | None = None) -> dict:
    """
    주간 페이지 위생 파이프 1회 실행.
    apply=None이면 env PAGE_HYGIENE_APPLY로 판단(기본 OFF). force_dry_run=True면 게이트
    설정과 무관하게 이번 실행만 무조건 미적용(검증용 — --dry-run CLI 플래그가 이걸 켠다).

    같은 물리 파일(예: 메인가이드 O1~O4)을 가리키는 target들은 그룹으로 묶어, 앞선 target의
    적용 결과를 다음 target 감사에 반영한 뒤(순차 처리) 파일당 1회만 write+commit한다.

    반환: {"per_target_results", "commits", "apply_total", "proposal_total", "error_total",
           "proposal_path", "summary_text", "apply_gate", "telegram_result"}
    """
    targets = targets if targets is not None else load_targets(clevel)
    apply_gate = _apply_live() if apply is None else apply
    clevel_label = clevel or "전체"

    by_path: dict[str, list[dict]] = {}
    for t in targets:
        by_path.setdefault(t["path"], []).append(t)

    per_target_results: list[dict] = []
    commits: list[dict] = []
    apply_total = 0
    proposal_total = 0
    error_total = 0

    for path, group in by_path.items():
        abs_path = os.path.join(_PROJECT_ROOT, path)
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                original_content = f.read()
        except Exception as e:  # noqa: BLE001
            for t in group:
                per_target_results.append({
                    "target": t, "audit_ok": False, "error": f"파일 읽기 실패: {e}",
                    "applied": [], "proposed": [],
                })
                error_total += 1
            continue

        working_content = original_content
        group_applied_summary: list[str] = []

        for t in group:
            r = _audit_one_target(
                t, working_content, apply_gate=apply_gate, force_dry_run=force_dry_run,
                claude_timeout=claude_timeout, model=model,
            )
            working_content = r.pop("content")
            per_target_results.append(r)
            if not r["audit_ok"]:
                error_total += 1
                _append_log({"event": "audit_error", "path": path, "label": t.get("label"), "error": r["error"]}, log_path)
                continue
            apply_total += len(r["applied"])
            proposal_total += len(r["proposed"])
            for c in r["applied"]:
                group_applied_summary.append(f"- [{c.get('kind')}] `{c.get('symbol')}` — {c.get('reason')}")

        if working_content != original_content:
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(working_content)
            commit_hash = _git_commit_file(path, "\n".join(group_applied_summary) or "(자동 적용분)")
            commits.append({"path": path, "commit": commit_hash})
            _append_log({"event": "applied_commit", "path": path, "commit": commit_hash,
                         "applied_count": len(group_applied_summary)}, log_path)

    proposal_path = write_proposal_file(per_target_results, clevel_label)
    # 제안서 자체도 커밋한다(2026-08-06 시토) — 안 하면 GM·웰리 화면까지 못 간다.
    #   배로는 이미 올라가는데(dispatch_proposal_ship) 배가 가리키는 파일이 이 PC 작업트리에만
    #   남아 있었다. 실측: 08-02 생성분이 4일째 미커밋, 앞선 2회(07-19·07-26)는 남의 커밋에
    #   우연히 딸려 들어가 회수됐다. 커밋 실패해도 감사는 계속된다(fail-soft — 반환값 무시).
    _git_commit_file(proposal_path, f"정리 후보 {proposal_total}건 · 대상 {clevel_label}")
    summary_text = build_telegram_summary(
        apply_total, proposal_total, len(commits), proposal_path, apply_gate, error_total,
    )
    dispatch_proposal_ship(proposal_total, proposal_path)

    telegram_result = None
    if notify:
        # ★배10011(2026-07-24, GM 승인) — 직접 발송 대신 일요일 주간묶음(sunday_weekly_bundle)에
        # 적재만 한다. 실제 발송은 weekly_self_review.py(일요일 10:30, 가장 늦게 도는 스크립트)가
        # 이 pending을 소비해 한 통으로 합쳐 보낸다(수신방=GM_DM, 기존과 동일 — 방 변경 없음).
        _scr_dir = os.path.dirname(os.path.abspath(__file__))
        if _scr_dir not in sys.path:
            sys.path.insert(0, _scr_dir)
        import weekly_bundle_pending as _bundle  # noqa: E402
        _bundle.append("sunday_weekly_bundle", source="weekly_page_hygiene", text=summary_text)
        telegram_result = {"ok": True, "absorbed": "sunday_weekly_bundle"}

    _append_log({
        "event": "run_summary", "clevel": clevel_label, "apply_gate": apply_gate,
        "apply_total": apply_total, "proposal_total": proposal_total,
        "error_total": error_total, "commits": len(commits),
    }, log_path)

    return {
        "per_target_results": per_target_results,
        "commits": commits,
        "apply_total": apply_total,
        "proposal_total": proposal_total,
        "error_total": error_total,
        "proposal_path": proposal_path,
        "summary_text": summary_text,
        "apply_gate": apply_gate,
        "telegram_result": telegram_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="주간 페이지 위생 자동화 — 하위모델 감사 → A(죽은코드) grep-0 게이트 통과 시 자동삭제, B/C/D는 제안만"
    )
    parser.add_argument("--clevel", default="coo", help="대상 C-Level(기본 coo). 'all'이면 전체 config 대상")
    parser.add_argument("--dry-run", action="store_true", help="PAGE_HYGIENE_APPLY=1이어도 이번 실행만 강제 미적용(검증용)")
    parser.add_argument("--no-notify", action="store_true", help="텔레그램 요약 발송 생략(검증용)")
    # ★300 → 900 (2026-08-24 시토 · 실측 근거).
    # 08-16 회차 감사 실패 25건 · 08-23 회차 21건이 전부 "타임아웃(300s)" 하나였다. 큰 페이지
    # (시설부 체계·지원부 체계·메인가이드 O1/O4·문의회원)가 매주 같은 자리에서 잘렸고, 그만큼이
    # 검사 없이 버려졌다. 같은 대상 3건을 900초로 재현하니 타임아웃 0건 — 값이 원인이 맞다.
    # 타임아웃은 상한이지 소요가 아니라, 제때 끝나는 조각의 실행 시간은 이 값을 올려도 늘지 않는다.
    # (남은 실패 1건은 "JSON 파싱 실패" 로 원인이 다르다 — 모델 응답 형식 문제, 별건.)
    parser.add_argument("--claude-timeout", type=int, default=900, help="조각(청크)당 headless claude 타임아웃(초)")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="감사에 사용할 모델")
    parser.add_argument("--limit", type=int, default=None, help="대상 target 수 제한(검증용 — 앞에서부터 N개만)")
    args = parser.parse_args()

    clevel = None if args.clevel == "all" else args.clevel
    targets = load_targets(clevel)
    if args.limit:
        targets = targets[: args.limit]

    result = run_pipeline(
        clevel=clevel, force_dry_run=args.dry_run, claude_timeout=args.claude_timeout,
        model=args.model, targets=targets, notify=not args.no_notify,
    )

    print("=" * 60)
    print(f"[weekly_page_hygiene] 대상 {len(targets)}건 | apply_gate={result['apply_gate']} | force_dry_run={args.dry_run}")
    print(f"자동 적용: {result['apply_total']}건 (커밋 {len(result['commits'])}건)")
    print(f"제안: {result['proposal_total']}건 | 감사 실패: {result['error_total']}건")
    print(f"정리안: {result['proposal_path']}")
    for c in result["commits"]:
        print(f"  커밋: {c['path']} -> {c['commit']}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
