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
    {"clevel": "coo", "label": "강습팀 업장관리", "path": "3. 웰페리온 가이드/coo/check/강습팀 업장관리.html"},
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
    {"clevel": "cmo", "label": "마케팅현황대시보드", "path": "3. 웰페리온 가이드/cmo/funnel/마케팅현황대시보드.html"},
    {"clevel": "cmo", "label": "문의흐름지도", "path": "3. 웰페리온 가이드/cmo/funnel/문의흐름지도.html"},
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
    {"clevel": "shared", "label": "AI운영한장", "path": "3. 웰페리온 가이드/AI운영한장.html"},
    {"clevel": "shared", "label": "전사회의", "path": "3. 웰페리온 가이드/전사회의.html"},
    {"clevel": "shared", "label": "웰페리온 대시보드(웹)", "path": "3. 웰페리온 가이드/wellperion_dashboard_web.html"},
    # ── shared 3 — 리다이렉트 스텁(감사 가치 낮으나 GM 지시로 포함) ──
    {"clevel": "shared", "label": "index(리다이렉트 스텁)", "path": "3. 웰페리온 가이드/index.html"},
    {"clevel": "shared", "label": "항해지도(리다이렉트 스텁)", "path": "3. 웰페리온 가이드/항해지도.html"},
    {"clevel": "shared", "label": "northstar_today(리다이렉트 스텁)", "path": "3. 웰페리온 가이드/northstar_today.html"},
]

DEFAULT_LOG_PATH = os.path.join(_PROJECT_ROOT, "status", "weekly_page_hygiene_log.jsonl")
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


# ── 감사 프롬프트 조립 (순수 함수) ──
def build_audit_prompt(target: dict, content: str) -> str:
    anchor = target.get("anchor")
    scope_note = (
        f"\n\n★분석 범위 한정: id=\"{anchor}\" 섹션(및 그 하위 요소)만 후보 대상으로 삼는다. "
        "다른 섹션 내용은 후보에 포함하지 마라(참고용으로만 읽어라)."
        if anchor else ""
    )
    return (
        "너는 웰페리온 ERP 페이지 위생 감사관이다. 아래 HTML 페이지 전체를 검토해 "
        "무분별·무의미·중복·죽은 콘텐츠 후보를 찾아라. 너는 파일을 수정하지 않는다 — "
        "오직 JSON 분석 결과만 출력한다.\n\n"
        f"페이지: {target.get('label')} ({target.get('path')}){scope_note}\n\n"
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


def run_audit_claude(prompt: str, timeout: int = 420, model: str = "claude-sonnet-4-6") -> dict:
    """
    headless claude 감사 호출(welly_auto_runner의 LIVE 호출 패턴 재사용). 읽기전용 분석
    전용이라 --permission-mode plan(편집 불가)로 호출한다.
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
                lines.append(f"- [{c.get('kind')}] {c.get('location', '')} — {c.get('reason')}{tag}")
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


def _audit_one_target(target: dict, working_content: str, apply_gate: bool, force_dry_run: bool,
                       claude_timeout: int, model: str) -> dict:
    """
    target 1개(페이지 또는 섹션) 감사 + (게이트 통과 시) 카테고리 A 적용 시도.
    working_content = 이 target 감사 시점의 현재 파일 내용(같은 파일을 공유하는 앞선 target의
    적용 결과가 이미 반영된 상태일 수 있음).
    반환: {"target", "audit_ok", "error", "applied"(list), "proposed"(list), "content"(str, 최신)}
    """
    prompt = build_audit_prompt(target, working_content)
    audit = run_audit_claude(prompt, timeout=claude_timeout, model=model)
    if not audit["ok"]:
        return {
            "target": target, "audit_ok": False, "error": audit["error"],
            "applied": [], "proposed": [], "content": working_content,
        }

    live_apply = apply_gate and not force_dry_run
    applied: list[dict] = []
    proposed: list[dict] = []
    content = working_content

    for cand in audit["candidates"]:
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
                  claude_timeout: int = 240, model: str = "claude-sonnet-4-6",
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
    summary_text = build_telegram_summary(
        apply_total, proposal_total, len(commits), proposal_path, apply_gate, error_total,
    )

    telegram_result = None
    if notify:
        telegram_result = send_telegram_summary(summary_text)

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
    parser.add_argument("--claude-timeout", type=int, default=240, help="페이지당 headless claude 타임아웃(초)")
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
