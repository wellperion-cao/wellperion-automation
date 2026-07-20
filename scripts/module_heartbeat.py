# -*- coding: utf-8 -*-
"""
module_heartbeat.py — 모듈 하트비트 공통 유틸 단일 정의 (배1307 5차).
─────────────────────────────────────────────────────────────────────────────
문제: module_silence_detector.py(배1307 3차)가 등록부 29개 중 21개를 "판정불가"로
분류했다 — 정상이라서가 아니라 판정할 로컬 흔적이 없어서다(GAS/구글시트에서만
돌거나, 로컬에 남기는 흔적이 그 모듈 전용이 아니라 다른 모듈과 공유돼 있거나).

이 모듈은 "모듈이 실제 결과를 낸 시점"을 기록하는 단일 진실을 제공한다.
호출부(각 스크립트)는 이 함수 하나만 부른다 — 하트비트 기록 방식을 각자
재구현하지 않는다(헌법 원리1: 한 진실 한 곳).

⚠️ 호출 시점 원칙: "스크립트가 시작됐다"가 아니라 "실제 산출물을 만들었다"는
증거가 있는 지점에서만 부른다(예: GAS 조회 성공 직후, 발송 성공 직후, 파일
기록 직후). 무조건 스크립트 진입부에서 부르면 죽은 로직이 여전히 살아있는
것처럼 보이는 거짓 하트비트가 된다 — INC-018(KPI 집계기 6일 침묵)이 바로
"떴다"와 "결과를 냈다"를 혼동해서 아무도 몰랐던 사고다.

기록 위치: status/heartbeats/{module_id}.json (모듈 1개 = 파일 1개, 매번 덮어쓰기).
공유 jsonl에 append 하지 않는 이유: module_silence_detector._ts_from_jsonl_file() 은
파일의 "마지막 줄"만 보므로, 여러 모듈이 한 jsonl을 공유하면 최근에 아무 모듈이나
기록한 줄이 다른 모듈의 신선도로 오판정된다(실측 확인 후 회피 — 파일당 모듈 1개 고정).

fail-soft: 기록 실패(권한·디스크 등)가 호출부의 본 작업을 절대 막지 않는다 —
예외를 삼키고 조용히 넘어간다(단, 반환값의 "ok" 로 성공 여부는 알 수 있다).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))  # 이 저장소 관행(module_silence_detector.py 상단 주석과 동일)

_SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _SCRIPTS_DIR.parent
HEARTBEAT_DIR = PROJECT_ROOT / "status" / "heartbeats"


def _now_utc(now=None) -> datetime:
    if now is not None:
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def record_heartbeat(module_id: str, detail: str = "", *, extra: dict | None = None,
                      now=None, root: Path = PROJECT_ROOT) -> dict:
    """모듈이 실제 결과를 낸 시점 → status/heartbeats/{module_id}.json 갱신(덮어쓰기).

    module_id: module_registry.json 의 id 그대로(예: "cto-gas-version-monitor").
    detail: 사람이 읽을 한 줄 요약(무엇을 냈는지) — 생략 가능.
    extra: 추가 필드가 필요하면(드묾) 병합. id/generated_at 은 덮어쓸 수 없음.
    반환: 기록한 레코드 dict. 쓰기 실패 시에도 dict 는 반환(ok=False로 표시).
    """
    now = _now_utc(now)
    rec = {
        "id": module_id,
        "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_at_kst": now.astimezone(KST).strftime("%Y-%m-%d %H:%M"),
        "detail": detail,
    }
    if extra:
        for k, v in extra.items():
            if k not in ("id", "generated_at"):
                rec[k] = v
    try:
        d = Path(root) / "status" / "heartbeats"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{module_id}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        rec["ok"] = True
    except Exception as e:  # fail-soft — 하트비트 기록 실패가 호출부 본작업을 막지 않음
        rec["ok"] = False
        rec["error"] = f"{type(e).__name__}: {str(e)[:120]}"
    return rec


def last_heartbeat(module_id: str, root: Path = PROJECT_ROOT) -> dict | None:
    """검증·디버깅용 — 마지막 기록 읽기. 없으면 None."""
    p = Path(root) / "status" / "heartbeats" / f"{module_id}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("사용법: python scripts/module_heartbeat.py <module_id> [detail]")
        sys.exit(1)
    mid = sys.argv[1]
    detail = sys.argv[2] if len(sys.argv) > 2 else ""
    out = record_heartbeat(mid, detail=detail)
    print(json.dumps(out, ensure_ascii=False, indent=2))
