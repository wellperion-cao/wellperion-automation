#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enforcement.py — 웰페리온 화이트리스트 코드강제 엔진 (AI 자율화 ③)

S2 공통탭의 advisory 화이트리스트를 '기계가 가로채는' 강제로 승격하는 중앙 엔진.
AI의 '생각'은 못 막으므로, 기계가 가로챌 수 있는 길목(pre-commit·deploy/env)에서만 강제한다.

【1-스위치 모드】 ssot/enforcement_mode.json 의 "mode":
  - off   : 완전 무동작(모든 체크가 위반 없음 반환·로그도 안 남김).
  - warn  : 감지·로그만(+선택 텔레그램 1줄). 항상 통과(exit 0). 기본값.
  - block : 실제 차단(위반 시 should_block=True → 호출부가 exit≠0). GM 명시 go 후에만.

【절대 안전 원칙(가드레일)】
  - 기본 모드 = warn. 절대 기본값으로 block 하지 말 것.
  - warn/off 는 항상 fail-open(통과). 이 레포는 watcher 가 5분마다 자동 커밋·푸시함 →
    warn 이 자동흐름을 막으면 대형사고. 그래서 warn 은 절대 차단 신호를 내지 않는다.
  - 엔진 내부 예외는 전부 삼켜 통과(fail-open). 가드 버그로 커밋 마비 금지.

【정당 변경 우회(GM 승인)】
  - 커밋 메시지에 bypass_token([GM-approved]) 이 있거나
  - bypass_flag_file(ssot/.enforcement_bypass) 가 존재하면
  위반이어도 통과. 우회 시 로그에 BYPASS 기록.

【차단 대상 4종 — 길목별】
  1) 공식값·약속 무단 변경 (pre-commit) : canon_values.json·약속.json staged 변경.
  2) 금지 경로·파일 변경     (pre-commit) : 블랙리스트 경로(결재 GAS·구버전 미끼 등).
  3) 보안 차단 라이브 발효   (deploy/env) : TOKEN_ENFORCE on 류 변경을 GM go 없이.
  4) 결제·지출 승인          (결재 흐름)  : 신규 구축 안 함 — 이미 결재현황(GM=유일
     최종결재)에서 게이트됨. 여기서는 재사용만, 신규 차단 로직 없음.

사용(헬퍼):
    from ssot.enforcement import (
        get_mode, is_bypassed, log_event, notify_warn,
        check_canon_promise_change, check_forbidden_path_change,
        check_security_live_activation, ENFORCE_MODE_OFF,
    )
"""
from __future__ import annotations

import io
import json
import re
import sys
import subprocess
from datetime import datetime
from pathlib import Path

# Windows 콘솔 UTF-8 강제. 이미 utf-8 이면 재래핑 금지(reload 시 닫힌 버퍼 오류 방지).
def _force_utf8(stream):
    try:
        if getattr(stream, "encoding", "").lower().startswith("utf-8"):
            return stream
        if hasattr(stream, "buffer"):
            return io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass
    return stream


sys.stdout = _force_utf8(sys.stdout)
sys.stderr = _force_utf8(sys.stderr)

ENFORCE_MODE_OFF = "off"
ENFORCE_MODE_WARN = "warn"
ENFORCE_MODE_BLOCK = "block"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "ssot" / "enforcement_mode.json"
_LOG_PATH = _REPO_ROOT / "logs" / "enforcement.log"

# ── 차단 대상 2) 금지 경로 블랙리스트 (보수적으로 시작) ─────────────────────
#    결재 GAS(GM=유일 최종결재 흐름 핵심) + 구버전 미끼(reference 메모리) 등.
#    fnmatch 글롭. 경로 구분자는 / 로 정규화 후 매칭.
FORBIDDEN_PATH_GLOBS = [
    # 결재 GAS — 결재현황 게이트 핵심. 무단 변경 감지.
    ".deploy-todo/*결재*",
    "*/coo/todo/apps_script_todo.js",
    # 구버전 미끼 파일 (reference_facility_check_live_gas: apps_script_v3.js=구버전 미끼)
    "*apps_script_v3.js",
]

# ── 차단 대상 1) 공식값·약속 정본 파일 ─────────────────────────────────────
CANON_PROMISE_GLOBS = [
    "ssot/canon_values.json",
    "ssot/약속.json",
]

# ── 차단 대상 3) 보안 라이브 발효 감지 패턴 ────────────────────────────────
#    staged diff(추가 라인)에서 TOKEN_ENFORCE 를 '1'/on 으로 켜는 변경 감지.
#    실제 라이브 발효는 ScriptProperties+재배포라 코드만으론 발효 안 되지만,
#    그 의도를 담은 코드 변경(기본값 변경·강제 ON 등)을 GM go 없이 들이는 걸 감지.
# 주의: 비교(!== / === / ==)는 발효가 아니라 '검사'다 → 오탐 금지.
#   Survey.js 의 안전 라인 `if (_accessProp_('TOKEN_ENFORCE') !== '1') return true;`
#   같은 비교문은 매칭하지 않도록 부정 룩비하인드로 = 앞의 ! = < > 를 배제하고,
#   = 뒤가 = 인 비교(==, ===)도 배제한다. 순수 대입(= '1')만 발효로 본다.
_SECURITY_ACTIVATION_PATTERNS = [
    re.compile(r"TOKEN_ENFORCE\s*(?<![!=<>])=(?![=])\s*['\"]?1['\"]?"),
    re.compile(r"setProperty\(\s*['\"]TOKEN_ENFORCE['\"]\s*,\s*['\"]?1['\"]?", re.I),
]


# ════════════════════════════════════════════════════════════════════════════
#  설정·모드
# ════════════════════════════════════════════════════════════════════════════
def _load_config() -> dict:
    """enforcement_mode.json 로드. 실패 시 안전 기본값(warn)."""
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # 설정 파일 없음/깨짐 = 가장 안전한 warn 으로 폴백(절대 block 폴백 금지).
        return {"mode": ENFORCE_MODE_WARN}


def get_mode() -> str:
    """현재 모드 반환. 알 수 없는 값은 warn 으로 강제(절대 block 폴백 금지)."""
    mode = str(_load_config().get("mode", ENFORCE_MODE_WARN)).strip().lower()
    if mode not in (ENFORCE_MODE_OFF, ENFORCE_MODE_WARN, ENFORCE_MODE_BLOCK):
        return ENFORCE_MODE_WARN
    return mode


def should_block(mode: str | None = None) -> bool:
    """차단 신호를 내야 하는 모드인가? block 일 때만 True."""
    if mode is None:
        mode = get_mode()
    return mode == ENFORCE_MODE_BLOCK


# ════════════════════════════════════════════════════════════════════════════
#  로깅 · 텔레그램
# ════════════════════════════════════════════════════════════════════════════
def log_event(kind: str, message: str) -> None:
    """logs/enforcement.log 에 1줄 append. 실패해도 조용히 통과(fail-open)."""
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mode = get_mode()
        line = f"[{ts}] mode={mode} {kind}: {message}\n"
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def notify_warn(message: str) -> None:
    """
    warn 모드 관찰용 텔레그램 1줄(선택). 설정 telegram_warn_notify=true 일 때만.
    실패·미설정 = 조용히 통과(fail-open). 동기 호출이 봇 토큰 없으면 즉시 반환.
    """
    try:
        cfg = _load_config()
        if not cfg.get("telegram_warn_notify", False):
            return
        sender = _REPO_ROOT / "scripts" / "tg_outbound_log.py"
        if not sender.exists():
            return
        # 기존 송부 스크립트를 best-effort 로 호출. 인터페이스 불명확 시 조용히 패스.
        subprocess.run(
            [sys.executable, str(sender), "--text", f"[enforcement][warn] {message}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════════════════
#  GM 승인 우회
# ════════════════════════════════════════════════════════════════════════════
def _commit_message() -> str:
    """현재 커밋 준비 중 메시지(.git/COMMIT_EDITMSG). 없으면 빈 문자열."""
    try:
        msg_file = _REPO_ROOT / ".git" / "COMMIT_EDITMSG"
        if msg_file.exists():
            return msg_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    return ""


def is_bypassed(commit_message: str | None = None) -> bool:
    """
    정당 변경 우회 여부. 커밋 메시지에 bypass_token 이 있거나
    bypass_flag_file 이 존재하면 True. 우회 시 호출부가 log_event 로 기록 권장.
    """
    try:
        cfg = _load_config()
        token = cfg.get("bypass_token", "[GM-approved]")
        flag_rel = cfg.get("bypass_flag_file", "ssot/.enforcement_bypass")

        if commit_message is None:
            commit_message = _commit_message()
        if token and token in (commit_message or ""):
            return True

        if flag_rel:
            flag_path = _REPO_ROOT / flag_rel
            if flag_path.exists():
                return True
    except Exception:
        pass
    return False


# ════════════════════════════════════════════════════════════════════════════
#  staged 파일·diff 헬퍼
# ════════════════════════════════════════════════════════════════════════════
def staged_files() -> list[str]:
    """staged 파일 경로 목록(/ 정규화). 실패 시 빈 리스트."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(_REPO_ROOT),
        )
        if proc.returncode != 0:
            return []
        parts = proc.stdout.split(b"\x00")
        out = []
        for p in parts:
            if p:
                try:
                    out.append(p.decode("utf-8", "replace").replace("\\", "/"))
                except Exception:
                    pass
        return out
    except Exception:
        return []


def staged_added_lines(path: str) -> list[str]:
    """특정 파일의 staged diff 에서 추가(+) 라인 목록. 실패 시 빈 리스트."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--unified=0", "--", path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(_REPO_ROOT),
        )
        if proc.returncode != 0:
            return []
        text = proc.stdout.decode("utf-8", "replace")
        added = []
        for line in text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added.append(line[1:])
        return added
    except Exception:
        return []


def _match_any_glob(path: str, globs: list[str]) -> bool:
    import fnmatch
    p = path.replace("\\", "/")
    name = Path(p).name
    for g in globs:
        gn = g.replace("\\", "/")
        if fnmatch.fnmatch(p, gn):
            return True
        if "/" not in gn and fnmatch.fnmatch(name, gn):
            return True
    return False


# ════════════════════════════════════════════════════════════════════════════
#  차단 대상 판정 4종 (감지만 — 차단 결정은 호출부가 get_mode 로)
#  각 함수 반환: 위반 파일/사유 리스트(빈=위반없음). 예외 시 빈 리스트(fail-open).
# ════════════════════════════════════════════════════════════════════════════
def check_canon_promise_change(files: list[str] | None = None) -> list[str]:
    """1) 공식값·약속 정본(canon_values.json·약속.json) staged 변경 감지."""
    try:
        if files is None:
            files = staged_files()
        return [f for f in files if _match_any_glob(f, CANON_PROMISE_GLOBS)]
    except Exception:
        return []


def check_forbidden_path_change(files: list[str] | None = None) -> list[str]:
    """2) 금지 경로·파일(블랙리스트) staged 변경 감지."""
    try:
        if files is None:
            files = staged_files()
        return [f for f in files if _match_any_glob(f, FORBIDDEN_PATH_GLOBS)]
    except Exception:
        return []


def check_security_live_activation(files: list[str] | None = None) -> list[str]:
    """
    3) 보안 차단 라이브 발효(TOKEN_ENFORCE on 류) staged 변경 감지.
    반환: '파일: 발효 패턴' 형태 사유 문자열 리스트.
    """
    try:
        if files is None:
            files = staged_files()
        reasons = []
        for f in files:
            fl = f.lower()
            # GAS/JS/env/설정류만 검사(불필요 스캔 방지)
            if not (fl.endswith(".js") or fl.endswith(".gs")
                    or fl.endswith(".json") or fl.endswith(".env")
                    or "env" in fl):
                continue
            for added in staged_added_lines(f):
                for pat in _SECURITY_ACTIVATION_PATTERNS:
                    if pat.search(added):
                        reasons.append(f"{f}: {added.strip()[:80]}")
                        break
        return reasons
    except Exception:
        return []


# ════════════════════════════════════════════════════════════════════════════
#  결제·지출 (차단 대상 4) — 신규 구축 없음(주석 명시)
# ════════════════════════════════════════════════════════════════════════════
# 결제·지출 승인은 enforcement.py 에 신규 차단 로직을 두지 않는다.
# 이미 결재현황(.deploy-todo/업무&결재 현황.js + 결재 GAS)에서 GM=유일 최종결재로
# 게이트되어 있으므로 그 흐름을 재사용한다. 여기서는 결재 GAS 자체의 '무단 변경'만
# check_forbidden_path_change() 블랙리스트로 감지한다(결재 게이트 코드 보호).


if __name__ == "__main__":
    # 진단용 자가점검 출력.
    m = get_mode()
    files = staged_files()
    print(f"[enforcement] mode={m}  bypass={is_bypassed()}  staged={len(files)}개")
    print(f"  1) canon/약속 변경 : {check_canon_promise_change(files)}")
    print(f"  2) 금지 경로 변경  : {check_forbidden_path_change(files)}")
    print(f"  3) 보안 라이브발효 : {check_security_live_activation(files)}")
    print(f"  4) 결제·지출       : 결재현황 게이트 재사용(신규 로직 없음)")
