# -*- coding: utf-8 -*-
"""브랜드 드리프트 검증기 (2026-07-24 · 배64 후속).

정본 = ssot/brand.json — 브랜드 기준(색·폰트·로고·톤·CTA·금지어 포인터)의 기계 원천.
scripts/brand_constants.py 는 이제 이 파일을 읽는 로더다. 이 스크립트는 원천·로더·
사람용 화면(브랜드가이드.html)·금지어 원천이 서로 어긋난 지점만 잡아낸다.
읽기 전용이다 — 어떤 파일도 쓰지 않고, 커밋도 발행도 하지 않는다.

검사:
  A. 원천(ssot/brand.json) ↔ 로더 폴백(scripts/brand_constants.py _FALLBACK) 값 일치
  B. CTA 문구 — ssot/brand.json cta.CLEAN_CTA_TEXT ↔ scripts/cta_utm.py CLEAN_CTA_TEXT 리터럴
  C. 금지어 — ssot/forbidden_terms.json 의 모든 term 이 브랜드가이드.html 에 실제로 보이는지
     + brand.json.forbidden_terms 가 값 복사 없이 포인터로만 남아있는지
  D. 자산 파일 실존 — fonts/logo 가 가리키는 파일·디렉터리
  E. _source="브랜드가이드.html 에서 복사" 항목의 출처 생존(파일 존재 + 핵심 문자열 잔존)

사용:
  python scripts\\brand_check.py            # 사람이 읽는 요약
  python scripts\\brand_check.py --json      # 기계 판독용 JSON 병기

종료코드: 경고 0건=0, 1건 이상=1.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
BRAND_JSON = ROOT / "ssot" / "brand.json"
FORBIDDEN_JSON = ROOT / "ssot" / "forbidden_terms.json"
BRAND_CONSTANTS_PY = ROOT / "scripts" / "brand_constants.py"
CTA_UTM_PY = ROOT / "scripts" / "cta_utm.py"
BRAND_GUIDE_HTML = ROOT / "3. 웰페리온 가이드" / "cmo" / "brand" / "브랜드가이드.html"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


class Result:
    """검사 하나의 결과 묶음 — OK/WARN/INFO 라인을 모은다."""

    def __init__(self, name: str):
        self.name = name
        self.warns: list[str] = []
        self.infos: list[str] = []  # 알림(정보성 — 종료코드에 영향 없음, SSOT 갱신 권고)
        self.summary: str | None = None

    def warn(self, msg: str) -> None:
        self.warns.append(msg)

    def info(self, msg: str) -> None:
        self.infos.append(msg)

    @property
    def ok(self) -> bool:
        return not self.warns


def _hex_of(entry: dict) -> str:
    return str(entry.get("hex", "")).upper()


def check_a_fallback_sync(brand: dict) -> Result:
    """검사 A — brand.json 원천 값과 brand_constants.py _FALLBACK 하드코딩 값 일치."""
    r = Result("A. 원천↔로더 폴백 일치")
    if not BRAND_CONSTANTS_PY.exists():
        r.warn(f"로더 파일 없음: {_rel(BRAND_CONSTANTS_PY)}")
        return r
    text = BRAND_CONSTANTS_PY.read_text(encoding="utf-8", errors="replace")

    core = brand.get("colors", {}).get("core", {})
    # (원천 dict 키, 폴백에서 찾을 변수명) — 코어 색상 7종 + 듀오톤 2종
    color_keys = ["BEIGE", "BLACK_BG", "WHITE", "GRAY", "HIGHLIGHT", "CHIP_BEIGE", "SEP_LINE"]
    for key in color_keys:
        entry = core.get(key)
        if not entry:
            r.warn(f"brand.json colors.core 에 '{key}' 없음")
            continue
        rgb = tuple(entry["rgb"])
        m = re.search(rf'"{key}"\s*:\s*\(([^)]+)\)', text)
        if not m:
            r.warn(f"[{key}] brand_constants.py _FALLBACK 에서 rgb 튜플을 못 찾음")
            continue
        fallback_rgb = tuple(int(x.strip()) for x in m.group(1).split(","))
        if fallback_rgb != rgb:
            r.warn(f"[{key}] 원천 rgb={rgb} ≠ 폴백 rgb={fallback_rgb} — brand_constants.py _FALLBACK 갱신 필요")

    for key in ("DUOTONE_DARK", "DUOTONE_LIGHT"):
        val = core.get(key)
        m = re.search(rf'"{key}"\s*:\s*"([^"]+)"', text)
        if not m:
            r.warn(f"[{key}] brand_constants.py _FALLBACK 에서 문자열 값을 못 찾음")
        elif val and m.group(1).upper() != str(val).upper():
            r.warn(f"[{key}] 원천='{val}' ≠ 폴백='{m.group(1)}'")

    # 부서 프리셋 9종 — primary/background/accent/text/text_secondary/wordmark
    presets = brand.get("colors", {}).get("department_presets", {})
    fields = ("primary", "background", "accent", "text", "text_secondary")
    for pkey, preset in presets.items():
        # 프리셋 블록 = 이 키의 등장 지점부터 다음 프리셋 키 등장 지점까지(정규식 중첩
        # 매칭은 불안정해 문자열 탐색으로 블록 경계를 잡는다).
        wm = preset.get("wordmark", "")
        idx = text.find(f'"{pkey}"')
        if idx == -1:
            r.warn(f"[프리셋 {pkey}] brand_constants.py _FALLBACK 에 키 자체가 없음")
            continue
        # 다음 프리셋 키 등장 지점까지, 혹은 문자열 끝까지를 이 블록으로 본다
        next_idx = text.find('\n        "', idx + 1)
        block = text[idx: next_idx if next_idx != -1 else idx + 600]
        for field in fields:
            entry = preset.get(field)
            if not isinstance(entry, dict) or "rgb" not in entry:
                continue
            rgb = tuple(entry["rgb"])
            fm = re.search(rf'"{field}"\s*:\s*\(([^)]+)\)', block)
            if not fm:
                r.warn(f"[프리셋 {pkey}.{field}] 폴백 블록에서 값을 못 찾음")
                continue
            fallback_rgb = tuple(int(x.strip()) for x in fm.group(1).split(","))
            if fallback_rgb != rgb:
                r.warn(f"[프리셋 {pkey}.{field}] 원천 rgb={rgb} ≠ 폴백 rgb={fallback_rgb}")
        if wm and f'"wordmark": "{wm}"' not in block:
            r.warn(f"[프리셋 {pkey}.wordmark] 원천='{wm}' 이 폴백 블록에 없음")

    # 폰트·로고 경로 — brand.json 은 절대경로 문자열, 폴백은 PROJECT_ROOT 조합식이라
    # 값 자체가 아니라 '같은 상대 구성요소(파일명)'를 대조한다.
    fonts = brand.get("fonts", {})
    for key in ("FONT_BOLD", "FONT_SEMIBOLD", "FONT_MEDIUM"):
        val = fonts.get(key)
        if val:
            fname = Path(val).name
            if fname not in text:
                r.warn(f"[fonts.{key}] 원천 파일명 '{fname}' 이 brand_constants.py _FALLBACK 에 없음")

    logo = brand.get("logo", {})
    for key in ("LOGO_WHITE_ALPHA", "LOGO_BEIGE_ALPHA"):
        val = logo.get(key)
        if val:
            fname = Path(val).name
            if fname not in text:
                r.warn(f"[logo.{key}] 원천 파일명 '{fname}' 이 brand_constants.py _FALLBACK 에 없음")

    return r


def check_b_cta_text(brand: dict) -> Result:
    """검사 B — CTA 문구: brand.json cta.CLEAN_CTA_TEXT ↔ cta_utm.py CLEAN_CTA_TEXT 리터럴 정확 일치."""
    r = Result("B. CTA 문구 일치")
    ssot_val = brand.get("cta", {}).get("CLEAN_CTA_TEXT")
    if ssot_val is None:
        r.warn("brand.json 에 cta.CLEAN_CTA_TEXT 없음")
        return r
    if not CTA_UTM_PY.exists():
        r.warn(f"파일 없음: {_rel(CTA_UTM_PY)}")
        return r
    text = CTA_UTM_PY.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'^CLEAN_CTA_TEXT\s*=\s*"([^"]*)"', text, re.MULTILINE)
    if not m:
        r.warn(f"{_rel(CTA_UTM_PY)} 에서 CLEAN_CTA_TEXT = \"...\" 리터럴을 못 찾음")
        return r
    code_val = m.group(1)
    if code_val != ssot_val:
        r.warn(
            f"CTA 문구 불일치 — brand.json='{ssot_val}' (len={len(ssot_val)}) ≠ "
            f"cta_utm.py='{code_val}' (len={len(code_val)})"
        )
    return r


def check_c_forbidden_terms(brand: dict, forbidden: dict) -> Result:
    """검사 C — 금지어 원천(forbidden_terms.json) ↔ 사람 화면(브랜드가이드.html) 정합."""
    r = Result("C. 금지어 원천↔화면 정합")

    # C-1. brand.json.forbidden_terms 는 포인터여야 한다(값 복사 금지)
    ft_pointer = brand.get("forbidden_terms", {})
    if "terms" in ft_pointer or "정본" not in ft_pointer:
        r.warn("brand.json.forbidden_terms 가 포인터 형태가 아님(값이 복사됐을 위험) — "
               "'정본' 필드로 ssot/forbidden_terms.json 만 가리켜야 함")

    # C-2. forbidden_terms.json 의 모든 term 이 브랜드가이드.html 본문에 실제로 나타나는지
    if not BRAND_GUIDE_HTML.exists():
        r.warn(f"브랜드가이드 화면 파일 없음: {_rel(BRAND_GUIDE_HTML)}")
        return r
    html_text = BRAND_GUIDE_HTML.read_text(encoding="utf-8", errors="replace")

    terms = forbidden.get("terms", [])
    missing = 0
    for entry in terms:
        term = entry.get("term", "")
        if not term:
            continue
        if term not in html_text:
            missing += 1
            r.warn(f"금지어 '{term}' 이 브랜드가이드.html 본문에 안 보임(기계는 잡지만 사람 화면엔 없음)")
    r.summary = f"경고 {len(r.warns)}건, 알림 {len(r.infos)}건 (금지어 {len(terms)}종 중 화면 미노출 {missing}건)"
    return r


def check_d_assets(brand: dict) -> Result:
    """검사 D — brand.json 이 가리키는 폰트 파일·로고 디렉터리 실존."""
    r = Result("D. 자산 파일 실존")
    fonts = brand.get("fonts", {})
    for key, val in fonts.items():
        p = Path(val)
        if not p.exists():
            r.warn(f"[fonts.{key}] 파일 없음: {val}")

    logo = brand.get("logo", {})
    for key in ("LOGO_DIR", "LOGO_WHITE_ALPHA", "LOGO_BEIGE_ALPHA"):
        val = logo.get(key)
        if not val:
            continue
        p = Path(val)
        if not p.exists():
            r.warn(f"[logo.{key}] 없음: {val}")
    return r


# 검사 E — _source 가 "브랜드가이드.html 에서 복사"인 항목들의 출처 생존 확인.
# (json 경로 표시용 라벨, brand.json 안에서 항목을 찾는 경로, 화면에 남아있어야 할 핵심
#  문자열 목록 — 이 중 하나라도 남아있으면 "생존"으로 본다. 표현이 다듬어져도 핵심 문구·
#  숫자값 중 하나는 보통 남기 때문에 과탐(전부 없어져야 경고)을 피한다).
E_SOURCE_PROBES = [
    ("colors.account_tracks", ["63BBA0", "2E6E5B"]),
    ("colors.partner_exceptions", ["8B1A2F"]),
    ("logo.account_usage", ["W 심볼만", "풀 로고"]),
    ("hashtag", ["한남동골프", "맨 끝 2개 고정"]),
    ("tone", ["1인칭 기록", "손그림 마커"]),
    ("account_separation", ["W 심볼만", "럭셔리 매거진"]),
]


def check_e_source_survival(brand: dict) -> Result:
    """검사 E — _source="브랜드가이드.html 에서 복사" 항목의 출처 생존(알림만·경고 아님)."""
    r = Result("E. 화면 출처 생존")
    if not BRAND_GUIDE_HTML.exists():
        r.info(f"브랜드가이드 화면 파일 없음: {_rel(BRAND_GUIDE_HTML)} — _source 항목 전수 생존 확인 불가")
        return r
    html_text = BRAND_GUIDE_HTML.read_text(encoding="utf-8", errors="replace")

    survived, lost = 0, 0
    for label, probes in E_SOURCE_PROBES:
        found = [p for p in probes if p in html_text]
        if found:
            survived += 1
        else:
            lost += 1
            r.info(f"[{label}] _source 표시 항목이지만 브랜드가이드.html 에서 후보 문자열 전부 소실"
                   f"({', '.join(probes)}) — 표현이 다듬어졌을 수 있음, SSOT(brand.json) 갱신 필요 신호")
    r.summary = f"경고 0건, 알림 {len(r.infos)}건 (_source 항목 {len(E_SOURCE_PROBES)}건 중 생존 {survived}·소실 {lost})"
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description="브랜드 드리프트 검증기(읽기 전용)")
    ap.add_argument("--json", action="store_true", help="기계 판독용 JSON 결과도 출력")
    args = ap.parse_args()

    if not BRAND_JSON.exists():
        print(f"[ERROR] SSOT 없음: {_rel(BRAND_JSON)}")
        return 1
    brand = _read_json(BRAND_JSON)

    if not FORBIDDEN_JSON.exists():
        print(f"[ERROR] SSOT 없음: {_rel(FORBIDDEN_JSON)}")
        return 1
    forbidden = _read_json(FORBIDDEN_JSON)

    results = [
        check_a_fallback_sync(brand),
        check_b_cta_text(brand),
        check_c_forbidden_terms(brand, forbidden),
        check_d_assets(brand),
        check_e_source_survival(brand),
    ]

    total_warns = sum(len(r.warns) for r in results)
    print("=== 브랜드 드리프트 검증 결과 ===")
    for r in results:
        tag = "OK" if r.ok else "WARN"
        body = r.summary or f"경고 {len(r.warns)}건, 알림 {len(r.infos)}건"
        print(f"[{tag}] {r.name} — {body}")
        for w in r.warns:
            print(f"    ⚠ {w}")
        for i in r.infos:
            print(f"    ℹ {i}")
    print("-----------------------------------")
    print(f"총 경고: {total_warns}건")

    if args.json:
        payload = {
            "ok": total_warns == 0,
            "total_warnings": total_warns,
            "checks": [
                {"name": r.name, "warnings": r.warns, "infos": r.infos}
                for r in results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 1 if total_warns else 0


if __name__ == "__main__":
    sys.exit(main())
