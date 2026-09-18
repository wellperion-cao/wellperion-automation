# -*- coding: utf-8 -*-
"""옛 혼재 로그(1회) → 센터별 폴더로 분리 (배 12768 · 상담봇_기획설계_v1.0.html §12③ · 시토).

무엇을 하나
  /srv/erp/chat_log.jsonl · counsel_usage.jsonl · chat_feedback.jsonl(+ 회전본 .타임스탬프)에 섞여
  쌓인 세 센터 행을, api_chat._log_path(tenant, kind) 가 읽는 새 위치(FAQ_DIR/{tenant}/*.jsonl)로
  나눠 옮긴다. 행의 tenant 칸으로 갈래를 정하고, 없거나 못 읽는 행은 {FAQ_DIR}/_unknown/ 로 보낸다.

안전 규칙
  - append 만 한다(멱등) — 대상 파일에 같은 줄(문자열 그대로)이 이미 있으면 건너뛴다.
  - 옛 파일은 지우지 않는다. --apply 로 성공하면 이름만 .migrated-YYYYMMDD 로 바꾼다(내용은 그대로).
  - 끝에 센터별 옮긴 행 수 표 + 검산(원본 줄 수 == 새로 옮긴 수 + 이미 있던 수) — 안 맞으면 exit 1.

사용:
  python3 split_chat_logs.py --dry-run     # 무엇이 어디로 갈지 미리보기(파일 안 만든다)
  python3 split_chat_logs.py --apply       # 실제 분리 + 옛 파일 이름 변경
  python3 split_chat_logs.py --selftest    # 임시 폴더에 가짜 3행으로 자체점검
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import api_chat  # noqa: E402 — TENANTS·FAQ_DIR 재사용(센터 판정 규칙을 두 곳에 안 둔다)

KINDS = {"chat": "chat_log.jsonl", "usage": "counsel_usage.jsonl", "feedback": "chat_feedback.jsonl"}


def _old_dir() -> str:
    """옛 혼재 파일이 있던 곳 — FAQ_DIR(.../erp/faq)의 부모(.../erp)."""
    return os.path.dirname(os.path.normpath(api_chat.FAQ_DIR)) or "/srv/erp"


def _old_generations(base_name: str, old_dir: str) -> list:
    """현재본 + 회전본(.타임스탬프) 전부 — api_chat._log_generations 와 같은 이름 규칙.
    이미 이번 스크립트가 옮긴 뒤 이름 바뀐 파일(.migrated-*)은 다시 원본으로 안 집는다(재실행 시 무한 접미 방지)."""
    try:
        names = [n for n in os.listdir(old_dir)
                 if (n == base_name or n.startswith(base_name + ".")) and ".migrated-" not in n]
    except OSError:
        return []
    rotated = sorted(n for n in names if n != base_name)
    return [os.path.join(old_dir, n) for n in rotated] + (
        [os.path.join(old_dir, base_name)] if base_name in names else [])


def _route_tenant(line: str) -> str:
    """행 하나가 갈 테넌트 — tenant 칸이 없거나 아는 센터가 아니거나 json 이 아니면 _unknown."""
    try:
        t = json.loads(line).get("tenant")
    except (json.JSONDecodeError, AttributeError):
        return "_unknown"
    return t if t in api_chat.TENANTS else "_unknown"


def split_kind(kind: str, apply: bool, old_dir: str = None) -> dict:
    """이 갈래(chat/usage/feedback) 옛 파일 전부를 센터별로 나눈다 — {tenant: 새로 옮긴 행 수} 반환."""
    old_dir = old_dir or _old_dir()
    base_name = KINDS[kind]
    sources = _old_generations(base_name, old_dir)
    dest_existing: dict = {}   # tenant → 대상 파일의 기존 줄 집합(중복 판정 · 파일당 한 번만 읽는다)
    written: dict = {}
    skipped_dup = 0
    total_src = 0
    for src in sources:
        try:
            with open(src, encoding="utf-8", errors="replace") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
        except OSError:
            continue
        total_src += len(lines)
        for line in lines:
            tenant = _route_tenant(line)
            dest = Path(api_chat.FAQ_DIR) / tenant / base_name
            if tenant not in dest_existing:
                try:
                    dest_existing[tenant] = set(
                        ln.strip() for ln in dest.read_text(encoding="utf-8").splitlines() if ln.strip())
                except OSError:
                    dest_existing[tenant] = set()
            if line in dest_existing[tenant]:
                skipped_dup += 1
                continue
            written[tenant] = written.get(tenant, 0) + 1
            dest_existing[tenant].add(line)   # 같은 실행 안의 중복도 걸러서 미리보기·실행 수를 맞춘다
            if apply:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
    new_total = sum(written.values())
    accounted = new_total + skipped_dup
    if accounted != total_src:
        print("[split_chat_logs] %s 검산 실패 — 원본 %d행 ≠ 처리 %d행(새 %d + 이미 있음 %d)"
              % (kind, total_src, accounted, new_total, skipped_dup), file=sys.stderr)
        sys.exit(1)
    print("[split_chat_logs] %s — 원본 %d행 · 새로 옮김 %d · 이미 있어 건너뜀 %d"
          % (kind, total_src, new_total, skipped_dup))
    for tenant, n in sorted(written.items()):
        print("  %-14s %d행" % (tenant, n))
    if apply and sources:
        stamp = datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")
        for src in sources:
            os.replace(src, src + ".migrated-" + stamp)
    return written


def _selftest() -> None:
    import tempfile
    tmp = tempfile.mkdtemp()
    faq_dir = os.path.join(tmp, "faq")
    os.makedirs(faq_dir, exist_ok=True)
    saved_faq_dir, api_chat.FAQ_DIR = api_chat.FAQ_DIR, faq_dir
    try:
        rows = [
            {"ts": "2026-09-18T10:00:00", "tenant": "1_wellperion", "q": "가짜질문A"},
            {"ts": "2026-09-18T10:01:00", "tenant": "2_dietcamp", "q": "가짜질문B"},
            {"ts": "2026-09-18T10:02:00", "q": "테넌트 칸 없음"},   # → _unknown
        ]
        src_path = os.path.join(tmp, "chat_log.jsonl")
        with open(src_path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        written = split_kind("chat", apply=True, old_dir=tmp)
        assert written == {"1_wellperion": 1, "2_dietcamp": 1, "_unknown": 1}, written
        assert (Path(faq_dir) / "1_wellperion" / "chat_log.jsonl").exists()
        assert (Path(faq_dir) / "_unknown" / "chat_log.jsonl").exists()
        assert not os.path.exists(src_path), "옛 파일은 지우지 않고 이름만 바뀌어야 한다"
        migrated = [n for n in os.listdir(tmp) if n.startswith("chat_log.jsonl.migrated-")]
        assert len(migrated) == 1, migrated
        # 재실행(같은 내용) — 이미 옮긴 3행 전부 중복으로 건너뛴다(멱등) · .migrated-* 는 다시 원본으로 안 잡는다.
        with open(src_path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        written2 = split_kind("chat", apply=True, old_dir=tmp)
        assert sum(written2.values()) == 0, written2
        # 같은 날 재실행이면 .migrated-YYYYMMDD 이름이 겹쳐 os.replace 가 그대로 덮어쓴다(1회성 스크립트라
        # 하루 안 재실행은 내용이 같을 때만 의미가 있다 — 문제 없음. 파일 자체는 여전히 1개여야 한다).
        migrated2 = [n for n in os.listdir(tmp) if n.startswith("chat_log.jsonl.migrated-")]
        assert len(migrated2) == 1, migrated2
        print("split_chat_logs selftest ok")
    finally:
        api_chat.FAQ_DIR = saved_faq_dir


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="미리보기만(파일 안 만든다)")
    g.add_argument("--apply", action="store_true", help="실제로 옮기고 옛 파일 이름을 바꾼다")
    g.add_argument("--selftest", action="store_true", help="임시 폴더로 자체점검")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
        return
    for kind in KINDS:
        split_kind(kind, apply=args.apply)


if __name__ == "__main__":
    main()
