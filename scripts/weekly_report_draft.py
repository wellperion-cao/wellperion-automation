# -*- coding: utf-8 -*-
"""주간 리포트 초안 자동 생성 — 3라인 직책체계 §7 (배860 시토 2026-09-01 · 원천 연결 웰리 결정 2026-09-08)

매주 월 07:00, monthly_ops_sync.bat 말미에서 호출된다(새 예약작업 없음 · 약속 L21).
월요일이 아니면 그냥 종료한다. --force 로 아무 요일이나 미리보기(발송 없음).

양식 = docs/3라인_직책체계_20260831.md §7 (4항목). 원천(웰리 결정 2026-09-08):
  ① 전결 처리 건   — 업무·결재 SSOT(GAS todo_list) 중 담당 '김남욱' 또는 생성자 GM 인 행이
                     지난주(월~일) 완료된 것. 전사일정 이벤트 나열 아님.
  ② 회장님 판단 필요 건 — 같은 todo_list 에서 결재요청에 '회장'·'대표'가 들어있고 미완료인 행.
  ③ 지적사항 처리 결과 — 회장님 지시 원장(coo/chairman/_chairman_items.js = 아직 미보고 건 목록 ·
                     chairman_reported.json = 보고 완료일). 열린 건 전부 + 지난주 보고 완료 건.
  ④ 다음 주 예정   — 전사일정 next_due 오늘~+7일. 담당에 '회장님' 있으면 ★ 상단.

발신 = scripts/notify/telegram_send.send(정본 관문 · tg_outbound_log 경유) 업무 보고 방(8254867551)
으로. 기본 dry-run, --send 일 때만 나간다. --date YYYY-MM-DD 로 기준일 지정(테스트·지난주 재발송용).
이 초안은 GM 검수 후 회장님께 나간다 — 자동 회장님 발송 아님.
"""
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    from collectors.ops_shared import TODO_DONE_STATUSES, gas_get as _gas_get, SSOT_API_URL
except ImportError:
    sys.path.insert(0, str(ROOT / "scripts"))
    from collectors.ops_shared import TODO_DONE_STATUSES, gas_get as _gas_get, SSOT_API_URL

SCHEDULE = ROOT / "status" / "schedule_ssot.json"
CHAIRMAN_DIR = ROOT / "3. 웰페리온 가이드" / "coo" / "chairman"
CHAIRMAN_ITEMS_JS = CHAIRMAN_DIR / "_chairman_items.js"
CHAIRMAN_REPORTED_JSON = CHAIRMAN_DIR / "chairman_reported.json"
DRAFT_DIR = ROOT / "status" / "drafts"
MAX_LINES = 15  # 섹션당 표시 상한 — 넘치면 「외 N건」으로 전사일정 화면을 가리킨다
SCHEDULE_URL = "https://wellperion-cao.github.io/wellperion-automation/coo/check/%EC%A0%84%EC%82%AC_%EC%9D%BC%EC%A0%95.html"
WD_KOR = "월화수목금토일"
GM_CHAT_ID = 8254867551  # 업무보고방 SSOT(ssot/canon_values.json telegram_chat_id)
GM_KEY = "1531"  # gm_handoff.py 와 동일 — 없으면 GM 행이 todo_list 조회에서 빠진다
GM_CREATOR = "김남욱GM"


def _load_items():
    data = json.loads(SCHEDULE.read_text(encoding="utf-8"))
    return data.get("items", [])


def _parse_due(item):
    raw = (item.get("next_due") or "").strip()[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _fmt(item, due):
    who = (item.get("assignee") or "").strip()
    t = (item.get("time") or "").strip()
    parts = [f"{due.month}/{due.day}({WD_KOR[due.weekday()]})"]
    if t:
        parts.append(t)
    parts.append((item.get("name") or "(이름 없음)").strip())
    line = " ".join(parts)
    if who:
        line += f" — {who}"
    return "· " + line


def _section(lines):
    if not lines:
        return ["· (해당 없음)"]
    shown = lines[:MAX_LINES]
    if len(lines) > MAX_LINES:
        shown.append(f"· 외 {len(lines) - MAX_LINES}건 — 전사일정 화면 참조")
    return shown


# ── ①②: 업무·결재 SSOT(GAS todo_list) ────────────────────────────────────
def _todo_rows():
    """업무·결재 SSOT 전체 행. gmkey 없으면 GM 행이 조회에서 빠진다(gm_handoff.py 와 동일 관문).
    실패하면 None — 호출부가 그 사실을 그대로 표기한다(지어내지 않는다)."""
    resp = _gas_get(SSOT_API_URL, params={"action": "todo_list", "include_gm": "1", "gmkey": GM_KEY},
                     timeout=40, label="weekly_report todo_list")
    if resp is None:
        return None
    try:
        data = resp.json()
        return (data.get("data") or []) if data.get("ok") else None
    except Exception:
        return None


def _last_content_line(text, limit=60):
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    line = lines[-1] if lines else ""
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _row_date(row, *keys):
    for k in keys:
        raw = str(row.get(k) or "").strip()[:10]
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            continue
    return None


def _build_gm_done(rows, last_mon, last_sun):
    out = []
    for r in rows:
        if "김남욱" not in str(r.get("담당자", "")) and str(r.get("생성자", "")) != GM_CREATOR:
            continue
        if str(r.get("상태", "")) not in TODO_DONE_STATUSES:
            continue
        done = _row_date(r, "완료일", "수정일", "종료일")
        if done is None or not (last_mon <= done <= last_sun):
            continue
        line = f"· {r.get('업무명', '(제목 없음)')} — {_last_content_line(r.get('내용'))}"
        appr = str(r.get("결재요청", "")).strip()
        if appr:
            line += f" (결재: {appr})"
        out.append((done, line))
    return [line for _, line in sorted(out)]


def _build_chairman_pending(rows):
    out = []
    for r in rows:
        appr = str(r.get("결재요청", ""))
        if "회장" not in appr and "대표" not in appr:
            continue
        if str(r.get("상태", "")) in TODO_DONE_STATUSES:
            continue
        due = str(r.get("종료일", "")).strip()[:10] or "기한 미정"
        out.append(f"· {r.get('업무명', '(제목 없음)')} — {appr} · {due}")
    return out


# ── ③: 회장님 지시 원장(coo/chairman) ──────────────────────────────────────
_CHAIRMAN_ENTRY_RE = re.compile(
    r'\{\s*id:\s*"([^"]+)"\s*,\s*title:\s*"((?:[^"\\]|\\.)*)"\s*,\s*when:\s*"((?:[^"\\]|\\.)*)"'
)
_CHAIRMAN_DATE_RE = re.compile(r"GM\s*전달\s*(\d{4})-(\d{2})-(\d{2})")
_CHAIRMAN_STATUS_TOKENS = ("진행 중", "대기", "미정")


def _chairman_status_line(cid, title, when):
    status = next((t.replace(" ", "") for t in _CHAIRMAN_STATUS_TOKENS if t in when), "확인필요")
    m = _CHAIRMAN_DATE_RE.search(when)
    reg = f"{int(m.group(2))}/{int(m.group(3))}" if m else "미상"
    return f"· {title} — {status} · 등재 {reg}"


def _chairman_done_title(raw_text, cid):
    """보고 완료된 건은 목록(_chairman_items.js)에서 빠진다 — 남는 건 등재 당시 주석뿐이라
    'dNN(제목)' 패턴으로만 찾는다. 없으면 지어내지 않고 미상으로 표기한다."""
    m = re.search(rf"{re.escape(cid)}\(([^)]+)\)", raw_text)
    return m.group(1) if m else "제목 미상(목록에서 이미 빠짐)"


def _build_chairman_section(last_mon, last_sun):
    try:
        raw = CHAIRMAN_ITEMS_JS.read_text(encoding="utf-8")
        reported = json.loads(CHAIRMAN_REPORTED_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"· 원천 읽기 실패 — {e}"]
    open_lines = [_chairman_status_line(cid, title, when)
                  for cid, title, when in _CHAIRMAN_ENTRY_RE.findall(raw)]
    done = []
    for cid, d in reported.items():
        if cid.startswith("_"):
            continue
        dd = _row_date({"d": d}, "d")
        if dd is not None and last_mon <= dd <= last_sun:
            done.append((dd, f"· {_chairman_done_title(raw, cid)} — 완료 {dd.month}/{dd.day}"))
    lines = open_lines + [line for _, line in sorted(done)]
    return lines or ["· 열린 건 없음"]


def _mark_star(line):
    return "· ★" + line[1:] if line.startswith("· ") else line


def build_draft(today=None):
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())  # 이번 주 월요일
    last_mon, last_sun = monday - timedelta(days=7), monday - timedelta(days=1)
    week_end = today + timedelta(days=6)

    upcoming = []
    for it in _load_items():
        due = _parse_due(it)
        if due is None:
            continue
        if today <= due <= week_end:
            key = (due, (it.get("time") or "").strip())
            upcoming.append((key, it, _fmt(it, due)))
    upcoming.sort(key=lambda x: x[0])
    upcoming_lines = (
        [_mark_star(line) for _, it, line in upcoming if "회장님" in (it.get("assignee") or "")]
        + [line for _, it, line in upcoming if "회장님" not in (it.get("assignee") or "")]
    )

    todo_rows = _todo_rows()
    if todo_rows is None:
        gm_done_lines = ["· 원천 읽기 실패 — 업무·결재 SSOT(todo_list) 조회 실패"]
        chairman_pending_lines = ["· 원천 읽기 실패 — 업무·결재 SSOT(todo_list) 조회 실패"]
    else:
        gm_done_lines = _build_gm_done(todo_rows, last_mon, last_sun) or ["· 지난주 완료된 GM 업무 없음(업무 SSOT 기준)"]
        chairman_pending_lines = _build_chairman_pending(todo_rows) or ["· 없음"]

    lines = [
        f"📋 주간 리포트 초안 — {today.month}/{today.day}({WD_KOR[today.weekday()]}) · 회장님 보고용",
        "(자동 초안입니다 — GM 검수 후 발송해 주세요. 회장님께 자동으로 나가지 않습니다)",
        "",
        "① 전결 처리 건 — 지난주(월~일) 완료된 GM 업무(업무·결재 SSOT 기준)",
        *_section(gm_done_lines),
        "",
        "② 회장님 판단 필요 건 — 결재 라인에 회장/대표 포함 · 미완료(업무·결재 SSOT 기준)",
        *_section(chairman_pending_lines),
        "",
        "③ 지적사항 처리 결과 — 회장님 지시 원장(coo/chairman) 기준",
        *_section(_build_chairman_section(last_mon, last_sun)),
        "",
        "④ 다음 주 예정 — 전사일정 (회장님 담당 건은 ★ 상단)",
        *_section(upcoming_lines),
        "",
        f"📎 전사일정 {SCHEDULE_URL}",
        "📄 양식 정본 docs/3라인_직책체계_20260831.md §7",
    ]
    return "\n".join(lines)


def main(argv):
    force = "--force" in argv
    send = "--send" in argv
    today = date.today()
    if "--date" in argv:
        today = datetime.strptime(argv[argv.index("--date") + 1], "%Y-%m-%d").date()
    if today.weekday() != 0 and not force:
        print(f"[skip] 월요일 아님({today}) — 초안 생성 안 함")
        return 0

    text = build_draft(today)
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    out = DRAFT_DIR / f"weekly_report_{today.strftime('%Y%m%d')}.md"
    out.write_text(text + "\n", encoding="utf-8")
    print(f"[ok] 초안 저장 {out}")

    if send:
        from notify.telegram_send import send as tg_send  # noqa: PLC0415 — 정본 발신 관문
        ok = tg_send(GM_CHAT_ID, text)
        print(f"[ok] 업무 보고 방 발신 {'완료' if ok else '실패'}")
    else:
        print(text)
    return 0


def _self_check():
    # 최소 자가검증 — 발송 없음. 새 필터링 로직(순수 함수)은 가짜 행으로 오프라인 검증.
    last_mon, last_sun = date(2026, 8, 31), date(2026, 9, 6)
    done_rows = [
        {"담당자": "김남욱 GM", "상태": "완료", "수정일": "2026-09-02", "업무명": "테스트건",
         "내용": "1줄\n마지막 줄", "결재요청": "GM"},
        {"담당자": "이경연 실장", "상태": "완료", "수정일": "2026-09-02", "업무명": "실장건", "내용": "x"},
        {"담당자": "김남욱 GM", "상태": "진행중", "수정일": "2026-09-02", "업무명": "미완료건", "내용": "x"},
    ]
    done = _build_gm_done(done_rows, last_mon, last_sun)
    assert len(done) == 1 and "테스트건" in done[0] and "마지막 줄" in done[0], done

    pend_rows = [
        {"결재요청": "회장,대표", "상태": "진행중", "업무명": "결재대기건", "종료일": "2026-09-10"},
        {"결재요청": "회장", "상태": "완료", "업무명": "이미완료건"},
    ]
    pend = _build_chairman_pending(pend_rows)
    assert len(pend) == 1 and "결재대기건" in pend[0], pend

    assert _chairman_status_line("d1", "제목", "GM 전달 2026-08-31 · 진행 중") == "· 제목 — 진행중 · 등재 8/31"

    # 통합 — todo_list 조회는 실패해도 build_draft 가 「원천 읽기 실패」로 죽지 않고 넘어가야 한다.
    text = build_draft(date(2026, 9, 7))
    for token in ("① 전결 처리 건", "② 회장님 판단", "③ 지적사항", "④ 다음 주 예정"):
        assert token in text, token
    print("[self-check ok]")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        sys.exit(main(sys.argv[1:]))
