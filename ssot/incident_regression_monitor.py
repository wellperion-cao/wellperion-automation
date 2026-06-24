#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
재발방지 회귀감시 — 주기(일일) 스캐너.
근거: GM 승인 2026-06-24. precommit_incident_guard 는 '커밋 시점·스테이지'만 점검 →
      변경 없이 현재 트리에 슬쩍 재발한 회귀(가드 자산 유실·캐논 복사 부활)는 못 잡는다.
      이 스크립트가 '현재 상태'를 일일 점검해 회귀를 자동 탐지한다(시토 축5 재발방지).

핵심 설계(노이즈 0):
  - 캐논 발산은 항상 일정량의 수용 FP(아카이브·백업·콘텐츠 문서)가 있다 → '무엇이든 >0=회귀'는 틀림.
  - baseline(ssot/incident_baseline.json = 현재 수용 상태)을 기준으로, baseline 초과 '신규' 드리프트만 회귀로 본다.
  - 처음 실행 시 현재 상태를 baseline으로 적립(established) → 경보 없음.

검사 3종:
  ① 캐논 발산 — divergence_scan 재활용. baseline 대비 신규 복사(INC-001/004/005 류) 0이어야.
  ② 가드 자산 무결 — INC-005~008 차단조치 핵심 파일·훅 실재(유실=회귀).
  ③ 박제 무결 — incidents.json GUARDED 인시던트가 GUARDED 유지.

출력: status/incident_health.md(가시화) + 콘솔. 반환 0=정상 / 1=회귀.
경보: 회귀(신규 드리프트·가드유실·박제깨짐)일 때만 텔레그램 1줄(정상은 조용히 — 성공 로그 노이즈 금지).
직접 실행: python ssot/incident_regression_monitor.py   ·  baseline 재설정: --set-baseline
"""
from __future__ import annotations

import os
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_HERE))

BASELINE_FILE = _HERE / "incident_baseline.json"

GUARD_ASSETS = {
    "INC-005 캐논 헬퍼": "ssot/canon.py",
    "INC-006 자동 push": "scripts/post_commit_push.py",
    "INC-007 큐 미러 동기화": "scripts/sync_queue_mirror.py",
    "INC-008 큐 머지 드라이버": "scripts/git_merge_queue.py",
    "커밋 가드 러너": "ssot/precommit_incident_guard.py",
    "발산 스캐너": "ssot/divergence_scan.py",
    "캐논 정본": "ssot/canon_values.json",
    "약속 정본": "ssot/약속.json",
    "재발방지 정본": "ssot/incidents.json",
}
GIT_HOOKS = [".git/hooks/pre-commit", ".git/hooks/post-commit"]


def _is_code(f: str) -> bool:
    return (f.startswith(("scripts/", "ssot/", "telegram_bot/"))
            or f.endswith((".py", ".js", ".gs")))


def _divergence_map() -> dict | None:
    """캐논 발산(정본·allow_globs 밖 복사) → {key: set(files)}. 스캐너 오류 시 None."""
    try:
        from divergence_scan import run_scan, load_canon  # type: ignore
        canon = load_canon(_ROOT)
        results = run_scan(_ROOT, canon)
        out = {}
        for r in results:
            files = {h.get("file", "") for h in r.get("hits", []) if h.get("file")}
            if files:
                out[r.get("key", "?")] = files
        return out
    except Exception:
        return None


def _missing_assets() -> list[str]:
    miss = []
    for label, rel in GUARD_ASSETS.items():
        if not (_ROOT / rel).exists():
            miss.append(f"{label} ({rel})")
    for h in GIT_HOOKS:
        if not (_ROOT / h).exists():
            miss.append(f"git 훅 ({h})")
    return miss


def _unguarded() -> list[str]:
    try:
        d = json.loads((_ROOT / "ssot" / "incidents.json").read_text(encoding="utf-8"))
        return [f"{i.get('id')}({i.get('상태')})" for i in d.get("incidents", []) if i.get("상태") != "GUARDED"]
    except Exception:
        return ["incidents.json 읽기 실패"]


def _load_baseline() -> dict | None:
    try:
        return json.loads(BASELINE_FILE.read_text(encoding="utf-8")).get("divergence")
    except Exception:
        return None


def _save_baseline(div: dict) -> None:
    payload = {"divergence": {k: sorted(v) for k, v in div.items()},
               "_doc": "재발방지 회귀감시 baseline — 이 시점의 수용된 캐논 발산(주로 콘텐츠·아카이브 FP). "
                       "이 목록 초과분만 회귀로 경보. 코드 드리프트를 고치면 --set-baseline 로 재설정."}
    BASELINE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _alert(text: str) -> None:
    try:
        env = _ROOT / "telegram_bot" / ".env"
        if not env.exists():
            return
        token = chat = None
        for ln in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            ln = ln.strip()
            if ln.startswith("TELEGRAM_BOT_TOKEN="):
                token = ln.split("=", 1)[1].strip().strip('"').strip("'")
            elif ln.startswith("TELEGRAM_CHAT_ID="):
                chat = ln.split("=", 1)[1].strip().strip('"').strip("'")
        if not token or not chat:
            return
        import urllib.parse
        import urllib.request
        data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode("utf-8")
        urllib.request.urlopen(
            urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data), timeout=10
        ).read()
    except Exception:
        pass


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()


def run(set_baseline: bool = False) -> int:
    cur = _divergence_map()
    missing = _missing_assets()
    unguarded = _unguarded()

    # 신규 드리프트 = baseline 초과분(파일 단위).
    new_drift = {}
    established = False
    if cur is None:
        scan_state = "스캔불가"
    else:
        base = _load_baseline()
        if base is None or set_baseline:
            _save_baseline(cur)
            established = True
            scan_state = "baseline 적립" if base is None else "baseline 재설정"
        else:
            scan_state = "OK"
            for k, files in cur.items():
                extra = files - set(base.get(k, []))
                if extra:
                    new_drift[k] = sorted(extra)

    regression = bool(new_drift) or bool(missing) or bool(unguarded)
    verdict = "⚠️ 회귀 감지" if regression else "✅ 정상(회귀 없음)"

    # 현재 발산을 코드/문서로 분리(코드=수정 후보).
    code_drift, doc_fp = [], 0
    if cur:
        for k, files in cur.items():
            for f in files:
                (code_drift.append((k, f)) if _is_code(f) else None)
                if not _is_code(f):
                    doc_fp += 1

    print("🛡️ 재발방지 회귀감시")
    print(f"  캐논 발산: {scan_state}" + (f" · 신규 {sum(len(v) for v in new_drift.values())}건 {list(new_drift)}" if new_drift else ""))
    print(f"  가드 자산 유실: {len(missing)}건" + (f" {missing}" if missing else ""))
    print(f"  박제 무결: {'깨짐 '+str(unguarded) if unguarded else 'OK(전부 GUARDED)'}")
    print(f"  (참고) 기존 코드 드리프트(수정 후보): {len(code_drift)}건 · 문서 FP {doc_fp}건")
    print(f"  판정: {verdict}" + (" · baseline established" if established else ""))

    lines = [
        "# 🛡️ 재발방지 회귀감시",
        f"_갱신: {_today()} · 자동 산출(ssot/incident_regression_monitor.py)_",
        "",
        f"## 판정: {verdict}",
        "",
        "| 검사 | 결과 |",
        "|---|---|",
        f"| 신규 캐논 발산(baseline 초과) | {sum(len(v) for v in new_drift.values())}건"
        + (f" · {', '.join(new_drift)}" if new_drift else "") + " |",
        f"| 가드 자산 무결 | {'유실 '+str(len(missing))+'건' if missing else 'OK'} |",
        f"| 박제 무결(GUARDED) | {'깨짐: '+', '.join(unguarded) if unguarded else 'OK'} |",
    ]
    if new_drift:
        lines += ["", "### ⚠️ 신규 드리프트(회귀)"]
        for k, fs in new_drift.items():
            lines += [f"- **{k}**: " + ", ".join(fs)]
    if missing:
        lines += ["", "### ⚠️ 유실 가드 자산", *[f"- {m}" for m in missing]]
    if code_drift:
        lines += ["", "### 🛠 기존 코드 캐논 드리프트 (수정 후보 · INC-005류, baseline 수용분)"]
        for k, f in code_drift:
            lines += [f"- {k} ← `{f}` (canon 직독으로 전환 권장)"]
    try:
        (_ROOT / "status" / "incident_health.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass

    if regression:
        det = []
        if new_drift:
            det.append(f"신규 캐논복사 {sum(len(v) for v in new_drift.values())}건({','.join(new_drift)})")
        if missing:
            det.append(f"가드유실 {len(missing)}건")
        if unguarded:
            det.append(f"박제깨짐 {len(unguarded)}건")
        _alert("🛡️⚠️ 재발방지 회귀 감지 — " + " / ".join(det) + ". status/incident_health.md 확인.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run(set_baseline=("--set-baseline" in sys.argv)))
