"""인사 쓰기 거울 — 쓰기 ok 직후 그 탭만 서버에 재적재한다 (CHRO 요청서③ · [나우열M 요청 2026-09-17]).

  POST /api/hr/mirror            본문 {"tabs": ["appl", "hire", …]} · 열람권 = api_hr 와 같은 관문(인사 허브 화면 열 수 있는 세션)
                                 → 3초 디바운스로 모아 탭별로 `migrate_hr.py --apply --light --tab <탭> --wait-lock 120` 을 백그라운드 실행.
                                 탭별 최소 간격 60초(그 안에 또 오면 간격이 찬 뒤 한 번만 돈다). 응답 = {"ok":true,"queued":[…],"skipped":[…]}
  GET  /api/hr/mirror/health     탭별 last_ok_at · last_error · lag_sec(마지막 성공 이후 초) · running · queued — 화면 킬스위치·실패 경고가 읽는다.

탭 열쇠 = migrate_hr.TABS 의 키(hire·emp·exit·appl·eval·onbo·blacklist·leave …). 상태 = /srv/erp/api/hr_mirror_state.json(재기동 뒤 복원).
안전망 = /etc/cron.d/erp-hr-mirror(차등 5·10·15분 · 같은 --light 명령 · advisory lock 공유). 화면 쪽(쓰기 ok 뒤 호출·킬스위치·경고) = CHRO.
⛔ 이 파일은 값(이름·연락처)을 다루지 않는다 — 탭 이름·시각·종료 코드만.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import threading
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api_hr  # noqa: E402  — 열람권 관문(_gate) 재사용 · 새 판정기를 만들지 않는다

router = APIRouter()

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "hr_mirror_state.json")
MIGRATE = os.path.join(HERE, "migrate_hr.py")
DEBOUNCE_SEC = 3.0
MIN_GAP_SEC = 60.0
WAIT_LOCK_SEC = 120
RUN_TIMEOUT_SEC = 600
TABS = ("hire", "emp", "exitroster", "exit", "appl", "eval", "onbo", "blacklist", "leave", "board", "schedchg")
KST = datetime.timezone(datetime.timedelta(hours=9))

_LOCK = threading.Lock()
_STATE: dict = {}
_PENDING: dict = {}          # tab → 요청 시각(디바운스 창)
_WORKER: threading.Thread | None = None


def _now() -> str:
    return datetime.datetime.now(KST).isoformat(timespec="seconds")


def _load(force: bool = False):
    """상태는 파일이 정본 — uvicorn 이 워커 2개라 프로세스마다 메모리가 따로다(2026-09-17 실측: 같은 탭이 5초 간격으로 두 번 돌았다).
    판정(간격·실행 중)은 매번 파일을 다시 읽고 한다."""
    global _STATE
    if _STATE and not force:
        return
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            _STATE = json.load(f)
    except Exception:
        _STATE = {}


def _save():
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_STATE, f, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)


def _tab(tab: str) -> dict:
    return _STATE.setdefault(tab, {"last_ok_at": None, "last_started_at": None, "last_error": None,
                                   "last_exit": None, "running": False, "queued": False})


def plan(tabs, state: dict, now_ts: float, min_gap: float = MIN_GAP_SEC):
    """순수 함수(자체점검이 잰다): 요청 탭 → (돌릴 탭, 건너뛸 탭·사유). 모르는 탭은 건너뜀 · 최소 간격 안이면 delay 로 표시."""
    run, skip = [], []
    for t in tabs:
        t = str(t).strip().lower()
        if t not in TABS:
            skip.append((t, "unknown-tab"))
            continue
        st = state.get(t) or {}
        last = st.get("last_started_ts") or 0
        if now_ts - float(last) < min_gap:
            skip.append((t, "min-gap"))          # 워커가 간격이 찬 뒤 한 번 돌린다(요청은 유지)
            continue
        run.append(t)
    return run, skip


def _run_tab(tab: str):
    # 프로세스 간 직렬화 — 탭별 잠금 파일(O_EXCL). 다른 워커 프로세스가 같은 탭을 막 돌렸으면(간격 안) 건너뛴다.
    lock_path = os.path.join(HERE, "hr_mirror_%s.lock" % tab)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode()); os.close(fd)
    except FileExistsError:
        try:
            if time.time() - os.path.getmtime(lock_path) < RUN_TIMEOUT_SEC:
                return                                     # 다른 프로세스가 돌리는 중
            os.remove(lock_path)                           # 죽은 잠금(타임아웃 지남) — 걷고 진행
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.close(fd)
        except Exception:
            return
    try:
        with _LOCK:
            _load(force=True)
            st = _tab(tab)
            if time.time() - float(st.get("last_started_ts") or 0) < MIN_GAP_SEC:
                st["queued"] = False; _save()
                return                                     # 다른 프로세스가 방금 돌렸다
            st.update({"running": True, "queued": False, "last_started_at": _now(), "last_started_ts": time.time()})
            _save()
        _run_tab_locked(tab)
    finally:
        try:
            os.remove(lock_path)
        except Exception:
            pass


def _run_tab_locked(tab: str):
    st = _tab(tab)
    cmd = [sys.executable, MIGRATE, "--apply", "--light", "--tab", tab, "--wait-lock", str(WAIT_LOCK_SEC)]
    try:
        p = subprocess.run(cmd, cwd=HERE, capture_output=True, timeout=RUN_TIMEOUT_SEC)
        code = p.returncode
        tail = p.stdout.decode("utf-8", "replace").strip().splitlines()[-3:]
        with _LOCK:
            _load(force=True)
            st = _tab(tab)
            st["last_exit"] = code
            if code == 0:
                st["last_ok_at"] = _now(); st["last_error"] = None
            else:
                # 값이 실릴 수 있는 stdout 은 안 남긴다 — 마지막 판정 줄([FAILED]/[LOCKED]) 만
                st["last_error"] = next((ln for ln in reversed(tail) if ln.strip().startswith(("[FAILED]", " [FAILED]", "[LOCKED]", " [LOCKED]"))),
                                        "exit %s" % code)[:200]
    except subprocess.TimeoutExpired:
        with _LOCK:
            _tab(tab).update({"last_exit": -1, "last_error": "timeout %ss" % RUN_TIMEOUT_SEC})
    except Exception as e:                       # noqa: BLE001
        with _LOCK:
            _tab(tab).update({"last_exit": -2, "last_error": type(e).__name__})
    finally:
        with _LOCK:
            _load(force=True)
            _tab(tab)["running"] = False
            _save()


def _worker():
    """디바운스 창이 닫힌 탭부터 순서대로(한 번에 한 탭 — advisory lock 이 어차피 직렬화한다)."""
    global _WORKER
    while True:
        time.sleep(1.0)
        with _LOCK:
            _load(force=True)
            now = time.time()
            ready = []
            for t, ts in list(_PENDING.items()):
                if now - ts < DEBOUNCE_SEC:
                    continue
                last = float((_STATE.get(t) or {}).get("last_started_ts") or 0)
                if now - last < MIN_GAP_SEC:
                    continue                          # 간격이 찰 때까지 대기(요청 유지)
                ready.append(t)
            for t in ready:
                _PENDING.pop(t, None)
            if not _PENDING and not ready:
                _WORKER = None
                return
        for t in [x for x in TABS if x in ready]:
            _run_tab(t)


def _ensure_worker():
    global _WORKER
    if _WORKER is None or not _WORKER.is_alive():
        _WORKER = threading.Thread(target=_worker, daemon=True)
        _WORKER.start()


@router.post("/api/hr/mirror")
async def mirror(request: Request):
    gate = api_hr._gate(request)
    if gate == "deny":
        raise HTTPException(403)
    if gate != "ok":
        raise HTTPException(503)
    try:
        body = await request.json()
        tabs = body.get("tabs") if isinstance(body, dict) else None
        if not isinstance(tabs, list) or not tabs:
            raise ValueError
    except Exception:
        raise HTTPException(400, "본문 = {\"tabs\": [\"appl\", …]}")
    with _LOCK:
        _load(force=True)
        run, skip = plan(tabs, _STATE, time.time())
        queued = []
        for t in run + [t for t, why in skip if why == "min-gap"]:
            _PENDING[t] = time.time()
            _tab(t)["queued"] = True
            queued.append(t)
        _save()
    _ensure_worker()
    return {"ok": True, "queued": sorted(set(queued)), "skipped": [t for t, why in skip if why == "unknown-tab"],
            "debounce_sec": DEBOUNCE_SEC, "min_gap_sec": MIN_GAP_SEC}


@router.get("/api/hr/mirror/health")
def health():
    with _LOCK:
        _load(force=True)
        snap = json.loads(json.dumps(_STATE))
        pending = sorted(_PENDING)
    now = datetime.datetime.now(KST)
    for t, st in snap.items():
        st.pop("last_started_ts", None)
        try:
            ok = datetime.datetime.fromisoformat(st["last_ok_at"])
            st["lag_sec"] = int((now - ok).total_seconds())
        except Exception:
            st["lag_sec"] = None
    return JSONResponse({"at": now.isoformat(timespec="seconds"), "tabs": snap, "pending": pending,
                         "debounce_sec": DEBOUNCE_SEC, "min_gap_sec": MIN_GAP_SEC, "wait_lock_sec": WAIT_LOCK_SEC})


def _selfcheck():
    run, skip = plan(["appl", "nope", "hire"], {"hire": {"last_started_ts": 1000.0}}, 1030.0)
    assert run == ["appl"] and ("nope", "unknown-tab") in skip and ("hire", "min-gap") in skip, (run, skip)
    run, skip = plan(["hire"], {"hire": {"last_started_ts": 1000.0}}, 1100.0)
    assert run == ["hire"] and not skip
    print("selfcheck ok")


if __name__ == "__main__":
    _selfcheck()
