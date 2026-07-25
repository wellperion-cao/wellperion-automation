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

KST = timezone(timedelta(hours=9))
LOCK_STALE_SEC = 600        # 10분 — 3분 주기의 3배 이상이면 확실히 죽은 것
HEARTBEAT_SEC = 15 * 60     # 15분 — 데이터 무변경이어도 이 이상 조용하면 강제 커밋(죽은 job과 구분)

sys.path.insert(0, str(SCRIPTS_DIR))
from cpo_report import _gas_get  # noqa: E402  (기존 검증된 GAS 조회 헬퍼 재사용 — 신규 포팅 없음)
from git_lock import git_commit_push, GitLockTimeout  # noqa: E402
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


def _content_key(payload: dict) -> str:
    """generated_at_kst/ts를 뺀 실질 내용만 비교(불필요 커밋 방지용 키)."""
    def strip(d):
        if isinstance(d, dict):
            return {k: strip(v) for k, v in d.items() if k not in ("ts", "generated_at_kst")}
        if isinstance(d, list):
            return [strip(x) for x in d]
        return d
    return _stable_dump(strip(payload))


def _should_commit(prev_head: dict | None, new_payload: dict) -> bool:
    """git HEAD 커밋본과 실내용이 같고 하트비트 주기도 안 지났으면 스킵(repo 건강 — 커밋 노이즈 절약).
    HEAD 기준 비교라야 '직전 회차 push가 실패해 작업트리만 앞서 있는' 상태를 정확히 잡아 재시도한다."""
    if prev_head is None:
        return True
    if _content_key(prev_head) != _content_key(new_payload):
        return True
    try:
        prev_ts = prev_head.get("ts") or prev_head.get("adult", {}).get("year", {}).get("ts")
        if prev_ts is None:
            return True
        age_sec = (time.time() * 1000 - prev_ts) / 1000
        return age_sec >= HEARTBEAT_SEC
    except Exception:
        return True


def main() -> int:
    no_push = "--no-push" in sys.argv
    STATUS_DIR.mkdir(parents=True, exist_ok=True)

    if not _lock_acquire():
        _log("[skip] 이전 회차가 아직 실행 중(락 보유) — 이번 회차 건너뜀")
        return 0

    try:
        warnings: list[str] = []
        prev_member = _load_prev(MEMBER_OUT)
        prev_lesson = _load_prev(LESSON_OUT)

        member_payload = build_member(prev_member, warnings)
        lesson_payload = build_lesson(prev_lesson, warnings)
        member_payload["warnings"] = warnings[:]  # 전체 워닝 공유 게시(디버그 편의)
        lesson_payload["warnings"] = warnings[:]

        # 작업트리 파일은 항상 갱신(다음 회차 carry-forward가 최신 시도값을 보게) — 커밋 여부만 별도 판단.
        MEMBER_OUT.write_text(
            json.dumps(member_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        LESSON_OUT.write_text(
            json.dumps(lesson_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        _log(f"[member] {member_payload.get('count', 0)}건, ok={member_payload.get('ok')}")
        a = lesson_payload["adult"]["year"]; y = lesson_payload["youth"]["year"]
        _log(f"[lesson] 성인 {a.get('count', 0)}건(ok={a.get('ok')}) · 유소년 {y.get('count', 0)}건(ok={y.get('ok')})")

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

        if warnings:
            _log("[warn] " + " | ".join(warnings))

        if not changed_paths:
            _log("[done] 커밋할 변경 없음")
            return 0

        if no_push:
            _log("[done] --no-push — 로컬 파일만 갱신, 커밋 생략")
            return 0

        try:
            git_commit_push(
                paths=changed_paths,
                message="chore(cpo): 문의 스냅샷 자동 발행 (inquiry_snapshot)",
                holder="cpo-inquiry-snapshot",
                repo_root=str(ROOT),
            )
            _log("[done] git 커밋·푸시 완료")
        except GitLockTimeout as e:
            _log(f"[error] git lock 타임아웃 — 다음 회차에 재시도: {e}")
        except Exception as e:
            _log(f"[error] git 커밋·푸시 실패(무해 — 파일은 로컬에 남음): {e}")
        return 0
    finally:
        _lock_release()


if __name__ == "__main__":
    sys.exit(main())
