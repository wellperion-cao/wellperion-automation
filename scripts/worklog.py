# scripts/worklog.py
# 전 C-Level 공용 "작업 현황 로그" 기록 모듈 (2026-07-23, GM 승인 · CMO-2026-07-23-WORKLOG-PANEL).
#
# 계기: AI하루 EP10이 검수큐 등록 누락돼 아무도 못 봄(2026-07-23 실사고) — 로그가
# "한 일"만 남기면 "빠진 것"은 놓친다. 이 모듈은 "한 일" 쪽(기록)만 담당한다.
# "빠진 것" 자동 적발은 scripts/worklog_gaps.py.
#
# API 1개:
#   from worklog import log
#   log(role, area, event, result="ok", detail="", ref="", url="")
#   → status/worklog.jsonl 에 1줄 append.
#
# ★고정 스키마(절대 변경 금지 — 화면 담당 에이전트가 동시에 이 규격으로 렌더 중):
#   {"ts":"2026-07-23T07:39:35+09:00","role":"cmo","area":"발행",
#    "event":"AI하루 01 인스타 발행","result":"warn",
#    "detail":"성공 토스트 확인·주소 미회수","ref":"CMO-...","url":""}
#   - ts = ISO8601 KST(+09:00) / role ∈ ceo|cfo|chro|cmo|coo|cpo|cto
#   - area = 짧은 한국어 분류(예 "발행","검수","제작","점검")
#   - event = 한 줄 한국어 요약(실무진이 읽는다 — 영어·코드·약어 금지)
#   - result ∈ ok|warn|fail / detail·ref·url 선택
#
# ★ best-effort — 기록 실패가 호출부(발행 등 본업)를 절대 막지 않는다.
#   log() 는 절대 예외를 던지지 않고 성공 여부(bool)만 반환한다.
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
WORKLOG_PATH = ROOT / "status" / "worklog.jsonl"

KST = timezone(timedelta(hours=9))

VALID_RESULTS = {"ok", "warn", "fail"}
_APPEND_RETRIES = 3
_APPEND_RETRY_WAIT_SEC = 0.2

# GM지시 접수 자동화(2026-08-08, GM 지시 A안) — UserPromptSubmit 훅 진입점.
# ref 채번 = 역할별 1000단위 구간(GM-YYYYMMDD-{구간+N}) — kungjjak_board.py --all-roles 가
# ref 로만 짝을 묶으므로(role 필터 없음) 역할이 겹치는 번호를 쓰면 다른 역할 접수가 한 표에
# 섞여버린다. 구간을 나눠 물리적으로 겹칠 수 없게 한다. 미지정 역할은 9000대로 격리.
_GM_REF_BLOCK = {"ceo": 1000, "cto": 2000, "cmo": 3000, "cpo": 4000,
                  "coo": 5000, "chro": 6000, "cfo": 7000}
_GM_REMINDER = ("[형식 고정] 말투=caveman ultra(군더더기·과정 서술 금지) · "
                "GM 물음 1개 = 표 1개(8요소 📌GM지시 🔍실측 ✅반영 🔎검수 📤올림 ⏱소요 💡더나았을방법 👉GM액션) · "
                "표 밖 줄글은 표로 못 담는 것만")


def _next_gm_ref(role: str, day: str) -> str:
    """그날·그 역할의 기존 최대 번호 다음(역할 구간 안에서). 파일 없으면 구간 첫 번호."""
    block = _GM_REF_BLOCK.get(role, 9000)
    prefix = f"GM-{day}-"
    max_nn = block
    if WORKLOG_PATH.exists():
        with open(WORKLOG_PATH, encoding="utf-8") as f:
            for line in f:
                if prefix not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("role") != role:
                    continue
                ref = str(d.get("ref") or "")
                if not ref.startswith(prefix):
                    continue
                try:
                    nn = int(ref[len(prefix):])
                except ValueError:
                    continue
                if block <= nn < block + 1000 and nn > max_nn:
                    max_nn = nn
    return f"{prefix}{max_nn + 1}"


def record_gm_prompt_hook() -> None:
    """UserPromptSubmit 훅 진입점 — GM 프롬프트를 GM지시 접수로 best-effort 기록하고,
    항상 리마인더 JSON 을 stdout 에 낸다(예외 나도 세션은 절대 막지 않는다)."""
    try:
        data = json.loads(sys.stdin.read())
        prompt = str(data.get("prompt") or "").strip()
        role = (os.environ.get("WELLPERION_ROLE") or "").strip().lower()
        # ★역할을 못 읽으면 조용히 건너뛰지 않는다(시포 배490 · 2026-08-08 실사고).
        #   그날 시포는 GM 지시 17건을 받아 16건을 끝냈는데 쿵짝표가 "오늘 받은 지시 없음"을 냈다.
        #   훅은 돌았고 리마인더도 나갔지만 role 이 비어 접수만 건너뛴 탓이었다 — 아무 흔적이
        #   없어서 그날 하루가 통째로 사라진 것처럼 보였다. 흔적을 남겨 다음엔 바로 잡히게 한다.
        if prompt and not role:
            try:
                log("", "GM지시", "역할 미인식 — 접수를 남기지 못했다",
                    result="fail",
                    detail="WELLPERION_ROLE 이 훅 프로세스에 안 넘어왔다. 부팅 배치의 환경변수 상속을 확인할 것(배490).")
            except Exception:
                pass
        if prompt and role:
            event = prompt.splitlines()[0].strip()
            # 사람이 친 것만 접수한다. 훅은 시스템이 주입하는 알림·명령 출력에도 똑같이 걸려서,
            # 2026-08-08 에 `<task-notification>` 한 줄이 GM 지시로 원장에 박혀 쿵짝표에
            # "진행중" 으로 떴다. 아무도 시키지 않은 일이 놓친 일로 보이면 판단이 어긋난다.
            # 'C-Level 부팅'(부팅 지시문)·'너는 …'(서브에이전트 역할 프롬프트)도 사람이 친 게 아니라
            # 붙여넣은 실행문이다. 2026-08-11 실측: 미완 91건 중 16건이 이 둘이었다 —
            # GM 이 시킨 적 없는 일이 "미완"으로 쌓여 쿵짝표 숫자를 부풀렸다.
            if event.startswith(('<', '[SYSTEM NOTIFICATION', '[형식 고정',
                                 'C-Level 부팅', '너는 ')):
                event = ''
            if len(event) > 120:
                event = event[:120] + "…"
            if event:
                # ★새 지시를 접수하기 전에 **직전 지시들을 닫는다**(2026-08-11).
                #   GM 이 다음 말을 걸었다는 건 앞 물음에 답이 끝났다는 뜻이다.
                #   Stop 훅에도 같은 호출을 뒀지만 그쪽은 실측상 이 세션에서 한 번도 발화하지
                #   않았다 — 접수는 100% 쌓이고 있으므로(이 훅) 닫는 것도 여기서 보장한다.
                #   멱등이라 두 곳에서 불려도 같은 ref 가 두 번 닫히지 않는다.
                close_gm_refs(role)
                day = datetime.now(tz=KST).strftime("%Y%m%d")
                ref = _next_gm_ref(role, day)
                log(role, "GM지시", event, result="warn",
                    detail="받음 · 자동 접수(UserPromptSubmit)", ref=ref)
    except Exception:
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                              "additionalContext": _GM_REMINDER}},
                      ensure_ascii=False))


def close_gm_refs(role: str, detail: str = "") -> int:
    """그 역할의 열린 GM 지시 접수(warn 만 있고 ok 짝 없는 것)를 닫는다. 닫은 건수를 돌려준다.

    왜 있나(2026-08-11): 접수는 UserPromptSubmit 훅이 기계로 남기는데 완료 짝은 사람이 손으로
    남겨야 해서, 답을 다 한 물음도 "미완"으로 쌓였다. 실측 — 시토 3/30 · 웰리 26/38 · 시모
    13/16 · 시포 8/12 로 역할마다 제각각이었고 미완이 91건까지 불었다.

    ★쿵짝표는 '물음↔답' 대장이다. '지시↔완수' 추적은 배(status/_queue.json)가 한다(약속 L15).
    두 벌을 만들면 진실이 둘이 된다(L01). 그래서 세션이 응답을 끝내면 여기서 닫고,
    후속 작업이 남은 건은 배가 이어받는다.

    """
    try:
        if not WORKLOG_PATH.exists():
            return 0
        role_v = (role or "").strip().lower()
        if not role_v:
            return 0
        warn: dict[str, str] = {}
        ok: set[str] = set()
        with open(WORKLOG_PATH, encoding="utf-8") as f:
            for line in f:
                if "GM-" not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if (d.get("role") or "").strip().lower() != role_v:
                    continue
                ref = str(d.get("ref") or "")
                if not ref.startswith("GM-"):
                    continue
                if d.get("result") == "warn":
                    warn.setdefault(ref, str(d.get("ts") or ""))
                elif d.get("result") == "ok":
                    ok.add(ref)
        n = 0
        for ref, ts in sorted(warn.items(), key=lambda kv: kv[1]):
            if ref in ok:
                continue
            if log(role_v, "GM지시", "답변 종결 — 세션이 응답을 마쳤다",
                   result="ok",
                   detail=detail or "후속 작업이 있으면 배(_queue)가 추적한다",
                   ref=ref):
                n += 1
        return n
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] close_gm_refs 예외(best-effort): {exc}")
        return 0


def log(
    role: str,
    area: str,
    event: str,
    result: str = "ok",
    detail: str = "",
    ref: str = "",
    url: str = "",
    ts: str = "",
) -> bool:
    """status/worklog.jsonl 에 고정 스키마로 1줄 append. best-effort(항상 bool 반환, 예외 안 던짐).

    role: ceo|cfo|chro|cmo|coo|cpo|cto (소문자 정규화만 하고 값 자체는 검증 실패해도 기록 시도
          — 스키마 계약을 지키되 호출부를 막지 않는 게 우선).
    result: ok|warn|fail (그 외 값이 오면 'ok'로 안전 폴백).
    ts: 소급 기록용 시각(ISO8601 KST). 비우면 지금. 접수를 놓쳐 나중에 남길 때,
        지금 시각으로 찍으면 쿵짝표의 소요 칸이 거짓이 된다 — 실제 시각을 넣는다.
        스키마는 그대로다(같은 ts 필드).
    """
    try:
        result_v = (result or "ok").strip().lower()
        if result_v not in VALID_RESULTS:
            result_v = "ok"
        record = {
            "ts": (ts or "").strip() or datetime.now(tz=KST).isoformat(timespec="seconds"),
            "role": (role or "").strip().lower(),
            "area": area or "",
            "event": event or "",
            "result": result_v,
            "detail": detail or "",
            "ref": ref or "",
            "url": url or "",
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        WORKLOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        last_exc: Exception | None = None
        for attempt in range(_APPEND_RETRIES):
            try:
                with open(WORKLOG_PATH, "a", encoding="utf-8") as f:
                    f.write(line)
                return True
            except Exception as exc:  # 동시 쓰기 등 — 짧게 재시도
                last_exc = exc
                if attempt < _APPEND_RETRIES - 1:
                    time.sleep(_APPEND_RETRY_WAIT_SEC)
        if last_exc:
            print(f"[WARN] worklog.log append 실패(best-effort): {last_exc}")
        return False
    except Exception as exc:
        print(f"[WARN] worklog.log 예외(best-effort, 호출부 무영향): {exc}")
        return False


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--hook-prompt":
        record_gm_prompt_hook()
    elif len(sys.argv) >= 4:
        ok = log(sys.argv[1], sys.argv[2], sys.argv[3])
        print(f"[{'OK' if ok else 'FAIL'}] worklog.log() 호출 — {WORKLOG_PATH}")
    else:
        print("사용: python worklog.py <role> <area> <event> | python worklog.py --hook-prompt")
