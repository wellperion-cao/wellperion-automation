# -*- coding: utf-8 -*-
"""상담봇 톤 테스트 — 클로드 Max 구독(claude CLI)으로 0원 실행 (GM 지시 2026-09-05 "테스트는 Max 토큰으로").

라이브(손님) = AWS Bedrock(server/erp_api/api_chat.py · 과금). 내부 톤·문구 점검은 이 스크립트 —
같은 시스템 프롬프트(정본 11구역 + FAQ + 오늘 운영 한 줄 + 컨시어지 원칙 7)를 그대로 쓰되 모델 호출만 GM PC 의
claude 명령(Max 구독)으로 돌린다. 서버·Bedrock 은 건드리지 않는다(과금 0).

  C:/Python314/python.exe scripts/counselbot_test.py "허리가 아픈데 운동해도 되나요"            # 다캠(기본)
  C:/Python314/python.exe scripts/counselbot_test.py "Do you open today?" --tenant 1_wellperion
  C:/Python314/python.exe scripts/counselbot_test.py --file questions.txt --tenant 2_dietcamp   # 한 줄 = 질문 하나
"""
from __future__ import annotations
import argparse, json, os, shutil, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "server/counselbot/tests"
LOG = TESTS / "log.jsonl"


def _rate(rid: str, rating: str, note: str) -> int:
    """문답 한 건에 good/bad 평가·메모를 붙인다(같은 파일 다시 씀 — 원장은 하나)."""
    rows = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    hit = [r for r in rows if r["id"] == rid]
    if not hit:
        print("없는 id:", rid); return 1
    hit[0]["rating"], hit[0]["note"] = rating, note
    LOG.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print("기록:", rid, rating, note); return 0


FAQ_SRC = {
    "1_wellperion": ROOT / "server/erp_api/seed_faq/1_wellperion.json",
    "2_dietcamp": ROOT / "2. 브랜드_자료/10_다이어트캠프_브랜드가이드/07_FAQ/faq.json",
    "3_spogym": ROOT / "server/erp_api/seed_faq/2_dietcamp.json",   # 빈 FAQ(미수령) — 핸드오프만 나와야 정상
}


def _stage_faq_dir() -> str:
    """api_chat 이 읽는 /srv/erp/faq/{tenant}/faq.json 모양을 임시 폴더에 만든다(저장소 정본 = 씨앗)."""
    d = Path(tempfile.mkdtemp(prefix="counselbot_faq_"))
    for t, src in FAQ_SRC.items():
        (d / t).mkdir()
        shutil.copy(src, d / t / "faq.json")
    return str(d)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", help="손님 질문 1개")
    ap.add_argument("--tenant", default="2_dietcamp", choices=sorted(FAQ_SRC))
    ap.add_argument("--file", help="질문 목록 파일(한 줄 = 질문 하나)")
    ap.add_argument("--model", default=None, help="claude CLI 모델명(기본 = model_router 기본 순서)")
    ap.add_argument("--set", action="store_true", help="server/counselbot/tests/{tenant}_questions.txt 전체 실행")
    ap.add_argument("--rate", nargs=2, metavar=("ID", "good|bad"), help="log.jsonl 의 문답에 평가 붙이기")
    ap.add_argument("--note", default="", help="--rate 메모(왜 나쁜가 · 정본에 무엇이 빠졌나)")
    a = ap.parse_args()
    if a.rate:
        return _rate(a.rate[0], a.rate[1], a.note)
    qs = [a.question] if a.question else []
    if a.file:
        qs += [l.strip() for l in Path(a.file).read_text(encoding="utf-8").splitlines() if l.strip()]
    if a.set:
        qs += [l.strip() for l in (TESTS / (a.tenant + "_questions.txt")).read_text(encoding="utf-8").splitlines() if l.strip()]
    if not qs:
        ap.error("질문 또는 --file 필요")

    os.environ["ERP_FAQ_DIR"] = _stage_faq_dir()
    os.environ.setdefault("ERP_CHAT_LOG", os.devnull)
    sys.path.insert(0, str(ROOT / "server/erp_api")); sys.path.insert(0, str(ROOT / "scripts"))
    import api_chat                       # noqa: E402 — 서버와 같은 프롬프트 조립기 재사용(약속 L21)
    from model_router import run_claude   # noqa: E402 — claude CLI(Max 구독) 관문 하나

    prof = api_chat._load_profile(a.tenant)
    system = api_chat._concierge_system_block(a.tenant, prof, api_chat._persona_of(a.tenant))
    print("[테스트] tenant=%s · 모델 호출 = claude CLI(Max 구독 · 0원) · 정본 %d자 · FAQ %d문답"
          % (a.tenant, len(system), len(api_chat._load_faq(a.tenant).get("faq") or [])))
    for q in qs:
        hint = " (질문이 영어이니 영어로 답하세요)" if api_chat._is_english_q(q) else ""
        prompt = system + "\n\n[손님 질문]\n" + q + hint + "\n\n[상담원 답변]"
        t0 = time.time()
        text, used = run_claude(prompt, models=[a.model] if a.model else None, label="counselbot-test")
        dt = time.time() - t0
        text = (text or "").strip()
        verdict = "OK" if text and not api_chat._forbidden_hit(text) and api_chat._grounded(text, system) else "검사 탈락→핸드오프"
        rid = time.strftime("%Y%m%d%H%M%S") + "-" + str(abs(hash(q)) % 10000)
        TESTS.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:   # 테스트 데이터 = 자산(GM 09-05) — 문답 전부 남긴다
            f.write(json.dumps({"id": rid, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tenant": a.tenant, "q": q,
                                "a": text, "model": used, "sec": round(dt, 1), "verdict": verdict,
                                "rating": None, "note": ""}, ensure_ascii=False) + "\n")
        print("\n[%s] Q: %s\nA(%s · %.1fs · %s): %s" % (rid, q, used, dt, verdict, text or "(빈 응답)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
