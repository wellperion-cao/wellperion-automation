"""구글(Apps Script) 의존 실측기 — 화면(HTML)마다 구글 웹앱 호출·서버 API 호출·서버끄기 플래그를 센다.
GM 지시 2026-09-14 「구글 삭제까지 마무리」· 시토 지시. 82% 같은 '줄 수 비율' 대신 실제 화면 수를 쓴다.

세는 범위: cbo·cfo·chro·cmo·coo·cpo·cto·erp (실제 ERP 화면이 있는 폴더).
reports·회사문서·home·gm·onboarding·dietcamp·counsel·public 은 화면이 아니라 뺐다
(정적 1회성 보고서·사내 문서라 분모를 부풀린다 — reports 70건 중 구글/서버 호출 있는 건 1건뿐 실측함).
그 안에서도 _archive·launchers·public 폴더는 지시대로 제외.

서버 쪽 구글 쓰기 호출 수(server_gas_calls)는 이 PC 에서 서버 DB 를 못 읽어 null 로 둔다.
시토가 서버 크론에서 채울 SQL(write_log 최근 24시간 · test 아닌 GAS 로 나간 건수, pushback 포함):
  SELECT count(*) FROM write_log
  WHERE at > now() - interval '24 hours'
    AND tenant_id != 'selftest'
    AND gas_status NOT IN ('test', 'skipped');
"""
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUIDE = REPO / "3. 웰페리온 가이드"
SCAN_ROOTS = ["cbo", "cfo", "chro", "cmo", "coo", "cpo", "cto", "erp"]
EXCLUDE_DIR_NAMES = {"_archive", "launchers", "public"}
NAWOOLM_LINES = {"cfo", "chro"}
# 폴더 밖에 있어도 나우열M 라인인 화면(AI 는 안 고친다 · 09-14 GM) — 폴더만 보면 AI 소관으로 잘못 찍힌다(2026-09-17 실측).
NAWOOLM_PATHS = {"coo/check/파트너팀_페이롤.html"}   # 강사 페이롤 · 정본 = 강사페이롤_DB 시트(cfo) + 바인딩 GAS 웹앱 · 나우열 09-17 작성

RE_GAS = re.compile(r"script\.google\.com/macros")
RE_API = re.compile(r"/api/")
RE_FLAG = re.compile(r"ERP_API_ON")


def owner_line(rel_path: str) -> str:
    top = rel_path.split("/", 1)[0]
    return "나우열M" if (top in NAWOOLM_LINES or rel_path in NAWOOLM_PATHS) else "AI"


def scan() -> dict:
    rows = []
    for root_name in SCAN_ROOTS:
        root = GUIDE / root_name
        if not root.is_dir():
            continue
        for f in root.rglob("*.html"):
            rel = f.relative_to(GUIDE)
            if EXCLUDE_DIR_NAMES & set(rel.parts[:-1]):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            has_gas = bool(RE_GAS.search(text))
            has_api = bool(RE_API.search(text))
            has_flag = bool(RE_FLAG.search(text))
            rows.append({
                "path": rel.as_posix(),
                "owner_line": owner_line(rel.as_posix()),
                "has_gas": has_gas,
                "has_api": has_api,
                "has_flag": has_flag,
            })

    gas_only = [r for r in rows if r["has_gas"] and not r["has_api"]]
    both = [r for r in rows if r["has_gas"] and r["has_api"]]
    server_only = [r for r in rows if r["has_api"] and not r["has_gas"]]

    return {
        "generated_at": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%dT%H:%M+09:00"),
        "scan_roots": SCAN_ROOTS,
        "excluded_dirs": sorted(EXCLUDE_DIR_NAMES),
        "screens_total": len(rows),
        "screens_gas_only": len(gas_only),
        "screens_both": len(both),
        "screens_server_only": len(server_only),
        "server_gas_calls": None,
        "list_gas_only": [{"path": r["path"], "owner_line": r["owner_line"]} for r in gas_only],
        "list_both": [{"path": r["path"], "owner_line": r["owner_line"]} for r in both],
    }


def write_json(data: dict) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    (REPO / "status" / "gas_dependency.json").write_text(text, encoding="utf-8")
    (GUIDE / "status" / "gas_dependency.json").write_text(text, encoding="utf-8")


def print_table(data: dict) -> None:
    print(f"전체 {data['screens_total']}장 · 구글만 {data['screens_gas_only']} · "
          f"폴백(구글+서버) {data['screens_both']} · 서버만 {data['screens_server_only']}")
    print(f"{'경로':<50} {'라인':<6} 상태")
    for r in data["list_gas_only"]:
        print(f"{r['path']:<50} {r['owner_line']:<6} 구글만")
    for r in data["list_both"]:
        print(f"{r['path']:<50} {r['owner_line']:<6} 폴백")


def _selfcheck():
    d = scan()
    # 세 갈래 합은 전체 이하(구글도 서버도 안 쓰는 정적 화면이 있을 수 있다)
    assert d["screens_gas_only"] + d["screens_both"] + d["screens_server_only"] <= d["screens_total"]
    assert d["screens_total"] > 0


if __name__ == "__main__":
    _selfcheck()
    result = scan()
    write_json(result)
    if "--print" in sys.argv:
        print_table(result)
    else:
        print(f"저장 완료 → status/gas_dependency.json · 전체 {result['screens_total']}장 "
              f"(구글만 {result['screens_gas_only']} · 폴백 {result['screens_both']} · "
              f"서버만 {result['screens_server_only']})")
