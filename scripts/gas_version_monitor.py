# -*- coding: utf-8 -*-
"""GAS 프로젝트 버전 위생 모니터 — 200 하드리밋 조기 경고.

배경:
    funnel GAS(scriptId ...s8KQru)가 배포 버전 200개 하드리밋에 걸려
    신규 배포가 막혔다(구글이 버전 삭제 API를 막아 회수 불가 — 이사만이 해법).
    check(165)가 다음으로 임박한 프로젝트 — 재발방지용 상시 모니터.

동작:
    clasp OAuth 토큰(~/.clasprc.json)을 재사용해 Apps Script API
    (projects.versions.list)로 각 프로젝트의 최신 versionNumber를 조회한다.
    버전은 삭제 불가(순번 연속) 전제이므로 최신 versionNumber == 총 버전수.
    토큰 만료 시 refresh_token으로 자동 재획득(.clasprc.json 갱신 저장).
    API 실패 시 `clasp versions` CLI 폴백.

실행법:
    python scripts/gas_version_monitor.py             # 표 출력
    python scripts/gas_version_monitor.py --json       # status/gas_version_status.json 발행
    python scripts/gas_version_monitor.py --warn       # 임계(>=180)만 1줄 요약, 없으면 무출력

새 정기 알림 채널을 만들지 않는다 — 기존 telegram_health_check.py(13시)가
--warn 결과를 흡수해 임계 초과 시에만 GM 채널에 경보를 얹는다.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_SCRIPT_DIR)
_CLASPRC_PATH = os.path.join(os.path.expanduser('~'), '.clasprc.json')
_STATUS_PATH = os.path.join(_ROOT_DIR, 'status', 'gas_version_status.json')

# (프로젝트명, scriptId, clasp 로컬 폴더명) — CLAUDE.md §GAS 5개 clasp 프로젝트와 동일 소스
_PROJECTS = [
    ("check", "1FLQAzjq6IME2A41QZlfZZSzzAeaFFDAr58M6T-JzDtzzbC4gEKuQFNp6", ".deploy-check"),
    ("funnel", "1A77oDRaa21K25c3-M1AgewNfUzfW-zamfRhYWjlYUrvIdPCYazs8KQru", ".deploy-funnel"),
    ("funnel-v2", "1BezMSW_rGi57IrC9IoxoQzczsATVzqwFa039cigvhad0wpCBdOmhHTjQ", ".deploy-funnel-v2"),
    ("todo", "1VUMgK-vJvxCUO_mjQPpTFLjtv3NWWt8ESkCHH-l3QyCYrpBw2RXsYFFg", ".deploy-todo"),
    ("voc", "1_jF5yhXZfBgw7KX9adW17ER0t_lQ8xrVaGsZBraUJ5AZZPzfIGuFKw9Y", ".deploy-voc"),
    # 강사 콘텐츠 접수(마케팅 접수 폼) — 2026-07-24 등록. 미등록이라 배포 관문
    # (gas_deploy_guard)을 통과할 수 없었고, 그대로 두면 raw clasp deploy 로 새는
    # 우회로가 된다(버전 200 하드리밋 감시 사각). 배9888.
    ("instructor", "1Q5RiwzqX3Ro1GHLPM9v__CH3DKeOxM4i7NecqI7w_rv6ev0yta4PhGP0", ".deploy-instructor"),
]

_HARD_LIMIT = 200
_ICON_RED = 190       # 표 상태 아이콘 임계
_ICON_ORANGE = 150    # 표 상태 아이콘 임계
_ALERT_THRESHOLD = 180  # --warn 및 헬스체크 경보 발동 임계


# ── clasp OAuth 토큰 재사용 ───────────────────────────────────────────────────
def _load_clasprc() -> dict:
    with open(_CLASPRC_PATH, encoding='utf-8') as f:
        return json.load(f)


def _refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> tuple[str, int]:
    """refresh_token으로 새 access_token 획득. (token, expiry_ms) 반환."""
    data = urllib.parse.urlencode({
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data, method='POST')
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read())
    expires_in = body.get('expires_in', 3600)
    return body['access_token'], int(time.time() * 1000) + expires_in * 1000


def _get_access_token() -> str | None:
    """clasp 토큰 재사용. 5분 이내 만료 예정이면 자동 갱신 + .clasprc.json 갱신 저장."""
    try:
        rc = _load_clasprc()
        tok = rc['tokens']['default']
    except Exception as e:
        print(f"[WARN] ~/.clasprc.json 로드 실패: {e}", flush=True)
        return None

    now_ms = time.time() * 1000
    if tok.get('expiry_date', 0) - now_ms > 5 * 60 * 1000:
        return tok['access_token']

    try:
        access_token, expiry_ms = _refresh_access_token(
            tok['client_id'], tok['client_secret'], tok['refresh_token'],
        )
    except Exception as e:
        print(f"[WARN] clasp 토큰 갱신 실패: {e} — 기존 토큰으로 계속 시도", flush=True)
        return tok.get('access_token')

    tok['access_token'] = access_token
    tok['expiry_date'] = expiry_ms
    try:
        with open(_CLASPRC_PATH, 'w', encoding='utf-8') as f:
            json.dump(rc, f, indent=2)
    except Exception as e:
        print(f"[WARN] .clasprc.json 갱신 저장 실패(이번 실행 토큰은 유효): {e}", flush=True)
    return access_token


# ── Apps Script API 조회 ─────────────────────────────────────────────────────
def _fetch_version_count(script_id: str, access_token: str) -> int | None:
    """실제 버전 엔트리 수 조회(전체 페이지네이션 실카운트). 실패 시 None.

    ★ 2026-07-18: 편집기 UI 버전 삭제가 가능해져(버전 일괄 삭제) max(versionNumber)는
       더 이상 총 버전수와 같지 않다(삭제 후에도 최신 번호는 유지). 200 하드리밋은
       '남아있는 버전 엔트리 수' 기준이므로 전체 페이지를 세어 실카운트를 반환한다.
    """
    total = 0
    page_token = None
    got_any = False
    while True:
        url = f'https://script.googleapis.com/v1/projects/{script_id}/versions?pageSize=100'
        if page_token:
            url += '&pageToken=' + urllib.parse.quote(page_token)
        req = urllib.request.Request(url, headers={'Authorization': f'Bearer {access_token}'})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            print(f"[WARN] {script_id} API 조회 실패: HTTP {e.code} {e.reason}", flush=True)
            return None if not got_any else total
        except Exception as e:
            print(f"[WARN] {script_id} API 조회 예외: {e}", flush=True)
            return None if not got_any else total
        got_any = True
        total += len(data.get('versions', []))
        page_token = data.get('nextPageToken')
        if not page_token:
            break
    return total


# ── clasp CLI 폴백 ────────────────────────────────────────────────────────────
def _clasp_fallback(local_dir: str) -> int | None:
    """API 실패 시 `clasp versions` CLI 폴백(로컬 clasp 로그인 필요)."""
    clasp_dir = os.path.join(_ROOT_DIR, local_dir)
    if not os.path.isdir(clasp_dir):
        return None
    try:
        result = subprocess.run(
            ['clasp', 'versions'], cwd=clasp_dir, capture_output=True,
            text=True, timeout=30, shell=True,
        )
        nums = []
        for line in result.stdout.splitlines():
            head = line.strip().split(' ', 1)[0]
            if head.isdigit():
                nums.append(int(head))
        return max(nums) if nums else None
    except Exception as e:
        print(f"[WARN] {local_dir} clasp 폴백 실패: {e}", flush=True)
        return None


def _status_icon(count: int) -> str:
    if count >= _ICON_RED:
        return "🔴"
    if count >= _ICON_ORANGE:
        return "🟠"
    return "🟢"


def collect() -> list[dict]:
    """5개 프로젝트 버전수 조회 결과 리스트. 각 dict: project/script_id/version_count/status/source."""
    access_token = _get_access_token()
    results: list[dict] = []
    for name, script_id, local_dir in _PROJECTS:
        count = None
        source = 'unknown'
        if access_token:
            count = _fetch_version_count(script_id, access_token)
            if count is not None:
                source = 'api'
        if count is None:
            count = _clasp_fallback(local_dir)
            if count is not None:
                source = 'clasp_fallback'
        results.append({
            'project': name,
            'script_id': script_id,
            'version_count': count,
            'status': _status_icon(count) if count is not None else "⚪",
            'source': source,
        })
    return results


def _write_status(results: list[dict]) -> None:
    payload = {
        'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'hard_limit': _HARD_LIMIT,
        'alert_threshold': _ALERT_THRESHOLD,
        'projects': results,
    }
    os.makedirs(os.path.dirname(_STATUS_PATH), exist_ok=True)
    with open(_STATUS_PATH, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[OK] 발행: {_STATUS_PATH}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description='GAS 프로젝트 버전 위생 모니터')
    parser.add_argument('--json', action='store_true', help='status/gas_version_status.json 발행')
    parser.add_argument('--warn', action='store_true',
                         help='임계(>=180) 프로젝트만 1줄 요약 출력(없으면 무출력)')
    args = parser.parse_args()

    results = collect()

    if args.warn:
        alerts = [r for r in results if r['version_count'] is not None and r['version_count'] >= _ALERT_THRESHOLD]
        if alerts:
            parts = [f"{r['project']} {r['version_count']}/{_HARD_LIMIT}" for r in alerts]
            print(f"⚠️ GAS 버전 임박: {', '.join(parts)}", flush=True)
        if args.json:
            _write_status(results)
        return

    header = f"{'프로젝트':<12}{'scriptId':<48}{'버전수':>8}  상태"
    print(header, flush=True)
    for r in results:
        count_str = str(r['version_count']) if r['version_count'] is not None else '조회실패'
        print(f"{r['project']:<12}{r['script_id']:<48}{count_str:>8}  {r['status']}", flush=True)

    if args.json:
        _write_status(results)


if __name__ == '__main__':
    main()
