# -*- coding: utf-8 -*-
"""
scripts/cto_goal_score.py — 시토 궁극 목표(모든 프로젝트 보안·백엔드가 문제없이 자동, 나아가
자율로) 진척을 3축(보안·안정·자율)으로 매일 자동 측정한다. 새 화면 없음 — 기존 T2
시스템 현황판(erp_status_publisher.py → status/erp_status.json → 자율현황.html)에 얹는다.

출력: status/cto_goal_score.json
  {measured_at, security, stability, autonomy, total, items:[{axis,name,value,target,pass,note}],
   last_notified_date}

축 점수 = 그 축 항목들의 value(0~100) 평균, value=null 항목은 분모 제외(전부 null이면 축=null).
total = null 아닌 축들의 평균(전부 null이면 0).
측정 실패(ssh·네트워크 등)는 예외로 죽지 않고 그 항목만 value=null+note 로 떨어진다(fail-safe).
"0 위장 금지" — 장치·표식 자체가 없어 못 재는 것과 실제로 0인 것을 구분한다.

사용:
  python scripts/cto_goal_score.py             # status/cto_goal_score.json 갱신(+ 하루 1회 GM 진행현황방 알림)
  python scripts/cto_goal_score.py --selfcheck # 가짜 입력으로 채점 함수만 assert(네트워크·ssh 안 씀)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_ROOT = _SCRIPTS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

KST = timezone(timedelta(hours=9))
ROOT = _ROOT
STATUS_DIR = ROOT / "status"
API_DIR = ROOT / "server" / "erp_api"
OUT = STATUS_DIR / "cto_goal_score.json"
EXPOSURES_PATH = STATUS_DIR / "cto_known_exposures.json"

ERP_BASE = "https://erp.wellperion.com"
PUBLIC_ALLOW = {
    "/api/jobs/public",
    "/api/reception/lookup/public",
    "/api/reception/lost/public",
    "/api/intake/health",
}

SSH_KEY = str(Path.home() / ".aws" / "wellperion-sito.pem")
SSH_HOST = "ec2-user@15.164.151.105"
SSH_BASE = ["ssh", "-i", SSH_KEY, "-o", "ConnectTimeout=8",
            "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes"]

SECRET_PATTERN = r"sk-ant-|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}"

AUTONOMY_MARKERS = ("pc_crash_guard", "telegram_health_check", "self_health_watchdog")
AUTONOMY_TARGET = 5


def _now_kst() -> datetime:
    return datetime.now(tz=KST)


# ── 채점 함수(순수 — --selfcheck 대상) ───────────────────────────────────────
def _ratio_score(passed: int, total: int) -> int:
    """비율 → 0~100 정수. total<=0 이면 잴 대상이 없다는 뜻이라 100(문제 없음)."""
    if total <= 0:
        return 100
    return round(passed / total * 100)


def axis_average(items: list) -> "int | None":
    """같은 축 items 의 value 평균(0~100 정수). value=None 인 항목은 분모 제외.
    전부 None 이면 None(측정 불가 — 0으로 위장하지 않는다)."""
    vals = [it["value"] for it in items if it.get("value") is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals))


def total_score(security, stability, autonomy) -> int:
    axes = [a for a in (security, stability, autonomy) if a is not None]
    if not axes:
        return 0
    return round(sum(axes) / len(axes))


# ── 보안(a) 비밀값 패턴 노출 ─────────────────────────────────────────────────
def sec_secrets_item() -> dict:
    name = "비밀값 패턴 노출(git grep)"
    try:
        r = subprocess.run(
            ["git", "grep", "-InE", SECRET_PATTERN, "HEAD", "--", ".", ":!tests/*"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        # git grep 은 매치 0건이면 returncode=1 — 에러가 아니다.
        lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
        n = len(lines)
        return {"axis": "security", "name": name, "value": 100 if n == 0 else 0,
                "target": 0, "pass": n == 0, "note": f"{n}건"}
    except Exception as e:
        return {"axis": "security", "name": name, "value": None, "target": 0,
                "pass": None, "note": f"측정 실패: {type(e).__name__}"}


# ── 보안(b) 서버 비로그인 200 경로 ───────────────────────────────────────────
_ROUTE_PREFIX_RE = re.compile(r'^router\s*=\s*APIRouter\(\s*(?:prefix\s*=\s*["\']([^"\']*)["\'])?',
                               re.MULTILINE)
_ROUTE_GET_RE = re.compile(r'^[ \t]*@(?:router|app)\.get\(\s*["\']([^"\']*)["\']', re.MULTILINE)


def _extract_get_paths() -> list:
    """server/erp_api/*.py 의 @router.get/@app.get 중 경로변수({..}) 없는 절대경로만."""
    paths = set()
    for f in sorted(API_DIR.glob("*.py")):
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        prefix = ""
        m = _ROUTE_PREFIX_RE.search(src)
        if m:
            prefix = m.group(1) or ""
        for gm in _ROUTE_GET_RE.finditer(src):
            p = gm.group(1)
            if "{" in p:
                continue
            full = p if p.startswith("/api/") else (prefix + p)
            if not full.startswith("/"):
                full = "/" + full
            full = full.rstrip("/") or "/"
            paths.add(full)
    return sorted(paths)


def sec_public_200_item() -> dict:
    name = "서버 비로그인 200 경로"
    try:
        candidates = _extract_get_paths()
    except Exception as e:
        return {"axis": "security", "name": name, "value": None, "target": 0,
                "pass": None, "note": f"경로 추출 실패: {type(e).__name__}"}
    checked = [p for p in candidates if p not in PUBLIC_ALLOW]
    if not checked:
        return {"axis": "security", "name": name, "value": 100, "target": 0,
                "pass": True, "note": "점검 대상 없음"}
    violations = []
    network_ok = False
    for path in checked:
        try:
            req = urllib.request.Request(ERP_BASE + path, method="GET")
            with urllib.request.urlopen(req, timeout=8) as resp:
                network_ok = True
                if resp.status == 200:
                    violations.append(path)
        except urllib.error.HTTPError:
            network_ok = True  # 401/403/404 등 = 비로그인 차단됨(정상)
        except Exception:
            continue  # 개별 경로 네트워크 실패는 건너뜀(다른 경로가 응답하면 network_ok=True)
    if not network_ok:
        return {"axis": "security", "name": name, "value": None, "target": 0,
                "pass": None, "note": "서버 응답 없음(네트워크 실패)"}
    n = len(violations)
    note = (f"{n}건: " + ", ".join(violations[:5])) if n else f"0건({len(checked)}개 경로 점검)"
    return {"axis": "security", "name": name, "value": 100 if n == 0 else 0,
            "target": 0, "pass": n == 0, "note": note}


# ── 보안(c) 알려진 열린 노출 ─────────────────────────────────────────────────
def _load_or_seed_exposures() -> list:
    if EXPOSURES_PATH.exists():
        try:
            data = json.loads(EXPOSURES_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []
    seed = [{"id": "12818", "what": "회원 GAS 무로그인 명단", "open": True}]
    try:
        STATUS_DIR.mkdir(parents=True, exist_ok=True)
        EXPOSURES_PATH.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return seed


def sec_known_exposures_item() -> dict:
    name = "알려진 열린 노출"
    try:
        items = _load_or_seed_exposures()
        n = sum(1 for x in items if isinstance(x, dict) and x.get("open"))
        return {"axis": "security", "name": name, "value": 100 if n == 0 else 0,
                "target": 0, "pass": n == 0, "note": f"{n}건 열림" if n else "0건"}
    except Exception as e:
        return {"axis": "security", "name": name, "value": None, "target": 0,
                "pass": None, "note": f"측정 실패: {type(e).__name__}"}


# ── schtasks 조회(erp_status_publisher 의 fail-safe 임시파일 방식 재사용) ────
def _schtasks_blocks():
    """(blocks, field) — blocks=작업별 텍스트 블록 리스트, field=라벨로 값 뽑는 함수.
    조회 실패 시 (None, None)."""
    try:
        from erp_status_publisher import _schtasks_dump, _schtasks_label, _L_HOST
    except Exception:
        return None, None
    out = _schtasks_dump()
    if not out:
        return None, None
    blocks, cur = [], []
    for line in out.split("\n"):
        if _schtasks_label(line) in _L_HOST:
            if cur:
                blocks.append("\n".join(cur))
            cur = [line]
        else:
            cur.append(line)
    if cur:
        blocks.append("\n".join(cur))

    def field(block, labels):
        for line in block.split("\n"):
            if _schtasks_label(line) in labels:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    return parts[1].strip()
        return ""
    return blocks, field


# ── 안정(a) 예약작업 정상 비율 ───────────────────────────────────────────────
def stab_task_health_item() -> dict:
    name = "예약작업 정상 비율(LastResult 0/267009)"
    try:
        from erp_status_publisher import _L_TASK, _L_LAST_RESULT
    except Exception as e:
        return {"axis": "stability", "name": name, "value": None, "target": 100,
                "pass": None, "note": f"모듈 로드 실패: {type(e).__name__}"}
    blocks, field = _schtasks_blocks()
    if blocks is None:
        return {"axis": "stability", "name": name, "value": None, "target": 100,
                "pass": None, "note": "schtasks 조회 실패"}
    total = healthy = 0
    for block in blocks:
        tname = field(block, _L_TASK)
        if not tname or "wellperion" not in tname.lower():
            continue
        raw = field(block, _L_LAST_RESULT)
        if not raw:
            continue
        try:
            code = int(raw)
        except ValueError:
            continue
        total += 1
        if code == 0 or code == 267009:
            healthy += 1
    if total == 0:
        return {"axis": "stability", "name": name, "value": None, "target": 100,
                "pass": None, "note": "Wellperion 예약작업 결과값 없음"}
    return {"axis": "stability", "name": name, "value": _ratio_score(healthy, total),
            "target": 100, "pass": healthy == total, "note": f"{healthy}/{total}"}


# ── 안정(b) 서버↔저장소 코드 일치율 ─────────────────────────────────────────
# ★개행 정규화(GM 지시) — 서버·저장소가 같은 코드라도 CRLF/LF 가 갈리면 md5가 달라
#   "불일치"로 오판된다(진단 실측: 불일치 18건 중 16건이 개행 차이뿐이었다). 원격은
#   sed 로 CR 을 지우고 md5 를 내고, 로컬(git blob)도 같은 규칙(\r\n→\n)으로 맞춘 뒤
#   비교한다 — 양쪽 다 정규화해야 공평한 비교다.
def _normalize_eol(raw: bytes) -> bytes:
    """CRLF→LF 로 맞춘다(파일 내용 비교 전 개행 차이를 제거)."""
    return raw.replace(b"\r\n", b"\n")


def _md5_norm(raw: bytes) -> str:
    return hashlib.md5(_normalize_eol(raw)).hexdigest()


def stab_server_md5_item() -> dict:
    name = "서버↔저장소 코드 일치율(md5·개행 정규화)"
    try:
        # 원격도 sed 's/\r$//' 로 CR 을 지운 뒤 md5 — 개행 차이만으로는 불일치가 안 남는다.
        remote_cmd = ("for f in /srv/erp/api/*.py; do printf '%s %s\\n' "
                      "\"$(sed 's/\\r$//' \"$f\" | md5sum | cut -d' ' -f1)\" \"$(basename \"$f\")\"; "
                      "done 2>/dev/null")
        r = subprocess.run(
            SSH_BASE + [SSH_HOST, remote_cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25,
        )
        remote = {}
        for line in (r.stdout or "").splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                remote[os.path.basename(parts[1])] = parts[0]
        if not remote:
            return {"axis": "stability", "name": name, "value": None, "target": 100,
                    "pass": None, "note": "ssh 실패 또는 원격 파일 없음"}
        total = same = 0
        for fname, md5 in remote.items():
            local_bytes = None
            for rel in (f"server/erp_api/{fname}", f"scripts/{fname}"):
                out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT,
                                      capture_output=True, timeout=10)
                if out.returncode == 0:
                    local_bytes = out.stdout
                    break
            if local_bytes is None:
                continue  # 저장소 대응 파일 없음 → 분모 제외
            total += 1
            if _md5_norm(local_bytes) == md5:
                same += 1
        if total == 0:
            return {"axis": "stability", "name": name, "value": None, "target": 100,
                    "pass": None, "note": "대응 파일 없음"}
        return {"axis": "stability", "name": name, "value": _ratio_score(same, total),
                "target": 100, "pass": same == total, "note": f"{same}/{total}"}
    except Exception as e:
        return {"axis": "stability", "name": name, "value": None, "target": 100,
                "pass": None, "note": f"측정 실패: {type(e).__name__}"}


# ── 안정(c) 24h erp-api 500 오류 ────────────────────────────────────────────
def stab_500_item() -> dict:
    name = "24h erp-api 500 오류"
    try:
        r = subprocess.run(
            SSH_BASE + [SSH_HOST,
                        "journalctl -u erp-api --since '24 hours ago' --no-pager 2>/dev/null "
                        "| grep -c ' 500 ' || true"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25,
        )
        raw = (r.stdout or "").strip().splitlines()
        if not raw:
            return {"axis": "stability", "name": name, "value": None, "target": 0,
                    "pass": None, "note": "ssh/journalctl 실패"}
        n = int(raw[0].strip() or "0")
        return {"axis": "stability", "name": name, "value": 100 if n == 0 else 0,
                "target": 0, "pass": n == 0, "note": f"{n}건"}
    except Exception as e:
        return {"axis": "stability", "name": name, "value": None, "target": 0,
                "pass": None, "note": f"측정 실패: {type(e).__name__}"}


# ── 안정(d) 헬스체크 failed_modules ──────────────────────────────────────────
def stab_health_endpoint_item() -> dict:
    name = "헬스체크 failed_modules"
    try:
        r = subprocess.run(
            SSH_BASE + [SSH_HOST, "curl -s -m 6 http://127.0.0.1:8001/api/health"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
        raw = (r.stdout or "").strip()
        if not raw:
            return {"axis": "stability", "name": name, "value": None, "target": 0,
                    "pass": None, "note": "ssh/curl 실패 또는 빈 응답"}
        try:
            data = json.loads(raw)
        except Exception:
            return {"axis": "stability", "name": name, "value": None, "target": 0,
                    "pass": None, "note": "응답 파싱 실패(헤더 필요 가능) — " + raw[:80]}
        fm = data.get("failed_modules")
        empty = not fm
        return {"axis": "stability", "name": name, "value": 100 if empty else 0,
                "target": 0, "pass": empty,
                "note": "없음" if empty else json.dumps(fm, ensure_ascii=False)[:100]}
    except Exception as e:
        return {"axis": "stability", "name": name, "value": None, "target": 0,
                "pass": None, "note": f"측정 실패: {type(e).__name__}"}


# ── 자율(a) 자가 복구 장치 수 / 목표 5 ───────────────────────────────────────
def auto_selfheal_item() -> dict:
    name = f"자가 복구 장치 수 / 목표 {AUTONOMY_TARGET}"
    try:
        from erp_status_publisher import _L_TASK
    except Exception as e:
        return {"axis": "autonomy", "name": name, "value": None, "target": 100,
                "pass": None, "note": f"모듈 로드 실패: {type(e).__name__}"}
    blocks, field = _schtasks_blocks()
    if blocks is None:
        return {"axis": "autonomy", "name": name, "value": None, "target": 100,
                "pass": None, "note": "schtasks 조회 실패"}
    _L_ACTION = ("실행할작업", "tasktorun")
    found = set()
    for block in blocks:
        action = field(block, _L_ACTION).lower()
        if any(m in action for m in AUTONOMY_MARKERS):
            tname = field(block, _L_TASK).lstrip("\\")
            if tname:
                found.add(tname)
    count = len(found)
    value = min(100, round(count / AUTONOMY_TARGET * 100))
    note = f"{count}/{AUTONOMY_TARGET}" + (" · " + ", ".join(sorted(found)) if found else "")
    return {"axis": "autonomy", "name": name, "value": value, "target": 100,
            "pass": count >= AUTONOMY_TARGET, "note": note}


# ── 자율(b) 자율 종결 표식 비율(closed_by=='auto' 또는 note '[자율]') ────────
def auto_marked_ratio_item() -> dict:
    name = "자율 종결 표식 비율(최근 7일 · cto)"
    try:
        archive = json.loads((STATUS_DIR / "_queue_archive.json").read_text(encoding="utf-8"))
        live = json.loads((STATUS_DIR / "_queue.json").read_text(encoding="utf-8"))
    except Exception as e:
        return {"axis": "autonomy", "name": name, "value": None, "target": 100,
                "pass": None, "note": f"큐 파일 못 읽음: {type(e).__name__}"}

    def _items(d):
        return d if isinstance(d, list) else (d.get("items") or [])
    all_items = _items(archive) + _items(live)

    def _marked(t):
        return t.get("closed_by") == "auto" or "[자율]" in (t.get("note") or "")

    ever_marked = any(isinstance(t, dict) and _marked(t) for t in all_items)
    if not ever_marked:
        # 표식 장치 자체가 아직 안 쓰였다 — 0%가 아니라 "못 잰다"(0 위장 금지).
        return {"axis": "autonomy", "name": name, "value": None, "target": 100,
                "pass": None, "note": "표식 없음"}

    cutoff = (_now_kst() - timedelta(days=7)).strftime("%Y-%m-%d")
    recent = [t for t in all_items if isinstance(t, dict) and t.get("clevel") == "cto"
              and t.get("status") == "DONE" and str(t.get("processed_at") or "")[:10] >= cutoff]
    if not recent:
        return {"axis": "autonomy", "name": name, "value": None, "target": 100,
                "pass": None, "note": "최근 7일 종결 배 없음"}
    marked = sum(1 for t in recent if _marked(t))
    return {"axis": "autonomy", "name": name, "value": _ratio_score(marked, len(recent)),
            "target": 100, "pass": marked == len(recent), "note": f"{marked}/{len(recent)}"}


def build_score() -> dict:
    security_items = [sec_secrets_item(), sec_public_200_item(), sec_known_exposures_item()]
    stability_items = [stab_task_health_item(), stab_server_md5_item(),
                        stab_500_item(), stab_health_endpoint_item()]
    autonomy_items = [auto_selfheal_item(), auto_marked_ratio_item()]

    security = axis_average(security_items)
    stability = axis_average(stability_items)
    autonomy = axis_average(autonomy_items)
    total = total_score(security, stability, autonomy)

    return {
        "_doc": "시토 목표 진척 3축 점수 — cto_goal_score.py 발행. erp_status_publisher 가 편승 발행.",
        "measured_at": _now_kst().strftime("%Y-%m-%d %H:%M:%S+09:00"),
        "security": security,
        "stability": stability,
        "autonomy": autonomy,
        "total": total,
        "items": security_items + stability_items + autonomy_items,
    }


def _load_prev() -> "dict | None":
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return None


def _selfcheck():
    assert _ratio_score(0, 0) == 100
    assert _ratio_score(5, 5) == 100
    assert _ratio_score(0, 4) == 0
    assert _ratio_score(2, 4) == 50
    assert axis_average([{"value": 100}, {"value": 0}]) == 50
    assert axis_average([{"value": None}, {"value": None}]) is None
    assert axis_average([{"value": None}, {"value": 80}]) == 80
    assert axis_average([]) is None
    assert total_score(100, 50, None) == 75
    assert total_score(None, None, None) == 0
    assert total_score(100, 100, 100) == 100
    # CRLF/LF 개행만 다른 두 판은 정규화 뒤 같은 md5 여야 한다(GM 지시 — 거짓 불일치 방지).
    lf = b"line1\nline2\n"
    crlf = b"line1\r\nline2\r\n"
    assert _normalize_eol(crlf) == lf
    assert _md5_norm(lf) == _md5_norm(crlf)
    assert _md5_norm(lf) != _md5_norm(b"line1\nline2changed\n")
    print("[cto_goal_score] --selfcheck OK")


def main():
    if "--selfcheck" in sys.argv:
        _selfcheck()
        return

    prev = _load_prev()
    payload = build_score()
    today = _now_kst().strftime("%Y-%m-%d")
    prev_total = (prev or {}).get("total")
    last_notified_date = (prev or {}).get("last_notified_date")
    should_notify = last_notified_date != today and (prev is None or prev_total != payload["total"])
    payload["last_notified_date"] = today if should_notify else last_notified_date

    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[cto_goal_score] wrote {OUT} — total={payload['total']} "
          f"security={payload['security']} stability={payload['stability']} autonomy={payload['autonomy']}")

    if should_notify:
        yesterday_str = str(prev_total) if prev_total is not None else "?"
        msg = (f"시토 목표 진척 {payload['total']}% (어제 {yesterday_str}%) · "
               f"보안 {payload['security']} · 안정 {payload['stability']} · 자율 {payload['autonomy']}")
        try:
            subprocess.run(
                [sys.executable, str(_SCRIPTS_DIR / "notify_gm_progress.py"), msg,
                 "--ship", "시토", "--state", "done"],
                cwd=ROOT, timeout=30,
            )
        except Exception as e:
            print(f"[cto_goal_score] 알림 실패: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
