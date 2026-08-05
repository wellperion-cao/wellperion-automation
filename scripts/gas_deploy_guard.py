# -*- coding: utf-8 -*-
"""GAS 배포 직전 버전 가드 — 200 하드리밋 조용한 소진 방지.

배경:
    GAS 배포(`clasp deploy`)마다 버전이 1개씩 영구 소비된다(삭제 불가).
    반복 배포가 조용히 버전을 쌓다가 200 하드리밋에 부딪히는 사고가
    funnel 프로젝트에서 실제 발생했다(#9001 — 이사로 대응). raw
    `clasp deploy` 대신 이 래퍼를 배포 관문으로 삼아 재발을 막는다
    (docs/GAS_배포_규율.md 참조).

동작:
    1) 대상 프로젝트의 현재 버전수를 조회한다(gas_version_monitor 재사용).
    2) 임계에 따라 판정:
       - count < 180              : 🟢 조용히 통과
       - 180 <= count < 195       : ⚠️ 눈에 띄는 경고 출력 후 진행(차단 안 함)
       - count >= 195             : 🔴 강경 경고 + 배포 중단(--force로만 강행)
       - 버전 조회 실패(None)      : WARN만 출력하고 통과 — 오탐으로 배포 자체를
                                     막지 않는다(원칙: 조회 실패는 배포 차단 사유가 아님)
    2-1) ★원격 무단변경 가드(2026-08-05 시토 — reception 08:50 배포 사고 재발방지).
       `clasp push --force`는 원격 GAS 코드를 로컬로 **경고 없이 통째 덮는다.** 사람이
       편집기(script.google.com)에서 직접 고친 내용이 있어도 사라진다. 막는 법:
       - 이 스크립트가 push 성공 직후마다 원격 콘텐츠(Apps Script API projects.getContent)의
         해시를 status/gas_push_baseline.json 에 프로젝트별로 저장해 둔다("우리가 마지막으로
         push 한 내용의 원격 지문").
       - 다음 배포 시도 때 push 하기 **전에** 원격 콘텐츠를 다시 조회해 해시를 비교한다.
         - 베이스라인과 같음        → 🟢 원격이 그대로다. 통과.
         - 베이스라인과 다름        → 🔴 우리가 모르는 새 원격 변경(=편집기 직접 수정 가능성).
                                      BLOCK + 파일별 unified diff 출력. --force 로만 강행.
         - 베이스라인 없음(최초)    → ⚠️ 대조 불가, WARN만 하고 통과(오탐 방지 원칙 동일 적용).
       - 대조 단위는 파일 콘텐츠 해시(sha256) — 전체 diff 는 BLOCK 일 때만 계산한다(평소엔
         해시 비교 1회 API 호출만 들어 값싸다). 한계: 베이스라인 자체가 이 스크립트를 거친
         배포에만 갱신되므로, "이 스크립트 도입 전"에 이미 있었던 원격-로컬 괴리는 최초 1회
         잡지 못한다(WARN 후 그 시점 원격을 새 베이스라인으로 삼는다).
    3) 통과 시 실제 `clasp push --force` + `clasp deploy`를 대상 clasp 폴더에서
       실행한다. `--` 뒤 인자는 `clasp deploy`에 그대로 패스스루된다
       (예: `-i <deploymentId> -d "설명"`).
    4) 배포 성공 후 status/gas_version_status.json 및 status/gas_push_baseline.json 을
       갱신한다(가능하면).

실행법:
    python scripts/gas_deploy_guard.py funnel-v2 -- -i AKfycby... -d "설명"
    python scripts/gas_deploy_guard.py check --check-only          # 검증용 dry-run(배포 안 함)
    python scripts/gas_deploy_guard.py funnel --check-only --force # BLOCK 우회 분기 확인
    python scripts/gas_deploy_guard.py reception --check-only --simulate-drift
        # 원격 무단변경을 흉내 내 BLOCK 판정만 확인(네트워크 호출 없음·배포 없음)

<project> = gas_version_monitor._PROJECTS 의 프로젝트명(check/funnel/funnel-v2/todo/reception)
            또는 로컬 clasp 폴더명(.deploy-check 등).

에이전트는 이제 raw `clasp deploy` 대신 이 스크립트로 배포한다.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPT_DIR)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import gas_version_monitor as gvm  # noqa: E402

_WARN_THRESHOLD = 180   # 이상이면 눈에 띄는 경고(진행은 허용)
_BLOCK_THRESHOLD = 195  # 이상이면 기본 중단(--force로만 강행)
_HARD_LIMIT = gvm._HARD_LIMIT

# ── INC-042 재발방지(2026-08-05 시토) ──────────────────────────────────────
# 배경: clasp deploy -i(기존 배포ID 재배포)는 성공 응답 후에도 실제 /exec 엔드포인트가
# 새 코드로 완전히 전환되기까지 전파 지연이 있다. 그 창에서 쓰기성 호출(삭제 등)을
# 검증용으로 보내면 옛 코드가 응답해 실고객 행이 지워질 수 있다(실제 발생: 박상훈 건).
# ★근본 해결(신버전 응답을 실제로 확인 후 통과)은 Survey.js에 버전 echo 액션을 새로
# 심어야 하는 더 큰 변경이라 이번엔 보류한다(과한 장치 — 배포마다 프로젝트 코드 자체를
# 건드리는 부담이 이 사고 재발확률보다 크다). 대신 값싸고 확실한 완화책: 배포 성공 직후
# 이 프로세스가 일정 시간 자체적으로 대기한 뒤에야 종료한다 — 배포→검증을 이어서 하는
# 사람·에이전트라면 다음 호출이 자연히 전파 지연 창 밖에서 일어난다.
# ponytail: 대기시간(20초)은 INC-042 실측("수 초 이내")에 안전 여유를 더한 추정치이지
# GAS가 보장하는 상한이 아니다. 상한을 알 수 없다는 뜻 — 그래도 "배포 직후 첫 호출은
# 반드시 읽기 전용" 원칙은 이 대기와 무관하게 항상 지켜야 한다(예외 없음). 업그레이드
# 경로: Survey.js에 action=_version(배포마다 바뀌는 상수) 추가 후 그 값이 바뀔 때까지
# 폴링하는 방식으로 교체하면 추정 대신 실측 확인이 된다.
_COOLDOWN_SEC = 20
_COOLDOWN_PATH = os.path.join(_ROOT_DIR, 'status', 'gas_deploy_cooldown.json')

# ── 원격 무단변경 가드(2026-08-05 시토) ─────────────────────────────────────
_BASELINE_PATH = os.path.join(_ROOT_DIR, 'status', 'gas_push_baseline.json')
_TYPE_EXT = {'SERVER_JS': '.js', 'HTML': '.html', 'JSON': '.json'}


def _fetch_remote_content(script_id: str, access_token: str | None) -> dict[str, str] | None:
    """Apps Script API projects.getContent — 원격 프로젝트 현재 파일 전체({파일명: 소스}).
    실패(토큰 없음·네트워크·권한)하면 None — 호출부가 오탐 방지로 통과 처리한다."""
    if not access_token:
        return None
    url = f'https://script.googleapis.com/v1/projects/{script_id}/content'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {access_token}'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"[WARN] {script_id} 원격 콘텐츠 조회 실패: {e}", flush=True)
        return None
    files: dict[str, str] = {}
    for f in data.get('files', []):
        name = f.get('name', '')
        ext = _TYPE_EXT.get(f.get('type', ''), '')
        key = name if (not ext or name.endswith(ext)) else name + ext
        files[key] = f.get('source', '')
    return files


def _content_hash(files: dict[str, str]) -> str:
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(name.encode('utf-8'))
        h.update(b'\x00')
        h.update(files[name].encode('utf-8'))
        h.update(b'\x00')
    return h.hexdigest()


def _load_baseline(name: str) -> dict | None:
    try:
        with open(_BASELINE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f).get(name)
    except Exception:
        return None


def _save_baseline(name: str, files: dict[str, str]) -> None:
    data = {}
    try:
        with open(_BASELINE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {}
    data[name] = {
        'hash': _content_hash(files),
        'files': files,
        'saved_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }
    try:
        os.makedirs(os.path.dirname(_BASELINE_PATH), exist_ok=True)
        with open(_BASELINE_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 베이스라인 저장 실패(배포 자체는 성공): {e}", flush=True)


def _diff_files(base_files: dict[str, str], remote_files: dict[str, str]) -> list[str]:
    """베이스라인(마지막 push 시점 원격) vs 지금 원격 — 파일별 unified diff(파일당 최대 40줄)."""
    out: list[str] = []
    for fname in sorted(set(base_files) | set(remote_files)):
        old, new = base_files.get(fname, ''), remote_files.get(fname, '')
        if old == new:
            continue
        d = list(difflib.unified_diff(
            old.splitlines(), new.splitlines(),
            fromfile=f'baseline/{fname}', tofile=f'remote-now/{fname}', lineterm='', n=1,
        ))
        if len(d) > 40:
            d = d[:40] + ['... (이하 생략)']
        out.append(f'--- {fname} ---')
        out.extend(d)
    return out


def _decide_drift(name: str, script_id: str, access_token: str | None,
                   simulate_drift: bool) -> tuple[str, str, list[str], dict[str, str] | None]:
    """(decision, message, diff_lines, remote_files) 반환. decision ∈ {PASS, WARN, BLOCK}.
    remote_files 는 성공적으로 조회됐을 때만 채워짐(push 후 베이스라인 갱신에 재사용)."""
    if simulate_drift:
        # ★검증 전용 — 네트워크 호출·실배포 없이 BLOCK 분기만 확인한다.
        base_files = {'(simulated).js': 'function f(){ return 1; }\n'}
        remote_files = {'(simulated).js': 'function f(){ return 1; }\n// 사람이 편집기에서 넣은 줄\n'}
        diff_lines = _diff_files(base_files, remote_files)
        return 'BLOCK', "🔴 [시뮬레이션] 원격 변경 감지 — 실제 조회 아님(--simulate-drift).", diff_lines, None

    remote_files = _fetch_remote_content(script_id, access_token)
    if remote_files is None:
        return 'WARN', "⚠️ 원격 콘텐츠 조회 실패 — 대조 없이 통과(오탐 방지).", [], None

    baseline = _load_baseline(name)
    if baseline is None:
        return ('WARN',
                "⚠️ 베이스라인 없음(이 가드 도입 후 첫 배포) — 대조 없이 통과. "
                "이번 push 성공 후 지금 원격 상태를 새 베이스라인으로 기록합니다.",
                [], remote_files)

    remote_hash = _content_hash(remote_files)
    if baseline.get('hash') == remote_hash:
        return 'PASS', "🟢 원격 변경 없음 — 마지막 배포 이후 그대로.", [], remote_files

    diff_lines = _diff_files(baseline.get('files', {}), remote_files)
    return ('BLOCK',
            "🔴 원격이 마지막 배포 이후 우리 모르게 바뀌었다 — 편집기 직접 수정일 수 있다. "
            "지금 push하면 그 내용이 사라진다. 배포 중단(--force로만 강행 가능).",
            diff_lines, remote_files)


def _write_cooldown(name: str) -> None:
    """배포 성공 직후 프로젝트별 쿨다운 마커를 남긴다(다른 스크립트가 참조 가능)."""
    data = {}
    try:
        with open(_COOLDOWN_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {}
    now = time.time()
    data[name] = {'deployed_at': now, 'cooldown_until': now + _COOLDOWN_SEC}
    try:
        os.makedirs(os.path.dirname(_COOLDOWN_PATH), exist_ok=True)
        with open(_COOLDOWN_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 쿨다운 마커 기록 실패(배포 자체는 성공): {e}", flush=True)


def in_deploy_cooldown(project: str) -> tuple[bool, float]:
    """다른 스크립트가 쓰기성 호출 전에 확인할 수 있는 공개 헬퍼.
    반환: (쿨다운 중인가, 남은 초). 마커가 없으면 (False, 0.0) — 배포 이력이 없거나
    이미 지난 것으로 간주(오탐으로 정상 작업을 막지 않는다)."""
    resolved = _resolve_project(project)
    name = resolved[0] if resolved else project
    try:
        with open(_COOLDOWN_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return False, 0.0
    entry = data.get(name)
    if not entry:
        return False, 0.0
    remaining = entry.get('cooldown_until', 0) - time.time()
    return (remaining > 0, max(0.0, remaining))


def _resolve_project(project_arg: str) -> tuple[str, str, str] | None:
    """project_arg(프로젝트명/로컬폴더명) → (name, script_id, local_dir). 못 찾으면 None."""
    norm = project_arg.strip().replace('\\', '/').strip('/')
    if norm.startswith('./'):
        norm = norm[2:]
    norm_lower = norm.lower()
    for name, script_id, local_dir in gvm._PROJECTS:
        local_norm = local_dir.replace('\\', '/').strip('/').lower()
        if norm_lower in (name.lower(), local_norm, f".deploy-{name}".lower()):
            return name, script_id, local_dir
    return None


def _fetch_count_for(script_id: str, local_dir: str) -> tuple[int | None, str]:
    """단일 프로젝트 버전수 조회(gas_version_monitor 로직 재사용). (count, source) 반환."""
    access_token = gvm._get_access_token()
    count = None
    source = 'unknown'
    if access_token:
        count = gvm._fetch_version_count(script_id, access_token)
        if count is not None:
            source = 'api'
    if count is None:
        count = gvm._clasp_fallback(local_dir)
        if count is not None:
            source = 'clasp_fallback'
    return count, source


def _decide(count: int | None) -> tuple[str, str]:
    """(decision, message) 반환. decision ∈ {'PASS', 'WARN', 'BLOCK'}."""
    if count is None:
        return 'WARN', (
            "⚠️ 버전수 조회 실패 — 확인 없이 통과(오탐 방지). "
            "수동으로 `clasp versions` 확인 권장."
        )
    if count >= _BLOCK_THRESHOLD:
        return 'BLOCK', (
            f"🔴 버전 {count}/{_HARD_LIMIT} — 200 하드리밋 임박. "
            f"배포 중단(--force로만 강행 가능). 이사(신규 프로젝트)를 먼저 검토하세요."
        )
    if count >= _WARN_THRESHOLD:
        return 'WARN', (
            f"⚠️ 버전 {count}/{_HARD_LIMIT} — 이사 임박. "
            f"배포는 계속 진행되나 곧 이사 계획이 필요합니다."
        )
    return 'PASS', f"🟢 버전 {count}/{_HARD_LIMIT} — 여유 있음."


def main() -> int:
    argv = sys.argv[1:]
    if '--' in argv:
        idx = argv.index('--')
        own_args, passthrough = argv[:idx], argv[idx + 1:]
    else:
        own_args, passthrough = argv, []

    parser = argparse.ArgumentParser(
        description='GAS 배포 직전 버전 가드 — raw clasp deploy 대신 사용',
    )
    parser.add_argument(
        'project',
        help='프로젝트명(check/funnel/funnel-v2/todo/reception) 또는 로컬 clasp 폴더명(.deploy-*)',
    )
    parser.add_argument(
        '--check-only', action='store_true',
        help='버전 조회·임계 판정만 하고 실제 배포는 하지 않음(검증용)',
    )
    parser.add_argument(
        '--force', action='store_true',
        help='BLOCK(>=195) 임계를 넘겨 강행 배포',
    )
    parser.add_argument(
        '--simulate-count', type=int, default=None,
        help='[테스트 전용] 실제 조회 대신 지정한 버전수로 임계 분기를 검증',
    )
    parser.add_argument(
        '--simulate-drift', action='store_true',
        help='[테스트 전용] 원격 무단변경을 흉내 내 BLOCK 분기만 확인(네트워크 호출·실배포 없음)',
    )
    parser.add_argument(
        '--description', '-d', default=None,
        help="clasp deploy -d 설명('--' 패스스루 인자가 있으면 무시됨)",
    )
    args = parser.parse_args(own_args)

    resolved = _resolve_project(args.project)
    if resolved is None:
        known = ', '.join(n for n, _, _ in gvm._PROJECTS)
        print(f"[ERROR] 알 수 없는 프로젝트: {args.project} (가능: {known})", flush=True)
        return 2
    name, script_id, local_dir = resolved

    if args.simulate_count is not None:
        count, source = args.simulate_count, 'simulated'
    else:
        count, source = _fetch_count_for(script_id, local_dir)

    decision, message = _decide(count)
    print(f"[{name}] scriptId={script_id} source={source}", flush=True)
    print(message, flush=True)

    if decision == 'BLOCK':
        if not args.force:
            print("배포 중단됨. 강행하려면 --force 명시.", flush=True)
            return 1
        print("--force 지정 — BLOCK 임계를 우회하여 진행합니다.", flush=True)

    # ★원격 무단변경 가드 — push(원격 통째 덮어쓰기) 전에 반드시 대조한다.
    drift_token = None if args.simulate_drift else gvm._get_access_token()
    drift_decision, drift_message, drift_diff, drift_remote_files = _decide_drift(
        name, script_id, drift_token, args.simulate_drift,
    )
    print(drift_message, flush=True)
    if drift_decision == 'BLOCK':
        for line in drift_diff:
            print(line, flush=True)
        if not args.force:
            print("배포 중단됨(원격 무단변경). 강행하려면 --force 명시.", flush=True)
            return 1
        print("--force 지정 — 원격 무단변경을 무시하고 진행합니다(이 push가 그 변경을 지웁니다).",
              flush=True)

    # ★로컬 역행 경보(경보만·차단 안 함) — 원격에는 있는데 로컬에는 없는 줄 수를 알린다.
    #   위 대조는 '원격이 우리 모르게 바뀌었나'만 본다. 반대 방향(로컬 편집이 유실돼 라이브보다
    #   뒤처진 상태)은 원격=베이스라인이라 PASS 로 통과하고, 그대로 push 하면 라이브에서 살아 있던
    #   코드가 조용히 사라진다. 2026-08-05 실사고: member_active_update 왕복 축소가 라이브(@248)에는
    #   있는데 로컬 작업트리에서만 사라져 있었다. 정상 삭제 편집도 걸리므로 판단은 사람이 한다.
    for _fname, _remote_src in (drift_remote_files or {}).items():
        _lpath = os.path.join(_ROOT_DIR, local_dir, _fname)
        if not os.path.isfile(_lpath):
            continue
        with open(_lpath, encoding='utf-8') as _lf:
            _local_lines = _lf.read().replace('\r\n', '\n').split('\n')
        _remote_lines = _remote_src.replace('\r\n', '\n').split('\n')
        _lost = sum(i2 - i1 for tag, i1, i2, _j1, _j2
                    in difflib.SequenceMatcher(None, _remote_lines, _local_lines).get_opcodes()
                    if tag == 'delete')
        if _lost:
            print(f"⚠️ [로컬 역행 확인] {_fname} — 원격에 있고 로컬에 없는 줄 {_lost}개. "
                  f"의도한 삭제면 그대로 진행, 아니면 push 를 멈추고 로컬을 먼저 회수하세요.",
                  flush=True)

    if args.check_only:
        print("[check-only] 실제 배포는 수행하지 않음.", flush=True)
        return 0

    clasp_dir = os.path.join(_ROOT_DIR, local_dir)
    if not os.path.isdir(clasp_dir):
        print(f"[ERROR] 로컬 clasp 폴더 없음: {clasp_dir}", flush=True)
        return 2

    deploy_cmd = ['clasp', 'deploy']
    if passthrough:
        deploy_cmd += passthrough
    elif args.description:
        deploy_cmd += ['-d', args.description]

    # ★ 2026-07-28 시모 — push 와 deploy 를 **하나의 락 안에서** 붙여 실행한다.
    #   왜: 배포는 두 단계다. clasp push(로컬 작업트리 → GAS) 다음에 clasp deploy(현재 GAS → /exec).
    #   이 저장소는 여러 세션이 작업트리 하나를 공유하므로, 두 단계 **사이에** 다른 세션이
    #   자기 사본을 push 하면 내 deploy 가 **남의 코드를 라이브로 올린다.**
    #   2026-07-28 실제 발생: 시모가 네이버 채널 분리를 push·deploy 했는데 사이에 시포 세션이
    #   끼어들어 라이브가 옛 코드로 되돌아갔다(같은 Survey.js 를 두 역할이 동시에 고치던 중).
    #   재푸시·재배포로 복구했지만, 그 사이 화면 숫자가 잘못 나갔다.
    #   고침: 커밋 직렬화에 쓰는 기존 GitLock 을 그대로 재사용한다(새 락 발명 금지·약속 L21).
    #   같은 락이라 배포 중에는 다른 세션의 커밋도 대기한다 — 작업트리가 안 흔들려야
    #   push 한 내용이 그대로 deploy 되기 때문이다.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from git_lock import GitLock
    except Exception as e:
        print(f"[ERROR] 배포 락 로드 실패 — 직렬화 없이 배포하지 않는다: {e}", flush=True)
        return 2

    try:
        with GitLock(holder=f"gas_deploy:{name}", repo_root=_ROOT_DIR):
            print(f"[{name}] clasp push --force ... (배포 락 확보)", flush=True)
            push = subprocess.run(['clasp', 'push', '--force'], cwd=clasp_dir, shell=True)
            if push.returncode != 0:
                print("[ERROR] clasp push 실패 — 배포 중단.", flush=True)
                return push.returncode

            # push 성공 직후 원격을 다시 읽어 새 베이스라인으로 기록한다(다음 배포가 대조할 지문).
            if not args.simulate_drift:
                post_push_files = _fetch_remote_content(script_id, drift_token or gvm._get_access_token())
                if post_push_files is not None:
                    _save_baseline(name, post_push_files)
                else:
                    print("[WARN] push 후 베이스라인 갱신 실패(다음 배포는 대조 없이 WARN 통과).", flush=True)

            print(f"[{name}] {' '.join(deploy_cmd)} ...", flush=True)
            deploy = subprocess.run(deploy_cmd, cwd=clasp_dir, shell=True)
            if deploy.returncode != 0:
                print("[ERROR] clasp deploy 실패.", flush=True)
                return deploy.returncode
    except Exception as e:
        # 락을 못 잡으면 배포하지 않는다 — 직렬화 없는 배포가 오늘 사고의 원인이었다.
        print(f"[ERROR] 배포 락 획득 실패 — 다른 세션이 커밋/배포 중일 수 있다. "
              f"잠시 후 다시 시도하라: {e}", flush=True)
        return 2

    print(f"[OK] {name} 배포 완료.", flush=True)
    # ★INC-042 재발방지(2026-08-05 시토) — 쿨다운 마커 기록 + 이 프로세스 자체를 대기시킨다.
    #   왜: 문구만 출력하고 바로 종료하면 사람도 에이전트도 그 다음 줄에서 바로 검증 호출을
    #   보낸다(오늘 사고가 정확히 이 순서였다). 대기 자체가 전파 지연 창을 지나가게 한다.
    _write_cooldown(name)
    print(f"  → 배포 전파 대기 {_COOLDOWN_SEC}초 — 이 시간 동안은 옛 코드가 응답할 수 있다. "
          f"기다리는 동안 검증 호출을 보내지 마라.", flush=True)
    time.sleep(_COOLDOWN_SEC)
    print("  → 대기 종료. 그래도 첫 검증은 반드시 읽기 전용 호출로만 하라(쓰기·삭제 검증 금지, 예외 없음) "
          "— 이 대기는 확률을 낮출 뿐 GAS 전파시간을 보장하지 않는다.", flush=True)

    try:
        results = gvm.collect()
        gvm._write_status(results)
    except Exception as e:
        print(f"[WARN] 배포 후 상태 갱신 실패(배포 자체는 성공): {e}", flush=True)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
