#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gm_directive_pipeline.py — GM 지시 정리 엔진 (배 2764 · GM 09-18)

왜 있나
  GM 이 날메모(PC 파일 / 텔레그램 GM지시방)를 던지면 표준 포맷으로 정리하고,
  담당별(AI 6역할 + 사람 관리자 3인)로 배·업무SSOT 배포까지 잇는다.
  정본 = status/briefs/CEO-2026-09-18-GM지시-자동화-파이프라인.md

파이프라인 2단계
  organize: 날메모(텍스트) → 표준 정리본(.md) + 항목 JSON 사이드카(.json)
            LLM 호출 = model_router.run_claude(JUDGMENT_CHAIN) — 판단 호출이라 Fable 5.1 1순위.
  publish : 정리본 JSON → 역할별 queue_dispatch.py(AI 6역할) / gm_handoff.py(사람 3인) 명령을
            만들어 실행(--apply) 또는 미리보기(기본, --dry-run). 3-트리거(💰/🔒/🚫) 항목은
            자동 배포 대상에서 빼고 GM 재확인 목록에만 남긴다. 매 항목을
            status/gm_directives.json 원장에 append.

쓰는 법
  python scripts/gm_directive_pipeline.py organize --in D:\\GM지시\\260919.txt --source GM
  python scripts/gm_directive_pipeline.py publish --md status/directives/2026-09-19_정리.md --apply
  python scripts/gm_directive_pipeline.py selfcheck

# ponytail: 원장(gm_directives.json)은 gm_asks.py 와 같은 방식 — 통째 read-modify-write,
# 전용 락 없음(호출 빈도가 낮다). 경합이 실측되면 queue_lock.py 패턴을 얹는다.
# ponytail: LLM 응답의 마크다운/JSON 분리는 고정 구분자(SPLIT_MARK) 한 줄 — 모델이 프롬프트의
# 출력형식 지시를 어기면(구분자 누락) organize 가 그 자리에서 실패하고 사람이 재시도한다.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime as _dt
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_router  # noqa: E402  (attribute 접근으로 호출 — selfcheck 가 run_claude 를 몽키패치한다)

KST = _dt.timezone(_dt.timedelta(hours=9))
LEDGER_PATH = ROOT / "status" / "gm_directives.json"

# AI 6역할만(약속 — CHRO 시로/CFO 시뽀는 나우열M 라인이라 이 큐 밖).
AI_ROLES = {"웰리": "ceo", "시토": "cto", "시모": "cmo", "시우": "coo", "시포": "cpo", "시보": "cbo"}
PEOPLE = ["이경연 실장", "이정헌 소장", "나우열M"]
TRIGGER_TAG = "⛔GM 재확인(💰/🔒/🚫)"
SPLIT_MARK = "<<<JSON>>>"


def _is_trigger(title: str) -> bool:
    """모델이 준 JSON "trigger" 불리언은 안 믿는다(실측 2026-09-18: 23/24건 뒤집혀 나옴).
    제목의 ⛔ 태그가 정본 — 코드가 결정적으로 다시 판정한다. 모델이 {TRIGGER_TAG} 를 통째로 안 쓰고
    해당 아이콘만 남겨 「⛔GM 재확인(💰)」식으로 줄이는 경우가 있어(실측: CCTV 결제 건이 그렇게 나와
    리터럴 전체 일치에서 새고 자동배포됨) 부분 일치로 잡는다."""
    t = title or ""
    return "⛔" in t or "GM 재확인" in t

FEWSHOT = """26.9.18(금) 에이전트 지시사항 정리
■ 웰리
1. [GM 지시] GM 지시 자동화 파이프라인 구축
   완료 기준: SSOT에 게시되고 승인 흐름이 동작함
■ 시토
1. [GM 지시] 텔레그램 GM지시방 신설
   완료 기준: 방 개설·봇 수신 확인
■ 시모
■ 시우
■ 시포
■ 시보
■ 미결 사항
■ 사람 관리자
"""


def _prompt(memo: str, source: str, date: str) -> str:
    return f"""너는 웰페리온 GM 지시 정리 엔진이다. 아래 GM 날메모를 표준 포맷으로 정리하라.

[규칙]
- 섹션 순서 고정(빈 섹션도 제목은 남긴다): 웰리 / 시토 / 시모 / 시우 / 시포 / 시보 / 미결 사항 / 사람 관리자
- 각 절 안 번호는 1. 2. 3. + 하위 (1) (2)
- 같은 건이 여러 역할에 흩어지면 주담당 1곳으로 모으고 그 항목에 「(협업: 역할)」 표기
- 당부·감정 문구는 목표 문장으로 압축
- 원문이 끊기거나 미확정이면 「미결 사항」 절로 뺀다
- 모든 항목 끝에 「완료 기준: …」 한 줄
- 모든 항목 앞에 [{source} 지시] 태그(원문에 회장님/대표님이 나오면 그쪽 태그로 바꾼다)
- 💰결제·🔒보안·🚫금지 관련 항목만 항목 끝(과 JSON title 끝)에 {TRIGGER_TAG} 를 붙이고 미결 사항에도 나열 —
  그 외 모든 항목은 이 태그를 절대 붙이지 않는다(일반 실행 항목이지 GM 재확인 대상이 아니다).
  해당하는 아이콘(💰/🔒/🚫)만 남겨 줄여 써도 된다 — 단 ⛔ 는 반드시 남긴다
- 사람 관리자(이경연 실장/이정헌 소장/나우열M) 앞 지시는 「사람 관리자」 절에 담고 기한을 명시

[견본]
{FEWSHOT}

[출력형식] 정확히 이 순서로 두 블록만 낸다.
1) 위 규칙을 따른 마크다운 정리본 전체
2) 그 다음 줄에 정확히 {SPLIT_MARK} 한 줄
3) 그 다음 블록 = 항목 배열 JSON 하나만(설명 텍스트 없이). 각 원소:
   {{"id": 정수, "role": "웰리|시토|시모|시우|시포|시보|이경연 실장|이정헌 소장|나우열M",
     "title": "한 줄 제목", "dod": "완료 기준 문장", "source": "{source}",
     "trigger": "이 항목 title 에 {TRIGGER_TAG} 가 붙어 있으면 true, 없으면 false(대부분 false다)",
     "collab": "협업 역할 또는 빈 문자열", "status": "new"}}

[날짜] {date}
[GM 날메모 원문]
{memo}
"""


def _extract_json_array(s: str) -> str:
    s = s.strip()
    m = re.search(r"```(?:json)?\s*(\[.*\])\s*```", s, re.DOTALL)
    return m.group(1) if m else s


def _read_memo(src: str) -> str:
    if src == "-":
        return sys.stdin.read()
    return Path(src).read_text(encoding="utf-8")


def organize(args) -> int:
    memo = _read_memo(args.in_)
    date = args.date or _dt.datetime.now(KST).strftime("%Y-%m-%d")
    source = args.source or "GM"
    prompt = _prompt(memo, source, date)
    text, model = model_router.run_claude(
        prompt, models=model_router.JUDGMENT_CHAIN, label="gm_directive_organize"
    )
    if not text:
        print("[실패] 정리 엔진(run_claude) 응답 없음 — 판단 체인 전멸", file=sys.stderr)
        return 1
    if SPLIT_MARK not in text:
        print(f"[실패] 응답에 {SPLIT_MARK} 구분자 없음 — 형식 위반", file=sys.stderr)
        return 1
    md_part, _, json_part = text.partition(SPLIT_MARK)
    md_part = md_part.strip()
    try:
        items = json.loads(_extract_json_array(json_part))
    except json.JSONDecodeError as e:
        print(f"[실패] JSON 파싱 실패: {e}", file=sys.stderr)
        return 1
    for it in items:
        it["trigger"] = _is_trigger(it.get("title", ""))  # 모델값 무시 · 제목 태그가 정본

    out_md = Path(args.out) if args.out else ROOT / "status" / "directives" / f"{date}_정리.md"
    out_json = out_md.with_suffix(".json")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md_part + "\n", encoding="utf-8")
    out_json.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[정리 완료] {out_md} ({len(items)}건 · 모델={model})")
    return 0


def _ledger_path() -> Path:
    # selfcheck 가 실제 원장을 더럽히지 않도록 env var 로 경로를 바꿔 끼울 수 있다(gm_asks.py 와 같은 패턴).
    override = os.environ.get("GM_DIRECTIVES_LEDGER_PATH")
    return Path(override) if override else LEDGER_PATH


def _load_ledger() -> dict:
    p = _ledger_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"items": []}
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return {"items": []}
    return data


def _save_ledger(data: dict) -> None:
    p = _ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _dispatch_cmd(item: dict, date: str, apply: bool) -> list[str] | None:
    """항목 하나 → queue_dispatch.py(AI) / gm_handoff.py(사람) 명령. 3-트리거·모르는
    역할은 None(자동 배포 제외)."""
    role = item.get("role", "")
    title = item.get("title", "")
    if _is_trigger(title):  # 사이드카에 남은 값 안 믿고 제목 태그로 재판정(방어적 이중 확인)
        return None
    dod = item.get("dod", "")
    source = item.get("source", "GM")
    py = sys.executable
    if role in AI_ROLES:
        cmd = [
            py, str(ROOT / "scripts" / "queue_dispatch.py"),
            "--to", AI_ROLES[role],
            "--title", f"{title} (GM {date})",
            "--note", f"GM 지시 {date}: {title} · 완료 기준: {dod}",
            "--next", dod,
            "--priority", "⛴️여객선", "--audience", "office",
            "--reversible", "yes", "--work-type", "update", "--gm-needed", "no",
        ]
        if AI_ROLES[role] == "ceo":
            cmd += ["--mine", "--waiting", f"GM 지시 {date}"]
    elif role in PEOPLE:
        cmd = [
            py, str(ROOT / "scripts" / "gm_handoff.py"),
            "--title", f"{title} (GM {date})",
            "--content", f"{title} · 완료 기준: {dod}",
            "--date", date,
            "--assignee", role,
            "--due", date,
            "--source", source,
            "--creator", "웰리",
        ]
    else:
        return None
    if not apply:
        cmd.append("--dry-run")
    return cmd


def publish(args) -> int:
    md_path = Path(args.md)
    items = json.loads(md_path.with_suffix(".json").read_text(encoding="utf-8"))
    date = args.date or _dt.datetime.now(KST).strftime("%Y-%m-%d")
    apply = bool(args.apply) and not args.dry_run

    ledger = _load_ledger()
    n_cmd = 0
    for item in items:
        cmd = _dispatch_cmd(item, date, apply)
        if cmd is None:
            tag = "[3-트리거 · GM 재확인 필요]" if _is_trigger(item.get("title", "")) else "[대상 아님]"
            print(f"{tag} #{item.get('id')} {item.get('role')} — {item.get('title')}")
            continue
        print(" ".join(cmd))
        n_cmd += 1
        status = "published"
        if apply:
            r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            print(r.stdout.strip())
            if r.returncode != 0:
                print(r.stderr.strip(), file=sys.stderr)
                status = "failed"
        else:
            status = "dry-run"
        ledger["items"].append({
            "id": item.get("id"), "date": date, "source": item.get("source", "GM"),
            "role": item.get("role"), "title": item.get("title"), "dod": item.get("dod"),
            "ship_no": None, "todo_id": None, "status": status, "carry_count": 0,
        })
    _save_ledger(ledger)
    print(f"[게시 {'완료' if apply else '미리보기'}] {n_cmd}건 명령 · 원장={_ledger_path()}")
    return 0


# ── selfcheck ────────────────────────────────────────────────────────────
_SAMPLE_MEMO = """웰리야 지시 자동화 파이프라인 좀 빨리 만들어줘. GM 지시방도 신설하고.
시토야 텔레그램 봇 수신 배선 해줘.
시토야 SSOT 게시 자동화도 같이 좀 해줘 (위 배선이랑 같은 건이다).
이번 달 카드값 승인 좀 해줘.
이경연 실장님한테는 이번주 금요일까지 CCTV 점검 결과 받아줘.
너무 힘든데 다들 고생 많다 화이팅.
아직 확정 안 된 건데 나중에 다시 얘기하자. 이건 미정.
"""


def _canned_response(_prompt: str) -> str:
    md = """26.9.18(금) 에이전트 지시사항 정리
■ 웰리
1. [GM 지시] 지시 자동화 파이프라인 구축
   완료 기준: SSOT에 게시되고 승인 흐름이 동작함
■ 시토
1. [GM 지시] 텔레그램 GM지시방 신설 + SSOT 게시 자동화 배선 (협업: 웰리)
   완료 기준: 방 개설·봇 수신·게시 자동화 확인
■ 시모
■ 시우
■ 시포
■ 시보
■ 미결 사항
1. [GM 지시] 이번 달 카드값 승인 ⛔GM 재확인(💰/🔒/🚫)
   완료 기준: GM 승인 확인
2. [GM 지시] 아직 확정 안 된 건 — 원문 미확정
   완료 기준: GM 재확인 후 확정
■ 사람 관리자
1. [GM 지시] 이경연 실장 — CCTV 점검 결과 취합
   완료 기준: 금요일까지 결과 수신
"""
    # trigger 값을 일부러 뒤집어 넣는다(2026-09-18 실측 그대로 재현: 태그 없는 23건이 true,
    # 태그 있는 1건이 false) — organize() 가 title 태그로 덮어써 바로잡는지 selfcheck 가 검증한다.
    items = [
        {"id": 1, "role": "웰리", "title": "지시 자동화 파이프라인 구축",
         "dod": "SSOT에 게시되고 승인 흐름이 동작함", "source": "GM", "trigger": True,
         "collab": "", "status": "new"},
        {"id": 2, "role": "시토", "title": "텔레그램 GM지시방 신설 + SSOT 게시 자동화 배선",
         "dod": "방 개설·봇 수신·게시 자동화 확인", "source": "GM", "trigger": True,
         "collab": "웰리", "status": "new"},
        # 실측 그대로: 모델이 태그를 통째로 안 쓰고 해당 아이콘만 남겨 줄인 변형
        {"id": 3, "role": "시토", "title": "이번 달 카드값 승인 ⛔GM 재확인(💰)",
         "dod": "GM 승인 확인", "source": "GM", "trigger": False, "collab": "", "status": "new"},
        {"id": 4, "role": "이경연 실장", "title": "CCTV 점검 결과 취합",
         "dod": "금요일까지 결과 수신", "source": "GM", "trigger": True, "collab": "", "status": "new"},
    ]
    return md + SPLIT_MARK + "\n```json\n" + json.dumps(items, ensure_ascii=False) + "\n```\n"


def selfcheck() -> int:
    orig = model_router.run_claude
    model_router.run_claude = lambda prompt, **kw: (_canned_response(prompt), "fake-model")
    scratch = ROOT / "status" / "directives" / "_selfcheck_정리.md"
    old_stdin_read = sys.stdin.read
    sys.stdin.read = lambda: _SAMPLE_MEMO
    old_ledger_env = os.environ.get("GM_DIRECTIVES_LEDGER_PATH")
    os.environ["GM_DIRECTIVES_LEDGER_PATH"] = str(scratch.with_name("_selfcheck_ledger.json"))
    try:
        rc = organize(argparse.Namespace(in_="-", source="GM", out=str(scratch), date="2026-09-18"))
        assert rc == 0, "organize 실패"
        md_text = scratch.read_text(encoding="utf-8")
        for role in AI_ROLES:
            assert f"■ {role}" in md_text, f"{role} 섹션 없음"
        assert "완료 기준:" in md_text, "완료 기준 누락"
        items = json.loads(scratch.with_suffix(".json").read_text(encoding="utf-8"))
        assert any(i["trigger"] for i in items), "결제 트리거 항목 미표시"
        assert any(i["role"] == "시토" and "배선" in i["title"] for i in items), "중복 병합 실패"
        # 모델이 준 trigger 는 일부러 뒤집어 넣었다(_canned_response, #3 은 축약 태그 「⛔GM 재확인(💰)」
        # 변형) — organize() 가 title 의 ⛔로 되잡는지 검증. 태그 없는 항목은 반드시 false.
        for i in items:
            assert i["trigger"] == _is_trigger(i["title"]), f"trigger 판정 오류: {i['title']}"
        assert next(i for i in items if i["id"] == 3)["trigger"] is True, "축약 태그(⛔GM 재확인(💰)) 못 잡음"

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc2 = publish(argparse.Namespace(md=str(scratch), date="2026-09-18", dry_run=False, apply=False))
        assert rc2 == 0, "publish 실패"
        out = buf.getvalue()
        n_cmds = out.count("queue_dispatch.py") + out.count("gm_handoff.py")
        assert n_cmds >= 3, f"명령 수 부족: {n_cmds}"
    finally:
        model_router.run_claude = orig
        sys.stdin.read = old_stdin_read
        if old_ledger_env is None:
            os.environ.pop("GM_DIRECTIVES_LEDGER_PATH", None)
        else:
            os.environ["GM_DIRECTIVES_LEDGER_PATH"] = old_ledger_env
        scratch.unlink(missing_ok=True)
        scratch.with_suffix(".json").unlink(missing_ok=True)
        Path(scratch.with_name("_selfcheck_ledger.json")).unlink(missing_ok=True)
    print(f"[selfcheck 통과] 섹션 6종·완료기준·트리거 표시·중복 병합 확인 · publish 명령 {n_cmds}건")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="GM 지시 정리 엔진 — organize(정리) / publish(배포) / selfcheck")
    sub = p.add_subparsers(dest="cmd", required=True)

    po = sub.add_parser("organize", help="GM 날메모 → 표준 정리본 + JSON 사이드카")
    po.add_argument("--in", dest="in_", required=True, help="메모 파일 경로 또는 '-'(stdin)")
    po.add_argument("--source", choices=["회장님", "대표님", "GM"], default="GM")
    po.add_argument("--out", help="정리본 .md 출력 경로(기본 status/directives/<date>_정리.md)")
    po.add_argument("--date", help="YYYY-MM-DD(기본 오늘 KST)")

    pp = sub.add_parser("publish", help="정리본 JSON → 배·업무SSOT 배포")
    pp.add_argument("--md", required=True, help="organize 로 만든 .md(같은 이름 .json 사이드카를 읽는다)")
    pp.add_argument("--date", help="YYYY-MM-DD(기본 오늘 KST)")
    pp.add_argument("--dry-run", action="store_true", help="명령만 미리 출력(기본값과 동일 · 명시용)")
    pp.add_argument("--apply", action="store_true", help="실제로 실행")

    sub.add_parser("selfcheck", help="고정 표본으로 organize+publish 자체점검")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.cmd == "organize":
        return organize(args)
    if args.cmd == "publish":
        return publish(args)
    if args.cmd == "selfcheck":
        return selfcheck()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
