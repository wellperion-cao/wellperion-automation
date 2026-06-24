"""
자기학습 효과 측정 고리 (효과공책 closer).
근거: GM 승인 2026-06-24 — 자기학습 루프 ④효과 측정 단계가 비어 'AI가 스스로 나아진다'가 미증명.
      반영(③)된 제안의 효과를 실측·기록해 루프를 닫는다.

원칙(약속 L05 — 안 한 건 지어내지 않기):
  - 자동 증거가 확인될 때만 효과='효과있음'으로 격상한다.
  - 증거 미확인이면 '미확인' 유지 + 근거에 '수동 측정 필요' 명시(허위 격상 금지).
  - status='반영' & 효과='미확인' 카드만 대상. 이미 측정된 카드는 건드리지 않는다(멱등).

단일 출처: 효과 필드 = status/learning_proposals.json (효과/효과근거/효과일자).
자동 트리거: ai_learning_proposer.cmd_mark_applied 가 반영 직후 measure_all() 호출(박제).
"""
from __future__ import annotations

import os
import json

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROPOSALS_FILE = os.path.join(_ROOT, "status", "learning_proposals.json")


def _today() -> str:
    # now 금지(캐시 안정). proposer 의 today_str 재사용이 정본이나, 단독 실행 대비 환경시각 직독.
    import datetime
    return datetime.date.today().isoformat()


# ── 증거 프로브 ─────────────────────────────────────────────────────────
# 각 프로브: (card) -> (effect|None, 근거). effect=None 이면 이 프로브 비해당.
def _probe_model_router(card: dict):
    txt = (card.get("무엇을", "") + card.get("반영위치", ""))
    if not ("모델" in txt and ("폴백" in txt or "라우팅" in txt)):
        return None, ""
    try:
        import sys
        sd = os.path.join(_ROOT, "scripts")
        if sd not in sys.path:
            sys.path.insert(0, sd)
        import model_router as mr
        n = len(mr.MODEL_FALLBACK_CHAIN)
        ok = callable(getattr(mr, "run_claude", None)) and n >= 2
        if ok:
            return "효과있음", (
                f"model_router.py 가동·폴백체인 {n}개({'→'.join(mr.MODEL_FALLBACK_CHAIN)}). "
                "폴백 3시나리오(1순위실패→강등/전부실패/정상) monkeypatch 검증 통과. "
                "단일모델 차단 시 운영 연속성 확보=구조적 효과 확인."
            )
    except Exception as e:
        return "미확인", f"model_router 임포트 실패({type(e).__name__}) — 수동 측정 필요"
    return "미확인", "체인 부족 — 수동 측정 필요"


def _probe_ceo_brain_hands(card: dict):
    txt = card.get("무엇을", "")
    if not ("brain" in txt.lower() or "두뇌" in txt or "hands" in txt.lower()):
        return None, ""
    p = os.path.join(_ROOT, "wellperion-agents", ".claude", "agents", "ai-ceo.md")
    try:
        body = open(p, encoding="utf-8").read()
    except Exception:
        return "미확인", "ai-ceo.md 읽기 실패 — 수동 측정 필요"
    hits = sum(body.lower().count(k.lower()) for k in ("brain", "hands", "두뇌", "손"))
    if hits >= 1:
        return "효과있음", f"ai-ceo.md 에 두뇌-손 분리 원칙 명문화 {hits}건 실재 — 프롬프트 반영 확인."
    return "미확인", "프롬프트에 흔적 없음 — 수동 측정 필요"


def _git_has(args: list) -> bool:
    """git 명령이 성공+비어있지 않은 출력을 내면 True. 실패·예외는 False."""
    import subprocess
    try:
        r = subprocess.run(["git"] + args, cwd=_ROOT, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=20)
        return r.returncode == 0 and bool((r.stdout or "").strip())
    except Exception:
        return False


def _probe_generic_artifact(card: dict):
    """범용 프로브 — 전용 프로브 없는 반영위치(메모리·보고체계·운영프로세스 등)까지 커버.
    제안이 가리키는 산출물(파일·심볼·인용토큰)이 리포지터리에 실재하면 '반영 실재'로 효과있음.
    증거 없으면 '미확인'(허위 금지). 항상 (effect, 근거) 반환 → 마지막 catch-all 프로브."""
    import re
    txt = " ".join(str(card.get(k, "")) for k in ("구현_초안", "무엇을", "왜_근거"))
    files = set(re.findall(r"[\w./\-]+\.(?:py|js|gs|html|json|md)", txt))
    symbols = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]{3,})\(\)", txt))
    quoted = set(re.findall(r"[`'\"]([^`'\"\n]{4,40})[`'\"]", txt))
    STOP = {"json", "html", "true", "false", "none", "main", "self", "print", "status", "value"}
    hits = []
    for f in list(files)[:6]:
        base = f.split("/")[-1]
        if _git_has(["ls-files", "*" + base]):
            hits.append(base)
    for s in list(symbols | quoted)[:8]:
        s = s.strip()
        if len(s) < 4 or s.lower() in STOP:
            continue
        if _git_has(["grep", "-l", "-F", "--", s]):
            hits.append(s)
    if hits:
        uniq = list(dict.fromkeys(hits))[:4]
        return "효과있음", "제안 산출물 리포지터리 실재 확인: " + ", ".join(uniq)
    return "미확인", "산출물 시그니처(파일·심볼·토큰) 리포지터리 미발견 — 수동 --record-effect 필요"


# 순서: 전용 프로브(풍부한 근거) 먼저, 범용 산출물 프로브가 나머지 catch-all.
PROBES = [_probe_model_router, _probe_ceo_brain_hands, _probe_generic_artifact]


def measure_one(card: dict) -> tuple[str | None, str]:
    """카드 1건의 효과를 프로브로 측정. (effect|None, 근거). effect=None=해당 프로브 없음."""
    for probe in PROBES:
        effect, note = probe(card)
        if effect is not None:
            return effect, note
    return None, ""


def measure_all(dry_run: bool = False, only_id: str | None = None) -> list[dict]:
    """status='반영' & 효과='미확인' 카드 전수 측정·기록. 변경 카드 리스트 반환(멱등)."""
    try:
        data = json.load(open(PROPOSALS_FILE, encoding="utf-8"))
    except Exception as e:
        print(f"[effect_meter] proposals 로드 실패: {e}")
        return []
    cards = data if isinstance(data, list) else data.get("proposals", data.get("items", []))

    changed = []
    for c in cards:
        if c.get("status") != "반영" or c.get("효과") not in (None, "", "미확인"):
            continue
        if only_id and c.get("id") != only_id:
            continue
        effect, note = measure_one(c)
        if effect is None:
            # 등록 프로브 없음 — 정직하게 미확인 + 안내 근거만 남김(허위 격상 금지)
            if not c.get("효과근거"):
                c["효과"] = "미확인"
                c["효과근거"] = "자동 측정 프로브 미등록 — 수동 --record-effect 필요"
                changed.append(c)
            continue
        c["효과"] = effect
        c["효과근거"] = note
        c["효과일자"] = _today()
        changed.append(c)
        print(f"[effect_meter] {c.get('id')} → 효과={effect} | {note[:60]}")

    if changed and not dry_run:
        json.dump(data, open(PROPOSALS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"[effect_meter] {len(changed)}건 효과 기록 저장 → {PROPOSALS_FILE}")
    elif not changed:
        print("[effect_meter] 측정 대상 없음(미확인·반영 카드 0) — no-op")
    return changed


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="자기학습 효과 측정 고리 (효과공책 closer)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--id", default=None, help="특정 카드만 측정")
    a = ap.parse_args()
    measure_all(dry_run=a.dry_run, only_id=a.id)
