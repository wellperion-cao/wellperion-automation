#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""screen_bins.py — 화면 지도(status/screen_map.json) 위에 「1차 분류」를 얹는다 (시보 · GM 지시 2026-09-17).

GM 원문: 「굳이 화면으로 남길 필요 없이 문서는 문서함에 보관 · 업무였던 것도 진행 완료면 문서로 보관 ·
정말 필요한 페이지만 유지 · 스텁이나 업데이트 과거 버전이나 옛것들은 정리해야 해, 막 삭제하면 안 되니까 1차 분류를 해줘」

네 갈래(bin) — 파일은 옮기지 않는다. 판정만 적고 GM 이 번호로 뒤집는다.
  유지    = 사람이 눌러서 일하는 화면 · 밖(워드프레스)에 끼워 넣는 원본 · 공개 첫 화면
  문서함  = 읽는 것(가이드·소개서·설계) + 끝난 업무 산출물(A3·검토·요약·정리본). 화면 지도에서 내리고 문서함으로
  정리    = 이동 스텁(옛 주소) · 옛 판(v0.x·초안·샘플 — 최신 판이 따로 있음) · 은퇴한 설계. 30일 두고 삭제 후보
  확인    = 규칙으로 못 가른 것 — 시보가 한 줄 이유를 적고 GM 이 번호로 답

정본 = status/screen_bins.json (이 스크립트가 만든다 · 손으로 고치지 않는다). GM 답은 아래 OVERRIDES 에 번호로 박는다.
화면 = erp/admin/screens.html 「시보 1차 분류」 절.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "status" / "screen_map.json"
OUT = ROOT / "status" / "screen_bins.json"
KST = timezone(timedelta(hours=9))

DONE_WORDS = re.compile(r"A3|A4|보고|검토|요약|정리본|비교|견적|제안|초안|기획|설계|명세|의견제출|결과|안내판|운영지침|채용공고|현수막|미팅|회의")
DATED = re.compile(r"(^|/)\d{6}_|_\d{8}([_.]|$)|20\d{6}")
OLD_VERSION = re.compile(r"_v0\.\d|샘플|_사본|백업|_old|옛", re.I)

# GM 이 번호로 답한 것 · 시보가 규칙 밖에서 판정한 것 — 번호(no) 기준. 값 = (bin, 이유)
OVERRIDES: dict[int, tuple[str, str]] = {
    # 회사문서 소개서 4판 — 공식은 v2.19(랩스 판 기준) · 통합본은 확인 · 옛 A3·샘플은 정리
    281: ("문서함", "웰페리온 회사소개서 v2.19 — 공식 판(랩스 판 「회사소개서 v2.19」)"),
    296: ("확인", "회사소개서 「통합」 — v2.19 와 무엇이 다른지 시보가 못 갈랐다 · GM 답"),
    297: ("정리", "회사소개서 A3 전체 20260722 — v2.19 의 옛 판"),
    298: ("정리", "회사소개서 A3 섹터 샘플 — 샘플(웰리도 삭제 권고)"),
    283: ("문서함", "브랜드확장 회사소개서 v1 — 완성 문서(확장 제안용)"),
    # 파트너 라인 — 단계가 지난 산출물은 문서함, 살아 있는 3장은 유지
    165: ("문서함", "다캠 1차 제안 Before&After — 끝난 단계 산출물"),
    166: ("문서함", "다캠 2차 제안 — 끝난 단계 산출물"),
    168: ("문서함", "다캠 초안 v0.1 — intro·brand·strategy 로 이어졌음"),
    170: ("문서함", "다캠 셋업 v0.1 — 번호 설문으로 대체됨(9/17)"),
    175: ("문서함", "고척 초안 v0.1 — intro·brand·strategy 3장으로 이어졌음(9/17)"),
    167: ("유지", "다캠 브랜드가이드 — 파트너가 보는 살아 있는 문서 3장 중 하나"),
    169: ("유지", "다캠 회사소개서 — 파트너 라인 3장"),
    171: ("유지", "다캠 운영전략 — 파트너 라인 3장"),
    174: ("유지", "고척 브랜드가이드 — 파트너 라인 3장"),
    176: ("유지", "고척 회사소개서 — 파트너 라인 3장"),
    177: ("유지", "고척 운영전략 — 파트너 라인 3장"),
    # 상담봇 설계 문서군
    181: ("문서함", "상담봇 원가 설계 v0.1 — 설계 문서(값은 로드맵 §5 가 정본)"),
    182: ("정리", "FAQ 통합 파이프라인 v1.0 — schema.md 「학습 루프」 절이 대체(9/17)"),
    183: ("문서함", "카톡 AI 파트너 상품 v0.1 — 설계 문서"),
    184: ("문서함", "상담봇 기획설계 v1.0 — 설계 정본(읽는 문서)"),
    185: ("문서함", "상담봇 질문세례 v1.0 — 질문은행(question_bank.json)이 정본 · 읽는 문서"),
    # 랩스 회사 문서
    160: ("문서함", "AX 랩스 회사 한 장 — 읽는 문서"),
    161: ("문서함", "AX 랩스 회사 소개서(밖) — 읽는 문서 · /labs/intro.html 로 배포"),
    162: ("문서함", "AX 랩스 전략 로드맵 — 읽는 문서(GM 은 §1·§10 두 표)"),
    186: ("문서함", "AX 랩스 브랜드가이드 — 화면 정본(읽는 문서)"),
    180: ("유지", "AX 랩스 공개 첫 화면(/labs/) — 밖에 보이는 화면"),
    173: ("유지", "환경 상태(알파·베타·라이브) — 운영 화면"),
    190: ("유지", "토큰 사용량 — 운영 화면(자율현황과 한 벌)"),
    187: ("유지", "화면 지도 — 이 정리의 자리"),
    196: ("유지", "홈페이지 둘러보기(360) — 밖에서 들어오는 링크 13"),
    12: ("유지", "다캠 둘러보기 — 파트너에게 보이는 화면(9/15 MVP 확정) · 접속은 밖에서 센다"),
    # coo 회장님 자리 — 살아 있는 원장 2장 + 회의 체계
    83: ("유지", "대표님 지시사항 — 살아 있는 원장(카드)"),
    107: ("유지", "회장님 지시사항 — 살아 있는 원장(카드)"),
    101: ("확인", "회의체계 — 9/16 새 화면(접속 0·고립) · 회의요약 A3 생성기와 한 벌인지 GM 답"),
    100: ("유지", "회의요약 A3 — 매일 07:50 재생성 화면(배 2705)"),
    131: ("유지", "매출·회원 현황 보고 — 매일 09:00 발송 원본 화면(접속 43)"),
    116: ("유지", "파트너팀 페이롤 — 카드 화면(접속 0 이지만 카드에 실림)"),
}


def load() -> dict:
    return json.loads(SRC.read_text(encoding="utf-8"))


def judge(e: dict) -> tuple[str, str]:
    """규칙 판정 — (bin, 이유). OVERRIDES 가 먼저다."""
    no = e.get("no")
    if no in OVERRIDES:
        return OVERRIDES[no]
    rel, kind, flags = e.get("rel", ""), e.get("kind", ""), set(e.get("flags") or [])
    hits, inb, card = int(e.get("hits") or 0), int(e.get("inbound") or 0), bool(e.get("in_card"))
    title = e.get("title") or ""
    if "이동스텁" in flags:
        if hits > 0:
            return ("정리", f"옛 주소 스텁 · 접속 {hits} — 아직 누가 쓴다 · 새 주소 안내 뒤 삭제")
        return ("정리", "옛 주소 스텁 · 접속 0 — 삭제 후보")
    if OLD_VERSION.search(rel) or ("임시" in flags and kind == "화면"):
        return ("정리", "옛 판·초안·임시 이름 — 최신 판이 따로 있으면 삭제 후보")
    if kind == "문서":
        return ("문서함", "읽는 문서(가이드·소개서·설계)")
    if kind == "업무":
        if card or hits >= 10:
            return ("유지", f"일하는 화면(카드 {'있음' if card else '없음'} · 접속 {hits})")
        if DATED.search(rel) or DONE_WORDS.search(rel) or DONE_WORDS.search(title):
            return ("문서함", "끝난 업무 산출물(날짜·A3·검토·요약)")
        return ("확인", "업무인데 끝났는지 못 가림")
    # kind == 화면
    if "외부삽입" in flags:
        return ("유지", "밖(워드프레스·공개)에 끼워 넣는 원본 — 접속은 밖에서 센다")
    if hits > 0 or card or inb > 0:
        return ("유지", f"쓰는 화면(접속 {hits} · 카드 {'있음' if card else '없음'} · 들어오는 링크 {inb})")
    return ("확인", "화면인데 접속 0 · 카드 밖 · 들어오는 링크 0")


def build() -> dict:
    d = load()
    screens = d.get("screens") or []
    bins: dict[str, dict] = {}
    counts: dict[str, int] = {"유지": 0, "문서함": 0, "정리": 0, "확인": 0}
    for e in screens:
        b, why = judge(e)
        bins[e["rel"]] = {"no": e.get("no"), "bin": b, "reason": why, "title": e.get("title"),
                          "kind": e.get("kind"), "hits": e.get("hits") or 0, "folder": e.get("folder")}
        counts[b] += 1
    return {
        "_about": "화면 지도 위 시보 1차 분류(GM 지시 2026-09-17) — scripts/screen_bins.py 가 만든다. 손으로 고치지 않는다. GM 답은 스크립트 OVERRIDES 에 번호로.",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source_generated": d.get("generated"),
        "total": len(screens),
        "counts": counts,
        "rule": "유지=일하는 화면·외부 삽입 원본·공개 첫 화면 / 문서함=읽는 문서+끝난 업무 산출물 / 정리=옛 주소 스텁·옛 판·초안(30일 뒤 삭제 후보) / 확인=시보가 못 가른 것(GM 번호 답)",
        "bins": bins,
    }


def render(d: dict) -> str:
    c = d["counts"]
    lines = [f"1차 분류 {d['total']}장 — 유지 {c['유지']} · 문서함 {c['문서함']} · 정리 {c['정리']} · 확인 {c['확인']}"]
    for b in ("확인", "정리"):
        rows = sorted((v for v in d["bins"].values() if v["bin"] == b), key=lambda v: v["no"])
        lines.append(f"== {b} {len(rows)}")
        for v in rows:
            lines.append(f"  #{v['no']:3d} {v['title'][:40]:40s} | {v['reason'][:60]}")
    return "\n".join(lines)


def self_test() -> None:
    e = {"no": 9999, "rel": "coo/chairman/260901_x_A3.html", "kind": "업무", "flags": [], "hits": 0}
    assert judge(e)[0] == "문서함"
    e = {"no": 9998, "rel": "x/y.html", "kind": "화면", "flags": ["이동스텁"], "hits": 5}
    assert judge(e)[0] == "정리"
    e = {"no": 9997, "rel": "cmo/home/wp_block.html", "kind": "화면", "flags": ["외부삽입"], "hits": 0}
    assert judge(e)[0] == "유지"
    e = {"no": 9996, "rel": "coo/x.html", "kind": "화면", "flags": [], "hits": 0, "inbound": 0}
    assert judge(e)[0] == "확인"
    assert judge({"no": 298})[0] == "정리"
    print("screen_bins 자가점검 통과")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        self_test()
        return 0
    d = build()
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(d, ensure_ascii=False) if a.json else render(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
