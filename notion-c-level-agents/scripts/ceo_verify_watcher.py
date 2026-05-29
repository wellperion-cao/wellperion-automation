# -*- coding: utf-8 -*-
"""CEO push-triggered verification watcher (검증 워처)

C-Level이 작업 완료 후 `[DONE][<CLEVEL>][<task_id>]` 태그가 담긴 commit을 push 하면,
CEO 워처가 이를 감지해 2단계 검증(LAYER 1 기계 검증 + LAYER 2 AI 검증)을 수행하고
APPROVED / REJECTED / AI_PENDING 판정을 내린 뒤 텔레그램 CEO 채널로 보고한다.

핵심 안전 원칙:
  - 완료 신호 = DUAL 신호(둘 다 필수): ① commit 메시지 태그 ② status/<clevel>.json status==DONE
    한쪽만 있으면 MISMATCH → 처리 안 함 (단일 신호로 승인 절대 금지).
  - 자동 재작업(rework) 절대 없음: 반려해도 C-Level 재트리거 금지. ledger 기록으로 루프 방지.
  - AI fallback 시 자동 승인 절대 금지: fit=None(AI_PENDING) → 수동 확인만 ping.
  - cursor·ledger는 atomic write(임시 파일 후 replace)로 크래시 생존.

실행:
  python ceo_verify_watcher.py --once                  # 1회 검증 패스 (기본)
  python ceo_verify_watcher.py --watch --interval 60   # 60초마다 폴링
  python ceo_verify_watcher.py --once --no-ai          # AI(LAYER 2) 생략
  python ceo_verify_watcher.py --once --dry-run        # 텔레그램·기록 없이 의도만 출력

환경변수 (.env, HardLink → telegram_bot/.env):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID = 8254867551   (CEO 단일 채널)
"""

import argparse
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows 터미널 출력 인코딩을 UTF-8로 강제 (한글 안전 출력)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 패키지 루트를 sys.path에 추가 (telegram_notifier import 용)
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_PACKAGE_ROOT / ".env")
except ImportError:
    pass  # dotenv 없으면 환경 변수에서 직접 읽음

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ceo_verify_watcher")

# ── 상수 ─────────────────────────────────────────────────────────────────────

DEFAULT_REPO = Path(r"C:\Users\jjky0\welperion-automation")
CLAUDE_CMD = shutil.which("claude") or "claude"

# commit 메시지 태그: [DONE][<CLEVEL>][<task_id>]
DONE_TAG_RE = re.compile(r"\[DONE\]\[([A-Za-z]+)\]\[([^\]]+)\]")

# 판정값
APPROVED = "APPROVED"
REJECTED = "REJECTED"
AI_PENDING = "AI_PENDING"
MISMATCH = "MISMATCH"

# git log 필드 구분자 (subprocess 파싱 안정성)
_FS = "\x1f"  # field separator


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 경로 헬퍼 ─────────────────────────────────────────────────────────────────

def status_dir(repo: Path) -> Path:
    return repo / "status"


def cursor_path(repo: Path) -> Path:
    return status_dir(repo) / "_ceo_cursor.txt"


def ledger_path(repo: Path) -> Path:
    return status_dir(repo) / "_ceo_processed.json"


def clevel_status_path(repo: Path, clevel: str) -> Path:
    return status_dir(repo) / f"{clevel.lower()}.json"


def ceo_log_path(repo: Path) -> Path:
    return repo / "logs" / "ceo_log.jsonl"


def stale_path(repo: Path) -> Path:
    return status_dir(repo) / "_ceo_mismatch_stale.json"


# Maximum consecutive passes a MISMATCH SHA may pin the cursor before GM escalation.
MISMATCH_STALE_LIMIT = 20


def read_stale(repo: Path) -> dict:
    """staleness counter map: {sha: int}."""
    p = stale_path(repo)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def write_stale(repo: Path, stale: dict) -> None:
    _atomic_write_text(stale_path(repo), json.dumps(stale, ensure_ascii=False, indent=2))


# ── atomic I/O ────────────────────────────────────────────────────────────────

def _atomic_write_text(path: Path, text: str) -> None:
    """임시 파일에 쓴 뒤 os.replace 로 원자적 교체 (크래시 생존).
    fsync 후 replace — ledger/cursor 내구성 보장.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def read_cursor(repo: Path) -> str:
    p = cursor_path(repo)
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return ""


def write_cursor(repo: Path, sha: str) -> None:
    _atomic_write_text(cursor_path(repo), sha.strip() + "\n")


def read_ledger(repo: Path) -> list:
    p = ledger_path(repo)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"ledger 파싱 실패, 빈 ledger로 진행: {exc}")
    return []


def write_ledger(repo: Path, ledger: list) -> None:
    _atomic_write_text(ledger_path(repo), json.dumps(ledger, ensure_ascii=False, indent=2))


def read_clevel_status(repo: Path, clevel: str) -> dict:
    p = clevel_status_path(repo, clevel)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"{p.name} 파싱 실패: {exc}")
        return {}


def status_task_id(data: dict) -> str:
    """status JSON에서 task_id 추출 — GM 신규 키 우선, 기존 키 폴백."""
    return data.get("task_id") or data.get("last_task_id") or ""


def status_value(data: dict) -> str:
    return (data.get("status") or "").upper()


def append_ceo_log(repo: Path, record: dict) -> None:
    p = ceo_log_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── git 헬퍼 (subprocess, agent_tasks_watcher run_omc 스타일) ──────────────────

def _git(repo: Path, args: list, timeout: int = 60) -> tuple[int, str, str]:
    """git 명령 실행. (returncode, stdout, stderr) 반환. 예외 시 (-1, '', msg)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo)] + args,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return -1, "", "git CLI 없음"
    except subprocess.TimeoutExpired:
        return -1, "", f"git timeout ({timeout}s)"
    except Exception as exc:
        return -1, "", str(exc)


def git_fetch(repo: Path) -> bool:
    """git fetch origin master (quiet). 오프라인이면 catch+log 후 False 반환."""
    rc, _out, err = _git(repo, ["fetch", "origin", "master", "--quiet"], timeout=60)
    if rc != 0:
        logger.warning(f"git fetch 실패(오프라인 가능) — 처리 건너뜀: {err.strip()[:200]}")
        return False
    return True


def git_head(repo: Path) -> str:
    rc, out, _ = _git(repo, ["rev-parse", "origin/master"], timeout=20)
    return out.strip() if rc == 0 else ""


def git_cursor_valid(repo: Path, sha: str) -> bool:
    """cursor SHA가 git history에 실제 존재하는지 확인."""
    return git_object_type(repo, sha) == "commit"


def git_new_commits(repo: Path, cursor: str) -> list:
    """cursor..origin/master 의 신규 commit 목록 (오래된 순). [(sha, subject, author)]."""
    fmt = f"%H{_FS}%s{_FS}%an"
    rng = f"{cursor}..origin/master" if cursor else "origin/master"
    rc, out, err = _git(repo, ["log", rng, f"--format={fmt}", "--reverse"], timeout=30)
    if rc != 0:
        logger.warning(f"git log 실패: {err.strip()[:200]}")
        return []
    commits = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(_FS)
        if len(parts) >= 3:
            commits.append((parts[0], parts[1], parts[2]))
    return commits


def git_object_type(repo: Path, sha: str) -> str:
    rc, out, _ = _git(repo, ["cat-file", "-t", sha], timeout=20)
    return out.strip() if rc == 0 else ""


def git_show_stat(repo: Path, sha: str) -> str:
    rc, out, _ = _git(repo, ["show", "--stat", "--format=%s%n%b", sha], timeout=30)
    return out.strip() if rc == 0 else ""


# ── commit 메시지 파싱 ────────────────────────────────────────────────────────

def parse_done_tag(subject: str):
    """commit subject에서 [DONE][CLEVEL][task_id] 추출. (clevel_lower, task_id) 또는 None."""
    m = DONE_TAG_RE.search(subject or "")
    if not m:
        return None
    return (m.group(1).lower(), m.group(2).strip())


# ── HTTP (artifact_url 검증) ─────────────────────────────────────────────────

def http_ok(url: str, timeout: int = 10) -> tuple[bool, str]:
    """artifact_url GET → status 200 기대. (ok, reason)."""
    try:
        import requests
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            return True, "200"
        return False, f"HTTP {resp.status_code}"
    except ImportError:
        # urllib 폴백
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "ceo-verify-watcher"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                code = getattr(r, "status", r.getcode())
                if code == 200:
                    return True, "200"
                return False, f"HTTP {code}"
        except Exception as exc:
            return False, f"artifact 접근 실패: {exc}"
    except Exception as exc:
        return False, f"artifact 접근 실패: {exc}"


# ── LAYER 1: 기계 검증 (순수 Python, AI 없음) ────────────────────────────────

def layer1_verify(repo: Path, sha: str, clevel: str, task_id: str,
                  artifact_url, ledger: list) -> dict:
    """LAYER 1 기계 검증. {passed: bool, reasons: [...]}."""
    reasons = []
    passed = True

    # a. commit 객체 존재
    if git_object_type(repo, sha) != "commit":
        passed = False
        reasons.append(f"commit {sha[:8]} 객체가 존재하지 않음")
    else:
        reasons.append(f"commit {sha[:8]} 존재 확인")

    # b. artifact_url (non-null) HTTP 200
    if artifact_url:
        ok, why = http_ok(artifact_url)
        if ok:
            reasons.append(f"artifact 200 OK ({artifact_url})")
        else:
            passed = False
            reasons.append(f"artifact 검증 실패: {why}")
    else:
        reasons.append("artifact_url 없음 — 스킵")

    # c. SSOT 중복: 동일 task_id가 다른 commit으로 이미 APPROVED 되어 있으면 충돌
    for rec in ledger:
        if (rec.get("task_id") == task_id
                and rec.get("verdict") == APPROVED
                and rec.get("commit") != sha):
            passed = False
            reasons.append(
                f"SSOT 충돌: task_id '{task_id}' 가 이미 다른 commit "
                f"{str(rec.get('commit'))[:8]} 로 APPROVED 됨"
            )
            break

    return {"passed": passed, "reasons": reasons}


# ── LAYER 2: AI 검증 (claude headless, run_omc 스타일) ────────────────────────

def _build_ai_prompt(ctx: dict) -> str:
    return (
        "당신은 웰페리온 AI CEO 검증관입니다. 한 C-Level이 아래 작업을 완료했다고 보고했습니다.\n"
        "이 작업이 OMC 운영 원칙(최소 변경·증거 기반·과도 설계 금지)과 태스크 의도에 부합하는지 판정하세요.\n\n"
        f"- C-Level: {ctx.get('clevel')}\n"
        f"- task_id: {ctx.get('task_id')}\n"
        f"- title: {ctx.get('title')}\n"
        f"- commit subject: {ctx.get('subject')}\n"
        f"- artifact_url: {ctx.get('artifact_url')}\n"
        f"- git show --stat:\n{ctx.get('show_stat', '')[:2000]}\n\n"
        "반드시 STRICT JSON 한 줄로만 답하세요. 다른 텍스트 금지:\n"
        '{"fit": true 또는 false, "reason": "...", "principle_check": "..."}'
    )


def _extract_json(text: str):
    """claude 출력에서 마지막 JSON 오브젝트 추출 시도."""
    text = text.strip()
    # --output-format json 래퍼면 result 필드를 먼저 펼침
    try:
        wrapper = json.loads(text)
        if isinstance(wrapper, dict) and "result" in wrapper and isinstance(wrapper["result"], str):
            text = wrapper["result"].strip()
        elif isinstance(wrapper, dict) and "fit" in wrapper:
            return wrapper
    except Exception:
        pass
    # 본문에서 {...} 추출
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None
    return None


def ai_layer_verify(ctx: dict, no_ai: bool = False) -> dict:
    """LAYER 2 AI 검증. {fit: true|false|None, reason, principle_check}.

    GRACEFUL FALLBACK: claude CLI 없음/오류/파싱불가 → fit=None, reason='AI_PENDING'.
    --no-ai → fit=None, reason='AI_SKIPPED'. 어떤 경우에도 자동 승인 없음.
    """
    if no_ai:
        return {"fit": None, "reason": "AI_SKIPPED", "principle_check": "AI 검증 생략(--no-ai)"}

    prompt = _build_ai_prompt(ctx)
    try:
        proc = subprocess.run(
            [CLAUDE_CMD, "--dangerously-skip-permissions",
             "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300,
        )
    except FileNotFoundError:
        logger.warning(f"claude CLI 없음 ({CLAUDE_CMD}) — AI_PENDING")
        return {"fit": None, "reason": "AI_PENDING", "principle_check": "claude CLI 없음"}
    except subprocess.TimeoutExpired:
        logger.warning("claude 호출 타임아웃 — AI_PENDING")
        return {"fit": None, "reason": "AI_PENDING", "principle_check": "AI 호출 타임아웃"}
    except Exception as exc:
        logger.warning(f"claude 호출 예외 — AI_PENDING: {exc}")
        return {"fit": None, "reason": "AI_PENDING", "principle_check": str(exc)}

    if proc.returncode != 0:
        logger.warning(f"claude 비정상 종료({proc.returncode}) — AI_PENDING")
        return {"fit": None, "reason": "AI_PENDING", "principle_check": f"exit {proc.returncode}"}

    verdict = _extract_json(proc.stdout)
    if not isinstance(verdict, dict) or "fit" not in verdict:
        logger.warning("claude 출력 파싱 불가 — AI_PENDING")
        return {"fit": None, "reason": "AI_PENDING", "principle_check": "출력 파싱 불가"}

    fit = verdict.get("fit")
    if fit not in (True, False):
        fit = None
    return {
        "fit": fit,
        "reason": verdict.get("reason", ""),
        "principle_check": verdict.get("principle_check", ""),
    }


# ── 단건 처리 ─────────────────────────────────────────────────────────────────

def process_commit(repo: Path, sha: str, subject: str, author: str,
                   ledger: list, telegram, no_ai: bool, dry_run: bool) -> dict:
    """단일 commit을 검증·판정·기록·보고. 결과 dict 반환(판정 포함).

    부수효과(dry_run=False): ceo_log append, telegram 발송, ledger append.
    cursor 전진은 호출자가 패스 종료 시 일괄 처리.
    """
    tag = parse_done_tag(subject)
    if not tag:
        return {"verdict": None, "skipped": "non-DONE"}

    clevel, task_id = tag
    cl = clevel.upper()

    # 멱등성: (task_id, commit) 이미 처리됨 → 스킵
    for rec in ledger:
        if rec.get("task_id") == task_id and rec.get("commit") == sha:
            logger.info(f"이미 처리됨 — 스킵: [{cl}][{task_id}] {sha[:8]}")
            return {"verdict": rec.get("verdict"), "skipped": "already_processed"}

    # [HIGH] amend/rebase 우회 차단: 동일 task_id가 다른 SHA로 이미 TERMINAL 판정됨
    # TERMINAL = APPROVED 또는 REJECTED (AI_PENDING은 비-terminal, 재시도 허용)
    TERMINAL = {APPROVED, REJECTED}
    for rec in ledger:
        if (rec.get("task_id") == task_id
                and rec.get("verdict") in TERMINAL
                and rec.get("commit") != sha):
            prior_verdict = rec["verdict"]
            prior_sha = str(rec.get("commit", ""))[:8]
            logger.warning(
                f"TERMINAL 재시도 차단 [{cl}][{task_id}]: "
                f"이미 {prior_verdict}({prior_sha}) — GM 수동 재개 필요. commit {sha[:8]} 스킵."
            )
            if not dry_run:
                _send_telegram(telegram,
                    f"🚫 재시도 차단 [{cl}][{task_id}] — "
                    f"이미 {prior_verdict}({prior_sha})로 최종 판정됨. "
                    f"새 commit {sha[:8]}은 GM 수동 재개 필요.")
            return {"verdict": prior_verdict, "skipped": "terminal_decided"}

    # DUAL 신호 검증
    sdata = read_clevel_status(repo, clevel)
    s_task = status_task_id(sdata)
    s_status = status_value(sdata)
    dual_ok = (s_task == task_id and s_status == "DONE")

    if not dual_ok:
        logger.warning(
            f"MISMATCH — 단일 신호 [{clevel.upper()}][{task_id}] {sha[:8]}: "
            f"status={clevel}.json task_id='{s_task}' status='{s_status}'. 처리 안 함."
        )
        if not dry_run:
            _send_telegram(telegram,
                           f"⚠️ MISMATCH [{clevel.upper()}][{task_id}] — "
                           f"commit 태그만 있고 status/{clevel}.json status≠DONE. "
                           f"단일 신호 — 승인 보류.")
        # MISMATCH는 ledger에 기록하지 않음 (status가 곧 DONE 되면 재처리되어야 함)
        return {"verdict": MISMATCH, "skipped": "mismatch"}

    title = sdata.get("title") or task_id
    artifact_url = sdata.get("artifact_url")

    # LAYER 1
    l1 = layer1_verify(repo, sha, clevel, task_id, artifact_url, ledger)

    # LAYER 2 (L1 통과 시에만)
    if l1["passed"]:
        ctx = {
            "clevel": clevel.upper(), "task_id": task_id, "title": title,
            "subject": subject, "artifact_url": artifact_url,
            "show_stat": git_show_stat(repo, sha),
        }
        l2 = ai_layer_verify(ctx, no_ai=no_ai)
    else:
        l2 = {"fit": None, "reason": "L1_FAILED — AI 생략", "principle_check": ""}

    # 판정
    if not l1["passed"]:
        verdict = REJECTED
        detail = "; ".join(l1["reasons"])
    elif l2.get("fit") is True:
        verdict = APPROVED
        detail = l2.get("reason", "")
    elif l2.get("fit") is False:
        verdict = REJECTED
        detail = l2.get("reason", "")
    else:  # fit is None
        verdict = AI_PENDING
        detail = l2.get("reason", "AI_PENDING")

    # cl already defined above from clevel.upper()
    logger.info(f"판정 {verdict} — [{cl}][{task_id}] {sha[:8]}: {detail[:160]}")

    # [HIGH] 부수효과 순서: (1) ledger append + write (durable) → (2) ceo_log → (3) telegram
    # 순서 보장: crash after (1) → next pass sees already_processed, skips cleanly (no dupe).
    if not dry_run:
        ledger.append({
            "task_id": task_id, "clevel": cl, "commit": sha,
            "verdict": verdict, "processed_at": _now_iso(),
        })
        write_ledger(repo, ledger)  # atomic + fsync — durable before any side-effect

        append_ceo_log(repo, {
            "ts": _now_iso(), "clevel": cl, "task_id": task_id, "commit": sha,
            "l1": l1, "l2": l2, "verdict": verdict, "artifact_url": artifact_url,
        })

        if verdict == APPROVED:
            _send_telegram(telegram, f"✅ 검증 통과 [{cl}][{task_id}] — {title}")
        elif verdict == REJECTED:
            _send_telegram(telegram, f"❌ 반려 [{cl}][{task_id}] — {detail[:200]} (재작업 자동 트리거 없음)")
        else:  # AI_PENDING
            _send_telegram(telegram, f"⏳ AI 검증 보류 [{cl}][{task_id}] — 수동 확인 필요")
    else:
        print(f"[DRY-RUN] 판정={verdict} [{cl}][{task_id}] {sha[:8]} | "
              f"L1={l1['passed']} L2.fit={l2.get('fit')} | {detail[:120]}")

    return {"verdict": verdict, "l1": l1, "l2": l2, "skipped": None}


def _send_telegram(telegram, message: str) -> None:
    if telegram is None:
        return
    try:
        telegram.send(message)
    except Exception as exc:
        logger.warning(f"텔레그램 발송 실패: {exc}")


# ── run_once ─────────────────────────────────────────────────────────────────

def run_once(repo: Path, telegram=None, no_ai: bool = False, dry_run: bool = False) -> dict:
    """1회 검증 패스. {processed, approved, rejected, pending, mismatch, skipped} 카운트 반환.

    [CRITICAL] MISMATCH 커서 정지:
      MISMATCH 발생 시 커서를 해당 commit 직전에서 멈춤 → 다음 패스에서 재스캔.
      staleness counter로 N패스 이상 해소 안 되면 GM 텔레그램 에스컬레이션.

    [HIGH] 커서 per-commit 점진적 전진:
      process_commit 내부에서 ledger를 durable write하므로 커서만 여기서 commit 단위로 전진.
      MISMATCH에서 정지하면 직전 SHA까지만 전진.

    [LOW] 커서 유효성 검증:
      cursor SHA가 git history에 없으면(force-push 등) HEAD로 리셋 + GM 알림.
    """
    counts = {"processed": 0, "approved": 0, "rejected": 0, "pending": 0,
              "mismatch": 0, "skipped": 0}

    if not git_fetch(repo):
        logger.info("fetch 불가 — 이번 패스 종료")
        return counts

    cursor = read_cursor(repo)

    # FIRST run: cursor 없음 → 현재 HEAD로 설정하고 아무것도 처리하지 않음 (전체 이력 스캔 방지)
    if not cursor:
        head = git_head(repo)
        if head:
            if not dry_run:
                write_cursor(repo, head)
            logger.info(f"첫 실행 — cursor를 origin/master HEAD({head[:8]})로 설정, 처리 0건")
        else:
            logger.warning("origin/master HEAD 조회 실패")
        return counts

    # [LOW] 커서 유효성 검증 — force-push/GC로 SHA가 사라졌을 때
    if not git_cursor_valid(repo, cursor):
        head = git_head(repo)
        logger.warning(f"cursor {cursor[:8]} 가 git history에 없음(force-push 또는 GC 가능성). "
                       f"HEAD({head[:8] if head else 'unknown'})로 리셋.")
        if not dry_run:
            if head:
                write_cursor(repo, head)
            _send_telegram(telegram,
                           f"⚠️ CEO 워처 cursor 리셋: {cursor[:8]} 이(가) git history에서 사라짐 "
                           f"(force-push?). HEAD {head[:8] if head else '?'}로 재설정. "
                           f"해당 구간 commit은 재스캔 불가 — GM 확인 필요.")
        else:
            print(f"[DRY-RUN] cursor {cursor[:8]} 무효 — HEAD {head[:8] if head else '?'}로 리셋 예정")
        return counts

    commits = git_new_commits(repo, cursor)
    if not commits:
        logger.info("신규 commit 없음")
        return counts

    logger.info(f"신규 commit {len(commits)}건 검사")
    ledger = read_ledger(repo)
    stale = read_stale(repo)
    last_safe_sha = cursor  # cursor는 완전히 처리된 마지막 SHA까지만 전진

    for sha, subject, author in commits:
        res = process_commit(repo, sha, subject, author, ledger, telegram, no_ai, dry_run)
        v = res.get("verdict")
        skip = res.get("skipped")

        if skip == "non-DONE":
            counts["skipped"] += 1
            # 비-DONE commit은 안전하게 커서 전진
            last_safe_sha = sha
            if not dry_run:
                write_cursor(repo, sha)
            # 이 sha가 stale 카운터에 있었으면 해제
            stale.pop(sha, None)

        elif skip == "already_processed":
            counts["skipped"] += 1
            last_safe_sha = sha
            if not dry_run:
                write_cursor(repo, sha)
            stale.pop(sha, None)

        elif skip == "terminal_decided":
            # 재시도 차단: 커서 전진, telegram은 process_commit 내부에서 이미 발송
            counts["skipped"] += 1
            last_safe_sha = sha
            if not dry_run:
                write_cursor(repo, sha)
            stale.pop(sha, None)

        elif v == MISMATCH:
            counts["mismatch"] += 1
            # [CRITICAL] MISMATCH: 커서 정지 — 이 sha를 다음 패스에서 재스캔
            stale[sha] = stale.get(sha, 0) + 1
            passes = stale[sha]
            logger.warning(f"MISMATCH cursor 정지: {sha[:8]} (연속 {passes}패스 미해소)")
            if not dry_run:
                write_stale(repo, stale)
            # staleness 에스컬레이션: MISMATCH_STALE_LIMIT 패스 초과 → GM에 1회 알림
            if passes == MISMATCH_STALE_LIMIT:
                msg = (f"🚨 DONE 커밋 {sha[:8]} 미해소 {passes}패스 경과 "
                       f"— status 미반영 가능성. GM 확인 필요.")
                logger.error(msg)
                if not dry_run:
                    _send_telegram(telegram, msg)
                else:
                    print(f"[DRY-RUN] STALE ESCALATION: {msg}")
            # 커서 전진하지 않고 루프 중단 — 뒤 commit들도 이번 패스에서 처리 안 함
            break

        elif v in (APPROVED, REJECTED, AI_PENDING):
            # 정상 판정: ledger는 process_commit 내부에서 이미 durable write됨
            # 커서만 여기서 전진
            if v == APPROVED:
                counts["approved"] += 1; counts["processed"] += 1
            elif v == REJECTED:
                counts["rejected"] += 1; counts["processed"] += 1
            else:
                counts["pending"] += 1; counts["processed"] += 1
            last_safe_sha = sha
            if not dry_run:
                write_cursor(repo, sha)
            stale.pop(sha, None)

        else:
            # 예상치 못한 verdict — 안전하게 커서 전진하지 않고 다음 commit으로
            logger.warning(f"알 수 없는 verdict={v} sha={sha[:8]} — 커서 정지")
            break

    # stale 맵에서 현재 cursor보다 오래된(더 이상 관련 없는) SHA 정리는 하지 않음:
    # MISMATCH가 해소되면 already_processed 경로에서 stale.pop(sha) 처리됨.
    if not dry_run:
        write_stale(repo, stale)
        logger.info(f"cursor={last_safe_sha[:8]}, ledger={len(ledger)}건, stale={len(stale)}건")
    else:
        print(f"[DRY-RUN] cursor 전진 예정 → {last_safe_sha[:8]} (기록 안 함)")

    logger.info(f"패스 완료: {counts}")
    return counts


# ── watch 루프 ────────────────────────────────────────────────────────────────

def run_watch(repo: Path, telegram=None, no_ai: bool = False,
              dry_run: bool = False, interval: int = 60) -> None:
    import time
    logger.info(f"검증 워처 시작 — 폴링 간격 {interval}초 (repo={repo})")
    while True:
        try:
            run_once(repo, telegram, no_ai, dry_run)
        except Exception as exc:
            logger.error(f"패스 오류: {exc}")
        time.sleep(interval)


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="CEO push-triggered 검증 워처")
    parser.add_argument("--once", action="store_true", help="1회 검증 패스 (기본)")
    parser.add_argument("--watch", action="store_true", help="폴링 루프 모드")
    parser.add_argument("--interval", type=int, default=60, help="폴링 간격(초, 기본 60)")
    parser.add_argument("--no-ai", action="store_true", help="LAYER 2 AI 검증 생략")
    parser.add_argument("--dry-run", action="store_true",
                        help="텔레그램·ledger·cursor 기록 없이 의도만 출력")
    parser.add_argument("--repo", default=str(DEFAULT_REPO), help="repo 루트 경로")
    parser.add_argument("--selftest", action="store_true",
                        help="내장 self-test 실행 (네트워크·git·텔레그램 stub)")
    args = parser.parse_args()

    if args.selftest:
        # 별도 테스트 모듈 위임
        from test_ceo_verify_watcher import run_selftest  # noqa: E402
        return 0 if run_selftest() else 1

    repo = Path(args.repo)

    # 텔레그램: dry-run이면 None (발송 안 함)
    telegram = None
    if not args.dry_run:
        try:
            from telegram_notifier import TelegramNotifier
            telegram = TelegramNotifier()
        except Exception as exc:
            logger.warning(f"TelegramNotifier 초기화 실패 — 발송 생략: {exc}")

    if args.watch:
        run_watch(repo, telegram, args.no_ai, args.dry_run, args.interval)
        return 0

    # 기본: --once
    run_once(repo, telegram, args.no_ai, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
