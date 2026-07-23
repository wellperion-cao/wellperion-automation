#!/usr/bin/env python3
"""공유 모듈 매퍼 — 배(ship) → 북극성 모듈 단일 소스 (voyage_module_map.py)

★ 이 파일은 '배→모듈' 배정의 **단일 진실**이다. 재구축·중복 금지.
  두 소비자가 **둘 다 이 파일을 import** 한다 (L01 한 곳만):
    1. scripts/northstar_recommender.py — 일일 북극성 추천 카드(모듈 그룹핑)
    2. (예정) 시토 '항해 지도' 페이지 빌더 — 스펙 .omc/specs/deep-interview-voyage-map-module-grouping.md
  ↳ 항해 지도 ship/스펙에 "이 헬퍼 공유·재구축 금지" 핸드오프 남김.

설계 정본(잠금):
  - 대항목 = 북극성 모듈. 정의 = 3. 웰페리온 가이드/coo/bootsetup_matrix.json 의 role별 owns.
  - 배→role = 기존 clevel 필드. role 안 module = title·note 키워드 휴리스틱(classifyShip 패턴).
  - 배정 = 자동 추론 + 수동 교정. 배에 optional 'module' 필드 있으면 그 값 우선, 없으면 추론.
  - 불명확 = "기타" 폴백(수동 지정 대기). 새 모듈 체계 하드코딩 금지(owns 재사용).

공개 API:
  - load_modules(role_id) -> list[dict{id,label,href,desc,page_url,keywords}]
  - all_modules() -> dict{role_id: [module,...]}
  - module_for_ship(ship, role_id=None) -> dict  # 항상 dict 반환("기타" 폴백 포함)
  - page_url_for(href) -> str
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
from pathlib import Path

BASE_DIR = Path(r"C:\Users\jjky0\welperion-automation")
MATRIX_FILE = BASE_DIR / "3. 웰페리온 가이드" / "coo" / "bootsetup_matrix.json"

# Pages 배포 루트 = 가이드 폴더가 루트(가이드 접두사 금지 → 404, INC 참조 reference_pages_url_no_guide_prefix).
PAGES_BASE = "https://wellperion-cao.github.io/wellperion-automation/"

# "기타" 폴백 모듈(수동 지정 대기 대상 표시).
OTHER_MODULE = {
    "id": "기타",
    "label": "기타(모듈 미지정)",
    "href": "",
    "desc": "자동 추론 규칙이 불명확 — 담당 C레벨/웰리 수동 지정 대기",
    "page_url": "",
    "keywords": [],
}

# ── 모듈별 추가 키워드(휴리스틱 보강) ────────────────────────────────────────
# key = 모듈 id(라벨 첫 토큰). owns 라벨·desc 만으론 약한 매칭을 보완하는 큐레이션.
# 새 모듈 체계가 아니라 '기존 owns 모듈'에 매칭 키워드만 얹는다.
_MODULE_KEYWORDS: dict[str, list[str]] = {
    # ── CMO ──
    "M1": ["콘텐츠", "제작", "슬라이드", "릴스", "카드뉴스", "이미지", "비주얼", "디자인",
           "compose", "barre", "ai시리즈", "ep", "발레", "썸네일", "영상", "movie"],
    "M2": ["대시보드", "집계", "전환", "문의흐름", "퍼널", "월간보고", "통계", "분석",
           "kpi", "리포트", "지도", "클릭", "노출"],
    "M3": ["발행", "검수", "review", "채널", "블로그", "카페", "인스타", "instagram",
           "당근", "카카오", "m5", "publish", "게시", "업로드", "watcher", "네이버"],
    # ── COO ──
    "O1": ["운영", "부서", "체계", "규정", "가이드카드", "매뉴얼", "a3", "업장", "조직",
           "회의", "리듬"],
    "O2": ["공지", "안내문", "게시판"],
    "O4": ["접수", "voc", "컴플레인", "이슈", "분실", "리셉션", "민원", "고충"],
    "S3": ["결재", "업무현황", "항로", "todo", "승인", "정책", "결재선"],
    # ── CTO ──
    "T1": ["기술", "서버", "jwt", "인증", "게이트", "보안", "인프라", "봇", "텔레그램",
           "알림", "헬스", "진단", "chat_id", "토큰", "pii", "세션", "접근통제"],
    "T2": ["자동화", "추천기", "북극성", "파이프라인", "스케줄", "자율", "watcher",
           "발행자동", "gm_aide", "자기학습", "스킬", "학습", "배관", "collector", "kpi측정"],
    # ── CPO ──
    "회원": ["회원", "문의", "등록", "멤버십", "강습", "달력", "cs", "상품", "요금",
             "유소년", "성인", "렌트", "비즈니스", "전환"],
    # ── CEO ──
    "home": ["전략", "통합", "오케스트레이션", "전사", "홈"],
    "G1": ["g1", "항로", "오늘의항로", "보드"],
    "S2": ["s2", "운영원칙", "r/r", "가이드허브", "erp"],
}


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def _module_id(label: str) -> str:
    """라벨 첫 토큰이 코드(M1/T2/O1/S2/G1 등)면 그걸 id로, 아니면 라벨 첫 단어."""
    label = (label or "").strip()
    if not label:
        return "기타"
    head = label.split()[0]
    if re.match(r"^[A-Za-z]\d+$", head) or head in ("home", "G1", "S2", "S3"):
        return head
    # 코드 없는 라벨(예: "통합 회원 관리") → 대표 키워드 id "회원" 매핑, 없으면 라벨.
    if "회원" in label:
        return "회원"
    return head


def page_url_for(href: str) -> str:
    """owns href(Pages 루트 상대경로) → 완전 URL. 한글=NFC 후 경로 인코딩, #fragment 보존."""
    href = (href or "").strip()
    if not href:
        return ""
    path, _, frag = href.partition("#")
    enc = urllib.parse.quote(_nfc(path), safe="/().")
    url = PAGES_BASE + enc
    if frag:
        url += "#" + frag
    return url


def _load_matrix() -> dict:
    try:
        return json.loads(MATRIX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"roles": []}


def load_modules(role_id: str) -> list[dict]:
    """role_id 의 owns 모듈 목록 → [{id,label,href,desc,page_url,keywords}]."""
    matrix = _load_matrix()
    role = next((r for r in matrix.get("roles", []) if r.get("id") == role_id), None)
    if not role:
        return []
    mods = []
    for o in role.get("owns", []):
        if not isinstance(o, dict):
            continue
        label = o.get("label", "")
        mid = _module_id(label)
        desc = o.get("desc", "")
        # 키워드 = 큐레이션 + 라벨 단어(코드 토큰 제외) + desc 단어(소문자)
        kw = list(_MODULE_KEYWORDS.get(mid, []))
        for w in re.split(r"[\s·,]+", _nfc(label)):
            w = w.strip().lower()
            if w and not re.match(r"^[a-z]\d+$", w) and len(w) >= 2:
                kw.append(w)
        for w in re.split(r"[\s·,()]+", _nfc(desc)):
            w = w.strip().lower()
            if len(w) >= 2:
                kw.append(w)
        mods.append({
            "id": mid,
            "label": label,
            "href": o.get("href", ""),
            "desc": desc,
            "page_url": page_url_for(o.get("href", "")),
            "keywords": sorted(set(kw)),
        })
    return mods


def all_modules() -> dict:
    matrix = _load_matrix()
    return {r.get("id"): load_modules(r.get("id")) for r in matrix.get("roles", [])}


def module_for_ship(ship: dict, role_id: str | None = None) -> dict:
    """배 → 소속 모듈 판정. 수동 교정('module' 필드) 우선, 없으면 title·note 키워드 휴리스틱.
    항상 dict 반환(매칭 실패 시 OTHER_MODULE '기타' 폴백)."""
    rid = (role_id or ship.get("clevel") or "").lower()
    mods = load_modules(rid)

    # 1) 수동 교정 우선 — module 필드가 있으면 그 id/label 로 owns 매칭(AC2)
    manual = str(ship.get("module", "") or "").strip()
    if manual:
        for m in mods:
            if manual.lower() in (m["id"].lower(), m["label"].lower()) or manual.lower() == m["id"].lower():
                return m
        # 수동값이 owns 에 없으면 그 값 그대로를 임시 모듈로(수동 지정 존중)
        return {"id": manual, "label": manual, "href": "", "desc": "(수동 지정)",
                "page_url": "", "keywords": []}

    # 2) 자동 추론 — title+note 텍스트 vs 각 모듈 keyword 점수(AC1)
    hay = _nfc(f"{ship.get('title','')} {ship.get('note','')}").lower()
    best, best_score = None, 0
    for m in mods:
        score = sum(1 for k in m["keywords"] if k and k in hay)
        if score > best_score:
            best, best_score = m, score
    if best and best_score > 0:
        return best

    # 3) 폴백 — role 에 owns 모듈이 정확히 1개면 그걸로(단일 모듈 role), 아니면 "기타"(AC3)
    if len(mods) == 1:
        return mods[0]
    return dict(OTHER_MODULE)


if __name__ == "__main__":
    import sys
    io_enc = getattr(sys.stdout, "reconfigure", None)
    if io_enc:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("[voyage_module_map] 모듈 매퍼 자가점검")
    for rid, mods in all_modules().items():
        print(f"\n== {rid} ({len(mods)} 모듈)")
        for m in mods:
            print(f"   [{m['id']}] {m['label']}  → {m['page_url']}")
    # 샘플 배 매핑
    samples = [
        {"clevel": "cmo", "title": "AI시리즈 ep31 슬라이드 제작", "note": ""},
        {"clevel": "cmo", "title": "블로그 검수 발행", "note": "review_queue"},
        {"clevel": "cto", "title": "텔레그램 알림 헬스체크", "note": "chat_id drift"},
        {"clevel": "cto", "title": "북극성 추천기 자동화 파이프라인", "note": ""},
        {"clevel": "cpo", "title": "강습 등록 원장", "note": ""},
        {"clevel": "coo", "title": "VOC 접수 게이트", "note": "컴플레인"},
        {"clevel": "cto", "title": "module 수동교정 예시", "note": "", "module": "T1"},
        {"clevel": "coo", "title": "정체불명 작업", "note": "xyz"},
    ]
    print("\n== 배 매핑 샘플")
    for s in samples:
        m = module_for_ship(s)
        print(f"   [{s['clevel']}] {s['title'][:30]:30s} → {m['id']} ({m['label']})")
