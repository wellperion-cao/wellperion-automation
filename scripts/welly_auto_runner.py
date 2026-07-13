"""
welly_auto_runner.py — 예약 Claude 러너 MVP (배237 phase3, GM 승인 2026-07-13).
정본 계획: docs/superpowers/specs/2026-07-13-welly-auto-runner-design.md

목표: 스케줄에 headless claude 세션을 자동으로 띄워, 가역·저위험 배 1척을
     실제 실행→검증→커밋까지 관통시킨다("웰리가 시켜서 완료까지"를 실제로 가능케).

★안전모델(기본 OFF)★
  1) 선별: welly_orchestrate.select_autonomous_ships(가역·담당 clevel·등록부 존재) +
     저위험 추가 필터(EXTRA_LOW_RISK_EXCLUDE_KEYWORDS) + 쿨다운 배 제외.
     난이도(priority) 오름차순 정렬 후 **1척만** 반환.
  2) 게이트: env RUNNER_LIVE(기본 미설정=OFF)="1"일 때만 실제 claude 호출.
     OFF면 dry-run — 배 선택 + 띄울 프롬프트 생성 + 로그만. claude 미호출·커밋 0·
     _queue.json 무변경.
  3) 재귀 폭주 방지: LIVE 실행 시 자식 프로세스 env에 WELLY_AUTO_RUNNER_ACTIVE=1을
     심는다. 이 env가 이미 켜져 있으면(=러너가 띄운 세션이 러너를 다시 부르려는 시도)
     즉시 guard-blocked로 거부(큐 로드조차 안 함).
  4) 폭주·비용 가드: 1회 1척(선별기 구조상 보장) · 실패 배는 COOLDOWN_HOURS 동안
     재선택 금지(status/welly_auto_runner_state.json) · claude 호출 타임아웃.
  5) 역롤백: LIVE 실행 전후 git HEAD 커밋 해시를 로그(status/welly_auto_runner_log.jsonl)에
     남긴다 — 문제 시 `git revert <commit>` 한 줄로 되돌릴 수 있다.

라이브 부작용 0 함수(순수) — select_one_low_risk_ship, build_orchestration_prompt.
run_once만 게이트에 따라 실제 I/O(파일 읽기/쓰기·subprocess) 수행.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from welly_orchestrate import select_autonomous_ships  # noqa: E402  (기존 선별기 재사용)
from module_registry import load_registry  # noqa: E402

# ── 경로 상수 ──
DEFAULT_QUEUE_PATH = os.path.join(_PROJECT_ROOT, "status", "_queue.json")
DEFAULT_STATE_PATH = os.path.join(_PROJECT_ROOT, "status", "welly_auto_runner_state.json")
DEFAULT_LOG_PATH = os.path.join(_PROJECT_ROOT, "status", "welly_auto_runner_log.jsonl")

# ── 게이트·가드 env 이름(기존 게이트들과 별도) ──
LIVE_ENV_VAR = "RUNNER_LIVE"
GUARD_ENV_VAR = "WELLY_AUTO_RUNNER_ACTIVE"

# ── 저위험 추가 제외 키워드(welly_orchestrate.IRREVERSIBLE_KEYWORDS 위에 보강) ──
# 배 지시문 명시: 발행·배포·삭제·외부전송·결제·보안·전략·공식값(기존)
#              + 라이브GAS·시트쓰기 관련(신규, 아래 3종으로 코드화).
EXTRA_LOW_RISK_EXCLUDE_KEYWORDS = (
    "라이브",
    "GAS",
    "시트쓰기",
    "시트 쓰기",
)

COOLDOWN_HOURS = 24
MAX_SHIPS_PER_RUN = 1  # 선별기 구조가 항상 1척만 반환하므로 이 상수는 문서화 목적

_PRIORITY_WEIGHT = {"⛵돛단배": 0, "⛴️여객선": 1, "🛳️크루즈": 2}


def _is_low_risk(ship: dict) -> bool:
    """welly_orchestrate._is_reversible보다 보수적인 저위험 판정(러너 전용 보강)."""
    fields = (
        ship.get("priority") or "",
        ship.get("title") or "",
        ship.get("note") or "",
    )
    text = " ".join(fields)
    return not any(keyword in text for keyword in EXTRA_LOW_RISK_EXCLUDE_KEYWORDS)


def _priority_rank(ship: dict) -> int:
    return _PRIORITY_WEIGHT.get(ship.get("priority"), 1)  # 미표기 배=중간 취급


def select_one_low_risk_ship(clevel, queue, registry=None, cooldown_task_ids=None):
    """
    welly_orchestrate.select_autonomous_ships(가역·해당clevel·활성·등록부존재) 결과에
    저위험 추가 필터 + 쿨다운 배 제외를 적용하고, 난이도(priority) 오름차순 정렬 후
    **1척만** 반환한다. 후보 없으면 None.
    """
    cooldown_task_ids = cooldown_task_ids or set()
    candidates = select_autonomous_ships(clevel, queue, registry=registry)
    candidates = [s for s in candidates if _is_low_risk(s)]
    candidates = [s for s in candidates if s.get("task_id") not in cooldown_task_ids]
    if not candidates:
        return None
    candidates.sort(key=_priority_rank)
    return candidates[0]


def build_orchestration_prompt(ship: dict, clevel: str = "cto", nick: str = "시토") -> str:
    """
    선택된 배 1척을 실행할 headless 세션에 줄 '웰리 오케스트레이션' 프롬프트를 조립한다.
    재귀 폭주 방지 지시를 프롬프트 레벨에서도 명시(코드 가드 WELLY_AUTO_RUNNER_ACTIVE와 이중 방어).
    """
    task_id = ship.get("task_id", "")
    title = ship.get("title", "")
    note = ship.get("note", "")
    priority = ship.get("priority", "")

    return (
        f"너는 웰페리온 AI CEO 웰리다. 아래 배 1척을 담당 C-Level({nick}, {clevel})의 "
        f"도메인 방식으로 실행하라. 이 세션은 예약 러너(welly_auto_runner.py)가 자동으로 "
        f"띄운 것이다.\n\n"
        f"배 ID: {task_id}\n"
        f"난이도: {priority}\n"
        f"제목: {title}\n"
        f"메모: {note}\n\n"
        "절차:\n"
        "1) 이 배를 도메인 방식으로 실행한다(가역 작업만 — 발행·배포·삭제·외부전송·결제·보안·"
        "전략·공식값·라이브 GAS/시트 쓰기는 절대 실행하지 말고 즉시 중단·보고).\n"
        "2) 실행 결과를 검증한다(프론트 변경이면 시크릿 크롬 라이브 렌더로 실측, 스크립트면 "
        "실행 로그/테스트로 증명).\n"
        "3) 변경한 파일만 명시 경로로 git add 후 커밋한다. 커밋 메시지 마지막 두 줄:\n"
        "   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>\n"
        "   Claude-Session: https://claude.ai/code/session_01VXU2K3Rd1oemGiF6E2mE6L\n"
        "4) wellperion-agents/scripts/clevel_post_action.py로 status/_queue.json에 완료를 "
        f"기록한다(--clevel {clevel.upper()} --task-id {task_id} --status 완료 "
        "--artifact-url <증거> --next <다음 한 줄 또는 --terminal>).\n\n"
        "절대 규칙(재귀 폭주 방지): 이 세션에서 welly_auto_runner.py를 실행·수정·재호출하거나 "
        "예약 Claude 러너를 새로 기동하지 마라. 위임 범위를 벗어나는 판단·전략·공식값 변경이 "
        "필요하면 실행을 멈추고 GM 결재로 넘겨라.\n"
        "완료 게이트: 아티팩트(파일·로그·스크린샷)와 라이브 링크(가능하면 시크릿 크롬 실측) "
        "없는 완료 보고는 금지한다."
    )


def _is_live() -> bool:
    return os.environ.get(LIVE_ENV_VAR, "0") == "1"


def _guard_active() -> bool:
    return os.environ.get(GUARD_ENV_VAR, "0") == "1"


def _load_queue(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {"cooldown": {}, "run_count": 0}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _active_cooldown_ids(state: dict, now: datetime | None = None) -> set:
    now = now or datetime.now(timezone.utc)
    ids = set()
    for task_id, info in state.get("cooldown", {}).items():
        until = info.get("until")
        try:
            until_dt = datetime.fromisoformat(until)
        except (TypeError, ValueError):
            continue
        if until_dt > now:
            ids.add(task_id)
    return ids


def _mark_cooldown(state: dict, task_id: str, reason: str, hours: int = COOLDOWN_HOURS,
                    now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    until = (now + timedelta(hours=hours)).isoformat()
    state.setdefault("cooldown", {})[task_id] = {"until": until, "reason": reason}


def _git_head(repo_root: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def _append_log(entry: dict, path: str) -> None:
    entry = dict(entry)
    entry.setdefault("at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_once(
    clevel: str = "cto",
    nick: str = "시토",
    queue_path: str | None = None,
    registry_path: str | None = None,
    state_path: str | None = None,
    log_path: str | None = None,
    live: bool | None = None,
    claude_timeout: int = 1200,
) -> dict:
    """
    러너 1회 실행.
    live=None이면 env RUNNER_LIVE로 판단(기본 OFF=dry-run). 테스트에서는 live=False/True를
    명시해 env에 무관하게 강제할 수 있다.

    반환 dict 키: mode("guard-blocked"|"dry-run"|"live"), ship(dict|None),
    prompt(str|None), executed(bool), commit(str|None), reason(str, 있을 때만).
    """
    queue_path = queue_path or DEFAULT_QUEUE_PATH
    state_path = state_path or DEFAULT_STATE_PATH
    log_path = log_path or DEFAULT_LOG_PATH
    live = _is_live() if live is None else live

    # ── 재귀 폭주 방지 가드: 큐 로드 전에 최우선 차단 ──
    if _guard_active():
        result = {
            "mode": "guard-blocked", "ship": None, "prompt": None,
            "executed": False, "commit": None,
            "reason": f"{GUARD_ENV_VAR}=1 — 러너가 띄운 세션 내부에서의 중첩 실행 차단(재귀 폭주 방지)",
        }
        _append_log({"event": "guard_blocked"}, log_path)
        return result

    queue = _load_queue(queue_path)
    registry = load_registry(registry_path)
    state = _load_state(state_path)
    cooldown_ids = _active_cooldown_ids(state)

    ship = select_one_low_risk_ship(clevel, queue, registry=registry, cooldown_task_ids=cooldown_ids)
    mode = "live" if live else "dry-run"

    if ship is None:
        result = {
            "mode": mode, "ship": None, "prompt": None, "executed": False, "commit": None,
            "reason": "선별된 가역·저위험 배 없음(비가역/타clevel/DONE/쿨다운 전부 제외 후 0건)",
        }
        _append_log({"event": "no_ship", "mode": mode, "clevel": clevel}, log_path)
        return result

    prompt = build_orchestration_prompt(ship, clevel=clevel, nick=nick)

    if not live:
        result = {
            "mode": "dry-run", "ship": ship, "prompt": prompt, "executed": False, "commit": None,
            "reason": f"{LIVE_ENV_VAR}!=1 — dry-run(claude 미호출·커밋0·_queue.json 무변경)",
        }
        _append_log(
            {"event": "dry_run_select", "task_id": ship.get("task_id"), "title": ship.get("title")},
            log_path,
        )
        return result

    # ── LIVE 경로: RUNNER_LIVE=1일 때만 도달 ──
    claude_bin = shutil.which("claude")
    if not claude_bin:
        result = {
            "mode": "live", "ship": ship, "prompt": prompt, "executed": False, "commit": None,
            "reason": "claude CLI 미설치(PATH 미해결) — 실행 불가",
        }
        _append_log({"event": "live_no_claude_cli", "task_id": ship.get("task_id")}, log_path)
        return result

    before_commit = _git_head(_PROJECT_ROOT)
    child_env = dict(os.environ)
    child_env[GUARD_ENV_VAR] = "1"  # 재귀 폭주 방지: 이 세션이 러너를 다시 못 부르게

    cmd = [
        claude_bin, "-p",
        "--model", "claude-sonnet-4-6",
        "--permission-mode", "acceptEdits",
        "--allowedTools", "Read Write Edit Bash(git *) Bash(python*)",
        "--output-format", "text",
    ]
    try:
        proc = subprocess.run(
            cmd, input=prompt, cwd=_PROJECT_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=claude_timeout, env=child_env,
        )
        stderr_text = (proc.stderr or "").strip()
        ok = proc.returncode == 0
    except subprocess.TimeoutExpired:
        ok = False
        stderr_text = f"타임아웃({claude_timeout}s)"
    except Exception as e:  # noqa: BLE001
        ok = False
        stderr_text = f"{type(e).__name__}: {e}"

    after_commit = _git_head(_PROJECT_ROOT)
    new_commit = after_commit if (after_commit and after_commit != before_commit) else None

    state["run_count"] = state.get("run_count", 0) + 1
    if not ok or not new_commit:
        _mark_cooldown(state, ship["task_id"], reason=(stderr_text or "커밋 생성 안 됨")[:200])
    _save_state(state, state_path)

    result = {
        "mode": "live", "ship": ship, "prompt": prompt, "executed": True,
        "success": ok and bool(new_commit), "commit": new_commit, "before_commit": before_commit,
        "stderr_tail": stderr_text[-500:] if stderr_text else "",
    }
    _append_log(
        {
            "event": "live_run", "task_id": ship.get("task_id"), "success": result["success"],
            "commit": new_commit, "before_commit": before_commit,
        },
        log_path,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="예약 Claude 러너 MVP — 가역·저위험 배 1척 자율 실행(게이트: env RUNNER_LIVE)"
    )
    parser.add_argument("--clevel", default="cto", help="대상 C-Level role(기본 cto)")
    parser.add_argument("--nick", default="시토", help="대상 C-Level 닉네임(기본 시토)")
    parser.add_argument(
        "--force-dry-run", action="store_true",
        help="RUNNER_LIVE=1이어도 이번 실행만 강제 dry-run(검증용 — env는 건드리지 않음)",
    )
    args = parser.parse_args()

    live = False if args.force_dry_run else None
    result = run_once(clevel=args.clevel, nick=args.nick, live=live)

    print("=" * 60)
    print(f"[welly_auto_runner] mode={result['mode']} executed={result['executed']}")
    if result.get("reason"):
        print(f"사유: {result['reason']}")
    ship = result.get("ship")
    if ship:
        print(f"선택 배: {ship.get('task_id')} | {ship.get('priority')} | {ship.get('title')}")
    if result["mode"] == "dry-run" and result.get("prompt"):
        print("-" * 60)
        print("[LIVE 발효 시 띄울 프롬프트 미리보기]")
        print(result["prompt"])
    if result.get("commit"):
        print(f"커밋: {result['commit']} (역롤백: git revert {result['commit']})")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
