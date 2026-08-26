# -*- coding: utf-8 -*-
"""
문의회원 읽기 서버 스냅샷 job (2026-07-16 시토)
설계 정본: docs/superpowers/specs/2026-07-16-문의읽기-서버스냅샷-design.md

목적: membership.html 첫 진입·모든 기기에서 0초 렌더 — localStorage 캐시가 없는 콜드 화면을 위해
2~3분 주기로 멤버십·강습(연간뷰) 문의 목록을 미리 서버(git)에 덤프해둔다.

데이터 소스: gviz 어댑터를 새로 포팅하지 않고 scripts/cpo_report.py 가 이미 프로덕션에서 쓰는
GAS 엔드포인트(_gas_get·FUNNEL_EXEC_URL)를 그대로 재사용 — 파싱 로직 중복·드리프트 위험 0
(GAS 응답이 곧 페이지가 기대하는 원본 shape). 강습 scope=all(전체보기, 실측 3,525건+)은 이번 범위
제외 — 매 3분 커밋하기엔 너무 크고, 그 화면은 상담사가 자주 여는 기본 화면이 아니다(설계 문서 참고).
그 화면은 기존처럼 페이지에서 GAS 라이브 조회를 그대로 쓴다.

★ 유실 0 원칙: 이 job은 순수 읽기 전용(가속층)이다. 실패해도 페이지의 gviz/GAS 실시간 재검증
경로는 전혀 영향받지 않는다(무조건 발사, 조건부 아님). 이 job이 죽으면 스냅샷이 stale해질 뿐 —
그래서 절대 예외로 죽지 않게 짠다(fail-soft) + 실패는 로그에 남긴다(조용한 실패 금지).

사용:
  python scripts\\cpo_inquiry_snapshot.py            # 조회→덤프→(변경 시)커밋·푸시
  python scripts\\cpo_inquiry_snapshot.py --no-push   # 로컬 파일만 갱신(디버그용, 커밋 안 함)

Task Scheduler: launchers\\cpo_inquiry_snapshot_hidden.vbs (3분 간격, Wellperion-CPO-Inquiry-Snapshot-3min)
되돌리기: schtasks /delete /tn "Wellperion-CPO-Inquiry-Snapshot-3min" /f 후 스크립트·launcher 삭제.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
STATUS_DIR = ROOT / "status"
LOCK_DIR = STATUS_DIR / ".locks" / "cpo_inquiry_snapshot"
MEMBER_OUT = STATUS_DIR / "inquiry_snapshot_member.json"
LESSON_OUT = STATUS_DIR / "inquiry_snapshot_lesson.json"
# 유효회원 명단 스냅샷(2026-08-13 시포 · GM "조회 5~6개를 줄여보자").
# 실측: member_active_list 는 응답이 515KB 인데도 36초가 걸린다(GAS 서버 처리가 느린 것이지
# 덩치 문제가 아니다). 같은 데이터를 이 스냅샷으로 받으면 0.3초다 — 이미 문의 2종이 쓰고 있는
# 방식을 유효회원에도 그대로 붙인다(새 모듈·새 예약 0, 이 스크립트 안에서 한 벌 더 받을 뿐).
ACTIVE_OUT = STATUS_DIR / "member_active_snapshot.json"
# LOSS(종료) 회원 명단 스냅샷 — 2026-08-13 GM 지시("3번 진행"). 실측: LOSS 명단 조회는 6.6초 걸린다.
# 유효회원과 같은 방식으로 미리 담아 두면 첫 화면이 0.3초다. 새 예약·새 모듈 없이 이 주기 안에서 한 벌 더 받는다.
ENDED_OUT = STATUS_DIR / "member_ended_snapshot.json"
# 회원 현황 한 장(2026-08-13 GM "현황 보는 게 너무 불편, 보고가 쉽게 들어가야" — 배312/578 데이터쪽).
# 신규·재등록·LOSS 월별 롤업 + 유효회원 구성 — cpo_report.build_status_onepager() 조립 결과 그대로 dump.
ONEPAGER_OUT = STATUS_DIR / "cpo_status_onepager.json"
ONEPAGER_STALE_SEC = 3 * 3600  # 3시간 — 월별 집계라 3분마다 새로 조회할 필요 없다(종료회원·등록월별 4콜 추가 부하 방지)

KST = timezone(timedelta(hours=9))
LOCK_STALE_SEC = 600        # 10분 — 3분 주기의 3배 이상이면 확실히 죽은 것
# (구 HEARTBEAT_SEC 제거 2026-08-14 — 살아있음 도장용 강제 커밋을 걷어냈다. 근거는 _should_commit 주석.
#  살아있음은 status/heartbeats/cpo-inquiry-snapshot.json + module_silence_detector 가 담당한다.)

sys.path.insert(0, str(SCRIPTS_DIR))
from cpo_report import _gas_get, build_status_onepager  # noqa: E402  (기존 검증된 GAS 조회·집계 재사용 — 신규 포팅 없음)
from module_heartbeat import record_heartbeat, last_heartbeat  # noqa: E402  (공통 유틸 — 자체 재구현 금지)

MODULE_ID = "cpo-inquiry-snapshot"


def _now_kst() -> datetime:
    return datetime.now(KST)


def _log(msg: str) -> None:
    line = f"[{_now_kst().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)


# ── 동시실행 가드 (git_lock.py의 mkdir-atomic 패턴과 동일 사상, 이 job 전용 별도 락) ──
def _lock_acquire() -> bool:
    LOCK_DIR.parent.mkdir(parents=True, exist_ok=True)
    try:
        LOCK_DIR.mkdir()
        (LOCK_DIR / "holder.txt").write_text(
            f"{os.getpid()}|{_now_kst().isoformat()}", encoding="utf-8"
        )
        return True
    except FileExistsError:
        try:
            content = (LOCK_DIR / "holder.txt").read_text(encoding="utf-8").strip()
            ts_str = content.split("|", 1)[1]
            age = (_now_kst() - datetime.fromisoformat(ts_str)).total_seconds()
        except Exception:
            age = LOCK_STALE_SEC + 1  # 판독 불가 → stale 취급(무한 잠김 방지)
        if age > LOCK_STALE_SEC:
            _log(f"[lock] stale({age:.0f}s) — steal")
            shutil.rmtree(LOCK_DIR, ignore_errors=True)
            try:
                LOCK_DIR.mkdir()
                (LOCK_DIR / "holder.txt").write_text(
                    f"{os.getpid()}|{_now_kst().isoformat()}", encoding="utf-8"
                )
                return True
            except Exception:
                return False
        return False


def _lock_release() -> None:
    shutil.rmtree(LOCK_DIR, ignore_errors=True)


# ── 이전 스냅샷 로드(실패 시 carry-forward용 — 작업트리 기준, 가장 최근 시도값) ──
def _load_prev(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── git HEAD 기준 직전 커밋본 로드(커밋 필요 여부 판단용 — 작업트리와 분리하는 이유:
#   작업트리 파일은 있는데 아직 커밋 안 된 상태(직전 회차 push 실패 등)를 "무변경"으로
#   오판해 영원히 재시도 안 하는 사고 방지. HEAD 기준이라야 "이미 원격에 반영됐나"를 정확히 안다). ──
def _load_prev_from_head(path: Path) -> dict | None:
    try:
        rel = path.relative_to(ROOT).as_posix()
        r = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            return None
        return json.loads(r.stdout)
    except Exception:
        return None


def _stable_dump(obj) -> str:
    """생성시각 등 메타 제외하고 비교하기 위한 안정 직렬화(정렬 키)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fetch_bucket(action: str, params: dict | None, label: str, warnings: list) -> tuple[bool, list]:
    """GAS 조회 1회. 성공→(True, rows) / 실패→(False, []) — 재시도는 다음 3분 주기가 대신함(스톰 방지)."""
    try:
        data = _gas_get(action, params, timeout=25, attempts=1)
    except Exception as e:
        data = None
        warnings.append(f"{label}: 예외 {e}")
    if data is None:
        warnings.append(f"{label}: GAS 조회 실패(재시도는 다음 3분 주기)")
        return False, []
    rows = data.get("data")
    if not isinstance(rows, list):
        warnings.append(f"{label}: 응답 shape 이상(data 배열 아님)")
        return False, []
    return True, rows


def build_member(prev: dict | None, warnings: list) -> dict:
    ok, rows = _fetch_bucket("member_inquiry_list", None, "member", warnings)
    now = _now_kst()
    if ok:
        return {"ok": True, "count": len(rows), "rows": rows,
                "ts": int(now.timestamp() * 1000), "generated_at_kst": now.strftime("%Y-%m-%d %H:%M")}
    # 실패 — 직전 값 carry-forward(빈 값으로 덮어쓰지 않음, 유실 0 원칙)
    if prev and isinstance(prev.get("rows"), list):
        warnings.append("member: 직전 스냅샷 carry-forward")
        carried = dict(prev)
        carried["ok"] = False
        return carried
    return {"ok": False, "count": 0, "rows": [],
            "ts": int(now.timestamp() * 1000), "generated_at_kst": now.strftime("%Y-%m-%d %H:%M")}


def build_active(prev: dict | None, warnings: list, scope: str = "valid") -> dict:
    """회원 명단 스냅샷. 화면이 쓰는 모양 그대로 {headers, rows} 로 담는다.
    scope='valid' 유효회원 · 'ended' LOSS 회원(2026-08-13 GM "3번 진행" — LOSS 명단도 첫 화면 0.3초로).
    실패 시 직전 값 carry-forward — 빈 명단으로 덮어쓰지 않는다(유실 0)."""
    now = _now_kst()
    tag = "active" if scope == "valid" else f"active.{scope}"
    try:
        data = _gas_get("member_active_list", {"scope": scope}, timeout=60, attempts=1)
    except Exception as e:
        data = None
        warnings.append(f"{tag}: 예외 {e}")
    rows = (data or {}).get("data")
    if data is not None and isinstance(rows, list) and scope != "valid":
        # LOSS 명단은 상단 카드 숫자를 쓰지 않는다 — 유효회원 쪽에서 이미 한 번 싣는다(중복 조회 0).
        return {"ok": True, "count": len(rows), "headers": data.get("headers") or [], "rows": rows,
                "ts": int(now.timestamp() * 1000), "generated_at_kst": now.strftime("%Y-%m-%d %H:%M")}
    if data is not None and isinstance(rows, list):
        # 상단 카드 숫자(오늘/이번달 문의·등록·이탈)도 같이 실어 보낸다 — 화면이 이 값을 즉시 그리고,
        # 뒤이어 도착하는 GAS 실시간 값이 덮는다. 집계는 서버 값을 그대로 나르기만 한다(계산 복제 0).
        try:
            stats = _gas_get("cpo_today_stats", None, timeout=30, attempts=1)
        except Exception as e:
            stats = None
            warnings.append(f"active.stats: 예외 {e}")
        if not (isinstance(stats, dict) and stats.get("ok")):
            warnings.append("active.stats: 카드 숫자 조회 실패 — 화면은 GAS 실시간 값만 쓴다")
            stats = None
        _append_daily_line(rows, stats, now, warnings)
        return {"ok": True, "count": len(rows), "headers": data.get("headers") or [], "rows": rows,
                "today_stats": stats,
                "ts": int(now.timestamp() * 1000), "generated_at_kst": now.strftime("%Y-%m-%d %H:%M")}
    warnings.append(f"{tag}: GAS 조회 실패(재시도는 다음 주기)")
    if prev and isinstance(prev.get("rows"), list):
        warnings.append(f"{tag}: 직전 스냅샷 carry-forward")
        carried = dict(prev)
        carried["ok"] = False
        return carried
    return {"ok": False, "count": 0, "headers": [], "rows": [],
            "ts": int(now.timestamp() * 1000), "generated_at_kst": now.strftime("%Y-%m-%d %H:%M")}


DAILY_OUT = STATUS_DIR / "member_daily.jsonl"


def _append_daily_line(rows: list, stats: dict | None, now, warnings: list) -> None:
    """하루 1줄 — 그날 회원 구성이 어땠는지 남긴다(2026-08-26 시포 · GM 지적).

    배경: 회원 수 스냅샷(member_active_snapshot.json)은 3분마다 같은 파일을 덮어써서
    **어제 값이 남지 않는다.** 그래서 오늘 숫자가 어제와 달라도 무엇이 달라졌는지 댈 근거가
    없었다 — GM 이 "어제 정원이랑 오늘 정원이랑 차이가 확 난다"고 본 그 자리다.
    회원 롤업 모듈은 주간(월요일)이라 일 단위 비교를 못 받쳐 준다.

    하루 첫 실행에만 한 줄 쓴다(같은 날 두 번 쓰지 않는다). 파일은 append 전용이라
    .gitattributes 의 `*.jsonl merge=union` 이 세션 충돌을 알아서 합친다(새 장치 0).
    """
    try:
        today = now.strftime("%Y-%m-%d")
        if DAILY_OUT.exists():
            tail = DAILY_OUT.read_text(encoding="utf-8").rstrip().rsplit("\n", 1)[-1]
            if tail and f'"date": "{today}"' in tail:
                return
        kinds: dict[str, int] = {}
        for r in rows:
            v = str(r.get("회원\n구분") or r.get("회원구분") or "").strip() or "미기재"
            kinds[v] = kinds.get(v, 0) + 1
        line = {
            "date": today,
            "at": now.strftime("%H:%M"),
            "유효회원": len(rows),
            "구분별": kinds,
        }
        if isinstance(stats, dict) and stats.get("ok"):
            for src, dst in (("memberCorp", "법인"), ("memberEnded", "종료"),
                             ("monthReg", "당월등록"), ("monthLoss", "당월이탈")):
                if stats.get(src) is not None:
                    line[dst] = stats[src]
        with DAILY_OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        _log(f"[daily] 회원 하루 기록 append — 유효 {len(rows)}명")
    except Exception as e:
        warnings.append(f"active.daily: 하루 기록 실패 {e}")


def build_lesson(prev: dict | None, warnings: list) -> dict:
    now = _now_kst()
    prev_adult = (prev or {}).get("adult", {}).get("year") if prev else None
    prev_youth = (prev or {}).get("youth", {}).get("year") if prev else None

    ok_a, rows_a = _fetch_bucket("lesson_inquiry_list", {"type": "성인강습"}, "lesson.adult.year", warnings)
    ok_y, rows_y = _fetch_bucket("lesson_inquiry_list", {"type": "유소년강습"}, "lesson.youth.year", warnings)

    def _bucket(ok, rows, prev_bucket, label):
        if ok:
            return {"ok": True, "count": len(rows), "rows": rows,
                     "ts": int(now.timestamp() * 1000), "generated_at_kst": now.strftime("%Y-%m-%d %H:%M")}
        if prev_bucket and isinstance(prev_bucket.get("rows"), list):
            warnings.append(f"{label}: 직전 스냅샷 carry-forward")
            carried = dict(prev_bucket)
            carried["ok"] = False
            return carried
        return {"ok": False, "count": 0, "rows": [],
                 "ts": int(now.timestamp() * 1000), "generated_at_kst": now.strftime("%Y-%m-%d %H:%M")}

    return {
        "adult": {"year": _bucket(ok_a, rows_a, prev_adult, "lesson.adult.year")},
        "youth": {"year": _bucket(ok_y, rows_y, prev_youth, "lesson.youth.year")},
    }


def build_onepager(prev: dict | None, warnings: list, active_payload: dict) -> dict:
    """회원 현황 한 장 — 신선도 게이트(ONEPAGER_STALE_SEC) 이내면 직전 값 그대로 반환(재조회 없음).
    지날 때만 build_status_onepager() 호출 — 종료회원·월별 등록리스트 등 무거운 추가 GAS 콜은
    이 게이트 통과 시에만 나간다(3분마다 쏘지 않는다, 월별 집계라 그럴 필요가 없다).
    유효회원(scope=valid) 행은 이 회차의 active_payload에서 재사용 — 중복 조회 금지."""
    now = _now_kst()
    if prev and isinstance(prev.get("ts"), (int, float)):
        age_sec = (now.timestamp() * 1000 - prev["ts"]) / 1000
        if age_sec < ONEPAGER_STALE_SEC:
            return prev  # 신선 — 이번 회차는 스킵(직전 값 그대로 carry)
    valid_rows = active_payload.get("rows") if active_payload.get("ok") else None
    try:
        payload = build_status_onepager(valid_rows=valid_rows)
    except Exception as e:
        warnings.append(f"onepager: 예외 {e}")
        if prev:
            warnings.append("onepager: 직전 스냅샷 carry-forward")
            return prev
        return {"generated_at": now.strftime("%Y-%m-%d %H:%M:%S"), "ts": int(now.timestamp() * 1000),
                "composition": {"ok": False, "detail": "조회 실패(못 잼)"}, "월별": {}}
    return payload


def _content_key(payload: dict) -> str:
    """generated_at_kst/ts를 뺀 실질 내용만 비교(불필요 커밋 방지용 키)."""
    def strip(d):
        if isinstance(d, dict):
            return {k: strip(v) for k, v in d.items() if k not in ("ts", "generated_at_kst", "generated_at")}
        if isinstance(d, list):
            return [strip(x) for x in d]
        return d
    return _stable_dump(strip(payload))


def _should_commit(prev_head: dict | None, new_payload: dict) -> bool:
    """git HEAD 커밋본과 실내용이 다를 때만 커밋한다(repo 건강 — 커밋 노이즈 절약).
    HEAD 기준 비교라야 '직전 회차 push가 실패해 작업트리만 앞서 있는' 상태를 정확히 잡아 재시도한다.

    ★살아있음 도장을 위한 강제 커밋을 걷어냈다 (2026-08-14 시토 · GM 물음).
      무엇이었나: 내용이 그대로여도 15분마다 한 번은 커밋해 '이 job 이 죽지 않았다'를 남겼다.
      실측(2026-08-14): 그 결과 오늘 커밋 354건 중 256건(72%)이 기계 커밋이었고, 이 스냅샷
      파일만 61건이었다. 그중 40건을 표본으로 열어 보니 **40건 전부 바뀐 줄이 시각 한 줄뿐**
      이었다(값 변화 0). 3분마다 도는 job 이 깃 이력을 도배하고, 커밋마다 push 가 붙어
      동시 커밋 충돌(INC-008 계열)의 확률을 스스로 올리고 있었다.
      왜 지워도 되나: 살아있음은 이미 **다른 곳에서 재고 있다** —
      status/heartbeats/cpo-inquiry-snapshot.json 을 매 회차 갱신하고,
      module_silence_detector 가 그 파일이 조용해지면 잡는다(module_reporter 가 매일 호출).
      같은 신호를 두 곳에서 낼 이유가 없다(약속 L01·L21). 깃 이력은 사람이 읽는 곳이지
      기계의 맥박을 적는 곳이 아니다.
    """
    if prev_head is None:
        return True
    return _content_key(prev_head) != _content_key(new_payload)


# ── 고객 접수 백엔드 예열 (배236 · GM 지시 2026-08-16) ──────────────────────────
# 왜: 접수만 별도 백엔드(intake-api)로 떼어낸 것은 GM 결재(2026-08-06)다. 그런데 실측해
#   보니 **예열된 상태 1.33초 vs 식은 상태 중앙값 8.87초(최대 69초)** 였다. 접수는 하루에
#   몇 건뿐이라 대부분 식어 있고, 식은 컨테이너를 깨우는 값이 덩치를 줄여 번 값보다 훨씬
#   크다 — 그래서 화면 주소를 옮기면 실제 고객 접수가 오히려 2초에서 9초로 느려진다.
#   기존 백엔드가 빠른 이유도 실력이 아니라 하루 종일 화면들이 두드려 늘 데워져 있어서다.
# 그래서 결재를 뒤집는 대신 같은 조건을 만들어 준다 — 3분마다 도는 이 job 이 지나가는 길에
#   진단용 ping 을 한 번 던져 컨테이너를 깨워 둔다. 새 예약작업·새 스크립트 0(약속 L21).
# ping 은 Intake.js 가 이미 갖고 있는 읽기 전용 진단 액션이다(쓰기·발신 없음).
# 실패는 무시한다 — 이건 가속층이고, 못 데워도 접수 자체는 종전대로 동작한다.
_INTAKE_PING_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbyLc2cnOeyyCpdrluJrgrUNrfhSJS3W-9wte5ndOBNS5S8Dux7KwcV8WAAXs2bwi2yFcw/exec"
)


def _warm_intake_api() -> None:
    import urllib.request
    t0 = time.time()
    try:
        req = urllib.request.Request(_INTAKE_PING_URL + "?action=ping",
                                     headers={"User-Agent": "wellperion-warmup"})
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read(200)
        _log(f"[warm] 접수 백엔드 예열 {time.time() - t0:.2f}초")
    except Exception as e:
        _log(f"[warm] 접수 백엔드 예열 건너뜀(무해): {type(e).__name__}: {str(e)[:80]}")
def main() -> int:
    no_push = "--no-push" in sys.argv
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    _warm_intake_api()

    if not _lock_acquire():
        _log("[skip] 이전 회차가 아직 실행 중(락 보유) — 이번 회차 건너뜀")
        return 0

    try:
        warnings: list[str] = []
        prev_member = _load_prev(MEMBER_OUT)
        prev_lesson = _load_prev(LESSON_OUT)
        prev_active = _load_prev(ACTIVE_OUT)

        prev_onepager = _load_prev(ONEPAGER_OUT)

        member_payload = build_member(prev_member, warnings)
        lesson_payload = build_lesson(prev_lesson, warnings)
        active_payload = build_active(prev_active, warnings)
        ended_payload = build_active(_load_prev(ENDED_OUT), warnings, scope="ended")
        onepager_payload = build_onepager(prev_onepager, warnings, active_payload)
        member_payload["warnings"] = warnings[:]  # 전체 워닝 공유 게시(디버그 편의)
        lesson_payload["warnings"] = warnings[:]
        active_payload["warnings"] = warnings[:]
        ended_payload["warnings"] = warnings[:]

        # 작업트리 파일은 항상 갱신(다음 회차 carry-forward가 최신 시도값을 보게) — 커밋 여부만 별도 판단.
        MEMBER_OUT.write_text(
            json.dumps(member_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        LESSON_OUT.write_text(
            json.dumps(lesson_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        ACTIVE_OUT.write_text(
            json.dumps(active_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        ENDED_OUT.write_text(
            json.dumps(ended_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        ONEPAGER_OUT.write_text(
            json.dumps(onepager_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _log(f"[active] {active_payload.get('count', 0)}명, ok={active_payload.get('ok')}")
        _log(f"[ended] {ended_payload.get('count', 0)}명, ok={ended_payload.get('ok')}")
        _log(f"[member] {member_payload.get('count', 0)}건, ok={member_payload.get('ok')}")
        a = lesson_payload["adult"]["year"]; y = lesson_payload["youth"]["year"]
        _log(f"[lesson] 성인 {a.get('count', 0)}건(ok={a.get('ok')}) · 유소년 {y.get('count', 0)}건(ok={y.get('ok')})")
        _op_comp = onepager_payload.get("composition", {})
        _log(f"[onepager] 유효회원 {_op_comp.get('유효회원_전체', '-')} · 그중 대기 {_op_comp.get('대기', '-')} · 법인 {_op_comp.get('법인', '-')} (ok={_op_comp.get('ok')})")

        # 가동 신호는 하트비트 1곳에만 남긴다(2026-07-25 시포·배1). 예전엔 회차마다 커밋이
        # 완료-배를 낳아 G1 '입항 완료(오늘)'를 도배했다 — 배는 실무 신호용이고, 무인 모듈의
        # '살아있음'은 자율현황 카드가 볼 자리(status/heartbeats/)가 정본이다. 파일을 실제로
        # 쓴 뒤에 부른다(스크립트 진입부 호출 금지 — 거짓 하트비트가 INC-018의 본질).
        _prev_hb = last_heartbeat(MODULE_ID) or {}
        _runs = int(_prev_hb.get("누적_회차") or 0) + 1  # extra는 평평하게 병합된다(중첩 아님)
        record_heartbeat(
            MODULE_ID,
            detail=(f"멤버십 {member_payload.get('count', 0)}건 · 성인강습 {a.get('count', 0)}건 · "
                    f"유소년 {y.get('count', 0)}건 (누적 {_runs}회차)"),
            extra={"누적_회차": _runs, "멤버십": member_payload.get("count", 0),
                   "성인강습": a.get("count", 0), "유소년": y.get("count", 0)},
        )

        changed_paths = []
        if _should_commit(_load_prev_from_head(MEMBER_OUT), member_payload):
            changed_paths.append(str(MEMBER_OUT))
        else:
            _log("[member] HEAD 대비 무변경(하트비트 이내) — 커밋 스킵")
        if _should_commit(_load_prev_from_head(LESSON_OUT), lesson_payload):
            changed_paths.append(str(LESSON_OUT))
        else:
            _log("[lesson] HEAD 대비 무변경(하트비트 이내) — 커밋 스킵")
        if _should_commit(_load_prev_from_head(ACTIVE_OUT), active_payload):
            changed_paths.append(str(ACTIVE_OUT))
        if _should_commit(_load_prev_from_head(ENDED_OUT), ended_payload):
            changed_paths.append(str(ENDED_OUT))
        else:
            _log("[active] HEAD 대비 무변경(하트비트 이내) — 커밋 스킵")
        if _should_commit(_load_prev_from_head(ONEPAGER_OUT), onepager_payload):
            changed_paths.append(str(ONEPAGER_OUT))
        else:
            _log("[onepager] HEAD 대비 무변경(신선도 게이트 이내) — 커밋 스킵")

        if warnings:
            _log("[warn] " + " | ".join(warnings))

        if not changed_paths:
            _log("[done] 커밋할 변경 없음")
            return 0

        if no_push:
            _log("[done] --no-push — 로컬 파일만 갱신, 커밋 생략")
            return 0

        # 커밋은 safe_commit 하나로 모은다(2026-07-25 시포 · 부팅 스킬 §5-2 커밋 관문 단일화).
        #   그전엔 git_commit_push 를 직접 불렀고, 이 저장소가 detached HEAD 로 돌 때마다
        #   push 가 "You are not currently on a branch" 로 죽었다 — 로그에 452건 누적(실측
        #   2026-07-25). 커밋은 됐지만 push 가 안 돼 라이브 반영이 다른 워처 손에 달려 있었고,
        #   index.lock 경합·pre-commit 훅 충돌까지 합쳐 매 회차 빨간 로그가 쌓였다.
        #   safe_commit 은 락 직렬화·HEAD 재검증·지정 경로만 담기·detached HEAD 를 모두 처리한다.
        rel_paths = [str(Path(p).resolve().relative_to(ROOT)).replace("\\", "/") for p in changed_paths]
        try:
            r = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "safe_commit.py"),
                 "-m", "chore(cpo): 문의 스냅샷 자동 발행 (inquiry_snapshot)", "--", *rel_paths],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=180,
            )
            tail = (r.stdout or "").strip().splitlines()
            _log("[done] " + (tail[0] if tail else "safe_commit 출력 없음"))
            if r.returncode != 0:
                _log(f"[warn] safe_commit rc={r.returncode} — 파일은 로컬에 남음, 다음 회차 재시도")
        except Exception as e:
            _log(f"[warn] 커밋 실패(무해 — 파일은 로컬에 남음): {type(e).__name__}: {str(e)[:120]}")
        return 0
    finally:
        _lock_release()


if __name__ == "__main__":
    sys.exit(main())
