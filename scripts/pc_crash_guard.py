# -*- coding: utf-8 -*-
"""PC 강제 재부팅 재발 방지 — 은행 보안 드라이버 자동 차단·페이지 풀 경보·재부팅 뒤 NUL 파일 복구.

배경(GM 지시 2026-09-19 「근본적으로 해결」): GM PC 가 두 번 블루스크린 났다 —
09-09 0x133(안랩 Safe Transaction MeDCoreD.sys/MeDVpDrv.sys), 09-19 0x3B(TKFsAv64.sys ·
INCA nProtect/Tachyon). 둘 다 은행 사이트가 몰래 재설치하는 한국 금융보안 커널 드라이버다.
크래시 부작용 — 쓰던 파일이 전부 NUL 로 남는다(status/_queue.json 두 벌·sessions/*.json·
worklog.jsonl 꼬리·origin/master ref). 09-18 엔 페이지 풀이 8.6GB 로 새 python 이 전부 멈췄다.

실행: 예약작업(시간마다+로그온 시, 관리자 권한, run_py_hidden.vbs 경유)이 이 스크립트를 돈다.
    python scripts/pc_crash_guard.py            # 기본 = 보고만(발견해도 안 고침)
    python scripts/pc_crash_guard.py --apply    # 실제로 끄고 복구까지
    python scripts/pc_crash_guard.py --dry-run  # 뭘 할지만 stdout (--apply 무시)
    python scripts/pc_crash_guard.py --selfcheck

허용 스위치: 환경변수 PC_GUARD_APPLY=1 도 --apply 와 동일하게 켠다.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys
from contextlib import nullcontext

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPT_DIR)
_STATE_PATH = os.path.join(_ROOT_DIR, "status", "pc_crash_guard.json")
_ENV_PATH = os.path.join(_ROOT_DIR, "telegram_bot", ".env")
_GUIDE_QUEUE_REL = "3. 웰페리온 가이드/status/_queue.json"

sys.path.insert(0, _SCRIPT_DIR)
from queue_lock import queue_lock, _json_lock_name  # noqa: E402

# ── 오펜더 상수(한 곳) ────────────────────────────────────────────────────────
OFFENDER_NAME_RE = re.compile(r"^(TK|Tk)")
OFFENDER_EXPLICIT_NAMES = {"MeDCoreD", "MeDVpDrv"}  # 안랩 Safe Transaction (09-09 0x133)
NDIS_COMPONENT_ID = "INCA_TKFWFV"                    # INCA nProtect NDIS 필터 (09-19 0x3B)
NDIS_SERVICE_NAME = "TKFWFV"
PAGED_POOL_ALERT_BYTES = 3 * 1024 ** 3               # 3GB (정상 <1GB, 09-18 실측 8.6GB)


# ── 오펜더 판정 (레지스트리와 무관 · 순수 함수 · 자체점검 대상) ────────────────
def is_offender_service(name: str, image_path: str = "") -> bool:
    """서비스명·ImagePath 만으로 차단 대상 여부를 정한다(레지스트리 접근 없음)."""
    if name in OFFENDER_EXPLICIT_NAMES:
        return True
    if OFFENDER_NAME_RE.match(name or "") and "TK" in (image_path or "").upper():
        return True
    return False


def scan_offender_services(services: list[dict]) -> list[dict]:
    """services: [{'name','start','image_path'}, ...] → Start!=4 인 오펜더만."""
    return [s for s in services
            if is_offender_service(s.get("name", ""), s.get("image_path", ""))
            and s.get("start") != 4]


def build_action_plan(ndis_present: bool, offenders: list[dict]) -> list[dict]:
    """NDIS 필터가 바인딩된 채 서비스부터 죽이면 네트워크가 끊긴다 — NDIS 제거가 항상 먼저."""
    plan: list[dict] = []
    if ndis_present:
        plan.append({"type": "netcfg_remove", "component_id": NDIS_COMPONENT_ID})
    for s in offenders:
        plan.append({"type": "set_start4", "service": s["name"]})
    return plan


# ── 레지스트리 읽기/쓰기 (Windows 전용 · winreg) ─────────────────────────────
def _enumerate_services() -> list[dict]:
    import winreg
    out = []
    key_path = r"SYSTEM\CurrentControlSet\Services"
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as root:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(root, name) as sk:
                    start = None
                    image_path = ""
                    try:
                        start = winreg.QueryValueEx(sk, "Start")[0]
                    except OSError:
                        pass
                    try:
                        image_path = winreg.QueryValueEx(sk, "ImagePath")[0]
                    except OSError:
                        pass
                    out.append({"name": name, "start": start, "image_path": image_path})
            except OSError:
                continue
    return out


def _ndis_filter_present() -> bool:
    """Network 클래스(GUID {4d36e974-...}) 하위에 Ndi\\Service=TKFWFV 가 있으면 설치됨."""
    import winreg
    cls = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e974-e325-11ce-bfc1-08002be10318}"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cls) as root:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(root, sub + r"\Ndi") as ndi:
                        svc = winreg.QueryValueEx(ndi, "Service")[0]
                        if str(svc).strip().lower() == NDIS_SERVICE_NAME.lower():
                            return True
                except OSError:
                    continue
    except OSError:
        pass
    return False


def _set_service_disabled(name: str) -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             rf"SYSTEM\CurrentControlSet\Services\{name}",
                             0, winreg.KEY_SET_VALUE) as sk:
            winreg.SetValueEx(sk, "Start", 0, winreg.REG_DWORD, 4)
        return True
    except OSError as e:
        print(f"[WARN] {name} Start=4 설정 실패: {e}", flush=True)
        return False


def _netcfg_remove(component_id: str) -> bool:
    try:
        r = subprocess.run(["netcfg", "-u", component_id], capture_output=True,
                            text=True, timeout=60)
        if r.returncode != 0:
            print(f"[WARN] netcfg -u {component_id} 실패(rc={r.returncode}): {r.stdout}{r.stderr}",
                  flush=True)
            return False
        return True
    except Exception as e:
        print(f"[WARN] netcfg -u {component_id} 예외: {e}", flush=True)
        return False


# ── PowerShell 헬퍼 (paged pool·이벤트로그) ──────────────────────────────────
# Windows PowerShell 5.1 은 파이프 stdout 을 시스템 기본 코드페이지(한글 Windows=cp949)로
# 낸다 — utf-8 로 그냥 디코드하면 한글이 깨진다(실측). 콘솔 출력 인코딩을 UTF-8 로 강제한다.
_PS_PREAMBLE = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "


def _ps(cmd: str, timeout: int = 30) -> str:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_PREAMBLE + cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )
    return r.stdout or ""


def get_paged_pool_bytes() -> float:
    out = _ps(r"(Get-Counter '\Memory\Pool Paged Bytes').CounterSamples[0].CookedValue")
    return float(out.strip())


def get_boot_time() -> "datetime.datetime | None":
    out = _ps("(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('o')").strip()
    if not out:
        return None
    try:
        return datetime.datetime.fromisoformat(out)
    except ValueError:
        return None


def get_bugcheck_events(since: datetime.datetime) -> list[str]:
    """System 로그의 Kernel-Power 41 / WER 1001(부팅오류) 을 since 이후로 조회."""
    since_iso = since.strftime("%m/%d/%Y %H:%M:%S")
    cmd = (
        f"Get-WinEvent -FilterHashtable @{{LogName='System';Id=41,1001;StartTime='{since_iso}'}} "
        "-ErrorAction SilentlyContinue | Select-Object @{n='TimeCreated';e={$_.TimeCreated.ToString('o')}},Id,Message "
        "| ConvertTo-Json -Depth 3 -Compress"
    )
    out = _ps(cmd, timeout=30).strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    lines = []
    for ev in data:
        ts = str(ev.get("TimeCreated", "?"))[:16].replace("T", " ")
        eid = ev.get("Id")
        if eid == 1001:
            m = re.search(r"0x[0-9A-Fa-f]{8}", str(ev.get("Message", "")))
            code = m.group(0) if m else "?"
            lines.append(f"부팅오류 {ts} · bugcheck {code}")
        else:
            lines.append(f"비정상 재부팅 감지 {ts}")
    return lines


# ── NUL 파일 감지·복구 (순수 로직 부분은 자체점검 대상) ──────────────────────
def is_all_nul(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return False
    return len(data) > 0 and data.count(b"\x00") == len(data)


def strip_trailing_nul(path: str) -> bool:
    """끝의 NUL 바이트만 잘라낸다(추가 로그). 바뀐 게 없으면 False."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return False
    stripped = data.rstrip(b"\x00")
    if stripped == data:
        return False
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "wb") as f:
        f.write(stripped)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return True


def _git_show_head(rel_path: str, root: str) -> "str | None":
    r = subprocess.run(["git", "show", f"HEAD:{rel_path}"], cwd=root, capture_output=True,
                        text=True, encoding="utf-8", errors="replace", timeout=30)
    if r.returncode != 0:
        return None
    return r.stdout


def restore_from_head(rel_path: str, root: str, git_show=None) -> bool:
    """tracked 파일을 HEAD 판으로 되살린다 — tmp+fsync+os.replace(전원 크래시에도 반쪽 안 남음)."""
    git_show = git_show or _git_show_head
    content = git_show(rel_path, root)
    if content is None:
        return False
    full = os.path.join(root, rel_path.replace("/", os.sep))
    tmp = f"{full}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, full)
    return True


def _is_tracked(rel_path: str, root: str) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", rel_path], cwd=root,
                        capture_output=True, text=True, timeout=30)
    return r.returncode == 0


def _candidate_paths(root: str) -> set[str]:
    cands = set(glob.glob(os.path.join(root, "status", "*.json")))
    cands.update(glob.glob(os.path.join(root, "status", "sessions", "*.json")))
    guide_q = os.path.join(root, *_GUIDE_QUEUE_REL.split("/"))
    if os.path.exists(guide_q):
        cands.add(guide_q)
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=60).stdout
        for line in out.splitlines():
            path = line[3:].strip().strip('"')
            full = os.path.join(root, path)
            if os.path.exists(full):
                cands.add(full)
    except Exception:
        pass
    return cands


def scan_and_restore(root: str, apply: bool) -> list[str]:
    """전부 NUL 인 파일을 찾아 tracked → HEAD 복구 / untracked → 삭제. worklog 는 꼬리만 자름."""
    findings: list[str] = []
    root_queue = os.path.join(root, "status", "_queue.json")
    guide_queue = os.path.join(root, *_GUIDE_QUEUE_REL.split("/"))
    for full in sorted(_candidate_paths(root)):
        if not is_all_nul(full):
            continue
        rel = os.path.relpath(full, root).replace("\\", "/")
        if _is_tracked(rel, root):
            if full == root_queue:
                lockctx = queue_lock(holder="pc_crash_guard")
            elif full == guide_queue:
                lockctx = queue_lock(holder="pc_crash_guard", lock_name=_json_lock_name(rel))
            else:
                lockctx = nullcontext()
            with lockctx:
                if apply:
                    ok = restore_from_head(rel, root)
                    findings.append(f"{'복구됨' if ok else '복구실패'}: {rel} (전부 NUL)")
                else:
                    findings.append(f"복구필요: {rel} (전부 NUL, tracked)")
        else:
            findings.append(f"{'삭제됨' if apply else '삭제필요'}: {rel} (전부 NUL, untracked)")
            if apply:
                try:
                    os.remove(full)
                except OSError:
                    pass
    worklog = os.path.join(root, "status", "worklog.jsonl")
    if apply and os.path.exists(worklog) and strip_trailing_nul(worklog):
        findings.append("worklog.jsonl 끝 NUL 제거")
    return findings


# ── 상태 파일 ─────────────────────────────────────────────────────────────────
def _load_state() -> dict:
    try:
        with open(_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    tmp = f"{_STATE_PATH}.tmp.{os.getpid()}"
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, _STATE_PATH)


# ── 텔레그램 경보 (자동화현황방 · 기존 헬퍼 재사용) ──────────────────────────
def _load_env(path: str) -> dict:
    env: dict = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


def _send_alert(findings: list[str], dry_run: bool) -> None:
    msg = "🛡 PC 보호 — 자동 점검\n" + "\n".join(f"▪ {f}" for f in findings[:7])
    if dry_run:
        print(f"[DRY-RUN] 경보:\n{msg}", flush=True)
        return
    try:
        from alert_router import TECH_CHECK, route
        from tg_outbound_log import send as _tg_send
        token = _load_env(_ENV_PATH).get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            print("[WARN] 봇 토큰 없음 — 경보 발송 불가", flush=True)
            return
        _tg_send(token, route(TECH_CHECK), msg, source="pc_crash_guard", timeout=15)
    except Exception as e:
        print(f"[WARN] 경보 발송 예외: {e}", flush=True)


# ── 자체점검 (레지스트리·실제 파일 접근 없음) ────────────────────────────────
def run_selfcheck() -> None:
    import tempfile

    # 1) 오펜더 판정
    assert is_offender_service("MeDVpDrv", r"C:\Program Files\AhnLab\MeDVpDrv.sys") is True
    assert is_offender_service("TKFsAv64", r"C:\Windows\System32\drivers\TKFsAv64.sys") is True
    assert is_offender_service("Tkfwfv", r"C:\Windows\System32\drivers\Tkfwfv.sys") is True
    assert is_offender_service("TCPIP", r"C:\Windows\System32\drivers\tcpip.sys") is False
    assert is_offender_service("MeDCoreD", "") is True  # 명시 이름은 ImagePath 없어도 오펜더

    started = [{"name": "TKFsAv64", "start": 3, "image_path": r"C:\...\TK\a.sys"},
               {"name": "tcpip", "start": 1, "image_path": r"C:\...\tcpip.sys"},
               {"name": "MeDVpDrv", "start": 4, "image_path": ""}]  # 이미 Start=4 → 대상 아님
    offenders = scan_offender_services(started)
    assert [o["name"] for o in offenders] == ["TKFsAv64"], offenders

    # 2) NDIS 제거가 항상 먼저
    plan = build_action_plan(True, offenders)
    assert plan[0] == {"type": "netcfg_remove", "component_id": NDIS_COMPONENT_ID}
    assert plan[1] == {"type": "set_start4", "service": "TKFsAv64"}
    plan2 = build_action_plan(False, offenders)
    assert plan2 == [{"type": "set_start4", "service": "TKFsAv64"}]
    plan3 = build_action_plan(True, [])
    assert plan3 == [{"type": "netcfg_remove", "component_id": NDIS_COMPONENT_ID}]

    # 3) NUL 감지·복구(git show 를 가짜로 대체)
    with tempfile.TemporaryDirectory() as td:
        good = os.path.join(td, "good.json")
        with open(good, "w", encoding="utf-8") as f:
            f.write('{"a":1}')
        assert is_all_nul(good) is False

        empty = os.path.join(td, "empty.json")
        open(empty, "wb").close()
        assert is_all_nul(empty) is False  # 빈 파일 = NUL 아님

        nulled = os.path.join(td, "nulled.json")
        with open(nulled, "wb") as f:
            f.write(b"\x00" * 40)
        assert is_all_nul(nulled) is True

        restored = restore_from_head("nulled.json", td,
                                      git_show=lambda rel, root: '{"restored":true}')
        assert restored is True
        with open(nulled, encoding="utf-8") as f:
            assert f.read() == '{"restored":true}'
        assert is_all_nul(nulled) is False

        missing_head = restore_from_head("no_such.json", td, git_show=lambda rel, root: None)
        assert missing_head is False

        # 4) 꼬리 NUL 제거(append 로그)
        worklog = os.path.join(td, "worklog.jsonl")
        with open(worklog, "wb") as f:
            f.write(b'{"a":1}\n' + b"\x00" * 12)
        assert strip_trailing_nul(worklog) is True
        with open(worklog, "rb") as f:
            assert f.read() == b'{"a":1}\n'
        assert strip_trailing_nul(worklog) is False  # 이미 깨끗하면 재실행은 무변화


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="PC 강제 재부팅 재발 방지 감시기")
    ap.add_argument("--apply", action="store_true", help="실제로 끄고 복구까지 한다")
    ap.add_argument("--dry-run", action="store_true", help="뭘 할지만 stdout(발송·변경 없음)")
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()

    if args.selfcheck:
        run_selfcheck()
        print("SELFCHECK OK", flush=True)
        return

    dry_run = args.dry_run
    apply = (args.apply or os.environ.get("PC_GUARD_APPLY") == "1") and not dry_run

    findings: list[str] = []

    # 1. 드라이버 가드
    try:
        services = _enumerate_services()
        offenders = scan_offender_services(services)
        ndis_present = _ndis_filter_present()
        if offenders or ndis_present:
            plan = build_action_plan(ndis_present, offenders)
            for action in plan:
                if action["type"] == "netcfg_remove":
                    ok = _netcfg_remove(action["component_id"]) if apply else None
                    findings.append(
                        f"{'NDIS 필터 제거됨' if ok else 'NDIS 필터 제거필요' if not apply else 'NDIS 필터 제거실패'}"
                        f": {action['component_id']}"
                    )
                else:
                    ok = _set_service_disabled(action["service"]) if apply else None
                    findings.append(
                        f"{'서비스 차단됨' if ok else '서비스 차단필요' if not apply else '서비스 차단실패'}"
                        f": {action['service']}"
                    )
    except Exception as e:
        print(f"[WARN] 드라이버 가드 예외: {e}", flush=True)

    # 2. 페이지 풀
    try:
        pp = get_paged_pool_bytes()
        if pp > PAGED_POOL_ALERT_BYTES:
            boot = get_boot_time()
            uptime = f"{(datetime.datetime.now() - boot)}" if boot else "?"
            findings.append(f"페이지 풀 {pp / 1024**3:.1f}GB (가동 {uptime}) — 재시작은 안 함, 확인 필요")
    except Exception as e:
        print(f"[WARN] 페이지 풀 조회 실패: {e}", flush=True)

    # 3. 크래시 뒤 NUL 파일
    try:
        state = _load_state()
        last_run_str = state.get("last_run")
        since = datetime.datetime.fromisoformat(last_run_str) if last_run_str else \
            datetime.datetime.now() - datetime.timedelta(hours=25)
        bug_events = get_bugcheck_events(since)
        if bug_events:
            findings.extend(bug_events[:2])
            findings.extend(scan_and_restore(_ROOT_DIR, apply))
    except Exception as e:
        print(f"[WARN] 크래시 뒷정리 예외: {e}", flush=True)

    if not dry_run:
        _save_state({"last_run": datetime.datetime.now().isoformat(), "last_findings": findings})

    print(f"findings={len(findings)}", flush=True)
    for f in findings:
        print(f" - {f}", flush=True)
    if findings:
        _send_alert(findings, dry_run)


if __name__ == "__main__":
    main()
